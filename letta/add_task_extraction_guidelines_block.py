#!/usr/bin/env python3
"""
Add task_extraction_tool_use_guidelines Block to Agents

This script creates and attaches a shared guidelines block to all agents
that have the extracted_tasks tools, providing clear instructions on how
to use the shared memory system.
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

GUIDELINES_CONTENT = """# Task Extraction Tool Use Guidelines

You share a memory block called extracted_tasks with other agents. The memory block tabulates tasks for Chad that you and other agents extract from a variety of sources.

## SHARED MEMORY RULES:

1. **Your section**: === {agent_name} ({agent_id}) ===
2. **Add updates**: add_extracted_tasks("Your extracted task")
3. **Modify your section**: update_tasks_section("Your updated section")
4. **Read others**: Check extracted_tasks memory block
5. **NEVER modify other agents' sections**
6. **NEVER use memory_replace on extracted_tasks**

## Tool Usage

### add_extracted_tasks
Use for quick task additions. Each call appends a new task with timestamp:
```
add_extracted_tasks("Review budget proposal by Friday")
```

### update_tasks_section
Use to reorganize, prioritize, or curate your entire section:
```
update_tasks_section(\"\"\"
HIGH PRIORITY:
- [2026-02-05 14:30] Review budget by Friday (IN PROGRESS)

COMPLETED:
- [2026-02-05 14:35] Email team about Q2 planning ✓
\"\"\")
```

## Best Practices

- **Accumulate throughout the day** with add_extracted_tasks
- **Curate periodically** with update_tasks_section to organize and remove completed tasks
- **Check the extracted_tasks block** to see what other agents have extracted
- **Never overwrite** content outside your section boundaries
- **Use timestamps** in format [YYYY-MM-DD HH:MM] for context
"""


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Add task_extraction_tool_use_guidelines Block")
    print("=" * 70)
    print()
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Initialize Letta client
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Find or create the guidelines block
    print("Finding or creating task_extraction_tool_use_guidelines block...")
    blocks = client.blocks.list()
    guidelines_block = None

    for block in blocks:
        if block.label == "task_extraction_tool_use_guidelines":
            guidelines_block = block
            print(f"  Found existing block: {block.id}")
            break

    if not guidelines_block:
        print("  Creating new block...")
        if not dry_run:
            guidelines_block = client.blocks.create(
                label="task_extraction_tool_use_guidelines",
                value=GUIDELINES_CONTENT,
                limit=5000
            )
            print(f"  Created: {guidelines_block.id}")
        else:
            print("  Would create block (dry run)")

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

            # Check if block already attached
            agent_blocks = client.agents.blocks.list(agent.id)
            block_attached = any(b.label == "task_extraction_tool_use_guidelines" for b in agent_blocks)

            if block_attached:
                print("  Block: Already attached")
                results["already_attached"].append(agent.name)
            else:
                if not dry_run and guidelines_block:
                    client.agents.blocks.attach(agent.id, guidelines_block.id)
                    print("  Block: Attached ✓")
                    results["attached"].append(agent.name)
                else:
                    print("  Block: Would attach (dry run)")

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
        print(f"Block attached to {len(results['attached'])} agents:")
        for name in results["attached"]:
            print(f"  ✓ {name}")
        print()

    if results["already_attached"]:
        print(f"Block already on {len(results['already_attached'])} agents")
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

    print("Guidelines provide:")
    print("  - Clear rules for shared memory usage")
    print("  - Tool usage instructions")
    print("  - Best practices for collaboration")

    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
