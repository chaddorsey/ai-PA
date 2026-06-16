#!/usr/bin/env python3
"""flag-meeting-task-overlaps.py — soft dedup for meeting tasks.

POLICY (per user, 2026-06-16): keep BOTH the semantic (docs-meeting) and the
marker ([c]/[;]) task paths — never suppress either, never block creation. When
a semantic task likely re-states an item the user explicitly marked, FLAG it as
a potential duplicate of the marker task so the confirmation step can resolve
it. Marked tasks carry user intent and are tagged so the UI can prioritize them.
Err toward flagging when unsure (the flag is advisory + non-destructive).

GROUND TRUTH = the `meeting_marker` rows in pa_web.task_queue (written verbatim
from the user's [c]/[;] notes by scan_meeting_markers.py). We do NOT re-hit the
flaky MCP here.

What it writes (idempotent, non-destructive — only enrichment JSONB):
  - On the marker-origin task:   enrichment.task_origin = "marker"
                                 enrichment.user_marked = true   (UI prioritizes)
  - On an overlapping semantic task:
        enrichment.potential_duplicate_of = {
            ref_id, title, marker_text, similarity }
    (so the confirmation UI can show "⚠ possible duplicate of <marked task>")

Matching is intra-meeting only (tasks grouped by Granola meeting UUID via
source_ref, OR by meeting title+date to bridge the UUID/not_* id duality).

Usage: python3 flag-meeting-task-overlaps.py [--window-hours 24] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# Tokens to ignore when comparing task text (function words + meeting filler).
_STOP = {
    "the", "a", "an", "to", "for", "of", "and", "or", "with", "in", "on", "at",
    "by", "is", "be", "as", "via", "from", "into", "this", "that", "it", "your",
    "you", "we", "i", "re", "about", "any", "will", "should", "need", "needs",
    "please", "per", "regarding", "re:", "etc", "vs", "—", "-",
}
MARKER_MATCH = 0.62   # >= this vs a marker → it's the marker-origin task itself
DUP_FLAG = 0.30       # in [DUP_FLAG, MARKER_MATCH) vs a marker → flag as possible dup


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{ts()}] [overlap-flag] {msg}", flush=True)


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 1 and w not in _STOP}


def similarity(a: str, b: str) -> float:
    """Jaccard over significant tokens. 0..1."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _db_url() -> str:
    url = os.environ.get("PA_WEB_POSTGRES_URL")
    if url:
        return url
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
    return f"postgresql://postgres:{pw}@localhost:{port}/postgres"


def _uuid_from(s: str) -> str | None:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s or "")
    return m.group(0) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int, default=24,
                    help="Only consider markers + tasks from the last N hours.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    flagged = 0
    tagged = 0
    with psycopg.connect(_db_url(), autocommit=True, connect_timeout=10) as conn:
        # 1. Ground truth: marker rows (verbatim user [c]/[;] items) in window.
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT payload->>'raw_description' AS marker_text,
                       payload->>'meeting_id'       AS meeting_id,
                       payload->>'title'            AS title
                  FROM pa_web.task_queue
                 WHERE source = 'meeting_marker'
                   AND created_at > NOW() - (%s || ' hours')::interval
                """,
                (args.window_hours,),
            )
            markers = [r for r in cur.fetchall() if r.get("marker_text")]
        if not markers:
            log(f"no meeting_marker rows in last {args.window_hours}h — nothing to do")
            return 0

        # Group markers by meeting (uuid + title).
        by_meeting: dict[str, dict] = {}
        for m in markers:
            key = m["meeting_id"] or (m["title"] or "")
            g = by_meeting.setdefault(key, {"uuid": m["meeting_id"], "title": m["title"], "texts": []})
            g["texts"].append(m["marker_text"])

        log(f"{len(markers)} marker(s) across {len(by_meeting)} meeting(s)")

        # 2. For each meeting, pull its open tasks and compare.
        for key, g in by_meeting.items():
            uuid = g["uuid"] or ""
            title = g["title"] or ""
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT ref_id,
                           COALESCE(suggested_title, raw_description, '') AS text,
                           source_ref, enrichment
                      FROM pa_web.tasks
                     WHERE source = 'meeting'
                       AND closed_at IS NULL
                       AND COALESCE(extracted_at, created_at) > NOW() - (%s || ' hours')::interval
                       AND ( source_ref LIKE %s
                             OR source_metadata->>'title' = %s )
                    """,
                    (args.window_hours, f"%{uuid}%", title),
                )
                tasks = cur.fetchall()
            if not tasks:
                continue

            # Classify each task vs the meeting's markers.
            for t in tasks:
                best_sim = 0.0
                best_marker = ""
                for mt in g["texts"]:
                    s = similarity(t["text"], mt)
                    if s > best_sim:
                        best_sim, best_marker = s, mt
                enr = t.get("enrichment") or {}
                if not isinstance(enr, dict):
                    enr = {}

                if best_sim >= MARKER_MATCH:
                    # This task IS (essentially) the marked item — tag user intent.
                    if enr.get("task_origin") == "marker" and enr.get("user_marked"):
                        continue
                    enr["task_origin"] = "marker"
                    enr["user_marked"] = True
                    if args.dry_run:
                        log(f"  [DRY] tag user-marked: {t['ref_id']} ({t['text'][:50]!r}) sim={best_sim:.2f}")
                    else:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE pa_web.tasks SET enrichment = %s WHERE ref_id = %s",
                                (Jsonb(enr), t["ref_id"]),
                            )
                    tagged += 1
                elif best_sim >= DUP_FLAG:
                    # Overlaps a marked item but isn't verbatim → likely the
                    # semantic restatement. Flag for confirmation-time resolution.
                    existing = enr.get("potential_duplicate_of") or {}
                    if existing.get("marker_text") == best_marker:
                        continue  # already flagged against this marker
                    enr["potential_duplicate_of"] = {
                        "marker_text": best_marker,
                        "similarity": round(best_sim, 2),
                        "reason": "overlaps a [c]/[;]-marked item from the same meeting",
                        "flagged_at": ts(),
                    }
                    if args.dry_run:
                        log(f"  [DRY] FLAG dup: {t['ref_id']} ({t['text'][:46]!r}) "
                            f"~ marker {best_marker[:40]!r} sim={best_sim:.2f}")
                    else:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE pa_web.tasks SET enrichment = %s WHERE ref_id = %s",
                                (Jsonb(enr), t["ref_id"]),
                            )
                    flagged += 1

    log(f"done: user_marked_tagged={tagged} potential_dups_flagged={flagged}"
        + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
