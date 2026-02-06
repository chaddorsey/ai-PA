#!/usr/bin/env python3
"""
Patch Documents Agent with Drive RAG Phase 2 Capabilities

This script patches the Documents Agent's persona and document_organization
blocks to add awareness of:
- Change monitoring (15-minute sync)
- Edit tracking (who changed what, when)
- Document diffs (what changed between versions)
- Recently changed documents query

Run with --dry-run to preview changes without applying them.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
DOCUMENTS_AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

# =============================================================================
# PATCH CONTENT
# =============================================================================

# Text to append to the persona block (after "Document Strategy" section)
PERSONA_PATCH = """
Change Monitoring:
- I track document edits automatically - the index syncs every 15 minutes
- I can show who edited a document and when (`get_document_edits`)
- I can show exactly what changed between versions (`get_document_changes`)
- I can find recently modified documents across 44,000+ indexed files
- New documents in Drive are automatically discovered and indexed
"""

# Text to prepend to document_organization block (before "Core Functions")
DOCUMENT_ORG_PATCH = """Change Monitoring & Edit Tracking:
- 44,000+ documents indexed with automatic 15-minute sync via Drive Changes API
- Track edit history: who modified, when, which revision
- Show diffs between document versions (block-level changes)
- Find recently changed documents: `get_recently_changed_documents(since="yesterday")`
- Supported types: Docs, Sheets, Slides, PDFs, text/markdown files

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


# =============================================================================
# PATCHING LOGIC
# =============================================================================

def find_block(blocks, label):
    """Find a block by label."""
    for block in blocks:
        if block.get('label') == label:
            return block
    return None


def patch_persona(current_value):
    """Patch persona block to add change monitoring section.

    Inserts after 'Document Strategy:' section, before 'Values:' section.
    """
    # Check if already patched
    if "Change Monitoring:" in current_value:
        return None, "Already contains 'Change Monitoring:' section"

    # Find insertion point - after Document Strategy, before Values
    if "Values:" in current_value:
        # Insert before "Values:"
        insertion_point = current_value.find("Values:")
        new_value = (
            current_value[:insertion_point].rstrip() +
            "\n" + PERSONA_PATCH + "\n" +
            current_value[insertion_point:]
        )
    elif "Document Strategy:" in current_value:
        # Find end of Document Strategy section and append after it
        # Look for double newline after Document Strategy
        ds_start = current_value.find("Document Strategy:")
        ds_section_end = current_value.find("\n\n", ds_start + 20)
        if ds_section_end == -1:
            # Append at end
            new_value = current_value.rstrip() + "\n" + PERSONA_PATCH
        else:
            # Find the actual end of the bulleted list
            remaining = current_value[ds_section_end:]
            # Skip past any continuation of bullet points
            new_value = current_value.rstrip() + "\n" + PERSONA_PATCH
    else:
        # Fallback: append at end
        new_value = current_value.rstrip() + "\n" + PERSONA_PATCH

    return new_value, None


def patch_document_organization(current_value):
    """Patch document_organization block to add change monitoring section.

    Prepends the change monitoring section before existing content.
    """
    # Check if already patched
    if "Change Monitoring & Edit Tracking:" in current_value:
        return None, "Already contains 'Change Monitoring & Edit Tracking:' section"

    # Prepend the new section
    new_value = DOCUMENT_ORG_PATCH + current_value

    return new_value, None


# =============================================================================
# MAIN
# =============================================================================

def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("Patch Documents Agent - Drive RAG Phase 2 Capabilities")
    print("=" * 70)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {DOCUMENTS_AGENT_ID}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Get current blocks
    print("Fetching current agent blocks...")
    blocks = get_agent_blocks(DOCUMENTS_AGENT_ID)

    if not blocks:
        print("ERROR: Could not fetch agent blocks")
        return 1

    print(f"Found {len(blocks)} blocks")
    print()

    # Find target blocks
    persona_block = find_block(blocks, "persona")
    doc_org_block = find_block(blocks, "document_organization")

    if not persona_block:
        print("ERROR: Could not find 'persona' block")
        return 1

    if not doc_org_block:
        print("ERROR: Could not find 'document_organization' block")
        return 1

    print(f"Found persona block: {persona_block.get('id')} ({len(persona_block.get('value', ''))} chars)")
    print(f"Found document_organization block: {doc_org_block.get('id')} ({len(doc_org_block.get('value', ''))} chars)")
    print()

    # Create backup
    backup_dir = "/Volumes/main-drive/ai-PA/letta/backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/documents_agent_phase2_backup_{timestamp}.json"

    backup_data = {
        "agent_id": DOCUMENTS_AGENT_ID,
        "timestamp": timestamp,
        "blocks": {
            "persona": {
                "id": persona_block.get('id'),
                "value": persona_block.get('value')
            },
            "document_organization": {
                "id": doc_org_block.get('id'),
                "value": doc_org_block.get('value')
            }
        }
    }

    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2)

    print(f"Backup saved to: {backup_file}")
    print()

    # Compute patches
    print("=" * 70)
    print("COMPUTING PATCHES")
    print("=" * 70)
    print()

    patches = []

    # Patch persona
    print("[persona block]")
    new_persona, persona_skip_reason = patch_persona(persona_block.get('value', ''))
    if persona_skip_reason:
        print(f"  SKIP: {persona_skip_reason}")
    else:
        old_len = len(persona_block.get('value', ''))
        new_len = len(new_persona)
        print(f"  Will patch: {old_len} -> {new_len} chars (+{new_len - old_len})")
        patches.append({
            "label": "persona",
            "block_id": persona_block.get('id'),
            "new_value": new_persona
        })
    print()

    # Patch document_organization
    print("[document_organization block]")
    new_doc_org, doc_org_skip_reason = patch_document_organization(doc_org_block.get('value', ''))
    if doc_org_skip_reason:
        print(f"  SKIP: {doc_org_skip_reason}")
    else:
        old_len = len(doc_org_block.get('value', ''))
        new_len = len(new_doc_org)
        print(f"  Will patch: {old_len} -> {new_len} chars (+{new_len - old_len})")
        patches.append({
            "label": "document_organization",
            "block_id": doc_org_block.get('id'),
            "new_value": new_doc_org
        })
    print()

    if not patches:
        print("No patches to apply - blocks already contain Phase 2 content")
        return 0

    # Show preview
    print("=" * 70)
    print("PATCH PREVIEW")
    print("=" * 70)

    for patch in patches:
        print()
        print(f"--- {patch['label']} ---")
        print()
        # Show the new content being added
        if patch['label'] == 'persona':
            print("Adding after existing content:")
            print(PERSONA_PATCH)
        else:
            print("Prepending to existing content:")
            print(DOCUMENT_ORG_PATCH)

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
        print(f"  Patching [{patch['label']}]...", end=" ")
        result = update_block(patch['block_id'], patch['new_value'])
        if result:
            print("OK")
            results["success"].append(patch['label'])
        else:
            print("FAILED")
            results["failed"].append(patch['label'])

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
    print()

    if results["failed"]:
        print("To restore from backup:")
        print(f"  python restore_block_backup.py {backup_file}")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
