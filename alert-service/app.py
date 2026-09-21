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
    # People the human detector can see in the zone. None means it had nothing
    # to report, which is not the same as an empty room — see db.touch_incident.
    occupancy: int | None = None


class WarningIn(BaseModel):
    """Tier 1a: gas above normal with nothing visible. Never sounds the alarm."""
    zoneId: str = DEFAULT_ZONE_ID
    description: str | None = ""
    # A short human-readable line of the readings that triggered it, e.g.
    # "MQ-2 620 ppm (baseline 300), CO 45 ppm, 31 °C". Carried into the push so
    # the recipient can judge it without opening the app.
    sensorSummary: str | None = ""
    detectedAt: str | None = None
    occupancy: int | None = None


class ClassificationIn(BaseModel):
    """Tier 3: what the fusion model says is burning, for the open incident."""
    zoneId: str = DEFAULT_ZONE_ID
    fuelType: str | None = None          # gas_fire | liquid_fuel | solid_combustible
    confidence: float | None = None
    # 'model' when classified, 'unavailable' when the classifier was not ready.
    # Stored either way, so the report can say WHY there is no fuel type rather
    # than leaving a silent blank.
    source: str = "model"
    occupancy: int | None = None


class ClearIn(BaseModel):
    zoneId: str = DEFAULT_ZONE_ID


class TestAlertIn(BaseModel):
    zoneId: str | None = None
    occupancy: int | None = None


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
        occupancy=body.occupancy,
    )


@app.post("/api/events/warning")
async def report_warning(body: WarningIn):
    """Tier 1a. Records and notifies quietly; a later flame escalates it in place."""
    return await intake.handle_warning(
        _db(), body.zoneId, body.description, body.sensorSummary,
        body.detectedAt, occupancy=body.occupancy,
    )


@app.post("/api/events/classification")
async def report_classification(body: ClassificationIn):
    """Tier 3. Attaches the fuel verdict to whatever fire is already open."""
    if body.source not in ("model", "unavailable"):
        raise HTTPException(400, "source must be 'model' or 'unavailable'")
    return await intake.handle_classification(
        _db(), body.zoneId, body.fuelType, body.confidence, body.source,
        occupancy=body.occupancy,
    )


@app.post("/api/events/clear")
async def report_clear(body: ClearIn):
    return await intake.handle_clear(_db(), body.zoneId)


@app.post("/api/test-alert")
async def test_alert(body: TestAlertIn | None = None):
    zone_id = (body.zoneId if body and body.zoneId else DEFAULT_ZONE_ID)
    # A non-zero occupancy by default, so a demo alert exercises the muster
    # path the human detector feeds rather than falling back to the estimate.
    occupancy = body.occupancy if body and body.occupancy is not None else 7
    return await intake.handle_confirmed_fire(
        _db(), zone_id, "fire", 0.92,
        "Open flames are visible among the fabric rolls with smoke rising toward the ceiling.",
        None, force=True, occupancy=occupancy,
    )
