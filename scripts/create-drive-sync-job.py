#!/usr/bin/env python3
"""
Create a scheduled job for Drive RAG sync via the Changes API.

This creates a recurring 10-minute job in the scheduler-service that
calls POST /v1/sync/changes on drive-rag-service. The sync endpoint
detects new, modified, and deleted files and auto-triggers re-ingestion.

Run once to set up:
    python3 scripts/create-drive-sync-job.py
"""

import json
import sys

import requests

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
JOB_TITLE = "Drive RAG Sync (Changes API)"

JOB = {
    "title": JOB_TITLE,
    "description": "Sync Google Drive changes every 10 minutes via Changes API. Auto-ingests changed documents.",
    "created_by": "system",
    "category": "drive_rag",
    "schedule": {
        "type": "cron",
        "expression": {"cron": "*/10 * * * *"},
    },
    "actions": [
        {
            "action_type": "http",
            "config": {
                "method": "POST",
                "url": "http://drive-rag-service:8000/v1/sync/changes",
                "headers": {"Content-Type": "application/json"},
                "timeout": 120,
                "retries": 2,
            },
        }
    ],
}


def main():
    # Check for existing job with same title
    try:
        resp = requests.get(
            f"{SCHEDULER_BASE_URL}/jobs",
            params={"category_filter": "drive_rag"},
            timeout=30,
        )
        resp.raise_for_status()
        existing = resp.json()
        if isinstance(existing, list):
            for job in existing:
                if job.get("title") == JOB_TITLE:
                    print(f"Job already exists: {job['job_id']} (status: {job.get('status', 'unknown')})")
                    print("Delete it first if you want to recreate.")
                    return 0
    except Exception as e:
        print(f"Warning: Could not check for existing jobs: {e}")

    # Create the job
    try:
        resp = requests.post(
            f"{SCHEDULER_BASE_URL}/jobs",
            json=JOB,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"Created job: {result.get('job_id', 'unknown')}")
        print(f"Title: {result.get('title', JOB_TITLE)}")
        print(f"Schedule: every 10 minutes")
        print(f"Target: POST http://drive-rag-service:8000/v1/sync/changes")
        return 0
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to scheduler at {SCHEDULER_BASE_URL}")
        print("Is the scheduler-service running?")
        return 1
    except Exception as e:
        print(f"Error creating job: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
