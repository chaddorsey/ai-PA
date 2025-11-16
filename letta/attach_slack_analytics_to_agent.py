#!/usr/bin/env python3
"""
Attach Slack Analytics Tools to Letta Agent

This script attaches the registered Slack analytics tools to your Letta agent
so the agent can use them in conversations.
"""

import os
import sys
from letta import Letta

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_AGENT_ID = os.getenv("LETTA_AGENT_ID")

def main():
    """Attach Slack analytics tools to Letta agent."""
    
    if not LETTA_AGENT_ID:
        print("❌ LETTA_AGENT_ID environment variable not set")
        print("   Set it with: export LETTA_AGENT_ID=your-agent-id")
        return 1
    
    print(f"{'='*60}")
    print("Attach Slack Analytics Tools to Agent")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {LETTA_AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Get available tools
        print("Finding Slack analytics tools...")
        all_tools = client.list_tools()
        
        slack_tools = []
        for tool in all_tools:
            if "slack" in tool.tags and "analytics" in tool.tags:
                slack_tools.append(tool)
        
        if not slack_tools:
            print("❌ No Slack analytics tools found!")
            print("   Run register_slack_analytics_tools.py first\n")
            return 1
        
        print(f"Found {len(slack_tools)} Slack analytics tools:\n")
        for tool in slack_tools:
            print(f"  • {tool.name}")
        
        print()
        
        # Get current agent state
        agent = client.get_agent(LETTA_AGENT_ID)
        current_tools = agent.tools or []
        current_tool_names = [t for t in current_tools]
        
        # Attach tools to agent
        print("Attaching tools to agent...")
        tools_attached = 0
        
        for tool in slack_tools:
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
        print(f"\nYour Letta agent can now use these Slack analytics tools!\n")
        
        print("Example usage in conversation with your agent:")
        print('  "Can you get me the channel analytics data?"')
        print('  "Show me the member analytics from Slack"')
        print('  "List recent CSV files from Slack"\n')
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())


