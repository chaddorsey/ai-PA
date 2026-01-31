#!/usr/bin/env python3
"""
Register and Attach Smart Meeting Search Tools to Letta Agent

This script registers and attaches the meeting search tools to the Granola agent:
- search_meetings_smart: Intelligent meeting search with date parsing and filtering
- get_meeting_details: Retrieve full meeting transcript by ID
- list_participants: List available participants for filtering

Target Agent: agent-398b4f6c-6afa-493f-8063-897c6b171a0d (Granola agent)
"""

import os
import sys
import inspect
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
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Import the tools
from meeting_search_tool import search_meetings_smart, get_meeting_details, list_participants

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
GRANOLA_AGENT_ID = os.getenv("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")

# Tools with their functions
TOOLS = [
    ("search_meetings_smart", search_meetings_smart),
    ("get_meeting_details", get_meeting_details),
    ("list_participants", list_participants),
]


def get_function_source(func):
    """Get the source code for a function."""
    return inspect.getsource(func)


def main():
    """Register and attach meeting search tools to the Granola agent."""

    print(f"{'='*60}")
    print("Register and Attach Meeting Search Tools")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Target Agent: {GRANOLA_AGENT_ID}\n")

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")

        # Register each tool
        print("Registering tools...\n")

        registered_tools = []
        for tool_name, tool_func in TOOLS:
            print(f"→ {tool_name}...")

            try:
                # Check if tool already exists
                existing_tools = client.tools.list()
                tools_list = existing_tools.items if hasattr(existing_tools, 'items') else existing_tools

                existing_tool = None
                for t in tools_list:
                    t_name = t.name if hasattr(t, 'name') else t.get('name')
                    if t_name == tool_name:
                        existing_tool = t
                        break

                if existing_tool:
                    # Update existing tool
                    tool_id = existing_tool.id if hasattr(existing_tool, 'id') else existing_tool.get('id')
                    print(f"  → Found existing tool (ID: {tool_id})")

                    # Delete and recreate to update source code
                    try:
                        client.tools.delete(tool_id=tool_id)
                        print(f"  → Deleted old version")
                    except Exception as e:
                        print(f"  → Could not delete: {e}")

                # Create new tool with source code
                source_code = get_function_source(tool_func)
                tool = client.tools.create(
                    source_code=source_code,
                    source_type="python",
                    tags=["meeting-search", "granola"]
                )
                tool_id = tool.id if hasattr(tool, 'id') else tool.get('id')
                print(f"  ✓ Registered (ID: {tool_id})")
                registered_tools.append((tool_name, tool_id))

            except Exception as e:
                print(f"  ✗ Error: {e}")
                import traceback
                traceback.print_exc()

        print()

        # Attach tools to agent
        print(f"Attaching tools to agent {GRANOLA_AGENT_ID}...\n")

        attached_count = 0
        for tool_name, tool_id in registered_tools:
            print(f"→ {tool_name}...")

            try:
                client.agents.tools.attach(
                    agent_id=GRANOLA_AGENT_ID,
                    tool_id=tool_id
                )
                print(f"  ✓ Attached")
                attached_count += 1

            except Exception as e:
                error_str = str(e).lower()
                if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                    print(f"  → Already attached")
                    attached_count += 1
                else:
                    print(f"  ✗ Error: {e}")

        print(f"\n{'='*60}")
        print("✓ Setup Complete")
        print(f"{'='*60}\n")

        print(f"Registered: {len(registered_tools)}/{len(TOOLS)} tools")
        print(f"Attached: {attached_count}/{len(registered_tools)} tools")

        print("\n--- Usage Examples ---\n")
        print('search_meetings_smart(query="budget discussions", participants="leslie,william")')
        print('search_meetings_smart(date_range="last-week", project="dst")')
        print('search_meetings_smart(meeting_type="1on1", scope="internal", limit=5)')
        print('get_meeting_details(meeting_id="f2d5b455-8f1b-4c4b-843b-8ec4958fec7b")')
        print('list_participants()')

        print("\n--- Supported Date Ranges ---\n")
        print("Relative: today, yesterday, last-week, this-week, last-month, this-month")
        print("Days: last-7-days, last-30-days")
        print("Absolute: 2025-05 (month), 2025-05-15 (day)")

        print("\n--- Supported Projects ---\n")
        print("dst, codap, grapher, itsi, leadership, research, external-partners")
        print("(Add more in meeting_search_tool.py PROJECT_CONTEXT_MAP)")

        return 0 if attached_count == len(TOOLS) else 1

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
