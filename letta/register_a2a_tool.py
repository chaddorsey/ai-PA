#!/usr/bin/env python3
"""
Register Agent-to-Agent Messaging Tool with Letta

This script registers the send_message_to_agent tool with your Letta instance
so it can be attached to agents for agent-to-agent communication.

Based on community workaround from:
https://forum.letta.com/t/custom-agent-to-agent-messaging-tool-for-v1-architecture/127
"""

import os
import sys
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, skip
except Exception:
    pass  # .env file doesn't exist or can't be loaded

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Add letta directory to path so we can import the tool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2a_tool import send_message_to_agent

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

def main():
    """Register agent-to-agent messaging tool with Letta."""
    
    print(f"{'='*60}")
    print("Agent-to-Agent Messaging Tool Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    # Check for LETTA_API_KEY (required for tool to work, but not for registration)
    letta_api_key = os.getenv("LETTA_API_KEY")
    if not letta_api_key:
        print("⚠ Warning: LETTA_API_KEY not set in environment")
        print("   The tool will need this to function properly.\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register the tool
        tool_name = "send_message_to_agent"
        
        print(f"Registering tool: {tool_name}\n")
        
        try:
            # Try create_from_function first (newer API)
            try:
                created_tool = client.tools.create_from_function(
                    func=send_message_to_agent,
                    tags=["agent-to-agent", "communication", "custom", "a2a"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Agent-to-agent messaging tool for v1 architecture")
                
            except AttributeError:
                # Fallback to create_tool if create_from_function doesn't exist
                created_tool = client.create_tool(
                    func=send_message_to_agent,
                    name=tool_name,
                    tags=["agent-to-agent", "communication", "custom", "a2a"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                print(f"    Description: Agent-to-agent messaging tool for v1 architecture")
            
            print(f"\n{'='*60}")
            print("Registration Complete")
            print(f"{'='*60}\n")
            
            print("✓ Tool registered successfully")
            print("\nTool Details:")
            print("  Name: send_message_to_agent")
            print("  Purpose: Send messages between Letta agents (v1 architecture workaround)")
            print("  Inputs:")
            print("    - sender_agent_id: The ID of the sending agent")
            print("    - recipient_agent_id: The ID of the recipient agent")
            print("    - message: The message content to send")
            print("  Outputs:")
            print("    - JSON with replies from recipient agent")
            print("    - status: 'ok' or 'error'")
            print("    - replies: List of reply strings")
            print("\nRequirements:")
            print("  - LETTA_API_KEY must be set in environment")
            print("  - LETTA_BASE_URL (defaults to http://localhost:8283)")
            print("  - Both agents must have agent_info memory block with their agent_id")
            print("\nTo attach this tool to your agents, run:")
            print(f"  python3 attach_a2a_tool_to_agents.py\n")
            
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

