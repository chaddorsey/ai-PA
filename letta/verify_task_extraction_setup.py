#!/usr/bin/env python3
"""
Verify Task Extraction System Setup

Checks that all 10 agents have:
- add_extracted_tasks tool
- update_tasks_section tool
- extracted_tasks memory block
- task_extraction_tool_use_guidelines block
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

# PA-Web + Sleeptime agent IDs
AGENT_IDS = [
    "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",  # Calendar
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",  # Tasks
    "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",  # Samantha
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",  # Pulse Monitor
    "agent-b4928949-8012-4436-a3c7-a9e510785147",  # Email
    "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",  # Documents
    "agent-fd0cd292-6a10-4b7f-abb3-d7732eae932c",  # pulse-sleeptime_copy
    "agent-feb2c0f7-4c70-4240-bc1d-21ad12319fc9",  # email-sleeptime
    "agent-62edcfac-2cc7-41a5-a3c2-d417da393397",  # tasks-sleeptime
    "agent-66c4a151-7182-4cfc-9195-68b2e34d0847",  # pulse-sleeptime
]

PAWEB_IDS = {
    "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",
}


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    print("=" * 80)
    print("EXTRACTED TASKS SYSTEM - COMPLETE VERIFICATION")
    print("=" * 80)
    print()

    all_good = True

    for agent_id in AGENT_IDS:
        agent = client.agents.retrieve(agent_id)
        tools = client.agents.tools.list(agent_id)
        blocks = client.agents.blocks.list(agent_id)

        has_add = any(t.name == "add_extracted_tasks" for t in tools)
        has_update = any(t.name == "update_tasks_section" for t in tools)
        has_tasks_block = any(b.label == "extracted_tasks" for b in blocks)
        has_guidelines = any(b.label == "task_extraction_tool_use_guidelines" for b in blocks)

        complete = all([has_add, has_update, has_tasks_block, has_guidelines])
        status = "✓✓✓✓" if complete else "✗   "
        agent_type = "[PA-Web   ]" if agent_id in PAWEB_IDS else "[Sleeptime]"

        t1 = "✓" if has_add else "✗"
        t2 = "✓" if has_update else "✗"
        b1 = "✓" if has_tasks_block else "✗"
        b2 = "✓" if has_guidelines else "✗"

        print(f"{status} {agent_type} {agent.name:35s} T1:{t1} T2:{t2} B1:{b1} B2:{b2}")

        if not complete:
            all_good = False

    print()
    print("Legend:")
    print("  T1 = add_extracted_tasks tool")
    print("  T2 = update_tasks_section tool")
    print("  B1 = extracted_tasks block")
    print("  B2 = task_extraction_tool_use_guidelines block")
    print()

    if all_good:
        print("✓ All 10 agents have complete task extraction system setup!")
    else:
        print("✗ Some agents are missing components")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
