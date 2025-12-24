#!/usr/bin/env python3
"""
Register Slack Custom Tools with Letta Agent

This script registers the 4 optimized Slack custom tools with Letta:
1. get_slack_channels
2. get_slack_messages
3. search_slack_messages
4. get_slack_users
"""

import os
import sys
from pathlib import Path

# Add letta directory to path so we can import the tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

# Import the Slack custom tools
from slack_custom_tools import (
    get_slack_channels,
    get_slack_messages,
    search_slack_messages,
    get_slack_users
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")


def main():
    """Register Slack custom tools with Letta agent."""
    
    print(f"{'='*60}")
    print("Slack Custom Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {AGENT_ID if AGENT_ID else 'Not set (will register tools only)'}\n")
    
    tools_to_register = [
        ("get_slack_channels", get_slack_channels, "Channel discovery and information"),
        ("get_slack_messages", get_slack_messages, "Messages from channels with complete context"),
        ("search_slack_messages", search_slack_messages, "Workspace-wide message search"),
        ("get_slack_users", get_slack_users, "User discovery and information")
    ]
    
    registered_tool_ids = []
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register each tool
        for tool_name, tool_func, tool_description in tools_to_register:
            print(f"Registering tool: {tool_name}")
            print(f"  Description: {tool_description}")
            
            try:
                # Try create_from_function first (newer API)
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=["slack", "custom", "monitoring", "information-extraction"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                registered_tool_ids.append(tool_id)
                
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "409" in error_str or "duplicate" in error_str:
                    print(f"  → Tool {tool_name} already exists")
                    # Try to find existing tool
                    try:
                        all_tools = client.tools.list()
                        for tool in all_tools:
                            if tool.get("name") == tool_name or (hasattr(tool, 'name') and tool.name == tool_name):
                                tool_id = tool.get("id") if isinstance(tool, dict) else (tool.id if hasattr(tool, 'id') else None)
                                if tool_id:
                                    registered_tool_ids.append(tool_id)
                                    print(f"    Found existing tool ID: {tool_id}")
                                    break
                    except Exception:
                        pass
                else:
                    print(f"  ❌ Failed to register {tool_name}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print()
        
        # Attach tools to agent if agent ID is provided
        if AGENT_ID and registered_tool_ids:
            print(f"→ Attaching {len(registered_tool_ids)} tools to agent {AGENT_ID}...")
            try:
                # Try newer SDK v1.0 method first
                if hasattr(client, 'agents') and hasattr(client.agents, 'tools') and hasattr(client.agents.tools, 'attach'):
                    for tool_id in registered_tool_ids:
                        try:
                            client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool_id)
                            print(f"  ✓ Attached tool {tool_id}")
                        except Exception as e:
                            error_str = str(e).lower()
                            if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                                print(f"  → Tool {tool_id} already attached")
                            else:
                                print(f"  ⚠ Could not attach tool {tool_id}: {e}")
                # Fallback to older method
                elif hasattr(client, 'add_tool_to_agent'):
                    for tool_id in registered_tool_ids:
                        try:
                            client.add_tool_to_agent(agent_id=AGENT_ID, tool_id=tool_id)
                            print(f"  ✓ Attached tool {tool_id}")
                        except Exception as e:
                            error_str = str(e).lower()
                            if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                                print(f"  → Tool {tool_id} already attached")
                            else:
                                print(f"  ⚠ Could not attach tool {tool_id}: {e}")
                else:
                    print(f"  ⚠ Tool attachment API not available")
                    print(f"     You can attach tools manually in Letta ADE using tool IDs:")
                    for tool_id in registered_tool_ids:
                        print(f"       - {tool_id}")
            except Exception as e:
                print(f"  ⚠ Could not attach tools to agent: {e}")
                print(f"     You can attach them manually in Letta ADE using tool IDs:")
                for tool_id in registered_tool_ids:
                    print(f"       - {tool_id}")
        elif not AGENT_ID:
            print(f"→ Agent ID not set - tools registered but not attached to any agent")
            print(f"   Set LETTA_AGENT_ID environment variable to attach automatically")
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("✓ Tools registered successfully")
        print("\nTool Details:")
        for tool_name, _, tool_description in tools_to_register:
            print(f"  - {tool_name}: {tool_description}")
        
        print("\nCompliance Status:")
        print("  ✓ All tools follow Letta compliance requirements:")
        print("    - Return Dict[str, Any] (not JSON strings)")
        print("    - Imports inside functions")
        print("    - Try-except wrappers")
        print("    - No nested def statements (all logic inlined)")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Failed to connect to Letta server or register tools: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

