#!/usr/bin/env python3
"""
Register retrieve_task_info Tool with Letta

This script registers the retrieve_task_info tool that allows any agent
to look up extracted task source references in the shared archive.
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

from retrieve_task_info_tool import retrieve_task_info


def main():
    print("=" * 70)
    print("Register retrieve_task_info Tool")
    print("=" * 70)
    print()

    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    print("Checking for existing retrieve_task_info tool...")
    try:
        existing_tools = client.tools.list()
        for tool in existing_tools:
            if tool.name == "retrieve_task_info":
                print(f"  Found existing tool: {tool.id}")
                response = input("Tool already exists. Re-register? [y/N]: ")
                if response.lower() != 'y':
                    print("Skipping registration.")
                    print(f"Existing tool ID: {tool.id}")
                    return 0

                print("  Deleting existing tool...")
                client.tools.delete(tool.id)
                print("  Deleted.")
                break
    except Exception as e:
        print(f"  Error checking existing tools: {e}")
        print("  Proceeding with registration...")

    print()
    print("Registering retrieve_task_info tool...")

    try:
        created_tool = client.tools.create_from_function(
            func=retrieve_task_info,
            tags=["memory", "tasks", "archive", "lookup"]
        )

        print()
        print("=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print()
        print(f"Tool Name: {created_tool.name}")
        print(f"Tool ID: {created_tool.id}")
        print(f"Tags: {', '.join(created_tool.tags or [])}")
        print()
        print("Next steps:")
        print("  1. Attach to agents that need task lookup capability")
        print("  2. Update agent guidance blocks to mention this tool")
        print()

        return 0

    except Exception as e:
        print()
        print("=" * 70)
        print("REGISTRATION FAILED")
        print("=" * 70)
        print()
        print(f"Error: {e}")
        print()
        import traceback
        print("Full traceback:")
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
