#!/usr/bin/env python3
"""
Import Granola meeting transcripts from local cache to Letta archival memory.

This script reads the Granola cache file and imports meetings with transcripts
that haven't already been imported. Useful for real-time/periodic import of
new meetings.

Usage:
    # Dry run (no insertion)
    python granola_cache_to_archival.py --dry-run

    # Import all available meetings with transcripts
    python granola_cache_to_archival.py

    # Import meetings from specific date onwards
    python granola_cache_to_archival.py --since 2026-01-27
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from letta_client import Letta
    LETTA_SDK_AVAILABLE = True
except ImportError:
    LETTA_SDK_AVAILABLE = False
    print("Warning: letta_client not available")

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")
CACHE_PATH = Path(os.path.expanduser("~/Library/Application Support/Granola/cache-v3.json"))
STATE_FILE = Path("/Volumes/main-drive/ai-PA/letta/.granola_cache_import_state.json")

# Your organization domain for internal/external classification
INTERNAL_DOMAIN = "concord.org"

# Token/character limits for archival memory
MAX_PASSAGE_CHARS = 28000

# Global Letta client
_letta_client = None


def get_letta_client():
    """Get or create Letta client singleton."""
    global _letta_client
    if _letta_client is None and LETTA_SDK_AVAILABLE:
        _letta_client = Letta(base_url=LETTA_BASE_URL)
    return _letta_client


def load_granola_cache() -> Optional[dict]:
    """Load and parse the Granola cache file."""
    if not CACHE_PATH.exists():
        print(f"  Cache file not found: {CACHE_PATH}")
        return None

    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        inner = json.loads(raw.get('cache', '{}'))
        state = inner.get('state', {})

        return {
            'transcripts': state.get('transcripts', {}),
            'documents': state.get('documents', {}),
            'meetings_metadata': state.get('meetingsMetadata', {}),
            'document_panels': state.get('documentPanels', {})
        }
    except Exception as e:
        print(f"  Error loading cache: {e}")
        return None


def format_transcript(transcript_data) -> str:
    """Format transcript segments into readable text."""
    # Transcript is a list of segments directly
    if not transcript_data or not isinstance(transcript_data, list):
        return ""

    lines = []
    for seg in transcript_data:
        source = seg.get('source', 'unknown')
        text = seg.get('text', '').strip()
        if text:
            # Map source to speaker
            speaker = "Me:" if source == 'microphone' else "Them:"
            lines.append(f"{speaker} {text}")

    return "\n".join(lines)


def generate_tags(meeting_meta: dict, documents: dict, meeting_id: str) -> list:
    """Generate searchable tags for the meeting."""
    tags = []

    # Date tag
    created = meeting_meta.get('created_at', '')
    if created:
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            tags.append(f"date:{dt.strftime('%Y-%m')}")
        except:
            pass

    # Meeting ID tag
    tags.append(f"id:{meeting_id}")

    # Get attendees from meeting_meta (where Granola stores them)
    attendees = meeting_meta.get('attendees', [])

    # Participant tags
    domains = set()
    for att in attendees:
        name = att.get('name', '')
        email = att.get('email', '')

        if name:
            first_name = name.split()[0].lower() if name else ""
            if first_name and len(first_name) > 1 and first_name.isalpha():
                tags.append(f"participant:{first_name}")

        if email and '@' in email:
            domain = email.split('@')[1].lower()
            domains.add(domain)

    # Organization tags
    for domain in domains:
        if domain != INTERNAL_DOMAIN:
            tags.append(f"org:{domain}")

    # Meeting type
    attendee_count = len(attendees)
    if attendee_count <= 2:
        tags.append("type:1on1")
    elif attendee_count <= 4:
        tags.append("type:small-group")
    else:
        tags.append("type:team")

    # Internal/External scope
    if domains and all(d == INTERNAL_DOMAIN for d in domains):
        tags.append("internal")
    elif domains:
        tags.append("external")

    # Source marker
    tags.append("source:cache")

    return list(set(tags))


def get_summary_from_panels(meeting_id: str, document_panels: dict) -> str:
    """Extract AI-generated summary from document panels.

    The summary is stored in documentPanels[meeting_id][panel_id]['original_content']
    for panels with template_slug 'meeting-summary-consolidated'.
    """
    panels = document_panels.get(meeting_id, {})
    if not panels:
        return ""

    # Find the summary panel
    for panel_id, panel in panels.items():
        if isinstance(panel, dict):
            template = panel.get('template_slug', '')
            if 'summary' in template.lower():
                # Prefer original_content (HTML) over content (structured)
                original = panel.get('original_content', '')
                if original:
                    # Convert HTML to plain text (basic)
                    import re
                    # Remove HTML tags
                    text = re.sub(r'<[^>]+>', '\n', original)
                    # Clean up whitespace
                    text = re.sub(r'\n\s*\n', '\n\n', text)
                    text = text.strip()
                    return text
    return ""


def format_content(meeting_id: str, meeting_meta: dict, documents: dict,
                   document_panels: dict, transcript_text: str) -> str:
    """Format meeting content for archival memory."""
    lines = []

    title = meeting_meta.get('title', 'Untitled Meeting')
    lines.append(f"## Meeting: {title}")
    lines.append("")

    lines.append(f"**ID:** {meeting_id}")

    created = meeting_meta.get('created_at', '')
    if created:
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            lines.append(f"**Date:** {dt.strftime('%Y-%m-%d %H:%M')}")
        except:
            pass

    # Get attendees from meeting_meta (where Granola stores them)
    attendees = meeting_meta.get('attendees', [])
    if attendees:
        names = [a.get('name', 'Unknown') for a in attendees if a.get('name')]
        if names:
            lines.append(f"**Participants:** {', '.join(names)}")

    # Get document for notes
    doc = documents.get(meeting_id, {})

    # User's own notes (typed during meeting)
    my_notes = doc.get('notes_markdown', '') or doc.get('notes_plain', '')
    if my_notes and my_notes.strip():
        lines.append("")
        lines.append("### My Notes")
        lines.append(my_notes.strip())

    # AI-generated summary from document panels (primary) or document (fallback)
    enhanced_notes = get_summary_from_panels(meeting_id, document_panels)
    if not enhanced_notes:
        enhanced_notes = doc.get('enhancedNotes', '')

    if enhanced_notes and enhanced_notes.strip():
        lines.append("")
        lines.append("### Summary")
        lines.append(enhanced_notes.strip())

    # Transcript
    if transcript_text:
        lines.append("")
        lines.append("### Transcript")
        lines.append(transcript_text)

    return '\n'.join(lines)


def split_long_text(text: str, max_chars: int) -> list:
    """
    Split long text into chunks at sentence or word boundaries.
    Used when a single line exceeds the max character limit.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_chars:
        # Find a good break point before max_chars
        chunk_end = max_chars

        # Try to break at sentence boundary (. ! ?)
        for punct in ['. ', '! ', '? ', '." ', '!" ', '?" ']:
            last_punct = remaining[:max_chars].rfind(punct)
            if last_punct > max_chars // 2:  # Only if it's in the second half
                chunk_end = last_punct + len(punct)
                break
        else:
            # No sentence boundary, try word boundary
            last_space = remaining[:max_chars].rfind(' ')
            if last_space > max_chars // 2:
                chunk_end = last_space + 1

        chunks.append(remaining[:chunk_end].strip())
        remaining = remaining[chunk_end:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def chunk_content(content: str, meeting_id: str, tags: list, meeting_title: str = "Meeting") -> list:
    """Split content into chunks if it exceeds the token limit."""
    if len(content) <= MAX_PASSAGE_CHARS:
        return [(content, tags)]

    chunks = []
    parts = content.split("### Transcript")

    if len(parts) == 2:
        header_and_summary = parts[0].strip()
        transcript = parts[1].strip()

        # First chunk: header + summary
        chunk1 = header_and_summary
        chunk1_tags = tags + ["chunk:summary"]

        if len(chunk1) <= MAX_PASSAGE_CHARS:
            chunks.append((chunk1, chunk1_tags))
        else:
            chunks.append((chunk1[:MAX_PASSAGE_CHARS], chunk1_tags))

        # Transcript chunks - handle long lines without newlines
        transcript_lines = transcript.split('\n')

        # Expand long lines by splitting at sentence/word boundaries
        expanded_lines = []
        for line in transcript_lines:
            if len(line) > MAX_PASSAGE_CHARS - 500:  # Leave room for header
                expanded_lines.extend(split_long_text(line, MAX_PASSAGE_CHARS - 500))
            else:
                expanded_lines.append(line)

        current_chunk = f"## Meeting: {meeting_title} (Transcript continued)\n\n**ID:** {meeting_id}\n\n### Transcript\n"
        chunk_num = 1

        def has_dialogue(text: str) -> bool:
            """Check if text contains actual dialogue content."""
            return 'Me:' in text or 'Them:' in text

        for line in expanded_lines:
            test_chunk = current_chunk + line + '\n'

            if len(test_chunk) > MAX_PASSAGE_CHARS:
                # Only save chunk if it has actual dialogue content (not just headers)
                if current_chunk.strip() and len(current_chunk) > 500 and has_dialogue(current_chunk):
                    chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
                    chunks.append((current_chunk.strip(), chunk_tags))
                    chunk_num += 1

                current_chunk = f"## Meeting: {meeting_title} (Transcript continued)\n\n**ID:** {meeting_id}\n\n### Transcript\n{line}\n"
            else:
                current_chunk = test_chunk

        # Last chunk - must have dialogue content, not just headers
        if current_chunk.strip() and "### Transcript" in current_chunk and len(current_chunk) > 500 and has_dialogue(current_chunk):
            chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
            chunks.append((current_chunk.strip(), chunk_tags))
    else:
        # No clear transcript section, chunk by size
        chunk_num = 1
        for i in range(0, len(content), MAX_PASSAGE_CHARS):
            chunk = content[i:i + MAX_PASSAGE_CHARS]
            chunk_tags = tags + [f"chunk:{chunk_num}"]
            chunks.append((chunk, chunk_tags))
            chunk_num += 1

    return chunks


def insert_to_archival(content: str, tags: list, dry_run: bool = False) -> bool:
    """Insert content into Letta archival memory."""
    if dry_run:
        print(f"  [DRY RUN] Would insert {len(content)} chars with tags: {tags[:5]}...")
        return True

    client = get_letta_client()
    if not client:
        print("  Letta client not available")
        return False

    try:
        client.agents.passages.create(
            agent_id=AGENT_ID,
            text=content,
            tags=tags  # Store tags for filterable search
        )
        return True
    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        print(f"  Error: {error_msg}")
        return False


def load_state() -> dict:
    """Load import state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {'imported_ids': []}


def save_state(state: dict):
    """Save import state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Import Granola cache to Letta archival memory')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not insert')
    parser.add_argument('--since', type=str, help='Only import meetings from this date onwards (YYYY-MM-DD)')
    parser.add_argument('--reset', action='store_true', help='Reset state and reimport all')
    args = parser.parse_args()

    print("=" * 70)
    print("Granola Cache to Letta Archival Memory Import")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Cache: {CACHE_PATH}")
    print(f"Dry run: {args.dry_run}")
    if args.since:
        print(f"Since: {args.since}")
    print()

    # Load state
    if args.reset:
        state = {'imported_ids': []}
        save_state(state)
        print("State reset.")
    else:
        state = load_state()

    imported_ids = set(state.get('imported_ids', []))
    print(f"Previously imported: {len(imported_ids)} meetings")

    # Load cache
    cache = load_granola_cache()
    if not cache:
        print("Failed to load cache")
        return

    transcripts = cache['transcripts']
    documents = cache['documents']
    meetings_meta = cache['meetings_metadata']
    document_panels = cache['document_panels']

    print(f"Cache contains: {len(transcripts)} transcripts, {len(meetings_meta)} meetings")
    print()

    # Find meetings to import
    meetings_to_import = []
    for meeting_id, transcript_data in transcripts.items():
        # Skip if already imported
        if meeting_id in imported_ids:
            continue

        # Get metadata
        meta = meetings_meta.get(meeting_id, {})
        created = meta.get('created_at', '')

        # Filter by date if specified
        if args.since and created < args.since:
            continue

        meetings_to_import.append({
            'id': meeting_id,
            'meta': meta,
            'transcript': transcript_data
        })

    # Sort by date
    meetings_to_import.sort(key=lambda x: x['meta'].get('created_at', ''))

    print(f"Meetings to import: {len(meetings_to_import)}")
    print()

    if not meetings_to_import:
        print("No new meetings to import.")
        return

    # Process meetings
    success_count = 0
    error_count = 0

    for i, meeting in enumerate(meetings_to_import, 1):
        meeting_id = meeting['id']
        meta = meeting['meta']
        transcript_data = meeting['transcript']

        title = meta.get('title', 'Untitled')[:50]
        print(f"[{i}/{len(meetings_to_import)}] {title}...")

        # Format transcript
        transcript_text = format_transcript(transcript_data)
        if not transcript_text:
            print("  No transcript text, skipping")
            continue

        # Generate tags
        tags = generate_tags(meta, documents, meeting_id)

        # Format content
        content = format_content(meeting_id, meta, documents, document_panels, transcript_text)
        tag_line = f"**Tags:** {', '.join(tags)}\n\n"
        full_content = tag_line + content

        # Chunk if needed
        meeting_title = meta.get('title', 'Untitled Meeting')
        chunks = chunk_content(full_content, meeting_id, tags, meeting_title)
        chunk_count = len(chunks)

        # Insert all chunks
        all_success = True
        for chunk_idx, (chunk_text, chunk_tags) in enumerate(chunks, 1):
            if not insert_to_archival(chunk_text, chunk_tags, dry_run=args.dry_run):
                all_success = False
                print(f"  Failed chunk {chunk_idx}/{chunk_count}")
                break

        if all_success:
            success_count += 1
            if not args.dry_run:
                imported_ids.add(meeting_id)
                state['imported_ids'] = list(imported_ids)
                save_state(state)

            if chunk_count > 1:
                print(f"  Inserted ({len(full_content)} chars, {chunk_count} chunks)")
            else:
                print(f"  Inserted ({len(full_content)} chars)")
        else:
            error_count += 1

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total: {len(meetings_to_import)}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")

    if args.dry_run:
        print("\n[DRY RUN] No data was inserted")
    else:
        print(f"\n Imported {success_count} meetings from cache.")


if __name__ == "__main__":
    main()
