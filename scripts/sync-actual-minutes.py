#!/usr/bin/env python3
"""Sync actual task time from the OmniFocus timer into pa_web.tasks.actual_minutes.

The timer logs real time-spent per task to omnifocus-timer/logs/completions.jsonl
(keyed by refId), but pa_web.tasks.actual_minutes (which existed) was never
written — so estimate-vs-actual couldn't be queried in one place. This closes
that half of the task eval loop: actuals land next to suggested_title/
confirmed_title + original_est_minutes/revised_est_minutes. Idempotent.

Env: PA_WEB_POSTGRES_URL. Source: omnifocus-timer/logs/completions.jsonl.
"""
import json
import os
import sys

import psycopg

COMPLETIONS = os.environ.get(
    "TIMER_COMPLETIONS",
    "/Volumes/main-drive/ai-PA/omnifocus-timer/logs/completions.jsonl",
)


def latest_actuals(path: str) -> dict[str, int]:
    """Map refId -> actual minutes; last completion for a refId wins."""
    out: dict[str, int] = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = e.get("refId")
                ms = e.get("totalMs") or e.get("sessionMs")
                if rid and ms:
                    out[rid] = max(1, round(ms / 60000))
    except FileNotFoundError:
        pass
    return out


def main() -> int:
    url = os.environ.get("PA_WEB_POSTGRES_URL")
    if not url:
        print(json.dumps({"status": "error", "error": "PA_WEB_POSTGRES_URL not set"}),
              file=sys.stderr)
        return 1
    actuals = latest_actuals(COMPLETIONS)
    updated = 0
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        for rid, mins in actuals.items():
            cur.execute(
                "UPDATE pa_web.tasks SET actual_minutes = %s "
                "WHERE ref_id = %s AND actual_minutes IS DISTINCT FROM %s",
                (mins, rid, mins),
            )
            updated += cur.rowcount
    print(json.dumps({"completions": len(actuals), "rows_updated": updated}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
