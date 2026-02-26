#!/usr/bin/env python3
"""
Register recall_activity Tool with Letta

Registers the recall_activity tool and attaches it to the main agent,
enabling cross-interface activity search in archival memory.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python3 letta/register_recall_activity_tool.py
"""

import os
import sys

# Add letta directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from awareness_tools.recall_activity import recall_activity

MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


def main():
    print("=" * 70)
    print("Register recall_activity Tool")
    print("=" * 70)
    print()

    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print(f"Main Agent ID:  {MAIN_AGENT_ID}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    tool_id = None
    print("Checking for existing recall_activity tool...")
    try:
        existing_tools = client.tools.list()
        for tool in existing_tools:
            if tool.name == "recall_activity":
                print(f"  Found existing tool: {tool.id}")
                response = input("Tool already exists. Re-register? [y/N]: ")
                if response.lower() != 'y':
                    print("Skipping registration.")
                    tool_id = tool.id
                    break

                print("  Deleting existing tool...")
                client.tools.delete(tool.id)
                print("  Deleted.")
                break
    except Exception as e:
        print(f"  Error checking existing tools: {e}")
        print("  Proceeding with registration...")

    # Register tool if needed
    if not tool_id:
        print()
        print("Registering recall_activity tool...")

        try:
            created_tool = client.tools.create_from_function(
                func=recall_activity,
                tags=["awareness", "cross-agent", "archival"],
            )
            tool_id = created_tool.id

            print()
            print("REGISTERED")
            print(f"  Tool Name: {created_tool.name}")
            print(f"  Tool ID: {created_tool.id}")
            print(f"  Tags: {', '.join(created_tool.tags or [])}")

        except Exception as e:
            print()
            print("REGISTRATION FAILED")
            print(f"  Error: {e}")
            import traceback
            print(traceback.format_exc())
            return 1

    # Attach to main agent
    print()
    print(f"Attaching to main agent ({MAIN_AGENT_ID})...")
    try:
        client.agents.tools.attach(agent_id=MAIN_AGENT_ID, tool_id=tool_id)
        print("  Attached successfully")
    except Exception as e:
        if "already" in str(e).lower():
            print("  Already attached")
        else:
            print(f"  Error attaching: {e}")
            return 1

    print()
    print("=" * 70)
    print("Done")
    print("=" * 70)
    print()
    print("The main agent can now use recall_activity() to search for")
    print("cross-interface activity in its archival memory.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
