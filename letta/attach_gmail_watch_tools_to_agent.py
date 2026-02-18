#!/usr/bin/env python3
"""Attach Gmail Watch tools to the Email Agent."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from letta_client import Letta

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
EMAIL_AGENT_ID = os.environ.get("EMAIL_AGENT_ID", "agent-b4928949-8012-4436-a3c7-a9e510785147")

TOOL_NAMES = [
    "watch_gmail_thread",
    "unwatch_gmail_thread",
    "list_watched_gmail_threads",
    "get_gmail_watch_status",
]


def main():
    client = Letta(base_url=LETTA_BASE_URL)

    # Get agent
    agent = client.agents.retrieve(agent_id=EMAIL_AGENT_ID)
    print(f"Agent: {agent.name} ({agent.id})")

    # Get existing tools on agent
    existing_tools = client.agents.tools.list(agent_id=EMAIL_AGENT_ID)
    existing_names = {t.name for t in existing_tools}
    print(f"Agent has {len(existing_names)} existing tools")

    # Find tool IDs by name
    all_tools = client.tools.list()
    tool_map = {t.name: t for t in all_tools}

    attached = 0
    for name in TOOL_NAMES:
        tool = tool_map.get(name)
        if not tool:
            print(f"  WARNING: Tool '{name}' not found in Letta")
            continue

        if name in existing_names:
            print(f"  Already attached: {name}")
        else:
            client.agents.tools.attach(agent_id=EMAIL_AGENT_ID, tool_id=tool.id)
            print(f"  Attached: {name}")
            attached += 1

    print(f"\nAttached {attached} new tools to {agent.name}")


if __name__ == "__main__":
    main()
