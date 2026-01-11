#!/usr/bin/env python3
"""
Auto-Madden Game State Service.

Real-time game state tracking with ESPN API polling and event emission.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from models import GameState, GameChange
from espn_client import ESPNClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', 'http://auto-madden-insight-engine:5131')
BASE_POLL_INTERVAL = float(os.environ.get('ESPN_POLL_INTERVAL', '3'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Set log level
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

# Global state
espn_client = ESPNClient()
current_state: Optional[GameState] = None
previous_state: Optional[GameState] = None
tracking_active = False
tracking_thread: Optional[threading.Thread] = None
last_play_id: Optional[str] = None


def detect_changes(old_state: Optional[GameState], new_state: GameState) -> List[GameChange]:
    """
    Detect meaningful changes between two game states.
    
    Args:
        old_state: Previous game state (None if first poll)
        new_state: Current game state
        
    Returns:
        List of detected changes.
    """
    changes: List[GameChange] = []
    
    if old_state is None:
        # Initial state - emit game start if in progress
        if new_state.status == 'in':
            changes.append(GameChange(
                change_type='game_start',
                description=f"Game in progress: {new_state.short_name}",
                significance=6,
                data={'status': new_state.status}
            ))
        return changes
    
    # Score change
    if (new_state.home_score != old_state.home_score or 
        new_state.away_score != old_state.away_score):
        
        scoring_team = None
        points = 0
        
        if new_state.home_score > old_state.home_score:
            scoring_team = new_state.home_team.name if new_state.home_team else 'Home'
            points = new_state.home_score - old_state.home_score
        else:
            scoring_team = new_state.away_team.name if new_state.away_team else 'Away'
            points = new_state.away_score - old_state.away_score
        
        score_type = 'touchdown' if points >= 6 else ('field_goal' if points == 3 else 'score')
        
        changes.append(GameChange(
            change_type='score_change',
            description=f"{scoring_team} scores! {new_state.home_team.abbreviation if new_state.home_team else 'HOME'} {new_state.home_score}, {new_state.away_team.abbreviation if new_state.away_team else 'AWAY'} {new_state.away_score}",
            significance=9,
            data={
                'scoring_team': scoring_team,
                'points': points,
                'score_type': score_type,
                'home_score': new_state.home_score,
                'away_score': new_state.away_score
            }
        ))
    
    # New play detection
    if new_state.recent_plays and len(new_state.recent_plays) > 0:
        latest_play = new_state.recent_plays[0]
        global last_play_id
        
        if latest_play.id != last_play_id:
            last_play_id = latest_play.id
            
            # Determine significance based on play type
            significance = 5
            if latest_play.is_scoring:
                significance = 9
            elif latest_play.is_turnover:
                significance = 9
            elif latest_play.yards_gained >= 20:
                significance = 7
            elif latest_play.yards_gained >= 10:
                significance = 6
            
            changes.append(GameChange(
                change_type='new_play',
                description=latest_play.description,
                significance=significance,
                data={
                    'play_id': latest_play.id,
                    'play_type': latest_play.play_type,
                    'yards_gained': latest_play.yards_gained,
                    'is_scoring': latest_play.is_scoring,
                    'is_turnover': latest_play.is_turnover,
                    'down': latest_play.down,
                    'distance': latest_play.distance
                }
            ))
            
            # Turnover detected
            if latest_play.is_turnover:
                changes.append(GameChange(
                    change_type='turnover',
                    description=f"TURNOVER! {latest_play.description}",
                    significance=9,
                    data={'play': latest_play.to_dict()}
                ))
            
            # Big play
            if latest_play.yards_gained >= 20:
                changes.append(GameChange(
                    change_type='big_play',
                    description=f"Big gain: {latest_play.yards_gained} yards!",
                    significance=7,
                    data={'yards': latest_play.yards_gained}
                ))
    
    # Quarter change
    if new_state.quarter != old_state.quarter:
        changes.append(GameChange(
            change_type='quarter_change',
            description=f"End of Q{old_state.quarter}",
            significance=6,
            data={'old_quarter': old_state.quarter, 'new_quarter': new_state.quarter}
        ))
    
    # Two-minute warning
    if new_state.is_two_minute_warning and not old_state.is_two_minute_warning:
        half = "first" if new_state.quarter == 2 else "second"
        changes.append(GameChange(
            change_type='two_minute_warning',
            description=f"Two-minute warning - {half} half",
            significance=7,
            data={'quarter': new_state.quarter}
        ))
    
    # Red zone entry
    if new_state.is_red_zone and not old_state.is_red_zone:
        changes.append(GameChange(
            change_type='red_zone_entry',
            description=f"{new_state.possession_team or 'Offense'} enters the red zone",
            significance=7,
            data={'yard_line': new_state.yard_line}
        ))
    
    # Possession change (without turnover - could be punt, score, etc.)
    if (new_state.possession_team != old_state.possession_team and
        new_state.possession_team is not None):
        # Only if not already detected as turnover
        if not any(c.change_type == 'turnover' for c in changes):
            changes.append(GameChange(
                change_type='possession_change',
                description=f"{new_state.possession_team} takes possession",
                significance=5,
                data={'new_possession': new_state.possession_team}
            ))
    
    # Win probability shift (>10% change)
    prob_diff = abs(new_state.home_win_probability - old_state.home_win_probability)
    if prob_diff >= 10:
        favored = new_state.home_team.name if new_state.home_win_probability > 50 else new_state.away_team.name
        changes.append(GameChange(
            change_type='momentum_shift',
            description=f"Momentum swinging - {favored} now at {max(new_state.home_win_probability, new_state.away_win_probability):.0f}%",
            significance=7,
            data={
                'shift': prob_diff,
                'home_wp': new_state.home_win_probability,
                'away_wp': new_state.away_win_probability
            }
        ))
    
    # Game status change
    if new_state.status != old_state.status:
        if new_state.status == 'halftime':
            changes.append(GameChange(
                change_type='halftime',
                description=f"HALFTIME: {new_state.home_team.abbreviation if new_state.home_team else 'HOME'} {new_state.home_score}, {new_state.away_team.abbreviation if new_state.away_team else 'AWAY'} {new_state.away_score}",
                significance=6,
                data={'status': 'halftime'}
            ))
        elif new_state.status == 'post':
            changes.append(GameChange(
                change_type='game_end',
                description=f"FINAL: {new_state.home_team.abbreviation if new_state.home_team else 'HOME'} {new_state.home_score}, {new_state.away_team.abbreviation if new_state.away_team else 'AWAY'} {new_state.away_score}",
                significance=8,
                data={'status': 'final'}
            ))
    
    return changes


def emit_changes(changes: List[GameChange], state: GameState):
    """
    Send detected changes to the insight engine.
    
    Args:
        changes: List of detected changes
        state: Current game state
    """
    if not changes:
        return
    
    for change in changes:
        try:
            payload = {
                'change': change.to_dict(),
                'state': state.to_dict()
            }
            
            response = requests.post(
                f"{INSIGHT_ENGINE_URL}/event",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.debug(f"Emitted change: {change.change_type}")
            else:
                logger.warning(f"Failed to emit change: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error emitting change to insight engine: {e}")
        except Exception as e:
            logger.error(f"Unexpected error emitting change: {e}")


def calculate_poll_interval(state: Optional[GameState]) -> float:
    """
    Calculate adaptive poll interval based on game state.
    
    Args:
        state: Current game state
        
    Returns:
        Poll interval in seconds.
    """
    if state is None:
        return 5.0
    
    if state.status == 'pre':
        return 60.0  # Pre-game: poll every minute
    
    if state.status == 'halftime':
        return 30.0  # Halftime: slow polling
    
    if state.status == 'post':
        return 0  # Game over: stop polling
    
    # During game
    if state.is_two_minute_warning:
        return 2.0  # Critical moments: fast polling
    
    if not state.clock_running:
        return 5.0  # Stopped clock: slower polling
    
    if state.quarter == 4 and state.score_differential <= 7:
        return 2.0  # Close game in 4th quarter
    
    return BASE_POLL_INTERVAL  # Normal play


def poll_loop(game_id: str):
    """
    Main polling loop for tracking a game.
    
    Args:
        game_id: ESPN game ID to track
    """
    global current_state, previous_state, tracking_active, last_play_id
    
    logger.info(f"Starting poll loop for game {game_id}")
    last_play_id = None
    
    while tracking_active:
        try:
            # Fetch latest data
            raw_data = espn_client.get_game_summary(game_id)
            
            if raw_data is None:
                logger.warning("Failed to fetch game data")
                time.sleep(5.0)
                continue
            
            # Parse new state
            new_state = espn_client.parse_game_state(raw_data)
            
            # Detect changes
            changes = detect_changes(current_state, new_state)
            
            # Store previous state
            previous_state = current_state
            current_state = new_state
            
            # Emit changes to insight engine
            if changes:
                emit_changes(changes, new_state)
                for change in changes:
                    logger.info(f"Change detected: {change.change_type} - {change.description}")
            
            # Calculate next poll interval
            interval = calculate_poll_interval(new_state)
            
            if interval == 0:
                logger.info("Game ended, stopping poll loop")
                tracking_active = False
                break
            
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"Poll loop error: {e}")
            time.sleep(5.0)
    
    logger.info("Poll loop ended")


# Flask Routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'auto-madden-game-state',
        'tracking_active': tracking_active,
        'game_id': current_state.game_id if current_state else None,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/games', methods=['GET'])
@app.route('/live/games', methods=['GET'])
@app.route('/live/espn/games', methods=['GET'])
def list_games():
    """List current NFL games."""
    games = espn_client.get_scoreboard()
    return jsonify({
        'status': 'ok',
        'games': games,
        'count': len(games)
    })


@app.route('/start', methods=['POST'])
@app.route('/live/espn/start', methods=['POST'])
def start_tracking():
    """
    Start tracking a game.
    
    Request body:
        - team: Team name/abbreviation to find game for
        - game_id: Specific ESPN game ID (optional, overrides team)
    """
    global tracking_active, tracking_thread, current_state, previous_state
    
    data = request.get_json() or {}
    
    # Check if already tracking
    if tracking_active:
        return jsonify({
            'status': 'error',
            'message': 'Already tracking a game',
            'current_game': current_state.short_name if current_state else None
        }), 400
    
    game_id = data.get('game_id')
    team = data.get('team')
    
    # Find game by team if no game_id provided
    if not game_id and team:
        game = espn_client.find_game_by_team(team)
        if game:
            game_id = game.get('game_id')
        else:
            return jsonify({
                'status': 'error',
                'message': f"No game found for team: {team}",
                'available_games': espn_client.get_scoreboard()
            }), 404
    
    if not game_id:
        return jsonify({
            'status': 'error',
            'message': 'Must provide team or game_id'
        }), 400
    
    # Get initial state
    raw_data = espn_client.get_game_summary(game_id)
    if not raw_data:
        return jsonify({
            'status': 'error',
            'message': f"Could not fetch game data for {game_id}"
        }), 404
    
    current_state = espn_client.parse_game_state(raw_data)
    previous_state = None
    
    # Start tracking thread
    tracking_active = True
    tracking_thread = threading.Thread(target=poll_loop, args=(game_id,), daemon=True)
    tracking_thread.start()
    
    logger.info(f"Started tracking game: {current_state.short_name}")
    
    return jsonify({
        'status': 'ok',
        'message': f"Now tracking: {current_state.short_name}",
        'game': {
            'game_id': game_id,
            'name': current_state.game_name,
            'short_name': current_state.short_name,
            'status': current_state.status,
            'score': f"{current_state.home_team.abbreviation if current_state.home_team else 'HOME'} {current_state.home_score}, {current_state.away_team.abbreviation if current_state.away_team else 'AWAY'} {current_state.away_score}"
        }
    })


@app.route('/stop', methods=['POST'])
@app.route('/live/espn/stop', methods=['POST'])
def stop_tracking():
    """Stop tracking the current game."""
    global tracking_active, current_state, previous_state
    
    if not tracking_active:
        return jsonify({
            'status': 'ok',
            'message': 'No game being tracked'
        })
    
    tracking_active = False
    game_name = current_state.short_name if current_state else 'Unknown'
    current_state = None
    previous_state = None
    
    logger.info(f"Stopped tracking game: {game_name}")
    
    return jsonify({
        'status': 'ok',
        'message': f"Stopped tracking: {game_name}"
    })


@app.route('/state', methods=['GET'])
@app.route('/live/espn/state', methods=['GET'])
def get_state():
    """Get current game state."""
    if current_state is None:
        return jsonify({
            'status': 'error',
            'message': 'No game being tracked'
        }), 404
    
    return jsonify({
        'status': 'ok',
        'state': current_state.to_dict()
    })


@app.route('/summary', methods=['GET'])
def get_summary():
    """Get game summary for catch-up."""
    if current_state is None:
        return jsonify({
            'status': 'error',
            'message': 'No game being tracked'
        }), 404
    
    # Build summary
    summary = {
        'game_name': current_state.short_name,
        'current_score': f"{current_state.home_team.name if current_state.home_team else 'Home'} {current_state.home_score}, {current_state.away_team.name if current_state.away_team else 'Away'} {current_state.away_score}",
        'quarter': current_state.quarter,
        'clock': current_state.clock,
        'situation': f"{current_state.down} and {current_state.distance} at the {current_state.yard_line}",
        'possession': current_state.possession_team,
        'key_moments': [],  # Would be populated from tracked changes
        'drives_summary': [],  # Would be populated from drive history
        'momentum': f"{'Home' if current_state.home_win_probability > 50 else 'Away'} favored at {max(current_state.home_win_probability, current_state.away_win_probability):.0f}%"
    }
    
    return jsonify({
        'status': 'ok',
        'summary': summary
    })


@app.route('/player', methods=['GET'])
def get_player():
    """Look up player by name."""
    name = request.args.get('name', '')
    
    if not name:
        return jsonify({
            'status': 'error',
            'message': 'Must provide player name'
        }), 400
    
    # TODO: Implement player lookup from ESPN
    # For now, return a placeholder
    return jsonify({
        'status': 'ok',
        'found': False,
        'message': f"Player lookup for '{name}' not yet implemented"
    })


if __name__ == '__main__':
    logger.info("Starting Auto-Madden Game State Service")
    app.run(host='0.0.0.0', port=5132, debug=False, threaded=True)

