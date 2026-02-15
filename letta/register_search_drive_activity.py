#!/usr/bin/env python3
"""
Register search_drive_activity tool with Letta.

This function is fully Letta-compliant (all imports inside function body,
try-except wrapped, no nested defs), so we register the raw source code.
"""
import os
import json
import urllib.request
import inspect
import importlib.util

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def http_post(url, data):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"HTTP Error {e.code}: {error_body}")
        return None


def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"GET Error: {e}")
        return None


def main():
    # Load the module to extract the function source
    module_path = os.path.join(os.path.dirname(__file__), "drive_analytics_tools.py")
    spec = importlib.util.spec_from_file_location("drive_analytics_tools", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    func = getattr(module, "search_drive_activity")
    source = inspect.getsource(func)

    # Letta needs typing imports at module level for type annotations
    full_source = "from typing import Dict, Any, Optional\n\n" + source

    print(f"Registering search_drive_activity with Letta at {LETTA_BASE}")
    print(f"Source code length: {len(full_source)} chars")

    # Check if already registered
    tools = http_get(f"{LETTA_BASE}/v1/tools/")
    if tools:
        for tool in tools:
            if tool.get("name") == "search_drive_activity":
                print(f"Tool already exists with ID: {tool['id']}")
                print("Deleting old version...")
                req = urllib.request.Request(
                    f"{LETTA_BASE}/v1/tools/{tool['id']}", method="DELETE"
                )
                try:
                    with urllib.request.urlopen(req, timeout=30):
                        print("Deleted old tool.")
                except Exception as e:
                    print(f"Warning: Could not delete old tool: {e}")

    result = http_post(
        f"{LETTA_BASE}/v1/tools/",
        {"source_code": full_source, "tags": ["drive", "analytics", "activity"]},
    )

    if result:
        tool_id = result.get("id")
        print(f"Successfully registered! Tool ID: {tool_id}")
        return tool_id
    else:
        print("Failed to register tool.")
        return None


if __name__ == "__main__":
    tool_id = main()
    if not tool_id:
        exit(1)
