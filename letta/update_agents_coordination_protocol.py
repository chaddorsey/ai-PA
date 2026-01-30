#!/usr/bin/env python3
"""
Update Agent Personas with Coordination Protocol

Adds the coordination_protocol instructions to specialist agents
(Calendar, Task, Email, Pulse) so they know how to participate in
coordinated multi-agent tasks.

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Specialist agents that participate in coordinated tasks
AGENTS = {
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
}

# Coordination protocol to add to agent personas
COORDINATION_PROTOCOL = """

<coordination_protocol>
When participating in multi-agent tasks, you'll see these memory blocks:

1. coordination_task (READ ONLY)
   - Contains current task context and what you need to contribute
   - Read this to understand your role
   - DO NOT modify this block

2. coordination_gathered (APPEND ONLY)
   - When you finish your work, call memory_insert to add ONE line
   - Tool: memory_insert("coordination_gathered", "[YourName HH:MM] Summary")
   - Format: [AgentName HH:MM] Brief summary (under 100 chars)
   - Example: [Calendar 10:30] Board Meeting, 2pm Jan 30, 3 participants
   - DO NOT use memory_replace or memory_rethink on this block

3. coordination_status (DO NOT TOUCH)
   - Handler uses this to track progress
   - You never need to read or modify this

Workflow:
1. Read coordination_task to understand what's needed
2. Do your specialized work (search, analyze, etc.)
3. Summarize findings in ONE line via memory_insert to coordination_gathered
4. Your part is done - handler will route to next agent if needed

If you encounter errors or can't complete your part, note it in your response and still add a line like:
[YourName HH:MM] Unable to complete - {brief reason}
</coordination_protocol>
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


def update_agent_persona(agent_name, agent_id):
    """Add coordination protocol to agent's persona."""
    print(f"\nProcessing {agent_name}...")

    # Get agent's memory blocks
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")
    if not blocks:
        print(f"  Could not get blocks")
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

    # Check if already has coordination protocol
    if "<coordination_protocol>" in current_persona:
        print(f"  Already has coordination protocol")
        return "skipped"

    # Add coordination protocol
    new_persona = current_persona + COORDINATION_PROTOCOL

    # Check length (Letta block limit is 8500 chars)
    if len(new_persona) > 8500:
        print(f"  ERROR: New persona exceeds 8500 chars ({len(new_persona)})")
        return False

    print(f"  Length: {len(current_persona)} -> {len(new_persona)} chars")

    # Update the block
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print(f"  Added coordination protocol")
        return "updated"
    else:
        print(f"  Failed to update")
        return False


def main():
    print("=" * 60)
    print("Update Agents with Coordination Protocol")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents to update: {len(AGENTS)}")

    updated = 0
    skipped = 0
    failed = 0

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
    print(f"  Skipped (already has protocol): {skipped}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All agents now have coordination protocol!")
    else:
        print(f"Warning: {failed} agents failed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
