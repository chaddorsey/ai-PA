#!/usr/bin/env python3
"""
User Watch History Schema Extension

Extends the content database with user-specific tables for tracking
watch history, ratings, and preferences.
"""

import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def extend_database_with_user_tables(db_path: str):
    """
    Add user-related tables to the content database.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            email TEXT,
            netflix_profile_id TEXT,
            prime_profile_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User watch history - links users to content with watch timestamps
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_id INTEGER,  -- FK to content table (may be NULL if not matched)
            title TEXT NOT NULL,  -- Original title from source
            episode_title TEXT,   -- For TV episodes
            season_number INTEGER,
            episode_number INTEGER,
            service TEXT NOT NULL,  -- netflix, prime, hulu, etc.
            service_content_id TEXT,  -- The service-specific ID
            watched_at TIMESTAMP,  -- When the user watched it
            source TEXT,  -- 'netflix_export', 'prime_export', 'manual', etc.
            raw_data TEXT,  -- JSON of original source data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (content_id) REFERENCES content(id)
        )
    ''')
    
    # User ratings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_id INTEGER,
            title TEXT NOT NULL,
            service TEXT,
            rating_type TEXT,  -- 'thumbs_up', 'thumbs_down', 'double_thumbs_up', 'stars', 'percent'
            rating_value TEXT,  -- The rating value (flexible for different systems)
            rated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (content_id) REFERENCES content(id)
        )
    ''')
    
    # User watchlist (things they want to watch)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_id INTEGER,
            title TEXT NOT NULL,
            service TEXT,
            priority INTEGER DEFAULT 0,  -- Higher = more interested
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',  -- 'pending', 'watching', 'completed', 'dropped'
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (content_id) REFERENCES content(id)
        )
    ''')
    
    # Service recommendations - what each streaming service is suggesting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_id INTEGER,
            title TEXT NOT NULL,
            service TEXT NOT NULL,
            service_content_id TEXT,
            recommendation_type TEXT,  -- 'because_you_watched', 'trending', 'new_release', 'top_pick', 'continue_watching'
            category TEXT,  -- The shelf/row name from the service
            position INTEGER,  -- Position in the row
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (content_id) REFERENCES content(id)
        )
    ''')
    
    # Continue watching - current state of in-progress content
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS continue_watching (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_id INTEGER,
            title TEXT NOT NULL,
            service TEXT NOT NULL,
            service_content_id TEXT,
            episode_title TEXT,
            season_number INTEGER,
            episode_number INTEGER,
            progress_percent INTEGER,  -- 0-100 how far through
            last_watched TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (content_id) REFERENCES content(id),
            UNIQUE(user_id, service, service_content_id)
        )
    ''')
    
    # Tracked series - intentional series tracking with status management
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracked_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            justwatch_id TEXT,
            imdb_id TEXT,
            
            -- Status fields
            tracking_status TEXT DEFAULT 'watching',  -- watching, finished, dropped, on_hold
            watch_status TEXT DEFAULT 'not_started',  -- not_started, in_progress, fully_watched
            
            -- Service information
            preferred_service TEXT,
            available_services TEXT,  -- JSON: [{service, seasons, last_checked}]
            
            -- Progress tracking
            total_seasons_known INTEGER,
            total_episodes_known INTEGER,
            watched_episode_count INTEGER DEFAULT 0,
            
            -- Manual progress overrides
            manual_progress TEXT,  -- JSON: {watched_through, additional_watched, note}
            
            -- Timestamps
            last_synced_at TEXT,
            last_availability_check TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            -- Metadata
            notes TEXT,
            auto_tracked_from_watchlist INTEGER DEFAULT 0,  -- 1 if auto-added from watchlist
            series_url TEXT,  -- URL to series page on preferred service
            
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, justwatch_id)
        )
    ''')
    
    # Indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watch_history_user ON user_watch_history(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watch_history_service ON user_watch_history(service)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watch_history_content ON user_watch_history(content_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watch_history_title ON user_watch_history(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watch_history_watched_at ON user_watch_history(watched_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ratings_user ON user_ratings(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlist(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_recommendations_user ON service_recommendations(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_recommendations_service ON service_recommendations(service)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_continue_watching_user ON continue_watching(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracked_series_user_status ON tracked_series(user_id, tracking_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracked_series_user_service ON tracked_series(user_id, preferred_service)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracked_series_title ON tracked_series(title)')
    
    conn.commit()
    conn.close()
    logger.info(f"Extended database with user tables at {db_path}")


def get_or_create_user(db_path: str, username: str, display_name: str = None) -> int:
    """
    Get or create a user record.
    
    Args:
        db_path: Path to the SQLite database
        username: Unique username
        display_name: Human-readable name
    
    Returns:
        User ID
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Try to get existing user
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        
        if row:
            return row[0]
        
        # Create new user
        cursor.execute('''
            INSERT INTO users (username, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (username, display_name or username, 
              datetime.now(timezone.utc).isoformat(),
              datetime.now(timezone.utc).isoformat()))
        
        conn.commit()
        return cursor.lastrowid
        
    finally:
        conn.close()


def add_watch_history_entry(
    db_path: str,
    user_id: int,
    title: str,
    service: str,
    watched_at: datetime = None,
    episode_title: str = None,
    season_number: int = None,
    episode_number: int = None,
    service_content_id: str = None,
    content_id: int = None,
    source: str = None,
    raw_data: str = None
) -> int:
    """
    Add a watch history entry.
    
    Args:
        db_path: Path to the SQLite database
        user_id: User ID
        title: Content title (show name or movie name)
        service: Streaming service name
        watched_at: When the user watched it
        episode_title: Episode title (for TV)
        season_number: Season number (for TV)
        episode_number: Episode number (for TV)
        service_content_id: The service-specific content ID
        content_id: FK to content table
        source: Source of this data
        raw_data: JSON of original source data
    
    Returns:
        Watch history entry ID
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO user_watch_history 
            (user_id, content_id, title, episode_title, season_number, episode_number,
             service, service_content_id, watched_at, source, raw_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            content_id,
            title,
            episode_title,
            season_number,
            episode_number,
            service,
            service_content_id,
            watched_at.isoformat() if watched_at else None,
            source,
            raw_data,
            datetime.now(timezone.utc).isoformat()
        ))
        
        conn.commit()
        return cursor.lastrowid
        
    finally:
        conn.close()


# =============================================================================
# TRACKED SERIES CRUD FUNCTIONS
# =============================================================================

VALID_TRACKING_STATUSES = ['watching', 'finished', 'dropped', 'on_hold']
VALID_WATCH_STATUSES = ['not_started', 'in_progress', 'fully_watched']


def create_tracked_series(
    db_path: str,
    user_id: int,
    title: str,
    justwatch_id: str = None,
    imdb_id: str = None,
    preferred_service: str = None,
    available_services: str = None,
    total_seasons_known: int = None,
    series_url: str = None,
    auto_tracked: bool = False
) -> int:
    """
    Create a new tracked series entry.
    
    Args:
        db_path: Path to the SQLite database
        user_id: User ID
        title: Series title
        justwatch_id: JustWatch ID for cross-service lookups
        imdb_id: IMDB ID
        preferred_service: Where to watch (netflix, hulu, etc.)
        available_services: JSON string of available services
        total_seasons_known: Number of seasons known
        series_url: URL to series page
        auto_tracked: Whether auto-added from watchlist
    
    Returns:
        Tracked series ID
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO tracked_series 
            (user_id, title, justwatch_id, imdb_id, preferred_service, 
             available_services, total_seasons_known, series_url,
             auto_tracked_from_watchlist, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, title, justwatch_id, imdb_id, preferred_service,
            available_services, total_seasons_known, series_url,
            1 if auto_tracked else 0, now, now
        ))
        
        conn.commit()
        return cursor.lastrowid
        
    finally:
        conn.close()


def get_tracked_series_by_id(db_path: str, series_id: int) -> dict:
    """Get a tracked series by its ID."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM tracked_series WHERE id = ?', (series_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_tracked_series_by_title(
    db_path: str,
    user_id: int,
    title: str
) -> dict:
    """
    Get a tracked series by title (case-insensitive partial match).
    
    Returns the first matching series or None.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Try exact match first
        cursor.execute(
            'SELECT * FROM tracked_series WHERE user_id = ? AND LOWER(title) = LOWER(?)',
            (user_id, title)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        # Try partial match
        cursor.execute(
            'SELECT * FROM tracked_series WHERE user_id = ? AND LOWER(title) LIKE LOWER(?)',
            (user_id, f'%{title}%')
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tracked_series(
    db_path: str,
    user_id: int,
    tracking_status: str = None,
    preferred_service: str = None
) -> list:
    """
    List tracked series with optional filters.
    
    Args:
        db_path: Path to the SQLite database
        user_id: User ID
        tracking_status: Filter by status (watching, finished, dropped, on_hold)
        preferred_service: Filter by service
    
    Returns:
        List of tracked series dicts
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        sql = 'SELECT * FROM tracked_series WHERE user_id = ?'
        params = [user_id]
        
        if tracking_status and tracking_status != 'all':
            sql += ' AND tracking_status = ?'
            params.append(tracking_status)
        
        if preferred_service and preferred_service != 'all':
            sql += ' AND preferred_service = ?'
            params.append(preferred_service)
        
        # Order: watching first, then by title
        sql += ''' ORDER BY 
            CASE tracking_status 
                WHEN 'watching' THEN 1 
                WHEN 'on_hold' THEN 2 
                WHEN 'finished' THEN 3 
                WHEN 'dropped' THEN 4 
            END,
            title
        '''
        
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_tracked_series(
    db_path: str,
    series_id: int,
    **kwargs
) -> bool:
    """
    Update a tracked series entry.
    
    Args:
        db_path: Path to the SQLite database
        series_id: Tracked series ID
        **kwargs: Fields to update (tracking_status, watch_status, preferred_service, etc.)
    
    Returns:
        True if updated, False if not found
    """
    allowed_fields = {
        'tracking_status', 'watch_status', 'preferred_service', 'available_services',
        'total_seasons_known', 'total_episodes_known', 'watched_episode_count',
        'manual_progress', 'last_synced_at', 'last_availability_check',
        'notes', 'series_url', 'justwatch_id', 'imdb_id'
    }
    
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return False
    
    updates['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [series_id]
        
        cursor.execute(
            f'UPDATE tracked_series SET {set_clause} WHERE id = ?',
            values
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_tracked_series(db_path: str, series_id: int) -> bool:
    """
    Delete a tracked series.
    
    Args:
        db_path: Path to the SQLite database
        series_id: Tracked series ID
    
    Returns:
        True if deleted, False if not found
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM tracked_series WHERE id = ?', (series_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_tracking_status(
    db_path: str,
    user_id: int,
    title: str,
    new_status: str
) -> dict:
    """
    Update the tracking status for a series.
    
    Args:
        db_path: Path to the SQLite database
        user_id: User ID
        title: Series title (fuzzy match)
        new_status: New tracking status
    
    Returns:
        Updated series dict or error dict
    """
    if new_status not in VALID_TRACKING_STATUSES:
        return {'error': f'Invalid status: {new_status}. Valid: {VALID_TRACKING_STATUSES}'}
    
    series = get_tracked_series_by_title(db_path, user_id, title)
    if not series:
        return {'error': f'Series not found: {title}'}
    
    update_tracked_series(db_path, series['id'], tracking_status=new_status)
    return get_tracked_series_by_id(db_path, series['id'])


def update_manual_progress(
    db_path: str,
    user_id: int,
    title: str,
    manual_progress: dict
) -> dict:
    """
    Update manual progress for a series.
    
    Args:
        db_path: Path to the SQLite database
        user_id: User ID
        title: Series title
        manual_progress: Dict with watched_through, additional_watched, source_note
    
    Returns:
        Updated series dict or error dict
    """
    import json
    
    series = get_tracked_series_by_title(db_path, user_id, title)
    if not series:
        return {'error': f'Series not found: {title}'}
    
    # Merge with existing manual progress
    existing = json.loads(series.get('manual_progress') or '{}')
    existing.update(manual_progress)
    
    update_tracked_series(
        db_path,
        series['id'],
        manual_progress=json.dumps(existing),
        watch_status='in_progress'  # If they're marking progress, they've started
    )
    return get_tracked_series_by_id(db_path, series['id'])


if __name__ == '__main__':
    import os
    
    logging.basicConfig(level=logging.INFO)
    
    db_path = os.environ.get('CONTENT_DB_PATH', '/app/data/content_database.db')
    extend_database_with_user_tables(db_path)
    print(f"Database extended at {db_path}")

