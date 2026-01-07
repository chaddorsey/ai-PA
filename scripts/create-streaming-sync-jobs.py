#!/usr/bin/env python3
"""
Create scheduled jobs for streaming data synchronization, series monitoring,
and session maintenance.

Jobs include:
- Streaming sync (watch history, watchlists, recommendations)
- Series monitoring (tracked series sync, new seasons check)
- Session maintenance (refresh sessions, clean browser states)
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
    },
    # Series monitoring jobs
    {
        "title": "Sync All Active Tracked Series",
        "description": "Sync episode-level watch progress for all series with tracking_status='watching'",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "30 4 * * *"}
        },
        "category": "series_monitoring",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run sync_all_active_series() for user chad. Log any changes or completions to the tracked_series memory block and the sync results including count of series synced and any errors to streaming_sync_status memory block. If any errors occur, log details to streaming_sync_errors_and_issues memory block."
            }
        }]
    },
    {
        "title": "Reconcile Watchlist Tracking",
        "description": "Auto-add series from streaming service watchlists to tracked_series",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "30 2 * * *"}
        },
        "category": "series_monitoring",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run reconcile_watchlist_tracking() for user chad. Update the tracked_series memory block with any additions or changes and log how many new series were auto-tracked from watchlists to streaming_sync_status memory block."
            }
        }]
    },
    {
        "title": "Check for New Seasons",
        "description": "Check JustWatch for new season availability on tracked series",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 5 * * 0"}
        },
        "category": "series_monitoring",
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": AGENT_ID,
                "message": "Run check_new_seasons() for user chad. If any new seasons are found, log them to streaming_sync_status memory block with the series name and new season number."
            }
        }]
    },
    # Session maintenance jobs
    {
        "title": "Refresh Streaming Sessions",
        "description": "Proactively refresh streaming service sessions before they expire",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 1 * * 0,3"}
        },
        "category": "session_maintenance",
        "actions": [{
            "action_type": "http",
            "config": {
                "url": "http://watch-history-service:5127/sessions/refresh-due",
                "method": "POST",
                "headers": {},
                "body": {},
                "timeout_seconds": 300
            }
        }]
    },
    {
        "title": "Clean Browser State Files",
        "description": "Weekly cleanup of browser state files to remove bloated localStorage data",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "30 0 * * 0"}
        },
        "category": "session_maintenance",
        "actions": [{
            "action_type": "http",
            "config": {
                "url": "http://watch-history-service:5127/sessions/cleanup-states",
                "method": "POST",
                "headers": {},
                "body": {},
                "timeout_seconds": 60
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

