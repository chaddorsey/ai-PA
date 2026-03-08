"""Register slack-cli Letta tools with the Letta API."""
import os
import sys
import json
import inspect
import requests

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

# Import all tool functions
from letta_tools.slack_conversations import run_slack_conversations
from letta_tools.slack_chat import run_slack_chat
from letta_tools.slack_users import run_slack_users
from letta_tools.slack_search import run_slack_search
from letta_tools.slack_reactions import run_slack_reactions
from letta_tools.slack_misc import run_slack_misc

TOOLS = [
    run_slack_conversations,
    run_slack_chat,
    run_slack_users,
    run_slack_search,
    run_slack_reactions,
    run_slack_misc,
]


def register_tool(func):
    """Register a single tool with the Letta API."""
    source_code = inspect.getsource(func)
    tool_name = func.__name__

    # Check if tool already exists
    resp = requests.get(f"{LETTA_BASE_URL}/v1/tools", params={"name": tool_name})
    if resp.status_code == 200:
        existing = resp.json()
        if existing:
            tool_id = existing[0]["id"]
            print(f"  Updating existing tool: {tool_name} ({tool_id})")
            resp = requests.patch(
                f"{LETTA_BASE_URL}/v1/tools/{tool_id}",
                json={"source_code": source_code},
            )
            resp.raise_for_status()
            return tool_id

    # Create new tool
    print(f"  Creating new tool: {tool_name}")
    resp = requests.post(
        f"{LETTA_BASE_URL}/v1/tools",
        json={"source_code": source_code},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def main():
    print(f"Registering slack-cli tools with Letta at {LETTA_BASE_URL}")
    tool_ids = {}
    for func in TOOLS:
        try:
            tool_id = register_tool(func)
            tool_ids[func.__name__] = tool_id
            print(f"  ✓ {func.__name__}: {tool_id}")
        except Exception as e:
            print(f"  ✗ {func.__name__}: {e}")

    print(f"\nRegistered {len(tool_ids)}/{len(TOOLS)} tools")
    print(json.dumps(tool_ids, indent=2))


if __name__ == "__main__":
    main()
