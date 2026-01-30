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
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Pulse Agent": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Main Agent": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}

# SUMMARY instruction block to append to personas (kept concise to fit block limits)
SUMMARY_INSTRUCTION = """

## Response Format - SUMMARY Line

End every response with: SUMMARY: <action in ≤10 words> #topic1 #topic2

Examples:
- SUMMARY: Scheduled meeting for Jan 8 at 3pm #calendar #meeting
- SUMMARY: Listed 5 priority tasks #tasks #omnifocus
- SUMMARY: Sent Slack message to #general #slack
- SUMMARY: Found quarterly report document #docs #search

Rules: Action-focused, 1-3 lowercase hashtags for categorization.
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


def update_agent_persona(agent_name, agent_id, force_update=False):
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

    # Check if already has SUMMARY instruction with hashtags
    has_summary = "SUMMARY:" in current_persona and "Response Format" in current_persona
    has_hashtags = "#topic1 #topic2" in current_persona or "hashtags" in current_persona.lower()

    if has_summary and has_hashtags and not force_update:
        print(f"  Already has SUMMARY instructions with hashtags")
        return "skipped"

    # If has old SUMMARY block without hashtags, replace it
    if has_summary and not has_hashtags:
        print(f"  Replacing old SUMMARY block with hashtag version...")
        # Find and remove the old SUMMARY block
        marker = "## Response Format - SUMMARY Line"
        if marker in current_persona:
            idx = current_persona.find(marker)
            # Find the section before the marker
            base_persona = current_persona[:idx].rstrip()
            new_persona = base_persona + SUMMARY_INSTRUCTION
        else:
            # Marker not found, just append
            new_persona = current_persona + SUMMARY_INSTRUCTION
    else:
        # Append SUMMARY instruction (no existing block)
        new_persona = current_persona + SUMMARY_INSTRUCTION

    # Update the block
    result = update_persona_block(agent_id, block_id, new_persona)
    if result:
        print(f"  Updated persona with SUMMARY instructions")
        return "updated"
    else:
        print(f"  Failed to update persona")
        return False


def main():
    print("=" * 60)
    print("Update Agent Personas with SUMMARY Instructions (with hashtags)")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents to update: {len(AGENTS)}")

    updated = 0
    failed = 0
    skipped = 0

    for agent_name, agent_id in AGENTS.items():
        result = update_agent_persona(agent_name, agent_id)
        if result == "updated":
            updated += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Updated: {updated}")
    print(f"  Skipped (already has hashtags): {skipped}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All agents now have SUMMARY instructions with hashtag support!")
    else:
        print(f"Warning: {failed} agents failed to update")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
