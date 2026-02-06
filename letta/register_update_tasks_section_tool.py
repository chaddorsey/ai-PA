#!/usr/bin/env python3
"""
Register update_tasks_section Tool with Letta

This script registers the update_tasks_section tool that allows agents to
curate/replace their entire section in the shared extracted_tasks memory block.
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

from update_tasks_section_tool import update_tasks_section


def main():
    print("=" * 70)
    print("Register update_tasks_section Tool")
    print("=" * 70)
    print()

    # Initialize Letta client
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    print("Checking for existing update_tasks_section tool...")
    try:
        existing_tools = client.tools.list()
        for tool in existing_tools:
            if tool.name == "update_tasks_section":
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
    print("Registering update_tasks_section tool...")

    try:
        # Register the tool
        created_tool = client.tools.create_from_function(
            func=update_tasks_section,
            tags=["memory", "tasks", "concurrent-safe", "shared-block", "curation"]
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
        print("This tool allows agents to:")
        print("  - Replace their entire tasks section with curated content")
        print("  - Reorganize, prioritize, or update tasks")
        print("  - Remove completed tasks")
        print("  - Auto-creates section if it doesn't exist")
        print()
        print("Next steps:")
        print("  1. Attach to PA-Web and sleeptime agents:")
        print("     python letta/attach_update_tasks_section_to_agents.py")
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
