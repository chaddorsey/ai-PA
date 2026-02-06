#!/usr/bin/env python3
"""
Attach add_extracted_tasks Tool to All Agents

This script attaches the add_extracted_tasks tool to all agents and ensures
they have the shared extracted_tasks memory block.
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


def main():
    dry_run = "--dry-run" in sys.argv
    specific_agent = None

    # Check for specific agent ID argument
    for arg in sys.argv[1:]:
        if arg.startswith("agent-"):
            specific_agent = arg
            break

    print("=" * 70)
    print("Attach add_extracted_tasks Tool to Agents")
    print("=" * 70)
    print()
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    if specific_agent:
        print(f"Target: Specific agent ({specific_agent})")
    else:
        print("Target: All agents")
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
        print("ERROR: add_extracted_tasks tool not found")
        print("Run: python letta/register_extracted_tasks_tool.py")
        return 1

    print()

    # Find or create shared extracted_tasks block
    print("Finding or creating shared extracted_tasks block...")
    blocks = client.blocks.list()
    extracted_tasks_block = None

    for block in blocks:
        if block.label == "extracted_tasks":
            extracted_tasks_block = block
            print(f"  Found existing block: {block.id}")
            break

    if not extracted_tasks_block:
        print("  Creating new extracted_tasks block...")
        initial_content = """# Extracted Tasks

This is a shared memory block where agents can contribute tasks they've extracted
from conversations, documents, or other sources.

Each agent adds tasks under their own section header:
=== Agent Name (agent_id) ===

Tasks are added using the add_extracted_tasks tool, which is concurrent-safe.

"""
        if not dry_run:
            extracted_tasks_block = client.blocks.create(
                label="extracted_tasks",
                value=initial_content
            )
            print(f"  Created: {extracted_tasks_block.id}")
        else:
            print("  Would create extracted_tasks block (dry run)")

    print()

    # Get all agents or specific agent
    if specific_agent:
        print(f"Fetching specific agent: {specific_agent}...")
        try:
            agent = client.agents.retrieve(specific_agent)
            agents = [agent]
            print(f"  Found: {agent.name}")
        except Exception as e:
            print(f"  ERROR: Could not retrieve agent {specific_agent}: {e}")
            return 1
    else:
        print("Fetching all agents...")
        agents = client.agents.list()
        print(f"  Found {len(agents)} agents")

    print()

    # Process each agent
    results = {
        "tool_attached": [],
        "tool_already_attached": [],
        "block_attached": [],
        "block_already_attached": [],
        "errors": []
    }

    for agent in agents:
        print(f"Processing: {agent.name} ({agent.id[:8]})")

        try:
            # Check if tool already attached
            agent_tools = client.agents.tools.list(agent.id)
            tool_attached = any(t.id == extracted_tasks_tool.id for t in agent_tools)

            if tool_attached:
                print("  Tool: Already attached")
                results["tool_already_attached"].append(agent.name)
            else:
                if not dry_run:
                    client.agents.tools.attach(agent.id, extracted_tasks_tool.id)
                    print("  Tool: Attached ✓")
                    results["tool_attached"].append(agent.name)
                else:
                    print("  Tool: Would attach (dry run)")

            # Check if block already attached
            agent_blocks = client.agents.blocks.list(agent.id)
            block_attached = any(b.label == "extracted_tasks" for b in agent_blocks)

            if block_attached:
                print("  Block: Already attached")
                results["block_already_attached"].append(agent.name)
            else:
                if not dry_run and extracted_tasks_block:
                    client.agents.blocks.attach(agent.id, extracted_tasks_block.id)
                    print("  Block: Attached ✓")
                    results["block_attached"].append(agent.name)
                else:
                    print("  Block: Would attach (dry run)")

        except Exception as e:
            print(f"  ERROR: {e}")
            results["errors"].append(f"{agent.name}: {str(e)}")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    if results["tool_attached"]:
        print(f"Tool attached to {len(results['tool_attached'])} agents:")
        for name in results["tool_attached"][:5]:
            print(f"  ✓ {name}")
        if len(results["tool_attached"]) > 5:
            print(f"  ... and {len(results['tool_attached']) - 5} more")
        print()

    if results["tool_already_attached"]:
        print(f"Tool already on {len(results['tool_already_attached'])} agents")
        print()

    if results["block_attached"]:
        print(f"Block attached to {len(results['block_attached'])} agents:")
        for name in results["block_attached"][:5]:
            print(f"  ✓ {name}")
        if len(results["block_attached"]) > 5:
            print(f"  ... and {len(results['block_attached']) - 5} more")
        print()

    if results["block_already_attached"]:
        print(f"Block already on {len(results['block_already_attached'])} agents")
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

    print("Agents can now use: add_extracted_tasks(task_description=\"...\")")

    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
