#!/usr/bin/env python3
"""
Setup agent_info Memory Blocks for Agent-to-Agent Communication

This script ensures both agents have the required 'agent_info' memory block
that contains their agent_id. This is required for the send_message_to_agent tool
to know the sender's agent_id.

Based on community workaround requirements:
https://forum.letta.com/t/custom-agent-to-agent-messaging-tool-for-v1-architecture/127
"""

import os
import sys
import json
import urllib.request
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass
except Exception:
    pass

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs and their names
AGENTS = [
    ("Main Orchestration Agent", "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"),
    ("Scheduling Agent", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"),
]

BLOCK_LABEL = "agent_info"
BLOCK_DESCRIPTION = "Read-only block containing this agent's ID for agent-to-agent communication"


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
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"POST Error {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"POST Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"PATCH Error {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"PATCH Error: {e}")
        return None


def get_agent(agent_id):
    """Get agent information."""
    return http_get(f"{LETTA_BASE_URL}/v1/agents/{agent_id}")


def get_existing_blocks(agent_id):
    """Get existing memory blocks for an agent."""
    try:
        response = http_get(f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory")
        if response and 'blocks' in response:
            return response['blocks']
        return []
    except Exception as e:
        print(f"Error getting blocks: {e}")
        return []


def find_or_create_block(block_label, block_value, block_description):
    """Find existing block by label or create new one."""
    # Check if block exists
    existing_blocks = http_get(f"{LETTA_BASE_URL}/v1/blocks/?label={block_label}")
    
    if existing_blocks and len(existing_blocks) > 0:
        block_id = existing_blocks[0].get('id')
        print(f"  → Found existing block (ID: {block_id})")
        
        # Update value if needed
        if existing_blocks[0].get('value') != block_value:
            print(f"  → Updating block value...")
            result = http_patch(
                f"{LETTA_BASE_URL}/v1/blocks/{block_id}",
                {"value": block_value}
            )
            if result:
                print(f"  ✓ Updated block value")
            else:
                print(f"  ✗ Failed to update block value")
        
        return block_id
    else:
        # Create new block
        print(f"  → Creating new block...")
        result = http_post(
            f"{LETTA_BASE_URL}/v1/blocks/",
            {
                "label": block_label,
                "description": block_description,
                "value": block_value,
                "limit": 1000  # Small limit for agent_info
            }
        )
        if result and result.get('id'):
            block_id = result['id']
            print(f"  ✓ Created block (ID: {block_id})")
            return block_id
        else:
            print(f"  ✗ Failed to create block")
            return None


def attach_block_to_agent(agent_id, block_id):
    """Attach memory block to agent."""
    result = http_patch(
        f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        {}
    )
    return result is not None


def main():
    print("="*60)
    print("Setup agent_info Memory Blocks for A2A Communication")
    print("="*60)
    print()
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print()
    
    success_count = 0
    
    for agent_name, agent_id in AGENTS:
        print(f"→ Processing {agent_name} ({agent_id})...")
        
        # Check if agent exists
        agent = get_agent(agent_id)
        if not agent:
            print(f"  ✗ Agent {agent_id} not found!")
            continue
        
        print(f"  ✓ Found agent: {agent.get('name', 'Unnamed')}")
        
        # Create or find agent_info block
        block_value = f"agent_id: {agent_id}"
        block_id = find_or_create_block(BLOCK_LABEL, block_value, BLOCK_DESCRIPTION)
        
        if not block_id:
            print(f"  ✗ Failed to create/find block")
            continue
        
        # Check if block is already attached
        existing_blocks = get_existing_blocks(agent_id)
        block_attached = any(b.get('id') == block_id for b in existing_blocks)
        
        if block_attached:
            print(f"  ✓ Block already attached to agent")
        else:
            # Attach block to agent
            print(f"  → Attaching block to agent...")
            if attach_block_to_agent(agent_id, block_id):
                print(f"  ✓ Block attached to agent")
            else:
                print(f"  ✗ Failed to attach block to agent")
                continue
        
        success_count += 1
        print()
    
    print("="*60)
    print("✓ Setup Complete")
    print("="*60)
    print()
    print(f"Successfully set up agent_info blocks for {success_count}/{len(AGENTS)} agents")
    print()
    print("Each agent now has an 'agent_info' memory block containing their agent_id.")
    print("This allows the send_message_to_agent tool to identify the sender.")
    print()
    
    return 0 if success_count == len(AGENTS) else 1


if __name__ == "__main__":
    sys.exit(main())

