#!/usr/bin/env python3
"""Register request_agent_followup tool with Letta and attach to main agent."""

import os
import sys
import inspect
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass
except Exception:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Add letta directory to path so we can import the tool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.request_agent_followup import request_agent_followup

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


def main():
    """Register request_agent_followup tool and attach to main agent."""

    print(f"{'='*60}")
    print("Register request_agent_followup Tool")
    print(f"{'='*60}")
    print()
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print()

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server")
        print()

        # Get function source
        source = inspect.getsource(request_agent_followup)
        tool_name = "request_agent_followup"

        # Check if tool already exists
        existing_tools = client.tools.list()
        existing = [t for t in existing_tools if t.name == tool_name]

        if existing:
            tool = existing[0]
            print(f"Tool '{tool_name}' already exists: {tool.id}")
            client.tools.update(
                tool_id=tool.id,
                source_code=source
            )
            tool_id = tool.id
            print(f"  Updated tool source code")
        else:
            # Create new tool
            try:
                created = client.tools.create_from_function(
                    func=request_agent_followup,
                    tags=["coordination", "evaluation"]
                )
            except AttributeError:
                created = client.create_tool(
                    func=request_agent_followup,
                    name=tool_name,
                    tags=["coordination", "evaluation"]
                )
            tool_id = created.id if hasattr(created, 'id') else created.get('id', 'N/A')
            print(f"  Created tool: {tool_id}")

        # Attach to main agent
        print()
        print(f"Attaching to main agent: {MAIN_AGENT_ID}")
        try:
            agent = client.agents.retrieve(agent_id=MAIN_AGENT_ID)
            current_tool_ids = [t.id if hasattr(t, 'id') else t for t in (agent.tool_ids or [])]

            if tool_id not in current_tool_ids:
                current_tool_ids.append(tool_id)
                client.agents.modify(
                    agent_id=MAIN_AGENT_ID,
                    tool_ids=current_tool_ids
                )
                print(f"  Attached tool to main agent")
            else:
                print(f"  Tool already attached to main agent")
        except Exception as e:
            print(f"  Warning: Could not attach to agent: {e}")
            print(f"  You can attach manually with:")
            print(f"    client.agents.modify(agent_id='{MAIN_AGENT_ID}', tool_ids=[..., '{tool_id}'])")

        print()
        print(f"{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}")
        print()
        print("Tool Details:")
        print(f"  Name: {tool_name}")
        print(f"  Purpose: No-op tool for orchestrator to read follow-up instructions")
        print(f"  Inputs:")
        print(f"    - agent_name: Specialist agent (calendar, document, email, pulse)")
        print(f"    - followup_prompt: Instructions for the next round")
        print()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
