#!/usr/bin/env python3
"""
Implement Shared Memory Architecture

This script:
1. Creates a single shared [human] block for all 6 agents
2. Creates a single shared [important_people] block for all 6 agents
3. Attaches these shared blocks to each agent (replacing individual copies)
4. Reports temp/empty blocks that could be cleaned up

Based on Letta v1 best practices for multi-agent systems.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs
AGENTS = {
    "Main Orchestrator (samantha)": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
    "Pulse Monitor": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "Calendar Agent": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "Documents Agent": "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",
    "Tasks Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
}

# =============================================================================
# SHARED BLOCK CONTENT
# =============================================================================

SHARED_HUMAN_CONTENT = '''User Information:
- Name: Chad Dorsey
- Email: cdorsey@concord.org
- Role: President and CEO, Concord Consortium
- Organization: Nonprofit educational technology, Concord, MA
- Time zone: EST (UTC-5)

Communication Preferences:
- Appreciates confirmation during interactions
- Prefers early/morning briefings
- Professional but conversational tone

Work Patterns:
- Morning block (9-11am): Email & tasks - prefers NO meetings during this time
- [Other patterns to be learned]

Current Priorities (Q1 2026):
- Submit proposals to NSF and other grant agencies
- Private foundation outreach with Danielle Kehoe (development director)
- Lead organization's collective proposal coordination effort

Cross-Agent Learned Patterns:
[Updated by any agent as preferences are discovered]
'''

# =============================================================================
# HTTP HELPERS
# =============================================================================

def http_request(url, method='GET', data=None):
    """Make HTTP request with redirect handling."""
    if data:
        payload = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method=method
        )
    else:
        req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 307:
            redirect_url = e.headers.get('Location')
            if redirect_url:
                return http_request(redirect_url, method, data)
        error_body = e.read().decode('utf-8')
        print(f"  HTTP Error {e.code}: {error_body[:300]}")
        return None
    except Exception as e:
        print(f"  Request Error: {e}")
        return None


def get_agent(agent_id):
    """Get full agent data."""
    return http_request(f"{LETTA_BASE}/v1/agents/{agent_id}")


def get_agent_blocks(agent_id):
    """Get agent's memory blocks."""
    agent = get_agent(agent_id)
    if agent:
        return agent.get('memory', {}).get('blocks', [])
    return []


def create_block(label, value, limit=5000, description=""):
    """Create a new memory block."""
    data = {
        "label": label,
        "value": value,
        "limit": limit,
    }
    if description:
        data["description"] = description
    return http_request(f"{LETTA_BASE}/v1/blocks", method='POST', data=data)


def attach_block_to_agent(agent_id, block_id):
    """Attach a block to an agent."""
    return http_request(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        method='PATCH'
    )


def detach_block_from_agent(agent_id, block_id):
    """Detach a block from an agent."""
    return http_request(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}",
        method='PATCH'
    )


# =============================================================================
# BACKUP AND ANALYSIS
# =============================================================================

def backup_all_blocks():
    """Backup all blocks from all agents."""
    backup_dir = "/Volumes/main-drive/ai-PA/letta/backups"
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/all_blocks_backup_{timestamp}.json"

    all_data = {}
    for agent_name, agent_id in AGENTS.items():
        blocks = get_agent_blocks(agent_id)
        all_data[agent_name] = {
            "agent_id": agent_id,
            "blocks": blocks
        }

    with open(backup_file, 'w') as f:
        json.dump(all_data, f, indent=2)

    print(f"  Backed up to: {backup_file}")
    return backup_file, all_data


def find_temp_empty_blocks(all_data):
    """Find temp and empty blocks that could be cleaned up."""
    candidates = []

    for agent_name, data in all_data.items():
        for block in data['blocks']:
            label = block.get('label', '')
            value = block.get('value', '')
            block_id = block.get('id', '')

            # Check for temp blocks
            is_temp = (
                label.startswith('temp_') or
                label.startswith('_temp') or
                label.startswith('__temp') or
                'temp' in label.lower()
            )

            # Check for empty blocks
            is_empty = len(value.strip()) == 0

            # Check for test blocks
            is_test = 'test' in label.lower()

            if is_temp or is_empty or is_test:
                candidates.append({
                    'agent': agent_name,
                    'label': label,
                    'block_id': block_id,
                    'chars': len(value),
                    'reason': 'temp' if is_temp else ('empty' if is_empty else 'test')
                })

    return candidates


def find_best_important_people(all_data):
    """Find the best [important_people] block to use as the shared version."""
    candidates = []

    for agent_name, data in all_data.items():
        for block in data['blocks']:
            if block.get('label') == 'important_people':
                candidates.append({
                    'agent': agent_name,
                    'block_id': block.get('id'),
                    'chars': len(block.get('value', '')),
                    'value': block.get('value', '')
                })

    if not candidates:
        return None

    # Return the largest one (most complete)
    return max(candidates, key=lambda x: x['chars'])


# =============================================================================
# MAIN IMPLEMENTATION
# =============================================================================

def main():
    print("=" * 70)
    print("Implement Shared Memory Architecture")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents: {len(AGENTS)}")
    print()

    # Step 1: Backup everything
    print("Step 1: Backing up all blocks...")
    backup_file, all_data = backup_all_blocks()
    print()

    # Step 2: Find temp/empty blocks
    print("Step 2: Identifying temp/empty blocks for potential cleanup...")
    cleanup_candidates = find_temp_empty_blocks(all_data)
    print(f"  Found {len(cleanup_candidates)} candidates:")
    for c in cleanup_candidates:
        print(f"    [{c['label']}] in {c['agent']} - {c['chars']} chars ({c['reason']})")
    print()

    # Step 3: Find best important_people block
    print("Step 3: Finding best [important_people] block...")
    best_important_people = find_best_important_people(all_data)
    if best_important_people:
        print(f"  Best source: {best_important_people['agent']} ({best_important_people['chars']} chars)")
        print(f"  Block ID: {best_important_people['block_id']}")
    else:
        print("  WARNING: No [important_people] block found!")
    print()

    # Step 4: Show current [human] blocks
    print("Step 4: Current [human] blocks to be replaced...")
    human_blocks = {}
    for agent_name, data in all_data.items():
        for block in data['blocks']:
            if block.get('label') == 'human':
                human_blocks[agent_name] = {
                    'block_id': block.get('id'),
                    'chars': len(block.get('value', ''))
                }
                print(f"  {agent_name}: {block.get('id')} ({len(block.get('value', ''))} chars)")
    print()

    # Step 5: Show plan
    print("=" * 70)
    print("IMPLEMENTATION PLAN")
    print("=" * 70)
    print()
    print("1. Create new shared [human] block with consolidated content")
    print(f"   Content: {len(SHARED_HUMAN_CONTENT)} chars")
    print()
    print("2. Use existing [important_people] block as shared version")
    print(f"   Source: {best_important_people['agent'] if best_important_people else 'N/A'}")
    print()
    print("3. For each agent:")
    print("   a. Detach old [human] block")
    print("   b. Attach shared [human] block")
    print("   c. If missing [important_people], attach shared version")
    print()
    print("4. Old [human] blocks will remain in system but unattached")
    print("   (Can be deleted later after verification)")
    print()

    # Confirm
    response = input("Proceed with implementation? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    print()
    print("=" * 70)
    print("EXECUTING IMPLEMENTATION")
    print("=" * 70)

    # Create shared [human] block
    print()
    print("Creating shared [human] block...")
    shared_human = create_block(
        label="human",
        value=SHARED_HUMAN_CONTENT,
        limit=5000,
        description="Shared user information across all agents"
    )

    if not shared_human:
        print("  ERROR: Failed to create shared [human] block")
        return 1

    shared_human_id = shared_human.get('id')
    print(f"  SUCCESS: Created {shared_human_id}")

    # Use the best important_people block as the shared one
    shared_important_people_id = best_important_people['block_id'] if best_important_people else None
    print()
    print(f"Using [important_people] block: {shared_important_people_id}")

    # Track which agents already have important_people
    agents_with_important_people = set()
    for agent_name, data in all_data.items():
        for block in data['blocks']:
            if block.get('label') == 'important_people':
                agents_with_important_people.add(agent_name)

    # Update each agent
    results = {"success": [], "failed": []}

    for agent_name, agent_id in AGENTS.items():
        print()
        print(f"Updating {agent_name}...")

        # Get old human block ID
        old_human_id = human_blocks.get(agent_name, {}).get('block_id')

        # Detach old [human] block
        if old_human_id:
            print(f"  Detaching old [human]: {old_human_id}")
            detach_result = detach_block_from_agent(agent_id, old_human_id)
            if detach_result is None:
                print(f"    WARNING: Detach may have failed (continuing anyway)")

        # Attach shared [human] block
        print(f"  Attaching shared [human]: {shared_human_id}")
        attach_result = attach_block_to_agent(agent_id, shared_human_id)
        if attach_result is None:
            print(f"    ERROR: Failed to attach shared [human]")
            results["failed"].append(agent_name)
            continue

        # Attach shared [important_people] if agent doesn't have it
        if agent_name not in agents_with_important_people and shared_important_people_id:
            print(f"  Attaching shared [important_people]: {shared_important_people_id}")
            attach_ip_result = attach_block_to_agent(agent_id, shared_important_people_id)
            if attach_ip_result is None:
                print(f"    WARNING: Failed to attach [important_people]")
        elif agent_name in agents_with_important_people:
            # Need to replace with shared version if different
            current_ip_id = None
            for block in all_data[agent_name]['blocks']:
                if block.get('label') == 'important_people':
                    current_ip_id = block.get('id')
                    break

            if current_ip_id != shared_important_people_id:
                print(f"  Replacing [important_people] with shared version...")
                # Detach current
                detach_block_from_agent(agent_id, current_ip_id)
                # Attach shared
                attach_block_to_agent(agent_id, shared_important_people_id)

        results["success"].append(agent_name)
        print(f"  SUCCESS")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"Shared [human] block: {shared_human_id}")
    print(f"Shared [important_people] block: {shared_important_people_id}")
    print()
    print(f"Successful updates: {len(results['success'])}")
    for name in results['success']:
        print(f"  ✓ {name}")

    if results['failed']:
        print(f"Failed updates: {len(results['failed'])}")
        for name in results['failed']:
            print(f"  ✗ {name}")

    print()
    print(f"Backup saved to: {backup_file}")
    print()

    # Report cleanup candidates
    if cleanup_candidates:
        print("=" * 70)
        print("CLEANUP CANDIDATES (for review)")
        print("=" * 70)
        print()
        print("The following blocks could potentially be cleaned up:")
        print("(No action taken - awaiting explicit confirmation)")
        print()
        for c in cleanup_candidates:
            print(f"  [{c['label']}]")
            print(f"    Agent: {c['agent']}")
            print(f"    Block ID: {c['block_id']}")
            print(f"    Size: {c['chars']} chars")
            print(f"    Reason: {c['reason']}")
            print()

    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print()
    print("1. Test agents to verify shared blocks are working")
    print("2. Verify [human] content appears in all agent conversations")
    print("3. Verify [important_people] is accessible to all agents")
    print("4. Review cleanup candidates and confirm which to remove")
    print("5. Consider creating domain-specific blocks for specialists")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
