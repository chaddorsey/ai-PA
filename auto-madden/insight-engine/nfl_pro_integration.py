"""
NFL Pro Integration for Insight Engine

Provides two types of NFL Pro data integration:
1. Play-by-play analysis: Formation, personnel, and historical comparison insights
2. Narrative insights: Pre-loaded insights from NFL Pro's content API for 
   player-triggered, break-time, and contextual delivery

The narrative insight system tracks usage across games to avoid repetition
within a game while optionally allowing reuse across different games.
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# Add nfl-pro-scraper to path for imports
NFL_PRO_SCRAPER_PATH = Path(__file__).parent.parent / "nfl-pro-scraper"
if str(NFL_PRO_SCRAPER_PATH) not in sys.path:
    sys.path.insert(0, str(NFL_PRO_SCRAPER_PATH))

# Path to historical database
DATA_PATH = Path(__file__).parent.parent / "data"
HISTORICAL_DB = DATA_PATH / "nfl_plays_2024.db"


class NFLProInsightGenerator:
    """
    Generates insights from NFL Pro detailed play data.
    
    Provides:
    - Formation analysis (SHOTGUN vs UNDER CENTER success rates)
    - Personnel grouping insights (11 personnel vs 12 personnel)
    - Defensive tendency analysis (box count, coverage)
    - Historical comparisons
    """
    
    # Personnel package descriptions
    PERSONNEL_DESCRIPTIONS = {
        '1 RB, 1 TE, 3 WR': '11 personnel (spread)',
        '1 RB, 2 TE, 2 WR': '12 personnel (balanced)',
        '2 RB, 1 TE, 2 WR': '21 personnel (power)',
        '1 RB, 3 TE, 1 WR': '13 personnel (heavy)',
        '2 RB, 2 TE, 1 WR': '22 personnel (jumbo)',
    }
    
    # Formation tendencies (general)
    FORMATION_TENDENCIES = {
        'SHOTGUN': {'pass_rate': 0.70, 'typical_play': 'pass'},
        'UNDER_CENTER': {'pass_rate': 0.45, 'typical_play': 'run'},
        'SINGLEBACK': {'pass_rate': 0.55, 'typical_play': 'balanced'},
        'I_FORM': {'pass_rate': 0.35, 'typical_play': 'run'},
        'PISTOL': {'pass_rate': 0.60, 'typical_play': 'pass'},
        'EMPTY': {'pass_rate': 0.90, 'typical_play': 'pass'},
    }
    
    def __init__(self):
        self._historical_cache: Dict[str, Any] = {}
        self._team_tendencies: Dict[str, Dict] = {}
    
    def get_formation_insight(
        self,
        formation: str,
        play_type: str,
        yards: int,
        situation: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Generate insight based on formation choice.
        
        Args:
            formation: Offensive formation (e.g., 'SHOTGUN')
            play_type: Type of play ('rush', 'pass')
            yards: Yards gained
            situation: Down, distance, field position
        
        Returns:
            Dict with 'headline' and 'body' or None
        """
        if not formation:
            return None
        
        formation_upper = formation.upper().replace(' ', '_')
        tendency = self.FORMATION_TENDENCIES.get(formation_upper)
        
        if not tendency:
            return None
        
        down = situation.get('down', 1)
        distance = situation.get('distance', 10)
        
        # Check if play matched formation tendency
        expected_play = 'pass' if tendency['pass_rate'] > 0.55 else 'run'
        matched_tendency = play_type == expected_play
        
        # Generate insight for interesting situations
        if not matched_tendency and yards >= 5:
            # Successful play against tendency
            return {
                'headline': f"Misdirection Success",
                'body': f"Running out of {formation.title()} kept the defense honest. "
                       f"They expected {expected_play} but got a {yards}-yard {play_type} instead.",
                'priority': 6,
            }
        
        if formation_upper == 'EMPTY' and play_type == 'rush':
            return {
                'headline': f"Empty Backfield Draw",
                'body': f"Surprisingly ran out of empty formation for {yards} yards. "
                       f"The defense was caught expecting pass.",
                'priority': 7,
            }
        
        if down == 3 and distance >= 7 and formation_upper != 'SHOTGUN':
            return {
                'headline': f"Unconventional 3rd Down Look",
                'body': f"Lined up in {formation.title()} on 3rd and {distance}. "
                       f"Most teams go shotgun here ({int(self.FORMATION_TENDENCIES.get('SHOTGUN', {}).get('pass_rate', 0.7) * 100)}% pass rate).",
                'priority': 5,
            }
        
        return None
    
    def get_personnel_insight(
        self,
        off_personnel: str,
        def_personnel: str,
        play_type: str,
        yards: int
    ) -> Optional[Dict[str, str]]:
        """
        Generate insight based on personnel packages.
        """
        if not off_personnel:
            return None
        
        personnel_name = self.PERSONNEL_DESCRIPTIONS.get(off_personnel, off_personnel)
        
        # Heavy personnel run success
        if '13' in personnel_name or '22' in personnel_name:
            if play_type == 'rush' and yards >= 5:
                return {
                    'headline': f"Power Run Success",
                    'body': f"{personnel_name.split('(')[0].strip()} brought extra blockers "
                           f"and moved the chains with a {yards}-yard run.",
                    'priority': 5,
                }
            elif play_type == 'pass' and yards >= 10:
                return {
                    'headline': f"Play Action Surprise",
                    'body': f"Heavy personnel sold the run fake and the pass went for {yards} yards. "
                           f"Defense bit hard on the play action.",
                    'priority': 6,
                }
        
        # Spread personnel 
        if '11' in personnel_name or 'spread' in personnel_name.lower():
            if play_type == 'rush' and yards >= 8:
                return {
                    'headline': f"Spread Run Success",
                    'body': f"Despite light personnel, the run game found a lane for {yards} yards. "
                           f"The spread formation created running room.",
                    'priority': 5,
                }
        
        return None
    
    def get_defensive_insight(
        self,
        defenders_in_box: Optional[int],
        play_type: str,
        yards: int,
        situation: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Generate insight based on defensive alignment.
        """
        if defenders_in_box is None:
            return None
        
        # Light box run success
        if defenders_in_box <= 6 and play_type == 'rush' and yards >= 8:
            return {
                'headline': f"Exposing the Light Box",
                'body': f"With only {defenders_in_box} defenders in the box, "
                       f"the run game exploited the numbers advantage for {yards} yards.",
                'priority': 6,
            }
        
        # Stacked box pass success
        if defenders_in_box >= 8 and play_type == 'pass' and yards >= 10:
            return {
                'headline': f"Making Them Pay",
                'body': f"Defense loaded the box with {defenders_in_box} defenders, "
                       f"leaving the secondary vulnerable. Pass went for {yards} yards.",
                'priority': 7,
            }
        
        # Run into stacked box failure
        if defenders_in_box >= 8 and play_type == 'rush' and yards <= 2:
            return {
                'headline': f"Stuffed at the Line",
                'body': f"Ran right into an 8-man box. {defenders_in_box} defenders "
                       f"overwhelmed the blocking scheme.",
                'priority': 5,
            }
        
        return None
    
    def get_historical_comparison(
        self,
        formation: str,
        personnel: str,
        play_type: str,
        possession_team: str
    ) -> Optional[Dict[str, Any]]:
        """
        Compare current play against historical data.
        
        Returns stats like success rate, average yards, etc.
        """
        if not HISTORICAL_DB.exists():
            return None
        
        cache_key = f"{formation}_{personnel}_{play_type}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]
        
        try:
            conn = sqlite3.connect(HISTORICAL_DB)
            cursor = conn.cursor()
            
            # Query for similar plays
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_plays,
                    AVG(CASE WHEN play_type = 'rush' THEN 
                        CAST(NULLIF(regexp_extract(play_description, 'for ([0-9]+) yard'), '') AS INTEGER)
                        ELSE NULL END) as avg_rush_yards,
                    SUM(is_scoring) as scoring_plays,
                    SUM(is_big_play) as big_plays
                FROM plays
                WHERE off_formation = ? AND play_type = ?
            ''', (formation, play_type))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0] > 20:  # Need sufficient sample
                result = {
                    'sample_size': row[0],
                    'avg_yards': row[1],
                    'scoring_rate': (row[2] / row[0]) * 100 if row[0] else 0,
                    'big_play_rate': (row[3] / row[0]) * 100 if row[0] else 0,
                }
                self._historical_cache[cache_key] = result
                return result
                
        except Exception as e:
            logger.error(f"Historical query error: {e}")
        
        return None
    
    def generate_play_insight(
        self,
        play: Dict[str, Any],
        state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Generate all applicable insights for a play with NFL Pro data.
        
        Args:
            play: NFL Pro play data with formation, personnel, etc.
            state: Current game state
        
        Returns:
            List of insight dicts with headline, body, priority
        """
        insights = []
        
        formation = play.get('off_formation', '')
        off_personnel = play.get('off_personnel', '')
        def_personnel = play.get('def_personnel', '')
        play_type = play.get('play_type', '')
        defenders_in_box = play.get('defenders_in_box')
        
        # Parse yards from description
        yards = 0
        desc = play.get('play_description', '')
        import re
        yards_match = re.search(r'for (\d+) yard', desc)
        if yards_match:
            yards = int(yards_match.group(1))
        
        situation = {
            'down': play.get('down', 1),
            'distance': play.get('yards_to_go', 10),
            'quarter': play.get('quarter', 1),
            'yard_line': play.get('yard_line', 50),
        }
        
        # Formation insight
        formation_insight = self.get_formation_insight(
            formation, play_type, yards, situation
        )
        if formation_insight:
            insights.append(formation_insight)
        
        # Personnel insight
        personnel_insight = self.get_personnel_insight(
            off_personnel, def_personnel, play_type, yards
        )
        if personnel_insight:
            insights.append(personnel_insight)
        
        # Defensive insight
        defensive_insight = self.get_defensive_insight(
            defenders_in_box, play_type, yards, situation
        )
        if defensive_insight:
            insights.append(defensive_insight)
        
        # Historical comparison for significant plays
        if yards >= 10 or play.get('is_scoring') or play.get('is_big_play'):
            historical = self.get_historical_comparison(
                formation, off_personnel, play_type, play.get('possession_team', '')
            )
            if historical and historical['sample_size'] > 50:
                insights.append({
                    'headline': "By The Numbers",
                    'body': f"This {formation.title()} {play_type} exceeded the league average. "
                           f"Similar plays this season averaged {historical['avg_yards']:.1f} yards.",
                    'priority': 4,
                })
        
        return insights
    
    def get_situational_tendency(
        self,
        team: str,
        situation: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get team's historical tendency in a situation.
        
        Args:
            team: Team abbreviation
            situation: 'red_zone', '3rd_short', '3rd_long', '2_minute', etc.
        
        Returns:
            Tendency data or None
        """
        if not HISTORICAL_DB.exists():
            return None
        
        try:
            conn = sqlite3.connect(HISTORICAL_DB)
            cursor = conn.cursor()
            
            # Map situation to query conditions
            conditions = {
                'red_zone': 'is_redzone = 1',
                '3rd_short': 'down = 3 AND yards_to_go <= 3',
                '3rd_long': 'down = 3 AND yards_to_go >= 7',
                'goal_line': 'yard_line LIKE "% 5" OR yard_line LIKE "% 3" OR yard_line LIKE "% 1"',
            }
            
            condition = conditions.get(situation, 'TRUE')
            
            # Get team tendencies - match both 3-letter abbreviation patterns
            cursor.execute(f'''
                SELECT 
                    play_type,
                    COUNT(*) as count,
                    AVG(is_scoring) * 100 as scoring_pct
                FROM plays
                WHERE possession_team = ? AND {condition}
                GROUP BY play_type
                ORDER BY count DESC
            ''', (team,))
            
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                total = sum(r[1] for r in rows)
                return {
                    'team': team,
                    'situation': situation,
                    'tendencies': [
                        {
                            'play_type': r[0],
                            'percentage': (r[1] / total) * 100,
                            'count': r[1],
                            'scoring_rate': r[2],
                        }
                        for r in rows
                    ],
                    'sample_size': total,
                }
                
        except Exception as e:
            logger.error(f"Tendency query error: {e}")
        
        return None


# Singleton instance
nfl_pro_generator = NFLProInsightGenerator()


def process_nfl_pro_play(play: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Convenience function to process an NFL Pro play.
    
    Called by the insight engine when NFL Pro data is available.
    """
    return nfl_pro_generator.generate_play_insight(play, state)


def get_pregame_tendencies(home_team: str, away_team: str) -> Dict[str, Any]:
    """
    Get pre-game tendency analysis for both teams.
    
    Returns formation preferences, situational tendencies, etc.
    """
    tendencies = {}
    
    for team in [home_team, away_team]:
        team_data = {
            'red_zone': nfl_pro_generator.get_situational_tendency(team, 'red_zone'),
            '3rd_short': nfl_pro_generator.get_situational_tendency(team, '3rd_short'),
            '3rd_long': nfl_pro_generator.get_situational_tendency(team, '3rd_long'),
        }
        tendencies[team] = team_data
    
    return tendencies


# ============================================================================
# NFL Pro Narrative Insight Integration
# ============================================================================

class NFLProNarrativeInsights:
    """
    Manages narrative insights from NFL Pro's content API.
    
    Provides:
    - Player-triggered insights when a player makes a notable play
    - Situation-triggered insights for game situations (red zone, 3rd down)
    - Break-time insights for commercial breaks, halftime
    - Cross-game usage tracking to avoid repetition
    
    Now supports loading from pre-processed insights (faster, with indices).
    """
    
    INSIGHT_CACHE_DIR = DATA_PATH / "nfl_pro_insights"
    PROCESSED_INSIGHT_DIR = DATA_PATH / "processed_insights"
    USAGE_HISTORY_FILE = DATA_PATH / "insight_usage_history.json"
    INSIGHTS_DB = DATA_PATH / "nfl_insights_2025.db"
    
    def __init__(self):
        self._index = None  # InsightIndex
        self._current_game_id: Optional[str] = None
        self._home_team: Optional[str] = None
        self._away_team: Optional[str] = None
        self._usage_history: Dict[str, List] = {}
        
        self._load_usage_history()
    
    def _load_usage_history(self):
        """Load historical insight usage from disk."""
        if self.USAGE_HISTORY_FILE.exists():
            try:
                with open(self.USAGE_HISTORY_FILE, 'r') as f:
                    self._usage_history = json.load(f)
                logger.info(f"Loaded usage history for {len(self._usage_history)} insights")
            except Exception as e:
                logger.error(f"Error loading usage history: {e}")
                self._usage_history = {}
    
    def _save_usage_history(self):
        """Save insight usage to disk."""
        try:
            self.USAGE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.USAGE_HISTORY_FILE, 'w') as f:
                json.dump(self._usage_history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving usage history: {e}")
    
    def load_from_processed(self, week: int) -> bool:
        """
        Load pre-processed insights for a week.
        
        This is the preferred method - uses pre-built index for fast retrieval.
        """
        processed_file = self.PROCESSED_INSIGHT_DIR / f"week_{week}_processed.json"
        
        if not processed_file.exists():
            logger.warning(f"No pre-processed insights for Week {week}")
            return False
        
        try:
            with open(processed_file, 'r') as f:
                data = json.load(f)
            
            self._processed_insights = data.get('insights', [])
            self._processed_index = data.get('index', {})
            
            # Track which insights have been served in current game
            self._served_in_game: set = set()
            
            logger.info(f"Loaded {len(self._processed_insights)} processed insights for Week {week}")
            return True
        except Exception as e:
            logger.error(f"Error loading processed insights: {e}")
            return False
    
    def load_from_db(self, game_uuid: str) -> bool:
        """
        Load insights directly from the insights database for a specific game.
        
        Falls back to this when processed file is not available.
        """
        if not self.INSIGHTS_DB.exists():
            logger.warning(f"Insights database not found: {self.INSIGHTS_DB}")
            return False
        
        try:
            import sqlite3
            conn = sqlite3.connect(self.INSIGHTS_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM insights WHERE game_id = ?
            ''', (game_uuid,))
            
            rows = cursor.fetchall()
            conn.close()
            
            self._processed_insights = [dict(row) for row in rows]
            self._processed_index = {}
            self._served_in_game = set()
            
            logger.info(f"Loaded {len(self._processed_insights)} insights from DB for game {game_uuid[:8]}")
            return len(self._processed_insights) > 0
        except Exception as e:
            logger.error(f"Error loading from DB: {e}")
            return False
    
    def get_insight_by_player(self, player_name: str) -> Optional[Dict]:
        """Get an unserved insight for a player from processed insights."""
        key = f"player:{player_name.lower()}"
        
        if hasattr(self, '_processed_index') and key in self._processed_index:
            insight_ids = self._processed_index[key]
            for insight in self._processed_insights:
                if insight.get('id') in insight_ids and insight.get('id') not in self._served_in_game:
                    self._served_in_game.add(insight['id'])
                    return self._format_insight(insight)
        
        # Fallback: search by name
        if hasattr(self, '_processed_insights'):
            for insight in self._processed_insights:
                if player_name.lower() in insight.get('player_name', '').lower():
                    if insight.get('id') not in self._served_in_game:
                        self._served_in_game.add(insight['id'])
                        return self._format_insight(insight)
        
        return None
    
    def get_insight_by_team(self, team_abbr: str) -> Optional[Dict]:
        """Get an unserved insight for a team."""
        key = f"team:{team_abbr.lower()}"
        
        if hasattr(self, '_processed_index') and key in self._processed_index:
            insight_ids = self._processed_index[key]
            for insight in self._processed_insights:
                if insight.get('id') in insight_ids and insight.get('id') not in self._served_in_game:
                    self._served_in_game.add(insight['id'])
                    return self._format_insight(insight)
        
        return None
    
    def get_insight_by_topic(self, topic: str) -> Optional[Dict]:
        """Get an unserved insight for a topic (passing, rushing, defense, etc.)."""
        key = f"topic:{topic.lower()}"
        
        if hasattr(self, '_processed_index') and key in self._processed_index:
            insight_ids = self._processed_index[key]
            for insight in self._processed_insights:
                if insight.get('id') in insight_ids and insight.get('id') not in self._served_in_game:
                    self._served_in_game.add(insight['id'])
                    return self._format_insight(insight)
        
        return None
    
    def get_random_unserved_insight(self, prefer_team: str = None) -> Optional[Dict]:
        """Get a random unserved insight, preferring given team if specified."""
        if not hasattr(self, '_processed_insights'):
            return None
        
        import random
        
        # Filter to unserved
        unserved = [i for i in self._processed_insights if i.get('id') not in self._served_in_game]
        
        if not unserved:
            return None
        
        # Prefer team if specified
        if prefer_team:
            team_insights = [i for i in unserved if prefer_team.upper() in (
                i.get('player_team', '').upper(),
                ' '.join(i.get('teams_mentioned', []))
            )]
            if team_insights:
                unserved = team_insights
        
        insight = random.choice(unserved)
        self._served_in_game.add(insight['id'])
        return self._format_insight(insight)
    
    def _format_insight(self, insight: Dict) -> Dict:
        """Format a processed insight for delivery."""
        return {
            'id': insight.get('id', ''),
            'headline': insight.get('player_name') or 'Game Insight',
            'body': insight.get('title', ''),
            'extended': insight.get('sub_note', ''),
            'source': 'nfl_pro',
            'priority': 7,
            'image_url': insight.get('image_url', ''),
            'local_image': insight.get('local_image', ''),
            'terms_of_art': insight.get('terms_of_art', []),
            'topics': insight.get('topics', [])
        }
    
    def get_unserved_count(self) -> int:
        """Get count of remaining unserved insights."""
        if not hasattr(self, '_processed_insights'):
            return 0
        return len([i for i in self._processed_insights if i.get('id') not in self._served_in_game])
    
    def load_game_insights(
        self,
        game_uuid: str,
        home_team: str,
        away_team: str,
        insights_data: Optional[List[Dict]] = None
    ) -> bool:
        """
        Load insights for a game.
        
        Args:
            game_uuid: NFL Pro game UUID
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            insights_data: Optional pre-fetched insights; if None, loads from cache
        
        Returns:
            True if insights loaded successfully
        """
        self._current_game_id = game_uuid
        self._home_team = home_team
        self._away_team = away_team
        
        try:
            from scrapers.insight_parser import InsightParser
            from models.insight_schema import InsightIndex
        except ImportError as e:
            logger.error(f"Could not import insight parser: {e}")
            return False
        
        # Try to load cached insights or use provided data
        if insights_data:
            parser = InsightParser()
            self._index = parser.parse_batch(insights_data)
        else:
            # Try to load from cache
            cache_file = self.INSIGHT_CACHE_DIR / f"{game_uuid[:8]}_insights.json"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                    self._index = InsightIndex.from_json(json.dumps(data))
                    logger.info(f"Loaded {len(self._index.all_insights)} insights from cache")
                except Exception as e:
                    logger.error(f"Error loading cached insights: {e}")
                    return False
            else:
                logger.warning(f"No cached insights for game {game_uuid[:8]}")
                return False
        
        # Restore usage history for these insights
        for insight in self._index.all_insights:
            if insight.id in self._usage_history:
                insight.usage_history = self._usage_history[insight.id]
                insight.times_used = len(insight.usage_history)
        
        logger.info(f"Loaded {len(self._index.all_insights)} narrative insights for {away_team} @ {home_team}")
        return True
    
    def get_player_insight(
        self,
        player_name: str,
        quarter: int,
        situation: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get an insight triggered by a player's notable play.
        
        Args:
            player_name: Player name (can be partial, e.g., "Mahomes")
            quarter: Current quarter
            situation: Optional situation context (e.g., "red_zone")
        
        Returns:
            Insight dict with headline, body, source, or None
        """
        if not self._index or not self._current_game_id:
            return None
        
        # Get insights for this player not yet used in this game
        insights = self._index.get_for_player(player_name, unused_only=False)
        insights = [i for i in insights if not i.was_used_in_game(self._current_game_id)]
        
        if not insights:
            return None
        
        # Prefer situation-relevant insights
        if situation:
            situation_insights = [i for i in insights if i.matches_situation(situation)]
            if situation_insights:
                insights = situation_insights
        
        # Take highest significance
        insight = max(insights, key=lambda i: i.significance)
        
        # Mark as used
        self._mark_used(insight.id, quarter)
        
        return {
            'id': insight.id,
            'headline': insight.title,
            'body': insight.primary_text,
            'extended': insight.secondary_text,
            'source': 'nfl_pro',
            'priority': min(insight.significance + 2, 10),  # Boost priority
        }
    
    def get_situation_insight(
        self,
        situation: str,
        team: str,
        quarter: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get an insight relevant to a game situation.
        
        Args:
            situation: Situation key (e.g., "red_zone", "3rd_down")
            team: Team abbreviation for context
            quarter: Current quarter
        
        Returns:
            Insight dict or None
        """
        if not self._index or not self._current_game_id:
            return None
        
        insights = self._index.get_for_situation(situation, team)
        insights = [i for i in insights if not i.was_used_in_game(self._current_game_id)]
        
        if not insights:
            return None
        
        insight = insights[0]  # Highest significance
        self._mark_used(insight.id, quarter)
        
        return {
            'id': insight.id,
            'headline': insight.title,
            'body': insight.primary_text,
            'extended': insight.secondary_text,
            'source': 'nfl_pro',
            'priority': insight.significance,
        }
    
    def get_break_insights(
        self,
        break_type: str,
        quarter: int,
        count: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get insights appropriate for a break period.
        
        Args:
            break_type: Type of break (e.g., "commercial", "halftime", "timeout")
            quarter: Current quarter
            count: Number of insights to return
        
        Returns:
            List of insight dicts, sorted by significance
        """
        if not self._index or not self._current_game_id:
            return []
        
        teams = [self._home_team, self._away_team]
        insights = self._index.get_for_break(quarter, teams=teams)
        insights = [i for i in insights if not i.was_used_in_game(self._current_game_id)]
        
        results = []
        for insight in insights[:count]:
            self._mark_used(insight.id, quarter)
            
            # Use extended text for breaks
            body = insight.get_presentation_text(mode='full')
            
            results.append({
                'id': insight.id,
                'headline': insight.title,
                'body': body,
                'source': 'nfl_pro',
                'priority': insight.significance,
                'is_extended': True,
            })
        
        return results
    
    def get_matchup_insights(
        self,
        quarter: int,
        count: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get head-to-head matchup insights.
        """
        if not self._index or not self._current_game_id:
            return []
        
        insights = self._index.get_matchup_insights(self._home_team, self._away_team)
        insights = [i for i in insights if not i.was_used_in_game(self._current_game_id)]
        
        results = []
        for insight in insights[:count]:
            self._mark_used(insight.id, quarter)
            results.append({
                'id': insight.id,
                'headline': insight.title,
                'body': insight.primary_text,
                'extended': insight.secondary_text,
                'source': 'nfl_pro',
                'priority': insight.significance + 1,  # Boost matchup priority
            })
        
        return results
    
    def get_pregame_insights(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get a sequence of insights for pre-game delivery.
        """
        if not self._index or not self._current_game_id:
            return []
        
        # Mix of matchup insights and general team insights
        results = []
        
        # Start with matchup insights
        matchups = self.get_matchup_insights(quarter=0, count=min(2, count))
        results.extend(matchups)
        
        # Add team-specific insights
        remaining = count - len(results)
        if remaining > 0 and self._home_team:
            home_insights = self._index.get_for_team(self._home_team, unused_only=True)
            home_insights = [i for i in home_insights if not i.was_used_in_game(self._current_game_id)]
            for insight in home_insights[:remaining // 2]:
                self._mark_used(insight.id, quarter=0)
                results.append({
                    'id': insight.id,
                    'headline': insight.title,
                    'body': insight.primary_text,
                    'source': 'nfl_pro',
                    'priority': insight.significance,
                })
        
        remaining = count - len(results)
        if remaining > 0 and self._away_team:
            away_insights = self._index.get_for_team(self._away_team, unused_only=True)
            away_insights = [i for i in away_insights if not i.was_used_in_game(self._current_game_id)]
            for insight in away_insights[:remaining]:
                self._mark_used(insight.id, quarter=0)
                results.append({
                    'id': insight.id,
                    'headline': insight.title,
                    'body': insight.primary_text,
                    'source': 'nfl_pro',
                    'priority': insight.significance,
                })
        
        return results
    
    def get_llm_context(
        self,
        player: str = None,
        team: str = None,
        situation: str = None
    ) -> str:
        """
        Get a context bundle for LLM synthesis.
        
        Returns formatted text with relevant background for LLM to use
        when generating custom insights.
        """
        if not self._index:
            return ""
        
        return self._index.get_llm_context_bundle(
            player=player,
            team=team,
            situation=situation
        )
    
    def _mark_used(self, insight_id: str, quarter: int):
        """Mark an insight as used and persist."""
        if self._index:
            game_date = datetime.now().strftime('%Y-%m-%d')
            self._index.mark_used(
                insight_id,
                quarter,
                game_id=self._current_game_id,
                game_date=game_date
            )
            
            # Update global usage history
            if insight_id not in self._usage_history:
                self._usage_history[insight_id] = []
            self._usage_history[insight_id].append({
                'game_id': self._current_game_id,
                'game_date': game_date,
                'quarter': quarter,
                'timestamp': datetime.now().isoformat(),
            })
            
            # Persist periodically
            self._save_usage_history()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded insights."""
        if not self._index:
            return {'loaded': False}
        
        unused = len(self._index.get_unused_for_game(self._current_game_id)) if self._current_game_id else 0
        
        return {
            'loaded': True,
            'total': len(self._index.all_insights),
            'unused_this_game': unused,
            'used_this_game': len(self._index.all_insights) - unused,
            'players_indexed': len(self._index.by_player),
            'matchup_insights': len(self._index.matchup_insights),
            'current_game': self._current_game_id,
        }


# Singleton instance
nfl_pro_narratives = NFLProNarrativeInsights()


# Convenience functions for insight engine integration
def load_narrative_insights(
    game_uuid: str,
    home_team: str = '',
    away_team: str = '',
    insights_data: List[Dict] = None,
    week: int = 18  # Default to current week
) -> int:
    """
    Load NFL Pro narrative insights for a game.
    
    Tries methods in order:
    1. Pre-processed insights file (fastest, with index)
    2. Direct database lookup by game UUID
    3. Original cache/parser method (fallback)
    
    Returns:
        Number of insights loaded
    """
    # Try loading from processed insights first (Week 18 for current games)
    if nfl_pro_narratives.load_from_processed(week):
        logger.info(f"Loaded Week {week} processed insights successfully")
        return nfl_pro_narratives.get_unserved_count()
    
    # Try loading from database by game ID
    if nfl_pro_narratives.load_from_db(game_uuid):
        logger.info(f"Loaded insights from DB for game {game_uuid[:8]}")
        return len(nfl_pro_narratives._processed_insights)
    
    # Fallback to original method
    if nfl_pro_narratives.load_game_insights(game_uuid, home_team, away_team, insights_data):
        if hasattr(nfl_pro_narratives, '_index') and nfl_pro_narratives._index:
            return len(nfl_pro_narratives._index.all_insights)
    
    return 0


def get_player_triggered_insight(
    player_name: str,
    quarter: int,
    situation: str = None
) -> Optional[Dict[str, Any]]:
    """Get an insight triggered by a player's play."""
    # Try new processed insights method first
    insight = nfl_pro_narratives.get_insight_by_player(player_name)
    if insight:
        return insight
    
    # Fallback to original method
    return nfl_pro_narratives.get_player_insight(player_name, quarter, situation)


def get_break_narrative_insights(
    break_type: str,
    quarter: int,
    count: int = 2,
    prefer_team: str = None
) -> List[Dict[str, Any]]:
    """Get narrative insights for a break period."""
    insights = []
    
    # Try processed insights first
    for _ in range(count):
        insight = nfl_pro_narratives.get_random_unserved_insight(prefer_team)
        if insight:
            insights.append(insight)
    
    if insights:
        return insights
    
    # Fallback to original method
    return nfl_pro_narratives.get_break_insights(break_type, quarter, count)


def get_pregame_narrative_insights(count: int = 5) -> List[Dict[str, Any]]:
    """Get a sequence of pregame insights."""
    return nfl_pro_narratives.get_pregame_insights(count)


def get_narrative_llm_context(
    player: str = None,
    team: str = None,
    situation: str = None
) -> str:
    """Get NFL Pro context for LLM synthesis."""
    return nfl_pro_narratives.get_llm_context(player, team, situation)

