#!/usr/bin/env python3
"""
Register Sports & Media Control Tools with Letta Agent

This script registers the sports and media control tools with Letta:
1. query_sports_games - Query ESPN for games
2. get_channel_for_game - Look up channel for a game/network
3. control_roku_tv - Control Roku TV via ECP
4. send_fios_ir_command - Send IR commands via Flipper Zero
5. tune_fios_channel - Tune FIOS to a specific channel
6. watch_game - Orchestrate watching a game end-to-end
"""

import os
import sys
from pathlib import Path

# Add this directory to path for imports
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

# Import the sports media tools
from sports_media_tools import (
    query_sports_games,
    get_channel_for_game,
    control_roku_tv,
    send_fios_ir_command,
    tune_fios_channel,
    watch_game
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_SPORTS_AGENT_ID", "agent-2515f29d-b773-43c5-b9ce-b6237897391d")
SLEEPTIME_AGENT_ID = os.getenv("LETTA_SLEEPTIME_AGENT_ID", "agent-a9f2c740-663c-4414-a553-47115180e49b")


def main():
    """Register sports media tools with Letta agent."""
    
    print(f"{'='*60}")
    print("Sports & Media Control Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Main Agent ID: {AGENT_ID}")
    print(f"Sleeptime Agent ID: {SLEEPTIME_AGENT_ID}\n")
    
    tools_to_register = [
        ("query_sports_games", query_sports_games, "Query ESPN for current/upcoming sports games"),
        ("get_channel_for_game", get_channel_for_game, "Look up FIOS channel for a game or network"),
        ("control_roku_tv", control_roku_tv, "Control Roku TV - power, apps, keypresses"),
        ("send_fios_ir_command", send_fios_ir_command, "Send IR command to FIOS cable box"),
        ("tune_fios_channel", tune_fios_channel, "Tune FIOS to a specific channel"),
        ("watch_game", watch_game, "End-to-end: find game and tune TV to watch it"),
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
                # Create tool from function
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=["sports", "media", "tv-control", "custom"]
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
                            t_name = tool.get("name") if isinstance(tool, dict) else (tool.name if hasattr(tool, 'name') else None)
                            if t_name == tool_name:
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
        
        # Attach tools to main agent
        if registered_tool_ids:
            print(f"→ Attaching {len(registered_tool_ids)} tools to main agent {AGENT_ID}...")
            attach_tools_to_agent(client, AGENT_ID, registered_tool_ids)
            
            # Also attach to sleeptime agent if different
            if SLEEPTIME_AGENT_ID and SLEEPTIME_AGENT_ID != AGENT_ID:
                print(f"\n→ Attaching tools to sleeptime agent {SLEEPTIME_AGENT_ID}...")
                attach_tools_to_agent(client, SLEEPTIME_AGENT_ID, registered_tool_ids)
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("✓ Tools registered successfully")
        print("\nTool Details:")
        for tool_name, _, tool_description in tools_to_register:
            print(f"  - {tool_name}: {tool_description}")
        
        print("\nUsage Examples:")
        print('  query_sports_games(team="patriots")')
        print('  get_channel_for_game(team="celtics")')
        print('  control_roku_tv(action="launch_app", app_name="netflix")')
        print('  tune_fios_channel(channel=570)')
        print('  watch_game(team="red sox")')
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Failed to connect to Letta server or register tools: {e}")
        import traceback
        traceback.print_exc()
        return 1


def attach_tools_to_agent(client, agent_id: str, tool_ids: list):
    """Attach tools to a specific agent."""
    try:
        # Try newer SDK v1.0 method first
        if hasattr(client, 'agents') and hasattr(client.agents, 'tools') and hasattr(client.agents.tools, 'attach'):
            for tool_id in tool_ids:
                try:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    print(f"  ✓ Attached tool {tool_id}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                        print(f"  → Tool {tool_id} already attached")
                    else:
                        print(f"  ⚠ Could not attach tool {tool_id}: {e}")
        # Fallback to older method
        elif hasattr(client, 'add_tool_to_agent'):
            for tool_id in tool_ids:
                try:
                    client.add_tool_to_agent(agent_id=agent_id, tool_id=tool_id)
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
            for tool_id in tool_ids:
                print(f"       - {tool_id}")
    except Exception as e:
        print(f"  ⚠ Could not attach tools to agent: {e}")
        print(f"     You can attach them manually in Letta ADE using tool IDs:")
        for tool_id in tool_ids:
            print(f"       - {tool_id}")


if __name__ == "__main__":
    sys.exit(main())

