#!/usr/bin/env python3
"""
Attach Drive Analytics Tools to Letta Agent

This script attaches the registered Drive analytics tools to your Letta agent
so the agent can use them in conversations and scheduled reminders.
"""

import os
import sys
from letta_client import Letta

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_AGENT_ID = os.getenv("LETTA_AGENT_ID")

def main():
    """Attach Drive analytics tools to Letta agent."""
    
    if not LETTA_AGENT_ID:
        print("❌ LETTA_AGENT_ID environment variable not set")
        print("   Set it with: export LETTA_AGENT_ID=your-agent-id")
        return 1
    
    print(f"{'='*60}")
    print("Attach Drive Analytics Tools to Agent")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {LETTA_AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Get available tools
        print("Finding Drive analytics tools...")
        all_tools = client.list_tools()
        
        drive_tools = []
        for tool in all_tools:
            if "drive" in tool.tags and "analytics" in tool.tags:
                drive_tools.append(tool)
        
        if not drive_tools:
            print("❌ No Drive analytics tools found!")
            print("   Run register_drive_analytics_tools.py first\n")
            return 1
        
        print(f"Found {len(drive_tools)} Drive analytics tools:\n")
        for tool in drive_tools:
            print(f"  • {tool.name}")
        
        print()
        
        # Get current agent state
        agent = client.get_agent(LETTA_AGENT_ID)
        current_tools = agent.tools or []
        current_tool_names = [t for t in current_tools]
        
        # Attach tools to agent
        print("Attaching tools to agent...")
        tools_attached = 0
        
        for tool in drive_tools:
            if tool.name not in current_tool_names:
                try:
                    client.add_tool_to_agent(
                        agent_id=LETTA_AGENT_ID,
                        tool_id=tool.id
                    )
                    print(f"  ✓ Attached: {tool.name}")
                    tools_attached += 1
                except Exception as e:
                    print(f"  ✗ Error attaching {tool.name}: {e}")
            else:
                print(f"  → Already attached: {tool.name}")
        
        print(f"\n{'='*60}")
        print("Attachment Complete")
        print(f"{'='*60}\n")
        
        print(f"✓ {tools_attached} new tools attached to agent")
        print(f"\nYour Letta agent can now use these Drive analytics tools!\n")
        
        print("Example usage in conversation with your agent:")
        print('  "Collect yesterday\'s Drive activity"')
        print('  "Show me the top edited documents"')
        print('  "Get documents I\'ve been viewing recently"')
        print('  "Check for comments mentioning me"\n')
        
        print("To set up scheduled reminders, use the schedule_reminder tool:")
        print('  "Schedule a reminder to collect Drive analytics every weekday at 6am"\n')
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

