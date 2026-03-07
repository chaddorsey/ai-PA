"""Register omnifocus-cli Letta tools with the Letta server.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_letta_tools.py [--agent-id <id>]
"""
import argparse
import inspect
import importlib.util
import sys
from pathlib import Path

TOOL_FILES = [
    "letta_tools/omnifocus_task.py",
    "letta_tools/omnifocus_search.py",
    "letta_tools/omnifocus_project.py",
    "letta_tools/omnifocus_inbox.py",
    "letta_tools/omnifocus_tags.py",
]


def load_function_from_file(filepath: str):
    """Load the first public function defined in a file."""
    spec = importlib.util.spec_from_file_location("mod", filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if not name.startswith("_"):
            return name, inspect.getsource(obj)
    raise ValueError(f"No public function found in {filepath}")


def main():
    import os
    import requests

    parser = argparse.ArgumentParser(description="Register omnifocus-cli tools with Letta")
    parser.add_argument("--agent-id", help="Agent ID to attach tools to")
    args = parser.parse_args()

    base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    tools_dir = Path(__file__).parent

    registered_ids = []

    for rel_path in TOOL_FILES:
        filepath = tools_dir / rel_path
        func_name, source_code = load_function_from_file(str(filepath))

        existing = requests.get(f"{base_url}/v1/tools", params={"limit": 100})
        existing.raise_for_status()
        existing_tool = next(
            (t for t in existing.json() if t["name"] == func_name), None
        )

        if existing_tool:
            resp = requests.patch(
                f"{base_url}/v1/tools/{existing_tool['id']}",
                json={"source_code": source_code},
            )
            resp.raise_for_status()
            tool_id = existing_tool["id"]
            print(f"  Updated: {func_name} ({tool_id})")
        else:
            resp = requests.post(
                f"{base_url}/v1/tools",
                json={"source_code": source_code},
            )
            resp.raise_for_status()
            tool_id = resp.json()["id"]
            print(f"  Created: {func_name} ({tool_id})")

        registered_ids.append(tool_id)

    if args.agent_id:
        print(f"\nAttaching {len(registered_ids)} tools to agent {args.agent_id}...")
        resp = requests.patch(
            f"{base_url}/v1/agents/{args.agent_id}",
            json={"tool_ids": registered_ids},
        )
        resp.raise_for_status()
        print("  Done.")

    print(f"\n{len(registered_ids)} tools registered successfully.")


if __name__ == "__main__":
    main()
