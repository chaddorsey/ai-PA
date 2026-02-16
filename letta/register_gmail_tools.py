#!/usr/bin/env python3
"""Register Gmail tools with Letta.

This script registers custom Gmail API tools with the Letta agent framework,
replacing the previous MCP-based gmail tools.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_gmail_tools.py

Requirements:
    - Letta server running at http://localhost:8283
    - Gmail OAuth credentials mounted at /root/.gmail-mcp/ in Letta container
    - google-api-python-client installed in Letta sandbox
"""

import os
import sys
from letta_client import Letta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_tools import (
    search_emails,
    read_email,
    get_email_thread,
    send_email,
    reply_to_email,
    draft_email,
    modify_email,
    list_labels,
    download_attachment,
)

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register_tools():
    """Register all Gmail tools with Letta."""
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (search_emails, ["gmail", "email", "search"]),
        (read_email, ["gmail", "email", "read"]),
        (get_email_thread, ["gmail", "email", "thread"]),
        (send_email, ["gmail", "email", "send"]),
        (reply_to_email, ["gmail", "email", "reply"]),
        (draft_email, ["gmail", "email", "draft"]),
        (modify_email, ["gmail", "email", "labels"]),
        (list_labels, ["gmail", "email", "labels"]),
        (download_attachment, ["gmail", "email", "attachment"]),
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
