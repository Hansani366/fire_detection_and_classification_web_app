"""
FireWatch AI – sensor bridge

Receives telemetry pushed by ESP32 sensor nodes (MQ-2, MQ-7, IR flame, DHT22)
and serves the latest reading per node to the dashboard.

WHY THE BOARD PUSHES RATHER THAN BEING POLLED. The camera bridge next door
reaches *out* to the ESP32-CAM because an MJPEG stream only exists while
someone is pulling it. Sensors are the opposite: the reading exists whether or
not anyone asks, the board is on DHCP so its address moves, and the diagram
calls for a *network* of nodes. Push inverts all three — the node only needs to
know this server's address, N nodes need no configuration here at all, and the
board runs no HTTP server that a half-open connection could wedge.

WHY THIS PUBLISHES A PLAIN-HTTP PORT. The dashboard is served over HTTPS with a
self-signed cert, and making an ESP32 accept that cert is a pointless fight. So
this service is published on the host (see docker-compose.yml) and the board
POSTs to it directly in the clear, exactly as alert-service does for the mobile
app. Browsers reach the same service through nginx over HTTPS, same-origin.

THE BOARD HAS NO CLOCK. It sends `uptimeMs` and a sequence number; wall-clock
timestamps are stamped here on arrival. Liveness likewise is measured here,
from the age of the last accepted sample — a node that dies mid-reading goes
stale rather than leaving its last value on the dashboard looking current.

MUST STAY SINGLE-WORKER: NODES is an in-process dict (see Dockerfile).
"""

import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# No sample for this long => the node is reported stale. Five missed posts at
# the sketch's default 3s cadence, so one dropped packet is not an outage.
STALE_AFTER_S = float(os.getenv("SENSOR_STALE_AFTER_S", "15"))
# Ring buffer depth per node: 720 samples ≈ 36 min at 3s.
HISTORY_MAX = int(os.getenv("SENSOR_HISTORY_MAX", "720"))
# Shared secret the node sends as X-Device-Key. Empty = accept anything, which
# is fine on a trusted LAN and is the default so nothing breaks out of the box.
INGEST_KEY = os.getenv("SENSOR_INGEST_KEY", "").strip()
# Bounds memory: this port is open to the LAN, so a chatty or buggy device
# must not be able to grow NODES without limit.
MAX_NODES = int(os.getenv("SENSOR_MAX_NODES", "32"))


def _threshold(name: str, warn: float, danger: float) -> tuple[float, float]:
    return (
        float(os.getenv(f"SENSOR_{name}_WARN", warn)),
        float(os.getenv(f"SENSOR_{name}_DANGER", danger)),
    )


# MQ-7 defaults track CO exposure limits (35 ppm is the OSHA 8-hour ceiling,
# 100 ppm is squarely dangerous) rather than anything fire-specific.
MQ2_WARN,  MQ2_DANGER  = _threshold("MQ2", 400, 800)
MQ7_WARN,  MQ7_DANGER  = _threshold("MQ7", 35, 100)
TEMP_WARN, TEMP_DANGER = _threshold("TEMP", 45, 60)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sensor-service")

# deviceId -> {"zoneId", "readings", "seq", "uptimeMs", "rssi", "mock",
#              "received_at" (ISO), "received_mono" (float), "first_seen" (ISO),
#              "samples" (deque)}
NODES: dict[str, dict] = {}

LEVEL_RANK = {"unknown": 0, "normal": 1, "warn": 2, "danger": 3}


# ── Request body ─────────────────────────────────────────────────────────────

class Readings(BaseModel):
    """One sweep of the four modules on the node.

    Every field is optional so a node with a sensor unplugged still reports the
    rest — a missing value renders as "—" rather than zero, which would read as
    a real measurement of nothing.
    """

    mq2_ppm: float | None = None        # MQ-2 smoke/LPG, converted on the board
    mq2_raw: int | None = None          # raw ADC, kept for calibration work
    mq7_ppm: float | None = None        # MQ-7 carbon monoxide
    mq7_raw: int | None = None
    flame: int | None = None            # 1 = flame seen (board normalises the active-low DO)
    flame_raw: int | None = None        # analog AO, lower = brighter IR source
    temperature_c: float | None = None  # DHT22
    humidity_pct: float | None = None   # DHT22


class Sample(BaseModel):
    # Constrained because deviceId is used as a dict key and echoed into the
    # dashboard; anything exotic is a bug or an intruder, not a device name.
    deviceId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    zoneId: str = Field(default="fabric-store", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    seq: int | None = None
    uptimeMs: int | None = None
    rssi: int | None = None             # dBm, for "is the Wi-Fi the problem?"
    mock: bool = False                  # true while the sketch is synthesising
    readings: Readings


# ── Level derivation ─────────────────────────────────────────────────────────

def _level(value: float | None, warn: float, danger: float) -> str:
    """Grade one reading. Levels are derived *here*, not in the browser, so the
    alerting path can later reuse them without reimplementing the thresholds."""
    if value is None:
        return "unknown"
    if value >= danger:
        return "danger"
    if value >= warn:
        return "warn"
    return "normal"


def _sensor_views(r: dict) -> list[dict]:
    """Flat readings -> the tile list the dashboard renders.

    Five tiles from four modules: the DHT22 reports two independent quantities
    and splitting them keeps each tile to a single number and a single level.
    """
    flame_on = bool(r.get("flame"))
    return [
        {
            "id": "mq2", "label": "Smoke / Gas", "module": "MQ-2",
            "value": r.get("mq2_ppm"), "unit": "ppm", "raw": r.get("mq2_raw"),
            "level": _level(r.get("mq2_ppm"), MQ2_WARN, MQ2_DANGER),
        },
        {
            "id": "mq7", "label": "Carbon Monoxide", "module": "MQ-7",
            "value": r.get("mq7_ppm"), "unit": "ppm", "raw": r.get("mq7_raw"),
            "level": _level(r.get("mq7_ppm"), MQ7_WARN, MQ7_DANGER),
        },
        {
            # Binary, so it carries `text` and the dashboard shows that instead
            # of a number. Any flame at all is a danger — there is no "warn".
            "id": "flame", "label": "Flame", "module": "IR Flame",
            "value": None if r.get("flame") is None else int(flame_on),
            "unit": "", "raw": r.get("flame_raw"),
            "text": "—" if r.get("flame") is None else ("Detected" if flame_on else "None"),
            "level": "unknown" if r.get("flame") is None else ("danger" if flame_on else "normal"),
        },
        {
            "id": "temperature", "label": "Temperature", "module": "DHT22",
            "value": r.get("temperature_c"), "unit": "°C", "raw": None,
            "level": _level(r.get("temperature_c"), TEMP_WARN, TEMP_DANGER),
        },
        {
            # Informational: low humidity accompanies fire but does not identify
            # it, so this tile never escalates on its own.
            "id": "humidity", "label": "Humidity", "module": "DHT22",
            "value": r.get("humidity_pct"), "unit": "%", "raw": None,
            "level": "normal" if r.get("humidity_pct") is not None else "unknown",
        },
    ]


def _node_json(node: dict, now: float) -> dict:
    age_ms = (now - node["received_mono"]) * 1000
    fresh = age_ms < STALE_AFTER_S * 1000
    sensors = _sensor_views(node["readings"])

    # A stale node's numbers are history, not measurements, so its level is
    # withheld rather than reported as normal — otherwise a node that died
    # during a fire would keep the dashboard green.
    worst = (
        max((s["level"] for s in sensors), key=lambda lv: LEVEL_RANK[lv])
        if fresh else "unknown"
    )

    return {
        "deviceId": node["deviceId"],
        "zoneId": node["zoneId"],
        "status": "ok" if fresh else "stale",
        "ageMs": round(age_ms),
        "seq": node["seq"],
        "uptimeMs": node["uptimeMs"],
        "rssi": node["rssi"],
        "mock": node["mock"],
        "receivedAt": node["received_at"],
        "firstSeen": node["first_seen"],
        "sampleCount": len(node["samples"]),
        "worstLevel": worst,
        "sensors": sensors,
    }


# ── App ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "[sensor] ready — stale after %.0fs, history %d, auth %s",
        STALE_AFTER_S, HISTORY_MAX, "on" if INGEST_KEY else "off (open LAN)",
    )
    yield


app = FastAPI(title="FireWatch Sensor Bridge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# Routes carry the full /api/sensors/ prefix because nginx forwards the original
# URI unchanged (its proxy_pass has no URI part) — same as the camera bridge.

@app.post("/api/sensors/ingest")
async def ingest(sample: Sample, x_device_key: str | None = Header(None)):
    """Accept one sweep from a node. Called by the board, not the browser."""
    if INGEST_KEY and x_device_key != INGEST_KEY:
        raise HTTPException(status_code=401, detail="Bad or missing X-Device-Key")

    if sample.deviceId not in NODES and len(NODES) >= MAX_NODES:
        raise HTTPException(
            status_code=429, detail=f"Too many nodes (limit {MAX_NODES})"
        )

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    readings = sample.readings.model_dump()

    node = NODES.get(sample.deviceId)
    if node is None:
        node = NODES[sample.deviceId] = {
            "deviceId": sample.deviceId,
            "first_seen": now_iso,
            "samples": deque(maxlen=HISTORY_MAX),
        }
        log.info("[sensor] new node %s (zone %s)", sample.deviceId, sample.zoneId)

    node.update(
        zoneId=sample.zoneId,
        readings=readings,
        seq=sample.seq,
        uptimeMs=sample.uptimeMs,
        rssi=sample.rssi,
        mock=sample.mock,
        received_at=now_iso,
        received_mono=time.monotonic(),
    )
    node["samples"].append({"t": now_iso, **readings})

    return {"ok": True, "deviceId": sample.deviceId, "receivedAt": now_iso}


@app.get("/api/sensors/latest")
async def latest():
    """Every known node with its most recent sweep. The dashboard polls this."""
    now = time.monotonic()
    nodes = sorted(
        (_node_json(n, now) for n in NODES.values()), key=lambda n: n["deviceId"]
    )
    return {
        "nodes": nodes,
        "nodeCount": len(nodes),
        "staleAfterMs": round(STALE_AFTER_S * 1000),
        "serverTime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {
            "mq2": {"warn": MQ2_WARN, "danger": MQ2_DANGER},
            "mq7": {"warn": MQ7_WARN, "danger": MQ7_DANGER},
            "temperature": {"warn": TEMP_WARN, "danger": TEMP_DANGER},
        },
    }


@app.get("/api/sensors/history")
async def history(
    deviceId: str = Query(..., pattern=r"^[A-Za-z0-9_.:-]{1,64}$"),
    limit: int = Query(120, ge=1, le=HISTORY_MAX),
):
    """The node's recent samples, oldest first — for sparklines and debugging."""
    node = NODES.get(deviceId)
    if node is None:
        raise HTTPException(status_code=404, detail=f"No node '{deviceId}' has reported")
    samples = list(node["samples"])[-limit:]
    return {"deviceId": deviceId, "count": len(samples), "samples": samples}


@app.get("/health")
async def health():
    """Container liveness. Never blocks on a node."""
    now = time.monotonic()
    return {
        "status": "ok",
        "service": "sensor-service",
        "nodes": len(NODES),
        "fresh": sum(
            1 for n in NODES.values()
            if (now - n["received_mono"]) < STALE_AFTER_S
        ),
        "authRequired": bool(INGEST_KEY),
    }
