#!/usr/bin/env python3
"""Register Drive RAG tools with Letta.

This script registers the document search and ingestion tools
with the Letta agent framework.

Usage:
    python register_drive_rag_tools.py

Requirements:
    - Letta server running at http://localhost:8283
    - drive-rag-service running (for tools to work)
"""

import os
import sys
from letta_client import Letta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drive_rag_tools import (
    search_documents,
    get_document_content,
    list_indexed_documents,
    ingest_document,
    get_index_stats,
    get_document_edits,
    get_document_changes,
    get_recently_changed_documents,
    fetch_document_from_drive,
    find_related_documents,
    explore_document_entities,
    extract_document_entities,
)

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register_tools():
    """Register all Drive RAG tools with Letta."""
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (search_documents, ["drive-rag", "search", "documents"]),
        (get_document_content, ["drive-rag", "documents"]),
        (list_indexed_documents, ["drive-rag", "documents"]),
        (ingest_document, ["drive-rag", "ingestion"]),
        (get_index_stats, ["drive-rag", "stats"]),
        (get_document_edits, ["drive-rag", "edits", "history"]),
        (get_document_changes, ["drive-rag", "edits", "diff"]),
        (get_recently_changed_documents, ["drive-rag", "edits", "recent"]),
        (fetch_document_from_drive, ["drive-rag", "documents", "fetch"]),
        (find_related_documents, ["drive-rag", "entities", "search"]),
        (explore_document_entities, ["drive-rag", "entities", "explore"]),
        (extract_document_entities, ["drive-rag", "entities", "extract"]),
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
