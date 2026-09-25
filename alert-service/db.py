"""
SQLite persistence for alert-service (via aiosqlite).

Three tables — devices (FCM tokens), zones (the 7 detectors + live status),
incidents (active + resolved). History is *derived* from resolved incidents,
so there is no separate history table.
"""

import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite

from zones_seed import ZONES

log = logging.getLogger("alert.db")

DB_PATH = os.getenv("DB_PATH", "alert.db")

# Muster head-count is not tracked by the vision backend — we synthesize it.
DEFAULT_MUSTER_PRESENT = 42
DEFAULT_MUSTER_TOTAL = 45


def _utcnow_ms() -> str:
    """Now, to the millisecond.

    Everything else in this file stamps to the second, which is fine for an
    incident timeline nobody reads to sub-second precision. Delivery timing is
    not that: Table 3.19 reports a median and a 95th percentile in milliseconds,
    and at second granularity every fast delivery measures as exactly zero.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


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

-- Occupants who marked themselves out, one row per person per incident.
--
-- WHY THIS IS NOT THE HEAD-COUNT, AND MUST NEVER BE FOLDED INTO IT. The camera
-- counts people still in the zone; this counts people who said they are out.
-- They are different measurements of the same evacuation, taken by different
-- instruments, and Section 3.4.8 requires them reported side by side with every
-- difference listed. The difference IS the finding: it is how you discover the
-- camera missed somebody behind a rack, or that somebody tapped the button from
-- the car park without ever having been in the building.
--
-- The composite primary key is what makes the number trustworthy. A responder
-- under stress taps twice; a notification is opened twice; the app retries a
-- request it never saw the answer to. Every one of those is the same person,
-- and INSERT OR IGNORE makes it count once.
CREATE TABLE IF NOT EXISTS checkouts (
    incident_id  TEXT NOT NULL,
    device_token TEXT NOT NULL,
    at           TEXT NOT NULL,
    PRIMARY KEY (incident_id, device_token)
);

-- Push delivery timing (Table 3.19, "decision to delivery").
--
-- MEASURED AS A ROUND TRIP ON THE SERVER CLOCK, then halved. The interval ends
-- on a handset whose clock we do not control and cannot check, so a one-way
-- measurement would be reporting NTP drift alongside network latency with no way
-- to separate them. Stamping both ends here removes the handset clock from the
-- measurement entirely.
--
-- What that buys is honesty about a different thing: the halved figure assumes a
-- symmetric path and folds the app's own handling time into the estimate. That
-- is a stated assumption rather than an invisible error, which is the trade this
-- design makes on purpose.
CREATE TABLE IF NOT EXISTS deliveries (
    incident_id  TEXT NOT NULL,
    device_token TEXT NOT NULL,
    sent_at      TEXT NOT NULL,   -- when we handed it to FCM
    received_at  TEXT,            -- when the device's acknowledgement got back
    rtt_ms       REAL,            -- received_at - sent_at
    oneway_ms    REAL,            -- rtt_ms / 2, the reported figure
    state        TEXT,            -- background | foreground | opened
    PRIMARY KEY (incident_id, device_token)
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
    muster_total   INTEGER,
    occupancy_current INTEGER, -- people the camera sees in the zone right now
    occupancy_peak    INTEGER, -- most it has seen since this incident opened
    -- Escalation tier. 'warning' is gas rising with nothing visible and no
    -- siren; 'fire' is a confirmed fire. A warning UPGRADES to fire in place
    -- rather than opening a second incident, because gas reaches the sensor
    -- 14-22s after a camera sees the flame -- so the two are the same event
    -- arriving twice, not two events.
    severity       TEXT,     -- warning | gas_danger | fire
    -- WHY gas_danger IS ITS OWN SEVERITY, not a fire with confidence 0. Tier 1b
    -- is dangerous gas with nothing visible: a camera cannot see carbon
    -- monoxide, so the alarm is real but there is no flame to describe. Folding
    -- it into 'fire' is what made the phone render "Confidence 0%" next to a
    -- fire alarm -- a number that looks broken precisely when it is correct.
    -- It still alarms and still rides the fire channel; only the wording differs.

    -- Whether the vision-language model was reachable when this incident opened
    -- (Algorithm 3). 'unavailable' is NOT a rejection: a fire box plus sensors
    -- above normal confirms a fire even when the VLM cannot be reached, and the
    -- incident records that it was confirmed on detection evidence alone. The
    -- app must not claim "confirmed by 2 AI checks" on that path.
    verification   TEXT,     -- confirmed | rejected | unavailable | not_applicable
    -- The raw reading line behind a gas warning ("MQ-2 620 ppm (warn), CO 45 ppm").
    -- Stored, not just pushed: the warning screen is reachable from the zone
    -- list minutes later, and the description alone ("gas is rising") is an
    -- assertion the reader cannot check without the numbers under it.
    sensor_summary TEXT,
    -- Fuel classification, attached later by the fusion model once the sensors
    -- agree. NULL until then, and NULL is meaningful: it says "not classified",
    -- never "no fuel".
    fuel_type      TEXT,     -- gas_fire | liquid_fuel | solid_combustible
    fuel_confidence REAL,
    fuel_source    TEXT,     -- 'model' | 'unavailable', with the reason in fuel_type
    -- When the fuel was first identified. Kept separate from detected_at
    -- because the gap between them IS the finding: the sensors need 14-22s to
    -- catch up with the camera, and the incident report should show that
    -- honestly rather than implying the system knew everything at once.
    classified_at  TEXT,
    -- The generated escape route, stored rather than recomputed later.
    --
    -- WHY THE WHOLE THING IS KEPT. The route-validity analysis asks four
    -- questions afterwards: did it reach a usable exit, did it pass within the
    -- hazard radius, how much longer was it than the hand-derived best route,
    -- and did it correctly refuse when there was no way out. Re-deriving any of
    -- that later would answer them about whatever the building looks like THEN.
    -- The blocked set in particular is evidence, not a cache.
    --
    -- route_site_key and route_plan_revision are not bookkeeping either: without
    -- them nobody can tell which building, or which version of it, a stored route
    -- was computed against, and the optimality gap quietly stops meaning anything
    -- the first time a wall moves mid-trial.
    route_json          TEXT,   -- the full RouteResult record
    route_blocked_json  TEXT,   -- {edges, exits, unreachable}
    route_exit_id       TEXT,
    route_refuge        INTEGER,-- 0 | 1
    route_length_m      REAL,
    route_generation_ms REAL,   -- the algorithm alone
    route_latency_ms    REAL,   -- detected_at -> route ready; THIS is the RO2.2 number
    route_generated_at  TEXT,
    route_site_key      TEXT,
    route_plan_revision TEXT,
    route_error         TEXT,   -- why there is no route; never a silent blank
    -- The situation report (RO3.1), stored AFTER its claims were checked against
    -- the detector and sensor evidence. What is kept is the graded claim list,
    -- not the model's raw answer: the point of the record is that a reader can
    -- see which statements were confirmed, which were withheld, and why.
    situation_report TEXT
);
"""

# Columns added after the first release. The SQLite file lives in a Docker
# volume that survives `compose down`, so an existing deployment already has an
# incidents table and CREATE TABLE IF NOT EXISTS will not add them.
_ADDED_COLUMNS = (
    ("occupancy_current", "INTEGER"),
    ("occupancy_peak", "INTEGER"),
    ("severity", "TEXT"),
    ("fuel_type", "TEXT"),
    ("fuel_confidence", "REAL"),
    ("fuel_source", "TEXT"),
    ("classified_at", "TEXT"),
    ("verification", "TEXT"),
    ("sensor_summary", "TEXT"),
    ("route_json", "TEXT"),
    ("route_blocked_json", "TEXT"),
    ("route_exit_id", "TEXT"),
    ("route_refuge", "INTEGER"),
    ("route_length_m", "REAL"),
    ("route_generation_ms", "REAL"),
    ("route_latency_ms", "REAL"),
    ("route_generated_at", "TEXT"),
    ("route_site_key", "TEXT"),
    ("route_plan_revision", "TEXT"),
    ("route_error", "TEXT"),
    ("situation_report", "TEXT"),
)


async def _migrate(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(incidents)") as cur:
        existing = {r["name"] for r in await cur.fetchall()}
    for name, decl in _ADDED_COLUMNS:
        if name not in existing:
            await db.execute(f"ALTER TABLE incidents ADD COLUMN {name} {decl}")
    await db.commit()


async def connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    return db


async def init_db(db: aiosqlite.Connection) -> None:
    """Create, migrate, then RECONCILE the zone table against the active site.

    WHY RECONCILE AND NOT JUST INSERT OR IGNORE. The database lives in the
    `alert-data` volume and survives `compose down`, so switching SITE_KEY on a
    machine that has run the other site leaves that site's zones sitting in the
    table. Old incidents then point at zone ids that are no longer seeded,
    `get_zone` returns None, `zone_json(None)` raises, and /api/state answers 500.

    That failure is almost invisible from the outside: the phone's `refresh()`
    swallows the exception by design so a dead backend does not blank the screen,
    which means the app goes on showing stale data indefinitely with no error
    anywhere. Hence: update the rows that survive, delete the ones that do not.

    Updating rather than replacing keeps `status` and `last_scan_at`, so a
    restart mid-incident does not reset a burning zone to clear.
    """
    await db.executescript(_SCHEMA)
    await _migrate(db)
    now = _utcnow()
    for z in ZONES:
        await db.execute(
            """INSERT INTO zones (id, name, floor, detector_id, status, last_scan_at, glyph)
                    VALUES (?, ?, ?, ?, 'clear', ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    floor = excluded.floor,
                    detector_id = excluded.detector_id,
                    glyph = excluded.glyph""",
            (z["id"], z["name"], z["floor"], z["detector_id"], now, z["glyph"]),
        )
    keep = [z["id"] for z in ZONES]
    placeholders = ",".join("?" * len(keep))
    async with db.execute(
        f"SELECT id FROM zones WHERE id NOT IN ({placeholders})", keep
    ) as cur:
        stale = [r["id"] for r in await cur.fetchall()]
    if stale:
        log.warning("Removing %d zone(s) left by a previous site: %s",
                    len(stale), ", ".join(stale))
        await db.execute(
            f"DELETE FROM zones WHERE id NOT IN ({placeholders})", keep)
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

async def create_incident(db, incident_id, zone_id, det_type, confidence, description,
                          detected_at, occupancy=None, severity="fire",
                          verification="confirmed", sensor_summary=None) -> dict:
    now = _utcnow()
    await db.execute(
        """INSERT INTO incidents
             (id, zone_id, type, confidence, description, detected_at, status,
              created_at, resolved_at, resolution, last_event_at, muster_present, muster_total,
              occupancy_current, occupancy_peak, severity, verification, sensor_summary)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (incident_id, zone_id, det_type, confidence, description, detected_at,
         now, now, DEFAULT_MUSTER_PRESENT, DEFAULT_MUSTER_TOTAL, occupancy, occupancy,
         severity, verification, sensor_summary),
    )
    await db.commit()
    return await get_incident(db, incident_id)


async def escalate_incident(db, incident_id, det_type, confidence, description,
                            detected_at, occupancy=None, severity="fire",
                            verification="confirmed") -> dict:
    """Raise a warning to a full alarm, in place.

    The gas that opened the warning and the flame the camera now sees are the
    same fire -- the sensors were simply slower. Opening a second incident
    would show the responder two fires in one room and start a second muster.

    `severity` is a parameter rather than a hard-coded 'fire' because a warning
    can escalate two ways. A flame on camera makes it a fire; the same gas
    simply getting worse makes it tier 1b, GAS DANGER -- an alarm with nothing
    visible. Writing 'fire' for the second case would assert a flame nobody saw.
    """
    now = _utcnow()
    await db.execute(
        """UPDATE incidents
             SET severity = ?,
                 verification = ?,
                 type = ?,
                 confidence = MAX(confidence, ?),
                 description = ?,
                 detected_at = ?,
                 last_event_at = ?,
                 occupancy_current = COALESCE(?, occupancy_current),
                 occupancy_peak = CASE
                     WHEN ? IS NULL THEN occupancy_peak
                     ELSE MAX(COALESCE(occupancy_peak, 0), ?)
                 END
           WHERE id = ?""",
        (severity, verification, det_type, confidence, description, detected_at, now,
         occupancy, occupancy, occupancy, incident_id),
    )
    await db.commit()
    return await get_incident(db, incident_id)


async def set_classification(db, incident_id, fuel_type, fuel_confidence, source) -> dict:
    """Attach (or replace) the fuel verdict on an incident.

    Replaced rather than kept, because the classifier's answer improves as the
    fire develops -- the reading from 90 seconds in is better evidence than the
    one from second 31, and a responder wants the current best answer, not the
    first one.
    """
    # Stamped only on the FIRST real verdict. The dashboard asks every second
    # and the answer can sharpen as the fire grows, but "when did we first know
    # what was burning?" has one answer, and overwriting it would erase the
    # very delay the report exists to show.
    await db.execute(
        """UPDATE incidents
             SET fuel_type = ?, fuel_confidence = ?, fuel_source = ?,
                 classified_at = CASE
                     WHEN ? = 'model' AND classified_at IS NULL THEN ?
                     ELSE classified_at
                 END
           WHERE id = ?""",
        (fuel_type, fuel_confidence, source, source, _utcnow(), incident_id),
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


async def get_all_incidents(db, limit: int = 200) -> list[dict]:
    """Every incident, newest first — the analysis reads resolved and live alike."""
    async with db.execute(
        "SELECT * FROM incidents ORDER BY COALESCE(resolved_at, detected_at) DESC LIMIT ?",
        (limit,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_resolved_incidents(db, limit: int = 50) -> list[dict]:
    async with db.execute(
        "SELECT * FROM incidents WHERE status = 'resolved' ORDER BY resolved_at DESC LIMIT ?",
        (limit,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def touch_incident(db, incident_id, confidence, description, last_event_at,
                         occupancy=None) -> None:
    """Refresh an active incident on a repeat fire event (keeps the peak confidence).

    A null occupancy means the human detector had nothing to say for this frame
    (service down, or the dashboard has not counted yet) — that must leave the
    stored numbers untouched rather than resetting the zone to "empty".
    """
    await db.execute(
        """UPDATE incidents
             SET confidence = MAX(confidence, ?),
                 description = ?,
                 last_event_at = ?,
                 occupancy_current = COALESCE(?, occupancy_current),
                 occupancy_peak = CASE
                     WHEN ? IS NULL THEN occupancy_peak
                     ELSE MAX(COALESCE(occupancy_peak, 0), ?)
                 END
           WHERE id = ?""",
        (confidence, description, last_event_at, occupancy, occupancy, occupancy, incident_id),
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


async def set_incident_route(db, incident_id: str, record: dict, blocked: dict,
                             latency_ms: float | None) -> None:
    """Attach a generated route to an incident. Clears any previous route_error."""
    await db.execute(
        """UPDATE incidents
             SET route_json = ?, route_blocked_json = ?, route_exit_id = ?,
                 route_refuge = ?, route_length_m = ?, route_generation_ms = ?,
                 route_latency_ms = ?, route_generated_at = ?, route_site_key = ?,
                 route_plan_revision = ?, route_error = NULL
           WHERE id = ?""",
        (json.dumps(record), json.dumps(blocked), record.get("exitId"),
         1 if record.get("status") == "refuge" else 0, record.get("lengthM"),
         record.get("generatedInMs"), latency_ms, _utcnow(),
         record.get("siteKey"), record.get("planRevision"), incident_id),
    )
    await db.commit()


async def set_situation_report(db, incident_id: str, report: dict) -> None:
    """Store the validated situation report against an incident."""
    await db.execute(
        "UPDATE incidents SET situation_report = ? WHERE id = ?",
        (json.dumps(report), incident_id),
    )
    await db.commit()


async def set_incident_route_error(db, incident_id: str, error: str) -> None:
    """Record WHY there is no route. A blank field would read as "not tried yet",
    and the analysis would quietly drop the case from its denominator."""
    await db.execute(
        "UPDATE incidents SET route_error = ?, route_generated_at = ? WHERE id = ?",
        (error, _utcnow(), incident_id),
    )
    await db.commit()


# ── Check-out and delivery ───────────────────────────────────────────────────

async def record_checkout(db, incident_id: str, device_token: str) -> int:
    """Mark one occupant out. Idempotent; returns the incident's total."""
    await db.execute(
        "INSERT OR IGNORE INTO checkouts (incident_id, device_token, at) VALUES (?, ?, ?)",
        (incident_id, device_token, _utcnow()),
    )
    await db.commit()
    return await count_checkouts(db, incident_id)


async def count_checkouts(db, incident_id: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) AS n FROM checkouts WHERE incident_id = ?", (incident_id,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def record_push_sent(db, incident_id: str, tokens: list[str]) -> None:
    """Stamp the moment each message was handed to FCM.

    INSERT OR IGNORE, not REPLACE: an incident that is pushed twice (a warning
    escalating to a fire, a classification arriving later) keeps the FIRST send.
    The interval Table 3.19 asks for runs from the decision, and the decision
    happened at the first push.
    """
    now = _utcnow_ms()
    for t in tokens:
        await db.execute(
            "INSERT OR IGNORE INTO deliveries (incident_id, device_token, sent_at) "
            "VALUES (?, ?, ?)",
            (incident_id, t, now),
        )
    await db.commit()


async def record_delivery(db, incident_id: str, device_token: str,
                          state: str | None = None) -> dict | None:
    """Close the loop for one device. Returns the row, or None if unmatched.

    Only the FIRST acknowledgement counts (`received_at IS NULL` in the WHERE):
    a foreground alert that is later tapped would otherwise overwrite a fast
    delivery with the time the person happened to pick up the phone, which is a
    measure of human attention, not of the system.
    """
    async with db.execute(
        "SELECT * FROM deliveries WHERE incident_id = ? AND device_token = ?",
        (incident_id, device_token),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if row["received_at"] is not None:
        return dict(row)   # already closed; keep the first

    # The arithmetic is done here rather than in SQL. SQLite's julianday() would
    # have to parse our own timestamp format back, and a parse it silently
    # disagreed with would produce a plausible-looking wrong number instead of
    # an error -- which is the worst outcome for a figure that goes in a table.
    now = _utcnow_ms()
    rtt = max(0.0, (_parse_ts(now) - _parse_ts(row["sent_at"])).total_seconds() * 1000.0)
    await db.execute(
        """UPDATE deliveries
              SET received_at = ?, rtt_ms = ?, oneway_ms = ?, state = COALESCE(?, state)
            WHERE incident_id = ? AND device_token = ? AND received_at IS NULL""",
        (now, rtt, rtt / 2.0, state, incident_id, device_token),
    )
    await db.commit()
    async with db.execute(
        "SELECT * FROM deliveries WHERE incident_id = ? AND device_token = ?",
        (incident_id, device_token),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_deliveries(db, incident_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM deliveries WHERE incident_id = ? ORDER BY sent_at", (incident_id,)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_all_deliveries(db, limit: int = 500) -> list[dict]:
    async with db.execute(
        "SELECT * FROM deliveries WHERE received_at IS NOT NULL "
        "ORDER BY sent_at DESC LIMIT ?", (limit,)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def bump_muster(db, incident_id: str) -> None:
    await db.execute(
        "UPDATE incidents SET muster_present = MIN(muster_present + 1, muster_total) WHERE id = ?",
        (incident_id,),
    )
    await db.commit()
