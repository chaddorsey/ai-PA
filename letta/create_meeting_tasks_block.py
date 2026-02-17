#!/usr/bin/env python3
"""Create queued_tasks_from_meetings memory block on the Granola agent."""
import os
import sys

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    # Check if block already exists
    agent = client.agents.retrieve(agent_id=AGENT_ID)
    for block in agent.memory.blocks:
        if block.label == "queued_tasks_from_meetings":
            print(f"Block already exists: {block.id}")
            return 0

    # Create block
    block = client.blocks.create(
        label="queued_tasks_from_meetings",
        value="# Queued Tasks from Meetings\n(empty)\n",
    )
    print(f"Created block: {block.id}")

    # Attach to agent
    client.agents.blocks.attach(agent_id=AGENT_ID, block_id=block.id)
    print(f"Attached to agent {AGENT_ID}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
