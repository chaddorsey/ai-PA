#!/usr/bin/env python3
"""Register process_email_task_queue tool with Letta and attach to email-agent."""

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

from email_task_queue_tool import process_email_task_queue

EMAIL_AGENT_ID = "agent-b4928949-8012-4436-a3c7-a9e510785147"


def main():
    print("=" * 60)
    print("Register process_email_task_queue Tool")
    print("=" * 60)

    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    client = Letta(base_url=LETTA_BASE)

    # Check for existing tool
    print("Checking for existing tool...")
    for tool in client.tools.list():
        if tool.name == "process_email_task_queue":
            print(f"  Found existing tool: {tool.id}")
            response = input("  Re-register? [y/N]: ")
            if response.lower() != "y":
                print("Skipping registration.")
                return 0
            client.tools.delete(tool.id)
            print("  Deleted.")
            break

    # Register
    print("\nRegistering tool...")
    created = client.tools.create_from_function(
        func=process_email_task_queue,
        tags=["email", "task-queue", "gmail"],
    )
    print(f"  Tool Name: {created.name}")
    print(f"  Tool ID:   {created.id}")

    # Attach to email-agent
    print(f"\nAttaching to email-agent ({EMAIL_AGENT_ID})...")
    try:
        client.agents.tools.attach(agent_id=EMAIL_AGENT_ID, tool_id=created.id)
        print("  Attached successfully.")
    except Exception as e:
        print(f"  Attach failed (may already be attached): {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
