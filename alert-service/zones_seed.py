"""
Zone catalog for the active FireWatch site.

Derived from `sites/<SITE_KEY>.json` via sites.py, so the zones, the facility
graph and the routes can never describe different buildings. SITE_KEY=home (the
trial facility) is the default; set SITE_KEY=unit7 for the demo factory.

THIS IS STILL A MIRRORED CONTRACT with the mobile app's `mock_data.dart`: the
ids, names, floors, detector ids and glyphs are what the phone renders against.
Change a zone in the site file and change it there too. A glyph the app's
ZoneGlyph enum does not know falls back to a fabric roll silently -- no crash,
no warning, and nobody notices until the demo.
"""

import os

from sites import ACTIVE

# The display name. The env var wins so a demo can relabel without editing data;
# otherwise it comes from the site file. Before this, SITE_NAME was hard-coded
# here and the compose env var it shadowed had no effect at all.
SITE_NAME = os.getenv("SITE_NAME") or ACTIVE.name

ZONES = ACTIVE.zones
ZONES_BY_ID = {z["id"]: z for z in ZONES}

# The zone a browser dashboard reports for (its webcam == this detector).
DEFAULT_ZONE_ID = ACTIVE.default_zone_id

# Dashboard system-health tiles (mirrors MockData.health). `Detectors` value is
# computed from the live zone count at runtime; the rest are static.
HEALTH_STATIC = [
    {"label": "AI pipeline", "value": "Active", "ok": True},
    {"label": "Alerts", "value": "Armed", "ok": True},
]
