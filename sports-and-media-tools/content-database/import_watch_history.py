#!/usr/bin/env python3
"""
Watch History Importer

Imports watch history from Netflix and Prime Video HTML exports,
enriches with JustWatch metadata, and populates the content database.

Usage:
    python import_watch_history.py --netflix /path/to/netflix.html --prime /path/to/prime.html --user chad
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('CONTENT_DB_PATH', '/app/data/content_database.db')

# Import from sibling modules
try:
    from user_schema import extend_database_with_user_tables, get_or_create_user, add_watch_history_entry
    from justwatch_scraper import search_justwatch, save_content_to_db, init_database, SUBSCRIBED_SERVICES
except ImportError:
    # Running standalone - define minimal versions
    logger.warning("Could not import from sibling modules, using standalone mode")
    
    def extend_database_with_user_tables(db_path):
        pass
    
    def get_or_create_user(db_path, username, display_name=None):
        return 1
    
    def add_watch_history_entry(**kwargs):
        return 1
    
    def search_justwatch(query, content_type=None):
        return []
    
    def save_content_to_db(content, offers):
        pass
    
    def init_database():
        pass
    
    SUBSCRIBED_SERVICES = ['netflix', 'hulu', 'disney', 'max', 'prime', 'apple', 'espn', 'youtube']


def parse_netflix_date(date_str: str) -> Optional[datetime]:
    """
    Parse Netflix date format (M/DD/YY or MM/DD/YY).
    
    Args:
        date_str: Date string like "1/01/26" or "12/25/24"
    
    Returns:
        Parsed datetime or None
    """
    try:
        # Netflix uses M/DD/YY format
        parts = date_str.strip().split('/')
        if len(parts) == 3:
            month = int(parts[0])
            day = int(parts[1])
            year = int(parts[2])
            # Assume 20xx for years < 50, 19xx for years >= 50
            if year < 50:
                year += 2000
            else:
                year += 1900
            return datetime(year, month, day, tzinfo=timezone.utc)
    except Exception as e:
        logger.warning(f"Could not parse Netflix date '{date_str}': {e}")
    return None


def extract_netflix_title_id(url: str) -> Optional[str]:
    """
    Extract Netflix title ID from URL.
    
    Args:
        url: Netflix URL like "https://www.netflix.com/title/82132741"
    
    Returns:
        Title ID or None
    """
    if '/title/' in url:
        return url.split('/title/')[-1].split('?')[0].split('/')[0]
    return None


def parse_netflix_title(full_title: str) -> Tuple[str, Optional[str], Optional[int], Optional[int]]:
    """
    Parse Netflix title to extract show name and episode info.
    
    Args:
        full_title: Full title like "Minx: Season 1: \"Mary Had a Little Hysterectomy\""
    
    Returns:
        Tuple of (show_name, episode_title, season_number, episode_number)
    """
    show_name = full_title
    episode_title = None
    season_number = None
    episode_number = None
    
    # Try to parse "Show: Season X: Episode Title" format
    # Also handles "Show: Season X: \"Episode Title\""
    season_match = re.match(r'^(.+?):\s*Season\s*(\d+):\s*["\"]?(.+?)["\"]?$', full_title, re.IGNORECASE)
    if season_match:
        show_name = season_match.group(1).strip()
        season_number = int(season_match.group(2))
        episode_title = season_match.group(3).strip().strip('"').strip("'")
        return show_name, episode_title, season_number, episode_number
    
    # Try "Show: Season X" format (no episode title)
    season_only_match = re.match(r'^(.+?):\s*Season\s*(\d+)$', full_title, re.IGNORECASE)
    if season_only_match:
        show_name = season_only_match.group(1).strip()
        season_number = int(season_only_match.group(2))
        return show_name, episode_title, season_number, episode_number
    
    # Try "Show: Episode Title" format (no season)
    simple_ep_match = re.match(r'^(.+?):\s*["\"]?(.+?)["\"]?$', full_title)
    if simple_ep_match:
        show_name = simple_ep_match.group(1).strip()
        episode_title = simple_ep_match.group(2).strip().strip('"').strip("'")
        # Check if episode_title looks like a season indicator
        if re.match(r'^Season\s*\d+', episode_title, re.IGNORECASE):
            # This is actually a season, not an episode
            episode_title = None
    
    return show_name, episode_title, season_number, episode_number


def parse_netflix_html(html_path: str) -> List[Dict]:
    """
    Parse Netflix viewing activity HTML file.
    
    Args:
        html_path: Path to the Netflix HTML file
    
    Returns:
        List of watch history entries
    """
    logger.info(f"Parsing Netflix HTML from {html_path}")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    entries = []
    rows = soup.select('.retableRow')
    
    logger.info(f"Found {len(rows)} Netflix watch history rows")
    
    for row in rows:
        try:
            # Get title and link
            title_col = row.select_one('.col.title')
            date_col = row.select_one('.col.date')
            
            if not title_col or not date_col:
                continue
            
            title_link = title_col.find('a')
            full_title = title_link.text.strip() if title_link else title_col.text.strip()
            href = title_link.get('href', '') if title_link else ''
            date_str = date_col.text.strip()
            
            # Parse the title
            show_name, episode_title, season_number, episode_number = parse_netflix_title(full_title)
            
            # Parse the date
            watched_at = parse_netflix_date(date_str)
            
            # Extract Netflix ID
            netflix_id = extract_netflix_title_id(href)
            
            entries.append({
                'service': 'netflix',
                'title': show_name,
                'full_title': full_title,
                'episode_title': episode_title,
                'season_number': season_number,
                'episode_number': episode_number,
                'service_content_id': netflix_id,
                'url': href,
                'watched_at': watched_at,
                'raw_date': date_str,
            })
            
        except Exception as e:
            logger.warning(f"Error parsing Netflix row: {e}")
            continue
    
    logger.info(f"Parsed {len(entries)} Netflix entries")
    return entries


def parse_prime_episode_title(ep_text: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Parse Prime Video episode title.
    
    Args:
        ep_text: Episode text like "Episode 1: The Innovator"
    
    Returns:
        Tuple of (episode_title, episode_number)
    """
    episode_title = ep_text
    episode_number = None
    
    # Try "Episode X: Title" format
    match = re.match(r'^Episode\s*(\d+):\s*(.+)$', ep_text, re.IGNORECASE)
    if match:
        episode_number = int(match.group(1))
        episode_title = match.group(2).strip()
    else:
        # Try just "Episode X" format
        match = re.match(r'^Episode\s*(\d+)$', ep_text, re.IGNORECASE)
        if match:
            episode_number = int(match.group(1))
            episode_title = None
    
    return episode_title, episode_number


def parse_prime_html(html_path: str) -> List[Dict]:
    """
    Parse Prime Video watch history HTML file.
    
    Args:
        html_path: Path to the Prime Video HTML file
    
    Returns:
        List of watch history entries
    """
    logger.info(f"Parsing Prime Video HTML from {html_path}")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    entries = []
    
    # Get all show/movie level items
    items = soup.select('[data-testid="activity-history-item"]')
    logger.info(f"Found {len(items)} Prime Video items")
    
    # Get all episodes
    episodes = soup.select('[data-testid="activity-history-item-episode"]')
    logger.info(f"Found {len(episodes)} Prime Video episodes")
    
    # Process show/movie level items
    for item in items:
        try:
            # Get title from img alt or link text
            img = item.select_one('img[alt]')
            title = img.get('alt', 'Unknown') if img else 'Unknown'
            
            # Get Prime ID from URL
            link = item.select_one('a[href*="gp/video/detail"]')
            href = link.get('href', '') if link else ''
            match = re.search(r'/detail/([A-Z0-9]+)/', href)
            prime_id = match.group(1) if match else None
            
            # Check if it's a movie or series
            delete_btn = item.select_one('button[aria-label]')
            is_movie = 'movie' in (delete_btn.get('aria-label', '').lower() if delete_btn else '')
            
            entries.append({
                'service': 'prime',
                'title': title,
                'full_title': title,
                'episode_title': None,
                'season_number': None,
                'episode_number': None,
                'service_content_id': prime_id,
                'url': href,
                'watched_at': None,  # Prime doesn't show watch dates in this export
                'is_movie': is_movie,
                'is_show_entry': True,  # This is a show-level entry
            })
            
        except Exception as e:
            logger.warning(f"Error parsing Prime item: {e}")
            continue
    
    # Process episodes - they're siblings, need to find parent show
    for ep in episodes:
        try:
            # Get episode title
            p = ep.select_one('p')
            ep_text = p.get_text(strip=True) if p else 'Unknown Episode'
            
            # Parse episode info
            episode_title, episode_number = parse_prime_episode_title(ep_text)
            
            # Get episode ID from form
            form = ep.select_one('form')
            title_id_input = form.select_one('input[name="titleIds"]') if form else None
            ep_id = title_id_input.get('value', None) if title_id_input else None
            
            # Find parent show by traversing up the DOM
            parent_show = 'Unknown'
            parent = ep.parent
            for _ in range(15):  # Go up to 15 levels
                if parent:
                    parent_img = parent.select_one('img[alt]')
                    if parent_img and parent_img.get('alt'):
                        parent_show = parent_img.get('alt')
                        break
                    parent = parent.parent
                else:
                    break
            
            # Parse season from parent show title (e.g., "Fallout - Season 2")
            season_number = None
            show_name = parent_show
            season_match = re.match(r'^(.+?)\s*-\s*Season\s*(\d+)$', parent_show, re.IGNORECASE)
            if season_match:
                show_name = season_match.group(1).strip()
                season_number = int(season_match.group(2))
            
            entries.append({
                'service': 'prime',
                'title': show_name,
                'full_title': f"{parent_show}: {ep_text}",
                'episode_title': episode_title,
                'season_number': season_number,
                'episode_number': episode_number,
                'service_content_id': ep_id,
                'url': None,
                'watched_at': None,
                'is_movie': False,
                'is_show_entry': False,  # This is an episode-level entry
            })
            
        except Exception as e:
            logger.warning(f"Error parsing Prime episode: {e}")
            continue
    
    logger.info(f"Parsed {len(entries)} Prime Video entries")
    return entries


def enrich_with_justwatch(entries: List[Dict], batch_size: int = 10, delay: float = 1.0) -> List[Dict]:
    """
    Enrich watch history entries with JustWatch metadata.
    
    Args:
        entries: List of watch history entries
        batch_size: Number of entries to process before pausing
        delay: Delay between batches (seconds)
    
    Returns:
        Enriched entries
    """
    logger.info(f"Enriching {len(entries)} entries with JustWatch metadata...")
    
    # Get unique titles to avoid duplicate API calls
    unique_titles = {}
    for entry in entries:
        title = entry.get('title', '')
        if title and title not in unique_titles:
            unique_titles[title] = None
    
    logger.info(f"Found {len(unique_titles)} unique titles to look up")
    
    # Look up each unique title
    processed = 0
    for title in unique_titles.keys():
        try:
            results = search_justwatch(title)
            if results:
                unique_titles[title] = results[0]
                
                # Save to content database with offers
                offers = results[0].get('offers', [])
                save_content_to_db(results[0], offers)
                
                logger.debug(f"Found JustWatch match for '{title}': {results[0].get('title')}")
            else:
                logger.debug(f"No JustWatch match for '{title}'")
            
            processed += 1
            if processed % batch_size == 0:
                logger.info(f"Processed {processed}/{len(unique_titles)} titles...")
                time.sleep(delay)
                
        except Exception as e:
            logger.warning(f"Error looking up '{title}' on JustWatch: {e}")
            continue
    
    logger.info(f"Completed JustWatch enrichment for {processed} titles")
    
    # Attach JustWatch data to entries
    for entry in entries:
        title = entry.get('title', '')
        jw_data = unique_titles.get(title)
        if jw_data:
            entry['justwatch_id'] = jw_data.get('id')
            entry['justwatch_title'] = jw_data.get('title')
            entry['year'] = jw_data.get('original_release_year')
            entry['content_type'] = jw_data.get('object_type')
            entry['description'] = jw_data.get('short_description')
            entry['poster'] = jw_data.get('poster')
    
    return entries


def get_content_id_from_db(db_path: str, justwatch_id: str) -> Optional[int]:
    """
    Get content ID from the database by JustWatch ID.
    
    Args:
        db_path: Path to the database
        justwatch_id: JustWatch content ID
    
    Returns:
        Content ID or None
    """
    if not justwatch_id:
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM content WHERE justwatch_id = ?', (str(justwatch_id),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def import_to_database(
    db_path: str,
    entries: List[Dict],
    user_id: int,
    source: str
) -> Tuple[int, int]:
    """
    Import watch history entries to the database.
    
    Args:
        db_path: Path to the database
        entries: List of watch history entries
        user_id: User ID
        source: Source identifier (e.g., 'netflix_export')
    
    Returns:
        Tuple of (successful_count, failed_count)
    """
    logger.info(f"Importing {len(entries)} entries to database for user {user_id}...")
    
    success = 0
    failed = 0
    
    for entry in entries:
        try:
            # Get content ID if we have JustWatch data
            content_id = get_content_id_from_db(db_path, entry.get('justwatch_id'))
            
            # Add to watch history
            add_watch_history_entry(
                db_path=db_path,
                user_id=user_id,
                title=entry.get('title'),
                service=entry.get('service'),
                watched_at=entry.get('watched_at'),
                episode_title=entry.get('episode_title'),
                season_number=entry.get('season_number'),
                episode_number=entry.get('episode_number'),
                service_content_id=entry.get('service_content_id'),
                content_id=content_id,
                source=source,
                raw_data=json.dumps(entry, default=str)
            )
            success += 1
            
        except Exception as e:
            logger.warning(f"Error importing entry '{entry.get('title')}': {e}")
            failed += 1
            continue
    
    logger.info(f"Imported {success} entries, {failed} failed")
    return success, failed


def main():
    parser = argparse.ArgumentParser(description='Import watch history from streaming services')
    parser.add_argument('--netflix', type=str, help='Path to Netflix HTML export')
    parser.add_argument('--prime', type=str, help='Path to Prime Video HTML export')
    parser.add_argument('--user', type=str, required=True, help='Username for the watch history')
    parser.add_argument('--db', type=str, default=DB_PATH, help='Path to the database')
    parser.add_argument('--skip-justwatch', action='store_true', help='Skip JustWatch enrichment')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for JustWatch lookups')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between batches (seconds)')
    
    args = parser.parse_args()
    
    if not args.netflix and not args.prime:
        parser.error("At least one of --netflix or --prime is required")
    
    # Initialize database
    logger.info(f"Using database at {args.db}")
    init_database()
    extend_database_with_user_tables(args.db)
    
    # Get or create user
    user_id = get_or_create_user(args.db, args.user, args.user.capitalize())
    logger.info(f"Using user ID {user_id} for '{args.user}'")
    
    all_entries = []
    
    # Parse Netflix
    if args.netflix:
        if os.path.exists(args.netflix):
            netflix_entries = parse_netflix_html(args.netflix)
            all_entries.extend(netflix_entries)
        else:
            logger.error(f"Netflix file not found: {args.netflix}")
    
    # Parse Prime Video
    if args.prime:
        if os.path.exists(args.prime):
            prime_entries = parse_prime_html(args.prime)
            all_entries.extend(prime_entries)
        else:
            logger.error(f"Prime Video file not found: {args.prime}")
    
    if not all_entries:
        logger.error("No entries parsed")
        return
    
    logger.info(f"Total entries to process: {len(all_entries)}")
    
    # Enrich with JustWatch
    if not args.skip_justwatch:
        all_entries = enrich_with_justwatch(all_entries, args.batch_size, args.delay)
    
    # Import to database
    netflix_entries = [e for e in all_entries if e.get('service') == 'netflix']
    prime_entries = [e for e in all_entries if e.get('service') == 'prime']
    
    total_success = 0
    total_failed = 0
    
    if netflix_entries:
        success, failed = import_to_database(args.db, netflix_entries, user_id, 'netflix_export')
        total_success += success
        total_failed += failed
    
    if prime_entries:
        success, failed = import_to_database(args.db, prime_entries, user_id, 'prime_export')
        total_success += success
        total_failed += failed
    
    logger.info(f"Import complete: {total_success} successful, {total_failed} failed")
    
    # Print summary
    print("\n" + "="*60)
    print("IMPORT SUMMARY")
    print("="*60)
    print(f"User: {args.user} (ID: {user_id})")
    print(f"Netflix entries: {len(netflix_entries)}")
    print(f"Prime Video entries: {len(prime_entries)}")
    print(f"Total imported: {total_success}")
    print(f"Failed: {total_failed}")
    print("="*60)


if __name__ == '__main__':
    main()

