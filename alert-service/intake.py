"""
Core alerting logic shared by every fire producer (browser dashboard today,
a server-side monitor later): dedupe on the way in, push exactly once, and
auto-clear when the fire stops being reported.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import db as store
import fcm
from zones_seed import DEFAULT_ZONE_ID, ZONES_BY_ID

log = logging.getLogger("alert.intake")

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))     # min gap between separate incidents in a zone
CLEAR_AFTER_SECONDS = int(os.getenv("CLEAR_AFTER_SECONDS", "30"))  # no fire event for this long → auto-clear
WATCHDOG_INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "5"))

# Serialises the read-then-create dedupe check so two near-simultaneous events
# can't both create an incident for the same zone.
_lock = asyncio.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return _utcnow()


def _zone_status_for(det_type: str) -> str:
    return "smoke" if det_type == "smoke" else "fire"


async def handle_confirmed_fire(db, zone_id, det_type, confidence, description, detected_at,
                                force=False, occupancy=None) -> dict:
    """
    Called on every confirmed-fire event. Returns {"incidentId", "created"}.
    De-dupes: repeat events for an already-active incident refresh it silently;
    a zone that just cleared stays quiet for COOLDOWN_SECONDS. `force=True`
    (used by /api/test-alert) skips the cooldown so demos always fire.

    `occupancy` is how many people the human detector can see in the zone, or
    None if it had nothing to report. It refreshes on every repeat event, so the
    muster count tracks the room emptying — see serializers.muster_json.
    """
    if zone_id not in ZONES_BY_ID:
        log.warning("Unknown zone '%s' — falling back to %s.", zone_id, DEFAULT_ZONE_ID)
        zone_id = DEFAULT_ZONE_ID
    det_type = det_type or "fire"
    confidence = float(confidence or 0.0)
    detected_at = detected_at or _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")
    occupancy = None if occupancy is None else max(0, int(occupancy))

    escalated = None
    async with _lock:
        active = await store.get_active_incident_for_zone(db, zone_id)
        if active and (active.get("severity") or "fire") == "warning":
            # THE UPGRADE PATH, and the reason tier 3 is not a separate event.
            # Gas reaches the sensor 14-22s after a camera sees the flame, so a
            # warning already open in this zone is almost always this same fire
            # detected earlier by a slower signal. Escalating it in place keeps
            # one incident, one muster and one timeline; opening a second would
            # show the responder two fires in one room.
            inc = await store.escalate_incident(
                db, active["id"], det_type, confidence, description, detected_at, occupancy)
            await store.set_zone_status(db, zone_id, _zone_status_for(det_type))
            log.info("Escalated warning %s to fire (zone %s).", active["id"], zone_id)
            escalated = inc
        elif active:
            await store.touch_incident(db, active["id"], confidence, description,
                                       _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"),
                                       occupancy)
            return {"incidentId": active["id"], "created": False, "reason": "already_active"}

    if escalated is not None:
        # Push outside the lock, exactly as a new incident does: the phone was
        # told about a quiet warning and must now be told it is a fire.
        zone = ZONES_BY_ID[zone_id]
        tokens = await store.list_tokens(db)
        dead = fcm.send_fire_push(tokens, {
            "id": escalated["id"], "zone_id": zone_id, "zone_name": zone["name"],
            "floor": zone["floor"], "detector_id": zone["detector_id"], "type": det_type,
            "confidence": confidence, "description": description,
            "detected_at": detected_at, "occupancy": occupancy,
        })
        if dead:
            await store.delete_tokens(db, dead)
        return {"incidentId": escalated["id"], "created": False, "reason": "escalated_from_warning"}

    async with _lock:

        last = await store.get_last_resolved_for_zone(db, zone_id)
        if not force and last and last.get("resolved_at"):
            since = (_utcnow() - _parse(last["resolved_at"])).total_seconds()
            if since < COOLDOWN_SECONDS:
                log.info("Zone %s cleared %.0fs ago (< %ds cooldown) — suppressing.", zone_id, since, COOLDOWN_SECONDS)
                return {"incidentId": None, "created": False, "reason": "cooldown"}

        incident_id = f"inc_{uuid4().hex[:8]}"
        inc = await store.create_incident(db, incident_id, zone_id, det_type, confidence,
                                          description, detected_at, occupancy)
        await store.set_zone_status(db, zone_id, _zone_status_for(det_type))
        log.info("New incident %s in zone %s (type=%s conf=%.2f occupancy=%s).",
                 incident_id, zone_id, det_type, confidence,
                 "unknown" if occupancy is None else occupancy)

    # Push outside the lock (network I/O shouldn't block the intake path).
    zone = ZONES_BY_ID[zone_id]
    ctx = {
        "id": inc["id"], "zone_id": zone_id, "zone_name": zone["name"], "floor": zone["floor"],
        "detector_id": zone["detector_id"], "type": det_type, "confidence": confidence,
        "description": description, "detected_at": detected_at, "occupancy": occupancy,
    }
    tokens = await store.list_tokens(db)
    dead = fcm.send_fire_push(tokens, ctx)
    if dead:
        await store.delete_tokens(db, dead)

    return {"incidentId": inc["id"], "created": True}


async def handle_warning(db, zone_id, description, sensor_summary, detected_at,
                         occupancy=None) -> dict:
    """Tier 1a: gas above normal, nothing visible. Records and notifies, never alarms.

    Kept deliberately quiet. Gas sensors react to cooking, aerosols, solvents
    and vehicle exhaust, so a warning that sounded the fire alarm would train
    people to ignore the fire alarm. It opens a `warning`-severity incident so
    the event is on the timeline and so a later flame can escalate it in place.
    """
    if zone_id not in ZONES_BY_ID:
        zone_id = DEFAULT_ZONE_ID
    detected_at = detected_at or _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")
    occupancy = None if occupancy is None else max(0, int(occupancy))

    async with _lock:
        active = await store.get_active_incident_for_zone(db, zone_id)
        if active:
            # A fire already open outranks a warning: refresh it and say nothing
            # more. Downgrading a fire to a warning would be dangerous.
            await store.touch_incident(
                db, active["id"], active["confidence"] or 0.0,
                active["description"] or description,
                _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"), occupancy)
            return {"incidentId": active["id"], "created": False,
                    "reason": "already_active",
                    "severity": active.get("severity") or "fire"}

        last = await store.get_last_resolved_for_zone(db, zone_id)
        if last and last.get("resolved_at"):
            since = (_utcnow() - _parse(last["resolved_at"])).total_seconds()
            if since < COOLDOWN_SECONDS:
                return {"incidentId": None, "created": False, "reason": "cooldown"}

        incident_id = f"warn_{uuid4().hex[:8]}"
        inc = await store.create_incident(
            db, incident_id, zone_id, "gas", 0.0, description, detected_at,
            occupancy, severity="warning")
        # The zone status stays 'clear'. Nothing is burning, and turning the
        # map red for a gas reading is exactly the false confidence tier 1a
        # exists to avoid.
        log.info("New gas warning %s in zone %s.", incident_id, zone_id)

    zone = ZONES_BY_ID[zone_id]
    tokens = await store.list_tokens(db)
    dead = fcm.send_warning_push(tokens, {
        "id": inc["id"], "zone_id": zone_id, "zone_name": zone["name"],
        "floor": zone["floor"], "detector_id": zone["detector_id"],
        "description": description, "detected_at": detected_at,
        "sensor_summary": sensor_summary,
    })
    if dead:
        await store.delete_tokens(db, dead)
    return {"incidentId": inc["id"], "created": True, "severity": "warning"}


async def handle_classification(db, zone_id, fuel_type, confidence, source,
                                occupancy=None) -> dict:
    """Tier 3: attach the fusion model's fuel verdict to the open fire.

    Only pushes when the verdict CHANGES. The dashboard asks for a
    classification every second; notifying every time would bury the responder
    under identical messages, and the one thing they need from this -- which
    extinguisher -- does not change unless the answer does.
    """
    if zone_id not in ZONES_BY_ID:
        zone_id = DEFAULT_ZONE_ID

    async with _lock:
        active = await store.get_active_incident_for_zone(db, zone_id)
        if not active:
            return {"incidentId": None, "applied": False, "reason": "no_active_incident"}
        if (active.get("severity") or "fire") != "fire":
            # Classifying a gas warning would assert a fire nobody has seen.
            return {"incidentId": active["id"], "applied": False, "reason": "not_a_fire"}
        previous = active.get("fuel_type")
        inc = await store.set_classification(db, active["id"], fuel_type, confidence, source)

    changed = previous != fuel_type and fuel_type is not None and source == "model"
    if changed:
        zone = ZONES_BY_ID[zone_id]
        tokens = await store.list_tokens(db)
        dead = fcm.send_classification_push(tokens, {
            "id": inc["id"], "zone_id": zone_id, "zone_name": zone["name"],
            "floor": zone["floor"], "fuel_type": fuel_type,
            "fuel_confidence": confidence,
            "occupancy": occupancy if occupancy is not None else inc.get("occupancy_current"),
        })
        if dead:
            await store.delete_tokens(db, dead)
        log.info("Incident %s classified as %s (%.2f).", inc["id"], fuel_type, confidence or 0.0)

    return {"incidentId": inc["id"], "applied": True, "changed": changed,
            "fuelType": fuel_type}


async def handle_clear(db, zone_id: str) -> dict:
    """A producer signals its alarm went off — resolve promptly on the next watchdog tick."""
    if zone_id in ZONES_BY_ID:
        active = await store.get_active_incident_for_zone(db, zone_id)
        if active:
            await store.mark_incident_idle(db, active["id"])
            return {"incidentId": active["id"], "cleared": True}
    return {"cleared": False}


async def _resolve_idle_once(db) -> int:
    """Resolve any active incident with no fresh fire event in CLEAR_AFTER_SECONDS. Returns count resolved."""
    resolved = 0
    for inc in await store.get_active_incidents(db):
        idle = (_utcnow() - _parse(inc["last_event_at"])).total_seconds()
        if idle >= CLEAR_AFTER_SECONDS:
            await store.resolve_incident(db, inc["id"], "auto_cleared")
            await store.set_zone_status(db, inc["zone_id"], "clear")
            log.info("Auto-cleared incident %s (zone %s, idle %.0fs).", inc["id"], inc["zone_id"], idle)
            resolved += 1
    return resolved


async def auto_clear_watchdog(db) -> None:
    """Background loop: return zones to 'clear' and move incidents into history once the fire stops."""
    log.info("Auto-clear watchdog running (idle=%ds, every %ds).", CLEAR_AFTER_SECONDS, WATCHDOG_INTERVAL)
    while True:
        try:
            await _resolve_idle_once(db)
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            log.error("Watchdog tick failed: %s", exc)
        await asyncio.sleep(WATCHDOG_INTERVAL)
