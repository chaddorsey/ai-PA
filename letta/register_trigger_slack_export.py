#!/usr/bin/env python3
"""
Register trigger_slack_analytics_export tool with Letta and attach to Pulse Monitor.

Usage:
  LETTA_BASE_URL=http://localhost:8283 python letta/register_trigger_slack_export.py
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

from trigger_slack_export import trigger_slack_analytics_export

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"
AGENT_ID = os.getenv("LETTA_AGENT_ID", PULSE_MONITOR_ID)


def main():
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Target Agent: {AGENT_ID}\n")

    client = Letta(base_url=LETTA_BASE_URL)
    tool_name = "trigger_slack_analytics_export"
    tags = ["slack", "analytics", "export", "pipeline"]

    # Delete existing tool if present
    try:
        for tool in client.tools.list():
            name = tool.name if hasattr(tool, "name") else tool.get("name")
            if name == tool_name:
                tid = tool.id if hasattr(tool, "id") else tool.get("id")
                if tid:
                    client.tools.delete(tool_id=tid)
                    print(f"Deleted existing tool: {tid}")
    except Exception as e:
        print(f"Warning during cleanup: {e}")

    # Register
    created_tool = client.tools.create_from_function(
        func=trigger_slack_analytics_export,
        tags=tags,
    )
    tool_id = created_tool.id if hasattr(created_tool, "id") else "N/A"
    print(f"Registered: {tool_name} (ID: {tool_id})")

    # Attach to agent
    try:
        client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool_id)
        print(f"Attached to agent {AGENT_ID}")
    except Exception as e:
        if "already" in str(e).lower():
            print(f"Already attached to agent")
        else:
            print(f"Could not attach: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
