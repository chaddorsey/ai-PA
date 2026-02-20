#!/usr/bin/env python3
"""
Create queued_tasks_from_drive Block and Attach to Docs & Transcripts Agent

Creates the Letta memory block used by gmail-watch-service to queue
drive comment tasks, then attaches it to the Docs & Transcripts agent.
"""

import os
import sys

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

BLOCK_LABEL = "queued_tasks_from_drive"
DOCS_AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

INITIAL_CONTENT = """# Queued Tasks from Drive Comments

Drive comment tasks queued by gmail-watch-service for extraction.
Process each entry using process_drive_task_queue tool, then remove it.

(empty)
"""


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta Base URL: {LETTA_BASE}")

    client = Letta(base_url=LETTA_BASE)

    # Check if block already exists
    print(f"Looking for existing '{BLOCK_LABEL}' block...")
    blocks = client.blocks.list()
    block = None
    for b in blocks:
        if b.label == BLOCK_LABEL:
            block = b
            print(f"  Found existing block: {b.id}")
            break

    if not block:
        print(f"  Creating new '{BLOCK_LABEL}' block...")
        block = client.blocks.create(
            label=BLOCK_LABEL,
            value=INITIAL_CONTENT,
        )
        print(f"  Created: {block.id}")

    # Attach to Docs & Transcripts agent
    print(f"\nAttaching block to Docs & Transcripts agent ({DOCS_AGENT_ID[:12]}...)...")
    try:
        agent_blocks = client.agents.blocks.list(DOCS_AGENT_ID)
        already_attached = any(b.label == BLOCK_LABEL for b in agent_blocks)

        if already_attached:
            print("  Block already attached")
        else:
            client.agents.blocks.attach(DOCS_AGENT_ID, block.id)
            print("  Block attached")
    except Exception as e:
        print(f"  ERROR attaching block: {e}")
        return 1

    print(f"\nBlock ID: {block.id}")
    print("Set this as DRIVE_TASK_QUEUE_BLOCK_ID in docker-compose.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
