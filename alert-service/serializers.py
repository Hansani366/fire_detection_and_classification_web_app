"""
Shape DB rows into the JSON the Flutter app expects.

These dicts are the source of truth for the Dart `fromJson` in
`firewatch/lib/data/models/models.dart`. Keys are camelCase to match Dart.
"""

from datetime import datetime, timezone

from zones_seed import HEALTH_STATIC, SITE_NAME


def _parse(ts: str) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def when_label(ts: str) -> str:
    """Human 'when' label mirroring the mock data ('Today 14:02', 'Yesterday 19:30', 'Mon 08:12', 'Jun 24')."""
    dt = _parse(ts).astimezone()
    now = datetime.now().astimezone()
    delta_days = (now.date() - dt.date()).days
    hm = dt.strftime("%H:%M")
    if delta_days <= 0:
        return f"Today {hm}"
    if delta_days == 1:
        return f"Yesterday {hm}"
    if delta_days < 7:
        return f"{dt.strftime('%a')} {hm}"
    return dt.strftime("%b %d").replace(" 0", " ")


def duration_min(detected_at: str, resolved_at: str) -> int:
    a, b = _parse(detected_at), _parse(resolved_at)
    mins = round((b - a).total_seconds() / 60)
    return max(1, mins)


def zone_json(z: dict) -> dict:
    return {
        "id": z["id"],
        "name": z["name"],
        "floor": z["floor"],
        "detectorId": z["detector_id"],
        "status": z["status"],
        "lastScanAt": z["last_scan_at"],
        "glyph": z["glyph"],
    }


def health_json(zones: list[dict]) -> list[dict]:
    online = len(zones)
    return [
        {"label": "Detectors", "value": f"{online} online", "ok": True},
        *HEALTH_STATIC,
    ]


def event_json(inc: dict) -> dict:
    return {
        "zoneId": inc["zone_id"],
        "type": inc["type"],
        "detected": True,
        "confidence": inc["confidence"],
        "description": inc["description"] or "",
        "detectedAt": inc["detected_at"],
    }


def incident_json(inc: dict, zone: dict) -> dict:
    return {
        "id": inc["id"],
        "zone": zone_json(zone),
        "event": event_json(inc),
        "muster": {
            "present": inc.get("muster_present", 42),
            "total": inc.get("muster_total", 45),
        },
    }


def _scene_notes(inc: dict) -> list[dict]:
    """One AI scene note from the incident description (the history-detail timeline)."""
    notes = []
    if inc.get("description"):
        state = "smoke" if inc["type"] == "smoke" else "fire"
        notes.append({
            "timeLabel": f"{_parse(inc['detected_at']).astimezone().strftime('%H:%M:%S')} · detected",
            "text": inc["description"],
            "state": state,
        })
        notes.append({
            "timeLabel": f"{_parse(inc['resolved_at']).astimezone().strftime('%H:%M:%S')} · cleared",
            "text": "No flame detected; scene confirmed clear.",
            "state": "cleared",
        })
    return notes


def history_json(inc: dict, zone_name: str, floor: str) -> dict:
    return {
        "id": f"h_{inc['id']}",
        "zoneName": zone_name,
        "type": inc["type"],
        "whenLabel": when_label(inc.get("resolved_at") or inc["detected_at"]),
        "durationMin": duration_min(inc["detected_at"], inc.get("resolved_at") or inc["detected_at"]),
        "floor": floor,
        "resolution": inc.get("resolution") or "auto_cleared",
        "peakConfidencePct": round((inc.get("confidence") or 0) * 100),
        "cause": None,
        "sceneNotes": _scene_notes(inc),
    }


def state_json(zones: list[dict], active_incident_json: dict | None) -> dict:
    return {
        "siteName": SITE_NAME,
        "detectorCount": len(zones),
        "allClear": all(z["status"] == "clear" for z in zones),
        "zones": [zone_json(z) for z in zones],
        "health": health_json(zones),
        "activeIncident": active_incident_json,
    }
