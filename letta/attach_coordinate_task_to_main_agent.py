#!/usr/bin/env python3
"""Attach coordinate_task tool to Main Agent."""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


def main():
    print("=" * 60)
    print("Attach coordinate_task to Main Agent")
    print("=" * 60)

    # Import letta client
    try:
        import letta_client
        client = letta_client.Letta(base_url=LETTA_BASE)
    except ImportError:
        from letta import create_client
        client = create_client(base_url=LETTA_BASE)

    # Find the tool
    tools = client.tools.list()
    coordinate_tool = None
    for tool in tools:
        if tool.name == "coordinate_task":
            coordinate_tool = tool
            break

    if not coordinate_tool:
        print("ERROR: coordinate_task tool not found. Run register script first.")
        print("Run: python letta/register_coordinate_task_tool.py")
        return 1

    print(f"Found tool: {coordinate_tool.id}")

    # Get Main Agent
    agent = client.agents.retrieve(MAIN_AGENT_ID)
    print(f"Main Agent: {agent.name}")

    # Check if already attached
    agent_tool_ids = [t.id for t in (agent.tools or [])]
    if coordinate_tool.id in agent_tool_ids:
        print("Tool already attached to Main Agent")
        return 0

    # Attach tool
    client.agents.tools.attach(
        agent_id=MAIN_AGENT_ID,
        tool_id=coordinate_tool.id
    )

    print("Successfully attached coordinate_task to Main Agent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
