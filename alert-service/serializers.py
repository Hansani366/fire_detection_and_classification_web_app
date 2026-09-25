"""
Shape DB rows into the JSON the Flutter app expects.

These dicts are the source of truth for the Dart `fromJson` in
`firewatch/lib/data/models/models.dart`. Keys are camelCase to match Dart.
"""

import json
from datetime import datetime, timezone

import extinguishers as ext
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


def muster_json(inc: dict) -> dict:
    """Evacuation progress, derived from the human detector where possible.

    OCCUPANCY IS NOT MUSTER, AND THE TWO MOVE IN OPPOSITE DIRECTIONS. The camera
    counts people *still in the zone*; `present` means people *accounted for*
    away from it. So the head-count that was in the room when the fire started
    becomes the total, and everyone no longer visible has, as far as we can
    tell, got out:

        total   = peak occupancy seen since the incident opened
        present = peak - current occupancy

    As the zone empties, current falls to 0 and present rises to meet total.

    THIS SEES ONE CAMERA'S FIELD OF VIEW, not the whole zone. Someone who was
    never in frame is never in the total, and someone who walks out of shot
    counts as evacuated. It is a far better number than the synthetic constant
    it replaces, but it is an estimate and the app should treat it as one.

    Falls back to the stored (synthetic) figures when no occupancy was ever
    recorded — an incident from before this existed, or one raised while the
    human detector was down.
    """
    peak = inc.get("occupancy_peak")
    if peak is None:
        return {
            "present": inc.get("muster_present", 42),
            "total": inc.get("muster_total", 45),
            "source": "estimated",
        }
    # An unknown current count must NOT read as an empty room: "we lost the
    # camera" would otherwise render as "everyone is out", which is the one
    # error this number must never make. Assume nobody has left instead.
    current = inc.get("occupancy_current")
    if current is None:
        current = peak
    return {
        "present": max(0, peak - current),
        "total": peak,
        "source": "vision",
    }


def classification_json(inc: dict) -> dict | None:
    """What is burning, or why we do not know yet.

    Returns None only when nothing has been attempted. Once the dashboard has
    asked, this is always present — including the `unavailable` case, because
    "the sensors are still warming up" is information a responder can act on,
    whereas a blank field looks like a bug.
    """
    source = inc.get("fuel_source")
    if not source:
        return None
    fuel = inc.get("fuel_type")
    return {
        "fuelType": fuel,
        "confidence": inc.get("fuel_confidence"),
        "source": source,                      # model | unavailable
        # One sentence for a lock screen, the full table for a screen that has
        # room. `response` is None when there is no fuel to respond to.
        "guidance": ext.short_guidance(fuel),
        "label": ext.label_for(fuel),
        "response": ext.guidance_for(fuel),
        # Both models were trained on CFAST simulation and have never seen a
        # recorded fire. The app should show this next to the fuel type until
        # it has been validated against real recordings.
        "trainedOn": "simulation",
    }


def route_json(inc: dict) -> dict | None:
    """The generated escape route, or None.

    EMBEDDED IN THE INCIDENT RATHER THAN FETCHED SEPARATELY. The incident screen
    is the one screen that must never fail: it opens from a notification tap, on a
    phone that has just woken up, sometimes on a network having a bad minute. The
    app already fetches /api/state and /api/incidents/{id}, so putting the route
    in there costs no extra round trip and adds no new way to fail. It is about
    400 bytes.

    Geometry is deliberately NOT here. The app owns the rooms, doors and exit bars
    as const data; only the parts that change with the fire travel. `siteKey` tells
    it which drawing to pair the route with.

    None means no route: no incident, or generation failed. The app renders that as
    the plan with no overlays, which is a path it already has.
    """
    raw = inc.get("route_json")
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return None
    # Serve the wire subset, not the analysis record.
    keep = ("status", "siteKey", "planRevision", "fireZoneId", "from", "hazard",
            "polyline", "exitId", "exitName", "muster", "blockedExitIds",
            "lengthM", "originReanchored", "instruction", "generatedInMs")
    return {k: record[k] for k in keep if k in record}


def checkout_json(inc: dict, checked_out: int) -> dict:
    """Check-out and head-count, side by side, with the gap named.

    THESE ARE TWO INSTRUMENTS, NOT ONE NUMBER. The camera counts people still in
    the zone; `checkedOut` counts people who said they are out. Section 3.4.8
    asks for both reported together with every difference listed, and the
    difference is the interesting part: a positive `unaccounted` may mean the
    camera is still seeing somebody who has not tapped, or that it is seeing a
    coat on a chair. Collapsing them into one figure throws away the only signal
    that either of them might be wrong.

    `unaccounted` is None when the camera never had a number, because "we do not
    know how many were in there" must never render as "everybody is out".
    """
    peak = inc.get("occupancy_peak")
    return {
        "checkedOut": checked_out,
        "peakOccupancy": peak,
        "currentOccupancy": inc.get("occupancy_current"),
        # Peak seen by the camera, minus those who have said they are out.
        "unaccounted": None if peak is None else max(0, peak - checked_out),
        "source": "device",
    }


def delivery_stats(rows: list[dict]) -> dict:
    """Median and 95th percentile of the one-way delivery estimate.

    The 95th percentile sits beside the median because in a safety system the
    worst case matters more than the typical one.
    """
    vals = sorted(r["oneway_ms"] for r in rows if r.get("oneway_ms") is not None)

    def _pct(p):
        if not vals:
            return None
        return round(vals[min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1))))], 1)

    return {
        "devices": len(rows),
        "acknowledged": len(vals),
        "p50Ms": _pct(50),
        "p95Ms": _pct(95),
        "maxMs": round(vals[-1], 1) if vals else None,
        "method": "round-trip on the server clock, halved",
        "caveat": ("Assumes a symmetric network path and includes the app's own "
                   "handling time. Measured this way so the handset clock, which "
                   "we cannot check, does not enter the figure."),
    }


def incident_json(inc: dict, zone: dict, checked_out: int = 0) -> dict:
    return {
        "id": inc["id"],
        # 'warning' = gas rising, nothing visible, no siren (tier 1a).
        # 'gas_danger' = dangerous gas, still nothing visible, but it DOES alarm
        # (tier 1b) -- a camera cannot see carbon monoxide. 'fire' = a flame
        # confirmed on camera. Defaulted rather than nullable so an incident
        # written before this field existed still reads as a fire.
        "severity": inc.get("severity") or "fire",
        # Whether the VLM was reachable when this opened. 'unavailable' means the
        # alarm stands on detection evidence alone, so the app must NOT claim it
        # was confirmed by two AI checks. Defaulted for the same reason.
        "verification": inc.get("verification") or "confirmed",
        # The readings behind a gas warning, so the phone can show what it is
        # reacting to rather than only asserting that something is happening.
        "sensorSummary": inc.get("sensor_summary") or "",
        "zone": zone_json(zone),
        "event": event_json(inc),
        "muster": muster_json(inc),
        "occupancy": {
            "current": inc.get("occupancy_current"),
            "peak": inc.get("occupancy_peak"),
        },
        "classification": classification_json(inc),
        "route": route_json(inc),
        "checkout": checkout_json(inc, checked_out),
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
        "peakOccupancy": inc.get("occupancy_peak"),
        # What was burning, kept with the record. Until now this was lost the
        # moment the fire resolved, so nobody could afterwards answer the first
        # question an investigation asks.
        "fuelType": inc.get("fuel_type"),
        "fuelLabel": ext.label_for(inc.get("fuel_type")) if inc.get("fuel_type") else None,
        "fireClass": (ext.EXTINGUISHERS.get(inc.get("fuel_type") or "") or {}).get("fire_class"),
        # `cause` was always null. The fuel is the closest thing the system can
        # honestly say about cause, so it goes here rather than leaving the
        # field permanently empty.
        "cause": ext.label_for(inc.get("fuel_type")) if inc.get("fuel_type") else None,
        "sceneNotes": _scene_notes(inc),
    }


def _gap(a: str | None, b: str | None) -> int | None:
    """Seconds between two stamps, or None if either is missing."""
    if not a or not b:
        return None
    return max(0, round((_parse(b) - _parse(a)).total_seconds()))


def report_json(inc: dict, zone: dict, checked_out: int = 0,
                deliveries: list[dict] | None = None) -> dict:
    """The record of one incident, for reading after it is over.

    WHY THE TIMELINE IS THE POINT. A responder wants to know what burned. An
    investigation wants to know when the system knew it. Those are different
    questions, and the gaps between the stamps answer the second one: gas
    reaches a sensor 14-22s after a camera sees the flame, so `detectedAt` and
    `classifiedAt` are genuinely apart. Reporting one stamp would imply the
    system knew everything at once, which it did not.

    An escalated incident keeps BOTH stories: `createdAt` is when the gas
    warning opened, `detectedAt` is when the flame was seen. The gap is how
    much notice the sensors gave before anything was visible -- which is the
    main thing the whole escalation design is for.
    """
    severity = inc.get("severity") or "fire"
    alarmed = severity in ("fire", "gas_danger")
    escalated = alarmed and (inc.get("created_at") != inc.get("detected_at"))

    # What the alarm actually was, in the responder's words. A tier 1b alarm must
    # never be written up as "fire confirmed": nobody saw a flame, and an
    # investigation reading this record afterwards would be misled about what the
    # system knew.
    if severity == "warning":
        alarm_label = "Gas warning raised"
    elif severity == "gas_danger":
        alarm_label = "Gas reached dangerous levels" if not escalated else \
                      "Gas warning escalated to a gas alarm"
    else:
        alarm_label = "Gas warning escalated to fire" if escalated else "Fire confirmed"

    timeline = []
    if escalated:
        timeline.append({"at": inc.get("created_at"), "what": "Gas warning raised",
                         "detail": "Sensor readings above normal, nothing visible on camera."})
    timeline.append({
        "at": inc.get("detected_at"),
        "what": alarm_label,
        "detail": inc.get("description") or "",
    })
    if inc.get("classified_at"):
        timeline.append({
            "at": inc["classified_at"],
            "what": f"Fuel identified as {ext.label_for(inc.get('fuel_type')).lower()}",
            "detail": ext.short_guidance(inc.get("fuel_type")),
        })
    if inc.get("resolved_at"):
        timeline.append({"at": inc["resolved_at"], "what": "Incident closed",
                         "detail": (inc.get("resolution") or "auto_cleared").replace("_", " ")})

    return {
        "id": inc["id"],
        "severity": severity,
        "verification": inc.get("verification") or "confirmed",
        "escalatedFromWarning": escalated,
        "zone": zone_json(zone),
        "status": inc.get("status"),
        "resolution": inc.get("resolution"),
        "detection": {
            "type": inc.get("type"),
            "peakConfidence": inc.get("confidence"),
            "description": inc.get("description") or "",
        },
        "classification": classification_json(inc),
        "occupancy": {
            "peak": inc.get("occupancy_peak"),
            "atClose": inc.get("occupancy_current"),
        },
        "muster": muster_json(inc),
        "checkout": checkout_json(inc, checked_out),
        "delivery": delivery_stats(deliveries or []),
        "route": route_json(inc),
        "routeLatencyMs": inc.get("route_latency_ms"),
        "routeError": inc.get("route_error"),
        "timeline": timeline,
        "durations": {
            # How long the sensors saw it before anything was visible. The
            # value of tier 1a, in seconds.
            "warningToFireS": _gap(inc.get("created_at"), inc.get("detected_at")) if escalated else None,
            # How long after the alarm the fuel was known.
            "fireToClassifiedS": _gap(inc.get("detected_at"), inc.get("classified_at")),
            "totalS": _gap(inc.get("created_at"), inc.get("resolved_at")),
        },
        "caveats": [
            "The fuel type comes from models trained on CFAST simulation. Neither "
            "has seen a recorded fire, so the fuel is a best estimate, not a finding.",
            "Occupancy counts one camera's field of view. Anyone never in frame was "
            "never counted, and anyone who walked out of shot counts as evacuated.",
            "The head-count and the check-out count are separate measurements of the "
            "same evacuation and will not agree. Neither is corrected against the other.",
        ],
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
