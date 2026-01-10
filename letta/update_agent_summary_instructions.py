#!/usr/bin/env python3
"""
Update Letta Agent Personas with SUMMARY Line Instructions

This script appends SUMMARY line instructions to agent personas for
cross-agent context tracking (Pattern 2).

Agents end responses with "SUMMARY: <brief action>" which is extracted
by the routing handler to maintain session context across agent switches.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs from agent_selector.py
AGENTS = {
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Calendar Agent": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "Pulse Agent": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Main Agent": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}

# SUMMARY instruction block to append to personas
SUMMARY_INSTRUCTION = """

## Response Format - SUMMARY Line

IMPORTANT: Always end your response with exactly one line starting with "SUMMARY:"
that captures the key action taken in 10 words or fewer. This helps maintain
context when the user switches between different assistants.

Examples:
- "I've scheduled your meeting for 3pm tomorrow. SUMMARY: Scheduled meeting for Jan 8 at 3pm"
- "Here are your top 5 tasks from OmniFocus. SUMMARY: Listed 5 priority tasks"
- "I've sent the Slack message to the team. SUMMARY: Sent Slack message to #general"
- "Your calendar shows 3 meetings today. SUMMARY: Showed 3 meetings for today"
- "I found the document you were looking for. SUMMARY: Found quarterly report document"

The SUMMARY line should be:
- Concise (10 words or fewer)
- Action-focused (what you did, not what you said)
- Specific enough to remind the user what happened
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


def get_agent_blocks(agent_id):
    """Get memory blocks for an agent."""
    return http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")


def update_persona_block(agent_id, block_id, new_value):
    """Update a memory block's value."""
    return http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_value}
    )


def update_agent_persona(agent_name, agent_id):
    """Update agent's persona with SUMMARY instructions."""
    print(f"\nProcessing {agent_name} ({agent_id})...")

    # Get agent's memory blocks
    blocks = get_agent_blocks(agent_id)
    if not blocks:
        print(f"  Could not get blocks for agent")
        return False

    # Find persona block
    persona_block = None
    for block in blocks:
        if block.get("label") == "persona":
            persona_block = block
            break

    if not persona_block:
        print(f"  No persona block found")
        return False

    current_persona = persona_block.get("value", "")
    block_id = persona_block.get("id")

    # Check if already has SUMMARY instruction
    if "SUMMARY:" in current_persona and "Response Format" in current_persona:
        print(f"  Already has SUMMARY instructions")
        return True

    # Append SUMMARY instruction
    new_persona = current_persona + SUMMARY_INSTRUCTION

    # Update the block
    result = update_persona_block(agent_id, block_id, new_persona)
    if result:
        print(f"  Updated persona with SUMMARY instructions")
        return True
    else:
        print(f"  Failed to update persona")
        return False


def main():
    print("=" * 60)
    print("Update Agent Personas with SUMMARY Instructions")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents to update: {len(AGENTS)}")

    updated = 0
    failed = 0
    skipped = 0

    for agent_name, agent_id in AGENTS.items():
        result = update_agent_persona(agent_name, agent_id)
        if result:
            if "Already has" in str(result):
                skipped += 1
            else:
                updated += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Updated: {updated}")
    print(f"  Skipped (already has): {skipped}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All agents now have SUMMARY instructions!")
    else:
        print(f"Warning: {failed} agents failed to update")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
