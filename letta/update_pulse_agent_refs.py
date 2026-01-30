#!/usr/bin/env python3
"""
Update Pulse Agent Persona with REFS Instructions

Adds REFS line instructions to the Pulse Agent for actionable
reference tracking across multiple domains: Jira, Confluence,
Google Drive, and Slack.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

PULSE_AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

# REFS instruction - multi-domain format with type field
REFS_INSTRUCTION = """

## REFS Line (for follow-up actions)

After SUMMARY, add REFS when identifying specific resources. Include type field:

Jira: REFS: {"type": "jira", "issueKey": "PROJ-123", "summary": "..."}
Confluence: REFS: {"type": "confluence", "pageId": "123", "title": "...", "space": "ENG"}
Drive: REFS: {"type": "drive", "documentId": "1abc...", "title": "..."}
Slack user: REFS: {"type": "slack_user", "userId": "U123", "username": "jsmith"}
Slack msg: REFS: {"type": "slack_msg", "channel": "C123", "ts": "1704912345.123", "text": "..."}

Rules: Include type + primary ID + human-readable field. Skip for analytics/aggregates.
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
    print("Update Pulse Agent with REFS Instructions")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Pulse Agent ID: {PULSE_AGENT_ID}")
    print()

    # Get agent's memory blocks
    print("Fetching agent memory blocks...")
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{PULSE_AGENT_ID}/core-memory/blocks")
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
    if "REFS Line" in current_persona:
        print()
        print("Pulse agent already has REFS instructions!")
        return 0

    # Append REFS instruction
    new_persona = current_persona + REFS_INSTRUCTION

    print(f"New length: {len(new_persona)} chars")

    if len(new_persona) > 5000:
        print(f"ERROR: New persona exceeds 5000 char limit")
        return 1

    print()
    print("Updating persona block...")

    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print("SUCCESS: Pulse agent updated with REFS instructions!")
        print()
        print("The agent will now emit REFS lines like:")
        print('  REFS: {"type": "jira", "issueKey": "PROJ-123", "summary": "Bug fix"}')
        print('  REFS: {"type": "drive", "documentId": "1abc", "title": "Report"}')
        print('  REFS: {"type": "slack_msg", "channel": "C123", "ts": "170491...", "text": "..."}')
        return 0
    else:
        print("ERROR: Failed to update persona")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
