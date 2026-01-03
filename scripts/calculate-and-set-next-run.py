#!/usr/bin/env python3
"""
Calculate next_run_at for cron jobs and update them.
Uses manual calculation for common cron patterns.
"""

import requests
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
TIMEZONE_STR = "America/New_York"

def calculate_next_run_for_cron(cron_expr: str, tz_str: str) -> datetime:
    """
    Calculate next run time for a cron expression.
    Handles common patterns manually.
    """
    tz = ZoneInfo(tz_str)
    now = datetime.now(tz)
    
    # Parse cron: minute hour day month weekday
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron format: {cron_expr}")
    
    minute_str, hour_str, day_str, month_str, weekday_str = parts
    
    # Handle minute
    if minute_str == "*":
        candidate_minute = now.minute
    elif "," in minute_str:
        # Multiple minutes (e.g., "0,30")
        minutes = [int(m) for m in minute_str.split(",")]
        candidate_minute = min([m for m in minutes if m >= now.minute] or minutes)
    else:
        candidate_minute = int(minute_str)
    
    # Handle hour
    if hour_str == "*":
        candidate_hour = now.hour
    elif "," in hour_str:
        # Multiple hours (e.g., "0,6,12,18")
        hours = sorted([int(h) for h in hour_str.split(",")])
        # Find next hour >= current hour
        next_hours = [h for h in hours if h >= now.hour] or hours
        candidate_hour = next_hours[0]
        # If using a later hour, reset minute to first in the list
        if candidate_hour > now.hour:
            candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
    else:
        candidate_hour = int(hour_str)
        # If hour is in the future, use first minute from the minute field
        if candidate_hour > now.hour:
            candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
        elif candidate_hour == now.hour and candidate_minute <= now.minute:
            # This hour has passed, move to next occurrence
            if "," in hour_str:
                hours = sorted([int(h) for h in hour_str.split(",")])
                next_hours = [h for h in hours if h > now.hour] or hours
                candidate_hour = next_hours[0] if next_hours[0] != now.hour else hours[(hours.index(now.hour) + 1) % len(hours)]
                candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
            else:
                # Single hour, move to tomorrow
                candidate_hour = int(hour_str)
                candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
                return (now.replace(hour=candidate_hour, minute=candidate_minute, second=0, microsecond=0) + timedelta(days=1)).astimezone(ZoneInfo("UTC"))
    
    # Handle day and weekday (simplified - assumes "*" for now)
    # For our use case, most are daily patterns
    
    # Build candidate datetime
    try:
        candidate = now.replace(hour=candidate_hour, minute=candidate_minute, second=0, microsecond=0)
        
        # If the time has passed today, move to next occurrence
        if candidate <= now:
            if "," in hour_str:
                # Multiple hours per day - try next hour
                hours = sorted([int(h) for h in hour_str.split(",")])
                current_idx = hours.index(candidate_hour) if candidate_hour in hours else 0
                if current_idx < len(hours) - 1:
                    candidate_hour = hours[current_idx + 1]
                    candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
                    candidate = now.replace(hour=candidate_hour, minute=candidate_minute, second=0, microsecond=0)
                else:
                    # Last hour of the day, move to tomorrow
                    candidate = candidate + timedelta(days=1)
                    candidate_hour = hours[0]
                    candidate_minute = int(minute_str.split(",")[0]) if "," in minute_str else int(minute_str)
                    candidate = candidate.replace(hour=candidate_hour, minute=candidate_minute)
            else:
                # Single hour, move to tomorrow
                candidate = candidate + timedelta(days=1)
    except ValueError:
        # Invalid date (e.g., Feb 30), move to next month
        candidate = (candidate + timedelta(days=32)).replace(day=1)
    
    return candidate.astimezone(ZoneInfo("UTC"))


def update_job_next_run(job_id: str, schedule_type: str, schedule_expr: dict, next_run_at: datetime) -> bool:
    """Update job's schedule including next_run_at via PATCH."""
    url = f"{SCHEDULER_BASE_URL}/jobs/{job_id}"
    
    payload = {
        "schedule": {
            "type": schedule_type,
            "expression": schedule_expr,
            "next_run_at": next_run_at.isoformat()
        }
    }
    
    try:
        response = requests.patch(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"   Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False


def main():
    print("=" * 70)
    print("Calculating and Setting next_run_at for Streaming Sync Jobs")
    print("=" * 70)
    print()
    
    # Get all jobs created by the agent
    url = f"{SCHEDULER_BASE_URL}/jobs"
    params = {"created_by_filter": "agent-a9f2c740-663c-4414-a553-47115180e49b"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        jobs = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR fetching jobs: {e}")
        sys.exit(1)
    
    updated = 0
    failed = 0
    skipped = 0
    
    for job in jobs:
        job_id = job.get("job_id")
        title = job.get("title")
        schedule_type = job.get("schedule_type")
        schedule_expr = job.get("schedule_expression", {})
        current_next_run = job.get("next_run_at")
        
        if current_next_run:
            print(f"✓ {title}: already has next_run_at")
            skipped += 1
            continue
        
        if schedule_type != "cron":
            print(f"⊘ {title}: skipping (type: {schedule_type})")
            skipped += 1
            continue
        
        cron_expr = schedule_expr.get("cron")
        if not cron_expr:
            print(f"⚠ {title}: no cron expression")
            skipped += 1
            continue
        
        print(f"Calculating for {title} (cron: {cron_expr})...", end=" ")
        
        try:
            next_run_at = calculate_next_run_for_cron(cron_expr, TIMEZONE_STR)
            next_run_str = next_run_at.isoformat()
            
            if update_job_next_run(job_id, schedule_type, schedule_expr, next_run_at):
                updated += 1
                print(f"✓ (next_run_at: {next_run_str})")
            else:
                failed += 1
                print("✗")
        except Exception as e:
            failed += 1
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 70)
    print(f"Updated: {updated}, Skipped: {skipped}, Failed: {failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()

