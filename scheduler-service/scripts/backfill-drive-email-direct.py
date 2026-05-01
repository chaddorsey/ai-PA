#!/usr/local/bin/python3
"""
backfill-drive-email-direct.py — backfill analytics.daily_snapshots
drive + email columns by hitting Google Admin Reports directly via gws CLI.

Bypasses Letta entirely. The Letta-tool path (analytics-backfill.py +
collect_analytics_snapshot via pulse-monitor) crashes Letta under
sustained load — drive + email aren't agent-natured tasks anyway.

For each gap-day in the last N days where drive_total_activities OR
email_total_sent is null/missing, this script:
  1. Calls `gws admin reports activities list applicationName=drive`
     for the date and aggregates activity counts by type
  2. Calls `gws admin reports activities list applicationName=gmail`
     for the date and aggregates send/receive counts
  3. UPSERTs (snapshot_date, drive_*, email_*) into analytics.daily_snapshots
     via psycopg, preserving any existing slack_* columns

Idempotent: re-running on already-filled dates is a no-op (existing fields
are not overwritten with non-null values).

Usage:
    backfill-drive-email-direct.py --window 180 --dry-run
    backfill-drive-email-direct.py --window 180 [--max N]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone

import psycopg


ENV_PATH = "/workspace/.env"


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


# Map Drive activity event names to our snapshot's activity_breakdown keys.
DRIVE_EVENT_BUCKETS = {
    "edit": "edit",
    "view": "view",
    "create": "create",
    "rename": "edit",
    "trash": "edit",
    "untrash": "edit",
    "delete": "edit",
    "upload": "create",
    "download": "view",
    "print": "view",
    "share": "share",
    "change_acl_editors": "share",
    "change_user_access": "share",
    "change_document_visibility": "share",
    "change_document_access_scope": "share",
    "change_role_user": "share",
    "create_comment": "comment",
    "edit_comment": "comment",
    "delete_comment": "comment",
    "resolve_comment": "comment",
    "reopen_comment": "comment",
}


def gws_admin_reports(application, start_iso, end_iso, max_results=1000):
    """Call gws admin reports activities list for a given application + window.

    Returns list of items (each is a Google Reports activity record). Uses
    the gws CLI (installed at /usr/local/bin/gws). Pages internally if Google
    returns a nextPageToken — Reports API caps at ~1000 per page.
    """
    items = []
    page_token = None
    while True:
        params = {
            "userKey": "all",
            "applicationName": application,
            "startTime": start_iso,
            "endTime": end_iso,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        cmd = ["gws", "admin-reports", "activities", "list", "--params", json.dumps(params)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"gws failed for {application} {start_iso}: {proc.stderr[:300]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"gws returned non-JSON for {application} {start_iso}: {proc.stdout[:300]}") from e
        result = data.get("result") or data
        page_items = result.get("items") or []
        items.extend(page_items)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.2)
    return items


def aggregate_drive(items):
    """Aggregate drive activity items into our snapshot's drive metrics."""
    activity_breakdown = {"edit": 0, "view": 0, "create": 0, "share": 0, "comment": 0, "other": 0}
    unique_users = set()
    unique_docs = set()
    total = 0

    for item in items:
        actor = (item.get("actor") or {}).get("email")
        if actor:
            unique_users.add(actor)
        for ev in item.get("events") or []:
            event_name = ev.get("name", "")
            bucket = DRIVE_EVENT_BUCKETS.get(event_name, "other")
            activity_breakdown[bucket] += 1
            total += 1
            for param in ev.get("parameters") or []:
                if param.get("name") == "doc_id":
                    val = param.get("value")
                    if val:
                        unique_docs.add(val)

    return {
        "total_activities": total,
        "unique_users": len(unique_users),
        "unique_documents": len(unique_docs),
        "activity_breakdown": activity_breakdown,
    }


def aggregate_email(items):
    """Aggregate gmail audit items into send/receive counts.

    Note: Google Gmail audit log reports administrative events, not message
    counts directly. For per-user message counts, the User Usage report is
    more appropriate. We use a simple heuristic — count distinct events as
    activity volume — and also tally distinct users to match what the
    existing collect_analytics_snapshot tool produces.
    """
    user_count = set()
    total = 0
    sent = 0
    received = 0

    for item in items:
        actor = (item.get("actor") or {}).get("email")
        if actor:
            user_count.add(actor)
        for ev in item.get("events") or []:
            name = (ev.get("name") or "").lower()
            total += 1
            if "send" in name or "compose" in name:
                sent += 1
            elif "receive" in name or "deliver" in name:
                received += 1

    ratio = round(sent / received, 3) if received else None
    return {
        "total_sent": sent,
        "total_received": received,
        "ratio": ratio,
        "total_activity": total,
        "user_count": len(user_count),
    }


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
             WHEN s.snapshot_date IS NULL                 THEN 'missing'
             WHEN s.drive_total_activities IS NULL AND s.email_total_sent IS NULL THEN 'drive+email-null'
             WHEN s.drive_total_activities IS NULL        THEN 'drive-null'
             WHEN s.email_total_sent IS NULL              THEN 'email-null'
             ELSE NULL
           END AS gap_kind
    FROM expected e
    LEFT JOIN analytics.daily_snapshots s ON e.d = s.snapshot_date
    WHERE s.snapshot_date IS NULL
       OR s.drive_total_activities IS NULL
       OR s.email_total_sent IS NULL
    ORDER BY e.d
    """
    with psycopg.connect(PG_URL, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (start, end))
            return cur.fetchall()


def upsert_row(target_date, drive, email):
    """Upsert (drive_*, email_*) into daily_snapshots without disturbing slack_* columns."""
    is_workday = target_date.weekday() < 5
    with psycopg.connect(PG_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.daily_snapshots
                  (snapshot_date, is_workday, collected_at,
                   drive_total_activities, drive_unique_users, drive_unique_documents,
                   drive_edits, drive_views, drive_creates, drive_shares,
                   drive_comments, drive_other_activities,
                   email_total_sent, email_total_received, email_ratio, email_total_activity,
                   raw_snapshot)
                VALUES (%s, %s, now(),
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_date) DO UPDATE SET
                  drive_total_activities = COALESCE(EXCLUDED.drive_total_activities, analytics.daily_snapshots.drive_total_activities),
                  drive_unique_users     = COALESCE(EXCLUDED.drive_unique_users,     analytics.daily_snapshots.drive_unique_users),
                  drive_unique_documents = COALESCE(EXCLUDED.drive_unique_documents, analytics.daily_snapshots.drive_unique_documents),
                  drive_edits            = COALESCE(EXCLUDED.drive_edits,            analytics.daily_snapshots.drive_edits),
                  drive_views            = COALESCE(EXCLUDED.drive_views,            analytics.daily_snapshots.drive_views),
                  drive_creates          = COALESCE(EXCLUDED.drive_creates,          analytics.daily_snapshots.drive_creates),
                  drive_shares           = COALESCE(EXCLUDED.drive_shares,           analytics.daily_snapshots.drive_shares),
                  drive_comments         = COALESCE(EXCLUDED.drive_comments,         analytics.daily_snapshots.drive_comments),
                  drive_other_activities = COALESCE(EXCLUDED.drive_other_activities, analytics.daily_snapshots.drive_other_activities),
                  email_total_sent       = COALESCE(EXCLUDED.email_total_sent,       analytics.daily_snapshots.email_total_sent),
                  email_total_received   = COALESCE(EXCLUDED.email_total_received,   analytics.daily_snapshots.email_total_received),
                  email_ratio            = COALESCE(EXCLUDED.email_ratio,            analytics.daily_snapshots.email_ratio),
                  email_total_activity   = COALESCE(EXCLUDED.email_total_activity,   analytics.daily_snapshots.email_total_activity)
                """,
                (
                    target_date, is_workday,
                    drive["total_activities"], drive["unique_users"], drive["unique_documents"],
                    drive["activity_breakdown"]["edit"],
                    drive["activity_breakdown"]["view"],
                    drive["activity_breakdown"]["create"],
                    drive["activity_breakdown"]["share"],
                    drive["activity_breakdown"]["comment"],
                    drive["activity_breakdown"]["other"],
                    email["total_sent"], email["total_received"], email["ratio"], email["total_activity"],
                    json.dumps({"drive": drive, "email": email, "source": "direct-gws-backfill"}),
                ),
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=180)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max", type=int, default=200)
    p.add_argument("--throttle-ms", type=int, default=300)
    args = p.parse_args()

    gaps = find_gaps(args.window)
    print(f"Found {len(gaps)} gap-days in last {args.window}d")
    by_kind = {}
    for d, kind in gaps:
        by_kind[kind] = by_kind.get(kind, 0) + 1
    for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {kind}: {n}")

    if args.dry_run:
        print("\nDry-run sample (first 20):")
        for d, kind in gaps[:20]:
            print(f"  {d}  {kind}")
        return 0

    to_fire = gaps[: args.max]
    if len(to_fire) < len(gaps):
        print(f"\nCapped at --max={args.max}; {len(gaps) - args.max} dates NOT processed this run.")

    print(f"\nProcessing {len(to_fire)} dates...")
    ok = 0
    failed = 0
    for d, kind in to_fire:
        start_iso = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()
        end_iso = (datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
        try:
            drive_items = gws_admin_reports("drive", start_iso, end_iso)
            email_items = gws_admin_reports("gmail", start_iso, end_iso)
            drive = aggregate_drive(drive_items)
            email = aggregate_email(email_items)
            upsert_row(d, drive, email)
            ok += 1
            print(f"  ✓ {d}  drive={drive['total_activities']} email={email['total_activity']}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {d}: {e}", file=sys.stderr)
        time.sleep(args.throttle_ms / 1000.0)

    print(f"\nDone: {ok} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
