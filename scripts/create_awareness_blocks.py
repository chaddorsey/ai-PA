#!/usr/bin/env python3
"""
Create and attach cross-agent awareness blocks to main agent and sleeptime companion.

Blocks:
- daily_awareness: Sleeptime writes daily digest here (what happened today)
- relationship_context: Sleeptime maintains ongoing relationship insights
- consolidation_instructions: How sleeptime should consolidate archival → core memory

Both awareness blocks are shared between main agent and sleeptime companion.
The instructions block is attached only to sleeptime.

Run once:
    LETTA_BASE_URL=http://localhost:8283 python3 scripts/create_awareness_blocks.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
SLEEPTIME_AGENT_ID = "agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2"

AGENTS = {
    "Main Agent": MAIN_AGENT_ID,
    "Sleeptime Companion": SLEEPTIME_AGENT_ID,
}

BLOCK_CONFIGS = [
    {
        "label": "daily_awareness",
        "description": "Daily digest of cross-interface activity. Updated by sleeptime companion.",
        "initial_value": (
            "[No activity consolidated yet. "
            "Sleeptime companion will populate this block with today's "
            "cross-interface activity summary after reviewing archival passages "
            "tagged memory:session.]"
        ),
        "limit": 5000,
        "target_agents": ["Main Agent", "Sleeptime Companion"],
    },
    {
        "label": "relationship_context",
        "description": "Ongoing relationship insights. Updated by sleeptime companion.",
        "initial_value": (
            "[No relationship context yet. "
            "Sleeptime companion will populate this block with patterns observed "
            "across conversations — communication preferences, recurring topics, "
            "relationship dynamics.]"
        ),
        "limit": 5000,
        "target_agents": ["Main Agent", "Sleeptime Companion"],
    },
    {
        "label": "consolidation_instructions",
        "description": "Instructions for sleeptime consolidation of cross-interface activity.",
        "initial_value": (
            "## Cross-Interface Consolidation Protocol\n\n"
            "When you wake up (every N steps), perform these consolidation tasks:\n\n"
            "### 1. Daily Awareness Update\n"
            "- Search archival memory for passages tagged 'memory:session' from today\n"
            "  (use archival_memory_search with query containing today's date)\n"
            "- Look for passages from ALL sources: source:slack, source:pa-web\n"
            "- Summarize into the 'daily_awareness' block using memory_rethink:\n"
            "  - Key topics discussed today\n"
            "  - Actions taken or requested\n"
            "  - Pending items or follow-ups\n"
            "  - Which interfaces were used (Slack DMs, pa-web)\n"
            "- Keep it concise (under 2000 chars) and actionable\n\n"
            "### 2. Relationship Context Update\n"
            "- Review new session passages for relationship-relevant signals:\n"
            "  - Communication preferences (time of day, verbosity, formality)\n"
            "  - Recurring topics or concerns\n"
            "  - Emotional tone or urgency patterns\n"
            "- Update 'relationship_context' block using memory_rethink\n"
            "- Only update when genuinely new patterns emerge; don't rewrite for no reason\n\n"
            "### 3. Important: Use memory_rethink\n"
            "- Use memory_rethink to rewrite blocks with updated content\n"
            "- Always preserve existing content that is still relevant\n"
            "- Call memory_finish_edits when done\n"
        ),
        "limit": 3000,
        "target_agents": ["Sleeptime Companion"],
    },
]


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_post(url, data):
    """Make HTTP POST request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  POST Error {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  POST Error: {e}")
        return None


def http_patch(url, data=None):
    """Make HTTP PATCH request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def get_or_create_block(label, description, initial_value, limit):
    """Get existing block by label or create new one."""
    existing = http_get(f"{LETTA_BASE}/v1/blocks/?label={label}")
    if existing and len(existing) > 0:
        print(f"    Found existing block: {existing[0]['id']}")
        return existing[0]["id"]

    result = http_post(
        f"{LETTA_BASE}/v1/blocks/",
        {
            "label": label,
            "description": description,
            "value": initial_value,
            "limit": limit,
        },
    )
    if result and result.get("id"):
        print(f"    Created block: {result['id']}")
        return result["id"]
    return None


def is_block_attached(agent_id, block_id):
    """Check if block is already attached to agent."""
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")
    if blocks:
        return any(b.get("id") == block_id for b in blocks)
    return False


def attach_block_to_agent(agent_id, block_id):
    """Attach block to agent's core memory."""
    result = http_patch(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
    )
    return result is not None


def main():
    print("=" * 60)
    print("Create Cross-Agent Awareness Blocks")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Main Agent: {MAIN_AGENT_ID}")
    print(f"Sleeptime:  {SLEEPTIME_AGENT_ID}")
    print()

    # Create blocks
    print("Creating awareness blocks...")
    block_ids = {}
    for config in BLOCK_CONFIGS:
        label = config["label"]
        print(f"  {label}:")
        block_id = get_or_create_block(
            label, config["description"], config["initial_value"], config["limit"]
        )
        if block_id:
            block_ids[label] = block_id
        else:
            print(f"    FAILED to create block")
    print()

    # Attach to target agents
    total_attachments = 0
    failed_attachments = 0
    for config in BLOCK_CONFIGS:
        label = config["label"]
        block_id = block_ids.get(label)
        if not block_id:
            print(f"Skipping {label}: no block ID")
            continue

        for agent_name in config["target_agents"]:
            agent_id = AGENTS[agent_name]
            if is_block_attached(agent_id, block_id):
                print(f"  {label} -> {agent_name}: already attached")
                total_attachments += 1
            elif attach_block_to_agent(agent_id, block_id):
                print(f"  {label} -> {agent_name}: attached")
                total_attachments += 1
            else:
                print(f"  {label} -> {agent_name}: FAILED")
                failed_attachments += 1
    print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Blocks created: {len(block_ids)}/{len(BLOCK_CONFIGS)}")
    print(f"  Attachments: {total_attachments} succeeded, {failed_attachments} failed")
    print()

    if block_ids:
        print("Verify with:")
        for label, block_id in block_ids.items():
            print(f"  curl {LETTA_BASE}/v1/blocks/{block_id}")
        print()

    return 0 if failed_attachments == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
