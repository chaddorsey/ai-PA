"""
Game Mapper: Maps ESPN game IDs to NFL Pro UUIDs

ESPN and NFL Pro use different game identifiers. This service maps between them
using team matchups and dates to correlate games.

Usage:
    from services.game_mapper import GameMapper
    mapper = GameMapper()
    nfl_pro_uuid = mapper.get_nfl_pro_uuid(espn_game_id, home_team, away_team)
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

DATA_PATH = Path(os.environ.get('DATA_PATH', '/Volumes/main-drive/ai-PA/auto-madden/data'))


class GameMapper:
    """Maps between ESPN game IDs and NFL Pro UUIDs."""
    
    MAPPING_FILE = DATA_PATH / "espn_nfl_pro_mapping.json"
    PLAYS_DB = DATA_PATH / "nfl_plays_2025.db"
    INSIGHTS_DB = DATA_PATH / "nfl_insights_2025.db"
    
    def __init__(self):
        self._mapping_cache: Dict[str, str] = {}
        self._uuid_to_teams: Dict[str, Tuple[str, str]] = {}
        self._load_mapping()
    
    def _load_mapping(self):
        """Load existing mapping from file."""
        if self.MAPPING_FILE.exists():
            try:
                with open(self.MAPPING_FILE, 'r') as f:
                    data = json.load(f)
                    self._mapping_cache = data.get('espn_to_nfl_pro', {})
                    logger.info(f"Loaded {len(self._mapping_cache)} game mappings")
            except Exception as e:
                logger.warning(f"Error loading mapping: {e}")
        
        # Build team lookup from plays database
        self._build_team_lookup()
    
    def _build_team_lookup(self):
        """Build lookup of NFL Pro UUID to team matchup."""
        if not self.PLAYS_DB.exists():
            return
        
        try:
            conn = sqlite3.connect(self.PLAYS_DB)
            cursor = conn.cursor()
            cursor.execute('SELECT game_id, home_team, away_team FROM games')
            for row in cursor.fetchall():
                game_id, home, away = row
                if home and away:
                    self._uuid_to_teams[game_id] = (home.upper(), away.upper())
            conn.close()
            logger.debug(f"Built team lookup for {len(self._uuid_to_teams)} games")
        except Exception as e:
            logger.warning(f"Error building team lookup: {e}")
        
        # Also check insights DB for games not in plays DB
        if not self.INSIGHTS_DB.exists():
            return
        
        try:
            conn = sqlite3.connect(self.INSIGHTS_DB)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT game_id FROM insights')
            insight_game_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # Mark games that have insights
            for uuid in insight_game_ids:
                if uuid not in self._uuid_to_teams:
                    self._uuid_to_teams[uuid] = ('UNKNOWN', 'UNKNOWN')
        except Exception as e:
            logger.warning(f"Error checking insights DB: {e}")
    
    def save_mapping(self):
        """Save mapping to file."""
        try:
            data = {
                'espn_to_nfl_pro': self._mapping_cache,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.MAPPING_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving mapping: {e}")
    
    def add_mapping(self, espn_id: str, nfl_pro_uuid: str):
        """Add a mapping between ESPN ID and NFL Pro UUID."""
        self._mapping_cache[espn_id] = nfl_pro_uuid
        self.save_mapping()
    
    def get_nfl_pro_uuid(
        self,
        espn_game_id: str,
        home_team: str = None,
        away_team: str = None
    ) -> Optional[str]:
        """
        Get NFL Pro UUID for an ESPN game.
        
        Args:
            espn_game_id: ESPN game ID
            home_team: Home team abbreviation (for matching)
            away_team: Away team abbreviation (for matching)
        
        Returns:
            NFL Pro UUID if found, None otherwise
        """
        # Check cache first
        if espn_game_id in self._mapping_cache:
            return self._mapping_cache[espn_game_id]
        
        # Try to match by teams
        if home_team and away_team:
            home_upper = home_team.upper()
            away_upper = away_team.upper()
            
            for uuid, (h, a) in self._uuid_to_teams.items():
                if h == home_upper and a == away_upper:
                    # Found match - cache it
                    self._mapping_cache[espn_game_id] = uuid
                    self.save_mapping()
                    logger.info(f"Mapped ESPN {espn_game_id} to NFL Pro {uuid[:8]} ({away_upper} @ {home_upper})")
                    return uuid
        
        return None
    
    def get_espn_id(self, nfl_pro_uuid: str) -> Optional[str]:
        """Get ESPN ID for an NFL Pro UUID (reverse lookup)."""
        for espn_id, uuid in self._mapping_cache.items():
            if uuid == nfl_pro_uuid:
                return espn_id
        return None
    
    def get_all_nfl_pro_uuids(self, week: int = None) -> List[str]:
        """Get all NFL Pro UUIDs, optionally filtered by week."""
        if not self.INSIGHTS_DB.exists():
            return list(self._uuid_to_teams.keys())
        
        try:
            conn = sqlite3.connect(self.INSIGHTS_DB)
            cursor = conn.cursor()
            
            if week:
                cursor.execute('SELECT DISTINCT game_id FROM insights WHERE week = ?', (week,))
            else:
                cursor.execute('SELECT DISTINCT game_id FROM insights')
            
            uuids = [row[0] for row in cursor.fetchall()]
            conn.close()
            return uuids
        except Exception as e:
            logger.error(f"Error getting UUIDs: {e}")
            return []
    
    def get_team_matchup(self, nfl_pro_uuid: str) -> Optional[Tuple[str, str]]:
        """Get team matchup (home, away) for an NFL Pro UUID."""
        return self._uuid_to_teams.get(nfl_pro_uuid)


# Singleton instance
_mapper = None

def get_mapper() -> GameMapper:
    """Get singleton GameMapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = GameMapper()
    return _mapper


def main():
    """Test the game mapper."""
    mapper = GameMapper()
    
    print("Game Mapper Status")
    print("=" * 50)
    print(f"Cached mappings: {len(mapper._mapping_cache)}")
    print(f"Known NFL Pro games: {len(mapper._uuid_to_teams)}")
    
    # Get Week 18 games
    week_18 = mapper.get_all_nfl_pro_uuids(week=18)
    print(f"\nWeek 18 games: {len(week_18)}")
    
    for uuid in week_18[:5]:
        teams = mapper.get_team_matchup(uuid)
        if teams:
            print(f"  {uuid[:8]}... = {teams[1]} @ {teams[0]}")
        else:
            print(f"  {uuid[:8]}... = (teams unknown)")


if __name__ == '__main__':
    main()

