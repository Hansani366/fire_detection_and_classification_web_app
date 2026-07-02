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


async def handle_confirmed_fire(db, zone_id, det_type, confidence, description, detected_at, force=False) -> dict:
    """
    Called on every confirmed-fire event. Returns {"incidentId", "created"}.
    De-dupes: repeat events for an already-active incident refresh it silently;
    a zone that just cleared stays quiet for COOLDOWN_SECONDS. `force=True`
    (used by /api/test-alert) skips the cooldown so demos always fire.
    """
    if zone_id not in ZONES_BY_ID:
        log.warning("Unknown zone '%s' — falling back to %s.", zone_id, DEFAULT_ZONE_ID)
        zone_id = DEFAULT_ZONE_ID
    det_type = det_type or "fire"
    confidence = float(confidence or 0.0)
    detected_at = detected_at or _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")

    async with _lock:
        active = await store.get_active_incident_for_zone(db, zone_id)
        if active:
            await store.touch_incident(db, active["id"], confidence, description,
                                       _utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"))
            return {"incidentId": active["id"], "created": False, "reason": "already_active"}

        last = await store.get_last_resolved_for_zone(db, zone_id)
        if not force and last and last.get("resolved_at"):
            since = (_utcnow() - _parse(last["resolved_at"])).total_seconds()
            if since < COOLDOWN_SECONDS:
                log.info("Zone %s cleared %.0fs ago (< %ds cooldown) — suppressing.", zone_id, since, COOLDOWN_SECONDS)
                return {"incidentId": None, "created": False, "reason": "cooldown"}

        incident_id = f"inc_{uuid4().hex[:8]}"
        inc = await store.create_incident(db, incident_id, zone_id, det_type, confidence, description, detected_at)
        await store.set_zone_status(db, zone_id, _zone_status_for(det_type))
        log.info("New incident %s in zone %s (type=%s conf=%.2f).", incident_id, zone_id, det_type, confidence)

    # Push outside the lock (network I/O shouldn't block the intake path).
    zone = ZONES_BY_ID[zone_id]
    ctx = {
        "id": inc["id"], "zone_id": zone_id, "zone_name": zone["name"], "floor": zone["floor"],
        "detector_id": zone["detector_id"], "type": det_type, "confidence": confidence,
        "description": description, "detected_at": detected_at,
    }
    tokens = await store.list_tokens(db)
    dead = fcm.send_fire_push(tokens, ctx)
    if dead:
        await store.delete_tokens(db, dead)

    return {"incidentId": inc["id"], "created": True}


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
