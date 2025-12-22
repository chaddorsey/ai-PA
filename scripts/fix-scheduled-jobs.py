#!/usr/bin/env python3
"""
Fix scheduled jobs by recalculating next_run_at from cron expressions.

This script updates the next_run_at field for all scheduled jobs based on their
cron expressions, ensuring they're properly scheduled.
"""

import sys
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
DEFAULT_TIMEZONE = "America/New_York"

def get_jobs(status_filter: str = "scheduled") -> list:
    """Get jobs from scheduler service."""
    url = f"{SCHEDULER_BASE_URL}/jobs"
    params = {"status_filter": status_filter}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR fetching jobs: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return []

def calculate_next_cron_run(cron_expr: str, timezone_str: str = DEFAULT_TIMEZONE) -> str:
    """Calculate next run time for cron expression."""
    try:
        from apscheduler.triggers.cron import CronTrigger
        
        tz = ZoneInfo(timezone_str)
        trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
        now = datetime.now(tz)
        next_run = trigger.get_next_fire_time(None, now)
        
        if next_run:
            return next_run.astimezone(ZoneInfo("UTC")).isoformat()
        else:
            # Fallback: use current time + 1 day
            return (datetime.now(ZoneInfo("UTC")) + timedelta(days=1)).isoformat()
    except ImportError:
        # Fallback calculation if apscheduler not available
        print("⚠️  Warning: apscheduler not available, using fallback calculation")
        from datetime import timedelta
        return (datetime.now(ZoneInfo("UTC")) + timedelta(days=1)).isoformat()
    except Exception as e:
        print(f"⚠️  Error calculating next run: {e}")
        from datetime import timedelta
        return (datetime.now(ZoneInfo("UTC")) + timedelta(days=1)).isoformat()

def update_job_next_run(job_id: str, next_run_at: str) -> bool:
    """Update a job's next_run_at via PATCH."""
    url = f"{SCHEDULER_BASE_URL}/jobs/{job_id}"
    
    # Get current job to preserve other fields
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        job = response.json()
    except Exception as e:
        print(f"   ❌ Failed to get job: {e}")
        return False
    
    # Update only the schedule to trigger next_run_at recalculation
    schedule = job.get("schedule_expression", {})
    schedule_type = job.get("schedule_type")
    
    payload = {
        "schedule": {
            "type": schedule_type,
            "expression": schedule,
            "next_run_at": next_run_at
        }
    }
    
    try:
        response = requests.patch(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Failed to update: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"      Response: {e.response.text}")
        return False

def main():
    print("=" * 70)
    print("🔧 Fix Scheduled Jobs - Recalculate next_run_at")
    print("=" * 70)
    print()
    
    # Get all scheduled jobs
    jobs = get_jobs("scheduled")
    
    if not jobs:
        print("No scheduled jobs found")
        return
    
    print(f"Found {len(jobs)} scheduled job(s)\n")
    
    # Filter to jobs that need fixing (cron jobs with past or missing next_run_at)
    now_utc = datetime.now(ZoneInfo("UTC"))
    jobs_to_fix = []
    
    for job in jobs:
        job_id = job.get("job_id")
        title = job.get("title", "Untitled")
        schedule_type = job.get("schedule_type")
        next_run_at = job.get("next_run_at")
        
        if schedule_type == "cron":
            schedule_expr = job.get("schedule_expression", {})
            cron_expr = schedule_expr.get("cron")
            
            if cron_expr:
                # Check if next_run_at is in the past or missing
                needs_fix = False
                if not next_run_at:
                    needs_fix = True
                    reason = "missing next_run_at"
                else:
                    try:
                        next_run_dt = datetime.fromisoformat(next_run_at.replace('Z', '+00:00'))
                        if next_run_dt < now_utc:
                            needs_fix = True
                            reason = f"next_run_at is in the past ({next_run_at})"
                    except:
                        needs_fix = True
                        reason = "invalid next_run_at format"
                
                if needs_fix:
                    jobs_to_fix.append({
                        "job_id": job_id,
                        "title": title,
                        "cron": cron_expr,
                        "reason": reason
                    })
    
    if not jobs_to_fix:
        print("✅ All scheduled jobs have valid next_run_at times")
        return
    
    print(f"Found {len(jobs_to_fix)} job(s) that need fixing:\n")
    for i, job in enumerate(jobs_to_fix, 1):
        print(f"{i}. {job['title']}")
        print(f"   ID: {job['job_id']}")
        print(f"   Cron: {job['cron']}")
        print(f"   Issue: {job['reason']}")
        print()
    
    # Fix each job
    print("🔧 Fixing jobs...\n")
    fixed = 0
    failed = 0
    
    for job in jobs_to_fix:
        print(f"Fixing: {job['title']}")
        
        # Calculate next run time
        next_run_at = calculate_next_cron_run(job['cron'])
        print(f"  Calculated next_run_at: {next_run_at}")
        
        # Update job
        if update_job_next_run(job['job_id'], next_run_at):
            print(f"  ✅ Updated successfully")
            fixed += 1
        else:
            print(f"  ❌ Failed to update")
            failed += 1
        print()
    
    print("=" * 70)
    print(f"✅ Fixed: {fixed}")
    if failed > 0:
        print(f"❌ Failed: {failed}")
    print("=" * 70)
    
    if fixed > 0:
        print("\n💡 Note: The scheduler service should automatically refresh these jobs.")
        print("   If jobs still don't run, try restarting the scheduler service:")
        print("   docker compose restart scheduler-service")

if __name__ == "__main__":
    main()

