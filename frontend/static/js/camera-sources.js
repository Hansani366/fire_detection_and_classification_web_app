/* ═══════════════════════════════════════════════════════════
   FireWatch AI — camera sources

   Two interchangeable frame sources behind one interface, so the
   detection loop never learns which camera it is talking to:

     { id, label, element, start(), stop(),
       isReady(), nativeSize(), drawInto(ctx, w, h) }

   Loaded as a classic script (the dashboard's main script is inline
   and non-module) and exposed as window.CameraSources.
═══════════════════════════════════════════════════════════ */
(function (global) {
"use strict";

/* 1×1 transparent GIF. Assigning this is the reliable way to drop an MJPEG
   connection — img.src = '' makes some browsers re-request the page URL. */
const BLANK_GIF = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

const FIRST_FRAME_TIMEOUT_MS = 12000;
const FIRST_FRAME_POLL_MS    = 150;


/* ── Laptop webcam (getUserMedia → <video>) ───────────────── */
function createWebcamSource({ video, onError }) {
  let stream  = null;
  let onEnded = null;

  return {
    id: 'webcam',
    label: 'Laptop',
    element: video,

    async start() {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      video.srcObject = stream;

      /* Unplugging a USB webcam, or revoking permission at the OS level, leaves
         the <video> frozen on its last frame — the same stale-frame hazard the
         ESP32 has. `ended` is the signal for it. */
      const track = stream.getVideoTracks()[0];
      if (track && onError) {
        onEnded = () => onError(new Error('Camera disconnected'));
        track.addEventListener('ended', onEnded);
      }

      await new Promise(res => video.addEventListener('loadedmetadata', res, { once: true }));
      // Let the video render one frame so getBoundingClientRect is valid
      await new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res)));
    },

    stop() {
      if (stream) {
        const track = stream.getVideoTracks()[0];
        if (track && onEnded) track.removeEventListener('ended', onEnded);
        stream.getTracks().forEach(t => t.stop());
        stream = null;
      }
      onEnded = null;
      video.srcObject = null;
    },

    isReady()    { return !!stream && video.readyState >= 2; },
    nativeSize() { return { w: video.videoWidth || 640, h: video.videoHeight || 480 }; },
    drawInto(ctx, w, h) { ctx.drawImage(video, 0, 0, w, h); },
  };
}


/* ── ESP32-CAM (proxied MJPEG → <img>) ────────────────────── */
function createEsp32Source({ img, host, onError }) {
  let failed     = false;
  let errHandler = null;

  const hostQuery = host ? '?host=' + encodeURIComponent(host) : '';

  function streamUrl() {
    const p = new URLSearchParams();
    if (host) p.set('host', host);
    p.set('t', Date.now());   // cache-bust, so a restart never reuses a dead connection
    return '/api/esp32/stream?' + p.toString();
  }

  /* Ask the bridge first. An <img> that simply never loads is a miserable thing
     to debug, and this turns a 12s silent timeout into an immediate, specific
     message ("connect refused", "not a local network address", …). Safe to
     probe here because no stream is open yet — the board only answers one
     request at a time. */
  async function preflight() {
    let body;
    try {
      body = await (await fetch('/api/esp32/health' + hostQuery)).json();
    } catch (e) {
      throw new Error('ESP32 bridge unreachable: ' + e.message);
    }
    if (body.status !== 'ok') {
      throw new Error(body.detail || ('ESP32-CAM ' + body.status));
    }
  }

  /* The `load` event is useless for multipart/x-mixed-replace: it fires per
     frame in some browsers, once in others, and not at all in Safari. Poll for
     decoded pixels instead. */
  function waitForFirstFrame() {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + FIRST_FRAME_TIMEOUT_MS;
      (function poll() {
        if (failed)             return reject(new Error('Could not reach the ESP32-CAM'));
        if (img.naturalWidth)   return resolve();
        if (Date.now() > deadline) {
          return reject(new Error('No frames from the ESP32-CAM — check the address and that the board is powered on'));
        }
        setTimeout(poll, FIRST_FRAME_POLL_MS);
      })();
    });
  }

  return {
    id: 'esp32',
    label: 'ESP32',
    element: img,

    async start() {
      failed = false;
      await preflight();
      errHandler = () => {
        failed = true;
        if (onError) onError(new Error('ESP32-CAM stream dropped'));
      };
      img.addEventListener('error', errHandler);
      img.src = streamUrl();
      await waitForFirstFrame();
    },

    stop() {
      if (errHandler) { img.removeEventListener('error', errHandler); errHandler = null; }
      img.src = BLANK_GIF;          // drops the connection to the board
      img.removeAttribute('src');
      failed = false;
    },

    isReady()    { return !failed && img.naturalWidth > 0; },
    nativeSize() { return { w: img.naturalWidth || 640, h: img.naturalHeight || 480 }; },
    drawInto(ctx, w, h) { ctx.drawImage(img, 0, 0, w, h); },
  };
}


global.CameraSources = { createWebcamSource, createEsp32Source };

})(window);
