#!/usr/bin/env python3
"""Register meeting processing tools and attach to the Granola agent."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

from meeting_scan_tool import scan_meeting_notes
from meeting_followup_tool import prepare_meeting_followup

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

TOOLS = [
    (scan_meeting_notes, ["meeting", "scan", "task-extraction"]),
    (prepare_meeting_followup, ["meeting", "followup", "email", "draft"]),
]


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {AGENT_ID}")
    print()

    client = Letta(base_url=LETTA_BASE)

    for func, tags in TOOLS:
        name = func.__name__
        print(f"--- {name} ---")

        # Check for existing
        for tool in client.tools.list():
            if tool.name == name:
                print(f"  Existing tool found: {tool.id}")
                response = input("  Re-register? [y/N]: ")
                if response.lower() != "y":
                    print("  Skipped.")
                    # Still try to attach
                    try:
                        client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool.id)
                        print(f"  Attached {tool.id} to agent.")
                    except Exception as e:
                        print(f"  Attach: {e}")
                    continue
                client.tools.delete(tool.id)
                print("  Deleted old version.")
                break

        # Register
        created = client.tools.create_from_function(func=func, tags=tags)
        print(f"  Registered: {created.id}")

        # Attach
        try:
            client.agents.tools.attach(agent_id=AGENT_ID, tool_id=created.id)
            print(f"  Attached to agent.")
        except Exception as e:
            print(f"  Attach: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
