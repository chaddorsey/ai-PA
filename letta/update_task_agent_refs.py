#!/usr/bin/env python3
"""
Update Task Agent Persona with REFS Instructions

Adds REFS line instructions to the Task Agent for actionable
reference tracking. When the agent creates, modifies, or queries
OmniFocus tasks, it emits REFS with taskId, name, and project
so follow-up requests can reference the task.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

TASK_AGENT_ID = "agent-dd15479e-6543-400e-8463-b2a48b13cd4a"

# REFS instruction to append after SUMMARY instructions
REFS_INSTRUCTION = """

## REFS Line (for follow-up actions)

After SUMMARY, add REFS with task details when creating/modifying/finding tasks:
REFS: {"taskId": "...", "name": "...", "project": "..."}

Example:
SUMMARY: Created task for weekly report #tasks #omnifocus
REFS: {"taskId": "task_abc123", "name": "Write weekly report", "project": "Work"}

Rules: Include taskId (required for updates), name, project. Skip for general queries.
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
    print("Update Task Agent with REFS Instructions")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Task Agent ID: {TASK_AGENT_ID}")
    print()

    # Get agent's memory blocks
    print("Fetching agent memory blocks...")
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{TASK_AGENT_ID}/core-memory/blocks")
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
    if "REFS Line" in current_persona or ("REFS:" in current_persona and "taskId" in current_persona):
        print()
        print("Task agent already has REFS instructions!")
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
        print("SUCCESS: Task agent updated with REFS instructions!")
        print()
        print("The agent will now emit REFS lines like:")
        print('  REFS: {"taskId": "abc123", "name": "Write report", "project": "Work"}')
        return 0
    else:
        print("ERROR: Failed to update persona")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
