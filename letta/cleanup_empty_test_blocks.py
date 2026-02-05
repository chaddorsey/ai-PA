#!/usr/bin/env python3
"""
Cleanup Empty and Test Blocks

Removes empty and test blocks from agents while preserving
temp blocks that contain useful content.

Blocks to REMOVE (empty/test):
- coordination_task_identity-e80a4f2b-* (empty)
- coordination_gathered_identity-e80a4f2b-* (empty)
- coordination_*-test-manual (test)
- preferences_TEST_* (test)
- __temp_slack_member_analytics_csv (empty)
- _temp_slack_member_analytics_csv (empty)

Blocks to KEEP (have content):
- temp_mpdm_list (108 chars)
- _temp_slack_shared_links_csv (2,150 chars)
"""

import urllib.request
import urllib.error
import json

LETTA_BASE = "http://localhost:8283"

# Blocks to remove - gathered from the audit
BLOCKS_TO_REMOVE = [
    # Empty coordination blocks (shared across multiple agents)
    {
        "block_id": "block-cc7ee5a6-a9e6-41f5-88a2-cd6c9b8c5590",
        "label": "coordination_task_identity-e80a4f2b-a157-47c4-af45-0a4e8f1aec3e",
        "agents": ["Pulse Monitor", "Calendar Agent", "Email Agent"],
        "agent_ids": [
            "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
            "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
            "agent-b4928949-8012-4436-a3c7-a9e510785147",
        ],
        "reason": "empty"
    },
    {
        "block_id": "block-7c0545c7-3f91-49b1-8a9a-c3f19967726c",
        "label": "coordination_gathered_identity-e80a4f2b-a157-47c4-af45-0a4e8f1aec3e",
        "agents": ["Pulse Monitor", "Calendar Agent", "Email Agent"],
        "agent_ids": [
            "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
            "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
            "agent-b4928949-8012-4436-a3c7-a9e510785147",
        ],
        "reason": "empty"
    },
    {
        "block_id": "block-ad4806a9-d0fd-4dc8-950c-e1ff574f5639",
        "label": "coordination_task_identity-e80a4f2b-a157-47c4-af45-0a4e8f1aec3e",
        "agents": ["Tasks Agent"],
        "agent_ids": ["agent-dd15479e-6543-400e-8463-b2a48b13cd4a"],
        "reason": "empty"
    },
    # Test blocks (Calendar Agent)
    {
        "block_id": "block-5542257e-a253-44ee-b227-4e92cfd222af",
        "label": "coordination_gathered_identity-test-manual",
        "agents": ["Calendar Agent"],
        "agent_ids": ["agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"],
        "reason": "test"
    },
    {
        "block_id": "block-742d6b57-bb6b-45c4-b1a6-b6df0754d812",
        "label": "coordination_task_identity-test-manual",
        "agents": ["Calendar Agent"],
        "agent_ids": ["agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"],
        "reason": "test"
    },
    {
        "block_id": "block-493fa5fc-c619-417c-83eb-08e03bd37583",
        "label": "preferences_TEST_E2E_FULL",
        "agents": ["Calendar Agent"],
        "agent_ids": ["agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"],
        "reason": "test"
    },
    {
        "block_id": "block-f8e8dfc2-b5f1-46f7-a375-e9bc02abc324",
        "label": "preferences_TEST_SLACKBOT_HELPER",
        "agents": ["Calendar Agent"],
        "agent_ids": ["agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"],
        "reason": "test"
    },
    {
        "block_id": "block-32e2f517-cdee-4e8a-b36a-0d58ffa925b5",
        "label": "preferences_TEST_VERIFY_E2E",
        "agents": ["Calendar Agent"],
        "agent_ids": ["agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"],
        "reason": "test"
    },
    # Empty temp blocks (Pulse Monitor)
    {
        "block_id": "block-2b462afa-8269-4edf-bb04-210cafafa15a",
        "label": "__temp_slack_member_analytics_csv",
        "agents": ["Pulse Monitor"],
        "agent_ids": ["agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"],
        "reason": "empty temp"
    },
    {
        "block_id": "block-b2f14f50-ff0f-4cb9-8791-56998755a97a",
        "label": "_temp_slack_member_analytics_csv",
        "agents": ["Pulse Monitor"],
        "agent_ids": ["agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"],
        "reason": "empty temp"
    },
]


def detach_block(agent_id, block_id):
    """Detach a block from an agent."""
    url = f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}"
    req = urllib.request.Request(url, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Block not attached - that's fine
            return True
        print(f"      Error detaching: {e.code}")
        return False
    except Exception as e:
        print(f"      Error: {e}")
        return False


def delete_block(block_id):
    """Delete a block."""
    url = f"{LETTA_BASE}/v1/blocks/{block_id}"
    req = urllib.request.Request(url, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Block already deleted
            return True
        print(f"      Error deleting: {e.code}")
        return False
    except Exception as e:
        print(f"      Error: {e}")
        return False


def main():
    print("=" * 70)
    print("Cleanup Empty and Test Blocks")
    print("=" * 70)
    print()
    print(f"Blocks to remove: {len(BLOCKS_TO_REMOVE)}")
    print()

    # Show what will be removed
    print("The following blocks will be removed:")
    for block in BLOCKS_TO_REMOVE:
        print(f"  [{block['label']}]")
        print(f"    Reason: {block['reason']}")
        print(f"    Agents: {', '.join(block['agents'])}")
    print()

    response = input("Proceed with cleanup? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    print()
    print("=" * 70)
    print("EXECUTING CLEANUP")
    print("=" * 70)

    removed = 0
    failed = 0

    for block in BLOCKS_TO_REMOVE:
        print()
        print(f"[{block['label']}]")

        # Step 1: Detach from all agents
        for agent_id in block['agent_ids']:
            print(f"  Detaching from {agent_id}...")
            detach_block(agent_id, block['block_id'])

        # Step 2: Delete the block
        print(f"  Deleting block {block['block_id']}...")
        if delete_block(block['block_id']):
            print(f"  ✓ Removed")
            removed += 1
        else:
            print(f"  ✗ Failed to delete")
            failed += 1

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Removed: {removed}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("✓ All empty/test blocks cleaned up successfully!")
    else:
        print(f"✗ {failed} blocks could not be removed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
