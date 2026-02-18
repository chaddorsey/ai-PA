#!/usr/bin/env python3
"""
Backfill analytics.daily_snapshots with historical data from Admin Reports API.

The Admin Reports API retains Drive and Email activity for ~180 days.
This script iterates over past workdays and calls collect_analytics_snapshot()
via the Letta agent API, using the same code path as the scheduled pipeline.

The DB uses upsert (merge-duplicates), so re-running is safe and idempotent.

Usage:
  # Backfill last 30 workdays (default)
  python scripts/backfill-analytics-history.py

  # Backfill last 90 calendar days of workdays
  python scripts/backfill-analytics-history.py --days 90

  # Backfill a specific date range
  python scripts/backfill-analytics-history.py --start 2025-09-01 --end 2026-02-17

  # Dry run (show dates without collecting)
  python scripts/backfill-analytics-history.py --dry-run

  # Custom delay between API calls (seconds)
  python scripts/backfill-analytics-history.py --delay 10
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta

LETTA_BASE_URL = "http://localhost:8283"
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_DELAY_SECONDS = 5


def get_workdays(start_date, end_date):
    """Generate workdays (Mon-Fri) between start and end dates, inclusive."""
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # Mon=0, Fri=4
            yield current
        current += timedelta(days=1)


def get_existing_snapshots(dates):
    """Check which dates already have snapshots in the DB."""
    # Query the Letta agent to check — but this is slow.
    # Instead, just return empty set and let upsert handle duplicates.
    return set()


def collect_for_date(date_str):
    """Call collect_analytics_snapshot via Letta agent API for a specific date."""
    message = (
        f"Run collect_analytics_snapshot(date='{date_str}') and report the summary. "
        f"This is a historical backfill — just run the tool and report results concisely."
    )

    payload = json.dumps({
        "messages": [{"role": "user", "content": message}]
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{LETTA_BASE_URL}/v1/agents/{PULSE_MONITOR_ID}/messages",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        messages = data if isinstance(data, list) else data.get("messages", [])

        # Find tool return message
        for msg in messages:
            if msg.get("message_type") == "tool_return_message":
                ret = msg.get("tool_return", "")
                try:
                    # Parse the tool return (Python repr format)
                    import ast
                    result = ast.literal_eval(ret)
                    return result
                except (ValueError, SyntaxError):
                    return {"status": "unknown", "raw": ret[:200]}

        return {"status": "no_tool_return", "raw": str(data)[:200]}

    except urllib.error.URLError as e:
        return {"status": "error", "error_message": str(e)}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Backfill analytics history")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Calendar days to look back (default: {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_SECONDS,
                        help=f"Seconds between API calls (default: {DEFAULT_DELAY_SECONDS})")
    parser.add_argument("--dry-run", action="store_true", help="Show dates without collecting")
    args = parser.parse_args()

    # Determine date range
    today = datetime.now()
    if args.end:
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end_date = today - timedelta(days=1)
        # Skip back to last workday
        while end_date.weekday() >= 5:
            end_date -= timedelta(days=1)

    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = today - timedelta(days=args.days)

    workdays = list(get_workdays(start_date, end_date))

    print(f"{'=' * 60}")
    print(f"Analytics History Backfill")
    print(f"{'=' * 60}")
    print(f"Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Workdays to process: {len(workdays)}")
    print(f"Delay between calls: {args.delay}s")
    print(f"Estimated time: ~{len(workdays) * (args.delay + 75) // 60} minutes")
    print(f"Letta agent: {PULSE_MONITOR_ID}")
    print()

    if args.dry_run:
        print("DRY RUN — dates that would be collected:")
        for d in workdays:
            print(f"  {d.strftime('%Y-%m-%d')} ({d.strftime('%A')})")
        print(f"\nTotal: {len(workdays)} workdays")
        return 0

    # Verify Letta is reachable
    try:
        health_req = urllib.request.Request(f"{LETTA_BASE_URL}/v1/health")
        with urllib.request.urlopen(health_req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"ERROR: Cannot reach Letta at {LETTA_BASE_URL}: {e}")
        return 1

    # Process each workday
    success_count = 0
    partial_count = 0
    error_count = 0
    results_log = []

    for i, workday in enumerate(workdays, 1):
        date_str = workday.strftime("%Y-%m-%d")
        day_name = workday.strftime("%a")
        print(f"[{i}/{len(workdays)}] {date_str} ({day_name})... ", end="", flush=True)

        result = collect_for_date(date_str)
        status = result.get("status", "unknown")

        if status == "ok":
            summary = result.get("summary", {})
            drive = summary.get("drive_activities", 0)
            email = summary.get("email_total", 0)
            slack = summary.get("slack_messages", 0)
            print(f"OK (drive={drive}, email={email}, slack={slack})")
            success_count += 1
        elif status == "partial":
            errors = result.get("errors", [])
            summary = result.get("summary", {})
            drive = summary.get("drive_activities", 0)
            email = summary.get("email_total", 0)
            print(f"PARTIAL (drive={drive}, email={email}) — {'; '.join(errors)[:100]}")
            partial_count += 1
        else:
            error_msg = result.get("error_message", result.get("raw", "unknown"))
            print(f"ERROR: {str(error_msg)[:100]}")
            error_count += 1

        results_log.append({"date": date_str, "status": status, "result": result})

        # Delay between calls (skip after last)
        if i < len(workdays):
            time.sleep(args.delay)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Backfill Complete")
    print(f"{'=' * 60}")
    print(f"Success: {success_count}")
    print(f"Partial: {partial_count}")
    print(f"Errors:  {error_count}")
    print(f"Total:   {len(workdays)}")

    if error_count > 0:
        print(f"\nFailed dates:")
        for entry in results_log:
            if entry["status"] not in ("ok", "partial"):
                print(f"  {entry['date']}: {entry['result'].get('error_message', 'unknown')[:100]}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
