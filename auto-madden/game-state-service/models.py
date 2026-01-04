"""
Data models for Auto-Madden Game State Service.

These models represent the game state as parsed from ESPN API responses.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class TeamInfo:
    """Information about a team in the game."""
    id: str
    name: str
    abbreviation: str
    score: int = 0
    record: Optional[str] = None
    ranking: Optional[int] = None  # For college teams

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class PlayEvent:
    """A single play in the game."""
    id: str
    play_type: str  # rush, pass_complete, pass_incomplete, sack, etc.
    description: str
    down: int
    distance: int
    yard_line: int
    yards_gained: int = 0
    is_scoring: bool = False
    is_turnover: bool = False
    is_penalty: bool = False
    timestamp: Optional[datetime] = None
    
    # Player involvement (when parseable)
    passer: Optional[str] = None
    rusher: Optional[str] = None
    receiver: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        if self.timestamp:
            result['timestamp'] = self.timestamp.isoformat()
        return result


@dataclass
class DriveInfo:
    """Information about a drive."""
    id: str
    start_yard_line: int
    start_quarter: int
    plays: List[PlayEvent] = field(default_factory=list)
    result: Optional[str] = None  # TD, FG, punt, turnover, downs, endOfHalf
    yards: int = 0
    time_elapsed: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'start_yard_line': self.start_yard_line,
            'start_quarter': self.start_quarter,
            'plays': [p.to_dict() for p in self.plays],
            'result': self.result,
            'yards': self.yards,
            'time_elapsed': self.time_elapsed
        }


@dataclass
class GameState:
    """Complete state of an NFL game."""
    game_id: str
    status: str  # pre, in, halftime, post
    
    # Current situation
    quarter: int = 1
    clock: str = "15:00"
    clock_running: bool = False
    down: int = 1
    distance: int = 10
    yard_line: int = 25
    possession_team: Optional[str] = None
    is_red_zone: bool = False
    is_two_minute_warning: bool = False
    
    # Teams
    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None
    
    # Timeouts
    home_timeouts: int = 3
    away_timeouts: int = 3
    
    # Win probability
    home_win_probability: float = 50.0
    away_win_probability: float = 50.0
    
    # Plays and drives
    recent_plays: List[PlayEvent] = field(default_factory=list)
    current_drive: Optional[DriveInfo] = None
    
    # Metadata
    game_name: str = ""
    short_name: str = ""
    broadcast_network: Optional[str] = None
    venue: Optional[str] = None
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'game_id': self.game_id,
            'status': self.status,
            'quarter': self.quarter,
            'clock': self.clock,
            'clock_running': self.clock_running,
            'down': self.down,
            'distance': self.distance,
            'yard_line': self.yard_line,
            'possession_team': self.possession_team,
            'is_red_zone': self.is_red_zone,
            'is_two_minute_warning': self.is_two_minute_warning,
            'home_team': self.home_team.to_dict() if self.home_team else None,
            'away_team': self.away_team.to_dict() if self.away_team else None,
            'home_timeouts': self.home_timeouts,
            'away_timeouts': self.away_timeouts,
            'home_win_probability': self.home_win_probability,
            'away_win_probability': self.away_win_probability,
            'recent_plays': [p.to_dict() for p in self.recent_plays],
            'current_drive': self.current_drive.to_dict() if self.current_drive else None,
            'game_name': self.game_name,
            'short_name': self.short_name,
            'broadcast_network': self.broadcast_network,
            'venue': self.venue,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

    @property
    def home_score(self) -> int:
        """Get home team score."""
        return self.home_team.score if self.home_team else 0

    @property
    def away_score(self) -> int:
        """Get away team score."""
        return self.away_team.score if self.away_team else 0

    @property
    def score_differential(self) -> int:
        """Get absolute score differential."""
        return abs(self.home_score - self.away_score)


@dataclass
class GameChange:
    """Represents a detected change in game state."""
    change_type: str  # new_play, score_change, turnover, quarter_change, etc.
    description: str
    significance: int = 5  # 1-10, higher = more significant
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'change_type': self.change_type,
            'description': self.description,
            'significance': self.significance,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }


# Play type mapping from ESPN type IDs
PLAY_TYPE_MAP = {
    '24': 'rush',
    '67': 'pass_complete',
    '26': 'pass_incomplete',
    '7': 'pass_interception',
    '68': 'sack',
    '36': 'fumble',
    '52': 'fumble_lost',
    '5': 'punt',
    '59': 'field_goal_attempt',
    '60': 'field_goal_made',
    '61': 'field_goal_missed',
    '53': 'extra_point',
    '8': 'penalty',
    '20': 'timeout',
    '22': 'two_minute_warning',
    '23': 'end_of_quarter',
    '6': 'kickoff',
    '29': 'touchdown',
    '76': 'two_point_conversion',
    '999': 'end_game',
    '3': 'end_game',
    '63': 'spike',
    '64': 'kneel',
    '65': 'pass_reception',
}


def get_play_type(espn_type_id: str) -> str:
    """Map ESPN play type ID to readable type."""
    return PLAY_TYPE_MAP.get(espn_type_id, 'unknown')

