#!/usr/bin/env python3
"""
Attach Scheduling Orchestration Tool to Letta Agent

This script attaches the orchestrate_scheduling tool to your Letta agent.
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
LETTA_AGENT_ID = os.getenv("LETTA_AGENT_ID")

def main():
    """Attach scheduling tool to Letta agent."""
    
    if not LETTA_AGENT_ID:
        print("❌ LETTA_AGENT_ID environment variable not set")
        print("   Set it with: export LETTA_AGENT_ID=your-agent-id")
        return 1
    
    print(f"{'='*60}")
    print("Attach Scheduling Tool to Agent")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {LETTA_AGENT_ID}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Find the tool by name
        tool_name = "orchestrate_scheduling"
        print(f"Looking for tool: {tool_name}...")
        
        try:
            # Try to get tools list and find our tool
            tools = client.tools.list()
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
                print(f"  python3 register_scheduling_tool.py\n")
                return 1
            
            # Attach tool to agent
            print(f"\nAttaching tool to agent {LETTA_AGENT_ID}...")
            
            try:
                # Get current agent to check existing tools
                agent = client.agents.retrieve(LETTA_AGENT_ID)
                current_tool_ids = agent.tools or []
                
                # Convert to list of strings if needed
                current_tool_ids = [t.id if hasattr(t, 'id') else (t.get('id') if isinstance(t, dict) else str(t)) for t in current_tool_ids]
                
                # Check if tool is already attached
                if tool_id in current_tool_ids:
                    print(f"  → Tool already attached to agent")
                else:
                    # Add tool to the list and update agent
                    updated_tool_ids = list(current_tool_ids) + [tool_id]
                    client.agents.modify(
                        agent_id=LETTA_AGENT_ID,
                        tool_ids=updated_tool_ids
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
            
            print("Your agent can now use the orchestrate_scheduling tool!")
            print("\nExample usage:")
            print('  "Find 45 minutes with Alex and Priya next Tuesday morning"')
            print('  "Schedule a 1-hour meeting with the team, minimize disruption"')
            print('  "Find time for a 30-minute sync with Sarah this week"')
            
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

