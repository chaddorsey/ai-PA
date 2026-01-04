#!/usr/bin/env python3
"""
Register Auto-Madden Tools with Letta Agents.

Registers game companion tools and attaches them to the appropriate agents.
"""

import os
import sys
from pathlib import Path

# Add this directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from auto_madden_tools import (
    get_current_game_state,
    ask_game_question,
    get_player_info,
    explain_play,
    get_game_summary,
)

from auto_madden_sleeptime_tools import (
    summarize_game_insights,
    update_user_knowledge,
    log_game_session,
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = os.getenv("AUTO_MADDEN_MAIN_AGENT_ID", "agent-30ff1be2-3922-42fb-b7ee-458cb5a3bb07")
SLEEPTIME_AGENT_ID = os.getenv("AUTO_MADDEN_SLEEPTIME_AGENT_ID", "agent-89d31c34-de69-4f34-b388-9bd8d9b647fa")


def attach_tools(client, agent_id: str, tool_ids: list):
    """Attach tools to a specific agent."""
    for tool_id in tool_ids:
        try:
            if hasattr(client, 'agents') and hasattr(client.agents, 'tools'):
                client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
            else:
                client.add_tool_to_agent(agent_id=agent_id, tool_id=tool_id)
            print(f"  ✓ Attached {tool_id}")
        except Exception as e:
            error_str = str(e).lower()
            if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                print(f"  → {tool_id} already attached")
            else:
                print(f"  ✗ Could not attach {tool_id}: {e}")


def main():
    """Register auto-madden tools with Letta agents."""
    
    print("=" * 60)
    print("Auto-Madden Tool Registration")
    print("=" * 60)
    print()
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Main Agent ID: {MAIN_AGENT_ID}")
    print(f"Sleeptime Agent ID: {SLEEPTIME_AGENT_ID}")
    print()
    
    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server")
        print()
    except Exception as e:
        print(f"✗ Failed to connect to Letta: {e}")
        return 1
    
    # Main agent tools
    main_tools = [
        ("get_current_game_state", get_current_game_state),
        ("ask_game_question", ask_game_question),
        ("get_player_info", get_player_info),
        ("explain_play", explain_play),
        ("get_game_summary", get_game_summary),
    ]
    
    # Sleeptime agent tools
    sleeptime_tools = [
        ("summarize_game_insights", summarize_game_insights),
        ("update_user_knowledge", update_user_knowledge),
        ("log_game_session", log_game_session),
    ]
    
    registered_main = []
    registered_sleep = []
    
    # Register main agent tools
    print("Registering main agent tools...")
    for name, func in main_tools:
        try:
            tool = client.tools.create_from_function(
                func=func,
                tags=["auto-madden", "game-companion"]
            )
            tool_id = tool.id if hasattr(tool, 'id') else tool.get('id')
            registered_main.append(tool_id)
            print(f"  ✓ {name}: {tool_id}")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  → {name} already exists")
                # Try to find existing tool
                try:
                    all_tools = client.tools.list()
                    for tool in all_tools:
                        t_name = tool.name if hasattr(tool, 'name') else tool.get('name')
                        if t_name == name:
                            tool_id = tool.id if hasattr(tool, 'id') else tool.get('id')
                            registered_main.append(tool_id)
                            print(f"    Found existing: {tool_id}")
                            break
                except Exception:
                    pass
            else:
                print(f"  ✗ {name}: {e}")
    
    print()
    
    # Register sleeptime agent tools
    print("Registering sleeptime agent tools...")
    for name, func in sleeptime_tools:
        try:
            tool = client.tools.create_from_function(
                func=func,
                tags=["auto-madden", "sleeptime"]
            )
            tool_id = tool.id if hasattr(tool, 'id') else tool.get('id')
            registered_sleep.append(tool_id)
            print(f"  ✓ {name}: {tool_id}")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  → {name} already exists")
                try:
                    all_tools = client.tools.list()
                    for tool in all_tools:
                        t_name = tool.name if hasattr(tool, 'name') else tool.get('name')
                        if t_name == name:
                            tool_id = tool.id if hasattr(tool, 'id') else tool.get('id')
                            registered_sleep.append(tool_id)
                            print(f"    Found existing: {tool_id}")
                            break
                except Exception:
                    pass
            else:
                print(f"  ✗ {name}: {e}")
    
    print()
    
    # Attach tools to agents
    if registered_main:
        print(f"Attaching {len(registered_main)} tools to main agent...")
        attach_tools(client, MAIN_AGENT_ID, registered_main)
        print()
    
    if registered_sleep:
        print(f"Attaching {len(registered_sleep)} tools to sleeptime agent...")
        attach_tools(client, SLEEPTIME_AGENT_ID, registered_sleep)
        print()
    
    print("=" * 60)
    print("Registration Complete")
    print("=" * 60)
    print()
    print("Main Agent Tools:")
    for name, _ in main_tools:
        print(f"  - {name}")
    print()
    print("Sleeptime Agent Tools:")
    for name, _ in sleeptime_tools:
        print(f"  - {name}")
    print()
    print("Usage:")
    print("  Start a session: Open http://localhost:5130")
    print("  Enter a team name to begin tracking their game")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

