#!/usr/bin/env python3
"""
Register Evaluate Proposed Times Tool with Letta Agent

This script registers the Evaluate_Proposed_Times tool with Letta for evaluating
externally-proposed meeting time windows against participant calendars.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

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

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
TOOL_NAME = "Evaluate_Proposed_Times"


def Evaluate_Proposed_Times(
    proposed_times: str,
    participants: str,
    duration_minutes: Optional[int] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate externally-proposed meeting time windows against participant calendars.

    Use this tool when someone external (recruiter, vendor, client) proposes specific
    time windows and you need to check which slots work for your participants. The tool
    fetches calendar data, identifies conflicts, and categorizes slots by feasibility.

    Args:
        proposed_times: Natural language time windows, one per line. Examples:
            "Tuesday 2-4pm"
            "Wednesday morning"
            "Thursday 1pm-3pm except 1:30-2pm"
            "Friday after 10am"
        participants: Comma-separated list of participant email addresses. Example:
            "cdorsey@concord.org,alex@example.com"
        duration_minutes: Meeting duration in minutes. Defaults to 30 if not specified.
            Use this to find slots that can fit the required meeting length.
        timezone: Timezone for interpreting times. Defaults to "America/New_York".
            Use standard timezone names like "America/Los_Angeles", "Europe/London".

    Returns:
        Dictionary with evaluation results containing:
        - status: "ok" on success, "error" on failure
        - clean_slots: List of time slots with NO conflicts (best options)
        - solo_adjust_slots: Slots where only ONE participant has a flexible conflict
        - multi_adjust_slots: Slots where MULTIPLE participants have conflicts
        - no_availability_windows: Original text of windows with no viable slots
        - error_message: Error description if status is "error"

        Each slot contains:
        - start: ISO datetime string
        - end: ISO datetime string
        - display: Human-readable format like "Tue 01/28 2:00PM-2:30PM"
        - conflicts: List of conflict details (for adjust slots)

    Example:
        >>> result = Evaluate_Proposed_Times(
        ...     proposed_times="Tuesday 2-4pm\\nWednesday morning",
        ...     participants="cdorsey@concord.org,alex@example.com",
        ...     duration_minutes=30,
        ...     timezone="America/New_York"
        ... )
        >>> # Returns categorized slots for the agent to present to user
    """
    # ALL IMPORTS INSIDE FUNCTION (Letta requirement)
    import asyncio
    import traceback
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Handle default values for optional parameters
        if duration_minutes is None:
            duration_minutes = 30
        if timezone is None:
            timezone = "America/New_York"

        # Validate inputs
        if not proposed_times or not proposed_times.strip():
            return {
                "status": "error",
                "error_message": "proposed_times is required and cannot be empty"
            }

        if not participants or not participants.strip():
            return {
                "status": "error",
                "error_message": "participants is required and cannot be empty"
            }

        # Import the orchestrator module (inside function for Letta)
        import sys
        import os
        letta_dir = os.path.dirname(os.path.abspath(__file__))
        if letta_dir not in sys.path:
            sys.path.insert(0, letta_dir)

        # Import the async evaluation function
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Run the async function synchronously
        # Handle both running in existing event loop and creating new one
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, create a new thread to run
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    evaluate_proposed_times(
                        proposed_times=proposed_times,
                        participants=participants,
                        duration_minutes=duration_minutes,
                        timezone=timezone
                    )
                )
                result = future.result(timeout=60)
        except RuntimeError:
            # No running event loop, we can use asyncio.run directly
            result = asyncio.run(
                evaluate_proposed_times(
                    proposed_times=proposed_times,
                    participants=participants,
                    duration_minutes=duration_minutes,
                    timezone=timezone
                )
            )

        return result

    except Exception as e:
        logger.exception("Error in Evaluate_Proposed_Times tool")
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }


def find_existing_tool(client, tool_name: str):
    """Find a tool by name and return its ID, or None if not found."""
    try:
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result

        for tool in tools:
            name = tool.name if hasattr(tool, 'name') else (tool.get("name") if isinstance(tool, dict) else None)
            tool_id = tool.id if hasattr(tool, 'id') else (tool.get("id") if isinstance(tool, dict) else None)

            if name == tool_name and tool_id:
                return tool_id
        return None
    except Exception:
        return None


def delete_tool(client, tool_id: str) -> bool:
    """Delete a tool by ID. Returns True if successful."""
    try:
        client.tools.delete(tool_id=tool_id)
        return True
    except Exception as e:
        print(f"  Warning: Could not delete tool {tool_id}: {e}")
        return False


def main():
    """Register Evaluate_Proposed_Times tool with Letta."""

    print(f"{'='*60}")
    print("Evaluate Proposed Times Tool Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Tool Name: {TOOL_NAME}\n")

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        # Check for existing tool and delete if found (for re-registration)
        print(f"Checking for existing tool: {TOOL_NAME}...")
        existing_tool_id = find_existing_tool(client, TOOL_NAME)

        if existing_tool_id:
            print(f"  Found existing tool (ID: {existing_tool_id})")
            print(f"  Deleting for re-registration...")
            if delete_tool(client, existing_tool_id):
                print(f"  Deleted existing tool")
            else:
                print(f"  Warning: Could not delete existing tool, will attempt registration anyway")
        else:
            print(f"  No existing tool found")

        # Register the tool
        print(f"\nRegistering tool: {TOOL_NAME}")

        try:
            created_tool = client.tools.create_from_function(
                func=Evaluate_Proposed_Times,
                tags=["scheduling", "calendar", "evaluation", "meetings", "custom"]
            )

            tool_id = created_tool.id if hasattr(created_tool, 'id') else (
                created_tool.get('id') if isinstance(created_tool, dict) else 'N/A'
            )

            print(f"  Registered successfully")
            print(f"  Tool ID: {tool_id}")

        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  Tool already exists (could not delete and recreate)")
                existing_id = find_existing_tool(client, TOOL_NAME)
                if existing_id:
                    print(f"  Existing Tool ID: {existing_id}")
                return 0
            else:
                print(f"  Error registering tool: {e}")
                import traceback
                traceback.print_exc()
                return 1

        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")

        print("Tool Details:")
        print(f"  Name: {TOOL_NAME}")
        print("  Purpose: Evaluate externally-proposed meeting time windows")
        print("  Inputs:")
        print("    - proposed_times: Natural language time windows (one per line)")
        print("    - participants: Comma-separated list of participant emails")
        print("    - duration_minutes: Meeting duration (optional, default 30)")
        print("    - timezone: Timezone for interpretation (optional, default America/New_York)")
        print("  Outputs:")
        print("    - status: 'ok' or 'error'")
        print("    - clean_slots: Slots with no conflicts")
        print("    - solo_adjust_slots: Slots with one flexible conflict")
        print("    - multi_adjust_slots: Slots with multiple conflicts")
        print("    - no_availability_windows: Windows with no viable slots")

        print("\nTo attach this tool to an agent, run:")
        print("  python3 letta/attach_evaluate_proposed_times_to_agent.py\n")

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
