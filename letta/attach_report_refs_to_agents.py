#!/usr/bin/env python3
"""
Attach Report Refs Tool to All Agents

This script attaches the report_refs tool to all configured agents
so they can report actionable references in a structured way.
"""

import os
import sys
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass
except Exception:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client or letta package not found")
        print("Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs to attach tool to
AGENTS = {
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "Main Agent": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}


def main():
    """Attach report_refs tool to all agents."""

    print("=" * 60)
    print("Attach Report Refs Tool to Agents")
    print("=" * 60)
    print()
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agents to update: {len(AGENTS)}")
    print()

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server")
        print()

        # Find the report_refs tool
        print("Finding report_refs tool...")
        tools = client.tools.list()
        report_refs_tool = None

        for tool in tools:
            name = tool.name if hasattr(tool, 'name') else tool.get('name', '')
            if name == "report_refs":
                report_refs_tool = tool
                break

        if not report_refs_tool:
            print("Error: report_refs tool not found!")
            print("Run register_report_refs_tool.py first.")
            return 1

        tool_id = report_refs_tool.id if hasattr(report_refs_tool, 'id') else report_refs_tool.get('id')
        print(f"  Found tool ID: {tool_id}")
        print()

        # Attach to each agent
        attached = 0
        skipped = 0
        failed = 0

        for agent_name, agent_id in AGENTS.items():
            print(f"Processing {agent_name}...")

            try:
                # Get agent's current tools
                agent = client.agents.retrieve(agent_id)
                current_tool_ids = []

                if hasattr(agent, 'tool_ids'):
                    current_tool_ids = agent.tool_ids or []
                elif hasattr(agent, 'tools'):
                    current_tool_ids = [t.id if hasattr(t, 'id') else t.get('id') for t in (agent.tools or [])]

                # Check if already attached
                if tool_id in current_tool_ids:
                    print(f"  Already has report_refs tool")
                    skipped += 1
                    continue

                # Attach the tool
                try:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                except AttributeError:
                    # Older API
                    client.attach_tool(agent_id=agent_id, tool_id=tool_id)

                print(f"  Attached report_refs tool")
                attached += 1

            except Exception as e:
                print(f"  Error: {e}")
                failed += 1

        print()
        print("=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"  Attached: {attached}")
        print(f"  Skipped (already attached): {skipped}")
        print(f"  Failed: {failed}")
        print()

        if failed == 0:
            print("All agents now have the report_refs tool!")
        else:
            print(f"Warning: {failed} agents failed to update")

        return 0 if failed == 0 else 1

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
