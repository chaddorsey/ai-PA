#!/usr/bin/env python3
"""
Register Slack Analytics Tools with Letta Agent

This script registers the custom Slack analytics tools with your Letta agent
so the agent can trigger exports and retrieve analytics data.
"""

import os
import sys
from letta import Letta
from slack_analytics_tools import (
    trigger_slack_analytics_export,
    list_recent_slack_files,
    get_slack_analytics_files,
    download_slack_file,
    get_slack_analytics_data,
    get_letta_tool_definitions
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_AGENT_ID = os.getenv("LETTA_AGENT_ID")

def main():
    """Register Slack analytics tools with Letta agent."""
    
    if not LETTA_AGENT_ID:
        print("❌ LETTA_AGENT_ID environment variable not set")
        print("   Set it with: export LETTA_AGENT_ID=your-agent-id")
        return 1
    
    print(f"{'='*60}")
    print("Slack Analytics Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {LETTA_AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register each tool
        tools = {
            "trigger_slack_analytics_export": trigger_slack_analytics_export,
            "list_recent_slack_files": list_recent_slack_files,
            "get_slack_analytics_files": get_slack_analytics_files,
            "download_slack_file": download_slack_file,
            "get_slack_analytics_data": get_slack_analytics_data,
        }
        
        tool_definitions = get_letta_tool_definitions()
        
        print("Registering tools with Letta:\n")
        
        for tool_def in tool_definitions:
            tool_name = tool_def["name"]
            tool_func = tools.get(tool_name)
            
            if not tool_func:
                print(f"  ⚠ Skipping {tool_name} - function not found")
                continue
            
            try:
                # Create tool in Letta
                created_tool = client.create_tool(
                    func=tool_func,
                    name=tool_name,
                    tags=["slack", "analytics", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                print(f"    Description: {tool_def['description'][:60]}...")
                
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  → Already exists: {tool_name}")
                else:
                    print(f"  ✗ Error registering {tool_name}: {e}")
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("To attach these tools to your agent, run:")
        print(f"  python3 attach_slack_analytics_to_agent.py\n")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())


