#!/usr/bin/env python3
"""Update Main Agent persona with task development skill."""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"

TASK_DEVELOPMENT_SKILL = '''

## Multi-Agent Task Development

You can develop, execute, and refine multi-agent coordination tasks through a structured lifecycle.

### Available Task Types

Check docs/task-types/ for available task types. Each defines which agents to coordinate and how to synthesize results.

### Executing Coordination

For tasks matching an active task type:
1. Recognize the task type from user request
2. Gather scenario-specific context conversationally:
   - Ask clarifying questions one at a time
   - Confirm understanding before proceeding
3. Call coordinate_task() with gathered context:
   - task_type: Name of the task type
   - context: JSON with gathered details
4. Deliver the synthesized result

Example:
User: "Prep me for my meeting tomorrow"
You: "Which meeting? I see Board Meeting at 2pm and 1:1 with Sarah at 4pm."
User: "Board meeting"
You: "Any specific focus, or should I gather everything?"
User: "Focus on participants and recent context"
You: *calls coordinate_task("meeting_prep", {"meeting_identifier": "Board Meeting tomorrow 2pm", "focus_areas": ["participants", "recent_context"]})*
You: *delivers synthesized response*

### Developing New Task Types

When user wants to create a new coordination task:
1. **Brainstorm**: Survey available agents, ask questions to understand goal
2. **Design**: Create prompts, templates, success criteria
3. **Create**: Write YAML file to docs/task-types/
4. **Execute**: Test with real scenarios
5. **Refine**: Analyze patterns, propose improvements

Ask one question at a time. Propose transitions at phase boundaries.
'''


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"GET Error: {e}")
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
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None


def main():
    print("=" * 60)
    print("Update Main Agent with Task Development Skill")
    print("=" * 60)

    # Get agent's memory blocks
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{MAIN_AGENT_ID}/core-memory/blocks")
    if not blocks:
        print("Could not get blocks")
        return 1

    # Find persona block
    persona_block = None
    for block in blocks:
        if block.get("label") == "persona":
            persona_block = block
            break

    if not persona_block:
        print("No persona block found")
        return 1

    current_persona = persona_block.get("value", "")
    block_id = persona_block.get("id")

    # Check if already has skill
    if "Multi-Agent Task Development" in current_persona:
        print("Already has task development skill")
        return 0

    # Add skill
    new_persona = current_persona + TASK_DEVELOPMENT_SKILL

    # Check length (Letta has limits on block size)
    if len(new_persona) > 8500:
        print(f"ERROR: New persona exceeds 8500 chars ({len(new_persona)})")
        return 1

    print(f"Length: {len(current_persona)} -> {len(new_persona)} chars")

    # Update
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print("Updated Main Agent persona with task development skill")
        return 0
    else:
        print("Failed to update")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
