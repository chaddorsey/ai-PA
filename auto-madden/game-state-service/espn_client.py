"""
ESPN API Client for Auto-Madden.

Fetches real-time game data from ESPN's hidden API endpoints.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from dateutil import parser as date_parser

from models import (
    TeamInfo, PlayEvent, DriveInfo, GameState,
    get_play_type
)

logger = logging.getLogger(__name__)

# ESPN API endpoints
ESPN_BASE_URL = "http://site.api.espn.com/apis/site/v2/sports/football"
NFL_SCOREBOARD = f"{ESPN_BASE_URL}/nfl/scoreboard"
NFL_SUMMARY = f"{ESPN_BASE_URL}/nfl/summary"
NFL_ATHLETES = f"{ESPN_BASE_URL}/nfl/athletes"

# Request timeout in seconds
REQUEST_TIMEOUT = 10


class ESPNClient:
    """Client for fetching NFL data from ESPN API."""

    def __init__(self):
        """Initialize the ESPN client."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Auto-Madden/1.0'
        })

    def get_scoreboard(self) -> List[Dict[str, Any]]:
        """
        Get current NFL scoreboard with all games.
        
        Returns:
            List of game summaries from the scoreboard.
        """
        try:
            response = self.session.get(NFL_SCOREBOARD, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            games = []
            for event in data.get('events', []):
                game_info = self._parse_scoreboard_event(event)
                if game_info:
                    games.append(game_info)
            
            return games
            
        except Exception as e:
            logger.error(f"Error fetching scoreboard: {e}")
            return []

    def get_game_summary(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed game summary including play-by-play.
        
        Args:
            game_id: ESPN game ID
            
        Returns:
            Raw game summary data from ESPN API.
        """
        try:
            response = self.session.get(
                NFL_SUMMARY,
                params={'event': game_id},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching game summary for {game_id}: {e}")
            return None

    def get_player_info(self, athlete_id: str) -> Optional[Dict[str, Any]]:
        """
        Get player details.
        
        Args:
            athlete_id: ESPN athlete ID
            
        Returns:
            Player information dictionary.
        """
        try:
            response = self.session.get(
                f"{NFL_ATHLETES}/{athlete_id}",
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching player {athlete_id}: {e}")
            return None

    def find_game_by_team(self, team_query: str) -> Optional[Dict[str, Any]]:
        """
        Find a game by team name.
        
        Args:
            team_query: Team name or abbreviation to search for
            
        Returns:
            Game summary if found, None otherwise.
        """
        team_query = team_query.lower().strip()
        games = self.get_scoreboard()
        
        for game in games:
            home = game.get('home_team', {})
            away = game.get('away_team', {})
            
            # Check home team
            if (team_query in home.get('name', '').lower() or
                team_query in home.get('abbreviation', '').lower()):
                return game
            
            # Check away team
            if (team_query in away.get('name', '').lower() or
                team_query in away.get('abbreviation', '').lower()):
                return game
        
        return None

    def parse_game_state(self, raw_data: Dict[str, Any]) -> GameState:
        """
        Parse ESPN game summary into GameState model.
        
        Args:
            raw_data: Raw ESPN API response
            
        Returns:
            Parsed GameState object.
        """
        # Extract basic game info from header
        header = raw_data.get('header', {})
        competitions = header.get('competitions', [{}])
        competition = competitions[0] if competitions else {}
        
        # Get game ID
        game_id = raw_data.get('header', {}).get('id', '')
        
        # Get status
        status_data = competition.get('status', {})
        status_type = status_data.get('type', {})
        status = self._map_status(status_type.get('state', 'pre'))
        
        # Get situation
        situation = raw_data.get('situation', {})

        # Parse teams
        home_team, away_team = self._parse_teams(competition)

        # Get clock and situation details
        clock_data = situation.get('clock', {})
        down = situation.get('down')
        distance = situation.get('distance')
        yard_line = situation.get('yardLine')

        # Possession
        possession_data = situation.get('possession', {})
        possession_team = possession_data.get('abbreviation')

        # If situation data is missing (timeout/commercial), try to get from last valid play
        if down is None or down < 1:
            drives = raw_data.get('drives', {})
            current_drive = drives.get('current', {})
            plays = current_drive.get('plays', [])
            # Search backwards for a play with valid end situation
            for play in reversed(plays):
                end_situation = play.get('end', {})
                if end_situation.get('down', 0) > 0:
                    down = end_situation.get('down')
                    distance = end_situation.get('distance')
                    yard_line = end_situation.get('yardLine')
                    break
            # Also try to get possession from drive
            if not possession_team:
                drive_team = current_drive.get('team', {})
                possession_team = drive_team.get('abbreviation')

        # Apply defaults if still missing
        down = down if down and down > 0 else 1
        distance = distance if distance else 10
        yard_line = yard_line if yard_line else 25
        
        # Is red zone
        is_red_zone = situation.get('isRedZone', False)
        
        # Two minute warning check
        period = status_data.get('period', 1)
        # Try status.displayClock first (more reliable), then situation.clock
        clock_display = status_data.get('displayClock') or clock_data.get('displayValue', '15:00')
        is_two_minute = self._is_two_minute_warning(clock_display, period)
        
        # Win probability
        predictor = raw_data.get('predictor', {})
        home_wp = predictor.get('homeTeam', {}).get('gameProjection', 50.0)
        away_wp = predictor.get('awayTeam', {}).get('gameProjection', 50.0)
        
        # Parse plays from drives
        recent_plays = self._parse_recent_plays(raw_data.get('drives', {}))
        
        # Parse current drive
        current_drive = self._parse_current_drive(raw_data.get('drives', {}))
        
        # Get timeouts
        home_timeouts = situation.get('homeTimeouts', 3)
        away_timeouts = situation.get('awayTimeouts', 3)
        
        # Game name
        game_name = header.get('gameNote', '')
        short_name = competition.get('shortName', '')
        if not short_name and home_team and away_team:
            short_name = f"{away_team.abbreviation} @ {home_team.abbreviation}"
        
        # Broadcast
        broadcasts = competition.get('broadcasts', [])
        broadcast_network = None
        if broadcasts:
            names = broadcasts[0].get('names', [])
            broadcast_network = names[0] if names else None
        
        # Venue
        venue_data = competition.get('venue', {})
        venue = venue_data.get('fullName')
        
        return GameState(
            game_id=game_id,
            status=status,
            quarter=period,
            clock=clock_display,
            clock_running=not situation.get('isClockStopped', True),
            down=down,
            distance=distance,
            yard_line=yard_line,
            possession_team=possession_team,
            is_red_zone=is_red_zone,
            is_two_minute_warning=is_two_minute,
            home_team=home_team,
            away_team=away_team,
            home_timeouts=home_timeouts,
            away_timeouts=away_timeouts,
            home_win_probability=home_wp,
            away_win_probability=away_wp,
            recent_plays=recent_plays,
            current_drive=current_drive,
            game_name=game_name,
            short_name=short_name,
            broadcast_network=broadcast_network,
            venue=venue,
            last_updated=datetime.now()
        )

    def _parse_scoreboard_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single event from the scoreboard."""
        try:
            competition = event.get('competitions', [{}])[0]
            competitors = competition.get('competitors', [])
            
            if len(competitors) < 2:
                return None
            
            home_team = None
            away_team = None
            
            for comp in competitors:
                team_data = comp.get('team', {})
                team_info = {
                    'id': team_data.get('id'),
                    'name': team_data.get('displayName'),
                    'abbreviation': team_data.get('abbreviation'),
                    'score': int(comp.get('score', 0)),
                }
                
                if comp.get('homeAway') == 'home':
                    home_team = team_info
                else:
                    away_team = team_info
            
            status = event.get('status', {}).get('type', {})
            
            # Build score string
            home_score = home_team['score'] if home_team else 0
            away_score = away_team['score'] if away_team else 0
            score_str = f"{away_score}-{home_score}" if status.get('state') != 'pre' else ''

            return {
                'game_id': event.get('id'),
                'id': event.get('id'),  # UI expects 'id'
                'name': event.get('name'),
                'short_name': event.get('shortName'),
                'status': self._map_status(status.get('state', 'pre')),
                'status_detail': status.get('shortDetail', ''),
                'home_team': home_team,
                'away_team': away_team,
                'home': home_team['abbreviation'] if home_team else '',  # UI expects 'home'
                'away': away_team['abbreviation'] if away_team else '',  # UI expects 'away'
                'score': score_str,  # UI expects 'score'
                'date': event.get('date'),
            }
            
        except Exception as e:
            logger.error(f"Error parsing scoreboard event: {e}")
            return None

    def _parse_teams(self, competition: Dict[str, Any]) -> tuple:
        """Parse home and away teams from competition data."""
        home_team = None
        away_team = None
        
        for comp in competition.get('competitors', []):
            team_data = comp.get('team', {})
            
            # Get record
            record = None
            for rec in comp.get('records', []):
                if rec.get('type') == 'total':
                    record = rec.get('summary')
                    break
            
            # Get ranking (college)
            ranking = None
            curated_rank = comp.get('curatedRank', {})
            if curated_rank.get('current'):
                ranking = curated_rank.get('current')
            
            team = TeamInfo(
                id=team_data.get('id', ''),
                name=team_data.get('displayName', 'Unknown'),
                abbreviation=team_data.get('abbreviation', 'UNK'),
                score=int(comp.get('score', 0)),
                record=record,
                ranking=ranking
            )
            
            if comp.get('homeAway') == 'home':
                home_team = team
            else:
                away_team = team
        
        return home_team, away_team

    def _parse_recent_plays(self, drives_data: Dict[str, Any]) -> List[PlayEvent]:
        """Parse recent plays from drives data."""
        plays = []
        
        # Current drive plays
        current = drives_data.get('current', {})
        for play in current.get('plays', []):
            parsed = self._parse_play(play)
            if parsed:
                plays.append(parsed)
        
        # Previous drives (last few plays)
        for drive in drives_data.get('previous', [])[-3:]:
            for play in drive.get('plays', [])[-3:]:
                parsed = self._parse_play(play)
                if parsed:
                    plays.append(parsed)
        
        # Sort by timestamp and return most recent 20
        plays.sort(key=lambda p: p.timestamp or datetime.min, reverse=True)
        return plays[:20]

    def _parse_play(self, play_data: Dict[str, Any]) -> Optional[PlayEvent]:
        """Parse a single play."""
        try:
            play_type_data = play_data.get('type', {})
            play_type_id = play_type_data.get('id', '')
            play_type = get_play_type(play_type_id)
            
            start = play_data.get('start', {})
            
            # Parse timestamp
            timestamp = None
            if play_data.get('wallclock'):
                try:
                    timestamp = date_parser.parse(play_data['wallclock'])
                except Exception:
                    pass
            
            return PlayEvent(
                id=play_data.get('id', ''),
                play_type=play_type,
                description=play_data.get('text', ''),
                down=start.get('down', 1),
                distance=start.get('distance', 10),
                yard_line=start.get('yardLine', 50),
                yards_gained=play_data.get('statYardage', 0),
                is_scoring=play_data.get('scoringPlay', False),
                is_turnover=play_type in ['pass_interception', 'fumble_lost'],
                is_penalty=play_type == 'penalty',
                timestamp=timestamp
            )
            
        except Exception as e:
            logger.error(f"Error parsing play: {e}")
            return None

    def _parse_current_drive(self, drives_data: Dict[str, Any]) -> Optional[DriveInfo]:
        """Parse current drive information."""
        current = drives_data.get('current', {})
        if not current:
            return None
        
        plays = []
        for play in current.get('plays', []):
            parsed = self._parse_play(play)
            if parsed:
                plays.append(parsed)
        
        return DriveInfo(
            id=current.get('id', ''),
            start_yard_line=current.get('start', {}).get('yardLine', 25),
            start_quarter=current.get('start', {}).get('period', 1),
            plays=plays,
            result=current.get('result'),
            yards=current.get('yards', 0),
            time_elapsed=current.get('timeElapsed', {}).get('displayValue')
        )

    def _map_status(self, state: str) -> str:
        """Map ESPN status state to our status."""
        mapping = {
            'pre': 'pre',
            'in': 'in',
            'post': 'post',
        }
        return mapping.get(state, 'pre')

    def _is_two_minute_warning(self, clock: str, period: int) -> bool:
        """Check if we're at the two-minute warning."""
        if period not in [2, 4]:
            return False
        
        try:
            parts = clock.split(':')
            minutes = int(parts[0])
            seconds = int(parts[1]) if len(parts) > 1 else 0
            total_seconds = minutes * 60 + seconds
            return total_seconds <= 120 and total_seconds >= 115
        except Exception:
            return False

