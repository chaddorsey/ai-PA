#!/usr/bin/env python3
"""
Remove add_extracted_tasks Tool from Non-PA-Web Agents

This script removes the add_extracted_tasks tool and extracted_tasks block
from agents that are not used in pa-web, keeping the system clean.

PA-Web uses these 6 agents:
- Calendar Agent (agent-892a2d58-b9f6-4baf-84f3-c431fe46487d)
- Tasks Agent (agent-dd15479e-6543-400e-8463-b2a48b13cd4a)
- Main Assistant/Samantha (agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a)
- Pulse Monitor (agent-2ed14ef4-6289-453a-ae27-290b6ed196b8)
- Email Agent (agent-b4928949-8012-4436-a3c7-a9e510785147)
- Documents Agent (agent-398b4f6c-6afa-493f-8063-897c6b171a0d)
"""

import os
import sys

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

# PA-Web agents (from pa-web-ui/static/js/chat.js)
PAWEB_AGENT_IDS = {
    "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",  # Calendar Agent
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",  # Tasks Agent
    "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",  # Main Assistant (Samantha)
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",  # Pulse Monitor
    "agent-b4928949-8012-4436-a3c7-a9e510785147",  # Email Agent
    "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",  # Documents Agent
}


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Remove add_extracted_tasks from Non-PA-Web Agents")
    print("=" * 70)
    print()
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Initialize Letta client
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Find the add_extracted_tasks tool
    print("Finding add_extracted_tasks tool...")
    tools = client.tools.list()
    extracted_tasks_tool = None

    for tool in tools:
        if tool.name == "add_extracted_tasks":
            extracted_tasks_tool = tool
            print(f"  Found: {tool.id}")
            break

    if not extracted_tasks_tool:
        print("  Tool not found - nothing to remove")
        return 0

    print()

    # Get all agents
    print("Fetching all agents...")
    agents = client.agents.list()
    print(f"  Found {len(agents)} agents")
    print()

    # Separate PA-Web agents from others
    paweb_agents = []
    non_paweb_agents = []

    for agent in agents:
        if agent.id in PAWEB_AGENT_IDS:
            paweb_agents.append(agent)
        else:
            non_paweb_agents.append(agent)

    print(f"PA-Web agents: {len(paweb_agents)}")
    for agent in paweb_agents:
        print(f"  ✓ {agent.name} ({agent.id[:8]})")
    print()

    print(f"Non-PA-Web agents (will remove tool): {len(non_paweb_agents)}")
    for agent in non_paweb_agents[:5]:
        print(f"  - {agent.name} ({agent.id[:8]})")
    if len(non_paweb_agents) > 5:
        print(f"  ... and {len(non_paweb_agents) - 5} more")
    print()

    if not non_paweb_agents:
        print("No non-PA-Web agents to clean up")
        return 0

    if dry_run:
        print("DRY RUN - Would remove tool from above agents")
        return 0

    # Confirm before proceeding
    response = input(f"Remove tool from {len(non_paweb_agents)} non-PA-Web agents? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    print()
    print("Removing tool from non-PA-Web agents...")
    print()

    results = {
        "tool_removed": [],
        "tool_not_attached": [],
        "block_detached": [],
        "block_not_attached": [],
        "errors": []
    }

    for agent in non_paweb_agents:
        print(f"Processing: {agent.name} ({agent.id[:8]})")

        try:
            # Check if tool is attached
            agent_tools = client.agents.tools.list(agent.id)
            tool_attached = any(t.id == extracted_tasks_tool.id for t in agent_tools)

            if tool_attached:
                try:
                    client.agents.tools.detach(agent.id, extracted_tasks_tool.id)
                    print("  Tool: Removed ✓")
                    results["tool_removed"].append(agent.name)
                except Exception as e:
                    print(f"  Tool: Error removing - {e}")
                    results["errors"].append(f"{agent.name} (tool): {str(e)}")
            else:
                print("  Tool: Not attached")
                results["tool_not_attached"].append(agent.name)

            # Check if block is attached
            agent_blocks = client.agents.blocks.list(agent.id)
            extracted_tasks_block = None
            for block in agent_blocks:
                if block.label == "extracted_tasks":
                    extracted_tasks_block = block
                    break

            if extracted_tasks_block:
                try:
                    client.agents.blocks.detach(agent.id, extracted_tasks_block.id)
                    print("  Block: Detached ✓")
                    results["block_detached"].append(agent.name)
                except Exception as e:
                    print(f"  Block: Error detaching - {e}")
                    results["errors"].append(f"{agent.name} (block): {str(e)}")
            else:
                print("  Block: Not attached")
                results["block_not_attached"].append(agent.name)

        except Exception as e:
            print(f"  ERROR: {e}")
            results["errors"].append(f"{agent.name}: {str(e)}")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    print(f"PA-Web agents (kept tool): {len(paweb_agents)}")
    print()

    if results["tool_removed"]:
        print(f"Tool removed from {len(results['tool_removed'])} agents:")
        for name in results["tool_removed"][:5]:
            print(f"  ✓ {name}")
        if len(results["tool_removed"]) > 5:
            print(f"  ... and {len(results['tool_removed']) - 5} more")
        print()

    if results["block_detached"]:
        print(f"Block detached from {len(results['block_detached'])} agents:")
        for name in results["block_detached"][:5]:
            print(f"  ✓ {name}")
        if len(results["block_detached"]) > 5:
            print(f"  ... and {len(results['block_detached']) - 5} more")
        print()

    if results["tool_not_attached"]:
        print(f"Tool not attached to {len(results['tool_not_attached'])} agents (no action needed)")
        print()

    if results["errors"]:
        print(f"Errors ({len(results['errors'])}):")
        for error in results["errors"]:
            print(f"  ✗ {error}")
        print()

    print("Cleanup complete. Tool now only on PA-Web agents.")

    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
