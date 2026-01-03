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


if __name__ == '__main__':
    import os
    
    logging.basicConfig(level=logging.INFO)
    
    db_path = os.environ.get('CONTENT_DB_PATH', '/app/data/content_database.db')
    extend_database_with_user_tables(db_path)
    print(f"Database extended at {db_path}")

