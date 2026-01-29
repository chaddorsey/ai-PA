#!/usr/bin/env python3
"""Register analyze_task_executions tool with Letta."""

import os
import sys
import inspect

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from letta_client import Letta
from tools.analyze_task_executions import analyze_task_executions

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def main():
    print("=" * 60)
    print("Register analyze_task_executions Tool")
    print("=" * 60)
    print()
    print(f"Letta Base URL: {LETTA_BASE}")
    print()

    try:
        client = Letta(base_url=LETTA_BASE)
        print("Connected to Letta server")
        print()

        # Get function source
        source = inspect.getsource(analyze_task_executions)

        # Check if tool already exists
        existing_tools = client.tools.list()
        existing_names = [t.name for t in existing_tools]

        if "analyze_task_executions" in existing_names:
            print("Tool 'analyze_task_executions' already exists")
            # Find and update
            for tool in existing_tools:
                if tool.name == "analyze_task_executions":
                    client.tools.update(
                        tool_id=tool.id,
                        source_code=source
                    )
                    print(f"  Updated tool: {tool.id}")
                    break
        else:
            # Create new tool
            try:
                tool = client.tools.create_from_function(
                    func=analyze_task_executions,
                    tags=["coordination", "analysis", "refinement"]
                )
            except AttributeError:
                # Fallback for older API
                tool = client.create_tool(
                    func=analyze_task_executions,
                    name="analyze_task_executions",
                    tags=["coordination", "analysis", "refinement"]
                )
            print(f"  Created tool: {tool.id}")

        print()
        print("=" * 60)
        print("Registration Complete")
        print("=" * 60)
        print()
        print("To attach this tool to an agent, use:")
        print("  client.tools.attach_to_agent(agent_id=AGENT_ID, tool_id=TOOL_ID)")
        print()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
