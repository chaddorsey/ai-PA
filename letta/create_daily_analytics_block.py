#!/usr/bin/env python3
"""
Create and attach the daily_analytics_briefing memory block to Pulse Monitor.

Usage:
  LETTA_BASE_URL=http://localhost:8283 python letta/create_daily_analytics_block.py
"""

import json
import os
import sys
import urllib.request

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
PULSE_MONITOR_ID = os.getenv(
    "LETTA_AGENT_ID",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
)

BLOCK_LABEL = "daily_analytics_briefing"
BLOCK_DESCRIPTION = (
    "Most recent daily analytics briefing. Updated each morning by "
    "compose_daily_briefing(). Contains Drive, Email, and Slack metrics "
    "with trend comparisons. Replaced daily — only the latest briefing is stored here."
)
INITIAL_VALUE = "(No briefing generated yet. Run compose_daily_briefing() to populate.)"


def main():
    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {PULSE_MONITOR_ID}\n")

    # Check if block already exists
    req = urllib.request.Request(
        f"{LETTA_BASE}/v1/blocks/?label={BLOCK_LABEL}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        existing = json.loads(resp.read().decode("utf-8"))

    if existing:
        block_id = existing[0].get("id")
        print(f"Block already exists: {block_id}")
    else:
        payload = json.dumps({
            "label": BLOCK_LABEL,
            "value": INITIAL_VALUE,
            "description": BLOCK_DESCRIPTION,
            "limit": 5000,
        }).encode("utf-8")
        create_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/blocks/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            block_id = result.get("id")
            print(f"Created block: {block_id}")

    # Attach to agent
    try:
        attach_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/agents/{PULSE_MONITOR_ID}/core-memory/blocks/attach/{block_id}",
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(attach_req, timeout=10)
        print(f"Attached to agent {PULSE_MONITOR_ID}")
    except Exception as e:
        err_str = str(e).lower()
        if "already" in err_str or "409" in err_str:
            print("Already attached to agent")
        else:
            print(f"Attach failed: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
