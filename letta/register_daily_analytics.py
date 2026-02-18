#!/usr/bin/env python3
"""
Register Daily Analytics Briefing Tools with Letta Agent.

Tools:
  - collect_analytics_snapshot: Captures Drive/Email/Slack metrics, persists to DB
  - compose_daily_briefing: Reads from DB + archival, writes briefing to block + markdown

Usage:
  LETTA_BASE_URL=http://localhost:8283 python letta/register_daily_analytics.py

Attach to Pulse Monitor:
  LETTA_BASE_URL=http://localhost:8283 LETTA_AGENT_ID=agent-2ed14ef4-6289-453a-ae27-290b6ed196b8 python letta/register_daily_analytics.py
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

from daily_analytics_snapshot import collect_analytics_snapshot
from compose_daily_briefing import compose_daily_briefing

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"


def main():
    print(f"{'='*60}")
    print("Daily Analytics Briefing Tools Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    agent_id = AGENT_ID or PULSE_MONITOR_ID
    print(f"Target Agent: {agent_id}\n")

    tools_to_register = [
        ("collect_analytics_snapshot", collect_analytics_snapshot,
         ["analytics", "drive", "email", "slack", "snapshot"]),
        ("compose_daily_briefing", compose_daily_briefing,
         ["analytics", "briefing", "trends", "daily"]),
    ]

    registered_tool_ids = []

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        for tool_name, tool_func, tags in tools_to_register:
            print(f"Registering tool: {tool_name}")

            try:
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=tags,
                )
                tool_id = created_tool.id if hasattr(created_tool, "id") else "N/A"
                print(f"  Registered: {tool_name} (ID: {tool_id})")
                registered_tool_ids.append(tool_id)

            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "409" in error_str:
                    print(f"  Tool exists, re-registering...")
                    try:
                        all_tools = client.tools.list()
                        for tool in all_tools:
                            name = tool.name if hasattr(tool, "name") else tool.get("name")
                            if name == tool_name:
                                tid = tool.id if hasattr(tool, "id") else tool.get("id")
                                if tid:
                                    client.tools.delete(tool_id=tid)
                                    created_tool = client.tools.create_from_function(
                                        func=tool_func,
                                        tags=tags,
                                    )
                                    new_id = created_tool.id if hasattr(created_tool, "id") else "N/A"
                                    registered_tool_ids.append(new_id)
                                    print(f"  Re-registered: {tool_name} (ID: {new_id})")
                                    break
                    except Exception as re_e:
                        print(f"  Could not re-register: {re_e}")
                else:
                    print(f"  Failed: {e}")
            print()

        if agent_id and registered_tool_ids:
            print(f"Attaching tools to agent {agent_id}...")
            for tool_id in registered_tool_ids:
                try:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    print(f"  Attached {tool_id}")
                except Exception as e:
                    if "already" in str(e).lower():
                        print(f"  Already attached: {tool_id}")
                    else:
                        print(f"  Could not attach: {e}")

        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}")
        return 0

    except Exception as e:
        print(f"\nFailed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
