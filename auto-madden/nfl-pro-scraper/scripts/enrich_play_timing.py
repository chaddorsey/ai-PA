#!/usr/bin/env python3
"""
Enrich play database with real-time (wall clock) timestamps from nflfastR via nfl_data_py.

The nflfastR data includes 'time_of_day' which contains actual wall-clock timestamps
for when each play occurred during the broadcast.
"""

import sqlite3
import nfl_data_py as nfl
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_nflfastr_game_id(game_uuid: str, home_team: str, away_team: str, 
                          season: int, week: int) -> str:
    """
    Convert NFL Pro game UUID to nflfastR game_id format.
    
    nflfastR uses format: YYYY_WW_AWAY_HOME (e.g., 2024_01_BAL_KC)
    """
    return f"{season}_{week:02d}_{away_team}_{home_team}"


def load_nflfastr_timing(season: int, columns: list = None) -> pd.DataFrame:
    """Load play-by-play data with timing columns from nflfastR."""
    if columns is None:
        columns = [
            'game_id', 'play_id', 'time_of_day', 'game_seconds_remaining',
            'quarter_seconds_remaining', 'half_seconds_remaining',
            'home_team', 'away_team', 'week', 'desc'
        ]
    
    logger.info(f"Loading nflfastR PBP data for {season}...")
    pbp = nfl.import_pbp_data([season], columns=columns)
    logger.info(f"Loaded {len(pbp)} plays")
    return pbp


def enrich_database(db_path: str, season: int):
    """Add time_of_day column to plays table and populate from nflfastR data."""
    
    # Load nflfastR data
    nflfastr_data = load_nflfastr_timing(season)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Add time_of_day column if it doesn't exist
    cursor.execute("PRAGMA table_info(plays)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'time_of_day' not in columns:
        logger.info("Adding time_of_day column to plays table...")
        cursor.execute("ALTER TABLE plays ADD COLUMN time_of_day TEXT")
        conn.commit()
    
    if 'real_seconds_elapsed' not in columns:
        logger.info("Adding real_seconds_elapsed column to plays table...")
        cursor.execute("ALTER TABLE plays ADD COLUMN real_seconds_elapsed REAL")
        conn.commit()
    
    # Get list of games in our database
    cursor.execute("SELECT DISTINCT game_id FROM plays")
    our_games = [row[0] for row in cursor.fetchall()]
    logger.info(f"Found {len(our_games)} games in database")
    
    # Get game metadata to build nflfastR game IDs
    cursor.execute("""
        SELECT DISTINCT game_id, 
               (SELECT possession_team FROM plays p2 WHERE p2.game_id = plays.game_id LIMIT 1) as sample_team
        FROM plays
    """)
    
    # For each game, try to match with nflfastR data
    games_enriched = 0
    plays_enriched = 0
    
    for game_id in our_games:
        # Get plays from our database
        cursor.execute("""
            SELECT id, play_id, sequence, quarter, start_clock, possession_team
            FROM plays 
            WHERE game_id = ?
            ORDER BY sequence
        """, (game_id,))
        our_plays = cursor.fetchall()
        
        if not our_plays:
            continue
        
        # Try to find matching game in nflfastR data
        # First, get teams from our data
        cursor.execute("""
            SELECT DISTINCT possession_team FROM plays WHERE game_id = ?
        """, (game_id,))
        teams = [row[0] for row in cursor.fetchall() if row[0]]
        
        if len(teams) < 2:
            logger.warning(f"Could not determine teams for game {game_id}")
            continue
        
        # Normalize team abbreviations (handle LAR vs LA for Rams, etc.)
        TEAM_ABBREV_MAP = {
            'LAR': 'LA',   # Rams
            'JAC': 'JAX',  # Jaguars
            'WSH': 'WAS',  # Commanders
        }
        normalized_teams = set()
        for team in teams:
            normalized_teams.add(TEAM_ABBREV_MAP.get(team, team))
        
        # Find matching game in nflfastR (try both team orderings)
        matching_games = nflfastr_data[
            (nflfastr_data['home_team'].isin(normalized_teams)) & 
            (nflfastr_data['away_team'].isin(normalized_teams))
        ]
        
        if matching_games.empty:
            logger.warning(f"No nflfastR match for game {game_id} ({teams})")
            continue
        
        nflfastr_game_id = matching_games['game_id'].iloc[0]
        game_plays = matching_games[matching_games['game_id'] == nflfastr_game_id].copy()
        
        logger.info(f"Matching {game_id} -> {nflfastr_game_id} ({len(game_plays)} plays)")
        
        # Calculate real_seconds_elapsed from game start
        first_time = None
        for idx, row in game_plays.iterrows():
            if pd.notna(row['time_of_day']) and first_time is None:
                try:
                    first_time = datetime.fromisoformat(row['time_of_day'].replace('Z', '+00:00'))
                except:
                    pass
        
        if first_time is None:
            logger.warning(f"No valid time_of_day in nflfastR for {nflfastr_game_id}")
            continue
        
        # Match plays by game clock (quarter + time) since play_ids don't match
        # Sort both datasets by game progression
        game_plays = game_plays.sort_values(['game_seconds_remaining'], ascending=False)
        game_plays_list = game_plays.to_dict('records')
        
        for our_id, our_play_id, sequence, quarter, start_clock, poss_team in our_plays:
            if not start_clock or not quarter:
                continue
            
            # Parse our clock to seconds remaining in game
            try:
                parts = start_clock.split(':')
                mins = int(parts[0])
                secs = int(parts[1]) if len(parts) > 1 else 0
                our_game_secs = (4 - quarter) * 900 + mins * 60 + secs
            except:
                continue
            
            # Find closest match in nflfastR by game_seconds_remaining
            best_match = None
            best_diff = float('inf')
            
            for nfl_play in game_plays_list:
                nfl_game_secs = nfl_play.get('game_seconds_remaining')
                if pd.isna(nfl_game_secs):
                    continue
                
                diff = abs(nfl_game_secs - our_game_secs)
                if diff < best_diff and diff < 30:  # Within 30 seconds
                    best_diff = diff
                    best_match = nfl_play
            
            if not best_match:
                continue
            
            time_of_day = best_match.get('time_of_day')
            
            if pd.isna(time_of_day) or not time_of_day:
                continue
            
            # Calculate seconds elapsed from game start
            try:
                play_time = datetime.fromisoformat(str(time_of_day).replace('Z', '+00:00'))
                real_seconds = (play_time - first_time).total_seconds()
            except:
                real_seconds = None
            
            # Update our database
            cursor.execute("""
                UPDATE plays 
                SET time_of_day = ?, real_seconds_elapsed = ?
                WHERE id = ?
            """, (time_of_day, real_seconds, our_id))
            plays_enriched += 1
        
        games_enriched += 1
        conn.commit()
        logger.info(f"  Enriched {plays_enriched} plays so far")
    
    conn.close()
    logger.info(f"Done! Enriched {games_enriched} games, {plays_enriched} plays total")


def verify_enrichment(db_path: str):
    """Check the results of enrichment."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM plays WHERE time_of_day IS NOT NULL
    """)
    enriched = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM plays")
    total = cursor.fetchone()[0]
    
    print(f"\n=== Enrichment Results ===")
    print(f"Total plays: {total}")
    print(f"With time_of_day: {enriched} ({100*enriched/total:.1f}%)")
    
    # Sample timing data
    cursor.execute("""
        SELECT sequence, quarter, start_clock, time_of_day, real_seconds_elapsed, 
               substr(play_description, 1, 50) as desc
        FROM plays 
        WHERE time_of_day IS NOT NULL 
        ORDER BY game_id, sequence
        LIMIT 10
    """)
    
    print("\n=== Sample enriched plays ===")
    for row in cursor.fetchall():
        print(f"  Seq {row[0]}: Q{row[1]} {row[2]} | {row[3]} | +{row[4]:.1f}s | {row[5]}")
    
    conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Enrich play database with real-time timestamps')
    parser.add_argument('--db', default='data/nfl_plays_2025.db', help='Database path')
    parser.add_argument('--season', type=int, default=2024, help='NFL season year')
    parser.add_argument('--verify', action='store_true', help='Just verify existing enrichment')
    
    args = parser.parse_args()
    
    db_path = Path(__file__).parent.parent.parent / args.db
    
    if args.verify:
        verify_enrichment(str(db_path))
    else:
        enrich_database(str(db_path), args.season)
        verify_enrichment(str(db_path))

