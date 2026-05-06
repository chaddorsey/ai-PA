"""SQLite index of curated highlights.

Schema is simple — one row per highlight (= one Frigate event we copied).
Lives at $HIGHLIGHTS_DIR/index.db, alongside the clip files. Co-located so
backups capture both clips and metadata in one filesystem snapshot.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


# Base schema: original columns only. New columns are added via the
# _MIGRATIONS list below so existing DBs upgrade in place.
_SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS highlights (
    event_id        TEXT PRIMARY KEY,
    camera          TEXT NOT NULL,
    label           TEXT NOT NULL,
    start_time      REAL NOT NULL,
    end_time        REAL,
    duration_s      REAL,
    score           REAL NOT NULL,
    fox_likelihood  REAL NOT NULL,
    clip_path       TEXT NOT NULL,
    thumb_path      TEXT,
    promoted        INTEGER NOT NULL DEFAULT 0,
    promoted_at     REAL,
    created_at      REAL NOT NULL DEFAULT (strftime('%s','now')),
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS highlights_camera_start ON highlights (camera, start_time DESC);
CREATE INDEX IF NOT EXISTS highlights_likelihood   ON highlights (fox_likelihood DESC, start_time DESC);
CREATE INDEX IF NOT EXISTS highlights_promoted     ON highlights (promoted, start_time DESC);
"""

# Migrations run after the base schema. Each ALTER is wrapped in
# try/except (duplicate-column = benign). New indexes are created last,
# after the columns they reference exist.
_MIGRATIONS = [
    "ALTER TABLE highlights ADD COLUMN favorited INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE highlights ADD COLUMN demoted INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE highlights ADD COLUMN last_action_by TEXT",
    "ALTER TABLE highlights ADD COLUMN last_action_at REAL",
    "ALTER TABLE highlights ADD COLUMN notified_at REAL",
    "ALTER TABLE highlights ADD COLUMN species TEXT",
    "ALTER TABLE highlights ADD COLUMN species_confidence TEXT",
    "ALTER TABLE highlights ADD COLUMN classifier_model TEXT",
    "ALTER TABLE highlights ADD COLUMN classifier_at REAL",
    "ALTER TABLE highlights ADD COLUMN classifier_raw TEXT",
    "CREATE INDEX IF NOT EXISTS highlights_favorited ON highlights (favorited, start_time DESC)",
    "CREATE INDEX IF NOT EXISTS highlights_demoted   ON highlights (demoted, start_time DESC)",
    "CREATE INDEX IF NOT EXISTS highlights_species   ON highlights (species, start_time DESC)",
    """CREATE TABLE IF NOT EXISTS viewer_state (
        email          TEXT PRIMARY KEY,
        last_seen_at   REAL NOT NULL,
        updated_at     REAL NOT NULL DEFAULT (strftime('%s','now'))
    )""",
    "ALTER TABLE highlights ADD COLUMN source TEXT NOT NULL DEFAULT 'frigate'",
    "CREATE INDEX IF NOT EXISTS highlights_source ON highlights (source, start_time DESC)",
    # Per-user favorites/demotes — replaces the single-bucket model.
    # The legacy highlights.favorited / .demoted columns stay as
    # *aggregate* state ("anyone favorited this") so existing UI
    # rendering doesn't break; per-user state lives here.
    """CREATE TABLE IF NOT EXISTS highlight_user_actions (
        highlight_id   TEXT NOT NULL,
        email          TEXT NOT NULL,
        action         TEXT NOT NULL,
        set_at         REAL NOT NULL,
        PRIMARY KEY (highlight_id, email, action)
    )""",
    "CREATE INDEX IF NOT EXISTS hua_email ON highlight_user_actions (email, action, set_at DESC)",
    "CREATE INDEX IF NOT EXISTS hua_highlight ON highlight_user_actions (highlight_id, action)",
    # Backfill existing favorited rows into the new per-user table,
    # keyed on last_action_by. Idempotent via INSERT OR IGNORE on PK.
    """INSERT OR IGNORE INTO highlight_user_actions (highlight_id, email, action, set_at)
       SELECT event_id, last_action_by, 'favorite', COALESCE(last_action_at, created_at)
       FROM highlights
       WHERE favorited = 1 AND last_action_by IS NOT NULL""",
    """INSERT OR IGNORE INTO highlight_user_actions (highlight_id, email, action, set_at)
       SELECT event_id, last_action_by, 'demote', COALESCE(last_action_at, created_at)
       FROM highlights
       WHERE demoted = 1 AND last_action_by IS NOT NULL""",
    # Remixes — user-defined sub-clips with optional zoom region.
    """CREATE TABLE IF NOT EXISTS remixes (
        remix_id        TEXT PRIMARY KEY,
        event_id        TEXT NOT NULL,
        created_by      TEXT,
        created_at      REAL NOT NULL DEFAULT (strftime('%s','now')),
        title           TEXT,
        start_offset_s  REAL NOT NULL,
        end_offset_s    REAL NOT NULL,
        zoom_x          REAL,
        zoom_y          REAL,
        zoom_scale      REAL NOT NULL DEFAULT 1.0,
        notes           TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS remixes_event ON remixes (event_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS remixes_creator ON remixes (created_by, created_at DESC)",
    # Landing-page featured highlights — admin-curated subset of clips
    # shown to anonymous visitors at /. featured=1 means "show on
    # landing"; featured_caption is an optional short admin-written
    # blurb shown under the card.
    "ALTER TABLE highlights ADD COLUMN featured INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE highlights ADD COLUMN featured_at REAL",
    "ALTER TABLE highlights ADD COLUMN featured_by TEXT",
    "ALTER TABLE highlights ADD COLUMN featured_caption TEXT",
    "CREATE INDEX IF NOT EXISTS highlights_featured ON highlights (featured, featured_at DESC)",
    # Per-user likes on remixes. PK enforces idempotency: a user can
    # only like a remix once. Aggregate count is computed on demand
    # (low row counts for now — premature to denormalize).
    """CREATE TABLE IF NOT EXISTS remix_likes (
        remix_id    TEXT NOT NULL,
        email       TEXT NOT NULL,
        created_at  REAL NOT NULL DEFAULT (strftime('%s','now')),
        PRIMARY KEY (remix_id, email)
    )""",
    "CREATE INDEX IF NOT EXISTS remix_likes_email ON remix_likes (email, created_at DESC)",
    # In-app notifications. payload is JSON-serialized — kind-specific
    # fields live there so adding new notification types doesn't
    # require a migration. read_at NULL = unread.
    """CREATE TABLE IF NOT EXISTS notifications (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_email  TEXT NOT NULL,
        kind             TEXT NOT NULL,
        payload          TEXT NOT NULL,
        created_at       REAL NOT NULL DEFAULT (strftime('%s','now')),
        read_at          REAL
    )""",
    "CREATE INDEX IF NOT EXISTS notif_recipient ON notifications (recipient_email, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS notif_unread ON notifications (recipient_email, read_at, created_at DESC)",
    # Web Push subscriptions — one row per (user, device). Endpoint is
    # the unique identifier the browser hands us; p256dh + auth are the
    # crypto parameters needed to encrypt the push body. user_agent is
    # captured at subscribe time so the settings panel can show the user
    # which devices they've enabled.
    """CREATE TABLE IF NOT EXISTS push_subscriptions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT NOT NULL,
        endpoint    TEXT NOT NULL UNIQUE,
        p256dh      TEXT NOT NULL,
        auth        TEXT NOT NULL,
        user_agent  TEXT,
        created_at  REAL NOT NULL DEFAULT (strftime('%s','now')),
        last_seen_at REAL
    )""",
    "CREATE INDEX IF NOT EXISTS push_sub_email ON push_subscriptions (email)",
    # Per-user notification kind preferences. (email, kind) is the
    # natural primary key. Defaults are applied in code (push_pref_get_all)
    # so adding a new kind doesn't require a migration.
    """CREATE TABLE IF NOT EXISTS push_preferences (
        email       TEXT NOT NULL,
        kind        TEXT NOT NULL,
        enabled     INTEGER NOT NULL,
        updated_at  REAL NOT NULL DEFAULT (strftime('%s','now')),
        PRIMARY KEY (email, kind)
    )""",
    # Optional extra value for prefs that need more than a boolean
    # (e.g. new_highlight severity threshold). NULL when unused.
    "ALTER TABLE push_preferences ADD COLUMN value TEXT",
    # Pause-all-notifications-until — single row per user. A NULL or
    # past timestamp means not paused.
    """CREATE TABLE IF NOT EXISTS push_pause (
        email         TEXT PRIMARY KEY,
        paused_until  REAL,
        updated_at    REAL NOT NULL DEFAULT (strftime('%s','now'))
    )""",
    # Recurring quiet hours — minute-of-day windows in the user's local
    # time. start_min/end_min are 0–1439. If start_min > end_min the
    # window crosses midnight (e.g. 22:00 → 07:00).
    """CREATE TABLE IF NOT EXISTS push_schedule_intervals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT NOT NULL,
        start_min   INTEGER NOT NULL,
        end_min     INTEGER NOT NULL,
        tz_offset_min INTEGER NOT NULL DEFAULT 0,
        created_at  REAL NOT NULL DEFAULT (strftime('%s','now'))
    )""",
    "CREATE INDEX IF NOT EXISTS push_schedule_email ON push_schedule_intervals (email)",
]


# Notification kinds the system can emit. Defaults govern behavior when
# the user has never explicitly toggled the kind. Kept here (not in the
# DB) so adding a new kind doesn't require a migration. UI surfaces the
# settings panel from this list.
PUSH_KIND_DEFAULTS: dict[str, dict[str, Any]] = {
    "remix_like":    {"enabled": True,  "label": "Likes on my remixes",
                       "desc": "Push when someone likes a remix you created."},
    "new_highlight": {"enabled": True,  "label": "New sightings",
                       "desc": "Notify me of fox or wildlife activity",
                       # Value gates the severity filter applied by
                       # web_push.broadcast_kind. UI surfaces these as
                       # radio buttons inside the New sightings panel.
                       "default_value": "all",
                       "options": [
                           {"value": "all",
                            "label": "All suspected sightings"},
                           {"value": "clusters",
                            "label": "More than one sighting within a short period"},
                           {"value": "high",
                            "label": "High activity / extended sightings only"},
                       ]},
}


# ---------------------------------------------------------------------------
# Per-user favorite/demote helpers
# ---------------------------------------------------------------------------

def user_action_set(db_path: Path, event_id: str, email: str, action: str) -> None:
    """Record that `email` performed `action` on `event_id`.
    action ∈ {'favorite', 'demote', 'archive'}. 'archive' is independent
    of favorite/demote (a clip can be both archived AND favorited);
    favorite + demote remain mutually exclusive per user."""
    import time as _time
    if action not in ("favorite", "demote", "archive"):
        raise ValueError(f"unknown action: {action!r}")
    now = _time.time()
    with connect(db_path) as conn:
        if action in ("favorite", "demote"):
            other = "demote" if action == "favorite" else "favorite"
            conn.execute(
                "DELETE FROM highlight_user_actions WHERE highlight_id = ? AND email = ? AND action = ?",
                [event_id, email, other],
            )
        conn.execute(
            "INSERT OR REPLACE INTO highlight_user_actions (highlight_id, email, action, set_at) "
            "VALUES (?, ?, ?, ?)",
            [event_id, email, action, now],
        )
        _refresh_aggregate(conn, event_id, email, now)


def user_action_clear_one(db_path: Path, event_id: str, email: str, action: str) -> None:
    """Clear a SPECIFIC action (e.g. unarchive) without touching others."""
    import time as _time
    now = _time.time()
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM highlight_user_actions WHERE highlight_id = ? AND email = ? AND action = ?",
            [event_id, email, action],
        )
        _refresh_aggregate(conn, event_id, email, now)


def user_action_clear(db_path: Path, event_id: str, email: str) -> None:
    """Remove any favorite/demote actions for this user on this highlight."""
    import time as _time
    now = _time.time()
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM highlight_user_actions WHERE highlight_id = ? AND email = ?",
            [event_id, email],
        )
        _refresh_aggregate(conn, event_id, email, now)


def _refresh_aggregate(conn: sqlite3.Connection, event_id: str,
                        email: str | None, ts: float) -> None:
    """Recompute legacy favorited/demoted columns from per-user table."""
    fav = conn.execute(
        "SELECT COUNT(*) AS n FROM highlight_user_actions WHERE highlight_id = ? AND action = 'favorite'",
        [event_id],
    ).fetchone()["n"]
    dem = conn.execute(
        "SELECT COUNT(*) AS n FROM highlight_user_actions WHERE highlight_id = ? AND action = 'demote'",
        [event_id],
    ).fetchone()["n"]
    conn.execute(
        "UPDATE highlights SET favorited = ?, demoted = ?, "
        "last_action_by = ?, last_action_at = ? WHERE event_id = ?",
        [1 if fav > 0 else 0, 1 if dem > 0 else 0, email, ts, event_id],
    )


def get_user_state(db_path: Path, event_id: str, email: str) -> dict[str, Any]:
    """Return {my_favorited, my_demoted, voters: [...]} for one highlight."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT email, action FROM highlight_user_actions WHERE highlight_id = ?",
            [event_id],
        ).fetchall()
    voters = [r["email"] for r in rows if r["action"] == "favorite"]
    demoters = [r["email"] for r in rows if r["action"] == "demote"]
    archivers = [r["email"] for r in rows if r["action"] == "archive"]
    return {
        "my_favorited": email in voters,
        "my_demoted": email in demoters,
        "my_archived": email in archivers,
        "voters": voters,
        "demoters": demoters,
        "archivers": archivers,
        "favorite_count": len(voters),
        "demote_count": len(demoters),
    }


def list_user_actions_bulk(db_path: Path, event_ids: list[str]) -> dict[str, dict]:
    """For a list of event_ids, return {event_id: {favorites: [emails],
    demotes: [emails]}}. Used by list endpoint to attach per-card vote data."""
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT highlight_id, email, action FROM highlight_user_actions "
            f"WHERE highlight_id IN ({placeholders})",
            event_ids,
        ).fetchall()
    out: dict[str, dict] = {eid: {"favorites": [], "demotes": [], "archives": []} for eid in event_ids}
    bucket_for = {"favorite": "favorites", "demote": "demotes", "archive": "archives"}
    for r in rows:
        b = bucket_for.get(r["action"])
        if b: out[r["highlight_id"]][b].append(r["email"])
    return out


def list_my_favorites(db_path: Path, email: str, *, limit: int = 100,
                      offset: int = 0) -> list[str]:
    """event_ids the user has favorited, newest favoriting first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT highlight_id FROM highlight_user_actions "
            "WHERE email = ? AND action = 'favorite' "
            "ORDER BY set_at DESC LIMIT ? OFFSET ?",
            [email, limit, offset],
        ).fetchall()
    return [r["highlight_id"] for r in rows]


def list_shared_favorites(db_path: Path, *, min_voters: int = 2,
                           limit: int = 100, offset: int = 0) -> list[tuple[str, int]]:
    """Highlights favorited by at least min_voters distinct emails.
    Returns [(event_id, count), ...] sorted by count desc, then start_time desc."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT hua.highlight_id, COUNT(DISTINCT hua.email) AS n "
            "FROM highlight_user_actions hua "
            "JOIN highlights h ON h.event_id = hua.highlight_id "
            "WHERE hua.action = 'favorite' "
            "GROUP BY hua.highlight_id "
            "HAVING n >= ? "
            "ORDER BY n DESC, h.start_time DESC "
            "LIMIT ? OFFSET ?",
            [min_voters, limit, offset],
        ).fetchall()
    return [(r["highlight_id"], r["n"]) for r in rows]


# ---------------------------------------------------------------------------
# Remix helpers
# ---------------------------------------------------------------------------

def remix_create(db_path: Path, *, event_id: str, created_by: str | None,
                 title: str | None, start_offset_s: float, end_offset_s: float,
                 zoom_x: float | None, zoom_y: float | None,
                 zoom_scale: float, notes: str | None) -> str:
    import secrets
    remix_id = secrets.token_urlsafe(8)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO remixes (remix_id, event_id, created_by, title, "
            "start_offset_s, end_offset_s, zoom_x, zoom_y, zoom_scale, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [remix_id, event_id, created_by, title, start_offset_s, end_offset_s,
             zoom_x, zoom_y, zoom_scale, notes],
        )
    return remix_id


def remix_get(db_path: Path, remix_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM remixes WHERE remix_id = ?", [remix_id]
        ).fetchone()
    return dict(row) if row else None


def remix_list_for_event(db_path: Path, event_id: str) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM remixes WHERE event_id = ? ORDER BY created_at DESC",
            [event_id],
        ).fetchall()
    return [dict(r) for r in rows]


def remix_list_for_user(db_path: Path, email: str, *, limit: int = 100,
                        offset: int = 0) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM remixes WHERE created_by = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [email, limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def remix_counts_bulk(db_path: Path, event_ids: list[str]) -> dict[str, int]:
    """Return {event_id: remix_count} for the given highlights. Used by
    the list endpoint to attach a 'N remixes' marker per card."""
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT event_id, COUNT(*) AS n FROM remixes "
            f"WHERE event_id IN ({placeholders}) GROUP BY event_id",
            event_ids,
        ).fetchall()
    out = {eid: 0 for eid in event_ids}
    for r in rows:
        out[r["event_id"]] = r["n"]
    return out


def remix_list_recent(db_path: Path, *, limit: int = 100, offset: int = 0,
                       embed_parent: bool = True) -> list[dict[str, Any]]:
    """All remixes newest-first, optionally enriched with parent
    highlight metadata so list views can render rich cards without an
    N+1 fetch (camera / start_time / thumb_path / species)."""
    if not embed_parent:
        with connect(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM remixes ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [limit, offset],
            ).fetchall()
        return [dict(r) for r in rows]
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT r.*, "
            "h.camera AS parent_camera, h.start_time AS parent_start_time, "
            "h.species AS parent_species, h.thumb_path AS parent_thumb_path "
            "FROM remixes r LEFT JOIN highlights h ON h.event_id = r.event_id "
            "ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def remix_update(db_path: Path, remix_id: str, *,
                  title: str | None = None,
                  start_offset_s: float | None = None,
                  end_offset_s: float | None = None,
                  zoom_x: float | None = None,
                  zoom_y: float | None = None,
                  zoom_scale: float | None = None,
                  notes: str | None = None) -> bool:
    fields, args = [], []
    for k, v in [("title", title), ("start_offset_s", start_offset_s),
                  ("end_offset_s", end_offset_s), ("zoom_x", zoom_x),
                  ("zoom_y", zoom_y), ("zoom_scale", zoom_scale),
                  ("notes", notes)]:
        if v is not None:
            fields.append(f"{k} = ?"); args.append(v)
    if not fields:
        return False
    args.append(remix_id)
    with connect(db_path) as conn:
        cur = conn.execute(
            f"UPDATE remixes SET {', '.join(fields)} WHERE remix_id = ?", args
        )
        return cur.rowcount > 0


def remix_delete(db_path: Path, remix_id: str, *, only_creator: str | None = None) -> bool:
    """Delete a remix. If only_creator is provided, only delete if
    created_by matches (otherwise no-op, returns False)."""
    with connect(db_path) as conn:
        if only_creator:
            cur = conn.execute(
                "DELETE FROM remixes WHERE remix_id = ? AND created_by = ?",
                [remix_id, only_creator],
            )
        else:
            cur = conn.execute(
                "DELETE FROM remixes WHERE remix_id = ?", [remix_id]
            )
        return cur.rowcount > 0


def get_viewer_state(db_path: Path, email: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT email, last_seen_at, updated_at FROM viewer_state WHERE email = ?",
            [email],
        ).fetchone()
    return dict(row) if row else None


def update_viewer_state(db_path: Path, email: str, last_seen_at: float) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO viewer_state (email, last_seen_at, updated_at) "
            "VALUES (?, ?, strftime('%s','now')) "
            "ON CONFLICT(email) DO UPDATE SET "
            "  last_seen_at = excluded.last_seen_at, "
            "  updated_at = strftime('%s','now')",
            [email, last_seen_at],
        )


def count_new_since(db_path: Path, since: float, *,
                    only_wildlife: bool = True) -> int:
    """How many highlights have arrived since the given timestamp.

    Defaults to wildlife-only (excludes person/vehicle/none) since those
    are the events that should produce a "new highlights" badge."""
    sql = "SELECT COUNT(*) AS n FROM highlights WHERE start_time > ? AND demoted = 0"
    args: list[Any] = [since]
    if only_wildlife:
        sql += " AND (species IS NULL OR species NOT IN ('none','person','vehicle','error'))"
    with connect(db_path) as conn:
        return conn.execute(sql, args).fetchone()["n"]


def update_classification(
    db_path: Path, event_id: str,
    species: str, confidence: str,
    model: str, at: float, raw: str,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE highlights SET species = ?, species_confidence = ?, "
            "classifier_model = ?, classifier_at = ?, classifier_raw = ? "
            "WHERE event_id = ?",
            [species, confidence, model, at, raw, event_id],
        )


def mark_notified(db_path: Path, event_id: str, ts: float) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE highlights SET notified_at = ? WHERE event_id = ?",
            [ts, event_id],
        )


def init(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA_BASE)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def upsert_highlight(db_path: Path, row: dict[str, Any]) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    sets = ",".join(f"{c}=excluded.{c}" for c in cols if c != "event_id")
    sql = (
        f"INSERT INTO highlights ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(event_id) DO UPDATE SET {sets}"
    )
    with connect(db_path) as conn:
        conn.execute(sql, [row[c] for c in cols])


def list_highlights(
    db_path: Path,
    camera: str | None = None,
    since: float | None = None,
    until: float | None = None,
    min_score: float = 0.0,
    bucket: str | None = None,  # "all" | "favorites" | "demoted" | "pending"
    hour_from: int | None = None,
    hour_to: int | None = None,
    limit: int = 100,
    offset: int = 0,
    merge_overlaps: bool = True,
    email: str | None = None,
) -> list[dict[str, Any]]:
    """List highlights with optional same-camera overlap dedup.

    With merge_overlaps=True (default), events that overlap in time on
    the same camera collapse to the longest one. MegaDetector tracks
    each animal as its own object, so a mom-and-kits visit produces
    N parallel events; the longest covers the full visit and is the
    canonical card. Shorter overlapping siblings are hidden from the
    listing but still exist in the DB for direct lookup.
    """
    sql = "SELECT * FROM highlights WHERE fox_likelihood >= ?"
    args: list[Any] = [min_score]
    if merge_overlaps:
        # Hide events that have a strictly longer overlapping event on
        # the same camera. Equality of duration is broken alphabetically
        # by event_id (deterministic, picks one canonical winner).
        # EXCEPTION: a user's own favorite always shows. The merge
        # picks one canonical event per visit, but if the user has
        # specifically faved a SHORTER overlapping sibling, that's
        # their explicit choice — don't hide it.
        merge_clause = """
            SELECT 1 FROM highlights h2
            WHERE h2.camera = highlights.camera
              AND h2.event_id != highlights.event_id
              AND h2.start_time < COALESCE(highlights.end_time,
                                            highlights.start_time + COALESCE(highlights.duration_s, 0))
              AND COALESCE(h2.end_time,
                           h2.start_time + COALESCE(h2.duration_s, 0)) > highlights.start_time
              AND (
                (COALESCE(h2.end_time, h2.start_time + COALESCE(h2.duration_s, 0)) - h2.start_time)
                  > (COALESCE(highlights.end_time, highlights.start_time + COALESCE(highlights.duration_s, 0)) - highlights.start_time)
                OR (
                  (COALESCE(h2.end_time, h2.start_time + COALESCE(h2.duration_s, 0)) - h2.start_time)
                    = (COALESCE(highlights.end_time, highlights.start_time + COALESCE(highlights.duration_s, 0)) - highlights.start_time)
                  AND h2.event_id < highlights.event_id
                )
              )
        """
        if email:
            sql += (
                " AND (EXISTS ("
                "   SELECT 1 FROM highlight_user_actions a "
                "   WHERE a.highlight_id = highlights.event_id "
                "     AND a.email = ? AND a.action = 'favorite')"
                " OR NOT EXISTS (" + merge_clause + "))"
            )
            args.append(email)
        else:
            sql += " AND NOT EXISTS (" + merge_clause + ")"
    if camera:
        sql += " AND camera = ?"
        args.append(camera)
    if since is not None:
        sql += " AND start_time >= ?"
        args.append(since)
    if until is not None:
        sql += " AND start_time <= ?"
        args.append(until)

    # Bucket filter — what set of highlights are we showing?
    if bucket == "favorites":
        sql += " AND favorited = 1"
    elif bucket == "demoted":
        sql += " AND demoted = 1"
    elif bucket == "pending" or bucket is None:
        # Hide demoted from the main view UNLESS the current viewer
        # has personally favorited the clip — a user's own favorite
        # rescues a globally-demoted clip back into their All view.
        # Without this, faving a clip another family member already
        # demoted made the card silently disappear from All.
        if email:
            sql += (
                " AND (demoted = 0 OR EXISTS ("
                "   SELECT 1 FROM highlight_user_actions a "
                "   WHERE a.highlight_id = highlights.event_id "
                "     AND a.email = ? AND a.action = 'favorite'))"
            )
            args.append(email)
        else:
            sql += " AND demoted = 0"
    # bucket == "all" → no extra filter

    # Time-of-day filter (uses local-time hour of start_time).
    # SQLite's strftime returns string '00'-'23'; cast to int.
    if hour_from is not None and hour_to is not None:
        hour_expr = "CAST(strftime('%H', start_time, 'unixepoch', 'localtime') AS INTEGER)"
        if hour_from <= hour_to:
            sql += f" AND {hour_expr} >= ? AND {hour_expr} < ?"
            args.extend([hour_from, hour_to])
        else:
            # Wraps midnight (e.g., 18→6 = night)
            sql += f" AND ({hour_expr} >= ? OR {hour_expr} < ?)"
            args.extend([hour_from, hour_to])

    sql += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def set_featured(
    db_path: Path,
    event_id: str,
    *,
    featured: bool,
    by: str | None = None,
    caption: str | None = None,
) -> dict[str, Any] | None:
    """Promote (featured=True) or unpromote (featured=False) a highlight
    for the public landing page. When unpromoting, clears featured_at /
    featured_by / featured_caption.
    """
    now = time.time()
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM highlights WHERE event_id = ?", [event_id]).fetchone()
        if not row:
            return None
        if featured:
            conn.execute(
                "UPDATE highlights SET featured = 1, featured_at = ?, featured_by = ?, "
                "featured_caption = ? WHERE event_id = ?",
                [now, by, caption, event_id],
            )
        else:
            conn.execute(
                "UPDATE highlights SET featured = 0, featured_at = NULL, featured_by = NULL, "
                "featured_caption = NULL WHERE event_id = ?",
                [event_id],
            )
        out = conn.execute("SELECT * FROM highlights WHERE event_id = ?", [event_id]).fetchone()
    return dict(out) if out else None


def list_featured(db_path: Path, *, limit: int = 6) -> list[dict[str, Any]]:
    """Featured highlights for the public landing page, newest first.

    Default cap of 6 matches the landing-page design (3×2 grid).
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM highlights WHERE featured = 1 "
            "ORDER BY featured_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [dict(r) for r in rows]


def set_action(db_path: Path, event_id: str, action: str, by: str | None) -> dict[str, Any] | None:
    """Apply a family-vote action to a highlight.

    action ∈ {"favorite", "demote", "clear"}
        favorite → favorited=1, demoted=0
        demote   → demoted=1, favorited=0
        clear    → favorited=0, demoted=0

    Records who acted and when. Returns the updated row, or None if not found.
    """
    import time as _time
    if action == "favorite":
        fav, dem = 1, 0
    elif action == "demote":
        fav, dem = 0, 1
    elif action == "clear":
        fav, dem = 0, 0
    else:
        raise ValueError(f"unknown action: {action!r}")
    now = _time.time()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE highlights SET favorited = ?, demoted = ?, "
            "last_action_by = ?, last_action_at = ? WHERE event_id = ?",
            [fav, dem, by, now, event_id],
        )
        if cur.rowcount == 0:
            return None
    return get_highlight(db_path, event_id)


def get_highlight(db_path: Path, event_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM highlights WHERE event_id = ?", [event_id]
        ).fetchone()
    return dict(row) if row else None


def mark_promoted(db_path: Path, event_id: str, ts: float) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE highlights SET promoted = 1, promoted_at = ? WHERE event_id = ?",
            [ts, event_id],
        )


def stats(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM highlights").fetchone()["n"]
        by_camera = [
            dict(r)
            for r in conn.execute(
                "SELECT camera, COUNT(*) AS n FROM highlights GROUP BY camera"
            ).fetchall()
        ]
        by_score = [
            dict(r)
            for r in conn.execute(
                "SELECT "
                "  CAST(fox_likelihood * 4 AS INTEGER) / 4.0 AS bucket, "
                "  COUNT(*) AS n "
                "FROM highlights GROUP BY bucket ORDER BY bucket"
            ).fetchall()
        ]
        promoted = conn.execute(
            "SELECT COUNT(*) AS n FROM highlights WHERE promoted = 1"
        ).fetchone()["n"]
    return {"total": total, "promoted": promoted, "by_camera": by_camera, "by_score": by_score}


# ---------------------------------------------------------------------------
# Remix likes + in-app notifications
# ---------------------------------------------------------------------------

def remix_like_add(db_path: Path, remix_id: str, email: str
                    ) -> tuple[int, bool]:
    """Idempotently add a like. Returns (current_like_count, was_new).
    was_new=False means the user had already liked this remix — caller
    should NOT generate a notification in that case."""
    with connect(db_path) as conn:
        before = conn.execute(
            "SELECT 1 FROM remix_likes WHERE remix_id = ? AND email = ?",
            [remix_id, email],
        ).fetchone()
        was_new = before is None
        if was_new:
            conn.execute(
                "INSERT INTO remix_likes (remix_id, email) VALUES (?, ?)",
                [remix_id, email],
            )
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM remix_likes WHERE remix_id = ?",
            [remix_id],
        ).fetchone()["n"]
    return int(count), was_new


def remix_likes_for_remix(db_path: Path, remix_id: str,
                           email: str | None = None) -> dict[str, Any]:
    """Single-remix like state for the modal heart."""
    with connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM remix_likes WHERE remix_id = ?",
            [remix_id],
        ).fetchone()["n"]
        my_liked = False
        if email:
            r = conn.execute(
                "SELECT 1 FROM remix_likes WHERE remix_id = ? AND email = ?",
                [remix_id, email],
            ).fetchone()
            my_liked = r is not None
    return {"like_count": int(count), "my_liked": bool(my_liked)}


def remix_likes_bulk(db_path: Path, remix_ids: list[str],
                      email: str | None = None) -> dict[str, dict[str, Any]]:
    """Per-remix {like_count, my_liked} for list endpoints. Avoids N+1."""
    if not remix_ids:
        return {}
    placeholders = ",".join("?" for _ in remix_ids)
    out: dict[str, dict[str, Any]] = {
        rid: {"like_count": 0, "my_liked": False} for rid in remix_ids
    }
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT remix_id, COUNT(*) AS n FROM remix_likes "
            f"WHERE remix_id IN ({placeholders}) GROUP BY remix_id",
            remix_ids,
        ).fetchall()
        for r in rows:
            out[r["remix_id"]]["like_count"] = int(r["n"])
        if email:
            mine = conn.execute(
                f"SELECT remix_id FROM remix_likes "
                f"WHERE email = ? AND remix_id IN ({placeholders})",
                [email] + list(remix_ids),
            ).fetchall()
            for r in mine:
                out[r["remix_id"]]["my_liked"] = True
    return out


def remix_ids_liked_by(db_path: Path, email: str) -> set[str]:
    """All remix_ids that this user has liked. Powers the "Liked by Me"
    status filter on the Remix view."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT remix_id FROM remix_likes WHERE email = ?", [email]
        ).fetchall()
    return {r["remix_id"] for r in rows}


def notif_create(db_path: Path, *, recipient_email: str, kind: str,
                  payload: dict[str, Any]) -> int:
    import json as _json
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO notifications (recipient_email, kind, payload) "
            "VALUES (?, ?, ?)",
            [recipient_email, kind, _json.dumps(payload)],
        )
        return int(cur.lastrowid)


def notif_list(db_path: Path, email: str, *, limit: int = 50,
                offset: int = 0, unread_only: bool = False
                ) -> list[dict[str, Any]]:
    import json as _json
    sql = ("SELECT * FROM notifications WHERE recipient_email = ?")
    args: list[Any] = [email]
    if unread_only:
        sql += " AND read_at IS NULL"
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = _json.loads(d["payload"]) if d["payload"] else {}
        except Exception:
            d["payload"] = {}
        out.append(d)
    return out


def notif_unread_count(db_path: Path, email: str) -> int:
    with connect(db_path) as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE recipient_email = ? AND read_at IS NULL",
            [email],
        ).fetchone()["n"]
    return int(n)


def notif_mark_read(db_path: Path, notif_id: int, email: str) -> bool:
    """Mark a single notification read. Email check prevents one user
    from clearing another user's notifications."""
    import time as _time
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at = ? "
            "WHERE id = ? AND recipient_email = ? AND read_at IS NULL",
            [_time.time(), notif_id, email],
        )
        return cur.rowcount > 0


def notif_mark_all_read(db_path: Path, email: str) -> int:
    import time as _time
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at = ? "
            "WHERE recipient_email = ? AND read_at IS NULL",
            [_time.time(), email],
        )
        return int(cur.rowcount)


# ---------------------------------------------------------------------------
# Web Push subscriptions + per-user kind preferences
# ---------------------------------------------------------------------------

def push_sub_save(db_path: Path, *, email: str, endpoint: str,
                   p256dh: str, auth: str, user_agent: str | None = None
                   ) -> int:
    """Upsert a subscription keyed on endpoint. If the same browser
    re-subscribes (e.g. after key rotation) we update the keys + email
    rather than create a duplicate."""
    import time as _time
    now = _time.time()
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO push_subscriptions "
            "(email, endpoint, p256dh, auth, user_agent, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET "
            "  email = excluded.email, p256dh = excluded.p256dh, "
            "  auth = excluded.auth, user_agent = excluded.user_agent, "
            "  last_seen_at = excluded.last_seen_at",
            [email, endpoint, p256dh, auth, user_agent, now],
        )
        return int(cur.lastrowid or 0)


def push_sub_list_for_email(db_path: Path, email: str
                             ) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, email, endpoint, p256dh, auth, user_agent, "
            "       created_at, last_seen_at "
            "FROM push_subscriptions WHERE email = ? "
            "ORDER BY created_at DESC",
            [email],
        ).fetchall()
    return [dict(r) for r in rows]


def push_sub_list_all_with_kind(db_path: Path, kind: str
                                  ) -> list[dict[str, Any]]:
    """All subscriptions whose owner has `kind` enabled. Used by the
    new_highlight broadcast path. Defaults from PUSH_KIND_DEFAULTS apply
    when the user has no explicit row for this kind."""
    default_enabled = bool(PUSH_KIND_DEFAULTS.get(kind, {}).get("enabled", True))
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT s.id, s.email, s.endpoint, s.p256dh, s.auth, "
            "       s.user_agent, p.enabled AS pref_enabled "
            "FROM push_subscriptions s "
            "LEFT JOIN push_preferences p "
            "  ON p.email = s.email AND p.kind = ?",
            [kind],
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # NULL pref → fall back to default. Explicit 0/1 wins.
        if d["pref_enabled"] is None:
            if default_enabled:
                out.append(d)
        elif int(d["pref_enabled"]) == 1:
            out.append(d)
    return out


def push_sub_delete_by_endpoint(db_path: Path, endpoint: str) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", [endpoint]
        )
        return cur.rowcount > 0


def push_pref_enabled_for(db_path: Path, email: str, kind: str) -> bool:
    """Resolve the effective preference for one (email, kind), applying
    PUSH_KIND_DEFAULTS when no explicit row exists."""
    default_enabled = bool(PUSH_KIND_DEFAULTS.get(kind, {}).get("enabled", True))
    with connect(db_path) as conn:
        r = conn.execute(
            "SELECT enabled FROM push_preferences WHERE email = ? AND kind = ?",
            [email, kind],
        ).fetchone()
    if r is None:
        return default_enabled
    return int(r["enabled"]) == 1


def push_pref_get_all(db_path: Path, email: str) -> dict[str, Any]:
    """Return the full kind table merged with this user's overrides.
    Shape: {kind: {enabled, value, label, desc, default_value, options}}.
    Caller-friendly — UI just iterates and renders."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT kind, enabled, value FROM push_preferences WHERE email = ?",
            [email],
        ).fetchall()
    overrides = {r["kind"]: {"enabled": int(r["enabled"]) == 1,
                              "value":   r["value"]}
                 for r in rows}
    out: dict[str, Any] = {}
    for kind, meta in PUSH_KIND_DEFAULTS.items():
        ov = overrides.get(kind, {})
        out[kind] = {
            "enabled":       ov.get("enabled", bool(meta.get("enabled", True))),
            "value":         ov.get("value") or meta.get("default_value"),
            "default_value": meta.get("default_value"),
            "label":         meta.get("label", kind),
            "desc":          meta.get("desc", ""),
            "options":       meta.get("options", []),
        }
    return out


def push_pref_value_for(db_path: Path, email: str, kind: str) -> str | None:
    """Just the value (severity etc.) — used by the broadcast filter."""
    default = PUSH_KIND_DEFAULTS.get(kind, {}).get("default_value")
    with connect(db_path) as conn:
        r = conn.execute(
            "SELECT value FROM push_preferences WHERE email = ? AND kind = ?",
            [email, kind],
        ).fetchone()
    if r is None or r["value"] is None:
        return default
    return r["value"]


def push_pref_set(db_path: Path, email: str, kind: str,
                   enabled: bool | None = None,
                   value: str | None = None) -> None:
    """Upsert; either field may be left as None to preserve existing.
    UI sends one field at a time so the other survives untouched."""
    import time as _time
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT enabled, value FROM push_preferences "
            "WHERE email = ? AND kind = ?",
            [email, kind],
        ).fetchone()
        if existing is None:
            cur_enabled = 1 if (enabled is True) else 0
            if enabled is None:
                # Unknown: fall back to declared default.
                cur_enabled = 1 if PUSH_KIND_DEFAULTS.get(kind, {}).get(
                    "enabled", True) else 0
            cur_value = value
        else:
            cur_enabled = int(existing["enabled"]) if enabled is None else (
                1 if enabled else 0)
            cur_value = existing["value"] if value is None else value
        conn.execute(
            "INSERT INTO push_preferences (email, kind, enabled, value, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(email, kind) DO UPDATE SET "
            "  enabled = excluded.enabled, value = excluded.value, "
            "  updated_at = excluded.updated_at",
            [email, kind, cur_enabled, cur_value, _time.time()],
        )


# ---- Pause + schedule -----------------------------------------------------

def push_pause_get(db_path: Path, email: str) -> float | None:
    with connect(db_path) as conn:
        r = conn.execute(
            "SELECT paused_until FROM push_pause WHERE email = ?", [email]
        ).fetchone()
    if r is None:
        return None
    until = r["paused_until"]
    if until is None:
        return None
    return float(until)


def push_pause_set(db_path: Path, email: str,
                    paused_until: float | None) -> None:
    """`paused_until` is a unix-epoch float; None clears the pause."""
    import time as _time
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO push_pause (email, paused_until, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET "
            "  paused_until = excluded.paused_until, "
            "  updated_at = excluded.updated_at",
            [email, paused_until, _time.time()],
        )


def push_pause_active(db_path: Path, email: str,
                       *, now: float | None = None) -> bool:
    import time as _time
    until = push_pause_get(db_path, email)
    if until is None:
        return False
    return until > (now or _time.time())


def push_schedule_list(db_path: Path, email: str) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, start_min, end_min, tz_offset_min "
            "FROM push_schedule_intervals "
            "WHERE email = ? ORDER BY start_min ASC",
            [email],
        ).fetchall()
    return [dict(r) for r in rows]


def push_schedule_add(db_path: Path, email: str,
                       start_min: int, end_min: int,
                       tz_offset_min: int = 0) -> int:
    if not (0 <= start_min <= 1439 and 0 <= end_min <= 1439):
        raise ValueError("start_min / end_min must be in [0, 1439]")
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO push_schedule_intervals "
            "(email, start_min, end_min, tz_offset_min) "
            "VALUES (?, ?, ?, ?)",
            [email, start_min, end_min, tz_offset_min],
        )
        return int(cur.lastrowid or 0)


def push_schedule_delete(db_path: Path, interval_id: int, email: str
                          ) -> bool:
    """Email check prevents one user from deleting another's intervals."""
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM push_schedule_intervals WHERE id = ? AND email = ?",
            [interval_id, email],
        )
        return cur.rowcount > 0


def push_schedule_active(db_path: Path, email: str,
                          *, now: float | None = None) -> bool:
    """True iff the current wall-clock time falls inside any of this
    user's quiet-hours intervals. Each interval carries its own
    tz_offset_min (captured at create-time from the browser's
    Date.getTimezoneOffset, so DST shifts apply automatically when the
    user re-saves the schedule)."""
    import time as _time
    intervals = push_schedule_list(db_path, email)
    if not intervals:
        return False
    now_ts = now or _time.time()
    for it in intervals:
        # Convert wall-clock UTC to the interval's local minute-of-day.
        # tz_offset_min is what JavaScript's Date.getTimezoneOffset()
        # returns: positive when local is BEHIND UTC. So local = UTC -
        # tz_offset_min.
        local_minutes = (int(now_ts // 60) - int(it["tz_offset_min"])) % 1440
        s, e = int(it["start_min"]), int(it["end_min"])
        if s == e:
            continue   # zero-width window — ignore
        if s < e:
            if s <= local_minutes < e:
                return True
        else:
            # Wraps midnight — e.g. 22:00 → 07:00 means in window when
            # local_minutes >= 22:00 OR < 07:00.
            if local_minutes >= s or local_minutes < e:
                return True
    return False
