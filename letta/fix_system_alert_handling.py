#!/usr/bin/env python3
# DEPRECATED 2026-06-01: One-time setup script.
# References Docker pulse-monitor predecessors `agent-6eb765bf-...` (idle
# since Feb 2026) and `agent-66c4a151-...` (idle since Dec 2025). The
# live pulse-monitor is `agent-2ed14ef4-...` (Docker) and
# `agent-local-d48b128a-...` (local mode). Re-running this script will
# silently fail to update the live agents. Kept for historical reference.
"""
Fix System Alert Handling in Agent System Prompts

Adds instructions to ignore Letta's system_alert messages (conversation summaries)
so agents don't acknowledge or relay them to users.
"""

import sys

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = "http://localhost:8283"

# System alert handling instructions to add
SYSTEM_ALERT_INSTRUCTIONS = """

CRITICAL: System Alert Message Handling
========================================
You may occasionally receive messages with content that starts with:
  "Note: prior messages have been hidden from view due to conversation memory constraints"

These are INTERNAL context management messages from the system. They are NOT part of the
user's conversation and should be completely transparent to the user.

REQUIRED BEHAVIOR:
- DO NOT acknowledge these messages in your responses
- DO NOT reference "system alert", "summary", or "memory constraints"
- DO NOT discuss or explain these messages to the user
- Respond ONLY to the user's actual message as if the system alert never appeared

These summaries are for your context only - the user should never know they exist.
"""

# Agents to update
AGENTS_TO_UPDATE = [
    ('pulse-monitor-agent', 'agent-6eb765bf-7268-4f6d-a380-c527c9c53000'),
    ('pulse-monitor-agent_copy', 'agent-2ed14ef4-6289-453a-ae27-290b6ed196b8'),
    ('pulse-monitor-agent-sleeptime', 'agent-66c4a151-7182-4cfc-9195-68b2e34d0847'),
    ('pulse-monitor-agent-sleeptime_copy', 'agent-fd0cd292-6a10-4b7f-abb3-d7732eae932c'),
    ('calendar-agent', 'agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218'),
    ('calendar-agent_copy', 'agent-892a2d58-b9f6-4baf-84f3-c431fe46487d'),
]


def main():
    """Update system prompts for all affected agents."""

    print("=" * 80)
    print("Fixing System Alert Handling in Agent Prompts")
    print("=" * 80)
    print()

    client = Letta(base_url=LETTA_BASE_URL)

    updated_count = 0
    skipped_count = 0

    for agent_name, agent_id in AGENTS_TO_UPDATE:
        print(f"Processing: {agent_name} ({agent_id})")

        try:
            # Get agent
            agent = client.agents.retrieve(agent_id)

            # Find persona or system block (different agents use different labels)
            instruction_block = None
            instruction_block_id = None
            block_label = None

            if hasattr(agent, 'memory') and hasattr(agent.memory, 'blocks'):
                for block in agent.memory.blocks:
                    if hasattr(block, 'label') and block.label in ('system', 'persona'):
                        instruction_block = block.value
                        instruction_block_id = block.id
                        block_label = block.label
                        break

            if not instruction_block:
                print(f"  ⚠ Warning: No system/persona block found for {agent_name}")
                skipped_count += 1
                continue

            # Check if already has the instructions
            if "System Alert Message Handling" in instruction_block:
                print(f"  → Already has system alert instructions, skipping")
                skipped_count += 1
                continue

            # Add instructions to block
            updated_block = instruction_block + SYSTEM_ALERT_INSTRUCTIONS

            # Update the block
            client.blocks.modify(
                block_id=instruction_block_id,
                value=updated_block
            )

            print(f"  ✓ Updated {block_label} block ({len(SYSTEM_ALERT_INSTRUCTIONS)} chars added)")
            updated_count += 1

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            continue

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"  Updated: {updated_count} agents")
    print(f"  Skipped: {skipped_count} agents")
    print()

    if updated_count > 0:
        print("✓ System prompts updated successfully")
        print()
        print("Agents will now ignore system_alert messages and not relay them to users.")

    return 0 if updated_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
