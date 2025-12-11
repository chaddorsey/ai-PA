#!/usr/bin/env python3
"""
Attach Agent-to-Agent Messaging Tool to Letta Agents

This script attaches the send_message_to_agent tool to the specified agents
so they can communicate with each other.

Agents:
- Main orchestration agent: agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a
- Scheduling agent: agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218
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

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs to attach the tool to
MAIN_ORCHESTRATION_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
SCHEDULING_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"

AGENT_IDS = [
    ("Main Orchestration Agent", MAIN_ORCHESTRATION_AGENT_ID),
    ("Scheduling Agent", SCHEDULING_AGENT_ID),
]

def main():
    """Attach agent-to-agent messaging tool to specified agents."""
    
    print(f"{'='*60}")
    print("Attach Agent-to-Agent Messaging Tool to Agents")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Find the tool by name
        tool_name = "send_message_to_agent"
        print(f"Looking for tool: {tool_name}...")
        
        try:
            # Try to get tools list and find our tool
            tools_result = client.tools.list()
            tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
            tool_id = None
            
            for tool in tools:
                # Handle both dict and Pydantic Tool objects
                tool_name_attr = tool.name if hasattr(tool, 'name') else (tool.get("name") if isinstance(tool, dict) else None)
                tool_id_attr = tool.id if hasattr(tool, 'id') else (tool.get("id") if isinstance(tool, dict) else None)
                
                if tool_name_attr == tool_name:
                    tool_id = tool_id_attr
                    print(f"  ✓ Found tool (ID: {tool_id})\n")
                    break
            
            if not tool_id:
                print(f"  ✗ Tool '{tool_name}' not found")
                print(f"\nPlease register the tool first by running:")
                print(f"  python3 register_a2a_tool.py\n")
                return 1
            
            # Attach tool to each agent
            print(f"Attaching tool to agents...\n")
            
            success_count = 0
            for agent_name, agent_id in AGENT_IDS:
                print(f"→ {agent_name} ({agent_id})...")
                
                try:
                    # Use the SDK v1.0 method: client.agents.tools.attach()
                    client.agents.tools.attach(
                        agent_id=agent_id,
                        tool_id=tool_id
                    )
                    print(f"  ✓ Tool attached successfully")
                    success_count += 1
                    
                except Exception as e:
                    error_str = str(e).lower()
                    if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                        print(f"  → Tool already attached to agent")
                        success_count += 1
                    else:
                        print(f"  ✗ Error attaching tool: {e}")
                        import traceback
                        traceback.print_exc()
            
            print(f"\n{'='*60}")
            print("✓ Attachment Complete")
            print(f"{'='*60}\n")
            
            print(f"Successfully attached tool to {success_count}/{len(AGENT_IDS)} agents")
            print("\nNext Steps:")
            print("1. Ensure both agents have an 'agent_info' memory block with their agent_id")
            print("   Example: agent_info block with value 'agent_id: agent-xxx-xxx-xxx'")
            print("2. Ensure LETTA_API_KEY is set in the environment where tools execute")
            print("3. Test agent-to-agent communication by having one agent send a message to the other")
            print("\nExample usage in agent conversation:")
            print('  "Send a message to the scheduling agent asking about availability"')
            print('  "Ask the main orchestration agent to help with scheduling"')
            
            return 0 if success_count == len(AGENT_IDS) else 1
            
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


