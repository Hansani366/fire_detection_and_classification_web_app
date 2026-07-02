"""
FireWatch alert-service — the mobile app's backend.

Holds site state (zones / incidents / history), receives confirmed-fire events
from the detection producers, sends FCM push notifications, and auto-clears
incidents when the fire stops. See CLAUDE-style notes in the sibling modules.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db as store
import fcm
import intake
import serializers as ser
from zones_seed import DEFAULT_ZONE_ID, ZONES_BY_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("alert")


# ── Request bodies ───────────────────────────────────────────────────────────

class DeviceIn(BaseModel):
    token: str
    platform: str | None = "android"
    label: str | None = None


class FireEventIn(BaseModel):
    zoneId: str = DEFAULT_ZONE_ID
    type: str | None = "fire"
    confidence: float | None = 0.0
    description: str | None = ""
    detectedAt: str | None = None


class ClearIn(BaseModel):
    zoneId: str = DEFAULT_ZONE_ID


class TestAlertIn(BaseModel):
    zoneId: str | None = None


# ── Lifespan: open DB, init FCM, run the auto-clear watchdog ──────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await store.connect()
    await store.init_db(app.state.db)
    fcm.init_fcm()
    app.state.watchdog = asyncio.create_task(intake.auto_clear_watchdog(app.state.db))
    log.info("alert-service ready.")
    try:
        yield
    finally:
        app.state.watchdog.cancel()
        try:
            await app.state.watchdog
        except asyncio.CancelledError:
            pass
        await app.state.db.close()


app = FastAPI(title="FireWatch alert-service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _db():
    return app.state.db


# ── App-facing endpoints ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "fcm": fcm.is_ready()}


@app.post("/api/devices")
async def register_device(body: DeviceIn):
    if not body.token:
        raise HTTPException(400, "token required")
    await store.upsert_device(_db(), body.token, body.platform, body.label)
    log.info("Registered device %s… (%s)", body.token[:12], body.label or "unlabelled")
    return {"ok": True}


async def _active_incident_json():
    inc = await store.get_latest_active_incident(_db())
    if not inc:
        return None
    zone = await store.get_zone(_db(), inc["zone_id"])
    return ser.incident_json(inc, zone)


@app.get("/api/state")
async def get_state():
    zones = await store.get_zones(_db())
    return ser.state_json(zones, await _active_incident_json())


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    inc = await store.get_incident(_db(), incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    zone = await store.get_zone(_db(), inc["zone_id"])
    return ser.incident_json(inc, zone)


@app.post("/api/incidents/{incident_id}/ack")
async def ack_incident(incident_id: str):
    inc = await store.get_incident(_db(), incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    await store.bump_muster(_db(), incident_id)
    return {"ok": True}


@app.get("/api/history")
async def get_history():
    out = []
    for inc in await store.get_resolved_incidents(_db()):
        z = ZONES_BY_ID.get(inc["zone_id"], {"name": inc["zone_id"], "floor": "Main floor"})
        out.append(ser.history_json(inc, z["name"], z["floor"]))
    return out


# ── Event intake (called by the browser dashboard / future producers) ─────────

@app.post("/api/events/fire")
async def report_fire(body: FireEventIn):
    return await intake.handle_confirmed_fire(
        _db(), body.zoneId, body.type, body.confidence, body.description, body.detectedAt,
    )


@app.post("/api/events/clear")
async def report_clear(body: ClearIn):
    return await intake.handle_clear(_db(), body.zoneId)


@app.post("/api/test-alert")
async def test_alert(body: TestAlertIn | None = None):
    zone_id = (body.zoneId if body and body.zoneId else DEFAULT_ZONE_ID)
    return await intake.handle_confirmed_fire(
        _db(), zone_id, "fire", 0.92,
        "Open flames are visible among the fabric rolls with smoke rising toward the ceiling.",
        None, force=True,
    )
