#!/usr/bin/env python3
"""
Register Google Calendar CRUD Tools with Letta Agent

This script registers all calendar tools with Letta using create_from_function.
"""

import os
import sys

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    print("Error: letta_client not found. Install with: pip install letta-client")
    sys.exit(1)

# Import calendar tools
from letta.calendar_tools.tools import (
    list_calendars,
    create_calendar_event,
    get_calendar_events,
    get_calendar_event,
    update_calendar_event,
    delete_calendar_event,
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")

# Tool definitions
TOOLS = [
    {
        "func": list_calendars,
        "tags": ["calendar", "list", "custom"]
    },
    {
        "func": create_calendar_event,
        "tags": ["calendar", "create", "crud", "custom"]
    },
    {
        "func": get_calendar_events,
        "tags": ["calendar", "read", "crud", "custom"]
    },
    {
        "func": get_calendar_event,
        "tags": ["calendar", "read", "crud", "custom"]
    },
    {
        "func": update_calendar_event,
        "tags": ["calendar", "update", "crud", "custom"]
    },
    {
        "func": delete_calendar_event,
        "tags": ["calendar", "delete", "crud", "custom"]
    },
]


def main():
    """Register all calendar tools with Letta agent."""
    
    print(f"{'='*60}")
    print("Google Calendar CRUD Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    if not AGENT_ID:
        print("Error: LETTA_AGENT_ID environment variable not set")
        print("Set it with: export LETTA_AGENT_ID=your-agent-id")
        return 1
    
    print(f"Agent ID: {AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        registered_tool_ids = []
        
        # Register each tool
        for tool_def in TOOLS:
            func = tool_def["func"]
            tags = tool_def["tags"]
            tool_name = func.__name__
            
            print(f"Registering tool: {tool_name}")
            
            try:
                # Use create_from_function (preferred method)
                created_tool = client.tools.create_from_function(
                    func=func,
                    tags=tags
                )
                
                # Extract tool ID
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (
                    created_tool.get('id') if isinstance(created_tool, dict) else 'N/A'
                )
                
                print(f"  ✓ Registered: {tool_name}")
                print(f"    Tool ID: {tool_id}")
                registered_tool_ids.append(tool_id)
                
            except AttributeError:
                # Fallback to older API if create_from_function doesn't exist
                print(f"  ⚠ create_from_function not available, trying alternative method")
                # This would need to be implemented based on available API
                print(f"  ✗ Registration failed for {tool_name}")
                continue
            except Exception as e:
                print(f"  ✗ Registration failed: {str(e)}")
                continue
        
        if not registered_tool_ids:
            print("\n✗ No tools were registered successfully")
            return 1
        
        # Attach tools to agent
        print(f"\n→ Attaching {len(registered_tool_ids)} tools to agent {AGENT_ID}...")
        
        try:
            # Attach tools to agent
            # Note: This may vary based on Letta API version
            if hasattr(client, 'agents') and hasattr(client.agents, 'attach_tools'):
                client.agents.attach_tools(AGENT_ID, registered_tool_ids)
                print(f"  ✓ Attached {len(registered_tool_ids)} tools to agent")
            else:
                print(f"  ⚠ Tool attachment API not available. Attach manually via Letta dashboard.")
                print(f"  Tool IDs: {registered_tool_ids}")
        except Exception as e:
            print(f"  ⚠ Could not attach tools automatically: {str(e)}")
            print(f"  Attach manually via Letta dashboard using tool IDs: {registered_tool_ids}")
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("✓ Registered calendar tools:")
        print("  • list_calendars - List all accessible calendars")
        print("  • create_calendar_event - Create new calendar events")
        print("  • get_calendar_events - Get events within date range")
        print("  • get_calendar_event - Get single event by ID")
        print("  • update_calendar_event - Update existing events")
        print("  • delete_calendar_event - Delete events")
        print()
        print("Next steps:")
        print("1. Ensure OAuth credentials are set up:")
        print("   - OAuth key file: ~/.gmail-mcp/gcp-oauth.calendar.desktop.json")
        print("   - Credentials will be saved to: ~/.gmail-mcp/calendar.credentials.json")
        print("2. Test tools by calling them through Letta")
        print("3. Tools will prompt for OAuth authentication on first use")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
