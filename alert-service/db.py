"""
SQLite persistence for alert-service (via aiosqlite).

Three tables — devices (FCM tokens), zones (the 7 detectors + live status),
incidents (active + resolved). History is *derived* from resolved incidents,
so there is no separate history table.
"""

import os
from datetime import datetime, timezone

import aiosqlite

from zones_seed import ZONES

DB_PATH = os.getenv("DB_PATH", "alert.db")

# Muster head-count is not tracked by the vision backend — we synthesize it.
DEFAULT_MUSTER_PRESENT = 42
DEFAULT_MUSTER_TOTAL = 45


def _utcnow() -> str:
    """ISO-8601 UTC with a trailing Z (matches the Dart DateTime.parse format)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    token       TEXT PRIMARY KEY,
    platform    TEXT,
    label       TEXT,
    created_at  TEXT,
    last_seen   TEXT
);

CREATE TABLE IF NOT EXISTS zones (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    floor        TEXT,
    detector_id  TEXT,
    status       TEXT,      -- clear | smoke | fire
    last_scan_at TEXT,
    glyph        TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    id             TEXT PRIMARY KEY,
    zone_id        TEXT,
    type           TEXT,     -- fire | smoke | both | none
    confidence     REAL,
    description    TEXT,
    detected_at    TEXT,
    status         TEXT,     -- active | resolved
    created_at     TEXT,
    resolved_at    TEXT,
    resolution     TEXT,     -- user_confirmed | auto_cleared | false_alarm
    last_event_at  TEXT,     -- refreshed on every fire event; drives the auto-clear watchdog
    muster_present INTEGER,
    muster_total   INTEGER
);
"""


async def connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    return db


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript(_SCHEMA)
    # Seed the 7 zones if they don't already exist (preserves status across restarts).
    now = _utcnow()
    for z in ZONES:
        await db.execute(
            """INSERT OR IGNORE INTO zones (id, name, floor, detector_id, status, last_scan_at, glyph)
               VALUES (?, ?, ?, ?, 'clear', ?, ?)""",
            (z["id"], z["name"], z["floor"], z["detector_id"], now, z["glyph"]),
        )
    await db.commit()


# ── Devices ──────────────────────────────────────────────────────────────────

async def upsert_device(db, token: str, platform: str | None, label: str | None) -> None:
    now = _utcnow()
    await db.execute(
        """INSERT INTO devices (token, platform, label, created_at, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(token) DO UPDATE SET
             platform=excluded.platform, label=excluded.label, last_seen=excluded.last_seen""",
        (token, platform, label, now, now),
    )
    await db.commit()


async def list_tokens(db) -> list[str]:
    async with db.execute("SELECT token FROM devices") as cur:
        return [r["token"] for r in await cur.fetchall()]


async def delete_tokens(db, tokens: list[str]) -> None:
    if not tokens:
        return
    await db.executemany("DELETE FROM devices WHERE token = ?", [(t,) for t in tokens])
    await db.commit()


# ── Zones ────────────────────────────────────────────────────────────────────

async def get_zones(db) -> list[dict]:
    async with db.execute("SELECT * FROM zones ORDER BY detector_id") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_zone(db, zone_id: str) -> dict | None:
    async with db.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)) as cur:
        r = await cur.fetchone()
        return dict(r) if r else None


async def set_zone_status(db, zone_id: str, status: str, last_scan_at: str | None = None) -> None:
    await db.execute(
        "UPDATE zones SET status = ?, last_scan_at = ? WHERE id = ?",
        (status, last_scan_at or _utcnow(), zone_id),
    )
    await db.commit()


# ── Incidents ────────────────────────────────────────────────────────────────

async def create_incident(db, incident_id, zone_id, det_type, confidence, description, detected_at) -> dict:
    now = _utcnow()
    await db.execute(
        """INSERT INTO incidents
             (id, zone_id, type, confidence, description, detected_at, status,
              created_at, resolved_at, resolution, last_event_at, muster_present, muster_total)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?, ?)""",
        (incident_id, zone_id, det_type, confidence, description, detected_at,
         now, now, DEFAULT_MUSTER_PRESENT, DEFAULT_MUSTER_TOTAL),
    )
    await db.commit()
    return await get_incident(db, incident_id)


async def get_incident(db, incident_id: str) -> dict | None:
    async with db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)) as cur:
        r = await cur.fetchone()
        return dict(r) if r else None


async def get_active_incident_for_zone(db, zone_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM incidents WHERE zone_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (zone_id,),
    ) as cur:
        r = await cur.fetchone()
        return dict(r) if r else None


async def get_latest_active_incident(db) -> dict | None:
    async with db.execute(
        "SELECT * FROM incidents WHERE status = 'active' ORDER BY last_event_at DESC LIMIT 1"
    ) as cur:
        r = await cur.fetchone()
        return dict(r) if r else None


async def get_active_incidents(db) -> list[dict]:
    async with db.execute("SELECT * FROM incidents WHERE status = 'active'") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_last_resolved_for_zone(db, zone_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM incidents WHERE zone_id = ? AND status = 'resolved' ORDER BY resolved_at DESC LIMIT 1",
        (zone_id,),
    ) as cur:
        r = await cur.fetchone()
        return dict(r) if r else None


async def get_resolved_incidents(db, limit: int = 50) -> list[dict]:
    async with db.execute(
        "SELECT * FROM incidents WHERE status = 'resolved' ORDER BY resolved_at DESC LIMIT ?",
        (limit,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def touch_incident(db, incident_id, confidence, description, last_event_at) -> None:
    """Refresh an active incident on a repeat fire event (keeps the peak confidence)."""
    await db.execute(
        """UPDATE incidents
             SET confidence = MAX(confidence, ?), description = ?, last_event_at = ?
           WHERE id = ?""",
        (confidence, description, last_event_at, incident_id),
    )
    await db.commit()


async def mark_incident_idle(db, incident_id: str) -> None:
    """Push last_event_at into the past so the watchdog resolves this incident on its next tick."""
    await db.execute(
        "UPDATE incidents SET last_event_at = '1970-01-01T00:00:00Z' WHERE id = ?",
        (incident_id,),
    )
    await db.commit()


async def resolve_incident(db, incident_id: str, resolution: str) -> None:
    await db.execute(
        "UPDATE incidents SET status = 'resolved', resolved_at = ?, resolution = ? WHERE id = ?",
        (_utcnow(), resolution, incident_id),
    )
    await db.commit()


async def bump_muster(db, incident_id: str) -> None:
    await db.execute(
        "UPDATE incidents SET muster_present = MIN(muster_present + 1, muster_total) WHERE id = ?",
        (incident_id,),
    )
    await db.commit()
