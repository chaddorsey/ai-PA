#!/usr/bin/env python3
"""
Sportradar NFL API Client for real-time game data.
"""

import requests
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)

# API Configuration
SPORTRADAR_API_KEY = os.environ.get('SPORTRADAR_API_KEY', 'Q5BynZfpo27iSiTF12s5xFZISpUHUwKsYrSg9ah0')
SPORTRADAR_BASE_URL = 'https://api.sportradar.us/nfl/official/trial/v7/en'


@dataclass
class LiveGameState:
    """Current state of a live game from Sportradar."""
    game_id: str
    status: str
    quarter: int
    clock: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    home_id: str
    away_id: str
    possession: Optional[str]
    down: Optional[int]
    distance: Optional[int]
    yard_line: Optional[int]
    last_play: Optional[str]
    is_red_zone: bool


def get_live_games() -> List[Dict[str, Any]]:
    """Get list of currently live NFL games."""
    # Get current week schedule
    url = f"{SPORTRADAR_BASE_URL}/games/2025/REG/18/schedule.json"
    params = {'api_key': SPORTRADAR_API_KEY}
    
    try:
        resp = requests.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        games = []
        for game in data.get('week', {}).get('games', []):
            if game.get('status') == 'inprogress':
                games.append({
                    'id': game.get('id'),
                    'home': game.get('home', {}).get('alias'),
                    'away': game.get('away', {}).get('alias'),
                    'home_id': game.get('home', {}).get('id'),
                    'away_id': game.get('away', {}).get('id'),
                    'status': game.get('status')
                })
        return games
    
    except Exception as e:
        logger.error(f"Error getting live games: {e}")
        return []


def get_game_state(game_id: str) -> Optional[LiveGameState]:
    """Get current state of a live game."""
    url = f"{SPORTRADAR_BASE_URL}/games/{game_id}/pbp.json"
    params = {'api_key': SPORTRADAR_API_KEY}
    
    try:
        resp = requests.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        summary = data.get('summary', {})
        home = summary.get('home', {})
        away = summary.get('away', {})
        
        # Get current quarter and clock from latest period
        periods = data.get('periods', [])
        quarter = 1
        clock = '15:00'
        last_play = None
        down = None
        distance = None
        yard_line = None
        possession = None
        
        if periods:
            last_period = periods[-1]
            quarter = last_period.get('number', 1)
            
            # Get latest play
            pbp = last_period.get('pbp', [])
            if pbp:
                last_event = pbp[-1]
                clock = last_event.get('clock', '15:00')
                last_play = last_event.get('description', '')
                
                # Get situation from last regular play
                for event in reversed(pbp):
                    if event.get('play_type') not in ['timeout', 'tv_timeout', 'two_minute_warning']:
                        situation = event.get('start_situation', {})
                        down = situation.get('down')
                        distance = situation.get('yfd')  # yards for first down
                        yard_line = situation.get('yardline')
                        possession = situation.get('possession', {}).get('alias')
                        break
        
        # Check red zone
        is_red_zone = yard_line is not None and yard_line <= 20
        
        return LiveGameState(
            game_id=game_id,
            status=data.get('status', 'unknown'),
            quarter=quarter,
            clock=clock,
            home_team=home.get('alias', 'HOME'),
            away_team=away.get('alias', 'AWAY'),
            home_score=home.get('points', 0),
            away_score=away.get('points', 0),
            home_id=home.get('id', ''),
            away_id=away.get('id', ''),
            possession=possession,
            down=down,
            distance=distance,
            yard_line=yard_line,
            last_play=last_play,
            is_red_zone=is_red_zone
        )
    
    except Exception as e:
        logger.error(f"Error getting game state: {e}")
        return None


def get_game_plays(game_id: str) -> List[Dict[str, Any]]:
    """Get all plays from a game."""
    url = f"{SPORTRADAR_BASE_URL}/games/{game_id}/pbp.json"
    params = {'api_key': SPORTRADAR_API_KEY}
    
    try:
        resp = requests.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        plays = []
        for period in data.get('periods', []):
            quarter = period.get('number', 1)
            for event in period.get('pbp', []):
                if event.get('play_type') not in ['timeout', 'tv_timeout', 'two_minute_warning', 'end_period']:
                    plays.append({
                        'id': event.get('id'),
                        'quarter': quarter,
                        'clock': event.get('clock', ''),
                        'description': event.get('description', ''),
                        'play_type': event.get('play_type', ''),
                        'scoring': event.get('scoring_play', False),
                        'yards': event.get('statistics', {}).get('yards', 0) if event.get('statistics') else 0
                    })
        
        return plays
    
    except Exception as e:
        logger.error(f"Error getting plays: {e}")
        return []


if __name__ == '__main__':
    # Test the client
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print("=== Live Games ===")
    games = get_live_games()
    for g in games:
        print(f"  {g['away']} @ {g['home']} - {g['id']}")
    
    if games:
        game_id = games[0]['id']
        print(f"\n=== Game State: {game_id} ===")
        state = get_game_state(game_id)
        if state:
            print(f"  Q{state.quarter} {state.clock}")
            print(f"  {state.away_team} {state.away_score} - {state.home_team} {state.home_score}")
            print(f"  {state.down} & {state.distance} at {state.yard_line}")
            print(f"  Possession: {state.possession}")
            print(f"  Last play: {state.last_play[:80]}..." if state.last_play else "")

