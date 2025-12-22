#!/usr/bin/env python3
"""
List all scheduled jobs from the scheduler service.
"""

import sys
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional

SCHEDULER_BASE_URL = "http://localhost:8087/v1"

def list_jobs(status_filter: Optional[str] = None) -> List[Dict]:
    """List jobs from scheduler service."""
    url = f"{SCHEDULER_BASE_URL}/jobs"
    params = {}
    if status_filter:
        params["status_filter"] = status_filter
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return []

def format_job(job: Dict) -> str:
    """Format a job for display."""
    job_id = job.get("job_id", "unknown")
    title = job.get("title", "Untitled")
    status = job.get("status", "unknown")
    next_run = job.get("next_run_at", "N/A")
    schedule_type = job.get("schedule_type", "N/A")
    category = job.get("category", "")
    created_by = job.get("created_by", "")
    
    # Format next_run timestamp if present
    if next_run and next_run != "N/A":
        try:
            dt = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
            next_run = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except:
            pass
    
    result = f"  Title: {title}\n"
    result += f"  ID: {job_id}\n"
    result += f"  Status: {status}\n"
    result += f"  Schedule: {schedule_type}\n"
    result += f"  Next Run: {next_run}\n"
    if category:
        result += f"  Category: {category}\n"
    if created_by:
        result += f"  Created By: {created_by}\n"
    
    return result

def main():
    print("=" * 70)
    print("📅 Scheduled Jobs")
    print("=" * 70)
    print()
    
    # Get all jobs (excluding archived by default)
    jobs = list_jobs()
    
    if not jobs:
        print("No jobs found")
        return
    
    # Filter to scheduled/active jobs
    scheduled = [j for j in jobs if j.get("status") in ["scheduled", "active"]]
    other = [j for j in jobs if j.get("status") not in ["scheduled", "active"]]
    
    print(f"Total jobs: {len(jobs)}")
    print(f"  - Scheduled/Active: {len(scheduled)}")
    print(f"  - Other status: {len(other)}")
    print()
    
    if scheduled:
        print("📋 Scheduled/Active Jobs:")
        print("-" * 70)
        for i, job in enumerate(scheduled, 1):
            print(f"{i}.")
            print(format_job(job))
            if i < len(scheduled):
                print()
    
    if other and len(other) <= 10:
        print("\n📋 Other Jobs:")
        print("-" * 70)
        for i, job in enumerate(other, 1):
            print(f"{i}. {job.get('title', 'Untitled')} - {job.get('status')}")
    
    if len(other) > 10:
        print(f"\n... and {len(other)} other job(s) with different statuses")

if __name__ == "__main__":
    main()

