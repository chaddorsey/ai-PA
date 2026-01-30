#!/usr/bin/env python3
"""
Backfill Granola meeting transcripts to Letta archival memory.

This script parses Zapier-exported Granola transcript files and inserts them
into a Letta agent's archival memory with appropriate tags for searchability.

Usage:
    # Dry run (no insertion)
    python granola_to_archival.py --dry-run

    # Insert all files
    python granola_to_archival.py

    # Insert specific file
    python granola_to_archival.py --file path/to/file.txt

    # Resume from specific file (alphabetically)
    python granola_to_archival.py --resume-from "granolaNote--2025-06"
"""

import os
import re
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
    print("Warning: letta_client not available, using HTTP fallback")

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")
SOURCE_DIR = Path("/Volumes/main-drive/ai-PA/data-resources/granola-transcripts")
STATE_FILE = Path("/Volumes/main-drive/ai-PA/letta/.granola_backfill_state.json")

# Your organization domain for internal/external classification
INTERNAL_DOMAIN = "concord.org"

# Token/character limits for archival memory
# Letta has 8192 token limit; ~4 chars per token gives us ~30000 chars safe limit
MAX_PASSAGE_CHARS = 28000

# Global Letta client
_letta_client = None


def get_letta_client():
    """Get or create Letta client singleton."""
    global _letta_client
    if _letta_client is None and LETTA_SDK_AVAILABLE:
        _letta_client = Letta(base_url=LETTA_BASE_URL)
    return _letta_client


def parse_granola_export(file_path: Path) -> Optional[dict]:
    """
    Parse a Zapier-exported Granola transcript file.

    Format:
    {
    {meetingNoteId: uuid},
    {meetingNoteTitle: title},
    {calendarEventId: id},
    {calendarEventTime: ISO datetime},
    {calendarEventTitle: title},
    {attendeesEmail: email1,email2},
    {attendeesName: name1,name2},
    {granolaLink: url},
    {myNotes: text},
    {enhancedNotes: text},
    {transcript: text}
    }
    """
    try:
        content = file_path.read_text(encoding='utf-8')

        # Extract fields using regex
        def extract_field(field_name: str) -> str:
            # Match {fieldName: value} or {fieldName: value},
            pattern = rf'\{{{field_name}:\s*(.*?)\}}'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
            return ""

        meeting_id = extract_field("meetingNoteId")
        title = extract_field("meetingNoteTitle")
        calendar_time = extract_field("calendarEventTime")
        attendees_email = extract_field("attendeesEmail")
        attendees_name = extract_field("attendeesName")
        granola_link = extract_field("granolaLink")
        my_notes = extract_field("myNotes")
        enhanced_notes = extract_field("enhancedNotes")
        transcript = extract_field("transcript")

        if not meeting_id:
            print(f"  ⚠️  No meeting ID found in {file_path.name}")
            return None

        # Parse date
        meeting_date = None
        if calendar_time:
            try:
                # Handle various ISO formats
                calendar_time = calendar_time.replace('Z', '+00:00')
                meeting_date = datetime.fromisoformat(calendar_time)
            except ValueError:
                pass

        # Parse attendees
        emails = [e.strip() for e in attendees_email.split(',') if e.strip()]
        names = [n.strip() for n in attendees_name.split(',') if n.strip()]

        return {
            'meeting_id': meeting_id,
            'title': title or "Untitled Meeting",
            'date': meeting_date,
            'attendees_email': emails,
            'attendees_name': names,
            'granola_link': granola_link,
            'my_notes': my_notes,
            'enhanced_notes': enhanced_notes,
            'transcript': transcript,
            'source_file': file_path.name
        }

    except Exception as e:
        print(f"  ❌ Error parsing {file_path.name}: {e}")
        return None


def generate_tags(meeting: dict) -> list:
    """Generate searchable tags for the meeting."""
    tags = []

    # Date tag (required)
    if meeting['date']:
        tags.append(f"date:{meeting['date'].strftime('%Y-%m')}")

    # Meeting ID tag
    tags.append(f"id:{meeting['meeting_id']}")

    # Participant tags (first names, lowercase)
    for name in meeting['attendees_name']:
        first_name = name.split()[0].lower() if name else ""
        if first_name and len(first_name) > 1:
            # Clean up names that are just usernames
            first_name = first_name.replace('_', '').replace('-', '')
            if first_name.isalpha():
                tags.append(f"participant:{first_name}")

    # Organization tags (from email domains)
    domains = set()
    for email in meeting['attendees_email']:
        if '@' in email:
            domain = email.split('@')[1].lower()
            domains.add(domain)

    for domain in domains:
        if domain != INTERNAL_DOMAIN:
            tags.append(f"org:{domain}")

    # Meeting type
    attendee_count = len(meeting['attendees_name'])
    if attendee_count <= 1:
        tags.append("type:1on1")
    elif attendee_count <= 3:
        tags.append("type:small-group")
    else:
        tags.append("type:team")

    # Internal/External scope
    if domains and all(d == INTERNAL_DOMAIN for d in domains):
        tags.append("internal")
    elif domains:
        tags.append("external")

    # Source marker (distinguishes from cache imports)
    tags.append("source:backfill")

    # Deduplicate
    return list(set(tags))


def format_content(meeting: dict) -> str:
    """Format meeting content for archival memory."""
    lines = []

    # Header
    lines.append(f"## Meeting: {meeting['title']}")
    lines.append("")

    # Metadata
    lines.append(f"**ID:** {meeting['meeting_id']}")
    if meeting['date']:
        lines.append(f"**Date:** {meeting['date'].strftime('%Y-%m-%d %H:%M %Z')}")

    if meeting['attendees_name']:
        names = ', '.join(meeting['attendees_name'])
        lines.append(f"**Participants:** {names}")

    if meeting['granola_link']:
        lines.append(f"**Granola Link:** {meeting['granola_link']}")

    lines.append("")

    # My Notes (if present)
    if meeting['my_notes'] and meeting['my_notes'].strip():
        lines.append("### My Notes")
        lines.append(meeting['my_notes'].strip())
        lines.append("")

    # Enhanced Notes / Summary
    if meeting['enhanced_notes'] and meeting['enhanced_notes'].strip():
        lines.append("### Summary")
        lines.append(meeting['enhanced_notes'].strip())
        lines.append("")

    # Transcript
    if meeting['transcript'] and meeting['transcript'].strip():
        lines.append("### Transcript")
        lines.append(meeting['transcript'].strip())

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


def chunk_content(content: str, meeting: dict, tags: list) -> list:
    """
    Split content into chunks if it exceeds the token limit.
    Returns list of (chunk_content, chunk_tags) tuples.
    """
    if len(content) <= MAX_PASSAGE_CHARS:
        return [(content, tags)]

    chunks = []

    # Split into metadata/summary section and transcript section
    parts = content.split("### Transcript")

    if len(parts) == 2:
        header_and_summary = parts[0].strip()
        transcript = parts[1].strip()

        # First chunk: header + summary (should fit)
        chunk1 = header_and_summary
        chunk1_tags = tags + ["chunk:summary"]

        if len(chunk1) <= MAX_PASSAGE_CHARS:
            chunks.append((chunk1, chunk1_tags))
        else:
            # Even header is too long, truncate summary
            chunks.append((chunk1[:MAX_PASSAGE_CHARS], chunk1_tags))

        # Remaining chunks: transcript in segments
        # First, split transcript into lines, then handle long lines
        transcript_lines = transcript.split('\n')

        # Expand long lines by splitting them at sentence/word boundaries
        expanded_lines = []
        for line in transcript_lines:
            if len(line) > MAX_PASSAGE_CHARS - 500:  # Leave room for header
                expanded_lines.extend(split_long_text(line, MAX_PASSAGE_CHARS - 500))
            else:
                expanded_lines.append(line)

        current_chunk = f"## Meeting: {meeting['title']} (Transcript continued)\n\n**ID:** {meeting['meeting_id']}\n\n### Transcript\n"
        chunk_num = 1

        def has_dialogue(text: str) -> bool:
            """Check if text contains actual dialogue content."""
            return 'Me:' in text or 'Them:' in text

        for line in expanded_lines:
            test_chunk = current_chunk + line + '\n'

            if len(test_chunk) > MAX_PASSAGE_CHARS:
                # Save current chunk only if it has actual dialogue content
                if current_chunk.strip() and len(current_chunk) > 500 and has_dialogue(current_chunk):
                    chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
                    chunks.append((current_chunk.strip(), chunk_tags))
                    chunk_num += 1

                current_chunk = f"## Meeting: {meeting['title']} (Transcript continued)\n\n**ID:** {meeting['meeting_id']}\n\n### Transcript\n{line}\n"
            else:
                current_chunk = test_chunk

        # Don't forget the last chunk - must have dialogue content
        if current_chunk.strip() and "### Transcript" in current_chunk and len(current_chunk) > 500 and has_dialogue(current_chunk):
            chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
            chunks.append((current_chunk.strip(), chunk_tags))
    else:
        # No clear transcript section, just chunk by size
        chunk_num = 1
        for i in range(0, len(content), MAX_PASSAGE_CHARS):
            chunk = content[i:i + MAX_PASSAGE_CHARS]
            chunk_tags = tags + [f"chunk:{chunk_num}"]
            chunks.append((chunk, chunk_tags))
            chunk_num += 1

    return chunks


def insert_to_archival(content: str, tags: list, dry_run: bool = False) -> bool:
    """Insert content into Letta archival memory using passages API."""
    if dry_run:
        print(f"  [DRY RUN] Would insert {len(content)} chars with tags: {tags[:5]}...")
        return True

    client = get_letta_client()
    if not client:
        print("  ❌ Letta client not available")
        return False

    try:
        # Use the passages API to insert into archival memory
        result = client.agents.passages.create(
            agent_id=AGENT_ID,
            text=content,
            tags=tags  # Store tags for filterable search
        )
        return True

    except Exception as e:
        error_msg = str(e)
        # Truncate long error messages
        if len(error_msg) > 300:
            error_msg = error_msg[:300] + "..."
        print(f"  ❌ Error inserting to archival: {error_msg}")
        return False


def load_state() -> dict:
    """Load backfill state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {'processed_ids': [], 'last_file': None}


def save_state(state: dict):
    """Save backfill state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Backfill Granola transcripts to Letta archival memory')
    parser.add_argument('--dry-run', action='store_true', help='Parse files but do not insert')
    parser.add_argument('--file', type=str, help='Process a single file')
    parser.add_argument('--resume-from', type=str, help='Resume from file matching this prefix')
    parser.add_argument('--reset', action='store_true', help='Reset state and start fresh')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    args = parser.parse_args()

    print("=" * 70)
    print("Granola to Letta Archival Memory Backfill")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Source: {SOURCE_DIR}")
    print(f"Dry run: {args.dry_run}")
    print()

    # Load or reset state
    if args.reset:
        state = {'processed_ids': [], 'last_file': None}
        save_state(state)
        print("State reset.")
    else:
        state = load_state()

    processed_ids = set(state.get('processed_ids', []))
    print(f"Previously processed: {len(processed_ids)} meetings")

    # Get files to process
    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(SOURCE_DIR.glob("granolaNote--*.txt"))

    if args.resume_from:
        files = [f for f in files if f.name >= args.resume_from]
        print(f"Resuming from files matching: {args.resume_from}")

    if args.limit:
        files = files[:args.limit]

    print(f"Files to process: {len(files)}")
    print()

    # Process files
    success_count = 0
    skip_count = 0
    error_count = 0

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {file_path.name[:60]}...")

        # Parse file
        meeting = parse_granola_export(file_path)
        if not meeting:
            error_count += 1
            continue

        # Skip if already processed
        if meeting['meeting_id'] in processed_ids:
            print(f"  ⏭️  Already processed")
            skip_count += 1
            continue

        # Generate tags
        tags = generate_tags(meeting)

        # Format content (embed tags at the top for searchability)
        content = format_content(meeting)
        tag_line = f"**Tags:** {', '.join(tags)}\n\n"
        full_content = tag_line + content

        # Chunk content if too large
        chunks = chunk_content(full_content, meeting, tags)
        chunk_count = len(chunks)

        # Insert all chunks to archival memory
        all_chunks_success = True
        for chunk_idx, (chunk_text, chunk_tags) in enumerate(chunks, 1):
            chunk_label = f"chunk {chunk_idx}/{chunk_count}" if chunk_count > 1 else "single"
            if not insert_to_archival(chunk_text, chunk_tags, dry_run=args.dry_run):
                all_chunks_success = False
                print(f"  ❌ Failed to insert {chunk_label}")
                break

        if all_chunks_success:
            success_count += 1
            if not args.dry_run:
                processed_ids.add(meeting['meeting_id'])
                state['processed_ids'] = list(processed_ids)
                state['last_file'] = file_path.name
                save_state(state)
            if chunk_count > 1:
                print(f"  ✅ Inserted ({len(full_content)} chars, {chunk_count} chunks, {len(tags)} tags)")
            else:
                print(f"  ✅ Inserted ({len(full_content)} chars, {len(tags)} tags)")
        else:
            error_count += 1

        # Progress every 50 files
        if i % 50 == 0:
            print(f"\n📊 Progress: {i}/{len(files)} | Success: {success_count} | Skip: {skip_count} | Error: {error_count}\n")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files: {len(files)}")
    print(f"Successful: {success_count}")
    print(f"Skipped (already processed): {skip_count}")
    print(f"Errors: {error_count}")

    if args.dry_run:
        print("\n⚠️  DRY RUN - No data was inserted")
    else:
        print(f"\n✅ Backfill complete! {success_count} meetings added to archival memory.")


if __name__ == "__main__":
    main()
