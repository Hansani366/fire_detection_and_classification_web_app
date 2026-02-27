import streamlit as st
import requests
import base64
import time
import threading
import queue
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import av
import numpy as np
import cv2

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FireWatch AI",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;400;600;700&display=swap');

* { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0a0f !important;
    color: #e0e0e0;
    font-family: 'Rajdhani', sans-serif;
}

[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 20% 0%, #1a0a00 0%, #0a0a0f 60%) !important;
}

.main .block-container { padding-top: 1rem; max-width: 1400px; }

/* Header */
.fw-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 0 8px;
    border-bottom: 1px solid #ff4b2b33;
    margin-bottom: 24px;
}
.fw-logo {
    font-family: 'Share Tech Mono', monospace;
    font-size: 2.4rem;
    color: #ff4b2b;
    letter-spacing: -1px;
    text-shadow: 0 0 30px #ff4b2b88;
}
.fw-subtitle {
    font-size: 0.85rem;
    color: #666;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: -4px;
}

/* Alarm banner */
.alarm-on {
    background: linear-gradient(90deg, #ff1a00, #ff4b2b, #ff1a00);
    background-size: 200% 100%;
    animation: alarm-slide 1s linear infinite, alarm-pulse 0.5s ease-in-out infinite alternate;
    border-radius: 8px;
    padding: 18px 24px;
    text-align: center;
    font-family: 'Share Tech Mono', monospace;
    font-size: 1.6rem;
    color: #fff;
    letter-spacing: 4px;
    font-weight: bold;
    margin-bottom: 20px;
    box-shadow: 0 0 40px #ff1a0088, 0 0 80px #ff1a0044;
}
.alarm-off {
    background: #111118;
    border: 1px solid #1f1f2e;
    border-radius: 8px;
    padding: 18px 24px;
    text-align: center;
    font-family: 'Share Tech Mono', monospace;
    font-size: 1.6rem;
    color: #2a2a3a;
    letter-spacing: 4px;
    margin-bottom: 20px;
}

@keyframes alarm-slide {
    0% { background-position: 0% 50%; }
    100% { background-position: 200% 50%; }
}
@keyframes alarm-pulse {
    0% { box-shadow: 0 0 40px #ff1a0088, 0 0 80px #ff1a0044; }
    100% { box-shadow: 0 0 60px #ff1a00cc, 0 0 120px #ff1a0066; }
}

/* Cards */
.fw-card {
    background: #111118;
    border: 1px solid #1f1f2e;
    border-radius: 10px;
    padding: 16px;
    height: 100%;
}
.fw-card-title {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    color: #ff4b2b;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.fw-card-title::before {
    content: '';
    display: inline-block;
    width: 6px; height: 6px;
    background: #ff4b2b;
    border-radius: 50%;
    box-shadow: 0 0 8px #ff4b2b;
}

/* VLM log */
.vlm-log {
    background: #0d0d14;
    border: 1px solid #1a1a28;
    border-radius: 6px;
    padding: 12px 14px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.82rem;
    color: #a0c0ff;
    line-height: 1.7;
    max-height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
.vlm-timestamp {
    color: #ff4b2b99;
    margin-right: 8px;
}
.vlm-entry { margin-bottom: 10px; border-bottom: 1px solid #1a1a28; padding-bottom: 10px; }
.vlm-entry:last-child { border-bottom: none; margin-bottom: 0; }

/* Stats */
.stat-row {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
}
.stat-box {
    flex: 1;
    background: #0d0d14;
    border: 1px solid #1a1a28;
    border-radius: 6px;
    padding: 12px;
    text-align: center;
}
.stat-value {
    font-family: 'Share Tech Mono', monospace;
    font-size: 1.6rem;
    color: #ff4b2b;
}
.stat-label {
    font-size: 0.7rem;
    color: #555;
    letter-spacing: 2px;
    text-transform: uppercase;
}

/* Detection badge */
.det-badge {
    display: inline-block;
    background: #ff4b2b22;
    border: 1px solid #ff4b2b55;
    border-radius: 4px;
    padding: 3px 10px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.8rem;
    color: #ff8060;
    margin: 3px;
}

/* Streamlit overrides */
[data-testid="stButton"] button {
    background: #ff4b2b !important;
    color: white !important;
    border: none !important;
    font-family: 'Share Tech Mono', monospace !important;
    letter-spacing: 2px !important;
    font-size: 0.8rem !important;
    border-radius: 6px !important;
    padding: 8px 20px !important;
    transition: all 0.2s !important;
}
[data-testid="stButton"] button:hover {
    background: #ff2200 !important;
    box-shadow: 0 0 20px #ff4b2b66 !important;
}

div[data-testid="column"] { padding: 0 6px; }
[data-testid="stMarkdownContainer"] p { margin: 0; }

.stSpinner > div { border-top-color: #ff4b2b !important; }

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ───────────────────────────────────────────────────────
if "fire_alarm" not in st.session_state:
    st.session_state.fire_alarm = False
if "vlm_log" not in st.session_state:
    st.session_state.vlm_log = []
if "total_detections" not in st.session_state:
    st.session_state.total_detections = 0
if "vlm_calls" not in st.session_state:
    st.session_state.vlm_calls = 0
if "last_detections" not in st.session_state:
    st.session_state.last_detections = []

YOLO_URL = "http://yolo-service:8000/detect"
VLM_URL  = "http://vlm-service:8019/describe-image/"
FIRE_KEYWORDS = {"fire", "smoke", "flame", "flames", "burning", "blaze", "wildfire", "inferno", "ember", "combustion"}

# ── Video processor ──────────────────────────────────────────────────────────
class FireDetector(VideoProcessorBase):
    def __init__(self):
        self.result_queue = queue.Queue(maxsize=2)
        self._last_send = 0

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        now = time.time()

        # Send frame to YOLO every 500ms
        if now - self._last_send > 0.5:
            self._last_send = now
            threading.Thread(target=self._process, args=(img.copy(),), daemon=True).start()

        return frame  # pass-through; overlay drawn in Streamlit

    def _process(self, img):
        try:
            _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            resp = requests.post(YOLO_URL, files={"file": ("frame.jpg", buf.tobytes(), "image/jpeg")}, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                dets = [d for d in data.get("detections", []) if d["confidence"] >= 0.5]
                if not self.result_queue.full():
                    self.result_queue.put({"detections": dets, "image": img, "ts": time.time()})
        except Exception as e:
            pass


detector_ctx = None

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="fw-header">
  <div>
    <div class="fw-logo">🔥 FIREWATCH</div>
    <div class="fw-subtitle">AI-Powered Smoke &amp; Fire Detection System</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Alarm banner (placeholder, updated in loop) ──────────────────────────────
alarm_ph = st.empty()

# ── Layout ───────────────────────────────────────────────────────────────────
col_cam, col_info = st.columns([3, 2], gap="medium")

with col_cam:
    st.markdown('<div class="fw-card"><div class="fw-card-title">Live Camera Feed</div>', unsafe_allow_html=True)
    RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
    ctx = webrtc_streamer(
        key="firewatch",
        video_processor_factory=FireDetector,
        rtc_configuration=RTC_CONFIG,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

with col_info:
    # Stats row
    stat_total_ph = st.empty()
    stat_vlm_ph   = st.empty()

    # Current detections
    st.markdown('<div class="fw-card" style="margin-bottom:12px"><div class="fw-card-title">Current Detections</div>', unsafe_allow_html=True)
    det_ph = st.empty()
    st.markdown("</div>", unsafe_allow_html=True)

    # VLM log
    st.markdown('<div class="fw-card"><div class="fw-card-title">VLM Scene Analysis</div>', unsafe_allow_html=True)
    vlm_ph = st.empty()
    st.markdown("</div>", unsafe_allow_html=True)

    # Reset button
    if st.button("⟳  RESET ALARM"):
        st.session_state.fire_alarm = False
        st.session_state.vlm_log = []
        st.session_state.total_detections = 0
        st.session_state.vlm_calls = 0
        st.session_state.last_detections = []

# ── Render helpers ───────────────────────────────────────────────────────────
def render_alarm(active: bool):
    if active:
        alarm_ph.markdown('<div class="alarm-on">🚨 &nbsp; FIRE ALARM ACTIVE &nbsp; 🚨</div>', unsafe_allow_html=True)
    else:
        alarm_ph.markdown('<div class="alarm-off">● &nbsp; SYSTEM NOMINAL</div>', unsafe_allow_html=True)

def render_stats():
    stat_total_ph.markdown(f"""
    <div class="stat-row">
      <div class="stat-box"><div class="stat-value">{st.session_state.total_detections}</div><div class="stat-label">Detections</div></div>
      <div class="stat-box"><div class="stat-value">{st.session_state.vlm_calls}</div><div class="stat-label">VLM Calls</div></div>
      <div class="stat-box"><div class="stat-value">{'🔴' if st.session_state.fire_alarm else '🟢'}</div><div class="stat-label">Alarm</div></div>
    </div>""", unsafe_allow_html=True)

def render_detections(dets):
    if not dets:
        det_ph.markdown('<span style="color:#333;font-size:0.85rem;font-family:\'Share Tech Mono\',monospace">No threats detected</span>', unsafe_allow_html=True)
    else:
        badges = "".join(f'<span class="det-badge">{d["label"]} {d["confidence"]*100:.0f}%</span>' for d in dets)
        det_ph.markdown(badges, unsafe_allow_html=True)

def render_vlm_log():
    if not st.session_state.vlm_log:
        vlm_ph.markdown('<div class="vlm-log" style="color:#333">Waiting for VLM analysis...</div>', unsafe_allow_html=True)
        return
    entries = ""
    for entry in reversed(st.session_state.vlm_log[-10:]):
        entries += f'<div class="vlm-entry"><span class="vlm-timestamp">[{entry["time"]}]</span>{entry["text"]}</div>'
    vlm_ph.markdown(f'<div class="vlm-log">{entries}</div>', unsafe_allow_html=True)

def call_vlm(img: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    try:
        resp = requests.post(VLM_URL, files={"file": ("frame.jpg", buf.tobytes(), "image/jpeg")}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("description", "")
    except Exception as e:
        return f"[VLM error: {e}]"
    return ""

# ── Main loop ────────────────────────────────────────────────────────────────
render_alarm(st.session_state.fire_alarm)
render_stats()
render_detections(st.session_state.last_detections)
render_vlm_log()

if ctx and ctx.video_processor:
    proc: FireDetector = ctx.video_processor
    while True:
        try:
            result = proc.result_queue.get(timeout=1.0)
        except queue.Empty:
            render_alarm(st.session_state.fire_alarm)
            render_stats()
            render_detections(st.session_state.last_detections)
            render_vlm_log()
            continue

        dets = result["detections"]
        img  = result["image"]

        if dets:
            st.session_state.total_detections += len(dets)
            st.session_state.last_detections = dets

            # Send to VLM
            st.session_state.vlm_calls += 1
            description = call_vlm(img)

            ts = time.strftime("%H:%M:%S")
            st.session_state.vlm_log.append({"time": ts, "text": description})

            # Check for fire/smoke keywords
            desc_lower = description.lower()
            if any(kw in desc_lower for kw in FIRE_KEYWORDS):
                st.session_state.fire_alarm = True
        else:
            st.session_state.last_detections = []

        render_alarm(st.session_state.fire_alarm)
        render_stats()
        render_detections(st.session_state.last_detections)
        render_vlm_log()
else:
    # Idle polling when camera not active
    while True:
        time.sleep(1)
        render_alarm(st.session_state.fire_alarm)
        render_stats()
        render_detections(st.session_state.last_detections)
        render_vlm_log()