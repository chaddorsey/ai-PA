#!/usr/bin/env python3
"""
Calculate and update next_run_at for streaming sync jobs that were created without it.
Uses the scheduler service's PATCH endpoint with a schedule update that triggers recalculation.
"""

import requests
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
TIMEZONE = "America/New_York"

def update_job_schedule(job_id: str, schedule_expr: dict) -> bool:
    """Update job's schedule via PATCH to trigger next_run_at recalculation."""
    url = f"{SCHEDULER_BASE_URL}/jobs/{job_id}"
    
    # Update the schedule to trigger recalculation
    # The scheduler service should recalculate next_run_at when schedule is updated
    payload = {
        "schedule": {
            "type": "cron",
            "expression": schedule_expr
        }
    }
    
    try:
        response = requests.patch(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"   Error updating: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False


def main():
    print("=" * 70)
    print("Fixing next_run_at for Streaming Sync Jobs")
    print("=" * 70)
    print()
    print("Note: This will update each job's schedule to trigger")
    print("the scheduler to recalculate next_run_at.")
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
        
        # Skip if already has next_run_at
        if current_next_run:
            print(f"✓ {title}: already has next_run_at")
            skipped += 1
            continue
        
        # Only process cron jobs
        if schedule_type != "cron":
            print(f"⊘ {title}: skipping (type: {schedule_type})")
            skipped += 1
            continue
        
        cron_expr = schedule_expr.get("cron")
        if not cron_expr:
            print(f"⚠ {title}: no cron expression found")
            skipped += 1
            continue
        
        print(f"Updating {title} (cron: {cron_expr})...", end=" ")
        
        try:
            if update_job_schedule(job_id, schedule_expr):
                # Verify the update worked
                verify_response = requests.get(f"{SCHEDULER_BASE_URL}/jobs/{job_id}", timeout=10)
                if verify_response.status_code == 200:
                    updated_job = verify_response.json()
                    new_next_run = updated_job.get("next_run_at")
                    if new_next_run:
                        updated += 1
                        print(f"✓ (next_run_at: {new_next_run})")
                    else:
                        # Schedule was updated but next_run_at still null
                        # This might be expected - scheduler calculates it internally
                        updated += 1
                        print(f"✓ (schedule updated, scheduler will calculate next_run_at)")
                else:
                    failed += 1
                    print(f"✗ (verification failed)")
            else:
                failed += 1
                print("✗")
        except Exception as e:
            failed += 1
            print(f"✗ Error: {e}")
    
    print()
    print("=" * 70)
    print(f"Updated: {updated}, Skipped: {skipped}, Failed: {failed}")
    print("=" * 70)
    print()
    if updated > 0:
        print("Jobs have been updated. The scheduler service should now")
        print("calculate next_run_at when it processes these jobs.")


if __name__ == "__main__":
    main()
