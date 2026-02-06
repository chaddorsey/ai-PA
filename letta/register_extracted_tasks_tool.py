#!/usr/bin/env python3
"""
Register add_extracted_tasks Tool with Letta

This script registers the add_extracted_tasks tool that allows multiple agents
to safely contribute to a shared extracted_tasks memory block without race conditions.
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

from extracted_tasks_tool import add_extracted_tasks


def main():
    print("=" * 70)
    print("Register add_extracted_tasks Tool")
    print("=" * 70)
    print()

    # Initialize Letta client
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    print("Checking for existing add_extracted_tasks tool...")
    try:
        existing_tools = client.tools.list()
        for tool in existing_tools:
            if tool.name == "add_extracted_tasks":
                print(f"  Found existing tool: {tool.id}")
                response = input("Tool already exists. Re-register? [y/N]: ")
                if response.lower() != 'y':
                    print("Skipping registration.")
                    print()
                    print(f"Existing tool ID: {tool.id}")
                    return 0

                # Delete existing tool
                print("  Deleting existing tool...")
                client.tools.delete(tool.id)
                print("  Deleted.")
                break
    except Exception as e:
        print(f"  Error checking existing tools: {e}")
        print("  Proceeding with registration...")

    print()
    print("Registering add_extracted_tasks tool...")

    try:
        # Register the tool
        created_tool = client.tools.create_from_function(
            func=add_extracted_tasks,
            tags=["memory", "tasks", "concurrent-safe", "shared-block"]
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
        print("  1. Create shared extracted_tasks block (if not exists)")
        print("  2. Run: python letta/attach_extracted_tasks_tool_to_agents.py")
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
