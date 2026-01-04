"""
Auto-Madden Letta Tools for Main Agent.

Tools for interacting with the real-time game companion system.
"""

from typing import Dict, Any, Optional


def get_current_game_state() -> Dict[str, Any]:
    """
    Get the current state of the active auto-madden game session.
    
    Returns information about the current score, clock, down and distance,
    possession, and recent plays to provide context for the conversation.
    
    Args:
        None - uses the active session
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - game_active: Whether a game is currently being tracked
        - score: Current score (e.g., "Patriots 14, Bills 10")
        - situation: Down, distance, field position
        - clock: Quarter and time remaining
        - recent_plays: Last 3 plays summarized
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    
    try:
        GAME_STATE_URL = "http://auto-madden-game-state:5132"
        
        response = requests.get(f"{GAME_STATE_URL}/state", timeout=5)
        
        if response.status_code != 200:
            return {
                "status": "error",
                "game_active": False,
                "error_message": "No active game session"
            }
        
        data = response.json()
        state = data.get('state', {})
        
        home_team = state.get('home_team', {})
        away_team = state.get('away_team', {})
        
        score = f"{home_team.get('name', 'Home')} {home_team.get('score', 0)}, {away_team.get('name', 'Away')} {away_team.get('score', 0)}"
        
        situation = f"{state.get('down', 1)} and {state.get('distance', 10)} at the {state.get('yard_line', 25)}-yard line"
        
        clock = f"Q{state.get('quarter', 1)} - {state.get('clock', '15:00')}"
        
        recent = []
        for play in state.get('recent_plays', [])[:3]:
            recent.append(play.get('description', 'Unknown play'))
        
        return {
            "status": "ok",
            "game_active": True,
            "score": score,
            "situation": situation,
            "clock": clock,
            "possession": state.get('possession_team', 'Unknown'),
            "recent_plays": recent
        }
        
    except Exception as e:
        return {
            "status": "error",
            "game_active": False,
            "error_message": f"Error getting game state: {str(e)}\n{traceback.format_exc()}"
        }


def ask_game_question(
    question: str
) -> Dict[str, Any]:
    """
    Ask a question about the current game and get a context-aware answer.
    
    Use this tool when the user asks questions about what's happening in the game,
    rules, players, strategies, or anything related to the football game being watched.
    
    Args:
        question: The user's question about the game (e.g., "What's an RPO?", "Who's number 87?")
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - answer: The answer to the question
        - context: Additional context or follow-up suggestions
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    
    try:
        INSIGHT_ENGINE_URL = "http://auto-madden-insight-engine:5131"
        
        response = requests.post(
            f"{INSIGHT_ENGINE_URL}/query",
            json={"question": question},
            timeout=30
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "answer": "",
                "error_message": f"Query failed: {response.text}"
            }
        
        result = response.json()
        
        return {
            "status": "ok",
            "answer": result.get("answer", "I couldn't find an answer to that question."),
            "context": result.get("context", "")
        }
        
    except Exception as e:
        return {
            "status": "error",
            "answer": "",
            "error_message": f"Error asking question: {str(e)}\n{traceback.format_exc()}"
        }


def get_player_info(
    player_name: str
) -> Dict[str, Any]:
    """
    Look up information about a player by name.
    
    Retrieves career stats, current team, position, and notable achievements
    for the specified player. Useful for answering questions like "Who is that?"
    or providing context about players involved in significant plays.
    
    Args:
        player_name: The player's name (e.g., "Patrick Mahomes", "Travis Kelce")
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - found: Whether the player was found
        - name: Full player name
        - position: Player position (QB, WR, etc.)
        - team: Current team
        - number: Jersey number
        - experience: Years in the league
        - highlights: Notable career achievements
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    
    try:
        GAME_STATE_URL = "http://auto-madden-game-state:5132"
        
        response = requests.get(
            f"{GAME_STATE_URL}/player",
            params={"name": player_name},
            timeout=10
        )
        
        if response.status_code != 200:
            return {
                "status": "ok",
                "found": False,
                "name": player_name,
                "error_message": f"Player lookup not available"
            }
        
        result = response.json()
        player = result.get('player', {})
        
        return {
            "status": "ok",
            "found": result.get('found', False),
            "name": player.get("name", player_name),
            "position": player.get("position", "Unknown"),
            "team": player.get("team", "Unknown"),
            "number": player.get("number", ""),
            "experience": player.get("experience", ""),
            "highlights": player.get("highlights", [])
        }
        
    except Exception as e:
        return {
            "status": "error",
            "found": False,
            "error_message": f"Error looking up player: {str(e)}\n{traceback.format_exc()}"
        }


def explain_play(
    play_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a detailed explanation of the most recent play or a specific play.
    
    Provides strategic context, what the offense was trying to do, how the
    defense responded, and what made the play succeed or fail.
    
    Args:
        play_description: Optional description to identify a specific play.
                         If not provided, explains the most recent play.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - play: Brief description of the play
        - explanation: Detailed breakdown of what happened
        - strategic_context: Why this play was called in this situation
        - what_to_watch: What to look for on similar situations
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    from typing import Optional
    
    try:
        INSIGHT_ENGINE_URL = "http://auto-madden-insight-engine:5131"
        
        payload = {}
        if play_description:
            payload["play_description"] = play_description
        
        response = requests.post(
            f"{INSIGHT_ENGINE_URL}/explain_play",
            json=payload,
            timeout=15
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "play": "",
                "explanation": "",
                "error_message": f"Could not explain play: {response.text}"
            }
        
        result = response.json()
        
        return {
            "status": "ok",
            "play": result.get("play", ""),
            "explanation": result.get("explanation", ""),
            "strategic_context": result.get("strategic_context", ""),
            "what_to_watch": result.get("what_to_watch", "")
        }
        
    except Exception as e:
        return {
            "status": "error",
            "play": "",
            "explanation": "",
            "error_message": f"Error explaining play: {str(e)}\n{traceback.format_exc()}"
        }


def get_game_summary() -> Dict[str, Any]:
    """
    Get a drive-by-drive summary of the game so far.
    
    Useful for catching up on what's happened in the game, especially if
    joining mid-game or returning from a break.
    
    Args:
        None - summarizes the current active game
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - game_name: The matchup (e.g., "Patriots vs Bills")
        - current_score: Current score
        - key_moments: List of pivotal plays/moments
        - drives_summary: Brief summary of each scoring drive
        - momentum: Which team has momentum and why
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    
    try:
        GAME_STATE_URL = "http://auto-madden-game-state:5132"
        
        response = requests.get(f"{GAME_STATE_URL}/summary", timeout=10)
        
        if response.status_code != 200:
            return {
                "status": "error",
                "game_name": "",
                "error_message": "No active game or summary unavailable"
            }
        
        result = response.json()
        summary = result.get('summary', {})
        
        return {
            "status": "ok",
            "game_name": summary.get("game_name", ""),
            "current_score": summary.get("current_score", ""),
            "key_moments": summary.get("key_moments", []),
            "drives_summary": summary.get("drives_summary", []),
            "momentum": summary.get("momentum", "")
        }
        
    except Exception as e:
        return {
            "status": "error",
            "game_name": "",
            "error_message": f"Error getting summary: {str(e)}\n{traceback.format_exc()}"
        }

