#!/usr/bin/env python3
"""Register OmniFocus CLI tool with Letta.

Registers a single general-purpose tool that provides full OmniFocus access:
  - run_omnifocus: CLI-backed tool for all OmniFocus operations

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_omnifocus_tools.py

Requirements:
    - Letta server running at http://localhost:8283
    - omnifocus-cli installed in Letta container (via entrypoint-wrapper.sh)
"""

import os
import sys
from letta_client import Letta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from omnifocus_tools import run_omnifocus

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register_tools():
    """Register OmniFocus tool with Letta."""
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (run_omnifocus, ["omnifocus", "tasks", "projects", "productivity"]),
    ]

    registered = []
    for func, tags in tools:
        try:
            tool = client.tools.create_from_function(
                func=func,
                tags=tags,
            )
            registered.append(tool.name)
            print(f"Registered: {tool.name}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Already exists: {func.__name__}")
                registered.append(func.__name__)
            else:
                print(f"Failed to register {func.__name__}: {e}")

    print(f"\nRegistered {len(registered)} tools")
    return registered


if __name__ == "__main__":
    register_tools()
