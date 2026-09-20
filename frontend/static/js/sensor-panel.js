/* ═══════════════════════════════════════════════════════════
   FireWatch AI — ESP32 sensor panel

   Polls /api/sensors/latest and renders one card body per node.

   The bridge grades every reading (normal / warn / danger) against
   thresholds it owns, so this file only maps a level to a colour.
   Keeping the judgement server-side means the alerting path can
   reuse it later without the thresholds living in two places.

   Loaded as a classic script (the dashboard's main script is inline
   and non-module) and exposed as window.SensorPanel.
═══════════════════════════════════════════════════════════ */
(function (global) {
"use strict";

const POLL_MS = 2000;

/* Two consecutive failures before the panel calls the bridge down — a single
   dropped poll during a compose restart should not blank a healthy panel.
   Same reasoning as the camera watchdog's strike count. */
const MAX_STRIKES = 2;

const state = {
  timerId:  null,
  strikes:  0,
  inFlight: false,   // a slow poll must not overlap the next tick
  els:      null,
  onUpdate: null,
};


/* ── Helpers ─────────────────────────────────────────────── */

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* Significant digits by magnitude: 812 ppm needs no decimal, 12.4 ppm does. */
function fmtValue(s) {
  if (s.text != null) return s.text;          // binary sensors carry their own words
  if (s.value == null) return '—';
  const v = Math.abs(s.value);
  const dp = v >= 100 ? 0 : 1;
  return s.value.toFixed(dp);
}

/* "fabric-store" → "Fabric Store". The bridge stays decoupled from
   alert-service's zone catalog, so the prettifying happens here. */
function zoneLabel(id) {
  return String(id || '')
    .split('-')
    .filter(Boolean)
    .map(w => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

function ageLabel(ms) {
  if (ms == null) return '';
  if (ms < 1000)  return 'just now';
  const s = Math.round(ms / 1000);
  if (s < 60) return s + 's ago';
  return Math.round(s / 60) + 'm ago';
}


/* ── Rendering ───────────────────────────────────────────── */

function tileHtml(s) {
  const unit = s.unit ? '<span class="sn-unit">' + esc(s.unit) + '</span>' : '';
  return (
    '<div class="sn-tile lv-' + esc(s.level) + '">' +
      '<div class="sn-tile-head">' +
        '<span class="sn-label">' + esc(s.label) + '</span>' +
        '<span class="sn-module">' + esc(s.module) + '</span>' +
      '</div>' +
      '<div class="sn-value">' + esc(fmtValue(s)) + unit + '</div>' +
    '</div>'
  );
}

function nodeHtml(node) {
  const stale = node.status !== 'ok';

  /* Stale nodes keep their numbers on screen but dimmed: blanking them loses
     the last-known reading, which is the useful thing when a node drops. The
     dimming plus the timestamp is what stops them being read as current. */
  const statusCls  = stale ? 'stale' : 'live';
  const statusText = stale ? 'Stale · ' + ageLabel(node.ageMs) : 'Live';

  const meta = [];
  if (node.mock)          meta.push('mock data');
  if (node.rssi != null)  meta.push(node.rssi + ' dBm');
  if (node.seq != null)   meta.push('#' + node.seq);

  return (
    '<div class="sn-node' + (stale ? ' is-stale' : '') + '">' +
      '<div class="sn-node-head">' +
        '<span class="sn-node-id">' + esc(node.deviceId) + '</span>' +
        '<span class="sn-node-zone">' + esc(zoneLabel(node.zoneId)) + '</span>' +
        '<span class="sn-node-state ' + statusCls + '">' +
          '<span class="svc-dot ' + (stale ? 'err' : 'ok') + '"></span>' + esc(statusText) +
        '</span>' +
      '</div>' +
      '<div class="sn-grid">' + node.sensors.map(tileHtml).join('') + '</div>' +
      (meta.length ? '<div class="sn-node-meta">' + esc(meta.join(' · ')) + '</div>' : '') +
    '</div>'
  );
}

function renderEmpty(msg, hint) {
  state.els.body.innerHTML =
    '<div class="sn-empty">' +
      '<span class="sn-empty-title">' + esc(msg) + '</span>' +
      (hint ? '<span class="sn-empty-hint">' + esc(hint) + '</span>' : '') +
    '</div>';
}

function setHeadState(kind, text) {
  const el = state.els.status;
  if (!el) return;
  el.className = 'sn-head-state ' + kind;
  el.innerHTML = '<span class="svc-dot ' + kind + '"></span>' + esc(text);
}

function render(data) {
  const nodes = data.nodes || [];

  if (!nodes.length) {
    setHeadState('idle', 'No nodes');
    renderEmpty(
      'No sensor nodes reporting',
      'Power on an ESP32 node, or run tools/mock_sender.py to simulate one'
    );
    return;
  }

  const live = nodes.filter(n => n.status === 'ok').length;
  setHeadState(live ? 'ok' : 'err', live + '/' + nodes.length + ' online');
  state.els.body.innerHTML = nodes.map(nodeHtml).join('');
}


/* ── Polling ─────────────────────────────────────────────── */

async function poll() {
  if (state.inFlight) return;       // previous poll still out; skip this tick
  state.inFlight = true;
  try {
    const res = await fetch('/api/sensors/latest', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();

    state.strikes = 0;
    render(data);
    if (state.onUpdate) state.onUpdate(data);
  } catch (err) {
    if (++state.strikes >= MAX_STRIKES) {
      setHeadState('err', 'Bridge down');
      renderEmpty(
        'Sensor bridge unreachable',
        'Is esp32-sensor-service running? docker compose ps esp32-sensor-service'
      );
      if (state.onUpdate) state.onUpdate(null);
    }
  } finally {
    state.inFlight = false;
  }
}

/* The panel runs independently of Start/Stop Monitoring: the nodes push whether
   or not the camera pipeline is up, and a sensor reading is worth seeing even
   when nobody is watching the video. */
function start(els, onUpdate) {
  stop();
  state.els      = els;
  state.onUpdate = onUpdate || null;
  state.strikes  = 0;
  setHeadState('idle', 'Connecting…');
  poll();
  state.timerId = setInterval(poll, POLL_MS);
}

function stop() {
  clearInterval(state.timerId);
  state.timerId = null;
}

global.SensorPanel = { start, stop, POLL_MS };

})(window);
