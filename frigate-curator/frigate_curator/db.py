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
    "CREATE INDEX IF NOT EXISTS highlights_favorited ON highlights (favorited, start_time DESC)",
    "CREATE INDEX IF NOT EXISTS highlights_demoted   ON highlights (demoted, start_time DESC)",
]


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
    hour_from: int | None = None,  # 0–23, inclusive
    hour_to: int | None = None,    # 0–23, exclusive (allows wrap, e.g. 18→6)
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM highlights WHERE fox_likelihood >= ?"
    args: list[Any] = [min_score]
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
        # default: hide demoted from main view; show everything else
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
