#!/usr/bin/env python3
"""
Register scheduled jobs for the curator-radar service.

Creates five cron jobs in scheduler-service:
  1. GitHub incremental star scan (weekly, Sunday 3am)
  2. GitHub curator event discovery (daily 6am)
  3. Twitter daily pipeline (daily 7am)
  4. Weekly digest delivery to Slack (Monday 8am)
  5. GitHub full rescore (weekly, Sunday 5am)

Run once to set up:
    python3 scripts/create-curator-radar-jobs.py
"""

import json
import sys

import requests

SCHEDULER_BASE_URL = "http://localhost:8087/v1"
CURATOR_RADAR_BASE = "http://curator-radar:5145/v1"
CATEGORY = "curator_radar"

JOBS = [
    {
        "title": "Curator Radar: GitHub Star Scan (Weekly)",
        "description": "Scan for new GitHub stars added in the past 7 days, fetch stargazers, and rescore.",
        "created_by": "system",
        "category": CATEGORY,
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 3 * * 0"},  # Sunday 3am
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "method": "POST",
                    "url": f"{CURATOR_RADAR_BASE}/backfill?since_days=7",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 600,
                    "retries": 1,
                },
            }
        ],
    },
    {
        "title": "Curator Radar: Stargazer Refresh (Weekly)",
        "description": "Check for changed star counts on existing repos, fetch new stargazers, and rescore.",
        "created_by": "system",
        "category": CATEGORY,
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 5 * * 0"},  # Sunday 5am (after backfill)
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "method": "POST",
                    "url": f"{CURATOR_RADAR_BASE}/stargazers/refresh",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 600,
                    "retries": 1,
                },
            }
        ],
    },
    {
        "title": "Curator Radar: GitHub Discovery (Daily)",
        "description": "Refresh public events from top GitHub curators to discover new repos.",
        "created_by": "system",
        "category": CATEGORY,
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 6 * * *"},  # Daily 6am
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "method": "POST",
                    "url": f"{CURATOR_RADAR_BASE}/monitor/refresh",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 300,
                    "retries": 2,
                },
            }
        ],
    },
    {
        "title": "Curator Radar: Twitter Daily Pipeline",
        "description": "Ingest new bookmarks, fetch retweeters, score, and sync Twitter list.",
        "created_by": "system",
        "category": CATEGORY,
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 7 * * *"},  # Daily 7am
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "method": "POST",
                    "url": f"{CURATOR_RADAR_BASE}/twitter/run",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 600,
                    "retries": 1,
                },
            }
        ],
    },
    {
        "title": "Curator Radar: Weekly Digest to Slack",
        "description": "Generate and deliver the weekly curator digest to Slack.",
        "created_by": "system",
        "category": CATEGORY,
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 8 * * 1"},  # Monday 8am
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "method": "POST",
                    "url": f"{CURATOR_RADAR_BASE}/digest/deliver?since_days=7",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 120,
                    "retries": 2,
                },
            }
        ],
    },
]


def main():
    # Check for existing jobs
    existing_titles = set()
    try:
        resp = requests.get(
            f"{SCHEDULER_BASE_URL}/jobs",
            params={"category_filter": CATEGORY},
            timeout=30,
        )
        resp.raise_for_status()
        existing = resp.json()
        if isinstance(existing, list):
            for job in existing:
                existing_titles.add(job.get("title"))
                print(f"  Existing: {job.get('title')} ({job['job_id']}, {job.get('status', '?')})")
    except Exception as e:
        print(f"Warning: Could not check existing jobs: {e}")

    created = 0
    skipped = 0

    for job_def in JOBS:
        title = job_def["title"]
        if title in existing_titles:
            print(f"  SKIP: {title} (already exists)")
            skipped += 1
            continue

        try:
            resp = requests.post(
                f"{SCHEDULER_BASE_URL}/jobs",
                json=job_def,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            job_id = result.get("job_id", "unknown")
            cron = job_def["schedule"]["expression"]["cron"]
            print(f"  CREATED: {title} ({job_id}) — cron: {cron}")
            created += 1
        except requests.exceptions.ConnectionError:
            print(f"Error: Cannot connect to scheduler at {SCHEDULER_BASE_URL}")
            print("Is the scheduler-service running?")
            return 1
        except Exception as e:
            print(f"  ERROR: {title}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  Response: {e.response.text}")

    print(f"\nDone: {created} created, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
