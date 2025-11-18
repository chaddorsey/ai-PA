#!/usr/bin/env python3
"""
Create Drive Analytics memory blocks via Letta API

This script creates the consolidated memory blocks needed for Drive analytics.
"""

import os
import json
import urllib.request

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID", "agent-6eb765bf-7268-4f6d-a380-c527c9c53000")


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"GET Error: {e}")
        return None


def http_post(url, data):
    """Make HTTP POST request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {error_body}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"PATCH Error {e.code}: {error_body}")
        return None


def get_agent():
    """Get agent information."""
    return http_get(f"{LETTA_BASE}/v1/agents/{AGENT_ID}")


def get_existing_blocks(agent_id):
    """Get existing memory blocks for an agent."""
    return http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")


def create_block(block_label, block_value, description=""):
    """Create a memory block."""
    # Check if block already exists
    existing = http_get(f"{LETTA_BASE}/v1/blocks/?label={block_label}")
    if existing and isinstance(existing, list) and len(existing) > 0:
        block_id = existing[0].get("id")
        print(f"  → Block '{block_label}' already exists (ID: {block_id})")
        return block_id
    
    # Create new block with descriptive description
    descriptions = {
        "drive_analytics_workspace": "Workspace-wide Google Drive activity analytics. Contains JSON with date-indexed entries (YYYY-MM-DD format). Each entry has workspace activity data including top-five lists for most edited, shared, commented, viewed documents, and most active users.",
        "drive_analytics_personal": "Personal Google Drive activity analytics. Contains JSON with date-indexed entries (YYYY-MM-DD format). Each entry has your personal activity data including documents you've engaged with, edit/view counts, and document links.",
        "drive_analytics_mentions": "Google Drive comments mentioning you. Contains JSON with date-indexed entries (YYYY-MM-DD format). Each entry has mentions with comment text, document links, timestamps, and author information.",
        "drive_analytics_averages": "Running averages for Drive analytics. Contains calculated 3-day, 10-day, and 50-day averages for various metrics. Updated weekly.",
        "drive_analytics_config": "Configuration for Drive analytics system. Contains settings like your email address and data retention period (max_days)."
    }
    
    # Create new block
    payload = {
        "label": block_label,
        "value": block_value,
        "description": description or descriptions.get(block_label, f"Drive analytics: {block_label}"),
        "limit": 50000  # 50k character limit
    }
    result = http_post(f"{LETTA_BASE}/v1/blocks/", payload)
    if result:
        return result.get("id")
    return None


def attach_block_to_agent(agent_id, block_id):
    """Attach a memory block to an agent."""
    # Check if already attached
    existing_blocks = get_existing_blocks(agent_id)
    if existing_blocks:
        for block in existing_blocks:
            if block.get("id") == block_id:
                print(f"  → Block already attached to agent")
                return True
    
    # Attach block
    result = http_patch(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        {}
    )
    return result is not None


def main():
    print("="*60)
    print("Create Drive Analytics Memory Blocks")
    print("="*60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {AGENT_ID}")
    print()
    
    # Check if agent exists
    agent = get_agent()
    if not agent:
        print(f"❌ Agent {AGENT_ID} not found!")
        return 1
    
    print(f"✓ Found agent: {agent.get('name', 'Unnamed')}")
    print()
    
    # Blocks to create
    blocks = {
        "drive_analytics_workspace": "{}",
        "drive_analytics_personal": "{}",
        "drive_analytics_mentions": "{}",
        "drive_analytics_averages": "{}",
        "drive_analytics_config": json.dumps({
            "my_email": "cdorsey@concord.org",
            "max_days": 50
        }, indent=2)
    }
    
    print("Creating memory blocks...\n")
    
    created = 0
    attached = 0
    for block_label, block_value in blocks.items():
        print(f"→ Creating '{block_label}'...")
        block_id = create_block(block_label, block_value)
        if block_id:
            print(f"  ✓ Created block (ID: {block_id})")
            created += 1
            # Attach to agent
            if attach_block_to_agent(AGENT_ID, block_id):
                print(f"  ✓ Attached to agent")
                attached += 1
            else:
                print(f"  ✗ Failed to attach to agent")
        else:
            print(f"  ✗ Failed to create block")
    
    print()
    print("="*60)
    print("✓ Setup Complete")
    print("="*60)
    print()
    print(f"Created {created} memory blocks")
    print(f"Attached {attached} blocks to agent")
    print()
    
    # Verify blocks are attached
    print("Verifying blocks are attached...")
    attached_blocks = get_existing_blocks(AGENT_ID)
    drive_blocks = [b for b in (attached_blocks or []) if b.get("label", "").startswith("drive_analytics")]
    print(f"Found {len(drive_blocks)} Drive analytics blocks attached:")
    for block in drive_blocks:
        print(f"  • {block.get('label')}")
    print()
    
    if len(drive_blocks) == len(blocks):
        print("✅ All blocks successfully created and attached!")
    else:
        print(f"⚠️  Expected {len(blocks)} blocks, found {len(drive_blocks)}")
    print()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

