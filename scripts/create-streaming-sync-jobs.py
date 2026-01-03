#!/usr/bin/env python3
"""
Create scheduled jobs for streaming data synchronization.
"""

import json
import requests
import sys
from typing import Dict, Any

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
AGENT_ID = "agent-a9f2c740-663c-4414-a553-47115180e49b"

JOBS = [
    {
        "title": "Full Streaming Data Sync",
        "description": "Comprehensive sync of watch history, watchlists, and recommendations from all streaming services",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 3 * * *"}
        },
        "category": "streaming_sync",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run sync_all_streaming_data for user chad with include_recommendations=true. Log the date and time and total items synced from each service to the streaming_sync_status memory block and log any errors or issues to the streaming_sync_errors_and_issues memory block."
            }
        }]
    },
    {
        "title": "Watch History Poll",
        "description": "Sync Continue Watching data from all streaming services every 6 hours",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 0,6,12,18 * * *"}
        },
        "category": "streaming_sync",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run poll_watch_history for user chad. Update the date and time and total items found from each service in the streaming_sync_status memory block and log any errors or issues to the streaming_sync_errors_and_issues memory block."
            }
        }]
    },
    {
        "title": "Watchlists Poll",
        "description": "Sync My List / Watchlist items from all streaming services",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 2,14 * * *"}
        },
        "category": "streaming_sync",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run poll_watchlists for user chad. Update the streaming_sync_status memory block to note the date and time and how many watchlist items were found for each service."
            }
        }]
    },
    {
        "title": "Recommendations Poll",
        "description": "Sync personalized recommendations from all streaming services",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 4 * * *"}
        },
        "category": "streaming_sync",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run poll_recommendations for user chad. Update the streaming_sync_status memory block with information on how many recommendations were found for each service."
            }
        }]
    },
    {
        "title": "Credential Health Check",
        "description": "Verify that all streaming service credentials are still valid and add notes about any that need re-authentication to the streaming_sync_errors_and_issues memory block.",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 5 * * *"}
        },
        "category": "maintenance",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run check_credential_status and log which streaming services have valid credentials and which need re-authentication to the streaming_sync_errors_and_issues memory block."
            }
        }]
    },
    {
        "title": "TV Listings Refresh",
        "description": "Trigger refresh of TV guide listings data to ensure cache is current",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 1,5,9,13,17,21 * * *"}
        },
        "category": "tv_guide",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Call get_tv_listings_now with sports_only=false to refresh TV listings data."
            }
        }]
    }
]


def create_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a job via the scheduler API."""
    url = f"{SCHEDULER_BASE_URL}/jobs"
    
    # Add created_by field
    job_data["created_by"] = AGENT_ID
    
    try:
        response = requests.post(url, json=job_data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR creating job '{job_data['title']}': {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def main():
    print("=" * 70)
    print("Creating Streaming Sync Scheduled Jobs")
    print("=" * 70)
    print()
    
    created_jobs = []
    failed_jobs = []
    
    for job_data in JOBS:
        title = job_data["title"]
        print(f"Creating: {title}...", end=" ")
        
        try:
            result = create_job(job_data)
            job_id = result.get("job_id", "unknown")
            next_run = result.get("next_run_at", "N/A")
            created_jobs.append({"title": title, "job_id": job_id, "next_run_at": next_run})
            print(f"✓ (ID: {job_id})")
        except Exception as e:
            failed_jobs.append({"title": title, "error": str(e)})
            print(f"✗ Failed: {e}")
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Successfully created: {len(created_jobs)}/{len(JOBS)}")
    print(f"Failed: {len(failed_jobs)}")
    print()
    
    if created_jobs:
        print("Created Jobs:")
        for job in created_jobs:
            print(f"  - {job['title']}")
            print(f"    ID: {job['job_id']}")
            print(f"    Next Run: {job['next_run_at']}")
            print()
    
    if failed_jobs:
        print("Failed Jobs:")
        for job in failed_jobs:
            print(f"  - {job['title']}: {job['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

