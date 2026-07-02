"""
Firebase Cloud Messaging sender (HTTP v1 via firebase-admin).

Designed to degrade gracefully: if the service-account key is missing or
firebase-admin isn't installed, the service still runs and every other endpoint
(state / events / history / dedupe / auto-clear) works — pushes are just logged
instead of sent. This lets you test the whole pipeline before Firebase is wired.
"""

import logging
import os

log = logging.getLogger("alert.fcm")

CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS", "/secrets/firebase-sa.json")
FIRE_CHANNEL_ID = "fire_alerts"  # MUST match the Android notification channel the app creates

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


def _build_message(token: str, ctx: dict):
    m = _messaging
    return m.Message(
        token=token,
        notification=m.Notification(
            title=f"🔥 Fire detected — {ctx['zone_name']}, {ctx['floor']}",
            body="Two AI checks confirmed flames. Tap for your safe route.",
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


def send_fire_push(tokens: list[str], ctx: dict) -> list[str]:
    """
    Send one fire alert to every token. Returns the list of dead tokens
    (unregistered / sender-mismatch) so the caller can prune them.
    """
    if not tokens:
        log.info("No registered devices — nothing to push for incident %s.", ctx.get("id"))
        return []
    if not _ready:
        log.warning(
            "[FCM disabled] Would push fire alert for incident %s (zone %s) to %d device(s).",
            ctx.get("id"), ctx.get("zone_id"), len(tokens),
        )
        return []

    m = _messaging
    dead: list[str] = []
    try:
        messages = [_build_message(t, ctx) for t in tokens]
        resp = m.send_each(messages)
        for token, r in zip(tokens, resp.responses):
            if not r.success and r.exception is not None:
                name = type(r.exception).__name__
                if name in ("UnregisteredError", "SenderIdMismatchError"):
                    dead.append(token)
                else:
                    log.warning("FCM send to %s… failed: %s", token[:12], r.exception)
        log.info(
            "Pushed fire alert for incident %s: %d ok, %d dead token(s).",
            ctx.get("id"), resp.success_count, len(dead),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("FCM send failed for incident %s: %s", ctx.get("id"), exc)
    return dead
