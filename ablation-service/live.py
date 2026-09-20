"""
Live sessions: all six combinations scored on the running system, at 1 Hz.

THIS TAB CANNOT MEASURE ACCURACY, AND MUST NOT PRETEND TO. Nothing on a live
feed carries a ground-truth label. What it can honestly show is *agreement* --
which combinations say fire right now, and where they disagree. Every number
returned here is a verdict or a confidence, never a score against truth.

THE SERVICE DECIDES WHEN TO SPEND A VLM CALL, NOT THE BROWSER. Combinations 3,
5 and 6 all read VLM output. If the browser drove it, the three would either
cost three Gemini calls per instant or silently share one by accident. Here the
cooldown and the sample-and-hold live next to the state they mutate, one call
serves every combination whose gate fired on that window, and `vlm_calls` is
reported per combination as a cost column -- because combination 3's fixed
cadence genuinely buys it more looks than the YOLO-gated arms, and that is part
of the finding rather than a bug to hide.

THE BUFFER IS CAPPED, LOUDLY, AND NEVER TRIMMED. predict() rebuilds features
over the whole session every tick, and demo.py forbids trimming because cummax
and the 25-window persistence mean reach back to the start. So a session stops
accepting ticks at LIVE_MAX_ROWS and says so, rather than quietly dropping its
own history and drifting away from what a batch score would give.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
import pandas as pd

import combos
import constants as K
import vision
from sensor_adapter import SensorAdapter, SensorGapError
from vlm_adapter import VLM_CHANNELS, VlmHold

log = logging.getLogger("ablation.live")

SESSIONS: dict[str, "LiveSession"] = {}
MAX_SESSIONS = 8

# Stand-in reading for a vision-only session. Mid-range ambient values inside
# the training distribution, and MQ readings at the generator's own baseline
# priors so the deltas come out at zero rather than hugely negative.
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


class LiveSession:
    """One monitoring run: its own clock, buffers, VLM hold and sensor baseline."""

    def __init__(self, session_id: str, sensor_source: str,
                 device_id: str | None, manual: dict | None,
                 baseline_mode: str, note: str):
        self.id = session_id
        self.started_at = time.monotonic()
        self.started_iso = _now()
        self.note = note
        self.sensor_source = sensor_source
        self.device_id = device_id
        self.manual = manual or {}

        self.rows: list[dict] = []
        self.window_idx = 0
        self.vlm = VlmHold()

        if sensor_source == "none":
            # Nothing to measure, so nothing to wait for: a vision-only session
            # scores from its first window instead of spending 30s baselining
            # a constant we already know.
            baseline_mode = "manual"
            self.manual = {**QUIET_ROOM, **self.manual,
                           "mq2_baseline": K.MQ2_BASELINE_HINT,
                           "mq7_baseline": K.MQ7_BASELINE_HINT}

        self.sensors = SensorAdapter(
            baseline_mode=baseline_mode,
            mq2_baseline=self.manual.get("mq2_baseline"),
            mq7_baseline=self.manual.get("mq7_baseline"),
        )
        self.vlm_calls_for: dict[int, int] = {3: 0, 5: 0, 6: 0}
        self.disagreements = 0
        self.last: dict | None = None
        self.error: str | None = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def full(self) -> bool:
        return len(self.rows) >= K.LIVE_MAX_ROWS

    def status(self) -> dict:
        return {
            "session_id": self.id,
            "started_at": self.started_iso,
            "note": self.note,
            "elapsed_s": round(self.elapsed, 1),
            "windows": len(self.rows),
            "max_windows": K.LIVE_MAX_ROWS,
            "full": self.full,
            "sensor": self.sensors.status(self.elapsed),
            "vlm": {"invocations": self.vlm.invocations, "errors": self.vlm.errors,
                    "calls_credited": self.vlm_calls_for},
            "disagreements": self.disagreements,
            "error": self.error,
        }


async def _fetch_sensors(client: httpx.AsyncClient, url: str,
                         device_id: str | None) -> dict | None:
    """Latest reading for one node, straight from esp32-sensor-service."""
    try:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        nodes = resp.json().get("nodes", [])
    except Exception as exc:                                   # noqa: BLE001
        log.warning("sensor fetch failed: %s", exc)
        return None
    if not nodes:
        return None
    node = next((n for n in nodes if n["deviceId"] == device_id), nodes[0]) \
        if device_id else nodes[0]
    # /latest reports display tiles, not the raw envelope, so flatten the tiles
    # back into the field names sensor_adapter expects.
    out: dict[str, float] = {}
    for tile in node.get("sensors", []):
        sid = tile.get("id", "")
        if tile.get("value") is not None:
            out[sid] = tile["value"]
        if tile.get("raw") is not None:
            out[f"{sid}_raw"] = tile["raw"]
    return out or None


async def tick(session: LiveSession, image: bytes, frame_w: int, frame_h: int,
               flicker_hz: float, yolo_url: str, vlm_url: str,
               sensor_url: str, clf, manifest: dict) -> dict:
    """Score one 1 Hz window through all six combinations."""
    if session.full:
        raise ValueError(
            f"session reached its {K.LIVE_MAX_ROWS}-window cap "
            f"({K.LIVE_MAX_ROWS / K.WINDOW_HZ / 60:.0f} min). Start a new one — "
            f"the buffer is never trimmed, because the model's running maxima "
            f"and persistence reach back to the first window.")

    t = session.elapsed
    timings: dict[str, int] = {}

    async with httpx.AsyncClient() as client:
        # YOLO and the sensor read are independent, so they overlap.
        started = time.perf_counter()
        yolo_task = client.post(yolo_url, files={"file": ("frame.jpg", image, "image/jpeg")},
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

        # ── the shared VLM sample ─────────────────────────────────────────
        # Combination 3 is ungated (a VLM-only arm that waited for YOLO would
        # not be VLM-only); 5 and 6 are gated on YOLO. One call serves whoever
        # fired, and each is credited so the cost column stays honest.
        gated_due = session.vlm.due(gated=bool(vis["yolo_detected"]))
        ungated_due = session.vlm.due(gated=True)
        invoked = False
        if ungated_due:
            started = time.perf_counter()
            try:
                resp = await client.post(
                    vlm_url, files={"file": ("frame.jpg", image, "image/jpeg")},
                    timeout=60.0)
                resp.raise_for_status()
                session.vlm.observe(resp.json())
                invoked = True
                session.vlm_calls_for[3] += 1
                if gated_due:
                    session.vlm_calls_for[5] += 1
                    session.vlm_calls_for[6] += 1
            except Exception as exc:                            # noqa: BLE001
                # Not an observation: keep the hold, keep ageing it.
                log.warning("VLM call failed: %s", exc)
                session.vlm.failed()
            timings["vlm_ms"] = round((time.perf_counter() - started) * 1000)

    # ── sensors ───────────────────────────────────────────────────────────
    if session.sensor_source == "manual":
        sensor_reading = session.manual.get("readings")
    elif session.sensor_source == "none":
        # A vision-only session still has to produce all ten sensor channels,
        # because the feature builder needs every column. Quiet-room constants
        # are used rather than zeros: the models never saw 0 degrees C or 0%
        # humidity, and feeding them a row from outside the training range
        # would make combinations 1, 4 and 6 misbehave in a way that looked
        # like a finding. They are meaningless in this mode either way, and
        # the UI says so.
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

    # A node that never reported at all would otherwise leave the session
    # baselining for ever, looking like it was working. Give it twice the
    # baseline window, then say plainly what is wrong.
    if sensor_channels is None and t > K.BASELINE_S * 2 and session.sensors.samples == 0:
        session.error = (
            f"no sensor readings in {t:.0f}s — check the node is posting, or "
            f"start the session with sensors set to 'none'")
        raise SensorGapError(session.error)

    if sensor_channels is None:
        # Still measuring the clean-air baseline. No row is emitted, because a
        # delta against an unknown baseline would poison every running maximum
        # built from it, for the rest of the session.
        session.vlm.tick()
        return {
            "baselining": True,
            "baseline_remaining_s": max(0.0, K.BASELINE_S - t),
            "window_idx": None,
            "status": session.status(),
        }

    # ── assemble the row ──────────────────────────────────────────────────
    row = {
        "experiment_id": session.id,
        "timestamp": pd.Timestamp.utcnow().tz_localize(None),
        **vis,
        **session.vlm.channels(invoked_this_window=invoked),
        **sensor_channels,
    }
    session.rows.append(row)
    session.vlm.tick()
    session.window_idx += 1

    # ── score the whole session ───────────────────────────────────────────
    started = time.perf_counter()
    frame = pd.DataFrame(session.rows)
    features = clf.build_features(frame)
    scored = combos.score_all(features, manifest, clf)
    timings["score_ms"] = round((time.perf_counter() - started) * 1000)

    verdicts = {}
    for c in sorted(scored["alarm"]):
        verdicts[c] = {
            "name": K.COMBOS[c],
            "alarm": bool(scored["alarm"][c].iloc[-1]),
            "score": float(scored["score"][c].iloc[-1]),
            "vlm_calls": session.vlm_calls_for.get(c, 0),
        }
    if scored.get("fuel") is not None:
        last = scored["fuel"].iloc[-1]
        verdicts[6]["predicted_class"] = str(last["predicted_class"])
        verdicts[6]["confidence"] = float(last["confidence"])
        verdicts[6]["low_confidence"] = bool(last["low_confidence"])

    # Agreement, not accuracy: how many pairs of combinations disagree right
    # now. This is the only honest summary a feed with no labels supports.
    alarms = [v["alarm"] for v in verdicts.values()]
    pairs = sum(1 for i in range(len(alarms)) for j in range(i + 1, len(alarms))
                if alarms[i] != alarms[j])
    if pairs:
        session.disagreements += 1

    result = {
        "baselining": False,
        "window_idx": len(session.rows) - 1,
        "elapsed_s": round(t, 1),
        "combos": verdicts,
        "channels": {k: (float(v) if not isinstance(v, pd.Timestamp) else None)
                     for k, v in row.items() if k not in ("experiment_id", "timestamp")},
        "vlm_invoked": invoked,
        # Returned so the browser can draw them and, more importantly, feed its
        # 16 Hz flicker sampler: the service runs YOLO, so this is the only way
        # the page knows where the flame is without detecting it a second time.
        "detections": [d for d in detections
                       if float(d.get("confidence", 0)) >= K.YOLO_DETECT_THRESHOLD],
        "disagreeing_pairs": pairs,
        "timings_ms": timings,
        "status": session.status(),
    }
    session.last = result
    return result


def create(sensor_source: str, device_id: str | None, manual: dict | None,
           baseline_mode: str, note: str) -> LiveSession:
    if len(SESSIONS) >= MAX_SESSIONS:
        oldest = min(SESSIONS.values(), key=lambda s: s.started_at)
        SESSIONS.pop(oldest.id, None)
    session_id = f"live_{uuid.uuid4().hex[:8]}"
    session = LiveSession(session_id, sensor_source, device_id, manual,
                          baseline_mode, note)
    SESSIONS[session_id] = session
    return session


def export_csv(session: LiveSession) -> str:
    if not session.rows:
        return ""
    buf = io.StringIO()
    pd.DataFrame(session.rows).to_csv(buf, index=False)
    return buf.getvalue()
