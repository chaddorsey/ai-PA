#!/usr/bin/env python3
"""
Auto-Madden Game Simulator.

Replays historical NFL games from ESPN API data at configurable speeds.
This allows testing and development of the companion system without requiring
a live game.

Features:
- Download and cache historical game data
- Replay at configurable speed (1x = real-time, 10x = 10 minutes = 1 minute, etc.)
- Emits events to insight-engine just like game-state-service would
- Can run as a standalone Flask service that mimics game-state-service API

Usage:
    # Download a game for simulation
    python game_simulator.py download 401671495
    
    # List cached games
    python game_simulator.py list
    
    # Simulate a game at 10x speed
    python game_simulator.py run 401671495 --speed 10
    
    # Run as a service (replaces game-state-service for testing)
    python game_simulator.py serve --port 5132
"""

import argparse
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# BREAK DETECTION SYSTEM
# Detects TV timeouts, team timeouts, halftime, and other stoppages
# ============================================================================

class BreakType:
    """Types of game breaks/stoppages."""
    OFFICIAL_TIMEOUT = 'official_timeout'      # TV commercial break
    TEAM_TIMEOUT = 'team_timeout'              # Team-called timeout
    POST_SCORE = 'post_score'                  # Break after scoring play
    TWO_MINUTE_WARNING = 'two_minute_warning'  # 2-minute warning
    QUARTER_BREAK = 'quarter_break'            # Between quarters 1-2, 3-4
    HALFTIME = 'halftime'                      # Halftime break
    INJURY_TIMEOUT = 'injury_timeout'          # Injury stoppage
    CHALLENGE = 'challenge'                    # Coach's challenge/review


# Estimated break durations in seconds (heuristics based on typical NFL timing)
BREAK_DURATIONS = {
    BreakType.OFFICIAL_TIMEOUT: 120,      # ~2 minutes for TV timeout
    BreakType.TEAM_TIMEOUT: 60,           # 30s minimum, often extended
    BreakType.POST_SCORE: 150,            # TD/FG celebration + commercial
    BreakType.TWO_MINUTE_WARNING: 120,    # 2-minute warning break
    BreakType.QUARTER_BREAK: 180,         # ~3 minutes between quarters
    BreakType.HALFTIME: 900,              # ~15 minutes
    BreakType.INJURY_TIMEOUT: 90,         # Variable, ~1.5 min average
    BreakType.CHALLENGE: 180,             # Reviews can take 3+ minutes
}

# Track break state globally for live mode
live_break_active = False
live_break_type = None
live_break_start_time = None


def detect_break_from_play(play_text: str, play_type: str) -> Optional[Dict[str, Any]]:
    """
    Detect if a play indicates a break/stoppage.
    
    Args:
        play_text: The play description text
        play_type: The play type from ESPN (e.g., 'Official Timeout', 'Timeout')
    
    Returns:
        Dict with break info if break detected, None otherwise
    """
    play_text_lower = play_text.lower()
    play_type_lower = play_type.lower() if play_type else ''
    
    # Official Timeout = TV commercial break
    if 'official timeout' in play_type_lower or 'official timeout' in play_text_lower:
        return {
            'break_type': BreakType.OFFICIAL_TIMEOUT,
            'duration': BREAK_DURATIONS[BreakType.OFFICIAL_TIMEOUT],
            'description': 'TV Timeout - Commercial Break',
            'analysis_opportunity': 'extended'  # Good time for deeper analysis
        }
    
    # Team timeout
    if play_type_lower == 'timeout' or ('timeout #' in play_text_lower):
        # Extract team name if possible
        team = None
        if ' by ' in play_text_lower:
            team = play_text.split(' by ')[-1].split(' at ')[0].strip()
        return {
            'break_type': BreakType.TEAM_TIMEOUT,
            'duration': BREAK_DURATIONS[BreakType.TEAM_TIMEOUT],
            'description': f'Team Timeout{" - " + team if team else ""}',
            'team': team,
            'analysis_opportunity': 'brief'
        }
    
    # Two-minute warning
    if 'two-minute warning' in play_text_lower or 'two minute warning' in play_text_lower:
        return {
            'break_type': BreakType.TWO_MINUTE_WARNING,
            'duration': BREAK_DURATIONS[BreakType.TWO_MINUTE_WARNING],
            'description': 'Two-Minute Warning',
            'analysis_opportunity': 'extended'
        }
    
    # Injury timeout
    if 'injury' in play_text_lower and 'timeout' in play_text_lower:
        return {
            'break_type': BreakType.INJURY_TIMEOUT,
            'duration': BREAK_DURATIONS[BreakType.INJURY_TIMEOUT],
            'description': 'Injury Timeout',
            'analysis_opportunity': 'brief'
        }
    
    # Challenge/Review
    if 'challenge' in play_text_lower or 'review' in play_text_lower or 'booth review' in play_text_lower:
        return {
            'break_type': BreakType.CHALLENGE,
            'duration': BREAK_DURATIONS[BreakType.CHALLENGE],
            'description': 'Official Review',
            'analysis_opportunity': 'extended'
        }
    
    return None


def detect_scoring_break(current_state: Dict, previous_state: Dict) -> Optional[Dict[str, Any]]:
    """
    Detect if a score just happened (triggers post-score break).
    """
    if not previous_state:
        return None
    
    curr_total = current_state.get('home_score', 0) + current_state.get('away_score', 0)
    prev_total = previous_state.get('home_score', 0) + previous_state.get('away_score', 0)
    
    if curr_total > prev_total:
        points_scored = curr_total - prev_total
        return {
            'break_type': BreakType.POST_SCORE,
            'duration': BREAK_DURATIONS[BreakType.POST_SCORE],
            'description': f'Post-Score Break ({points_scored} points)',
            'points_scored': points_scored,
            'analysis_opportunity': 'extended'
        }
    
    return None


def detect_quarter_break(current_quarter: int, previous_quarter: int) -> Optional[Dict[str, Any]]:
    """
    Detect quarter changes (halftime is special).
    """
    if current_quarter != previous_quarter:
        if current_quarter == 3 and previous_quarter == 2:
            # Halftime
            return {
                'break_type': BreakType.HALFTIME,
                'duration': BREAK_DURATIONS[BreakType.HALFTIME],
                'description': 'Halftime',
                'analysis_opportunity': 'halftime'  # Maximum analysis opportunity
            }
        elif current_quarter > previous_quarter:
            # Regular quarter break
            return {
                'break_type': BreakType.QUARTER_BREAK,
                'duration': BREAK_DURATIONS[BreakType.QUARTER_BREAK],
                'description': f'End of Quarter {previous_quarter}',
                'new_quarter': current_quarter,
                'analysis_opportunity': 'extended'
            }
    
    return None


# Configuration
ESPN_BASE_URL = "http://site.api.espn.com/apis/site/v2/sports/football/nfl"
CACHE_DIR = Path(__file__).parent / "cached_games"
INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', 'http://localhost:5131')

# Ensure cache directory exists
CACHE_DIR.mkdir(exist_ok=True)


class GameData:
    """Parsed game data ready for simulation."""
    
    def __init__(self, raw_data: Dict[str, Any]):
        """Initialize from raw ESPN API data."""
        self.raw = raw_data
        self.game_id = self._extract_game_id()
        self.home_team = self._extract_team('home')
        self.away_team = self._extract_team('away')
        self.plays = self._extract_plays()
        self.win_probability = self._extract_win_prob()
        self.scoring_plays = raw_data.get('scoringPlays', [])
        # Build a lookup for score at each scoring play
        self.scoring_play_scores = self._build_scoring_lookup()
        
    def _extract_game_id(self) -> str:
        """Extract game ID from header."""
        header = self.raw.get('header', {})
        return header.get('id', '')
    
    def _extract_team(self, home_away: str) -> Dict[str, Any]:
        """Extract team info."""
        header = self.raw.get('header', {})
        comps = header.get('competitions', [{}])
        if not comps:
            return {}
        
        for comp in comps[0].get('competitors', []):
            if comp.get('homeAway') == home_away:
                team = comp.get('team', {})
                return {
                    'id': team.get('id', ''),
                    'name': team.get('displayName', ''),
                    'abbreviation': team.get('abbreviation', ''),
                    'score': int(comp.get('score', 0))
                }
        return {}
    
    def _extract_plays(self) -> List[Dict[str, Any]]:
        """Extract all plays in chronological order with timestamps."""
        plays = []
        drives = self.raw.get('drives', {}).get('previous', [])
        
        for drive in drives:
            for play in drive.get('plays', []):
                wallclock = play.get('wallclock')
                if wallclock:
                    try:
                        play['_timestamp'] = date_parser.parse(wallclock)
                    except Exception:
                        play['_timestamp'] = None
                else:
                    play['_timestamp'] = None
                
                play['_drive_id'] = drive.get('id')
                play['_drive_result'] = drive.get('result')
                plays.append(play)
        
        # Sort by timestamp
        plays_with_ts = [p for p in plays if p.get('_timestamp')]
        plays_without_ts = [p for p in plays if not p.get('_timestamp')]
        
        plays_with_ts.sort(key=lambda p: p['_timestamp'])
        
        return plays_with_ts + plays_without_ts
    
    def _extract_win_prob(self) -> Dict[str, float]:
        """Extract win probability by play ID."""
        wp = {}
        for entry in self.raw.get('winprobability', []):
            play_id = str(entry.get('playId', ''))
            if play_id:
                wp[play_id] = entry.get('homeWinPercentage', 0.5)
        return wp
    
    def _build_scoring_lookup(self) -> Dict[str, Dict[str, int]]:
        """Build lookup of scores at each scoring play."""
        lookup = {}
        for sp in self.scoring_plays:
            play_id = str(sp.get('id', ''))
            if play_id:
                lookup[play_id] = {
                    'home_score': sp.get('homeScore', 0),
                    'away_score': sp.get('awayScore', 0)
                }
        return lookup
    
    @property
    def game_name(self) -> str:
        """Get game name."""
        return f"{self.away_team.get('name', 'Away')} at {self.home_team.get('name', 'Home')}"
    
    @property
    def short_name(self) -> str:
        """Get short game name."""
        return f"{self.away_team.get('abbreviation', 'AWAY')} @ {self.home_team.get('abbreviation', 'HOME')}"
    
    @property
    def final_score(self) -> str:
        """Get final score."""
        return f"{self.home_team.get('abbreviation')} {self.home_team.get('score')}, {self.away_team.get('abbreviation')} {self.away_team.get('score')}"
    
    @property 
    def total_plays(self) -> int:
        """Total number of plays."""
        return len(self.plays)
    
    @property
    def game_duration(self) -> Optional[timedelta]:
        """Actual game duration from first to last play."""
        if len(self.plays) < 2:
            return None
        
        first_ts = self.plays[0].get('_timestamp')
        last_ts = self.plays[-1].get('_timestamp')
        
        if first_ts and last_ts:
            return last_ts - first_ts
        return None


class GameSimulator:
    """Simulates a historical game by replaying plays at configurable speed."""
    
    def __init__(self, game_data: GameData, speed: float = 1.0):
        """
        Initialize simulator.
        
        Args:
            game_data: Parsed game data
            speed: Playback speed multiplier (1.0 = real-time, 10.0 = 10x faster)
        """
        self.game = game_data
        self.speed = speed
        self.current_play_index = 0
        self.running = False
        self.paused = False
        self._thread: Optional[threading.Thread] = None
        
        # Current simulated state
        self.current_state: Dict[str, Any] = {}
        self.home_score = 0
        self.away_score = 0
        
        # Callbacks
        self.on_play: Optional[callable] = None
        self.on_score: Optional[callable] = None
        self.on_state_change: Optional[callable] = None
    
    def reset(self):
        """Reset simulation to beginning."""
        self.current_play_index = 0
        self.home_score = 0
        self.away_score = 0
        self.current_state = self._build_initial_state()
    
    def _build_initial_state(self) -> Dict[str, Any]:
        """Build initial game state."""
        # Copy team data but reset scores to 0
        home_team = dict(self.game.home_team)
        away_team = dict(self.game.away_team)
        home_team['score'] = 0
        away_team['score'] = 0
        
        return {
            'game_id': self.game.game_id,
            'status': 'in',
            'quarter': 1,
            'clock': '15:00',
            'clock_running': False,
            'down': 1,
            'distance': 10,
            'yard_line': 25,
            'possession_team': None,
            'is_red_zone': False,
            'is_two_minute_warning': False,
            'home_team': home_team,
            'away_team': away_team,
            'home_timeouts': 3,
            'away_timeouts': 3,
            'home_win_probability': 50.0,
            'away_win_probability': 50.0,
            'recent_plays': [],
            'short_name': self.game.short_name,
            'game_name': self.game.game_name
        }
    
    def _update_state_from_play(self, play: Dict[str, Any]):
        """Update current state based on a play."""
        start = play.get('start', {})
        end = play.get('end', {})
        
        # Update from play end state
        self.current_state['down'] = end.get('down', start.get('down', 1))
        self.current_state['distance'] = end.get('distance', start.get('distance', 10))
        self.current_state['yard_line'] = end.get('yardLine', start.get('yardLine', 50))
        
        # Determine quarter from drive
        period = play.get('period', {})
        if isinstance(period, dict):
            self.current_state['quarter'] = period.get('number', 1)
        elif isinstance(period, int):
            self.current_state['quarter'] = period
        
        # Clock from play
        clock = play.get('clock', {})
        if isinstance(clock, dict):
            self.current_state['clock'] = clock.get('displayValue', '15:00')
        
        # Red zone check
        yards_to_endzone = end.get('yardsToEndzone', 100)
        self.current_state['is_red_zone'] = yards_to_endzone <= 20
        
        # Win probability
        play_id = str(play.get('id', ''))
        if play_id in self.game.win_probability:
            home_wp = self.game.win_probability[play_id] * 100
            self.current_state['home_win_probability'] = home_wp
            self.current_state['away_win_probability'] = 100 - home_wp
        
        # Add to recent plays
        recent = self.current_state.get('recent_plays', [])
        recent.insert(0, {
            'id': play.get('id'),
            'type': play.get('type', {}).get('text', 'Unknown'),
            'description': play.get('text', ''),
            'yards_gained': play.get('statYardage', 0),
            'is_scoring': play.get('scoringPlay', False),
            'down': start.get('down', 1),
            'distance': start.get('distance', 10)
        })
        self.current_state['recent_plays'] = recent[:20]
        
        # Check for scoring and update score
        if play.get('scoringPlay'):
            play_id = str(play.get('id', ''))
            if play_id in self.game.scoring_play_scores:
                scores = self.game.scoring_play_scores[play_id]
                self.home_score = scores['home_score']
                self.away_score = scores['away_score']
                self.current_state['home_team']['score'] = self.home_score
                self.current_state['away_team']['score'] = self.away_score
                logger.info(f"SCORE UPDATE: {self.current_state['away_team']['abbreviation']} {self.away_score} - {self.current_state['home_team']['abbreviation']} {self.home_score}")
    
    def run(self):
        """Run simulation in foreground."""
        # Don't reset if we have a specific start index
        if self.current_play_index == 0:
            self.reset()
        else:
            self.current_state = self._build_initial_state()
        self.running = True
        
        logger.info(f"Starting simulation: {self.game.game_name}")
        logger.info(f"Total plays: {self.game.total_plays}")
        logger.info(f"Speed: {self.speed}x")
        
        if self.game.game_duration:
            real_duration = self.game.game_duration / self.speed
            logger.info(f"Estimated simulation duration: {real_duration}")
        
        last_timestamp = None
        
        # Start from current_play_index (may be set externally)
        start_index = self.current_play_index
        logger.info(f"Starting from play {start_index + 1}/{self.game.total_plays}")
        
        for i, play in enumerate(self.game.plays[start_index:], start=start_index):
            if not self.running:
                break
            
            while self.paused:
                time.sleep(0.1)
            
            self.current_play_index = i
            
            # Calculate delay based on timestamps
            current_ts = play.get('_timestamp')
            if last_timestamp and current_ts:
                real_delay = (current_ts - last_timestamp).total_seconds()
                sim_delay = real_delay / self.speed
                
                # Cap delay to avoid very long waits
                sim_delay = min(sim_delay, 30.0)
                
                if sim_delay > 0.1:
                    time.sleep(sim_delay)
            else:
                # Default delay between plays
                time.sleep(1.0 / self.speed)
            
            last_timestamp = current_ts
            
            # Update state
            self._update_state_from_play(play)
            
            # Callbacks
            if self.on_play:
                self.on_play(play, self.current_state)
            
            if self.on_state_change:
                self.on_state_change(self.current_state)
            
            # Log progress periodically
            if i % 20 == 0:
                logger.info(f"Play {i+1}/{self.game.total_plays}: Q{self.current_state['quarter']} - {self.current_state['clock']}")
        
        self.running = False
        self.current_state['status'] = 'post'
        logger.info(f"Simulation complete. Final: {self.game.final_score}")
    
    def start(self):
        """Start simulation in background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Simulation already running")
            return
        
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop simulation."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def pause(self):
        """Pause simulation."""
        self.paused = True
    
    def resume(self):
        """Resume simulation."""
        self.paused = False


def download_game(game_id: str) -> Optional[Path]:
    """
    Download game data from ESPN and cache locally.
    
    Args:
        game_id: ESPN game ID
        
    Returns:
        Path to cached file or None if failed.
    """
    cache_file = CACHE_DIR / f"{game_id}.json"
    
    if cache_file.exists():
        logger.info(f"Game {game_id} already cached at {cache_file}")
        return cache_file
    
    logger.info(f"Downloading game {game_id} from ESPN...")
    
    try:
        response = requests.get(
            f"{ESPN_BASE_URL}/summary",
            params={'event': game_id},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        # Validate we got useful data
        drives = data.get('drives', {}).get('previous', [])
        if not drives:
            logger.error("No drive data found - game may not be complete")
            return None
        
        total_plays = sum(len(d.get('plays', [])) for d in drives)
        logger.info(f"Downloaded {len(drives)} drives, {total_plays} plays")
        
        # Cache the data
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Cached to {cache_file}")
        return cache_file
        
    except Exception as e:
        logger.error(f"Failed to download game: {e}")
        return None


def load_game(game_id: str) -> Optional[GameData]:
    """Load game data from cache."""
    cache_file = CACHE_DIR / f"{game_id}.json"
    
    if not cache_file.exists():
        logger.error(f"Game {game_id} not in cache. Run 'download {game_id}' first.")
        return None
    
    with open(cache_file, 'r') as f:
        raw_data = json.load(f)
    
    return GameData(raw_data)


def list_cached_games():
    """List all cached games."""
    games = [g for g in CACHE_DIR.glob("*.json") if not g.name.startswith('._')]
    
    if not games:
        print("No cached games. Use 'download <game_id>' to cache a game.")
        return
    
    print(f"\nCached Games ({len(games)}):")
    print("-" * 60)
    
    for game_file in sorted(games):
        game_id = game_file.stem
        try:
            game = load_game(game_id)
            if game:
                duration = game.game_duration
                duration_str = str(duration).split('.')[0] if duration else "N/A"
                print(f"  {game_id}: {game.game_name}")
                print(f"           {game.total_plays} plays, {duration_str} duration")
                print(f"           Final: {game.final_score}")
                print()
        except Exception as e:
            print(f"  {game_id}: Error loading - {e}")


def find_recent_games(date_str: str = None) -> List[Dict[str, Any]]:
    """Find completed games from ESPN scoreboard."""
    if date_str:
        url = f"{ESPN_BASE_URL}/scoreboard?dates={date_str}"
    else:
        url = f"{ESPN_BASE_URL}/scoreboard"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = []
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {})
            if status.get('state') == 'post':
                comps = event.get('competitions', [{}])[0].get('competitors', [])
                home = next((c for c in comps if c.get('homeAway') == 'home'), {})
                away = next((c for c in comps if c.get('homeAway') == 'away'), {})
                
                games.append({
                    'id': event.get('id'),
                    'name': event.get('name'),
                    'date': event.get('date'),
                    'home_score': home.get('score'),
                    'away_score': away.get('score')
                })
        
        return games
        
    except Exception as e:
        logger.error(f"Failed to fetch games: {e}")
        return []


def find_play_by_game_time(game: GameData, quarter: int = None, clock: str = None) -> int:
    """
    Find play index closest to specified game time.
    
    Args:
        game: GameData object
        quarter: Quarter number (1-4)
        clock: Game clock string (e.g., "12:30", "5:00")
        
    Returns:
        Index of the closest play.
    """
    if not quarter and not clock:
        return 0
    
    target_quarter = int(quarter) if quarter else 1
    
    # Parse target clock to seconds remaining in quarter
    target_seconds = 900  # 15:00 default
    if clock:
        try:
            parts = clock.replace(' ', '').split(':')
            minutes = int(parts[0])
            seconds = int(parts[1]) if len(parts) > 1 else 0
            target_seconds = minutes * 60 + seconds
        except Exception:
            pass
    
    best_index = 0
    best_diff = float('inf')
    
    for i, play in enumerate(game.plays):
        # Get play's quarter
        period = play.get('period', {})
        if isinstance(period, dict):
            play_quarter = period.get('number', 1)
        else:
            play_quarter = 1
        
        # Get play's clock
        play_clock = play.get('clock', {})
        if isinstance(play_clock, dict):
            clock_str = play_clock.get('displayValue', '15:00')
        else:
            clock_str = '15:00'
        
        try:
            parts = clock_str.split(':')
            play_seconds = int(parts[0]) * 60 + int(parts[1])
        except Exception:
            play_seconds = 900
        
        # Calculate difference (quarter difference * 900 + clock difference)
        quarter_diff = abs(play_quarter - target_quarter) * 900
        clock_diff = abs(play_seconds - target_seconds)
        total_diff = quarter_diff + clock_diff
        
        # Prefer plays at or after the target time
        if play_quarter > target_quarter or (play_quarter == target_quarter and play_seconds <= target_seconds):
            total_diff -= 1  # Slight preference for "at or after"
        
        if total_diff < best_diff:
            best_diff = total_diff
            best_index = i
    
    return best_index


def emit_to_insight_engine(state: Dict[str, Any], change_type: str, description: str, data: Dict[str, Any] = None):
    """Emit a state change to the insight engine."""
    try:
        payload = {
            'change': {
                'change_type': change_type,
                'description': description,
                'significance': 5,
                'data': data or {}
            },
            'state': state
        }
        
        logger.info(f"Emitting event: {change_type} - {description[:50]}...")
        
        response = requests.post(
            f"{INSIGHT_ENGINE_URL}/event",
            json=payload,
            timeout=5
        )
        
        if response.status_code != 200:
            logger.warning(f"Failed to emit to insight engine: {response.status_code}")
            
    except Exception as e:
        logger.debug(f"Could not emit to insight engine: {e}")


def run_simulation(game_id: str, speed: float = 1.0, emit_events: bool = True):
    """Run a game simulation."""
    game = load_game(game_id)
    if not game:
        return
    
    sim = GameSimulator(game, speed=speed)
    
    if emit_events:
        def on_play(play, state):
            description = play.get('text', 'Play occurred')
            emit_to_insight_engine(state, 'new_play', description)
        
        sim.on_play = on_play
    
    print(f"\n{'=' * 60}")
    print(f"SIMULATION: {game.game_name}")
    print(f"{'=' * 60}")
    print(f"Plays: {game.total_plays}")
    print(f"Speed: {speed}x")
    print(f"Final Score: {game.final_score}")
    print(f"{'=' * 60}\n")
    
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\nSimulation stopped by user")
        sim.stop()


# Flask service for drop-in replacement of game-state-service
from flask import Flask, jsonify, request

flask_app = Flask(__name__)

# Enable CORS for cross-origin requests from the UI
@flask_app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response
current_simulator: Optional[GameSimulator] = None


@flask_app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'auto-madden-simulator',
        'mode': 'simulation',
        'simulation_active': current_simulator.running if current_simulator else False
    })


@flask_app.route('/games')
def list_games_api():
    """List cached games available for simulation."""
    games = []
    for game_file in [g for g in CACHE_DIR.glob("*.json") if not g.name.startswith('._')]:
        game_id = game_file.stem
        try:
            game = load_game(game_id)
            if game:
                games.append({
                    'game_id': game_id,
                    'name': game.game_name,
                    'short_name': game.short_name,
                    'status': 'cached',
                    'home_team': game.home_team,
                    'away_team': game.away_team
                })
        except Exception:
            pass
    
    return jsonify({'status': 'ok', 'games': games, 'count': len(games)})


@flask_app.route('/start', methods=['POST'])
def start_simulation_api():
    """Start a simulation.
    
    POST body:
        game_id: ESPN game ID (optional, uses first cached if not provided)
        speed: Playback speed multiplier (default: 1.0 for real-time sync)
        start_quarter: Quarter to start from (1-4, optional)
        start_clock: Game clock to start from (e.g., "12:30", optional)
    """
    global current_simulator
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    speed = float(data.get('speed', 1.0))  # Default to real-time for video sync
    start_quarter = data.get('start_quarter')
    start_clock = data.get('start_clock')
    
    if not game_id:
        # Find first cached game
        games = list(CACHE_DIR.glob("*.json"))
        if games:
            game_id = games[0].stem
        else:
            return jsonify({'status': 'error', 'message': 'No cached games available'}), 404
    
    game = load_game(game_id)
    if not game:
        return jsonify({'status': 'error', 'message': f'Game {game_id} not found'}), 404
    
    if current_simulator and current_simulator.running:
        current_simulator.stop()
    
    current_simulator = GameSimulator(game, speed=speed)
    
    # Jump to specific game time if requested
    start_play_index = 0
    if start_quarter or start_clock:
        start_play_index = find_play_by_game_time(game, start_quarter, start_clock)
        current_simulator.current_play_index = start_play_index
        logger.info(f"Starting from play {start_play_index} (Q{start_quarter} {start_clock})")
    
    def on_play(play, state):
        description = play.get('text', 'Play occurred')
        play_type = play.get('type', {}).get('text', '').lower()
        yards = play.get('statYardage', 0)
        
        # Determine the most specific event type
        if play.get('scoringPlay'):
            emit_to_insight_engine(state, 'score_change', description)
        elif 'fumble' in play_type or 'interception' in play_type or 'fumble' in description.lower() or 'intercepted' in description.lower():
            emit_to_insight_engine(state, 'turnover', description)
        elif yards >= 15:
            # Emit big play with yards data
            emit_to_insight_engine(state, 'big_play', description, {'yards': yards})
        elif state.get('is_red_zone') and not getattr(on_play, '_was_red_zone', False):
            emit_to_insight_engine(state, 'red_zone_entry', description)
        else:
            emit_to_insight_engine(state, 'new_play', description)
        
        # Track red zone state for entry detection
        on_play._was_red_zone = state.get('is_red_zone', False)
        
        # Check for two-minute warning
        clock = state.get('clock', '15:00')
        quarter = state.get('quarter', 1)
        if clock and quarter in [2, 4]:
            try:
                mins, secs = clock.split(':')
                total_secs = int(mins) * 60 + int(secs)
                if total_secs <= 120 and not getattr(on_play, f'_2min_q{quarter}', False):
                    emit_to_insight_engine(state, 'two_minute_warning', f'Two-minute warning, Q{quarter}', {'quarter': quarter})
                    setattr(on_play, f'_2min_q{quarter}', True)
            except:
                pass
    
    on_play._was_red_zone = False
    current_simulator.on_play = on_play
    current_simulator.start()
    
    return jsonify({
        'status': 'ok',
        'message': f'Simulation started: {game.short_name} at {speed}x speed',
        'game': {
            'game_id': game_id,
            'name': game.game_name,
            'short_name': game.short_name,
            'status': 'in'
        },
        'starting_play': start_play_index,
        'total_plays': game.total_plays
    })


@flask_app.route('/stop', methods=['POST'])
def stop_simulation_api():
    """Stop current simulation."""
    global current_simulator
    
    if current_simulator:
        current_simulator.stop()
        current_simulator = None
    
    return jsonify({'status': 'ok', 'message': 'Simulation stopped'})


@flask_app.route('/refresh', methods=['POST'])
def refresh_live_game():
    """Refresh live game data from ESPN (for live games)."""
    global current_simulator
    
    if not current_simulator:
        return jsonify({'status': 'error', 'message': 'No simulation running'}), 404
    
    game_id = current_simulator.game.game_id
    old_play_count = current_simulator.game.total_plays
    current_index = current_simulator.current_play_index
    
    logger.info(f"Refreshing live game {game_id}...")
    
    try:
        # Delete cache to force re-download
        cache_file = CACHE_DIR / f"{game_id}.json"
        if cache_file.exists():
            cache_file.unlink()
        
        # Download fresh data
        download_game(game_id)
        
        # Load the refreshed game
        new_game = load_game(game_id)
        if not new_game:
            return jsonify({'status': 'error', 'message': 'Failed to refresh game data'}), 500
        
        new_play_count = new_game.total_plays
        
        # Update the simulator's game data while keeping position
        current_simulator.game = new_game
        
        # Rebuild state if we have new plays
        if new_play_count > old_play_count:
            logger.info(f"Found {new_play_count - old_play_count} new plays")
        
        return jsonify({
            'status': 'ok',
            'message': f'Refreshed: {old_play_count} -> {new_play_count} plays',
            'old_plays': old_play_count,
            'new_plays': new_play_count,
            'current_index': current_index
        })
    
    except Exception as e:
        logger.error(f"Error refreshing game: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@flask_app.route('/pause', methods=['POST'])
def pause_simulation_api():
    """Pause current simulation."""
    if current_simulator and current_simulator.running:
        current_simulator.pause()
        return jsonify({'status': 'ok', 'message': 'Simulation paused'})
    return jsonify({'status': 'error', 'message': 'No simulation running'}), 404


@flask_app.route('/resume', methods=['POST'])
def resume_simulation_api():
    """Resume paused simulation."""
    if current_simulator and current_simulator.paused:
        current_simulator.resume()
        return jsonify({'status': 'ok', 'message': 'Simulation resumed'})
    return jsonify({'status': 'error', 'message': 'No paused simulation'}), 404


@flask_app.route('/speed', methods=['POST'])
def set_speed_api():
    """Change simulation speed."""
    if not current_simulator:
        return jsonify({'status': 'error', 'message': 'No simulation running'}), 404
    
    data = request.get_json() or {}
    new_speed = float(data.get('speed', 1.0))
    current_simulator.speed = new_speed
    
    return jsonify({
        'status': 'ok', 
        'message': f'Speed set to {new_speed}x',
        'speed': new_speed
    })


@flask_app.route('/jump', methods=['POST'])
def jump_to_time_api():
    """Jump to a specific game time."""
    global current_simulator
    
    if not current_simulator:
        return jsonify({'status': 'error', 'message': 'No simulation running'}), 404
    
    data = request.get_json() or {}
    quarter = data.get('quarter')
    clock = data.get('clock')
    
    if not quarter and not clock:
        return jsonify({'status': 'error', 'message': 'Provide quarter and/or clock'}), 400
    
    # Find the play
    play_index = find_play_by_game_time(current_simulator.game, quarter, clock)
    current_simulator.current_play_index = play_index
    
    # Update state to match that point
    if play_index < len(current_simulator.game.plays):
        play = current_simulator.game.plays[play_index]
        current_simulator._update_state_from_play(play)
    
    return jsonify({
        'status': 'ok',
        'message': f'Jumped to play {play_index + 1}',
        'play_index': play_index,
        'total_plays': current_simulator.game.total_plays
    })


@flask_app.route('/state')
def get_state_api():
    """Get current simulation state."""
    if not current_simulator or not current_simulator.running:
        return jsonify({'status': 'error', 'message': 'No simulation running'}), 404
    
    return jsonify({
        'status': 'ok',
        'state': current_simulator.current_state
    })


@flask_app.route('/summary')
def get_summary_api():
    """Get simulation summary."""
    if not current_simulator:
        return jsonify({'status': 'error', 'message': 'No simulation running'}), 404
    
    return jsonify({
        'status': 'ok',
        'summary': {
            'game_name': current_simulator.game.short_name,
            'current_score': f"{current_simulator.current_state.get('home_team', {}).get('abbreviation', 'HOME')} vs {current_simulator.current_state.get('away_team', {}).get('abbreviation', 'AWAY')}",
            'quarter': current_simulator.current_state.get('quarter', 1),
            'clock': current_simulator.current_state.get('clock', '15:00'),
            'progress': f"{current_simulator.current_play_index + 1}/{current_simulator.game.total_plays}",
            'key_moments': [],
            'drives_summary': [],
            'momentum': ''
        }
    })


# Live polling state
live_game_id: Optional[str] = None
live_polling: bool = False
live_last_state: Optional[Dict[str, Any]] = None
live_poll_thread: Optional[threading.Thread] = None

# Sportradar live polling (for future use)
sportradar_game_id: Optional[str] = None
sportradar_polling: bool = False
sportradar_last_play_id: Optional[str] = None


# ============== ESPN LIVE MODE ==============

# Global state for live mode
live_game_id = None
live_polling = False
live_last_state = None
live_poll_thread = None
live_pregame_triggered = False  # Track if pregame insights have been sent


def fetch_espn_live_state(game_id: str) -> Optional[Dict[str, Any]]:
    """Fetch current game state from ESPN."""
    import requests
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        resp = requests.get(url, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        for event in data.get('events', []):
            if event.get('id') == game_id:
                comp = event.get('competitions', [{}])[0]
                status = event.get('status', {})
                situation = comp.get('situation', {})
                
                home = None
                away = None
                for team in comp.get('competitors', []):
                    if team.get('homeAway') == 'home':
                        home = team
                    else:
                        away = team
                
                # Build team dicts in the format the insight engine expects
                home_team_dict = {
                    'abbreviation': home.get('team', {}).get('abbreviation', 'HOME') if home else 'HOME',
                    'score': int(home.get('score', 0)) if home else 0
                }
                away_team_dict = {
                    'abbreviation': away.get('team', {}).get('abbreviation', 'AWAY') if away else 'AWAY',
                    'score': int(away.get('score', 0)) if away else 0
                }
                
                # Handle pre-game status
                status_type = status.get('type', {})
                status_name = status_type.get('name', '')
                status_desc = status_type.get('description', 'Unknown')
                is_pregame = status_name in ['STATUS_SCHEDULED', 'STATUS_PREGAME']
                
                # For pre-game, period may be 0 or undefined
                quarter = status.get('period', 0)
                if is_pregame:
                    quarter = 0  # Explicitly 0 for pre-game
                
                return {
                    'game_id': game_id,
                    'quarter': quarter,
                    'clock': status.get('displayClock', '15:00') if not is_pregame else 'Pre-Game',
                    'home_team': home_team_dict,
                    'away_team': away_team_dict,
                    'home_score': home_team_dict['score'],
                    'away_score': away_team_dict['score'],
                    'down': situation.get('down'),
                    'distance': situation.get('distance'),
                    'yard_line': situation.get('yardLine'),
                    'possession': situation.get('possession'),
                    'down_distance_text': situation.get('downDistanceText', ''),
                    'last_play': situation.get('lastPlay', {}).get('text', ''),
                    'is_red_zone': situation.get('isRedZone', False),
                    'status': status_desc,
                    'status_name': status_name,
                    'short_detail': status_type.get('shortDetail', ''),
                    'is_pregame': is_pregame,
                    'kickoff_time': status.get('date', '') if is_pregame else None
                }
        return None
    except Exception as e:
        logger.error(f"Error fetching ESPN state: {e}")
        return None


def live_poll_loop(game_id: str, poll_interval: int = 15):
    """Background thread that polls ESPN and emits events."""
    global live_polling, live_last_state
    
    import requests
    insight_url = "http://localhost:5131/event"
    
    logger.info(f"Starting live ESPN polling for game {game_id} every {poll_interval}s")
    poll_count = 0
    
    while live_polling:
        try:
            poll_count += 1
            state = fetch_espn_live_state(game_id)
            
            # Always log to help debug
            logger.info(f"📊 Poll #{poll_count}: state={'OK' if state else 'None'}, has_prev={live_last_state is not None}")
            
            if state:
                if poll_count % 3 == 0:  # Log every 3rd poll
                    logger.info(f"📊 Poll #{poll_count}: {state.get('down_distance_text')} | {state.get('last_play', '')[:30]}...")
            
            # Check for changes
            if live_last_state:
                # Score change?
                if (state['home_score'] != live_last_state['home_score'] or 
                    state['away_score'] != live_last_state['away_score']):
                    event = {
                        'event_type': 'score_change',
                        'state': state,
                        'previous_score': {
                            'home': live_last_state['home_score'],
                            'away': live_last_state['away_score']
                        }
                    }
                    try:
                        requests.post(insight_url, json=event, timeout=5)
                        logger.info(f"📢 Score change: {state['away_team']['abbreviation']} {state['away_score']} - {state['home_team']['abbreviation']} {state['home_score']}")
                    except Exception as e:
                        logger.error(f"Failed to send event: {e}")
                
                # Quarter change?
                elif state['quarter'] != live_last_state['quarter']:
                    event = {
                        'event_type': 'quarter_change',
                        'state': state,
                        'new_quarter': state['quarter']
                    }
                    try:
                        requests.post(insight_url, json=event, timeout=5)
                        logger.info(f"📢 Quarter {state['quarter']} starting")
                    except Exception as e:
                        logger.error(f"Failed to send event: {e}")
                
                # New play (down changed, distance changed, or last_play changed)?
                # Use separate if (not elif) so this always runs
                play_changed = (state['down'] != live_last_state.get('down') or 
                    state['down_distance_text'] != live_last_state.get('down_distance_text') or
                    state['last_play'] != live_last_state.get('last_play'))
                
                if play_changed:
                    event = {
                        'event_type': 'new_play',
                        'state': state,
                        'play_description': state['last_play']
                    }
                    logger.info(f"🎯 SENDING EVENT: new_play to {insight_url}")
                    try:
                        resp = requests.post(insight_url, json=event, timeout=5)
                        logger.info(f"📢 Sent new_play, response: {resp.status_code}, body: {resp.text[:100]}")
                    except Exception as e:
                        logger.error(f"❌ Failed to send event: {e}")
                
                # Red zone entry?
                if state['is_red_zone'] and not live_last_state.get('is_red_zone'):
                    event = {
                        'event_type': 'red_zone_entry',
                        'state': state
                    }
                    try:
                        requests.post(insight_url, json=event, timeout=5)
                        logger.info(f"📢 RED ZONE!")
                    except Exception as e:
                        logger.error(f"Failed to send event: {e}")
                
                # ============================================================
                # BREAK DETECTION - Detect stoppages for deeper analysis
                # ============================================================
                global live_break_active, live_break_type, live_break_start_time
                
                break_info = None
                
                # Check for break from play text/type
                if play_changed and state.get('last_play'):
                    # Get play type from the last play
                    play_text = state.get('last_play', '')
                    # Try to detect break from text patterns
                    if 'official timeout' in play_text.lower():
                        break_info = detect_break_from_play(play_text, 'Official Timeout')
                    elif 'timeout #' in play_text.lower() or 'timeout by' in play_text.lower():
                        break_info = detect_break_from_play(play_text, 'Timeout')
                    elif 'two-minute warning' in play_text.lower() or 'two minute warning' in play_text.lower():
                        break_info = detect_break_from_play(play_text, 'Two-Minute Warning')
                    elif 'challenge' in play_text.lower() or 'review' in play_text.lower():
                        break_info = detect_break_from_play(play_text, 'Review')
                
                # Check for scoring break
                if not break_info:
                    break_info = detect_scoring_break(state, live_last_state)
                
                # Check for quarter break
                if not break_info:
                    break_info = detect_quarter_break(
                        state.get('quarter', 1), 
                        live_last_state.get('quarter', 1)
                    )
                
                # If we detected a break, send break_start event
                if break_info and not live_break_active:
                    live_break_active = True
                    live_break_type = break_info['break_type']
                    live_break_start_time = time.time()
                    
                    event = {
                        'event_type': 'break_start',
                        'state': state,
                        'break_info': break_info
                    }
                    try:
                        resp = requests.post(insight_url, json=event, timeout=5)
                        logger.info(f"⏸️ BREAK: {break_info['description']} (~{break_info['duration']}s) - Analysis: {break_info['analysis_opportunity']}")
                        logger.info(f"   Response: {resp.status_code}, insights: {resp.text[:80]}")
                    except Exception as e:
                        logger.error(f"Failed to send break event: {e}")
                
                # Check if break might be over (play resumed)
                elif live_break_active and play_changed:
                    # If it's a real play (not another timeout), break is over
                    play_text = state.get('last_play', '').lower()
                    if not any(x in play_text for x in ['timeout', 'warning', 'review', 'challenge']):
                        elapsed = time.time() - live_break_start_time if live_break_start_time else 0
                        logger.info(f"▶️ BREAK ENDED: {live_break_type} lasted {elapsed:.0f}s")
                        live_break_active = False
                        live_break_type = None
                        live_break_start_time = None
            
            # Debug: Log state comparison
            if live_last_state:
                if state['last_play'] != live_last_state.get('last_play'):
                    logger.info(f"🔍 Play changed: {state['last_play'][:40]}...")
                if state['down_distance_text'] != live_last_state.get('down_distance_text'):
                    logger.info(f"🔍 Situation changed: {state['down_distance_text']}")
            
            live_last_state = state
        
            time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"Error in poll loop: {e}")
            time.sleep(poll_interval)
    
    logger.info("Live polling stopped")


@flask_app.route('/live/espn/games', methods=['GET'])
def get_espn_live_games():
    """Get list of current/in-progress NFL games from ESPN."""
    import requests
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        resp = requests.get(url, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        games = []
        for event in data.get('events', []):
            status = event.get('status', {})
            status_type = status.get('type', {}).get('name', '')
            
            # Include in-progress and scheduled games
            if status_type in ['STATUS_IN_PROGRESS', 'STATUS_HALFTIME', 'STATUS_SCHEDULED', 'STATUS_END_PERIOD']:
                comp = event.get('competitions', [{}])[0]
                home = None
                away = None
                for team in comp.get('competitors', []):
                    if team.get('homeAway') == 'home':
                        home = team
                    else:
                        away = team
                
                games.append({
                    'id': event.get('id'),
                    'name': event.get('shortName'),
                    'home': home.get('team', {}).get('abbreviation') if home else '?',
                    'away': away.get('team', {}).get('abbreviation') if away else '?',
                    'home_score': home.get('score', '0') if home else '0',
                    'away_score': away.get('score', '0') if away else '0',
                    'status': status.get('type', {}).get('shortDetail', ''),
                    'is_live': status_type == 'STATUS_IN_PROGRESS'
                })
        
        response = jsonify({'status': 'ok', 'games': games})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@flask_app.route('/live/espn/start', methods=['POST'])
def start_live_espn():
    """Start live ESPN polling mode."""
    global live_game_id, live_polling, live_last_state, live_poll_thread, live_pregame_triggered
    
    # Stop any existing polling
    live_polling = False
    if live_poll_thread and live_poll_thread.is_alive():
        live_poll_thread.join(timeout=2)
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    poll_interval = data.get('interval', 15)  # seconds between polls
    
    if not game_id:
        # Auto-find first live or upcoming game
        import requests
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            resp = requests.get(url, timeout=10, verify=False)
            data = resp.json()
            
            # First look for in-progress games
            for event in data.get('events', []):
                if event.get('status', {}).get('type', {}).get('name') == 'STATUS_IN_PROGRESS':
                    game_id = event.get('id')
                    logger.info(f"Auto-selected live game: {event.get('shortName')}")
                    break
            
            # If no live games, look for upcoming games (pre-game)
            if not game_id:
                for event in data.get('events', []):
                    status_name = event.get('status', {}).get('type', {}).get('name', '')
                    if status_name in ['STATUS_SCHEDULED', 'STATUS_PREGAME']:
                        game_id = event.get('id')
                        logger.info(f"Auto-selected upcoming game: {event.get('shortName')}")
                        break
                        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Could not find games: {e}'}), 500
        
        if not game_id:
            return jsonify({'status': 'error', 'message': 'No live or upcoming games found'}), 404
    
    # Get initial state
    initial_state = fetch_espn_live_state(game_id)
    if not initial_state:
        return jsonify({'status': 'error', 'message': 'Could not fetch game state'}), 500
    
    live_game_id = game_id
    live_last_state = initial_state
    live_polling = True
    
    # Check if this is a pre-game state
    game_status = initial_state.get('status', '')
    is_pregame = game_status in ['Scheduled', 'Pre-Game', 'Pregame'] or initial_state.get('quarter', 1) == 0
    
    # Get team info for pregame
    home_team = initial_state.get('home_team', {})
    away_team = initial_state.get('away_team', {})
    home_abbr = home_team.get('abbreviation', '') if isinstance(home_team, dict) else str(home_team)
    away_abbr = away_team.get('abbreviation', '') if isinstance(away_team, dict) else str(away_team)
    
    # Trigger pre-game insights if game hasn't started AND we haven't already
    pregame_triggered = False
    if (is_pregame or initial_state.get('quarter', 1) < 1) and not live_pregame_triggered:
        try:
            import requests
            pregame_resp = requests.post(
                f"{INSIGHT_ENGINE_URL}/pregame",
                json={
                    'game_id': game_id,
                    'home_abbr': home_abbr,
                    'away_abbr': away_abbr
                },
                timeout=10
            )
            if pregame_resp.status_code == 200:
                pregame_triggered = True
                live_pregame_triggered = True  # Mark as triggered to prevent duplicates
                logger.info(f"🎬 Pre-game sequence triggered for {away_abbr} @ {home_abbr}")
        except Exception as e:
            logger.warning(f"Could not trigger pregame: {e}")
    else:
        # Game is in progress - still load context
        try:
            import requests
            requests.post(
                f"{INSIGHT_ENGINE_URL}/load_matchup",
                json={
                    'game_id': game_id,
                    'home_abbr': home_abbr,
                    'away_abbr': away_abbr
                },
                timeout=10
            )
            logger.info(f"📚 Matchup context loaded for {away_abbr} @ {home_abbr}")
        except Exception as e:
            logger.debug(f"Could not load matchup: {e}")
    
    # Start polling thread
    live_poll_thread = threading.Thread(target=live_poll_loop, args=(game_id, poll_interval), daemon=True)
    live_poll_thread.start()
    
    response = jsonify({
        'status': 'ok',
        'message': f"{'Pre-game' if is_pregame else 'Live'} mode started: {away_abbr} @ {home_abbr}",
        'game_id': game_id,
        'poll_interval': poll_interval,
        'is_pregame': is_pregame,
        'pregame_triggered': pregame_triggered,
        'current': {
            'quarter': initial_state['quarter'],
            'clock': initial_state['clock'],
            'status': game_status,
            'score': f"{away_abbr} {initial_state['away_score']} - {home_abbr} {initial_state['home_score']}"
        }
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@flask_app.route('/live/espn/state', methods=['GET'])
def get_live_espn_state():
    """Get current live state."""
    global live_last_state, live_game_id, live_polling
    
    if not live_game_id or not live_polling:
        return jsonify({'status': 'error', 'message': 'No live mode active. Call /live/espn/start first'}), 404
    
    if live_last_state:
        response = jsonify({
            'status': 'ok',
            'polling': live_polling,
            'state': {
                'game_id': live_last_state['game_id'],
                'quarter': live_last_state['quarter'],
                'clock': live_last_state['clock'],
                'home_team': live_last_state['home_team'],  # Already a dict now
                'away_team': live_last_state['away_team'],  # Already a dict now
                'down': live_last_state['down'],
                'distance': live_last_state['distance'],
                'yard_line': live_last_state['yard_line'],
                'down_distance_text': live_last_state['down_distance_text'],
                'last_play': live_last_state['last_play'],
                'is_red_zone': live_last_state['is_red_zone'],
                'short_name': f"{live_last_state['away_team']['abbreviation']} @ {live_last_state['home_team']['abbreviation']}"
            }
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    else:
        return jsonify({'status': 'error', 'message': 'No state available yet'}), 404


@flask_app.route('/live/espn/stop', methods=['POST'])
def stop_live_espn():
    """Stop live polling."""
    global live_game_id, live_polling, live_last_state, live_pregame_triggered
    
    live_polling = False
    live_game_id = None
    live_last_state = None
    live_pregame_triggered = False  # Reset for next game
    
    response = jsonify({'status': 'ok', 'message': 'Live polling stopped'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


# ============== SPORTRADAR LIVE MODE (requires production key) ==============

@flask_app.route('/live/start', methods=['POST'])
def start_live_sportradar():
    """Start live polling from Sportradar API."""
    global sportradar_game_id, sportradar_polling, sportradar_last_play_id
    
    from sportradar_client import get_live_games, get_game_state
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    
    if not game_id:
        # Auto-find first live game
        games = get_live_games()
        if games:
            game_id = games[0]['id']
            logger.info(f"Auto-selected live game: {games[0]['away']} @ {games[0]['home']}")
        else:
            return jsonify({'status': 'error', 'message': 'No live games found'}), 404
    
    sportradar_game_id = game_id
    sportradar_polling = True
    sportradar_last_play_id = None
    
    # Get initial state
    state = get_game_state(game_id)
    if state:
        return jsonify({
            'status': 'ok',
            'message': f'Live polling started: {state.away_team} @ {state.home_team}',
            'game_id': game_id,
            'current': {
                'quarter': state.quarter,
                'clock': state.clock,
                'score': f'{state.away_team} {state.away_score} - {state.home_team} {state.home_score}'
            }
        })
    else:
        return jsonify({'status': 'error', 'message': 'Could not get game state'}), 500


@flask_app.route('/live/state', methods=['GET'])
def get_live_state():
    """Get current live game state from Sportradar."""
    global sportradar_game_id
    
    if not sportradar_game_id:
        return jsonify({'status': 'error', 'message': 'No live game active. Call /live/start first'}), 404
    
    from sportradar_client import get_game_state
    
    state = get_game_state(sportradar_game_id)
    if state:
        return jsonify({
            'status': 'ok',
            'state': {
                'game_id': state.game_id,
                'quarter': state.quarter,
                'clock': state.clock,
                'home_team': {'abbreviation': state.home_team, 'score': state.home_score},
                'away_team': {'abbreviation': state.away_team, 'score': state.away_score},
                'down': state.down,
                'distance': state.distance,
                'yard_line': state.yard_line,
                'possession_team': state.possession,
                'is_red_zone': state.is_red_zone,
                'last_play': state.last_play,
                'short_name': f'{state.away_team} @ {state.home_team}'
            }
        })
    else:
        return jsonify({'status': 'error', 'message': 'Could not get game state'}), 500


@flask_app.route('/live/stop', methods=['POST'])
def stop_live_sportradar():
    """Stop live polling."""
    global sportradar_game_id, sportradar_polling
    
    sportradar_game_id = None
    sportradar_polling = False
    
    return jsonify({'status': 'ok', 'message': 'Live polling stopped'})


def run_server(port: int = 5132):
    """Run as a Flask server."""
    logger.info(f"Starting simulator server on port {port}")
    logger.info("")
    logger.info("=== Simulation Mode (cached games) ===")
    logger.info("  GET  /games - List cached games")
    logger.info("  POST /start {game_id, speed} - Start simulation")
    logger.info("  GET  /state - Get current state")
    logger.info("  POST /stop - Stop simulation")
    logger.info("")
    logger.info("=== LIVE MODE (ESPN real-time) ===")
    logger.info("  GET  /live/espn/games - List live NFL games")
    logger.info("  POST /live/espn/start {game_id?, interval?} - Start live polling")
    logger.info("  GET  /live/espn/state - Get current live state")
    logger.info("  POST /live/espn/stop - Stop live polling")
    logger.info("")
    flask_app.run(host='0.0.0.0', port=port, debug=False)


def main():
    parser = argparse.ArgumentParser(description='Auto-Madden Game Simulator')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Download command
    dl_parser = subparsers.add_parser('download', help='Download a game for simulation')
    dl_parser.add_argument('game_id', help='ESPN game ID')
    
    # List command
    subparsers.add_parser('list', help='List cached games')
    
    # Find command
    find_parser = subparsers.add_parser('find', help='Find recent completed games')
    find_parser.add_argument('--date', help='Date in YYYYMMDD format', default=None)
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run a simulation')
    run_parser.add_argument('game_id', help='Game ID to simulate')
    run_parser.add_argument('--speed', type=float, default=10.0, help='Playback speed (default: 10x)')
    run_parser.add_argument('--no-emit', action='store_true', help='Do not emit events to insight engine')
    
    # Serve command
    serve_parser = subparsers.add_parser('serve', help='Run as a service')
    serve_parser.add_argument('--port', type=int, default=5132, help='Port to listen on')
    
    args = parser.parse_args()
    
    if args.command == 'download':
        download_game(args.game_id)
    
    elif args.command == 'list':
        list_cached_games()
    
    elif args.command == 'find':
        games = find_recent_games(args.date)
        if games:
            print(f"\nCompleted Games:")
            print("-" * 60)
            for g in games:
                print(f"  {g['id']}: {g['name']}")
                print(f"           {g['home_score']} - {g['away_score']}")
        else:
            print("No completed games found")
    
    elif args.command == 'run':
        run_simulation(args.game_id, speed=args.speed, emit_events=not args.no_emit)
    
    elif args.command == 'serve':
        run_server(port=args.port)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

