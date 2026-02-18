#!/usr/bin/env python3
"""Register Gmail Watch tools with Letta."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from letta_client import Letta

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

TOOLS_MODULE = "gmail_watch_tools"
TOOL_FUNCTIONS = [
    "watch_gmail_thread",
    "unwatch_gmail_thread",
    "list_watched_gmail_threads",
    "get_gmail_watch_status",
]


def main():
    client = Letta(base_url=LETTA_BASE_URL)

    # Get existing tools
    existing_tools = client.tools.list()
    existing_names = {t.name: t for t in existing_tools}

    import importlib
    module = importlib.import_module(TOOLS_MODULE)

    for func_name in TOOL_FUNCTIONS:
        func = getattr(module, func_name)

        if func_name in existing_names:
            print(f"  Updating existing tool: {func_name}")
            client.tools.upsert_from_function(func=func)
        else:
            print(f"  Creating new tool: {func_name}")
            client.tools.upsert_from_function(func=func)

    print(f"\nRegistered {len(TOOL_FUNCTIONS)} Gmail Watch tools.")

    # Verify
    all_tools = client.tools.list()
    registered = [t.name for t in all_tools if t.name in TOOL_FUNCTIONS]
    print(f"Verified: {registered}")


if __name__ == "__main__":
    main()
