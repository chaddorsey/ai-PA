"""Register the run_slack Letta tool with the Letta API.

Registers a single general-purpose tool (matching the run_gws pattern)
instead of multiple granular tools. Skills guide the agent on command syntax.
"""
import os
import sys
import json
import inspect
import requests

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

from letta_tools.slack_tool import run_slack

TOOLS = [run_slack]

# Tools that were previously registered and should be removed from agents
DEPRECATED_TOOLS = [
    "run_slack_conversations",
    "run_slack_chat",
    "run_slack_users",
    "run_slack_search",
    "run_slack_reactions",
    "run_slack_misc",
]


def register_tool(func):
    """Register a single tool with the Letta API."""
    source_code = inspect.getsource(func)
    tool_name = func.__name__

    # Check if tool already exists
    resp = requests.get(f"{LETTA_BASE_URL}/v1/tools/", params={"name": tool_name})
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
        f"{LETTA_BASE_URL}/v1/tools/",
        json={"source_code": source_code},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def cleanup_deprecated_tools():
    """List deprecated tools that still exist (for manual removal from agents)."""
    found = []
    for name in DEPRECATED_TOOLS:
        resp = requests.get(f"{LETTA_BASE_URL}/v1/tools/", params={"name": name})
        if resp.status_code == 200:
            existing = resp.json()
            if existing:
                found.append((name, existing[0]["id"]))
    return found


def main():
    print(f"Registering slack-cli tools with Letta at {LETTA_BASE_URL}")

    # Register the single run_slack tool
    tool_ids = {}
    for func in TOOLS:
        try:
            tool_id = register_tool(func)
            tool_ids[func.__name__] = tool_id
            print(f"  OK {func.__name__}: {tool_id}")
        except Exception as e:
            print(f"  FAIL {func.__name__}: {e}")

    print(f"\nRegistered {len(tool_ids)}/{len(TOOLS)} tools")
    print(json.dumps(tool_ids, indent=2))

    # Check for deprecated tools
    deprecated = cleanup_deprecated_tools()
    if deprecated:
        print(f"\nDeprecated tools still registered (remove from agents manually):")
        for name, tool_id in deprecated:
            print(f"  {name}: {tool_id}")
        print("\nTo delete a deprecated tool:")
        print(f"  curl -X DELETE {LETTA_BASE_URL}/v1/tools/<tool_id>")


if __name__ == "__main__":
    main()
