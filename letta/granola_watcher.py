#!/usr/bin/env python3
"""
Granola Cache Watcher Service

This script monitors the Granola cache for new meetings with transcripts
and imports them to Letta archival memory. It can be run periodically
via cron or launchd.

Usage:
    # Run once (for cron)
    python granola_watcher.py

    # Run continuously with polling interval
    python granola_watcher.py --daemon --interval 300

    # Dry run
    python granola_watcher.py --dry-run

Setup for launchd (macOS):
    1. Copy granola-watcher.plist to ~/Library/LaunchAgents/
    2. launchctl load ~/Library/LaunchAgents/com.ai-pa.granola-watcher.plist
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from granola_cache_to_archival import (
    load_granola_cache,
    format_transcript,
    generate_tags,
    format_content,
    chunk_content,
    insert_to_archival,
    AGENT_ID,
    CACHE_PATH
)

# Configuration
STATE_FILE = Path("/Volumes/main-drive/ai-PA/letta/.granola_watcher_state.json")
LOG_FILE = Path("/Volumes/main-drive/ai-PA/letta/logs/granola_watcher.log")

# Ensure log directory exists
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_state() -> dict:
    """Load watcher state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {
        'imported_ids': [],
        'last_check': None,
        'last_cache_mtime': None
    }


def save_state(state: dict):
    """Save watcher state to file."""
    state['last_check'] = datetime.utcnow().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_cache_mtime() -> Optional[float]:
    """Get modification time of cache file."""
    if CACHE_PATH.exists():
        return CACHE_PATH.stat().st_mtime
    return None


def check_for_new_meetings(imported_ids: Set[str], dry_run: bool = False) -> tuple[int, int]:
    """
    Check for new meetings with transcripts and import them.

    Returns:
        Tuple of (success_count, error_count)
    """
    cache = load_granola_cache()
    if not cache:
        logger.warning("Failed to load cache")
        return 0, 0

    transcripts = cache['transcripts']
    documents = cache['documents']
    meetings_meta = cache['meetings_metadata']
    document_panels = cache['document_panels']

    # Find new meetings with transcripts
    new_meetings = []
    for meeting_id, transcript_data in transcripts.items():
        if meeting_id in imported_ids:
            continue

        # Skip empty transcripts
        if not transcript_data or not isinstance(transcript_data, list) or len(transcript_data) == 0:
            continue

        meta = meetings_meta.get(meeting_id, {})
        new_meetings.append({
            'id': meeting_id,
            'meta': meta,
            'transcript': transcript_data
        })

    if not new_meetings:
        logger.info("No new meetings to import")
        return 0, 0

    # Sort by creation date
    new_meetings.sort(key=lambda x: x['meta'].get('created_at', ''))

    logger.info(f"Found {len(new_meetings)} new meetings to import")

    success_count = 0
    error_count = 0

    for meeting in new_meetings:
        meeting_id = meeting['id']
        meta = meeting['meta']
        transcript_data = meeting['transcript']

        title = meta.get('title', 'Untitled')[:50]
        created = meta.get('created_at', '')[:19]
        logger.info(f"Importing: {title} ({created})")

        # Format transcript
        transcript_text = format_transcript(transcript_data)
        if not transcript_text:
            logger.warning(f"No transcript text for {meeting_id}")
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

        # Insert all chunks
        all_success = True
        for chunk_idx, (chunk_text, chunk_tags) in enumerate(chunks, 1):
            if not insert_to_archival(chunk_text, chunk_tags, dry_run=dry_run):
                all_success = False
                logger.error(f"Failed to insert chunk {chunk_idx}/{len(chunks)}")
                break

        if all_success:
            success_count += 1
            if not dry_run:
                imported_ids.add(meeting_id)
            logger.info(f"Imported {title} ({len(full_content)} chars, {len(chunks)} chunks)")
        else:
            error_count += 1

    return success_count, error_count


def run_once(dry_run: bool = False) -> bool:
    """Run a single check for new meetings."""
    logger.info("=" * 50)
    logger.info("Granola Watcher - Single Run")
    logger.info("=" * 50)

    state = load_state()
    imported_ids = set(state.get('imported_ids', []))
    last_mtime = state.get('last_cache_mtime')

    logger.info(f"Previously imported: {len(imported_ids)} meetings")

    # Check if cache has been modified
    current_mtime = get_cache_mtime()
    if current_mtime is None:
        logger.warning("Cache file not found")
        return False

    if last_mtime and current_mtime <= last_mtime:
        logger.info("Cache unchanged since last check")
        return True

    # Check for new meetings
    success, errors = check_for_new_meetings(imported_ids, dry_run=dry_run)

    # Save state
    if not dry_run:
        state['imported_ids'] = list(imported_ids)
        state['last_cache_mtime'] = current_mtime
        save_state(state)

    logger.info(f"Summary: {success} imported, {errors} errors")
    return errors == 0


def run_daemon(interval: int, dry_run: bool = False):
    """Run continuously, checking for new meetings periodically."""
    logger.info("=" * 50)
    logger.info(f"Granola Watcher - Daemon Mode (interval: {interval}s)")
    logger.info("=" * 50)

    while True:
        try:
            run_once(dry_run=dry_run)
        except Exception as e:
            logger.error(f"Error during check: {e}")

        logger.info(f"Sleeping for {interval} seconds...")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Granola Cache Watcher Service')
    parser.add_argument('--dry-run', action='store_true', help='Do not insert to archival')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds (default: 300)')
    parser.add_argument('--reset', action='store_true', help='Reset watcher state')
    args = parser.parse_args()

    if args.reset:
        state = {
            'imported_ids': [],
            'last_check': None,
            'last_cache_mtime': None
        }
        save_state(state)
        logger.info("Watcher state reset")
        return

    if args.daemon:
        run_daemon(args.interval, dry_run=args.dry_run)
    else:
        success = run_once(dry_run=args.dry_run)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
