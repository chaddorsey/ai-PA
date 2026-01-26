#!/usr/bin/env python3
"""
Setup template blocks for Letta Conversations on the Scheduler Agent.

These blocks will be isolated (copied per conversation) when using
isolated_block_labels in conversation creation, enabling per-user
context without permission-based access control.

Run once to set up the agent, or to verify blocks are configured correctly.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("ERROR: letta-client or letta package not installed")
        sys.exit(1)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SCHEDULER_AGENT_ID = os.getenv(
    "SCHEDULER_AGENT_ID",
    "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
)

# Blocks that should be isolated per conversation
ISOLATED_BLOCKS = [
    {
        "label": "user_preferences",
        "value": "No user preferences learned yet. This block will be populated as I learn about this user's scheduling preferences through our conversations.",
        "description": "Per-user scheduling preferences (isolated per conversation)",
        "limit": 2000,
    },
    {
        "label": "user_calendar_context",
        "value": "No calendar context yet. This block tracks the current user's recent scheduling requests and calendar state.",
        "description": "Per-user calendar context (isolated per conversation)",
        "limit": 2000,
    },
]


def main():
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Scheduler Agent ID: {SCHEDULER_AGENT_ID}")
    print()

    client = Letta(base_url=LETTA_BASE_URL)
    print("Connected to Letta server\n")

    # Get current agent blocks
    try:
        agent = client.agents.retrieve(agent_id=SCHEDULER_AGENT_ID)
        current_labels = [b.label for b in agent.memory.blocks]
        print(f"Agent '{agent.name}' has {len(current_labels)} blocks")
    except Exception as e:
        print(f"ERROR: Could not retrieve agent: {e}")
        return 1

    # Add or verify isolated blocks
    for block_config in ISOLATED_BLOCKS:
        label = block_config["label"]

        if label in current_labels:
            print(f"  [EXISTS] {label}")
            continue

        print(f"  [ADDING] {label}...")
        try:
            # Create block
            block = client.blocks.create(**block_config)
            print(f"    Created: {block.id}")

            # Attach to agent
            client.agents.blocks.attach(
                agent_id=SCHEDULER_AGENT_ID,
                block_id=block.id
            )
            print(f"    Attached to agent")
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

    print()
    print("Setup complete!")
    print()
    print("To create a conversation with isolated blocks:")
    print("  POST /v1/conversations/?agent_id=<agent_id>")
    print("  Body: {")
    print('    "isolated_block_labels": ["user_preferences", "user_calendar_context"]')
    print("  }")

    return 0


if __name__ == "__main__":
    sys.exit(main())
