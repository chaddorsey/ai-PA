#!/usr/bin/env python3
"""Register Google Workspace CLI tools with Letta.

Registers two tools that provide full Google Workspace API access:
  - run_gws: General-purpose tool for ANY gws CLI command
  - fetch_gmail_messages: Batch-fetch Gmail messages with configurable fields

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_gmail_tools.py

Requirements:
    - Letta server running at http://localhost:8283
    - gws CLI installed in Letta container (via entrypoint-wrapper.sh)
    - gws credentials mounted at /root/.gws/credentials.json
"""

import os
import sys
from letta_client import Letta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_tools import (
    run_gws,
    fetch_gmail_messages,
)

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register_tools():
    """Register Google Workspace tools with Letta."""
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (run_gws, ["gws", "google", "gmail", "calendar", "drive"]),
        (fetch_gmail_messages, ["gws", "gmail", "email", "batch", "inbox"]),
    ]

    registered = []
    for func, tags in tools:
        try:
            tool = client.tools.upsert_from_function(
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
