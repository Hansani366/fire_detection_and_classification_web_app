"""
FireWatch alert-service — the mobile app's backend.

Holds site state (zones / incidents / history), receives confirmed-fire events
from the detection producers, sends FCM push notifications, and auto-clears
incidents when the fire stops. See CLAUDE-style notes in the sibling modules.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db as store
import routing
import sites
import extinguishers as ext
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
    # Which alarm tier this is. 'gas_danger' is tier 1b: dangerous gas with
    # nothing visible on camera. Defaulted to None (meaning 'fire') so an older
    # producer that does not send it keeps behaving exactly as before.
    severity: str | None = None
    # Whether the vision-language model was reachable (Algorithm 3). Defaults to
    # 'confirmed' for the same backwards-compatibility reason. 'unavailable'
    # means the alarm stands on detection evidence alone.
    verification: str | None = "confirmed"


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
    """Demo hook. `severity` lets a demo exercise the quiet and sensor-only
    tiers too -- otherwise the only way to see a gas warning or a carbon-monoxide
    alarm on a phone is to actually produce the gas."""
    zoneId: str | None = None
    occupancy: int | None = None
    severity: str | None = "fire"   # fire | gas_danger | warning


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


def _zone_or_stub(zone: dict | None, zone_id: str) -> dict:
    """A zone row, or a readable stand-in for one that is no longer seeded.

    An incident outlives the zone catalogue: switch sites, or rename a zone, and
    old rows point at ids that are gone. `zone_json(None)` raises, which turns a
    single stale row into a 500 on /api/state -- and the phone swallows that by
    design, so it would show stale data forever with no error anywhere. Degrade
    to a named stub instead and keep serving.
    """
    if zone:
        return zone
    log.warning("Incident references unknown zone %r; serving a stub.", zone_id)
    return {"id": zone_id, "name": zone_id.replace("-", " ").title(),
            "floor": "Unknown", "detector_id": "", "status": "clear",
            "last_scan_at": None, "glyph": "fabricRoll"}


async def _active_incident_json():
    inc = await store.get_latest_active_incident(_db())
    if not inc:
        return None
    zone = await store.get_zone(_db(), inc["zone_id"])
    return ser.incident_json(inc, _zone_or_stub(zone, inc["zone_id"]))


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
    return ser.incident_json(inc, _zone_or_stub(zone, inc["zone_id"]))


@app.get("/api/incidents/{incident_id}/report")
async def get_incident_report(incident_id: str):
    """The record of one incident, for reading after it is over.

    Separate from /api/incidents/{id}, which is the live view the phone polls
    while a fire is burning. A report is read afterwards and answers different
    questions -- when did the system know what, and how long did each step
    take -- so it carries a timeline and the gaps between its stamps.
    """
    inc = await store.get_incident(_db(), incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    zone = await store.get_zone(_db(), inc["zone_id"])
    return ser.report_json(inc, _zone_or_stub(zone, inc["zone_id"]))


@app.get("/api/incidents/{incident_id}/route")
async def get_incident_route(incident_id: str):
    """The full stored route record, for analysis. The phone does not call this.

    Superset of the `route` block on the incident: it also carries the node path,
    the blocked edge set and the latency, which the app has no use for and the
    route-validity analysis cannot do without.
    """
    inc = await store.get_incident(_db(), incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    if inc.get("route_error"):
        return {"incidentId": incident_id, "route": None, "error": inc["route_error"]}
    if not inc.get("route_json"):
        return {"incidentId": incident_id, "route": None, "error": "not generated"}
    return {
        "incidentId": incident_id,
        "route": json.loads(inc["route_json"]),
        "blocked": json.loads(inc.get("route_blocked_json") or "{}"),
        "latencyMs": inc.get("route_latency_ms"),
        "generatedAt": inc.get("route_generated_at"),
        "error": None,
    }


@app.get("/api/site/plan")
async def get_site_plan():
    """Which facility this service is routing for.

    The app carries its own drawing for each site, so this is not geometry -- it
    is the handshake that says which drawing to use and which coordinate space
    the route arrives in. A mismatch here is the bug where a correct route is
    drawn through the walls of a different building.
    """
    site = sites.ACTIVE
    return {
        "siteKey": site.key,
        "siteName": site.name,
        "revision": site.revision,
        "designSize": {"w": site.design_w, "h": site.design_h},
        "pxPerM": site.px_per_m,
        "hazardRadiusM": site.hazard_radius_m,
        "exits": [{"id": x.id, "name": x.name, "priority": x.priority}
                  for x in sorted(site.exits.values(), key=lambda e: (e.priority, e.id))],
        "zoneIds": [z["id"] for z in site.zones],
    }


@app.get("/api/analysis/routes")
async def analyse_routes(limit: int = 200):
    """The four route measures of Section 3.4.8, computed from STORED rows.

    Nothing is re-derived against today's graph: validity and hazard intersection
    are checked against the hazard point, radius and plan revision each route was
    actually generated under. Recomputing would re-answer the question about a
    building that has since been edited.

    Incidents whose routing failed are counted in `errors` and in neither rate, so
    the denominators stay honest.
    """
    site = sites.ACTIVE
    rows, errors = [], 0
    for inc in await store.get_all_incidents(_db(), limit):
        if inc.get("route_error") or not inc.get("route_json"):
            errors += 1
            continue
        record = json.loads(inc["route_json"])
        ok, reasons = routing.validate(site, record)
        intersects = routing.hazard_intersects(site, record)
        gt = site.ground_truth.get(record.get("fireZoneId")) or {}

        gap = None
        if gt and not gt.get("refugeExpected") and gt.get("lengthM"):
            gap = (record["lengthM"] - gt["lengthM"]) / gt["lengthM"]

        if not gt:
            refusal = "n/a"
        elif gt["refugeExpected"] and record["status"] == "refuge":
            refusal = "correct"
        elif gt["refugeExpected"]:
            refusal = "missed"          # routed someone past a fire: the bad one
        elif record["status"] == "refuge":
            refusal = "false_refuge"    # refused when a way out existed
        else:
            refusal = "n/a"

        rows.append({
            "incidentId": inc["id"], "fireZoneId": record.get("fireZoneId"),
            "status": record.get("status"), "exitId": record.get("exitId"),
            "lengthM": record.get("lengthM"),
            "generationMs": record.get("generatedInMs"),
            "latencyMs": inc.get("route_latency_ms"),
            "planRevision": record.get("planRevision"),
            "valid": ok, "invalidReasons": reasons,
            "hazardIntersects": intersects,
            "optimalityGap": gap, "refusal": refusal,
            "expectedExitId": gt.get("exitId"),
        })

    n = len(rows) or 1
    lat = sorted(r["latencyMs"] for r in rows if r["latencyMs"] is not None)

    def _pct(vals, p):
        if not vals:
            return None
        return round(vals[min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1))))], 1)

    return {
        "siteKey": site.key, "planRevision": site.revision,
        "count": len(rows), "errors": errors,
        "summary": {
            "validityRate": round(sum(r["valid"] for r in rows) / n, 4),
            # Must be zero. Any row above zero is a routing bug, not a statistic.
            "hazardIntersectionRate": round(sum(r["hazardIntersects"] for r in rows) / n, 4),
            "correctRefusals": sum(r["refusal"] == "correct" for r in rows),
            "missedRefusals": sum(r["refusal"] == "missed" for r in rows),
            "falseRefuges": sum(r["refusal"] == "false_refuge" for r in rows),
            "latencyMs": {"p50": _pct(lat, 50), "p95": _pct(lat, 95),
                          "max": (round(lat[-1], 1) if lat else None),
                          # RO2.2's five-second claim, counted rather than asserted.
                          "countOver5000ms": sum(v > 5000 for v in lat)},
        },
        "rows": rows,
    }


@app.post("/api/incidents/{incident_id}/ack")
async def ack_incident(incident_id: str):
    inc = await store.get_incident(_db(), incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    await store.bump_muster(_db(), incident_id)
    return {"ok": True}


@app.get("/api/extinguishers")
async def get_extinguishers():
    """The full response table, for any screen with room to show it.

    Served rather than duplicated so the dashboard, the phone and the incident
    record give the same answer about the same fire. Static, so a client can
    fetch it once at start-up.
    """
    return {
        "fuels": ext.EXTINGUISHERS,
        "universalCautions": ext.UNIVERSAL_CAUTIONS,
        # Said once, here, rather than repeated on every card: the classifier
        # has three fuel classes and real fires have more.
        "modelLimits": [
            "Cooking oil is class F and needs wet chemical. This model has no "
            "class F and will report a chip-pan fire as liquid fuel.",
            "The model cannot see whether electrical equipment is live, which "
            "changes the correct extinguisher whatever is burning.",
        ],
    }


@app.get("/api/history")
async def get_history():
    out = []
    for inc in await store.get_resolved_incidents(_db()):
        z = ZONES_BY_ID.get(inc["zone_id"], {"name": inc["zone_id"], "floor": "Main floor"})
        out.append(ser.history_json(inc, z["name"], z["floor"]))
    return out


# ── Event intake (called by the browser dashboard / future producers) ─────────

FIRE_SEVERITIES = ("fire", "gas_danger")
# "not_applicable" is tier 1b: dangerous gas with no camera detection, so there
# was never a box to verify. Distinct from "unavailable", which means we asked
# and could not reach the model.
VERIFICATION_RESULTS = ("confirmed", "rejected", "unavailable", "not_applicable")


@app.post("/api/events/fire")
async def report_fire(body: FireEventIn):
    # Validated here rather than on the model, matching how ClassificationIn.source
    # is handled: a bad value is a caller bug and deserves a 400, not a silent
    # coercion that would put an unreadable severity in the incident record.
    severity = body.severity or "fire"
    if severity not in FIRE_SEVERITIES:
        raise HTTPException(400, f"severity must be one of {FIRE_SEVERITIES}")
    verification = body.verification or "confirmed"
    if verification not in VERIFICATION_RESULTS:
        raise HTTPException(400, f"verification must be one of {VERIFICATION_RESULTS}")
    return await intake.handle_confirmed_fire(
        _db(), body.zoneId, body.type, body.confidence, body.description, body.detectedAt,
        occupancy=body.occupancy, severity=severity, verification=verification,
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
    severity = (body.severity if body and body.severity else "fire")
    if severity not in ("fire", "gas_danger", "warning"):
        raise HTTPException(400, "severity must be fire, gas_danger or warning")

    if severity == "warning":
        # Tier 1a: no siren, separate channel, zone stays clear.
        return await intake.handle_warning(
            _db(), zone_id,
            "Gas readings are above normal. No fire seen on camera.",
            "MQ-2 620 ppm (warn), CO 45 ppm (warn)", None, occupancy=occupancy,
        )

    if severity == "gas_danger":
        # Tier 1b: alarms, but nothing is visible, so confidence is genuinely 0.
        return await intake.handle_confirmed_fire(
            _db(), zone_id, "smoke", 0.0,
            "Dangerous gas levels with nothing visible on camera. "
            "MQ-7 118 ppm (danger).",
            None, force=True, occupancy=occupancy,
            severity="gas_danger", verification="not_applicable",
        )

    return await intake.handle_confirmed_fire(
        _db(), zone_id, "fire", 0.92,
        "Open flames are visible among the fabric rolls with smoke rising toward the ceiling.",
        None, force=True, occupancy=occupancy,
    )
