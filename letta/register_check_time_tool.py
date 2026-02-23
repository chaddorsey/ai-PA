#!/usr/bin/env python3
"""
Register check_current_time Tool with Letta

Replaces the n8n-hosted Check_Time MCP tool with a reliable local
implementation that doesn't depend on external time APIs.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from check_time_tool import check_current_time


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    existing_tools = client.tools.list()
    for tool in existing_tools:
        if tool.name == "check_current_time":
            print(f"Found existing tool: {tool.id}")
            response = input("Tool already exists. Re-register? [y/N]: ")
            if response.lower() != 'y':
                print(f"Existing tool ID: {tool.id}")
                return 0
            print("Deleting existing tool...")
            client.tools.delete(tool.id)
            print("Deleted.")
            break

    print("Registering check_current_time tool...")
    created_tool = client.tools.create_from_function(
        func=check_current_time,
        tags=["time", "utility", "date"],
    )

    print(f"Tool Name: {created_tool.name}")
    print(f"Tool ID:   {created_tool.id}")
    print()

    # Attach to the daily-schedule-agent
    AGENT_ID = "agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2"
    print(f"Attaching to daily-schedule-agent ({AGENT_ID})...")

    # Get current tool IDs and add the new one
    agent = client.agents.retrieve(AGENT_ID)
    current_tool_ids = [t.id for t in agent.tools]

    # Remove old n8n Check_Time if present
    old_check_time_ids = [t.id for t in agent.tools if t.name == "Check_Time"]
    if old_check_time_ids:
        print(f"  Removing old Check_Time MCP tool: {old_check_time_ids}")
        current_tool_ids = [tid for tid in current_tool_ids if tid not in old_check_time_ids]

    current_tool_ids.append(created_tool.id)
    client.agents.modify(AGENT_ID, tool_ids=current_tool_ids)
    print("  Attached successfully.")

    print()
    print("Done! The agent now uses check_current_time instead of the n8n Check_Time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
