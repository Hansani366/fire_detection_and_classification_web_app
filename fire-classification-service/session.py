"""
Live classification sessions: frames and sensor readings in, a fuel verdict out.

THE MODEL IS NOT A FRAME CLASSIFIER. 72 of the fusion model's 96 features are
rolling statistics, running maxima and a 25-window persistence mean. Its own
docstring says a detached row "will produce a prediction, but a poor one". So a
session owns its whole history and scores the sequence, never a single frame.

THE BUFFER IS CAPPED, NEVER TRIMMED. predict() rebuilds features over the whole
session each tick, and cummax and persistence reach back to the first window --
so dropping old rows would silently change the answer. A session stops
accepting ticks at LIVE_MAX_ROWS and says so.

THE SERVICE DECIDES WHEN TO SPEND A VLM CALL. The caller sends the frame it
already has; the cooldown and the sample-and-hold live here, beside the state
they mutate, so a caller cannot accidentally invoke Gemini every second.

AN ERROR IS NOT AN OBSERVATION. A failed VLM call keeps the previous verdict
and keeps ageing it. Zeroing the channels mid-session would invent a confident
"saw nothing" from a request that never completed.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
import pandas as pd

import constants as K
import vision
from sensor_adapter import SensorAdapter, SensorGapError
from vlm_adapter import VlmHold

log = logging.getLogger("classify.session")

SESSIONS: dict[str, "Session"] = {}
MAX_SESSIONS = 8

# Stand-in reading for a vision-only session. Mid-range ambient values inside
# the training distribution, with the MQ channels at the generator's own
# baseline priors so their deltas come out at zero rather than hugely negative.
QUIET_ROOM = {
    "mq2_raw": K.MQ2_BASELINE_HINT,
    "mq7_raw": K.MQ7_BASELINE_HINT,
    "temperature_c": 22.0,
    "humidity_pct": 55.0,
    "flame": 0,
    "flame_raw": K.FLAME_DARK_COUNTS,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Session:
    """One monitoring run: its own clock, buffer, VLM hold and sensor baseline."""

    def __init__(self, session_id: str, zone_id: str, sensor_source: str,
                 device_id: str | None, baseline_mode: str):
        self.id = session_id
        self.zone_id = zone_id
        self.started = time.monotonic()
        self.started_iso = _now()
        self.sensor_source = sensor_source
        self.device_id = device_id

        if sensor_source == "none":
            # Nothing to measure, so nothing to wait for.
            baseline_mode = "manual"
            self.sensors = SensorAdapter(
                baseline_mode="manual",
                mq2_baseline=K.MQ2_BASELINE_HINT, mq7_baseline=K.MQ7_BASELINE_HINT)
        else:
            self.sensors = SensorAdapter(baseline_mode=baseline_mode)

        self.rows: list[dict] = []
        self.vlm = VlmHold()
        self.last: dict | None = None
        self.error: str | None = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def full(self) -> bool:
        return len(self.rows) >= K.LIVE_MAX_ROWS

    def status(self) -> dict:
        return {
            "session_id": self.id,
            "zone_id": self.zone_id,
            "started_at": self.started_iso,
            "elapsed_s": round(self.elapsed, 1),
            "windows": len(self.rows),
            "max_windows": K.LIVE_MAX_ROWS,
            "full": self.full,
            "sensor": self.sensors.status(self.elapsed),
            "vlm": {"invocations": self.vlm.invocations, "errors": self.vlm.errors},
            "error": self.error,
        }


async def _fetch_sensors(client: httpx.AsyncClient, url: str,
                         device_id: str | None) -> dict | None:
    """Latest reading for one node, straight from esp32-sensor-service."""
    try:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        nodes = resp.json().get("nodes", [])
    except Exception as exc:                                    # noqa: BLE001
        log.warning("sensor fetch failed: %s", exc)
        return None
    if not nodes:
        return None
    node = next((n for n in nodes if n["deviceId"] == device_id), nodes[0]) \
        if device_id else nodes[0]
    # /latest reports display tiles, so flatten them back into the raw field
    # names the adapter expects.
    out: dict[str, float] = {}
    for tile in node.get("sensors", []):
        sid = tile.get("id", "")
        if tile.get("value") is not None:
            out[sid] = tile["value"]
        if tile.get("raw") is not None:
            out[f"{sid}_raw"] = tile["raw"]
    return out or None


async def tick(session: Session, image: bytes, frame_w: int, frame_h: int,
               flicker_hz: float, yolo_url: str, vlm_url: str, sensor_url: str,
               clf) -> dict:
    """Score one 1 Hz window and return the fuel verdict."""
    if session.full:
        raise ValueError(
            f"session reached its {K.LIVE_MAX_ROWS}-window cap "
            f"({K.LIVE_MAX_ROWS / K.WINDOW_HZ / 60:.0f} min). Start a new one — the "
            f"buffer is never trimmed, because the model's running maxima and "
            f"persistence reach back to the first window.")

    t = session.elapsed
    timings: dict[str, int] = {}

    async with httpx.AsyncClient() as client:
        started = time.perf_counter()
        yolo_task = client.post(yolo_url,
                                files={"file": ("frame.jpg", image, "image/jpeg")},
                                timeout=10.0)
        sensor_task = (_fetch_sensors(client, sensor_url, session.device_id)
                       if session.sensor_source == "node"
                       else asyncio.sleep(0, result=None))
        yolo_resp, sensor_reading = await asyncio.gather(
            yolo_task, sensor_task, return_exceptions=True)
        timings["yolo_ms"] = round((time.perf_counter() - started) * 1000)

        if isinstance(yolo_resp, BaseException):
            raise RuntimeError(f"fire detector unreachable: {yolo_resp}")
        detections = yolo_resp.json().get("detections", [])
        vis = vision.channels(detections, frame_w, frame_h, flicker_hz)

        invoked = False
        if session.vlm.due(gated=bool(vis["yolo_detected"])):
            started = time.perf_counter()
            try:
                resp = await client.post(
                    vlm_url, files={"file": ("frame.jpg", image, "image/jpeg")},
                    timeout=60.0)
                resp.raise_for_status()
                session.vlm.observe(resp.json())
                invoked = True
            except Exception as exc:                            # noqa: BLE001
                log.warning("VLM call failed: %s", exc)
                session.vlm.failed()
            timings["vlm_ms"] = round((time.perf_counter() - started) * 1000)

    if session.sensor_source == "none":
        sensor_reading = QUIET_ROOM
    if isinstance(sensor_reading, BaseException):
        sensor_reading = None
    if sensor_reading:
        session.sensors.observe(t, sensor_reading)

    try:
        sensor_channels = session.sensors.channels(t)
    except SensorGapError as exc:
        session.error = str(exc)
        raise

    if sensor_channels is None and t > K.BASELINE_S * 2 and session.sensors.samples == 0:
        session.error = (f"no sensor readings in {t:.0f}s — check the node is posting, "
                         f"or start the session with sensors set to 'none'")
        raise SensorGapError(session.error)

    if sensor_channels is None:
        # Still measuring the clean-air baseline. No row is emitted: a delta
        # against an unknown baseline is meaningless, and the running maxima
        # built from it would never forget it.
        session.vlm.tick()
        return {
            "baselining": True,
            "baseline_remaining_s": max(0.0, K.BASELINE_S - t),
            "fuel": None,
            "status": session.status(),
        }

    session.rows.append({
        "experiment_id": session.id,
        "timestamp": pd.Timestamp.utcnow().tz_localize(None),
        **vis,
        **session.vlm.channels(invoked_this_window=invoked),
        **sensor_channels,
    })
    session.vlm.tick()

    started = time.perf_counter()
    result = clf.predict(pd.DataFrame(session.rows), smooth=True, gate=False)
    timings["score_ms"] = round((time.perf_counter() - started) * 1000)
    last = result.iloc[-1]

    fuel = {
        "predictedClass": str(last["predicted_class"]),
        "confidence": float(last["confidence"]),
        # The model's own abstention gate. Worth knowing before trusting it:
        # confidence scores AUROC 0.486 as a novelty detector -- chance -- so a
        # high number does NOT mean "this is a familiar situation".
        "lowConfidence": bool(last["low_confidence"]),
        "probabilities": {c: float(last[f"p_{c}"]) for c in clf.classes},
    }

    out = {
        "baselining": False,
        "window": len(session.rows) - 1,
        "elapsed_s": round(t, 1),
        "fuel": fuel,
        "vlm_invoked": invoked,
        "detections": [d for d in detections
                       if float(d.get("confidence", 0)) >= K.YOLO_DETECT_THRESHOLD],
        "timings_ms": timings,
        "status": session.status(),
    }
    session.last = out
    return out


def create(zone_id: str, sensor_source: str, device_id: str | None,
           baseline_mode: str) -> Session:
    if len(SESSIONS) >= MAX_SESSIONS:
        oldest = min(SESSIONS.values(), key=lambda s: s.started)
        SESSIONS.pop(oldest.id, None)
    session_id = f"cls_{uuid.uuid4().hex[:8]}"
    session = Session(session_id, zone_id, sensor_source, device_id, baseline_mode)
    SESSIONS[session_id] = session
    return session
