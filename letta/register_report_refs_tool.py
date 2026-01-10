#!/usr/bin/env python3
"""
Register Report Refs Tool with Letta

This script registers the report_refs tool with your Letta instance
so agents can report actionable references in a structured way.

The routing handler parses tool calls (not free-form text) to extract
references reliably.
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

# Add letta directory to path so we can import the tool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_refs_tool import report_refs

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def main():
    """Register report_refs tool with Letta."""

    print("=" * 60)
    print("Report Refs Tool Registration")
    print("=" * 60)
    print()
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print()

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server")
        print()

        tool_name = "report_refs"
        print(f"Registering tool: {tool_name}")

        try:
            # Try create_from_function first (newer API)
            try:
                created_tool = client.tools.create_from_function(
                    func=report_refs,
                    tags=["refs", "coordination", "handler", "routing"]
                )
            except AttributeError:
                # Fallback to create_tool if create_from_function doesn't exist
                created_tool = client.create_tool(
                    func=report_refs,
                    name=tool_name,
                    tags=["refs", "coordination", "handler", "routing"]
                )

            tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
            print(f"  Tool ID: {tool_id}")
            print()
            print("=" * 60)
            print("Registration Complete")
            print("=" * 60)
            print()
            print("Tool registered successfully!")
            print()
            print("Tool Details:")
            print("  Name: report_refs")
            print("  Purpose: Report actionable references for handler coordination")
            print("  Inputs:")
            print("    - ref_type: Type of resource (calendar_event, task, email, etc.)")
            print("    - ref_id: Unique identifier for the resource")
            print("    - metadata: Optional dict with title, subject, start, etc.")
            print()
            print("To attach this tool to agents, run:")
            print("  python3 attach_report_refs_to_agents.py")
            print()

            return 0

        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  Tool already exists: {tool_name}")
                print()
                print("To update, delete the tool first and re-run this script.")
                return 0
            else:
                print(f"  Error registering {tool_name}: {e}")
                import traceback
                traceback.print_exc()
                return 1

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
