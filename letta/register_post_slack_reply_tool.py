#!/usr/bin/env python3
"""
Register post_slack_channel_reply Tool with Letta

Registers the tool and attaches it to tasks-agent-sleeptime.
Designed to be run once from the host.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python letta/register_post_slack_reply_tool.py
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

from post_slack_channel_reply_tool import post_slack_channel_reply

TOOL_NAME = "post_slack_channel_reply"
# tasks-agent-sleeptime — runs background task lifecycle + completion feedback
AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"


def main():
    print("=" * 70)
    print(f"Register {TOOL_NAME} Tool")
    print("=" * 70)
    print()

    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    print(f"Checking for existing {TOOL_NAME} tool...")
    existing_tools = client.tools.list()
    for tool in existing_tools:
        if tool.name == TOOL_NAME:
            print(f"  Found existing tool: {tool.id}")
            response = input("Tool already exists. Re-register? [y/N]: ")
            if response.lower() != "y":
                print(f"Existing tool ID: {tool.id}")
                return 0
            print("  Deleting existing tool...")
            client.tools.delete(tool.id)
            print("  Deleted.")
            break

    print()
    print(f"Registering {TOOL_NAME} tool...")
    created_tool = client.tools.create_from_function(
        func=post_slack_channel_reply,
        tags=["slack", "outbound", "channel-reply"],
    )

    print()
    print(f"Tool Name: {created_tool.name}")
    print(f"Tool ID:   {created_tool.id}")
    print()

    # Attach to the tasks-agent-sleeptime
    print(f"Attaching to tasks-agent-sleeptime ({AGENT_ID})...")
    agent = client.agents.retrieve(AGENT_ID)
    current_tool_ids = [t.id for t in agent.tools]

    if created_tool.id not in current_tool_ids:
        current_tool_ids.append(created_tool.id)
        client.agents.modify(AGENT_ID, tool_ids=current_tool_ids)
        print("  Attached successfully.")
    else:
        print("  Already attached.")

    print()
    print("Done!")
    print()
    print(f"Tool ID: {created_tool.id}")
    print()
    print("Environment variables needed in Letta container:")
    print("  SLACK_MCP_XOXP_TOKEN (user token — already configured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
