#!/usr/bin/env python3
"""
Register Solo Availability Tool with Letta Agent

This script registers the find_my_availability tool with Letta so agents
can handle simple availability queries for a single user.
"""

import os
import sys
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Load from project root .env file
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, skip
except Exception:
    pass  # .env file doesn't exist or can't be loaded

# Add letta directory to path so we can import the tool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

from solo_availability_tool import find_my_availability

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

def main():
    """Register solo availability tool with Letta."""

    print(f"{'='*60}")
    print("Solo Availability Tool Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}\n")

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")

        # Register the tool
        tool_name = "find_my_availability"

        print(f"Registering tool: {tool_name}\n")

        try:
            # Try create_from_function first (newer API)
            try:
                created_tool = client.tools.create_from_function(
                    func=find_my_availability,
                    tags=["scheduling", "availability", "calendar", "solo", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                # Handle both dict and Pydantic model responses
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Find available time slots for a single user")

            except AttributeError:
                # Fallback to create_tool if create_from_function doesn't exist
                created_tool = client.create_tool(
                    func=find_my_availability,
                    name=tool_name,
                    tags=["scheduling", "availability", "calendar", "solo", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Find available time slots for a single user")

            print(f"\n{'='*60}")
            print("Registration Complete")
            print(f"{'='*60}\n")

            print("✓ Tool registered successfully")
            print("\nTool Details:")
            print("  Name: find_my_availability")
            print("  Purpose: Find available time slots in a user's calendar")
            print("  Inputs:")
            print("    - user_id: User's email address")
            print("    - duration_minutes: Length of meeting slot (15-180)")
            print("    - date_range: Time period (e.g., 'today', 'this week', 'next Monday')")
            print("    - time_preference: morning/afternoon/evening (optional)")
            print("    - max_results: Number of slots to return (default 10)")
            print("  Outputs:")
            print("    - status: 'ok', 'no_availability', or 'error'")
            print("    - available_slots: List of available time slots")
            print("    - summary: Human-readable summary")
            print("\nTo attach this tool to the Calendar Agent, run:")
            print(f"  python3 attach_solo_availability_to_agent.py\n")

            return 0

        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  → Tool already exists: {tool_name}")
                print("\nTo update the tool, delete it first and re-run this script.")
                return 0
            else:
                print(f"  ✗ Error registering {tool_name}: {e}")
                import traceback
                traceback.print_exc()
                return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
