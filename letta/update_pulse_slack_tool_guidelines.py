#!/usr/bin/env python3
"""
Update Pulse Monitor's slack_tool_use_guidelines Block

Adds guidance about when to use get_slack_messages vs search_slack_messages
for comprehensive message retrieval vs content-based search.
"""

import os
import sys
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
PULSE_AGENT_ID = "agent-6eb765bf-7268-4f6d-a380-c527c9c53000"

# New section to add at the beginning
TOOL_SELECTION_GUIDANCE = """# Slack Tool Selection Guide

## When to Use Which Tool

| Goal | Best Tool | Why |
|------|-----------|-----|
| Retrieve ALL messages from a channel/DM | `get_slack_messages(channel=<id>)` | Uses conversations.history API - designed for complete retrieval |
| Search for messages by keyword/content | `search_slack_messages(query=...)` | Uses Slack's search index - optimized for finding specific content |
| Find channels/DMs | `get_slack_channels(types=...)` | Returns channel metadata and IDs |

## Key Distinction

- **get_slack_messages**: Complete retrieval from a specific conversation
  - Retrieves messages chronologically from a single channel
  - Guaranteed to return ALL messages (up to limit parameter)
  - Best for: "show me all DMs from Person X", "get recent #channel activity"

- **search_slack_messages**: Content-based search across workspace
  - Searches Slack's index (may not return everything)
  - Can search across multiple channels
  - Best for: "find messages mentioning X", "search for keyword Y"

## Comprehensive DM Review Workflow

For requests like "look through all of Person's DMs" or "review my conversation with Person":

1. **Get the DM channel ID**:
   ```python
   get_slack_channels(types="im")  # Returns all DM channels
   # Find the channel where members include the target user
   ```

2. **Retrieve all messages**:
   ```python
   get_slack_messages(
       channel="<dm_channel_id>",
       start_date="2026-01-15",
       limit=500  # Adjust as needed
   )
   ```

**Don't use** `search_slack_messages` with `is_dm=true` for comprehensive retrieval - it may miss messages.

---

"""


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
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
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Update Pulse Monitor - Slack Tool Selection Guidance")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {PULSE_AGENT_ID}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Get agent's memory blocks
    print("Fetching agent memory blocks...")
    agent = http_get(f"{LETTA_BASE}/v1/agents/{PULSE_AGENT_ID}")
    if not agent:
        print("ERROR: Could not get agent")
        return 1

    blocks = agent.get("memory", {}).get("blocks", [])

    # Find slack_tool_use_guidelines block
    guidelines_block = None
    for block in blocks:
        if block.get("label") == "slack_tool_use_guidelines":
            guidelines_block = block
            break

    if not guidelines_block:
        print("ERROR: No slack_tool_use_guidelines block found")
        return 1

    current_value = guidelines_block.get("value", "")
    block_id = guidelines_block.get("id")
    block_limit = guidelines_block.get("limit", 5000)

    print(f"  Current content: {len(current_value)} chars")
    print(f"  Block limit: {block_limit} chars")
    print()

    # Check if already patched
    if "# Slack Tool Selection Guide" in current_value:
        print("Block already contains tool selection guidance - no update needed")
        return 0

    # Create new content by prepending the guidance
    new_value = TOOL_SELECTION_GUIDANCE + current_value

    print(f"  New content: {len(new_value)} chars")
    print()

    # Check if new content fits
    if len(new_value) > block_limit:
        print(f"ERROR: New content ({len(new_value)}) exceeds limit ({block_limit})")
        return 1

    # Show preview
    print("=" * 70)
    print("PREVIEW OF ADDITION")
    print("=" * 70)
    print(TOOL_SELECTION_GUIDANCE)
    print("=" * 70)
    print()

    if dry_run:
        print("DRY RUN - No changes applied")
        print("Run without --dry-run to apply this update")
        return 0

    # Confirm before update
    response = input("Add tool selection guidance to slack_tool_use_guidelines? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Update the block
    print("Updating slack_tool_use_guidelines block...")
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_value}
    )

    if result:
        print()
        print("SUCCESS: Tool selection guidance added!")
        print()
        print("The Pulse Monitor now knows:")
        print("  ✓ When to use get_slack_messages (complete retrieval)")
        print("  ✓ When to use search_slack_messages (content search)")
        print("  ✓ Workflow for comprehensive DM review")
        print()
        print(f"Updated block: {len(current_value)} → {len(new_value)} chars")
        return 0
    else:
        print("ERROR: Failed to update block")
        return 1


if __name__ == "__main__":
    sys.exit(main())
