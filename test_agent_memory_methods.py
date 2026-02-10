#!/usr/bin/env python3
"""Check what memory-related methods are available"""

import os
try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))

AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

print("Checking agent memory methods...")
print()

# Check what's available on client.agents
print("Methods on client.agents:")
agent_methods = [m for m in dir(client.agents) if not m.startswith('_')]
print(agent_methods)
print()

# Check if there are memory-specific methods
if hasattr(client.agents, 'memory'):
    print("client.agents.memory methods:")
    print([m for m in dir(client.agents.memory) if not m.startswith('_')])
    print()

# Check agent object
agent = client.agents.retrieve(AGENT_ID)
print(f"Agent type: {type(agent)}")
print(f"Agent attributes: {[a for a in dir(agent) if not a.startswith('_')][:20]}")
print()

# Check if agent has memory methods
if hasattr(agent, 'memory') and hasattr(agent.memory, 'update'):
    print("Agent has memory.update method!")

# Check client structure for memory operations
print("\nLooking for memory-related attributes on client...")
for attr in dir(client):
    if 'memory' in attr.lower() and not attr.startswith('_'):
        print(f"  {attr}")
