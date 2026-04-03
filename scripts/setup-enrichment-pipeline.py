#!/usr/bin/env python3
"""
One-time setup for the enrichment pipeline:
1. Creates a dedicated Letta conversation for enrichment
2. Registers the scanner as a recurring scheduler job
3. Prints configuration values to add to .env

Usage:
    python3 scripts/setup-enrichment-pipeline.py

Idempotent — re-running detects existing conversation/job and reuses them.
"""

import json
import os
import sys
import urllib.request
import urllib.error

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
SCHEDULER_BASE = os.environ.get("SCHEDULER_URL", "http://localhost:8087/v1")
AGENT_ID = "agent-dd15479e-6543-400e-8463-b2a48b13cd4a"
ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"


def letta_request(method, path, data=None, timeout=15):
    """HTTP request to Letta API with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(
                loc, data=body,
                headers={"Content-Type": "application/json"} if body else {},
                method=method,
            )
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


def scheduler_request(method, path, data=None, timeout=30):
    """HTTP request to scheduler service."""
    url = f"{SCHEDULER_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def setup_conversation():
    """Create or find the enrichment conversation."""
    print("=== Step 1: Enrichment Conversation ===")

    # Check if conversation already exists
    try:
        convs = letta_request("GET", f"/v1/conversations/?agent_id={AGENT_ID}")
        if isinstance(convs, list):
            for c in convs:
                if c.get("label") == "enrichment-pipeline":
                    conv_id = c["id"]
                    print(f"  Found existing conversation: {conv_id}")
                    return conv_id
    except Exception:
        pass

    # Create new conversation
    conv = letta_request("POST", f"/v1/conversations/?agent_id={AGENT_ID}", {"label": "enrichment-pipeline"})
    conv_id = conv["id"]
    print(f"  Created conversation: {conv_id}")
    return conv_id


def setup_scanner_job(conv_id):
    """Register or find the enrichment scanner job."""
    print("\n=== Step 2: Scanner Job ===")

    # Check if job already exists
    try:
        jobs = scheduler_request("GET", "/jobs?category_filter=enrichment_pipeline")
        if isinstance(jobs, list):
            for j in jobs:
                if j.get("status") in ("scheduled", "paused"):
                    job_id = j["job_id"]
                    print(f"  Found existing job: {job_id} (status: {j['status']})")
                    return job_id
    except Exception:
        pass

    # Register new job
    job = scheduler_request("POST", "/jobs", {
        "title": "Enrichment Pipeline Scanner",
        "description": (
            "Scans archival for tasks needing enrichment (enrichment:none), "
            "dispatches focused messages to the enrichment conversation, "
            "and handles timeout recovery for stuck tasks."
        ),
        "created_by": "system",
        "category": "enrichment_pipeline",
        "schedule": {
            "type": "interval",
            "expression": {"seconds": 30},
        },
        "actions": [{
            "action_type": "script",
            "config": {
                "script": "enrichment-scanner.py",
                "env": {
                    "LETTA_BASE_URL": "http://letta:8283",
                    "TASKS_AGENT_ID": AGENT_ID,
                    "ENRICHMENT_CONV_ID": conv_id,
                    "ARCHIVE_ID": ARCHIVE_ID,
                },
            },
        }],
    })
    job_id = job["job_id"]
    print(f"  Created job: {job_id}")
    return job_id


def main():
    print("Enrichment Pipeline Setup\n")

    # Step 1: Create conversation
    conv_id = setup_conversation()

    # Step 2: Register scanner job
    job_id = setup_scanner_job(conv_id)

    # Step 3: Print configuration
    print("\n=== Configuration ===")
    print(f"  ENRICHMENT_CONV_ID={conv_id}")
    print(f"  Scanner job ID: {job_id}")
    print(f"\nAdd to .env:")
    print(f"  ENRICHMENT_CONV_ID={conv_id}")

    # Step 4: Remind about cron cleanup
    print(f"\n=== Cron Cleanup ===")
    print(f"  Remove from crontab:")
    print(f"    */2 * * * * /Users/dorseyhomeserver/bin/spark-queue-drain.sh ...")
    print(f"\n  Also fold spark queue checking into the scanner if desired.")

    print("\nSetup complete!")


if __name__ == "__main__":
    main()
