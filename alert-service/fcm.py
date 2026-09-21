"""
Firebase Cloud Messaging sender (HTTP v1 via firebase-admin).

Designed to degrade gracefully: if the service-account key is missing or
firebase-admin isn't installed, the service still runs and every other endpoint
(state / events / history / dedupe / auto-clear) works — pushes are just logged
instead of sent. This lets you test the whole pipeline before Firebase is wired.
"""

import logging
import os

# The response guidance lives in extinguishers.py, which the dashboard and the
# incident record read from too -- one table, so the phone, the screen and the
# report cannot give three different answers about the same fire.
from extinguishers import label_for, short_guidance

log = logging.getLogger("alert.fcm")

CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS", "/secrets/firebase-sa.json")
FIRE_CHANNEL_ID = "fire_alerts"  # MUST match the Android notification channel the app creates

# A SEPARATE CHANNEL, ON PURPOSE. A gas warning is not a fire: nothing is
# visibly burning and nobody should evacuate yet. If it arrived on
# FIRE_CHANNEL_ID it would play the fire sound at full volume, and after two or
# three cooking-smoke false alarms people mute the channel -- which silences
# the real fire alert too. A quieter channel is what keeps the loud one
# trusted. The app must create this channel; until it does, Android falls back
# to its default channel, which is still quieter than the fire one.
WARNING_CHANNEL_ID = "gas_warnings"

_ready = False
_messaging = None  # firebase_admin.messaging module, imported lazily


def init_fcm() -> bool:
    """Initialise firebase-admin if a credentials file is present. Returns readiness."""
    global _ready, _messaging
    if not os.path.exists(CREDENTIALS_PATH):
        log.warning(
            "FCM disabled: no service-account key at %s. "
            "Pushes will be logged, not sent. Drop firebase-sa.json in to enable.",
            CREDENTIALS_PATH,
        )
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(CREDENTIALS_PATH))
        _messaging = messaging
        _ready = True
        log.info("FCM ready (firebase-admin initialised from %s).", CREDENTIALS_PATH)
    except Exception as exc:  # noqa: BLE001 — never let FCM setup crash the service
        log.error("FCM init failed (%s). Pushes will be logged, not sent.", exc)
        _ready = False
    return _ready


def is_ready() -> bool:
    return _ready


def _notification_body(ctx: dict) -> str:
    """People still in the zone is the most actionable thing on a lock screen,
    so it goes in the body when the human detector has a number. A count of
    None means it had nothing to say — say nothing rather than imply zero."""
    occupancy = ctx.get("occupancy")
    if occupancy is None:
        return "Two AI checks confirmed flames. Tap for your safe route."
    if occupancy == 0:
        return "Two AI checks confirmed flames. No one detected in the zone."
    people = "1 person" if occupancy == 1 else f"{occupancy} people"
    return f"Two AI checks confirmed flames. {people} still in the zone."


def _build_message(token: str, ctx: dict):
    m = _messaging
    occupancy = ctx.get("occupancy")
    return m.Message(
        token=token,
        notification=m.Notification(
            title=f"🔥 Fire detected — {ctx['zone_name']}, {ctx['floor']}",
            body=_notification_body(ctx),
        ),
        data={
            "type": "fire_alert",
            "route": "/incident",
            "incidentId": str(ctx["id"]),
            "zoneId": str(ctx["zone_id"]),
            "zoneName": str(ctx["zone_name"]),
            "floor": str(ctx["floor"]),
            "detectorId": str(ctx.get("detector_id", "")),
            "detectionType": str(ctx["type"]),
            "confidence": str(ctx["confidence"]),
            "description": str(ctx["description"] or ""),
            "detectedAt": str(ctx["detected_at"]),
            # Empty string rather than "None" when unknown — the Dart side
            # parses these as strings and "None" would read as a real value.
            "occupancy": "" if occupancy is None else str(occupancy),
        },
        android=m.AndroidConfig(
            priority="high",
            notification=m.AndroidNotification(
                channel_id=FIRE_CHANNEL_ID,
                sound="default",
                priority="max",
                visibility="public",
            ),
        ),
    )


def _build_warning_message(token: str, ctx: dict):
    """Tier 1a: gas is rising and nothing is visible. Informational, not an alarm."""
    m = _messaging
    return m.Message(
        token=token,
        notification=m.Notification(
            title=f"⚠️ Gas levels rising — {ctx['zone_name']}, {ctx['floor']}",
            body=ctx.get("description") or "Sensor readings are above normal. No fire seen yet.",
        ),
        data={
            "type": "gas_warning",
            "route": "/incident",
            "severity": "warning",
            "incidentId": str(ctx["id"]),
            "zoneId": str(ctx["zone_id"]),
            "zoneName": str(ctx["zone_name"]),
            "floor": str(ctx["floor"]),
            "detectorId": str(ctx.get("detector_id", "")),
            "description": str(ctx.get("description") or ""),
            "detectedAt": str(ctx["detected_at"]),
            "sensors": str(ctx.get("sensor_summary") or ""),
        },
        android=m.AndroidConfig(
            # Deliberately NOT high/max and not the fire channel: this must not
            # look or sound like an evacuation.
            priority="normal",
            notification=m.AndroidNotification(
                channel_id=WARNING_CHANNEL_ID,
                priority="default",
                visibility="public",
            ),
        ),
    )


def _build_classification_message(token: str, ctx: dict):
    """Tier 3: the fire already alarmed; this says what is burning."""
    m = _messaging
    fuel = ctx.get("fuel_type") or ""
    label = label_for(fuel)
    guidance = short_guidance(fuel)
    return m.Message(
        token=token,
        notification=m.Notification(
            title=f"{label} — {ctx['zone_name']}, {ctx['floor']}",
            body=guidance or "Fuel type identified. Tap for details.",
        ),
        data={
            "type": "fire_classified",
            "route": "/incident",
            "severity": "fire",
            "incidentId": str(ctx["id"]),
            "zoneId": str(ctx["zone_id"]),
            "zoneName": str(ctx["zone_name"]),
            "floor": str(ctx["floor"]),
            "fuelType": str(fuel),
            "fuelConfidence": str(ctx.get("fuel_confidence") or ""),
            "fuelGuidance": guidance,
            "occupancy": "" if ctx.get("occupancy") is None else str(ctx["occupancy"]),
        },
        android=m.AndroidConfig(
            priority="high",
            notification=m.AndroidNotification(
                channel_id=FIRE_CHANNEL_ID,
                sound="default",
                priority="max",
                visibility="public",
            ),
        ),
    )


def _send(tokens: list[str], ctx: dict, builder, what: str) -> list[str]:
    """Shared send path. Returns dead tokens so the caller can prune them."""
    if not tokens:
        log.info("No registered devices — nothing to push for incident %s.", ctx.get("id"))
        return []
    if not _ready:
        log.warning(
            "[FCM disabled] Would push %s for incident %s (zone %s) to %d device(s).",
            what, ctx.get("id"), ctx.get("zone_id"), len(tokens),
        )
        return []

    m = _messaging
    dead: list[str] = []
    try:
        messages = [builder(t, ctx) for t in tokens]
        resp = m.send_each(messages)
        for token, r in zip(tokens, resp.responses):
            if not r.success and r.exception is not None:
                name = type(r.exception).__name__
                if name in ("UnregisteredError", "SenderIdMismatchError"):
                    dead.append(token)
                else:
                    log.warning("FCM send to %s… failed: %s", token[:12], r.exception)
        log.info(
            "Pushed %s for incident %s: %d ok, %d dead token(s).",
            what, ctx.get("id"), resp.success_count, len(dead),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("FCM send failed for incident %s: %s", ctx.get("id"), exc)
    return dead


def send_fire_push(tokens: list[str], ctx: dict) -> list[str]:
    return _send(tokens, ctx, _build_message, "fire alert")


def send_warning_push(tokens: list[str], ctx: dict) -> list[str]:
    return _send(tokens, ctx, _build_warning_message, "gas warning")


def send_classification_push(tokens: list[str], ctx: dict) -> list[str]:
    return _send(tokens, ctx, _build_classification_message, "fuel classification")
