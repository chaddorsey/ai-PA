#!/usr/bin/env python3
"""
Update Agent Personas to Use report_refs Tool

Replaces the text-based REFS instructions with tool-based instructions.
Agents will call report_refs() instead of emitting REFS: {...} in text.
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs
AGENTS = {
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
}

# Old text-based REFS patterns to remove
OLD_REFS_PATTERNS = [
    "## REFS Line (for follow-up actions)",
    "## Response Format - REFS Line",
    "REFS: {",
]

# New tool-based instruction (short, fits block limits)
TOOL_INSTRUCTION = """

## report_refs Tool (for follow-up actions)

After finding/creating/modifying a resource, call report_refs() so the user can reference it in follow-ups like "update that" or "reply to that".

Example: report_refs(ref_type="calendar_event", ref_id="abc123", title="Team Standup")

Call this for: events, tasks, emails, issues, documents, messages.
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
    """Update agent's persona to use report_refs tool."""
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

    # Check if already has tool instruction
    if "report_refs Tool" in current_persona or "report_refs()" in current_persona:
        print(f"  Already has tool instruction")
        return "skipped"

    # Remove old REFS text instructions if present
    new_persona = current_persona
    for pattern in OLD_REFS_PATTERNS:
        if pattern in new_persona:
            # Find and remove the old REFS section
            idx = new_persona.find(pattern)
            if idx > 0:
                # Find the section start (look for ## header)
                section_start = new_persona.rfind("##", 0, idx)
                if section_start == -1:
                    section_start = idx
                # Keep everything before this section
                new_persona = new_persona[:section_start].rstrip()
                print(f"  Removed old REFS text instruction")
                break

    # Add new tool instruction
    new_persona = new_persona + TOOL_INSTRUCTION

    # Check length
    if len(new_persona) > 5000:
        print(f"  ERROR: New persona exceeds 5000 chars ({len(new_persona)})")
        return False

    print(f"  Length: {len(current_persona)} -> {len(new_persona)} chars")

    # Update the block
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print(f"  Updated to use report_refs tool")
        return "updated"
    else:
        print(f"  Failed to update")
        return False


def main():
    print("=" * 60)
    print("Update Agents to Use report_refs Tool")
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
    print(f"  Skipped (already has tool instruction): {skipped}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All agents now instruct to use report_refs tool!")
    else:
        print(f"Warning: {failed} agents failed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
