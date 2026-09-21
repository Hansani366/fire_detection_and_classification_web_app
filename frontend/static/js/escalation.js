/* ═══════════════════════════════════════════════════════════
   ESCALATION LADDER

   Replaces the dashboard's single "YOLO and VLM agree" rule with four
   levels, so the response matches how strong the evidence is:

     1a  warning  gas above normal, nothing visible     → message, NO siren
     1b  danger   dangerous gas, still nothing visible  → siren
     2   fire     camera + VLM agree                    → siren, incident
     3   classified  sensors agree too                  → fuel type added

   WHY TIER 1a MUST NOT SOUND THE ALARM. Gas sensors react to cooking,
   aerosols, solvents and vehicle exhaust. A warning that sounded the
   fire alarm would teach people to ignore the fire alarm — and the one
   that matters is the one they then miss.

   WHY TIER 1b EXISTS ANYWAY. The MQ-7 measures carbon monoxide. It is
   invisible and odourless, a camera will never see it, and at the
   danger threshold it is lethal to someone asleep. That case has to be
   able to wake people without waiting for a flame.

   WHY TIER 3 IS NOT A SEPARATE EVENT. Gas reaches the sensor 14–22 s
   after a camera sees the flame, so "all three agree" is almost always
   tier 2 arriving late with better information. It upgrades the open
   incident; alert-service does the same thing on its side.

   Classic script, attaches to window — same convention as
   camera-sources.js and sensor-panel.js.
═══════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  // A level must hold this many consecutive sensor polls before it counts.
  // The panel polls every 2 s, so this is ~6 s of agreement — long enough to
  // ride out one bad reading, short enough to matter.
  var STRIKES = 3;

  // Matches alert-service's COOLDOWN_SECONDS. Without it, a reading sitting
  // just over the threshold would send a notification every poll.
  var WARNING_COOLDOWN_MS = 120000;

  // The classifier needs a clean-air baseline and then time for its rolling
  // features to fill. Asking before that yields confident nonsense.
  var CLASSIFY_INTERVAL_MS = 1000;

  var RANK = { unknown: 0, normal: 1, warn: 2, danger: 3 };

  var S = {
    zoneId: 'fabric-store',
    running: false,
    // sensors
    level: 'unknown', candidate: 'unknown', strikes: 0, summary: '', nodes: [],
    // vision, pushed in by the detection loop
    yoloHit: false, vlmConfirmed: false, vlmAvailable: true, vlm: null, occupancy: null,
    // outputs
    tier: 'clear', alarm: false, reported: false,
    warningSentAt: 0, warningText: '',
    classification: null, classifySentFor: null,
    session: null, classifyTimer: null, classifyBusy: false,
    captureFrame: null, onChange: null,
  };

  function post(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  /* ── sensors in ───────────────────────────────────────── */

  function onSensors(payload) {
    if (!payload || !payload.nodes || !payload.nodes.length) {
      applyLevel('unknown', '', []);
      return;
    }
    // Worst node wins. One room on fire is not averaged away by three quiet
    // ones — the grading already happened in esp32-sensor-service, which is
    // the single place thresholds are defined.
    var worst = 'normal';
    var offenders = [];
    payload.nodes.forEach(function (n) {
      var lvl = n.status === 'stale' ? 'unknown' : (n.worstLevel || 'unknown');
      if (RANK[lvl] > RANK[worst]) worst = lvl;
      if (lvl === 'warn' || lvl === 'danger') offenders.push(n);
    });
    applyLevel(worst, summarise(payload, offenders), payload.nodes);
  }

  function summarise(payload, offenders) {
    // A line a person can read on a lock screen without opening the app, and
    // the same line the warning generator is asked to explain.
    var parts = [];
    (offenders.length ? offenders : payload.nodes).slice(0, 2).forEach(function (n) {
      (n.sensors || []).forEach(function (t) {
        if (t.level === 'warn' || t.level === 'danger') {
          parts.push(t.label + ' ' + (t.text || t.value) + (t.unit ? ' ' + t.unit : '') +
                     ' (' + t.level + ')');
        }
      });
    });
    return parts.join(', ');
  }

  function applyLevel(level, summary, nodes) {
    S.summary = summary;
    S.nodes = nodes;
    if (level === S.candidate) {
      if (S.strikes < STRIKES) S.strikes++;
    } else {
      S.candidate = level;
      S.strikes = 1;
    }
    // A level only becomes real once it has held. Dropping back to something
    // calmer is allowed immediately — being too quick to relax is safe, being
    // too quick to alarm is not.
    if (S.strikes >= STRIKES || RANK[level] < RANK[S.level]) S.level = level;
    evaluate();
  }

  /* ── vision in ────────────────────────────────────────── */

  function onVision(v) {
    S.yoloHit = !!v.yoloHit;
    S.vlmConfirmed = !!v.vlmConfirmed;
    S.vlmAvailable = v.vlmAvailable !== false;
    S.vlm = v.vlm || null;
    if (v.occupancy !== undefined) S.occupancy = v.occupancy;
    evaluate();
  }

  /* ── the ladder ───────────────────────────────────────── */

  function decide() {
    var gassy = S.level === 'warn' || S.level === 'danger';

    // Tier 2. The deployed rule, unchanged — plus one addition: if the VLM is
    // unreachable but YOLO and the sensors both say fire, that is still strong
    // evidence. Today a VLM outage silently disables the alarm entirely.
    if (S.yoloHit && (S.vlmConfirmed || (!S.vlmAvailable && gassy))) return 'fire';

    // Tier 1b. Nothing visible, but the gas is at a level that can kill.
    if (S.level === 'danger') return 'danger';

    // Tier 1a. Rising, but not dangerous and not visible.
    if (S.level === 'warn') return 'warning';

    return 'clear';
  }

  function evaluate() {
    if (!S.running) return;
    var next = decide();
    var was = S.tier;
    S.tier = next;
    S.alarm = next === 'fire' || next === 'danger';

    if (next === 'warning') sendWarning();
    if (S.alarm && !S.reported) { S.reported = true; sendFire(next); }
    if (!S.alarm && S.reported) { S.reported = false; sendClear(); }

    if (next !== was && S.onChange) S.onChange(state());
  }

  /* ── tier 1a: the quiet warning ───────────────────────── */

  function sendWarning() {
    var now = Date.now();
    if (now - S.warningSentAt < WARNING_COOLDOWN_MS) return;
    S.warningSentAt = now;

    var readings = S.summary || 'gas readings above the normal baseline';
    // Text in, text out — no image. At tier 1a there is by definition nothing
    // to see, so asking the VLM to look at an empty room would return "no
    // fire" and tell nobody anything.
    fetch('/api/warn', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ readings: readings, zone: S.zoneId, level: S.level }),
    })
      .then(function (r) { return r.json(); })
      .catch(function () { return { message: 'Gas readings above normal. No fire seen.' }; })
      .then(function (out) {
        S.warningText = out.message;
        if (S.onChange) S.onChange(state());
        return post('/api/events/warning', {
          zoneId: S.zoneId,
          description: out.message,
          sensorSummary: readings,
          occupancy: S.occupancy,
        });
      })
      .catch(function (e) { console.warn('[escalation] warning failed', e); });
  }

  /* ── tier 2 / 1b: the alarm ───────────────────────────── */

  function sendFire(tier) {
    var vlm = S.vlm || {};
    var description = tier === 'danger'
      // Tier 1b has no picture to describe, so the readings ARE the report.
      ? 'Dangerous gas levels with nothing visible on camera. ' + (S.summary || '')
      : (vlm.description || 'Fire or smoke confirmed on camera.') +
        (S.vlmAvailable ? '' : ' (VLM unavailable — confirmed by camera and sensors.)');

    post('/api/events/fire', {
      zoneId: S.zoneId,
      type: tier === 'danger' ? 'smoke' : (vlm.type || 'fire'),
      confidence: tier === 'danger' ? 0.0 : (vlm.confidence || 0.9),
      description: description,
      occupancy: S.occupancy,
    }).catch(function (e) { console.warn('[escalation] fire report failed', e); });
  }

  function sendClear() {
    S.classification = null;
    S.classifySentFor = null;
    post('/api/events/clear', { zoneId: S.zoneId })
      .catch(function (e) { console.warn('[escalation] clear failed', e); });
  }

  /* ── tier 3: what is burning ──────────────────────────── */

  async function startSession() {
    try {
      // fire-classification-service, NOT ablation-service. The live alarm
      // must not depend on a research tool: changing the ablation page should
      // never be able to break the thing that wakes people up.
      var r = await post('/api/classify/sessions', {
        zoneId: S.zoneId, sensor_source: 'node', baseline_mode: 'quiet_prefix',
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      S.session = (await r.json()).session_id;
    } catch (e) {
      console.warn('[escalation] no classifier session', e.message);
      S.session = null;
    }
  }

  async function classifyTick() {
    // Only while a fire is actually open AND the sensors agree. Classifying a
    // scene the sensors cannot corroborate would be the fusion model guessing
    // from vision alone, which is the one thing it is worst at.
    if (S.classifyBusy || !S.session || S.tier !== 'fire') return;
    if (S.level !== 'warn' && S.level !== 'danger') return;
    if (!S.captureFrame) return;

    S.classifyBusy = true;
    try {
      var blob = await S.captureFrame();
      if (!blob) return;
      var form = new FormData();
      form.append('file', blob, 'frame.jpg');
      form.append('frame_w', 640);
      form.append('frame_h', 480);
      var r = await fetch('/api/classify/sessions/' + S.session + '/tick',
                          { method: 'POST', body: form });
      if (!r.ok) return;
      var tick = await r.json();

      if (tick.baselining) {
        // Say why there is no answer yet rather than leaving a blank that
        // looks like a bug.
        report(null, null, 'unavailable',
               'sensors still warming up (' + Math.ceil(tick.baseline_remaining_s) + 's)');
        return;
      }
      var fuel = tick.fuel;
      if (!fuel || !fuel.predictedClass || fuel.predictedClass === 'no_fire') return;
      report(fuel.predictedClass, fuel.confidence, 'model',
             fuel.lowConfidence ? 'low confidence' : '');
    } catch (e) {
      console.warn('[escalation] classify failed', e.message);
    } finally {
      S.classifyBusy = false;
    }
  }

  function report(fuel, confidence, source, note) {
    var key = source + ':' + (fuel || '');
    S.classification = { fuelType: fuel, confidence: confidence, source: source, note: note };
    if (S.onChange) S.onChange(state());
    // Only tell alert-service when the answer changes. The dashboard asks
    // every second; the responder needs the verdict, not a heartbeat.
    if (key === S.classifySentFor) return;
    S.classifySentFor = key;
    post('/api/events/classification', {
      zoneId: S.zoneId, fuelType: fuel, confidence: confidence,
      source: source, occupancy: S.occupancy,
    }).catch(function (e) { console.warn('[escalation] classification failed', e); });
  }

  /* ── lifecycle ────────────────────────────────────────── */

  function state() {
    return {
      tier: S.tier, alarm: S.alarm, sensorLevel: S.level,
      sensorSummary: S.summary, warningText: S.warningText,
      classification: S.classification, vlmAvailable: S.vlmAvailable,
      classifierReady: !!S.session,
    };
  }

  function configure(opts) {
    if (opts.zoneId) S.zoneId = opts.zoneId;
    if (opts.captureFrame) S.captureFrame = opts.captureFrame;
    if (opts.onChange) S.onChange = opts.onChange;
  }

  function start() {
    if (S.running) return;
    S.running = true;
    S.reported = false;
    startSession();
    S.classifyTimer = setInterval(classifyTick, CLASSIFY_INTERVAL_MS);
  }

  function stop() {
    if (!S.running) return;
    S.running = false;
    clearInterval(S.classifyTimer); S.classifyTimer = null;
    if (S.reported) { S.reported = false; sendClear(); }
    if (S.session) {
      fetch('/api/classify/sessions/' + S.session, { method: 'DELETE' }).catch(function () {});
      S.session = null;
    }
    S.tier = 'clear'; S.alarm = false; S.yoloHit = false;
    S.vlmConfirmed = false; S.classification = null;
    if (S.onChange) S.onChange(state());
  }

  global.Escalation = {
    configure: configure, start: start, stop: stop,
    onSensors: onSensors, onVision: onVision, state: state,
    STRIKES: STRIKES,
  };
})(window);
