#!/usr/bin/env python3
"""
Register Request Handler Tool with Letta Agent

This script registers the delegate_to_specialist tool with Letta using create_from_function.
"""

import os
import sys
from pathlib import Path

# Add letta directory to path so we can import the tool
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

# Import the request handler tool
from request_handler_tool import delegate_to_specialist

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")


def main():
    """Register request handler tool with Letta agent."""
    
    print(f"{'='*60}")
    print("Request Handler Tool Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {AGENT_ID if AGENT_ID else 'Not set (will register tool only)'}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register the tool
        tool_name = "delegate_to_specialist"
        
        print(f"Registering tool: {tool_name}\n")
        
        try:
            # Try create_from_function first (newer API)
            created_tool = client.tools.create_from_function(
                func=delegate_to_specialist,
                tags=["routing", "delegation", "custom", "request-handler"]
            )
            print(f"  ✓ Registered: {tool_name}")
            tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
            print(f"    Tool ID: {tool_id}")
            print(f"    Description: Route requests to specialist agents (task, calendar, pulse, documents, email)")
            
            # Attach tool to agent if agent ID is provided
            if AGENT_ID:
                print(f"\n→ Attaching tool to agent {AGENT_ID}...")
                try:
                    # Try newer SDK v1.0 method first
                    if hasattr(client, 'agents') and hasattr(client.agents, 'tools') and hasattr(client.agents.tools, 'attach'):
                        client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool_id)
                        print(f"  ✓ Attached tool to agent")
                    # Fallback to older method
                    elif hasattr(client, 'add_tool_to_agent'):
                        client.add_tool_to_agent(agent_id=AGENT_ID, tool_id=tool_id)
                        print(f"  ✓ Attached tool to agent")
                    else:
                        print(f"  ⚠ Tool attachment API not available")
                        print(f"     You can attach it manually in Letta ADE using tool ID: {tool_id}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                        print(f"  → Tool already attached to agent")
                    else:
                        print(f"  ⚠ Could not attach tool to agent: {e}")
                        print(f"     You can attach it manually in Letta ADE using tool ID: {tool_id}")
            else:
                print(f"\n→ Agent ID not set - tool registered but not attached to any agent")
                print(f"   Set LETTA_AGENT_ID environment variable to attach automatically")
            
            print(f"\n{'='*60}")
            print("Registration Complete")
            print(f"{'='*60}\n")
            
            print("✓ Tool registered successfully")
            print("\nTool Details:")
            print("  Name: delegate_to_specialist")
            print("  Purpose: Route requests to specialist agents for delegation")
            print("  Inputs:")
            print("    - domain: The domain to route to")
            print("    - request: The request message to send to the specialist agent")
            print("  Outputs:")
            print("    - String response from the specialist agent")
            print("    - Error message if routing failed")
            print("\nSupported Domains:")
            print("  - task: Tasks Agent (OmniFocus) - agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
            print("  - calendar: Calendar Agent - agent-892a2d58-b9f6-4baf-84f3-c431fe46487d")
            print("  - pulse: Pulse Agent (Slack, analytics) - agent-2ed14ef4-6289-453a-ae27-290b6ed196b8")
            print("  - documents/docs: Documents Agent (Drive, transcripts) - agent-398b4f6c-6afa-493f-8063-897c6b171a0d")
            print("  - email: Email Agent - agent-b4928949-8012-4436-a3c7-a9e510785147")
            
            return 0
            
        except Exception as e:
            print(f"\n❌ Failed to register tool: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    except Exception as e:
        print(f"\n❌ Failed to connect to Letta server: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
