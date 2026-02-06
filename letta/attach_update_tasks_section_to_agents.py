#!/usr/bin/env python3
"""
Attach update_tasks_section Tool to PA-Web and Sleeptime Agents

This script attaches the update_tasks_section tool to the same 10 agents that
have add_extracted_tasks (6 PA-Web + 4 sleeptime agents).
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

# Sleeptime agents (associated with PA-Web agents)
SLEEPTIME_AGENT_IDS = {
    "agent-fd0cd292-6a10-4b7f-abb3-d7732eae932c",  # pulse-monitor-agent-sleeptime_copy
    "agent-feb2c0f7-4c70-4240-bc1d-21ad12319fc9",  # email-agent-sleeptime
    "agent-62edcfac-2cc7-41a5-a3c2-d417da393397",  # tasks-agent-sleeptime
    "agent-66c4a151-7182-4cfc-9195-68b2e34d0847",  # pulse-monitor-agent-sleeptime
}


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Attach update_tasks_section Tool")
    print("=" * 70)
    print()
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Initialize Letta client
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Find the update_tasks_section tool
    print("Finding update_tasks_section tool...")
    tools = client.tools.list()
    update_tool = None

    for tool in tools:
        if tool.name == "update_tasks_section":
            update_tool = tool
            print(f"  Found: {tool.id}")
            break

    if not update_tool:
        print("ERROR: update_tasks_section tool not found")
        print("Run: python letta/register_update_tasks_section_tool.py")
        return 1

    print()

    # Combine all agent IDs
    all_agent_ids = PAWEB_AGENT_IDS | SLEEPTIME_AGENT_IDS

    print(f"Target agents: {len(all_agent_ids)}")
    print("  - 6 PA-Web agents")
    print("  - 4 Sleeptime agents")
    print()

    # Process each agent
    results = {
        "attached": [],
        "already_attached": [],
        "errors": []
    }

    for agent_id in all_agent_ids:
        try:
            agent = client.agents.retrieve(agent_id)
            print(f"Processing: {agent.name} ({agent.id[:8]})")

            # Check if tool already attached
            agent_tools = client.agents.tools.list(agent.id)
            tool_attached = any(t.id == update_tool.id for t in agent_tools)

            if tool_attached:
                print("  Tool: Already attached")
                results["already_attached"].append(agent.name)
            else:
                if not dry_run:
                    client.agents.tools.attach(agent.id, update_tool.id)
                    print("  Tool: Attached ✓")
                    results["attached"].append(agent.name)
                else:
                    print("  Tool: Would attach (dry run)")

        except Exception as e:
            print(f"  ERROR: {e}")
            results["errors"].append(f"{agent_id[:8]}: {str(e)}")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    if results["attached"]:
        print(f"Tool attached to {len(results['attached'])} agents:")
        for name in results["attached"]:
            print(f"  ✓ {name}")
        print()

    if results["already_attached"]:
        print(f"Tool already on {len(results['already_attached'])} agents")
        print()

    if results["errors"]:
        print(f"Errors ({len(results['errors'])}):")
        for error in results["errors"]:
            print(f"  ✗ {error}")
        print()

    if dry_run:
        print("DRY RUN - No changes applied")
        print("Run without --dry-run to apply changes")
        print()

    print("Agents now have TWO tools for extracted_tasks:")
    print("  1. add_extracted_tasks - Quick task additions (append-only)")
    print("  2. update_tasks_section - Curate entire section (scoped replacement)")

    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
