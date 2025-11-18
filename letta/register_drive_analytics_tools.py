#!/usr/bin/env python3
"""
Register Drive Analytics Tools with Letta Agent

This script registers the custom Drive analytics tools with your Letta agent
so the agent can collect and analyze Google Drive activity data.
"""

import os
import sys
from letta_client import Letta
from drive_analytics_tools import (
    collect_daily_workspace_activity,
    collect_daily_personal_activity,
    collect_daily_mentions,
    calculate_running_averages,
    get_drive_analytics_summary,
    get_drive_trends,
    get_my_drive_activity,
    get_drive_mentions,
    get_document_activity,
    get_top_documents,
    get_recent_my_activity,
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

def main():
    """Register Drive analytics tools with Letta agent."""
    
    print(f"{'='*60}")
    print("Drive Analytics Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Define all tools
        tools = {
            "collect_daily_workspace_activity": collect_daily_workspace_activity,
            "collect_daily_personal_activity": collect_daily_personal_activity,
            "collect_daily_mentions": collect_daily_mentions,
            "calculate_running_averages": calculate_running_averages,
            "get_drive_analytics_summary": get_drive_analytics_summary,
            "get_drive_trends": get_drive_trends,
            "get_my_drive_activity": get_my_drive_activity,
            "get_drive_mentions": get_drive_mentions,
            "get_document_activity": get_document_activity,
            "get_top_documents": get_top_documents,
            "get_recent_my_activity": get_recent_my_activity,
        }
        
        print("Registering tools with Letta:\n")
        
        registered_tools = []
        for tool_name, tool_func in tools.items():
            try:
                # Create tool in Letta - try both methods
                try:
                    created_tool = client.tools.create_from_function(
                        func=tool_func,
                        tags=["drive", "analytics", "custom"]
                    )
                except AttributeError:
                    # Fallback to create_tool if create_from_function doesn't exist
                    created_tool = client.create_tool(
                        func=tool_func,
                        name=tool_name,
                        tags=["drive", "analytics", "custom"]
                    )
                
                print(f"  ✓ Registered: {tool_name}")
                registered_tools.append(created_tool)
                
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    print(f"  → Already exists: {tool_name}")
                else:
                    print(f"  ✗ Error registering {tool_name}: {e}")
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print(f"✓ Registered {len(registered_tools)} tools")
        print("\nTo attach these tools to your agent, run:")
        print(f"  python3 attach_drive_analytics_to_agent.py\n")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

