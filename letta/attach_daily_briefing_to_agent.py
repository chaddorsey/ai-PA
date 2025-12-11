#!/usr/bin/env python3
"""
Attach Daily Briefing Tool to Letta Agent

This script attaches the generate_daily_briefing tool to your Letta agent.
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

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = "agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2"

def main():
    """Attach daily briefing tool to Letta agent."""
    
    print(f"{'='*60}")
    print("Attach Daily Briefing Tool to Agent")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Find the tool by name
        tool_name = "generate_daily_briefing"
        print(f"Looking for tool: {tool_name}...")
        
        try:
            # Try to get tools list and find our tool
            # Handle SDK v1.0 pagination (returns page object with .items)
            tools_result = client.tools.list()
            tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
            tool_id = None
            
            for tool in tools:
                # Handle both dict and Pydantic Tool objects
                tool_name_attr = tool.name if hasattr(tool, 'name') else (tool.get("name") if isinstance(tool, dict) else None)
                tool_id_attr = tool.id if hasattr(tool, 'id') else (tool.get("id") if isinstance(tool, dict) else None)
                
                if tool_name_attr == tool_name:
                    tool_id = tool_id_attr
                    print(f"  ✓ Found tool (ID: {tool_id})")
                    break
            
            if not tool_id:
                print(f"  ✗ Tool '{tool_name}' not found")
                print(f"\nPlease register the tool first by running:")
                print(f"  python3 register_daily_briefing_tool.py\n")
                return 1
            
            # Attach tool to agent using SDK v1.0 API
            print(f"\nAttaching tool to agent {AGENT_ID}...")
            
            try:
                # Use the SDK v1.0 method: client.agents.tools.attach()
                client.agents.tools.attach(
                    agent_id=AGENT_ID,
                    tool_id=tool_id
                )
                print(f"  ✓ Tool attached successfully")
                
            except Exception as e:
                error_str = str(e).lower()
                if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                    print(f"  → Tool already attached to agent")
                else:
                    print(f"  ✗ Error attaching tool: {e}")
                    print(f"\nYou can attach the tool manually in Letta ADE:")
                    print(f"  Tool ID: {tool_id}")
                    import traceback
                    traceback.print_exc()
                    return 1
            
            print(f"\n{'='*60}")
            print("✓ Attachment Complete")
            print(f"{'='*60}\n")
            
            print("Your agent can now use the generate_daily_briefing tool!")
            print("\nExample usage:")
            print('  "Update the daily briefing"')
            print('  "Generate today\'s schedule"')
            print('  "Show me my available time today"')
            
            return 0
            
        except Exception as e:
            print(f"❌ Error: {e}")
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

