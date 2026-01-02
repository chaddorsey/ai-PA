#!/usr/bin/env python3
"""
Setup Sports & Media Control Agent

This script configures the Letta agent with:
- System prompt for sports and media control
- Memory blocks for user preferences and configuration
"""

import os
import sys
import json

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
AGENT_ID = os.getenv("LETTA_SPORTS_AGENT_ID", "agent-2515f29d-b773-43c5-b9ce-b6237897391d")

# System prompt for the sports and media control agent
SYSTEM_PROMPT = """You are a Sports & Media Control Assistant. Your primary purpose is to help users watch sports games and control their TV/entertainment system.

## Your Capabilities

1. **Sports Information**
   - Query current and upcoming games across NFL, NBA, MLB, NHL, NCAA Football, NCAA Basketball, and MLS
   - Look up what channel or streaming service a game is on
   - Find games by team name (e.g., "Patriots", "Celtics", "Red Sox")

2. **TV Control**
   - Control the Roku TV (power on/off, launch apps, navigate)
   - Switch between streaming apps and cable TV
   - Tune the FIOS cable box to specific channels
   - Send remote control commands (volume, navigation, etc.)

3. **End-to-End Orchestration**
   - When asked to "watch the [team] game", you will:
     1. Find the game and determine where it's airing
     2. Turn on the TV if needed
     3. Either launch the streaming app or switch to cable
     4. Tune to the correct channel

## Available Tools

- `query_sports_games`: Get game schedules from ESPN
- `get_channel_for_game`: Look up what channel a game is on
- `control_roku_tv`: Control the Roku TV (power, apps, keys)
- `send_fios_ir_command`: Send individual IR commands to FIOS
- `tune_fios_channel`: Tune to a specific FIOS channel
- `watch_game`: Full orchestration to watch a team's game

## User Preferences

The user primarily follows Boston sports teams (Patriots, Celtics, Bruins, Red Sox) but may ask about any team. Always prefer HD channels (typically 500+ on FIOS) over SD channels.

## Response Guidelines

1. When the user asks about games, provide concise, useful information:
   - Game matchup
   - Status (live, upcoming, or finished)
   - Time if upcoming
   - Channel/network

2. When taking actions, confirm what you did:
   - "I've tuned to ESPN (channel 570) for the Patriots game"
   - "I've launched Netflix on the Roku"

3. If a game isn't found or there's an error, suggest alternatives:
   - Check if the game is at a different time
   - Suggest the network's channel directly
   - Offer to show all games for that sport

## Location & Setup

- Location: Acton, Massachusetts
- Cable Provider: Verizon FIOS
- TV: Roku TV at 192.168.7.187
- Cable Box: Verizon FIOS (controlled via Flipper Zero IR)
- FIOS HD channels start at 500 (e.g., ESPN is 570, CBS is 504)
"""

# Memory block content for user preferences
USER_PREFERENCES = {
    "favorite_teams": [
        "New England Patriots",
        "Boston Celtics", 
        "Boston Bruins",
        "Boston Red Sox"
    ],
    "preferred_channels": {
        "use_hd": True,
        "hd_prefix": 500
    },
    "location": {
        "city": "Acton",
        "state": "Massachusetts",
        "timezone": "America/New_York"
    },
    "tv_setup": {
        "roku_ip": "192.168.7.187",
        "roku_port": 8060,
        "cable_provider": "Verizon FIOS",
        "cable_input": "HDMI1"
    }
}


def main():
    """Setup the sports agent with system prompt and memory blocks."""
    
    print(f"{'='*60}")
    print("Sports & Media Control Agent Setup")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Get the agent to verify it exists
        print(f"→ Verifying agent {AGENT_ID}...")
        try:
            agent = client.agents.retrieve(agent_id=AGENT_ID)
            print(f"  ✓ Found agent: {agent.name if hasattr(agent, 'name') else AGENT_ID}")
        except Exception as e:
            print(f"  ⚠ Could not retrieve agent: {e}")
            print("  The agent may not exist yet. You can create it in the Letta ADE.")
            print("\nProceeding with memory block creation...")
        
        # Create or update memory blocks
        print(f"\n→ Setting up memory blocks...")
        
        try:
            # Create preferences memory block
            preferences_block = client.blocks.create(
                label="user_preferences",
                value=json.dumps(USER_PREFERENCES, indent=2)
            )
            print(f"  ✓ Created 'user_preferences' block")
            
            # Attach to agent
            if hasattr(client.agents, 'blocks') and hasattr(client.agents.blocks, 'attach'):
                client.agents.blocks.attach(
                    agent_id=AGENT_ID,
                    block_id=preferences_block.id
                )
                print(f"  ✓ Attached 'user_preferences' block to agent")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "409" in error_str:
                print(f"  → 'user_preferences' block already exists")
            else:
                print(f"  ⚠ Could not create preferences block: {e}")
        
        # Print system prompt for manual configuration
        print(f"\n{'='*60}")
        print("Agent Configuration")
        print(f"{'='*60}\n")
        
        print("System Prompt (copy to agent's system prompt in Letta ADE):\n")
        print("-" * 40)
        print(SYSTEM_PROMPT)
        print("-" * 40)
        
        print("\n\nUser Preferences (stored in memory block):\n")
        print(json.dumps(USER_PREFERENCES, indent=2))
        
        print(f"\n{'='*60}")
        print("Setup Complete")
        print(f"{'='*60}\n")
        
        print("Next Steps:")
        print("1. Copy the system prompt above to your agent in Letta ADE")
        print("2. Verify the user_preferences memory block is attached")
        print("3. Run register_sports_media_tools.py to attach the tools")
        print("4. Test with: 'What games are on tonight?'")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

