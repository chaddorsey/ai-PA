#!/usr/bin/env python3
"""Register search_github_stars tool with the Letta server.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_github_stars_tools.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from letta_client import Letta
from github_stars_tools import search_github_stars

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def main():
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (search_github_stars, ["github", "stars", "repos", "search"]),
    ]

    registered = []
    for func, tags in tools:
        try:
            tool = client.tools.upsert_from_function(
                func=func,
                tags=tags,
            )
            registered.append(tool.name)
            print(f"Registered: {tool.name} ({tool.id})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Already exists: {func.__name__}")
                registered.append(func.__name__)
            else:
                print(f"Failed to register {func.__name__}: {e}")

    print(f"\nRegistered {len(registered)} tools")


if __name__ == "__main__":
    main()
