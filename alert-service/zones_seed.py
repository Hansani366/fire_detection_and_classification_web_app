"""
Zone catalog for the FireWatch site.

This MUST mirror `firewatch/lib/data/mock/mock_data.dart` exactly — the ids,
names, floors, detector ids and glyphs are the contract the mobile app renders
against. If you change a zone here, change it there too.
"""

SITE_NAME = "Unit 7"

# Each zone: id, name, floor, detector_id, glyph (Dart ZoneGlyph.name).
ZONES = [
    {"id": "fabric-store",  "name": "Fabric Store",   "floor": "Main floor", "detector_id": "Detector 01", "glyph": "fabricRoll"},
    {"id": "cutting-floor", "name": "Cutting Floor",  "floor": "Main floor", "detector_id": "Detector 02", "glyph": "scissors"},
    {"id": "dyeing",        "name": "Dyeing Section", "floor": "Main floor", "detector_id": "Detector 03", "glyph": "dyeing"},
    {"id": "sewing-a",      "name": "Sewing Line A",  "floor": "Main floor", "detector_id": "Detector 04", "glyph": "iron"},
    {"id": "warehouse",     "name": "Warehouse",      "floor": "Main floor", "detector_id": "Detector 05", "glyph": "warehouse"},
    {"id": "boiler",        "name": "Boiler Room",    "floor": "Main floor", "detector_id": "Detector 06", "glyph": "boiler"},
    {"id": "finishing",     "name": "Finishing",      "floor": "Main floor", "detector_id": "Detector 07", "glyph": "finishing"},
]

ZONES_BY_ID = {z["id"]: z for z in ZONES}

# The zone a browser dashboard reports for (its webcam == this detector).
DEFAULT_ZONE_ID = "fabric-store"

# Dashboard system-health tiles (mirrors MockData.health). `Detectors` value is
# computed from the live zone count at runtime; the rest are static.
HEALTH_STATIC = [
    {"label": "AI pipeline", "value": "Active", "ok": True},
    {"label": "Alerts", "value": "Armed", "ok": True},
]
