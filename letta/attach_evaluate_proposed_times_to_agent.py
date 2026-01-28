#!/usr/bin/env python3
"""
Attach Evaluate Proposed Times Tool to Letta Agent

This script attaches the Evaluate_Proposed_Times tool to a Letta agent
for evaluating externally-proposed meeting time windows.
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
DEFAULT_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
TOOL_NAME = "Evaluate_Proposed_Times"


def get_agent_id() -> str:
    """Get agent ID from environment or use default."""
    # Check for scheduler-specific agent ID first
    agent_id = os.getenv("LETTA_SCHEDULER_AGENT_ID")
    if agent_id:
        return agent_id

    # Fallback to general agent ID
    agent_id = os.getenv("LETTA_AGENT_ID")
    if agent_id:
        return agent_id

    # Use default
    return DEFAULT_AGENT_ID


def find_tool_by_name(client, tool_name: str):
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
    except Exception as e:
        print(f"  Error listing tools: {e}")
        return None


def is_tool_attached(client, agent_id: str, tool_id: str) -> bool:
    """Check if a tool is already attached to an agent."""
    try:
        # Get agent's current tools
        agent = client.agents.get(agent_id=agent_id)
        agent_tools = agent.tool_ids if hasattr(agent, 'tool_ids') else (
            agent.get('tool_ids') if isinstance(agent, dict) else []
        )
        return tool_id in (agent_tools or [])
    except Exception:
        # If we can't check, assume not attached
        return False


def main():
    """Attach Evaluate_Proposed_Times tool to Letta agent."""

    agent_id = get_agent_id()

    print(f"{'='*60}")
    print("Attach Evaluate Proposed Times Tool to Agent")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {agent_id}")

    # Indicate source of agent ID
    if os.getenv("LETTA_SCHEDULER_AGENT_ID"):
        print(f"  (from LETTA_SCHEDULER_AGENT_ID)")
    elif os.getenv("LETTA_AGENT_ID"):
        print(f"  (from LETTA_AGENT_ID)")
    else:
        print(f"  (default)")
    print()

    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        # Find the tool by name
        print(f"Looking for tool: {TOOL_NAME}...")
        tool_id = find_tool_by_name(client, TOOL_NAME)

        if not tool_id:
            print(f"  Tool '{TOOL_NAME}' not found")
            print(f"\nPlease register the tool first by running:")
            print(f"  python3 letta/register_evaluate_proposed_times.py\n")
            return 1

        print(f"  Found tool (ID: {tool_id})")

        # Check if already attached
        if is_tool_attached(client, agent_id, tool_id):
            print(f"\n  Tool already attached to agent")
            print(f"\n{'='*60}")
            print("Attachment Complete (already attached)")
            print(f"{'='*60}\n")
            return 0

        # Attach tool to agent
        print(f"\nAttaching tool to agent {agent_id}...")

        try:
            client.agents.tools.attach(
                agent_id=agent_id,
                tool_id=tool_id
            )
            print(f"  Tool attached successfully")

        except Exception as e:
            error_str = str(e).lower()
            if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                print(f"  Tool already attached to agent")
            else:
                print(f"  Error attaching tool: {e}")
                print(f"\nYou can attach the tool manually in Letta ADE:")
                print(f"  Tool ID: {tool_id}")
                print(f"  Agent ID: {agent_id}")
                import traceback
                traceback.print_exc()
                return 1

        print(f"\n{'='*60}")
        print("Attachment Complete")
        print(f"{'='*60}\n")

        print(f"Agent can now use the {TOOL_NAME} tool!")
        print("\nExample usage scenarios:")
        print('  "A recruiter proposed Tuesday 2-4pm or Wednesday morning.')
        print('   Check which slots work for me and Alex."')
        print()
        print('  "The vendor can meet Thursday 1-3pm except 1:30-2pm.')
        print('   Find the best 30-minute slot for our team."')
        print()
        print('  "Client availability: Friday after 10am, Monday before noon.')
        print('   Which options have no conflicts?"')

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
