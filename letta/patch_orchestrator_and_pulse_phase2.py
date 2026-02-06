#!/usr/bin/env python3
"""
Patch Orchestrator (Samantha) and Pulse Monitor with Drive RAG Phase 2 Awareness

This script patches:
1. Samantha's persona - Add document delegation guidance for Phase 2 capabilities
2. Pulse Monitor's slack_pulse_reporting_process - Add document change awareness

Run with --dry-run to preview changes without applying them.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Agent IDs
SAMANTHA_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
PULSE_MONITOR_AGENT_ID = "agent-6eb765bf-7268-4f6d-a380-c527c9c53000"

# =============================================================================
# PATCH CONTENT
# =============================================================================

# For Samantha: Expand the Delegation Philosophy with document-specific guidance
# Insert after "I always provide specialists with enough context to be effective"
SAMANTHA_PERSONA_PATCH = """

Document Delegation (Drive RAG):
- "Find documents about X" → Documents Agent (semantic search)
- "Who edited the budget spreadsheet?" → Documents Agent (edit tracking)
- "What changed in the project plan?" → Documents Agent (document diffs)
- "Show me recent document activity" → Documents Agent (change monitoring)
The Documents Agent has 44,000+ indexed documents with semantic search, edit tracking, and 15-minute change sync."""

# For Pulse Monitor: Add section to slack_pulse_reporting_process
PULSE_REPORTING_PATCH = """

3. Document Activity Section (Optional Enhancement)
   - When generating comprehensive pulse reports, consider including Drive document activity
   - Use `get_recently_changed_documents(since="yesterday")` for daily Drive activity
   - Cross-reference document edits with Slack discussions for fuller context
   - Key metrics to surface:
     - Documents with most edits in period
     - Who's been active editing shared documents
     - Documents edited that relate to current discussions
   - This adds organizational awareness beyond just Slack/Jira/Confluence
"""


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


def get_agent_blocks(agent_id):
    """Get agent's memory blocks."""
    agent = http_request(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if agent:
        return agent.get('memory', {}).get('blocks', [])
    return []


def update_block(block_id, new_value):
    """Update a block's value."""
    return http_request(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        method='PATCH',
        data={"value": new_value}
    )


def find_block(blocks, label):
    """Find a block by label."""
    for block in blocks:
        if block.get('label') == label:
            return block
    return None


# =============================================================================
# PATCHING LOGIC
# =============================================================================

def patch_samantha_persona(current_value):
    """Patch Samantha's persona to add document delegation guidance.

    Appends after "Delegation Philosophy" section.
    """
    # Check if already patched
    if "Document Delegation (Drive RAG):" in current_value:
        return None, "Already contains 'Document Delegation (Drive RAG):' section"

    # Find the end of Delegation Philosophy section
    # Looking for the last line of that section
    marker = "I always provide specialists with enough context to be effective"

    if marker in current_value:
        insertion_point = current_value.find(marker) + len(marker)
        new_value = (
            current_value[:insertion_point] +
            SAMANTHA_PERSONA_PATCH +
            current_value[insertion_point:]
        )
    else:
        # Fallback: append at end
        new_value = current_value.rstrip() + "\n" + SAMANTHA_PERSONA_PATCH

    return new_value, None


def patch_pulse_reporting_process(current_value):
    """Patch Pulse Monitor's reporting process to add document awareness.

    Appends after the existing sections.
    """
    # Check if already patched
    if "Document Activity Section" in current_value:
        return None, "Already contains 'Document Activity Section'"

    # Find the end of existing numbered sections (after section 2)
    # Look for a good insertion point - after the workflow section starts
    if "Workflow:" in current_value:
        # Insert before "Workflow:" but after the structure sections
        insertion_point = current_value.find("Workflow:")
        new_value = (
            current_value[:insertion_point].rstrip() +
            PULSE_REPORTING_PATCH + "\n\n" +
            current_value[insertion_point:]
        )
    else:
        # Fallback: append at end
        new_value = current_value.rstrip() + PULSE_REPORTING_PATCH

    return new_value, None


# =============================================================================
# MAIN
# =============================================================================

def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Patch Orchestrator & Pulse Monitor - Drive RAG Phase 2 Awareness")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Prepare patches list
    patches = []
    backup_data = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "agents": {}
    }

    # =========================================================================
    # SAMANTHA
    # =========================================================================
    print("-" * 70)
    print("SAMANTHA (Main Orchestrator)")
    print("-" * 70)
    print(f"Agent ID: {SAMANTHA_AGENT_ID}")
    print()

    samantha_blocks = get_agent_blocks(SAMANTHA_AGENT_ID)
    if not samantha_blocks:
        print("ERROR: Could not fetch Samantha's blocks")
    else:
        print(f"Found {len(samantha_blocks)} blocks")

        persona_block = find_block(samantha_blocks, "persona")
        if persona_block:
            backup_data["agents"]["samantha"] = {
                "persona": {
                    "id": persona_block.get('id'),
                    "value": persona_block.get('value')
                }
            }

            print(f"Found persona block: {persona_block.get('id')[:30]}... ({len(persona_block.get('value', ''))} chars)")

            new_persona, skip_reason = patch_samantha_persona(persona_block.get('value', ''))
            if skip_reason:
                print(f"  SKIP: {skip_reason}")
            else:
                old_len = len(persona_block.get('value', ''))
                new_len = len(new_persona)
                print(f"  Will patch: {old_len} -> {new_len} chars (+{new_len - old_len})")
                patches.append({
                    "agent": "Samantha",
                    "label": "persona",
                    "block_id": persona_block.get('id'),
                    "new_value": new_persona,
                    "patch_content": SAMANTHA_PERSONA_PATCH
                })
        else:
            print("ERROR: Could not find 'persona' block")

    print()

    # =========================================================================
    # PULSE MONITOR
    # =========================================================================
    print("-" * 70)
    print("PULSE MONITOR")
    print("-" * 70)
    print(f"Agent ID: {PULSE_MONITOR_AGENT_ID}")
    print()

    pulse_blocks = get_agent_blocks(PULSE_MONITOR_AGENT_ID)
    if not pulse_blocks:
        print("ERROR: Could not fetch Pulse Monitor's blocks")
    else:
        print(f"Found {len(pulse_blocks)} blocks")

        reporting_block = find_block(pulse_blocks, "slack_pulse_reporting_process")
        if reporting_block:
            backup_data["agents"]["pulse_monitor"] = {
                "slack_pulse_reporting_process": {
                    "id": reporting_block.get('id'),
                    "value": reporting_block.get('value')
                }
            }

            print(f"Found slack_pulse_reporting_process block: {reporting_block.get('id')[:30]}... ({len(reporting_block.get('value', ''))} chars)")

            new_reporting, skip_reason = patch_pulse_reporting_process(reporting_block.get('value', ''))
            if skip_reason:
                print(f"  SKIP: {skip_reason}")
            else:
                old_len = len(reporting_block.get('value', ''))
                new_len = len(new_reporting)
                print(f"  Will patch: {old_len} -> {new_len} chars (+{new_len - old_len})")
                patches.append({
                    "agent": "Pulse Monitor",
                    "label": "slack_pulse_reporting_process",
                    "block_id": reporting_block.get('id'),
                    "new_value": new_reporting,
                    "patch_content": PULSE_REPORTING_PATCH
                })
        else:
            print("ERROR: Could not find 'slack_pulse_reporting_process' block")

    print()

    if not patches:
        print("No patches to apply - blocks already contain Phase 2 content")
        return 0

    # Save backup
    backup_dir = "/Volumes/main-drive/ai-PA/letta/backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = backup_data["timestamp"]
    backup_file = f"{backup_dir}/orchestrator_pulse_phase2_backup_{timestamp}.json"

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2)

    print(f"Backup saved to: {backup_file}")
    print()

    # Show preview
    print("=" * 70)
    print("PATCH PREVIEW")
    print("=" * 70)

    for patch in patches:
        print()
        print(f"--- {patch['agent']}: {patch['label']} ---")
        print()
        print("Adding:")
        print(patch['patch_content'])

    print()

    if dry_run:
        print("=" * 70)
        print("DRY RUN - No changes applied")
        print("=" * 70)
        print()
        print("Run without --dry-run to apply these patches")
        return 0

    # Confirm
    print("=" * 70)
    print("READY TO APPLY PATCHES")
    print("=" * 70)
    print()
    response = input(f"Apply {len(patches)} patch(es)? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Apply patches
    print()
    print("Applying patches...")

    results = {"success": [], "failed": []}

    for patch in patches:
        print(f"  Patching [{patch['agent']}: {patch['label']}]...", end=" ")
        result = update_block(patch['block_id'], patch['new_value'])
        if result:
            print("OK")
            results["success"].append(f"{patch['agent']}: {patch['label']}")
        else:
            print("FAILED")
            results["failed"].append(f"{patch['agent']}: {patch['label']}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    if results["success"]:
        print(f"Successfully patched ({len(results['success'])}):")
        for label in results["success"]:
            print(f"  ✓ {label}")

    if results["failed"]:
        print(f"Failed ({len(results['failed'])}):")
        for label in results["failed"]:
            print(f"  ✗ {label}")

    print()
    print(f"Backup at: {backup_file}")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
