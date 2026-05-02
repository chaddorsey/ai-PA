"""SQLite index of curated highlights.

Schema is simple — one row per highlight (= one Frigate event we copied).
Lives at $HIGHLIGHTS_DIR/index.db, alongside the clip files. Co-located so
backups capture both clips and metadata in one filesystem snapshot.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS highlights (
    event_id        TEXT PRIMARY KEY,
    camera          TEXT NOT NULL,
    label           TEXT NOT NULL,
    start_time      REAL NOT NULL,        -- unix epoch seconds
    end_time        REAL,
    duration_s      REAL,
    score           REAL NOT NULL,        -- Frigate detection confidence
    fox_likelihood  REAL NOT NULL,        -- our heuristic, 0.0–1.0
    clip_path       TEXT NOT NULL,        -- relative to highlights root
    thumb_path      TEXT,
    promoted        INTEGER NOT NULL DEFAULT 0,  -- 1 if manually promoted
    promoted_at     REAL,
    created_at      REAL NOT NULL DEFAULT (strftime('%s','now')),
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS highlights_camera_start ON highlights (camera, start_time DESC);
CREATE INDEX IF NOT EXISTS highlights_likelihood   ON highlights (fox_likelihood DESC, start_time DESC);
CREATE INDEX IF NOT EXISTS highlights_promoted     ON highlights (promoted, start_time DESC);
"""


def init(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


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
    sql += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


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
