#!/usr/bin/env python3
"""
Attach Coordination Blocks to Specialist Agents

Creates and attaches the three coordination blocks to each specialist agent
so they can participate in coordinated tasks.

Blocks:
- coordination_task_{identity_id} - Attached for reading
- coordination_gathered_{identity_id} - Attached for appending

Note: Status block is handler-only and not attached to agents.

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Default identity ID (for initial setup)
DEFAULT_IDENTITY_ID = os.getenv(
    "DEFAULT_IDENTITY_ID",
    "identity-e80a4f2b-a157-47c4-af45-0a4e8f1aec3e"  # Chad's identity
)

# Specialist agents
AGENTS = {
    "Calendar Agent": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
}

# Block configurations
BLOCK_CONFIGS = [
    {
        "label_template": "coordination_task_{identity_id}",
        "description": "Task context for coordinated multi-agent task (READ ONLY)",
        "initial_value": "",
        "limit": 500,
    },
    {
        "label_template": "coordination_gathered_{identity_id}",
        "description": "Agent findings (APPEND ONLY via memory_insert)",
        "initial_value": "",
        "limit": 2000,
    },
]


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_post(url, data):
    """Make HTTP POST request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  POST Error {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  POST Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def get_or_create_block(label, description, initial_value, limit):
    """Get existing block or create new one."""
    # Check for existing
    existing = http_get(f"{LETTA_BASE}/v1/blocks/?label={label}")
    if existing and len(existing) > 0:
        print(f"    Found existing block: {existing[0]['id']}")
        return existing[0]['id']

    # Create new
    result = http_post(
        f"{LETTA_BASE}/v1/blocks/",
        {
            "label": label,
            "description": description,
            "value": initial_value,
            "limit": limit,
        }
    )
    if result and result.get('id'):
        print(f"    Created block: {result['id']}")
        return result['id']

    return None


def attach_block_to_agent(agent_id, block_id):
    """Attach block to agent's core memory."""
    result = http_patch(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        {}
    )
    return result is not None


def is_block_attached(agent_id, block_id):
    """Check if block is already attached to agent."""
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")
    if blocks:
        return any(b.get('id') == block_id for b in blocks)
    return False


def main():
    print("=" * 60)
    print("Attach Coordination Blocks to Agents")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Identity ID: {DEFAULT_IDENTITY_ID}")
    print(f"Agents: {len(AGENTS)}")
    print()

    # Create blocks
    print("Creating coordination blocks...")
    block_ids = {}

    for config in BLOCK_CONFIGS:
        label = config["label_template"].format(identity_id=DEFAULT_IDENTITY_ID)
        print(f"  {label}")
        block_id = get_or_create_block(
            label,
            config["description"],
            config["initial_value"],
            config["limit"]
        )
        if block_id:
            block_ids[label] = block_id
        else:
            print(f"    FAILED to create block")

    print()

    # Attach blocks to each agent
    success_count = 0

    for agent_name, agent_id in AGENTS.items():
        print(f"Processing {agent_name}...")

        agent_success = True
        for label, block_id in block_ids.items():
            if is_block_attached(agent_id, block_id):
                print(f"  {label}: already attached")
            else:
                if attach_block_to_agent(agent_id, block_id):
                    print(f"  {label}: attached")
                else:
                    print(f"  {label}: FAILED to attach")
                    agent_success = False

        if agent_success:
            success_count += 1
        print()

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Blocks created: {len(block_ids)}")
    print(f"  Agents updated: {success_count}/{len(AGENTS)}")
    print()

    return 0 if success_count == len(AGENTS) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
