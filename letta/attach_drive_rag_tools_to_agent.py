#!/usr/bin/env python3
"""Attach Drive RAG tools to a Letta agent.

This script attaches the registered document search and ingestion
tools to a specified Letta agent.

Usage:
    python attach_drive_rag_tools_to_agent.py [agent_id]

    If no agent_id is provided, uses LETTA_AGENT_ID environment variable.
"""

import os
import sys
from letta_client import Letta

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

# Tool names to attach
DRIVE_RAG_TOOLS = [
    "search_documents",
    "get_document_content",
    "list_indexed_documents",
    "ingest_document",
    "get_index_stats",
    "get_document_edits",
    "get_document_changes",
    "fetch_document_from_drive",
    "find_related_documents",
    "explore_document_entities",
    "extract_document_entities",
]


def attach_tools(agent_id: str):
    """Attach Drive RAG tools to an agent."""
    client = Letta(base_url=LETTA_BASE_URL)

    # Get all available tools
    all_tools = client.tools.list()
    tool_map = {t.name: t for t in all_tools}

    # Get current agent tools
    agent = client.agents.retrieve(agent_id=agent_id)
    current_tool_ids = [t.id for t in agent.tools] if agent.tools else []

    attached = []
    for tool_name in DRIVE_RAG_TOOLS:
        tool = tool_map.get(tool_name)
        if not tool:
            print(f"Tool not found: {tool_name} - run register_drive_rag_tools.py first")
            continue

        if tool.id in current_tool_ids:
            print(f"Already attached: {tool_name}")
            attached.append(tool_name)
            continue

        try:
            client.agents.tools.attach(
                agent_id=agent_id,
                tool_id=tool.id,
            )
            attached.append(tool_name)
            print(f"Attached: {tool_name}")
        except Exception as e:
            print(f"Failed to attach {tool_name}: {e}")

    print(f"\nAttached {len(attached)} tools to agent {agent_id}")
    return attached


if __name__ == "__main__":
    # Get agent ID from argument or environment
    if len(sys.argv) > 1:
        agent_id = sys.argv[1]
    else:
        agent_id = os.environ.get("LETTA_AGENT_ID")

    if not agent_id:
        print("Error: No agent ID provided.")
        print("Usage: python attach_drive_rag_tools_to_agent.py <agent_id>")
        print("   Or: set LETTA_AGENT_ID environment variable")
        sys.exit(1)

    attach_tools(agent_id)
