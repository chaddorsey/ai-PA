#!/usr/bin/env python3
"""
Create scheduler jobs for the daily analytics briefing pipeline.

Pipeline (all times ET, cron in UTC):
  1. 2:00 AM ET (07:00 UTC) Mon-Fri: Trigger Slack CSV export
  2. 2:30 AM ET (07:30 UTC) Mon-Fri: Collect quantitative snapshot
  3. 3:00 AM ET (08:00 UTC) Mon-Fri: Slack vibe-check heartbeat
  4. 6:00 AM ET (11:00 UTC) Mon-Fri: Compose morning briefing

Usage:
  python scripts/create-analytics-pipeline-jobs.py
"""

import json
import sys
import requests

SCHEDULER_URL = "http://localhost:8087/v1"
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

JOBS = [
    {
        "title": "Daily Analytics: Slack CSV Export Trigger",
        "description": "Trigger Slack analytics CSV export (channels + members). CSV covers 2-3 days ago due to Slack delay.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 7 * * 1-5"},
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Trigger Slack analytics CSV export for channels and members. Use trigger_slack_analytics_export(analytics_type='all'). Report the result.",
            },
        }],
    },
    {
        "title": "Daily Analytics: Quantitative Snapshot",
        "description": "Collect Drive/Email/Slack metrics and persist to analytics.daily_snapshots database.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "30 7 * * 1-5"},
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Collect the daily analytics snapshot using collect_analytics_snapshot(). This captures Drive, Email, and Slack quantitative metrics and persists them to the analytics database. Report the summary and any errors.",
            },
        }],
    },
    {
        "title": "Daily Analytics: Slack Vibe Check",
        "description": "Generate qualitative Slack channel summaries and write to archival memory for briefing assembly.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 8 * * 1-5"},
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": (
                    "Generate the daily Slack vibe check for yesterday across the top channels. "
                    "After summarizing each channel, write the summary to archival memory tagged "
                    "`daily_vibe_check` with today's date in YYYY-MM-DD format. "
                    "When all channels are done, write a combined summary to archival memory with "
                    "the same tag. Do NOT rely on conversation context to preserve these — the "
                    "compose step will read them from archival memory."
                ),
            },
        }],
    },
    {
        "title": "Daily Analytics: Compose Morning Briefing",
        "description": "Assemble final briefing from DB snapshot + archival vibe check. Writes to memory block + markdown.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 11 * * 1-5"},
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Compose the daily analytics briefing using compose_daily_briefing(). This reads from the analytics database and archival memory, computes trend comparisons, and writes the briefing to both the daily_analytics_briefing memory block and the markdown archive. Share the briefing text with me.",
            },
        }],
    },
]


def main():
    print(f"Scheduler: {SCHEDULER_URL}")
    print(f"Agent: {PULSE_MONITOR_ID}\n")

    for job in JOBS:
        print(f"Creating: {job['title']}")
        try:
            resp = requests.post(f"{SCHEDULER_URL}/jobs", json=job, timeout=30)
            if resp.status_code in (200, 201):
                data = resp.json()
                job_id = data.get("job_id", "?")
                next_run = data.get("next_run_at", "?")
                print(f"  Created: {job_id}")
                print(f"  Next run: {next_run}")
            else:
                print(f"  Failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")
        print()

    print("Done. Verify with:")
    print(f"  curl -s {SCHEDULER_URL}/jobs?category=analytics_pipeline | python3 -c \"import sys,json; [print(j['title']) for j in json.load(sys.stdin)]\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
