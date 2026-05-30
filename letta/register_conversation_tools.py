#!/usr/bin/env python3
"""
Register Conversation Tools with Letta

This script registers the find_user_blocks and create_user_memory_block tools
that enable multi-user conversation isolation in the scheduler agent.

These tools use naming conventions to enable per-user block discovery
and creation, supporting the Letta Conversations API pilot.
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

# Add letta directory to path for conversation_tools imports
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

from conversation_tools.find_user_blocks import find_user_blocks
from conversation_tools.create_user_memory_block import create_user_memory_block
# lookup_staff removed 2026-05-30 (Phase 4 of Letta identities strip-out).
# People lookups now go through canonical (agents-canonical Gitea repo) via
# Bash + curl per docs/.../canonical_reference_protocol.

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def register_tool(client, func, tool_name, tags):
    """Register a single tool with Letta."""
    print(f"Registering: {tool_name}...")

    try:
        try:
            created_tool = client.tools.create_from_function(
                func=func,
                tags=tags
            )
            tool_id = created_tool.id if hasattr(created_tool, 'id') else (
                created_tool.get('id') if isinstance(created_tool, dict) else 'N/A'
            )
            print(f"  ✓ Registered: {tool_name} (ID: {tool_id})")
            return tool_id

        except AttributeError:
            # Fallback to older API
            created_tool = client.create_tool(
                func=func,
                name=tool_name,
                tags=tags
            )
            tool_id = created_tool.id if hasattr(created_tool, 'id') else (
                created_tool.get('id') if isinstance(created_tool, dict) else 'N/A'
            )
            print(f"  ✓ Registered: {tool_name} (ID: {tool_id})")
            return tool_id

    except Exception as e:
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            print(f"  → Already exists: {tool_name}")
            return None
        else:
            print(f"  ✗ Error registering {tool_name}: {e}")
            return None


def main():
    """Register conversation tools with Letta."""

    print(f"{'='*60}")
    print("Conversation Tools Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")

        tools = [
            {
                "func": find_user_blocks,
                "name": "find_user_blocks",
                "tags": ["conversation", "multi-user", "memory", "custom"]
            },
            {
                "func": create_user_memory_block,
                "name": "create_user_memory_block",
                "tags": ["conversation", "multi-user", "memory", "custom"]
            },
        ]

        registered = 0
        for tool in tools:
            result = register_tool(
                client,
                tool["func"],
                tool["name"],
                tool["tags"]
            )
            if result:
                registered += 1

        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")

        print(f"✓ {registered} tool(s) registered")
        print("\nTools registered:")
        print("  1. find_user_blocks - Discover memory blocks for a user")
        print("  2. create_user_memory_block - Create new user preference blocks")
        print("\nTo attach these tools to the scheduler agent, run:")
        print("  python3 letta/attach_conversation_tools_to_agent.py\n")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
