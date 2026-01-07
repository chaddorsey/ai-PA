#!/usr/bin/env python3
"""
Tracked Series Database Initializer

A one-time script to bootstrap the tracked_series table from existing watch history.
This handles the initial population of:
- Finished series (fully watched, no recent activity)
- Dropped series (partially watched, abandoned)
- Watching series (currently active in continue_watching)

Usage:
    # Step 1: Generate review file
    python initialize_tracked_series.py --extract --user chad
    
    # Step 2: Review and edit the generated YAML file
    # Edit: series_review_chad.yaml
    
    # Step 3: Import reviewed categorizations
    python initialize_tracked_series.py --import --user chad
"""

import argparse
import json
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('CONTENT_DB_PATH', '/app/data/content_database.db')

# Thresholds for categorization heuristics
FINISHED_EPISODE_THRESHOLD = 10  # Series with >= this many episodes watched
FINISHED_DAYS_INACTIVE = 60  # Days since last watch to consider "finished"
DROPPED_EPISODE_THRESHOLD = 3  # Series with <= this many episodes
DROPPED_DAYS_INACTIVE = 90  # Days since last watch to consider "dropped"
RECENT_ACTIVITY_DAYS = 30  # Activity within this period = "watching"


def get_user_id(db_path: str, username: str) -> Optional[int]:
    """Get user ID from username."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_series_statistics(db_path: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Extract all unique series from watch history with aggregated statistics.
    
    Returns list of dicts with:
    - title: Series name
    - service: Primary streaming service
    - episode_count: Number of episodes watched
    - first_watched: Earliest watch date
    - last_watched: Most recent watch date
    - seasons_watched: Set of season numbers
    - has_episode_data: Whether we have episode-level data
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get aggregated watch history data
    cursor.execute('''
        SELECT 
            title,
            service,
            COUNT(*) as episode_count,
            MIN(watched_at) as first_watched,
            MAX(watched_at) as last_watched,
            COUNT(DISTINCT season_number) as season_count,
            GROUP_CONCAT(DISTINCT season_number) as seasons,
            SUM(CASE WHEN episode_title IS NOT NULL THEN 1 ELSE 0 END) as episodes_with_data
        FROM user_watch_history
        WHERE user_id = ?
            AND title IS NOT NULL
            AND title != ''
            AND title != ':'
        GROUP BY title, service
        ORDER BY episode_count DESC
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        seasons = []
        if row['seasons']:
            try:
                seasons = [int(s) for s in row['seasons'].split(',') if s and s != 'None']
            except ValueError:
                pass
        
        results.append({
            'title': row['title'],
            'service': row['service'],
            'episode_count': row['episode_count'],
            'first_watched': row['first_watched'],
            'last_watched': row['last_watched'],
            'season_count': row['season_count'] or 0,
            'seasons_watched': sorted(seasons) if seasons else [],
            'has_episode_data': row['episodes_with_data'] > 0,
        })
    
    return results


def get_continue_watching(db_path: str, user_id: int) -> Dict[str, Dict]:
    """
    Get currently in-progress series from continue_watching table.
    Returns dict keyed by lowercase title.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            title,
            service,
            season_number,
            episode_number,
            progress_percent,
            last_watched
        FROM continue_watching
        WHERE user_id = ?
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {row['title'].lower(): dict(row) for row in rows}


def get_existing_tracked(db_path: str, user_id: int) -> Dict[str, Dict]:
    """Get already tracked series to avoid duplicates."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT title, tracking_status, watch_status
        FROM tracked_series
        WHERE user_id = ?
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {row['title'].lower(): dict(row) for row in rows}


def categorize_series(
    series_stats: List[Dict],
    continue_watching: Dict[str, Dict],
    existing_tracked: Dict[str, Dict]
) -> Dict[str, List[Dict]]:
    """
    Apply heuristics to categorize series into tracking statuses.
    
    Categories:
    - watching: Active series (in continue_watching or recent activity)
    - finished: Completed series (many episodes, no recent activity)
    - dropped: Abandoned series (few episodes, old activity)
    - skip: Not worth tracking (single watches, non-series content)
    - review: Ambiguous cases needing human decision
    """
    now = datetime.now(timezone.utc)
    
    categories = {
        'watching': [],
        'finished': [],
        'dropped': [],
        'skip': [],
        'review': [],
    }
    
    for series in series_stats:
        title = series['title']
        title_lower = title.lower()
        
        # Skip if already tracked
        if title_lower in existing_tracked:
            continue
        
        # Parse last watched date
        last_watched = None
        days_since_watch = None
        if series['last_watched']:
            try:
                if 'T' in series['last_watched']:
                    last_watched = datetime.fromisoformat(
                        series['last_watched'].replace('Z', '+00:00')
                    )
                else:
                    last_watched = datetime.strptime(
                        series['last_watched'], '%Y-%m-%d'
                    ).replace(tzinfo=timezone.utc)
                days_since_watch = (now - last_watched).days
            except (ValueError, TypeError):
                pass
        
        episode_count = series['episode_count']
        
        # Build entry for categorization
        entry = {
            'title': title,
            'service': series['service'],
            'episode_count': episode_count,
            'last_watched': series['last_watched'],
            'days_since_watch': days_since_watch,
            'seasons_watched': series['seasons_watched'],
            'reason': '',
        }
        
        # Rule 1: In continue_watching = definitely watching
        if title_lower in continue_watching:
            cw = continue_watching[title_lower]
            entry['current_season'] = cw.get('season_number')
            entry['current_episode'] = cw.get('episode_number')
            entry['reason'] = 'In continue_watching'
            categories['watching'].append(entry)
            continue
        
        # Rule 2: Recent activity (last 30 days) with multiple episodes = watching
        if days_since_watch is not None and days_since_watch <= RECENT_ACTIVITY_DAYS:
            if episode_count >= 2:
                entry['reason'] = f'Recent activity ({days_since_watch} days ago)'
                categories['watching'].append(entry)
                continue
        
        # Rule 3: Many episodes watched + old activity = likely finished
        if episode_count >= FINISHED_EPISODE_THRESHOLD:
            if days_since_watch is None or days_since_watch > FINISHED_DAYS_INACTIVE:
                entry['reason'] = f'{episode_count} episodes, inactive {days_since_watch or "unknown"} days'
                categories['finished'].append(entry)
                continue
        
        # Rule 4: Few episodes + very old = likely dropped or one-time watch
        if episode_count <= DROPPED_EPISODE_THRESHOLD:
            if days_since_watch is None or days_since_watch > DROPPED_DAYS_INACTIVE:
                if episode_count == 1:
                    entry['reason'] = 'Single episode/movie - not a tracked series'
                    categories['skip'].append(entry)
                else:
                    entry['reason'] = f'Only {episode_count} episodes, inactive {days_since_watch or "unknown"} days'
                    categories['dropped'].append(entry)
                continue
        
        # Rule 5: Everything else needs review
        entry['reason'] = f'{episode_count} episodes, {days_since_watch or "unknown"} days inactive'
        categories['review'].append(entry)
    
    return categories


def generate_review_file(
    categories: Dict[str, List[Dict]],
    output_path: str,
    username: str
):
    """
    Generate a YAML file for human review before import.
    """
    review_data = {
        'metadata': {
            'username': username,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'instructions': '''
Review each category below and adjust as needed:
- Move series between categories by cut/paste
- Change 'status' field to: watching, finished, dropped, on_hold, or skip
- Add 'notes' field for any comments
- Remove entries you don't want to track at all

After review, run: python initialize_tracked_series.py --import --user {username}
'''.format(username=username),
        },
        'summary': {
            'watching': len(categories['watching']),
            'finished': len(categories['finished']),
            'dropped': len(categories['dropped']),
            'skip': len(categories['skip']),
            'review': len(categories['review']),
        },
        'categories': {},
    }
    
    # Format each category
    for status, series_list in categories.items():
        if not series_list:
            continue
        
        formatted_entries = []
        for series in series_list:
            entry = {
                'title': series['title'],
                'status': status if status != 'skip' else 'skip',
                'service': series['service'],
                'episode_count': series['episode_count'],
                'last_watched': series['last_watched'],
                'reason': series['reason'],
            }
            
            # Add optional fields
            if series.get('seasons_watched'):
                entry['seasons_watched'] = series['seasons_watched']
            if series.get('current_season'):
                entry['current_progress'] = {
                    'season': series['current_season'],
                    'episode': series.get('current_episode'),
                }
            
            formatted_entries.append(entry)
        
        review_data['categories'][status] = formatted_entries
    
    with open(output_path, 'w') as f:
        yaml.dump(review_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    logger.info(f"Generated review file: {output_path}")
    return review_data['summary']


def import_from_review_file(
    review_path: str,
    db_path: str,
    user_id: int,
    dry_run: bool = False
) -> Tuple[int, int, int]:
    """
    Import tracked series from the reviewed YAML file.
    
    Returns: (imported_count, skipped_count, error_count)
    """
    with open(review_path, 'r') as f:
        review_data = yaml.safe_load(f)
    
    imported = 0
    skipped = 0
    errors = 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for category, series_list in review_data.get('categories', {}).items():
            if not series_list:
                continue
            
            for entry in series_list:
                status = entry.get('status', category)
                
                # Skip entries marked as 'skip'
                if status == 'skip':
                    skipped += 1
                    continue
                
                # Map status to valid tracking_status values
                tracking_status = status
                if tracking_status not in ('watching', 'finished', 'dropped', 'on_hold'):
                    logger.warning(f"Invalid status '{status}' for {entry['title']}, defaulting to 'finished'")
                    tracking_status = 'finished'
                
                # Determine watch_status
                if tracking_status == 'finished':
                    watch_status = 'fully_watched'
                elif tracking_status == 'watching':
                    watch_status = 'in_progress'
                else:
                    watch_status = 'in_progress'
                
                title = entry['title']
                service = entry.get('service')
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would import: {title} ({tracking_status})")
                    imported += 1
                    continue
                
                try:
                    # Check for existing entry
                    cursor.execute(
                        'SELECT id FROM tracked_series WHERE user_id = ? AND LOWER(title) = LOWER(?)',
                        (user_id, title)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        logger.debug(f"Already exists: {title}")
                        skipped += 1
                        continue
                    
                    # Insert new tracked series
                    now = datetime.now(timezone.utc).isoformat()
                    cursor.execute('''
                        INSERT INTO tracked_series 
                        (user_id, title, tracking_status, watch_status, preferred_service,
                         watched_episode_count, notes, added_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        user_id,
                        title,
                        tracking_status,
                        watch_status,
                        service,
                        entry.get('episode_count', 0),
                        entry.get('notes', f"Auto-imported: {entry.get('reason', '')}"),
                        now,
                        now,
                    ))
                    imported += 1
                    logger.info(f"Imported: {title} ({tracking_status})")
                    
                except Exception as e:
                    logger.error(f"Error importing {title}: {e}")
                    errors += 1
        
        if not dry_run:
            conn.commit()
            
    finally:
        conn.close()
    
    return imported, skipped, errors


def print_summary(categories: Dict[str, List[Dict]]):
    """Print a summary of categorized series."""
    print("\n" + "=" * 70)
    print("SERIES CATEGORIZATION SUMMARY")
    print("=" * 70)
    
    for status in ['watching', 'finished', 'dropped', 'review', 'skip']:
        series_list = categories.get(status, [])
        count = len(series_list)
        print(f"\n{status.upper()} ({count} series):")
        print("-" * 40)
        
        # Show first 10 with details
        for series in series_list[:10]:
            eps = series['episode_count']
            days = series.get('days_since_watch', '?')
            print(f"  • {series['title']} ({series['service']})")
            print(f"    {eps} episodes, {days} days ago - {series['reason']}")
        
        if count > 10:
            print(f"  ... and {count - 10} more")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Initialize tracked_series from watch history'
    )
    parser.add_argument('--user', type=str, default='chad',
                        help='Username to process')
    parser.add_argument('--db', type=str, default=DB_PATH,
                        help='Path to the database')
    parser.add_argument('--extract', action='store_true',
                        help='Extract and categorize series, generate review file')
    parser.add_argument('--import', dest='do_import', action='store_true',
                        help='Import from review file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be imported without making changes')
    parser.add_argument('--output', type=str,
                        help='Output file path for review YAML')
    
    args = parser.parse_args()
    
    # Determine output file path
    output_path = args.output or f'series_review_{args.user}.yaml'
    
    # Get user ID
    user_id = get_user_id(args.db, args.user)
    if not user_id:
        logger.error(f"User not found: {args.user}")
        return 1
    
    logger.info(f"Processing user: {args.user} (ID: {user_id})")
    
    if args.extract:
        # Step 1: Extract and categorize
        logger.info("Extracting series statistics from watch history...")
        series_stats = get_series_statistics(args.db, user_id)
        logger.info(f"Found {len(series_stats)} unique series in watch history")
        
        logger.info("Getting continue_watching data...")
        continue_watching = get_continue_watching(args.db, user_id)
        logger.info(f"Found {len(continue_watching)} series in continue_watching")
        
        logger.info("Checking for existing tracked series...")
        existing = get_existing_tracked(args.db, user_id)
        logger.info(f"Found {len(existing)} already tracked series")
        
        logger.info("Categorizing series...")
        categories = categorize_series(series_stats, continue_watching, existing)
        
        # Print summary
        print_summary(categories)
        
        # Generate review file
        summary = generate_review_file(categories, output_path, args.user)
        
        print(f"\n✅ Review file generated: {output_path}")
        print(f"\nSummary:")
        for status, count in summary.items():
            print(f"  {status}: {count}")
        print(f"\nNext steps:")
        print(f"  1. Review and edit: {output_path}")
        print(f"  2. Run: python {__file__} --import --user {args.user}")
        
    elif args.do_import:
        # Step 2: Import from review file
        if not os.path.exists(output_path):
            logger.error(f"Review file not found: {output_path}")
            logger.error("Run with --extract first to generate it")
            return 1
        
        logger.info(f"Importing from: {output_path}")
        imported, skipped, errors = import_from_review_file(
            output_path, args.db, user_id, dry_run=args.dry_run
        )
        
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Import complete:")
        print(f"  ✅ Imported: {imported}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  ❌ Errors: {errors}")
        
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

