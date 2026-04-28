#!/usr/bin/env python3
"""
Backfill analytics.daily_snapshots for missing weekday dates.

For each missing date in the working window:
  1. Run collect_analytics_snapshot via Letta /v1/tools/run with that date.
  2. Drive + Email retroactively populate (Admin Reports lookback ~6 months).
  3. Slack will likely come back as 'slack_collected: False' for any date
     outside the rolling Slack-CSV window — that's expected and accepted
     for this first-pass backfill.
  4. Optionally emit a Layer-5 backfill marker so MC can see what happened.

Usage:
    python3 scripts/backfill-analytics-snapshots.py --start 2026-04-01 --end 2026-04-26
    python3 scripts/backfill-analytics-snapshots.py --since-days 30
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

LETTA_URL = "http://localhost:8283"
PG_HOST = "supabase-db"
SNAPSHOT_TOOL_ID = None  # resolved at runtime


def get_existing_dates():
    pw = os.popen("grep -E '^POSTGRES_PASSWORD' /Volumes/main-drive/ai-PA/.env | cut -d= -f2- | tr -d '\"'").read().strip()
    cmd = (
        f"docker exec -e PGPASSWORD={pw} supabase-db psql -h localhost -U postgres -d postgres "
        f"-At -c \"SELECT snapshot_date FROM analytics.daily_snapshots ORDER BY snapshot_date;\""
    )
    out = os.popen(cmd).read().strip()
    return {date.fromisoformat(d) for d in out.split("\n") if d}


def get_snapshot_tool():
    r = urllib.request.urlopen(f"{LETTA_URL}/v1/tools/?limit=500")
    tools = json.loads(r.read())
    return next(t for t in tools if t.get("name") == "collect_analytics_snapshot")


def run_snapshot(tool, target_date):
    body = json.dumps({
        "source_code": tool["source_code"],
        "name": "collect_analytics_snapshot",
        "source_type": "python",
        "args": {"date": target_date.isoformat()},
        "args_json_schema": tool["json_schema"]["parameters"],
        "json_schema": tool["json_schema"],
    }).encode()
    req = urllib.request.Request(f"{LETTA_URL}/v1/tools/run", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=300)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"status": "http_error", "error": f"{e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"status": "exception", "error": str(e)[:300]}


def is_weekday(d):
    return d.weekday() < 5


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=None)
    p.add_argument("--end", type=date.fromisoformat, default=None)
    p.add_argument("--since-days", type=int, default=None)
    p.add_argument("--include-weekends", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    today = date.today()
    if args.since_days:
        start = today - timedelta(days=args.since_days)
        end = today - timedelta(days=1)
    else:
        start = args.start or (today - timedelta(days=30))
        end = args.end or (today - timedelta(days=1))

    existing = get_existing_dates()
    print(f"existing snapshots in DB: {len(existing)} dates", flush=True)

    # Build list of dates to fill
    todo = []
    cur = start
    while cur <= end:
        if (args.include_weekends or is_weekday(cur)) and cur not in existing:
            todo.append(cur)
        cur += timedelta(days=1)

    print(f"backfill plan: {len(todo)} dates from {start} to {end}", flush=True)
    for d in todo:
        print(f"  - {d.isoformat()} ({d.strftime('%a')})", flush=True)

    if args.dry_run:
        print("(dry-run; not running)", flush=True)
        return 0

    tool = get_snapshot_tool()
    print(f"loaded snapshot tool: {tool['id']}", flush=True)

    results = []
    for i, d in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {d.isoformat()} ...", flush=True)
        t0 = time.time()
        res = run_snapshot(tool, d)
        elapsed = time.time() - t0
        status = res.get("status")
        rt = res.get("tool_return") or res.get("error") or ""
        # extract key fields from successful return
        line = f"   {status}  ({elapsed:.1f}s)"
        if isinstance(rt, dict):
            line += (
                f"  drive={rt.get('drive_collected')} email={rt.get('email_collected')} "
                f"slack={rt.get('slack_collected')}  errs={len(rt.get('errors') or [])}"
            )
        else:
            line += f"  preview={str(rt)[:140]}"
        print(line, flush=True)
        results.append({"date": d.isoformat(), "status": status, "elapsed": elapsed, "ret": str(rt)[:300]})
        # Be polite — 2s pacing between snapshots
        time.sleep(2)

    # Summary
    ok = sum(1 for r in results if r["status"] == "success")
    print(f"\n=== backfill complete: {ok}/{len(results)} succeeded ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
