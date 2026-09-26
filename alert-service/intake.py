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
import report as situation
import routing
import sites
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


def _route_for_push(inc: dict | None) -> dict | None:
    """The wire subset of a stored route, for the FCM payload."""
    if not inc:
        return None
    import serializers as ser  # local: avoids a cycle at module import
    return ser.route_json(inc)


async def _attach_report(db, incident_id: str, zone_id: str,
                         scene: dict | None, evidence: dict | None) -> None:
    """Grade the scene description and store what survives (RO3.1).

    The evidence the claims are checked against is assembled here rather than
    taken on trust from the caller: occupancy and the fuel verdict are read back
    off the incident row, because those are the numbers the rest of the system
    acts on. A caller that reported a different head-count from the one stored
    against the incident would otherwise be allowed to validate a claim against
    its own copy.

    Wrapped, like routing: a report is what the responder reads, but the alarm is
    what makes them look.
    """
    if not scene:
        return
    try:
        inc = await store.get_incident(db, incident_id)
        zone = ZONES_BY_ID.get(zone_id, {"id": zone_id, "name": zone_id})
        ev = dict(evidence or {})
        ev.setdefault("occupancy", (inc or {}).get("occupancy_current"))
        ev.setdefault("fuelType", (inc or {}).get("fuel_type"))
        built = situation.build(scene, ev, zone)
        await store.set_situation_report(db, incident_id, built)
        g = built["grounding"]
        log.info("Report for %s: %d claims, %d supported, %d withheld.",
                 incident_id, g["claims"], g["supported"], g["contradicted"])
    except Exception as exc:  # noqa: BLE001
        log.error("Situation report failed for %s: %s", incident_id, exc)


async def _attach_route(db, incident_id: str, zone_id: str, detected_at: str) -> None:
    """Generate and store the escape route for an open incident.

    ROUTING MUST NEVER BE ABLE TO SUPPRESS THE ALARM. Everything in here is
    wrapped, and a failure is recorded on the incident rather than raised: a
    missing route is a worse screen, but a missing alarm is a fire nobody was
    told about. The push goes out either way, from the caller, outside the lock.

    Cheap enough (sub-millisecond over tens of nodes, and no `await` inside) that
    it runs under the intake lock, which guarantees the route is stored before any
    reader can see the incident.
    """
    try:
        site = sites.ACTIVE
        if zone_id not in site.zone_anchors:
            await store.set_incident_route_error(
                db, incident_id, f"zone {zone_id!r} has no anchor in site {site.key!r}")
            return
        rr = routing.route_for_zone(site, fire_zone_id=zone_id)
        record = rr.to_record()
        blocked = {"edges": [list(e) for e in rr.blocked_edges],
                   "exits": list(rr.blocked_exit_ids),
                   "unreachable": list(rr.unreachable_exit_ids)}
        latency = None
        try:
            latency = max(0.0, (_utcnow() - _parse(detected_at)).total_seconds() * 1000.0)
        except Exception:  # noqa: BLE001 - a bad stamp must not lose the route
            pass
        await store.set_incident_route(db, incident_id, record, blocked, latency)
        log.info("Route for %s (%s): %s %s, %.1f m in %.2f ms",
                 incident_id, zone_id, rr.status, rr.exit_id or rr.refuge_node,
                 rr.length_m, rr.generation_ms)
    except Exception as exc:  # noqa: BLE001
        log.error("Route generation failed for %s: %s", incident_id, exc)
        try:
            await store.set_incident_route_error(db, incident_id, f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            pass


async def handle_confirmed_fire(db, zone_id, det_type, confidence, description, detected_at,
                                force=False, occupancy=None, severity="fire",
                                verification="confirmed", scene=None, evidence=None,
                                detection_mode=None) -> dict:
    """
    Called on every confirmed-fire event. Returns {"incidentId", "created"}.
    De-dupes: repeat events for an already-active incident refresh it silently;
    a zone that just cleared stays quiet for COOLDOWN_SECONDS. `force=True`
    (used by /api/test-alert) skips the cooldown so demos always fire.

    `occupancy` is how many people the human detector can see in the zone, or
    None if it had nothing to report. It refreshes on every repeat event, so the
    muster count tracks the room emptying — see serializers.muster_json.

    `severity` distinguishes tier 2 ('fire', a flame confirmed on camera) from
    tier 1b ('gas_danger', dangerous gas with nothing visible). Both alarm and
    both ride the fire channel — a camera cannot see carbon monoxide, so tier 1b
    has to be loud — but only one of them should claim a flame was seen.

    `scene` and `evidence` are the raw material for the situation report: the
    model's structured claims, and what the detectors and sensors logged for the
    same moment. Nothing from `scene` reaches a responder until report.py has
    graded it against `evidence` -- see _attach_report.

    `verification` records whether the vision-language model was reachable. It is
    stored rather than inferred, because 'unavailable' is not a rejection: per
    Algorithm 2 a fire box plus sensors above normal still confirms a fire when
    the VLM cannot be reached, and the responder is entitled to know that the
    alarm rests on detection evidence alone.
    """
    if zone_id not in ZONES_BY_ID:
        log.warning("Unknown zone '%s' — falling back to %s.", zone_id, DEFAULT_ZONE_ID)
        zone_id = DEFAULT_ZONE_ID
    det_type = det_type or "fire"
    severity = severity if severity in ("fire", "gas_danger") else "fire"
    verification = verification or "confirmed"
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
                db, active["id"], det_type, confidence, description, detected_at, occupancy,
                severity=severity, verification=verification)
            await store.set_zone_status(db, zone_id, _zone_status_for(det_type))
            # A warning carries no route (nothing is burning). Now something is.
            await _attach_route(db, active["id"], zone_id, detected_at)
            await store.set_detection_mode(db, active["id"], detection_mode)
            await _attach_report(db, active["id"], zone_id, scene, evidence)
            log.info("Escalated warning %s to fire (zone %s).", active["id"], zone_id)
            escalated = await store.get_incident(db, active["id"])
        elif active:
            await store.touch_incident(db, active["id"], confidence, description,
                                       _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"),
                                       occupancy)
            # THE LATE SCENE STILL COUNTS. The dashboard posts a fire twice: once
            # immediately, and once when the vision-language description comes
            # back. The immediate post opens the incident, so the one carrying
            # the description always arrives second and used to be thrown away
            # here -- which left every live incident with no situation report,
            # the one thing RO3.1 exists to produce. Accepting it on the refresh
            # path makes the order irrelevant: whichever post carries a scene
            # fills the report in, and once filled it is not rewritten, so the
            # ten-second keep-alives cannot overwrite it.
            if scene and not active.get("situation_report"):
                await _attach_report(db, active["id"], zone_id, scene, evidence)
            return {"incidentId": active["id"], "created": False, "reason": "already_active"}

    if escalated is not None:
        # Push outside the lock, exactly as a new incident does: the phone was
        # told about a quiet warning and must now be told it is a fire.
        zone = ZONES_BY_ID[zone_id]
        tokens = await store.list_tokens(db)
        # Stamp before dispatch, not after: the interval Table 3.19 measures
        # starts when the decision leaves this service.
        await store.record_push_sent(db, escalated["id"], tokens)
        dead = fcm.send_fire_push(tokens, {
            "id": escalated["id"], "zone_id": zone_id, "zone_name": zone["name"],
            "floor": zone["floor"], "detector_id": zone["detector_id"], "type": det_type,
            "confidence": confidence, "description": description,
            "detected_at": detected_at, "occupancy": occupancy,
            "severity": severity, "verification": verification,
            "route": _route_for_push(await store.get_incident(db, escalated["id"])),
        })
        if dead:
            await store.delete_tokens(db, dead)
        return {"incidentId": escalated["id"], "created": False, "reason": "escalated_from_warning"}

    async with _lock:

        last = await store.get_last_resolved_for_zone(db, zone_id)
        # A WARNING MUST NEVER GATE A FIRE. The cooldown exists to stop one
        # fire from being reported as several incidents while it flickers in
        # and out of view. A gas warning is not a fire, so letting it start
        # that cooldown means a genuine fire in the two minutes after someone
        # opens a window is silently dropped -- no incident, no push, no alarm
        # on anyone's phone. Found by testing exactly that sequence.
        gating = last and (last.get("severity") or "fire") == "fire"
        if not force and gating and last.get("resolved_at"):
            since = (_utcnow() - _parse(last["resolved_at"])).total_seconds()
            if since < COOLDOWN_SECONDS:
                log.info("Zone %s cleared %.0fs ago (< %ds cooldown) — suppressing.", zone_id, since, COOLDOWN_SECONDS)
                return {"incidentId": None, "created": False, "reason": "cooldown"}

        incident_id = f"inc_{uuid4().hex[:8]}"
        inc = await store.create_incident(db, incident_id, zone_id, det_type, confidence,
                                          description, detected_at, occupancy,
                                          severity=severity, verification=verification)
        await store.set_zone_status(db, zone_id, _zone_status_for(det_type))
        await _attach_route(db, incident_id, zone_id, detected_at)
        await store.set_detection_mode(db, incident_id, detection_mode)
        await _attach_report(db, incident_id, zone_id, scene, evidence)
        log.info("New incident %s in zone %s (type=%s conf=%.2f occupancy=%s).",
                 incident_id, zone_id, det_type, confidence,
                 "unknown" if occupancy is None else occupancy)

    # Push outside the lock (network I/O shouldn't block the intake path).
    zone = ZONES_BY_ID[zone_id]
    ctx = {
        "id": inc["id"], "zone_id": zone_id, "zone_name": zone["name"], "floor": zone["floor"],
        "detector_id": zone["detector_id"], "type": det_type, "confidence": confidence,
        "description": description, "detected_at": detected_at, "occupancy": occupancy,
        "severity": severity, "verification": verification,
        "route": _route_for_push(await store.get_incident(db, inc["id"])),
    }
    tokens = await store.list_tokens(db)
    await store.record_push_sent(db, inc["id"], tokens)
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
            occupancy, severity="warning", verification="not_applicable",
            sensor_summary=sensor_summary)
        # The zone status stays 'clear'. Nothing is burning, and turning the
        # map red for a gas reading is exactly the false confidence tier 1a
        # exists to avoid.
        log.info("New gas warning %s in zone %s.", incident_id, zone_id)

    zone = ZONES_BY_ID[zone_id]
    tokens = await store.list_tokens(db)
    await store.record_push_sent(db, inc["id"], tokens)
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
