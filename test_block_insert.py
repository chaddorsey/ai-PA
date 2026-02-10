#!/usr/bin/env python3
"""Test block insert operation via Python client"""

import os
try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))

BLOCK_ID = "block-5a516880-1e01-4da5-a71b-23cad597a339"
AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

print("Testing block insert via Python client...")
print(f"Block ID: {BLOCK_ID}")
print(f"Agent ID: {AGENT_ID}")
print()

# Try to insert using the client
try:
    # Check what methods are available on blocks
    print("Available methods on client.blocks:")
    print([m for m in dir(client.blocks) if not m.startswith('_')])
    print()

    # Try to modify block value
    block = client.blocks.retrieve(BLOCK_ID)
    print(f"Current block value length: {len(block.value)}")

    # Append test content
    new_value = block.value + "\n=== Python Client Test ===\n[2026-02-05 22:52] Test from Python client\n"

    updated = client.blocks.modify(
        block_id=BLOCK_ID,
        value=new_value
    )

    print(f"Updated block value length: {len(updated.value)}")
    print("Success!")
    print("\nTrying to find agent-specific block modify...")

    # Check agent.memory methods
    agent = client.agents.retrieve(AGENT_ID)
    print("\nAgent memory keys:", list(agent.memory.keys()) if hasattr(agent, 'memory') and isinstance(agent.memory, dict) else "not a dict")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
