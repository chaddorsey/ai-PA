#!/usr/local/bin/python3
"""
analytics-backfill.py — backfill analytics.daily_snapshots gaps.

Walks the last 180 days, finds dates where:
  - The row is missing entirely, OR
  - drive_total_activities IS NULL, OR
  - email_total_sent IS NULL

For each, fires a fire-and-forget agent message to pulse-monitor asking it
to run collect_analytics_snapshot(date='YYYY-MM-DD'). The tool fetches
Drive + Email from Google Admin Reports (180d retention) and upserts the
daily_snapshots row.

Slack data older than ~14 days is unrecoverable (Slack rotates CSV URLs);
those dates will get drive+email backfilled but slack section stays null.

Usage:
    python3 analytics-backfill.py --dry-run
    python3 analytics-backfill.py [--max N]    # cap fan-out per run

Designed to be invoked manually for one-time backfill, not as a recurring
cron. Idempotent: re-running on already-filled dates is a no-op.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta

import psycopg


ENV_PATH = "/workspace/.env"
LETTA = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
PULSE_MONITOR = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"


def read_env(name):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


PG_PASSWORD = read_env("POSTGRES_PASSWORD") or ""
PG_URL = (
    read_env("PA_WEB_POSTGRES_URL")
    or f"postgresql://postgres:{PG_PASSWORD}@supabase-db:5432/postgres"
)


def find_gaps(window_days):
    today = date.today()
    start = today - timedelta(days=window_days)
    end = today - timedelta(days=1)

    sql = """
    WITH expected AS (
      SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS d
    )
    SELECT e.d,
           CASE
             WHEN s.snapshot_date IS NULL                                THEN 'missing'
             WHEN s.drive_total_activities IS NULL AND s.email_total_sent IS NULL THEN 'drive+email-null'
             WHEN s.drive_total_activities IS NULL                       THEN 'drive-null'
             WHEN s.email_total_sent IS NULL                             THEN 'email-null'
             ELSE NULL
           END AS gap_kind
    FROM expected e
    LEFT JOIN analytics.daily_snapshots s ON e.d = s.snapshot_date
    WHERE
      s.snapshot_date IS NULL
      OR s.drive_total_activities IS NULL
      OR s.email_total_sent IS NULL
    ORDER BY e.d
    """

    with psycopg.connect(PG_URL, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (start, end))
            return cur.fetchall()


def fire_backfill(target_date):
    prompt = (
        f"Backfill: run collect_analytics_snapshot(date='{target_date}'). "
        f"This fills the analytics.daily_snapshots row for that date with "
        f"Drive + Email metrics from Google Admin Reports. Slack data may be "
        f"unavailable for dates older than ~14 days (Slack rotates CSV URLs); "
        f"if Slack fails, that's expected — drive + email are what we're recovering. "
        f"Reply with one short line: 'Backfill {target_date}: <summary>'."
    )
    body = {"messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        f"{LETTA}/v1/agents/{PULSE_MONITOR}/messages/async",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Letta /messages/async blocks until queued; under fan-out this can take >30s.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("id")
        except Exception as e:
            if attempt == 2:
                sys.stderr.write(f"  ! {target_date}: {e}\n")
                return None
            time.sleep(5 * (attempt + 1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=180, help="Lookback window in days (default 180)")
    p.add_argument("--dry-run", action="store_true", help="List gaps; don't fire")
    p.add_argument("--max", type=int, default=200, help="Cap fan-out per run")
    p.add_argument("--throttle-ms", type=int, default=200, help="Sleep between fires (ms)")
    args = p.parse_args()

    gaps = find_gaps(args.window)
    print(f"Found {len(gaps)} gap-days in last {args.window}d:")
    by_kind = {}
    for d, kind in gaps:
        by_kind[kind] = by_kind.get(kind, 0) + 1
    for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {kind}: {n}")

    if not gaps:
        return 0

    if args.dry_run:
        print("\nDry-run sample (first 20):")
        for d, kind in gaps[:20]:
            print(f"  {d}  {kind}")
        return 0

    to_fire = gaps[: args.max]
    if len(to_fire) < len(gaps):
        print(f"\nCapped at --max={args.max}; {len(gaps) - args.max} dates NOT fired this run. Re-run to continue.")

    print(f"\nFiring backfill for {len(to_fire)} dates...")
    fired = 0
    for d, kind in to_fire:
        run_id = fire_backfill(d.strftime("%Y-%m-%d"))
        if run_id:
            fired += 1
            if fired % 20 == 0:
                print(f"  ...{fired}/{len(to_fire)} fired")
        time.sleep(args.throttle_ms / 1000.0)

    print(f"\nFired {fired}/{len(to_fire)} backfill runs (asynchronously, fire-and-forget).")
    print("Watch progress: SELECT COUNT(*) FROM analytics.daily_snapshots WHERE snapshot_date > CURRENT_DATE - 180 AND drive_total_activities IS NOT NULL;")
    return 0


if __name__ == "__main__":
    sys.exit(main())
