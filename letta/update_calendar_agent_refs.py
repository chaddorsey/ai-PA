#!/usr/bin/env python3
"""
Update Calendar Agent Persona with REFS Instructions

Adds REFS line instructions to the Calendar Agent for actionable
reference tracking. When the agent creates, modifies, or queries
calendar events, it emits REFS with eventId, title, and start time
so follow-up requests can reference the event.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

CALENDAR_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"

# REFS instruction to append after SUMMARY instructions (kept concise for block limits)
REFS_INSTRUCTION = """

## REFS Line (for follow-up actions)

After SUMMARY, add REFS with event details when creating/modifying/finding events:
REFS: {"eventId": "...", "title": "...", "start": "ISO-8601"}

Example:
SUMMARY: Created standup for tomorrow #calendar
REFS: {"eventId": "abc123", "title": "Team Standup", "start": "2026-01-11T10:00:00"}

Rules: Include eventId (required for updates), title, start. Skip for general queries.
"""


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method='PATCH'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def main():
    print("=" * 60)
    print("Update Calendar Agent with REFS Instructions")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Calendar Agent ID: {CALENDAR_AGENT_ID}")
    print()

    # Get agent's memory blocks
    print("Fetching agent memory blocks...")
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{CALENDAR_AGENT_ID}/core-memory/blocks")
    if not blocks:
        print("ERROR: Could not get blocks for agent")
        return 1

    # Find persona block
    persona_block = None
    for block in blocks:
        if block.get("label") == "persona":
            persona_block = block
            break

    if not persona_block:
        print("ERROR: No persona block found")
        return 1

    current_persona = persona_block.get("value", "")
    block_id = persona_block.get("id")

    print(f"Found persona block: {block_id}")
    print(f"Current length: {len(current_persona)} chars")

    # Check if already has REFS instruction
    if "REFS Line" in current_persona or "REFS:" in current_persona and "eventId" in current_persona:
        print()
        print("Calendar agent already has REFS instructions!")
        print("Use --force to update anyway.")
        return 0

    # Append REFS instruction
    new_persona = current_persona + REFS_INSTRUCTION

    print(f"New length: {len(new_persona)} chars")
    print()
    print("Updating persona block...")

    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print("SUCCESS: Calendar agent updated with REFS instructions!")
        print()
        print("The agent will now emit REFS lines like:")
        print('  REFS: {"eventId": "abc123", "title": "Team Standup", "start": "2026-01-11T10:00:00"}')
        return 0
    else:
        print("ERROR: Failed to update persona")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
