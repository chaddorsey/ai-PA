#!/usr/bin/env python3
"""
Register process_drive_task_queue Tool with Letta

Registers and attaches the drive task queue processing tool to the
Docs & Transcripts agent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from drive_task_queue_tool import process_drive_task_queue

DOCS_AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"
TOOL_NAME = "process_drive_task_queue"


def main():
    print("=" * 70)
    print("Register process_drive_task_queue Tool")
    print("=" * 70)

    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")

    client = Letta(base_url=LETTA_BASE)

    # Check if tool already exists
    print(f"\nChecking for existing {TOOL_NAME} tool...")
    existing_tools = client.tools.list()
    for tool in existing_tools:
        if tool.name == TOOL_NAME:
            print(f"  Found existing tool: {tool.id}")
            response = input("Tool already exists. Re-register? [y/N]: ")
            if response.lower() != "y":
                print(f"Keeping existing tool: {tool.id}")
                return 0
            print("  Deleting existing tool...")
            client.tools.delete(tool.id)
            print("  Deleted.")
            break

    # Register
    print(f"\nRegistering {TOOL_NAME} tool...")
    try:
        created_tool = client.tools.create_from_function(
            func=process_drive_task_queue,
            tags=["drive", "tasks", "comments", "queue"],
        )
        print(f"  Tool ID: {created_tool.id}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        print(traceback.format_exc())
        return 1

    # Attach to Docs & Transcripts agent
    print(f"\nAttaching to Docs & Transcripts agent ({DOCS_AGENT_ID[:12]}...)...")
    try:
        agent_tools = client.agents.tools.list(DOCS_AGENT_ID)
        already_attached = any(t.name == TOOL_NAME for t in agent_tools)
        if already_attached:
            print("  Tool already attached")
        else:
            client.agents.tools.attach(DOCS_AGENT_ID, created_tool.id)
            print("  Tool attached")
    except Exception as e:
        print(f"  ERROR attaching: {e}")
        return 1

    print(f"\nDone. Tool ID: {created_tool.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
