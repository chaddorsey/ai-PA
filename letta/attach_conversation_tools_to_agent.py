#!/usr/bin/env python3
"""
Attach Conversation Tools to Scheduler Agent

This script attaches the find_user_blocks and create_user_memory_block tools
to the scheduler agent, enabling multi-user conversation isolation.
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
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
# Default to scheduler agent ID
SCHEDULER_AGENT_ID = os.getenv(
    "LETTA_SCHEDULER_AGENT_ID",
    os.getenv("LETTA_AGENT_ID", "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d")
)

# Tools to attach. lookup_staff removed 2026-05-30 — see Phase 4 of
# docs/followups/2026-05-30-strip-letta-identities.md. People lookups are
# now canonical-backed; agents do them via Bash + curl per the
# canonical_reference_protocol.
CONVERSATION_TOOLS = ["find_user_blocks", "create_user_memory_block"]


def find_tool_id(client, tool_name):
    """Find tool ID by name."""
    try:
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result

        for tool in tools:
            name = tool.name if hasattr(tool, 'name') else (
                tool.get("name") if isinstance(tool, dict) else None
            )
            tool_id = tool.id if hasattr(tool, 'id') else (
                tool.get("id") if isinstance(tool, dict) else None
            )

            if name == tool_name:
                return tool_id

        return None

    except Exception as e:
        print(f"  ✗ Error listing tools: {e}")
        return None


def attach_tool(client, agent_id, tool_name, tool_id):
    """Attach a tool to an agent."""
    try:
        client.agents.tools.attach(
            agent_id=agent_id,
            tool_id=tool_id
        )
        print(f"  ✓ Attached: {tool_name}")
        return True

    except Exception as e:
        error_str = str(e).lower()
        if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
            print(f"  → Already attached: {tool_name}")
            return True
        else:
            print(f"  ✗ Error attaching {tool_name}: {e}")
            return False


def main():
    """Attach conversation tools to scheduler agent."""

    print(f"{'='*60}")
    print("Attach Conversation Tools to Scheduler Agent")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Scheduler Agent ID: {SCHEDULER_AGENT_ID}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")

        # Verify agent exists
        try:
            agent = client.agents.retrieve(agent_id=SCHEDULER_AGENT_ID)
            agent_name = agent.name if hasattr(agent, 'name') else 'Unknown'
            print(f"✓ Agent found: {agent_name}\n")
        except Exception as e:
            print(f"❌ Agent not found: {SCHEDULER_AGENT_ID}")
            print(f"   Error: {e}")
            return 1

        print("Looking for conversation tools...")
        attached = 0
        missing = []

        for tool_name in CONVERSATION_TOOLS:
            tool_id = find_tool_id(client, tool_name)

            if not tool_id:
                print(f"  ✗ Tool not found: {tool_name}")
                missing.append(tool_name)
                continue

            print(f"  ✓ Found: {tool_name} (ID: {tool_id})")

            if attach_tool(client, SCHEDULER_AGENT_ID, tool_name, tool_id):
                attached += 1

        print(f"\n{'='*60}")
        print("Attachment Complete")
        print(f"{'='*60}\n")

        if missing:
            print(f"⚠️  {len(missing)} tool(s) not found:")
            for name in missing:
                print(f"   - {name}")
            print("\nPlease register tools first by running:")
            print("  python3 letta/register_conversation_tools.py\n")
            return 1

        print(f"✓ {attached} tool(s) attached to scheduler agent")
        print("\nThe scheduler agent can now:")
        print("  - Discover user memory blocks via find_user_blocks")
        print("  - Create new preference blocks via create_user_memory_block")
        print("  - (staff lookups: use Bash + canonical curl per canonical_reference_protocol)")
        print("\nMulti-user conversation isolation is now enabled!\n")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
