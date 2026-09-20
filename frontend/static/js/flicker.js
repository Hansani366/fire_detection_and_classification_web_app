/* ═══════════════════════════════════════════════════════════
   FLAME FLICKER METER

   Estimates flame_flicker_hz, one of the six YOLO channels the fusion
   model reads. Real flame flickers at roughly 1–3 Hz; sunlight glare
   and reflections sit near zero. That difference is the whole point of
   the channel: it is what separates a fire from a bright light.

   WHY IT SAMPLES AT 16 Hz AND NOT AT THE DETECTION RATE. This is the
   one thing that cannot be compromised. The dashboard's detection loop
   runs at 2 Hz, whose Nyquist limit is 1 Hz. Sampling brightness there
   would alias a 2.1 Hz flame down to about 0.1 Hz — which is exactly
   the value the training generator emits for "nothing there". The
   feature would report "no flame" on every real flame, and it would
   look entirely plausible doing it. At 16 Hz the Nyquist limit is 8 Hz,
   which covers the model's full 0–6 Hz range with room to spare.

   WHY IT MEASURES INSIDE THE FIRE BOXES, NOT THE WHOLE FRAME. The
   generator conditions flicker on flame being visible. Whole-frame
   luminance is dominated by room lighting, and a flame occupying 3% of
   the frame would not move it.

   WHY AN FFT AND NOT ZERO CROSSINGS. Flame luminance is not zero-mean,
   carries strong DC, and trends upward as the fire grows; turbulence
   adds many small local reversals that inflate a crossing count. A
   detrended, windowed spectrum separates "a peak at 2 Hz" from "noise
   everywhere", which is precisely the glare-versus-flame question.

   Classic script, attaches to window — same convention as
   camera-sources.js and sensor-panel.js, because the pages that use it
   run non-module inline scripts.
═══════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  // Mirrored in ablation-service/constants.py. Change both together —
  // the browser measures this channel and the service consumes it.
  var SAMPLE_HZ = 16;
  var WINDOW_N = 64;                       // 4.0 s at 16 Hz
  var BIN_HZ = SAMPLE_HZ / WINDOW_N;       // 0.25 Hz resolution
  var MAX_HZ = 6.0;
  var PEAK_RATIO = 3.0;                    // peak must beat 3x the median bin
  var QUIET_HZ = 0.1;                      // the generator's "nothing" value
  var CROP = 96;                           // px; the crop is downscaled to this
  var BOX_TIMEOUT_MS = 1000;               // no box for this long → reset

  /* Hann window, precomputed once. Suppresses spectral leakage from the
     residual trend, which would otherwise smear DC across low bins and
     drown a genuine 2 Hz peak. */
  var HANN = new Float64Array(WINDOW_N);
  for (var i = 0; i < WINDOW_N; i++) {
    HANN[i] = 0.5 * (1 - Math.cos((2 * Math.PI * i) / (WINDOW_N - 1)));
  }

  /* Naive real DFT. O(N^2) is 4,096 operations at N=64, run once a
     second — far cheaper than the machinery a fast FFT would need. */
  function spectrum(samples) {
    var half = WINDOW_N >> 1;
    var mags = new Float64Array(half);
    for (var k = 0; k < half; k++) {
      var re = 0, im = 0;
      for (var n = 0; n < WINDOW_N; n++) {
        var a = (-2 * Math.PI * k * n) / WINDOW_N;
        re += samples[n] * Math.cos(a);
        im += samples[n] * Math.sin(a);
      }
      mags[k] = Math.sqrt(re * re + im * im);
    }
    return mags;
  }

  function median(values) {
    var sorted = Array.prototype.slice.call(values).sort(function (a, b) { return a - b; });
    var mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function estimate(buffer) {
    /* Detrend with a least-squares line. A growing fire gets steadily
       brighter; without removing that ramp its energy lands in the low
       bins and looks like very slow flicker. */
    var n = WINDOW_N, sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (var i = 0; i < n; i++) { sx += i; sy += buffer[i]; sxx += i * i; sxy += i * buffer[i]; }
    var denom = n * sxx - sx * sx;
    var slope = denom === 0 ? 0 : (n * sxy - sx * sy) / denom;
    var intercept = (sy - slope * sx) / n;

    var windowed = new Float64Array(n);
    for (var j = 0; j < n; j++) windowed[j] = (buffer[j] - (intercept + slope * j)) * HANN[j];

    var mags = spectrum(windowed);

    /* Bins 0 and 1 are DC and 0.25 Hz — below any real flame, and where
       whatever trend survived detrending ends up. */
    var best = -1, bestMag = 0;
    for (var k = 2; k < mags.length; k++) {
      if (k * BIN_HZ > MAX_HZ) break;
      if (mags[k] > bestMag) { bestMag = mags[k]; best = k; }
    }
    if (best < 0) return QUIET_HZ;

    /* Glare has a flat spectrum; flame has a peak. Without this test the
       meter would return the argmax of pure noise and call it a flame. */
    var floorMag = median(mags.subarray(2));
    if (!(bestMag > PEAK_RATIO * floorMag)) return QUIET_HZ;

    return Math.max(0, Math.min(MAX_HZ, best * BIN_HZ));
  }

  /**
   * create({ sample }) → meter
   *   sample() must return a mean luminance in 0..255 for the current
   *   flame region, or null when there is no fire box to measure.
   */
  function create(opts) {
    var sample = opts.sample;
    var buffer = new Float64Array(WINDOW_N);
    var filled = 0;
    var head = 0;
    var timer = null;
    var lastBoxAt = 0;
    var current = QUIET_HZ;

    function reset() { filled = 0; head = 0; current = QUIET_HZ; }

    function step() {
      var value = null;
      try { value = sample(); } catch (e) { value = null; }

      if (value === null || value === undefined) {
        /* A fire box can blink out for a frame. Only a sustained absence
           clears the history — otherwise one dropped detection would
           restart the 4 s warm-up. */
        if (lastBoxAt && Date.now() - lastBoxAt > BOX_TIMEOUT_MS) reset();
        return;
      }
      lastBoxAt = Date.now();

      buffer[head] = value;
      head = (head + 1) % WINDOW_N;
      if (filled < WINDOW_N) { filled++; return; }

      /* Read the ring oldest-first so the FFT sees real time order. */
      var ordered = new Float64Array(WINDOW_N);
      for (var i = 0; i < WINDOW_N; i++) ordered[i] = buffer[(head + i) % WINDOW_N];
      current = estimate(ordered);
    }

    return {
      start: function () { if (!timer) timer = setInterval(step, 1000 / SAMPLE_HZ); },
      stop: function () { clearInterval(timer); timer = null; reset(); },
      /* During warm-up this reports the generator's quiet value rather
         than 0, so the first four seconds of a session stay inside the
         distribution the model was trained on. */
      value: function () { return current; },
      warmup: function () { return filled < WINDOW_N; },
      progress: function () { return Math.min(1, filled / WINDOW_N); },
      SAMPLE_HZ: SAMPLE_HZ,
      WINDOW_N: WINDOW_N
    };
  }

  /**
   * Mean luminance inside a set of boxes, drawn from a camera source.
   * Returns null when there is nothing to measure.
   */
  function makeBoxSampler(getSource, getBoxes, getNativeSize) {
    var canvas = document.createElement('canvas');
    canvas.width = CROP; canvas.height = CROP;
    var ctx = canvas.getContext('2d', { willReadFrequently: true });

    return function () {
      var source = getSource();
      var boxes = getBoxes();
      if (!source || !source.isReady() || !boxes || !boxes.length) return null;

      var size = getNativeSize();
      /* Union bounding box of the fire detections. A single crop keeps
         this to one getImageData per sample, which is what makes 16 Hz
         affordable. */
      var x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
      for (var i = 0; i < boxes.length; i++) {
        var b = boxes[i].box;
        if (b[0] < x1) x1 = b[0];
        if (b[1] < y1) y1 = b[1];
        if (b[2] > x2) x2 = b[2];
        if (b[3] > y2) y2 = b[3];
      }
      x1 = Math.max(0, x1); y1 = Math.max(0, y1);
      x2 = Math.min(size.w, x2); y2 = Math.min(size.h, y2);
      var w = x2 - x1, h = y2 - y1;
      if (w < 2 || h < 2) return null;

      try {
        ctx.drawImage(source.element, x1, y1, w, h, 0, 0, CROP, CROP);
        var data = ctx.getImageData(0, 0, CROP, CROP).data;
        var sum = 0;
        /* Rec. 601 luma. Sampling every 4th pixel is plenty for a mean
           and keeps a 16 Hz tick well under a millisecond. */
        for (var p = 0; p < data.length; p += 16) {
          sum += 0.299 * data[p] + 0.587 * data[p + 1] + 0.114 * data[p + 2];
        }
        return sum / (data.length / 16);
      } catch (e) {
        return null;   // tainted canvas or a source mid-teardown
      }
    };
  }

  global.FlickerMeter = { create: create, makeBoxSampler: makeBoxSampler,
                          SAMPLE_HZ: SAMPLE_HZ, WINDOW_N: WINDOW_N, QUIET_HZ: QUIET_HZ };
})(window);
