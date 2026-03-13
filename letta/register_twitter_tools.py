#!/usr/bin/env python3
"""Register run_twitter tool with the Letta server."""
import os
import requests
from pathlib import Path

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def main():
    # Read the full source file (not just the function — ENDPOINTS is inside the function body)
    source_path = Path(__file__).parent / "twitter_tools.py"
    module_source = source_path.read_text()

    # Check for existing tool
    resp = requests.get(f"{LETTA_BASE_URL}/v1/tools/", params={"limit": 100}, timeout=30)
    resp.raise_for_status()
    existing = {t["name"]: t["id"] for t in resp.json()}

    tool_name = "run_twitter"
    tool_payload = {
        "name": tool_name,
        "description": "Interact with Twitter — read feeds, search, manage lists, bookmark tweets.",
        "source_code": module_source,
        "source_type": "python",
        "tags": ["twitter"],
    }

    if tool_name in existing:
        tool_id = existing[tool_name]
        resp = requests.patch(
            f"{LETTA_BASE_URL}/v1/tools/{tool_id}/",
            json=tool_payload,
            timeout=30,
        )
        resp.raise_for_status()
        print(f"Updated tool: {tool_name} ({tool_id})")
    else:
        resp = requests.post(
            f"{LETTA_BASE_URL}/v1/tools/",
            json=tool_payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"Created tool: {tool_name} ({result.get('id', 'unknown')})")


if __name__ == "__main__":
    main()
