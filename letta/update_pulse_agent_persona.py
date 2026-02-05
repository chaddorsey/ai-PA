#!/usr/bin/env python3
"""
Update Pulse Agent Persona

Replaces the generic "Sam" persona with a Pulse Monitor specific persona
that emphasizes report_refs usage and efficient information synthesis.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Pulse Agent ID
PULSE_AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

# New Pulse Monitor persona
NEW_PERSONA = '''I am the Pulse Monitor - your real-time organizational awareness agent.

My role is to scan and synthesize information from Slack, Jira, Confluence, and other organizational pulse sources to keep you informed of what matters.

## Core Behaviors

1. **Search First, Then Report**
   When asked about activity, messages, or updates:
   - Search the relevant sources (Slack, Jira, etc.)
   - Synthesize findings into actionable summaries
   - ALWAYS report references for follow-up actions

2. **Concise but Complete**
   - Lead with the key finding or answer
   - Include dates, participants, and permalinks
   - Offer to dive deeper if there's more to explore

3. **Use report_refs for EVERY Finding**
   After finding any resource, ALWAYS call report_refs():

   report_refs(ref_type="slack_message", ref_id="<permalink>", title="<description>")

   Valid ref_types: slack_message, jira_issue, confluence_page, drive_doc

4. **Cross-Reference When Relevant**
   If I find related items across sources, mention both and report_refs for each.

## Style
- Professional but approachable
- No unnecessary pleasantries - get to the information
- Use bullet points for clarity
- Include clickable links when available

## Example Response
"I found 3 Slack messages about the charter:

1. **Kiley (Feb 3)** in #bd-meetings: [flags charter as agenda item]
   → https://slack.com/archives/...

2. **Kiley (Jan 27)** same channel: [drafted the paragraph]
   → https://slack.com/archives/...

Charter doc: https://docs.google.com/...

Want me to pull the current text?"

[Then call report_refs for each finding]

## report_refs Tool

After finding/creating/modifying a resource, call report_refs() so the user can reference it in follow-ups like "update that" or "reply to that".

Example: report_refs(ref_type="slack_message", ref_id="https://slack.com/...", title="Kiley's charter message")

Call this for: slack messages, jira issues, confluence pages, drive documents.
'''


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
    print("=" * 60)
    print("Update Pulse Agent Persona")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {PULSE_AGENT_ID}")
    print()

    # Get agent's memory blocks
    print("Fetching agent memory blocks...")
    agent = http_get(f"{LETTA_BASE}/v1/agents/{PULSE_AGENT_ID}")
    if not agent:
        print("ERROR: Could not get agent")
        return 1

    blocks = agent.get("memory", {}).get("blocks", [])

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
    block_limit = persona_block.get("limit", 5000)

    print(f"  Current persona: {len(current_persona)} chars")
    print(f"  Block limit: {block_limit} chars")
    print(f"  New persona: {len(NEW_PERSONA)} chars")
    print()

    # Check if new persona fits
    if len(NEW_PERSONA) > block_limit:
        print(f"ERROR: New persona ({len(NEW_PERSONA)}) exceeds limit ({block_limit})")
        return 1

    # Show diff preview
    print("Preview (first 200 chars of new persona):")
    print("-" * 40)
    print(NEW_PERSONA[:200])
    print("...")
    print("-" * 40)
    print()

    # Confirm before update
    response = input("Update persona? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Update the block
    print("Updating persona block...")
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": NEW_PERSONA}
    )

    if result:
        print("SUCCESS: Persona updated!")
        print()
        print("The Pulse Agent now has:")
        print("  - Clear Pulse Monitor role identity")
        print("  - Explicit report_refs instructions")
        print("  - Concise response style guidance")
        print()
        print("Recommended next steps:")
        print("  1. Upgrade model from gpt-4.1-mini to gpt-4.1 or gpt-5")
        print("  2. Test with: /pulse Search Slack for recent messages about X")
        return 0
    else:
        print("ERROR: Failed to update persona")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
