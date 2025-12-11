#!/usr/bin/env python3
"""
Register Daily Briefing Tool with Letta Agent

This script registers the generate_daily_briefing tool with your Letta agent
so the agent can generate formatted daily schedule briefings with available time calculations.
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

# Add letta directory to path so we can import the daily briefing tool
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

from daily_briefing.generate_daily_briefing import generate_daily_briefing

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

def main():
    """Register daily briefing tool with Letta agent."""
    
    print(f"{'='*60}")
    print("Daily Briefing Tool Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register the tool
        tool_name = "generate_daily_briefing"
        
        print(f"Registering tool: {tool_name}\n")
        
        try:
            # Try create_from_function first (newer API)
            try:
                created_tool = client.tools.create_from_function(
                    func=generate_daily_briefing,
                    tags=["calendar", "briefing", "schedule", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                # Handle both dict and Pydantic model responses
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Daily briefing tool with schedule and available time calculations")
                
            except AttributeError:
                # Fallback to create_tool if create_from_function doesn't exist
                created_tool = client.create_tool(
                    func=generate_daily_briefing,
                    name=tool_name,
                    tags=["calendar", "briefing", "schedule", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Daily briefing tool with schedule and available time calculations")
            
            print(f"\n{'='*60}")
            print("Registration Complete")
            print(f"{'='*60}\n")
            
            print("✓ Tool registered successfully")
            print("\nTool Details:")
            print("  Name: generate_daily_briefing")
            print("  Purpose: Generate formatted daily schedule briefing with available time calculations")
            print("  Inputs:")
            print("    - calendar_id: Calendar identifier (defaults to 'cdorsey@concord.org')")
            print("    - timezone: Timezone for calculations (defaults to 'America/New_York')")
            print("  Outputs:")
            print("    - status: 'ok' or 'error'")
            print("    - briefing: Markdown-formatted daily briefing")
            print("    - memory_content: Content for updating memory block")
            print("    - timestamp: ISO timestamp of when briefing was generated")
            print("    - events_retrieved: Number of events retrieved")
            print("    - events_included: Number of events included after filtering")
            print("    - total_available_minutes: Total available time in minutes")
            print("\nTo attach this tool to your agent, you can use the Letta SDK:")
            print("  from letta_client import Letta")
            print("  client = Letta()")
            print("  agent = client.agents.get(agent_id)")
            print("  agent.attach_tool(tool_id)\n")
            
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

