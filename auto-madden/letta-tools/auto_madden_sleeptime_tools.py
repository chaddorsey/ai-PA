"""
Auto-Madden Letta Tools for Sleeptime Agent.

Tools for aggregation, knowledge tracking, and session logging.
"""

from typing import Dict, Any, Optional


def summarize_game_insights(
    game_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Summarize all insights delivered during a game session.
    
    Aggregates the insights that were pushed to the user during the game,
    categorizing them by type and identifying key learning moments.
    Use this after a game ends to update memory about the session.
    
    Args:
        game_id: Optional game ID to summarize. If not provided, uses the most recent session.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - game_name: The matchup that was watched
        - total_insights: Number of insights delivered
        - by_type: Count of insights by type
        - key_explanations: Most important explanations given
        - concepts_introduced: New concepts explained to user
        - user_questions: Questions the user asked
        - error_message: Error details if status is "error"
    """
    import requests
    import traceback
    from typing import Optional
    
    try:
        INSIGHT_ENGINE_URL = "http://auto-madden-insight-engine:5131"
        
        params = {}
        if game_id:
            params["game_id"] = game_id
        
        response = requests.get(
            f"{INSIGHT_ENGINE_URL}/session_summary",
            params=params,
            timeout=15
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": "No session data available"
            }
        
        result = response.json()
        
        return {
            "status": "ok",
            "game_id": result.get("game_id", ""),
            "game_name": result.get("game_name", ""),
            "total_insights": result.get("total_insights", 0),
            "by_type": result.get("by_type", {}),
            "key_explanations": result.get("key_explanations", []),
            "concepts_introduced": result.get("concepts_introduced", []),
            "user_questions": result.get("user_questions", [])
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Error summarizing insights: {str(e)}\n{traceback.format_exc()}"
        }


def update_user_knowledge(
    concepts_learned: str,
    knowledge_area: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update the record of what football concepts the user has learned.
    
    Track the user's growing knowledge to avoid repeating explanations
    and to tailor future insights to their level.
    
    Args:
        concepts_learned: Comma-separated list of concepts (e.g., "RPO,play-action,zone coverage")
        knowledge_area: Optional area category (e.g., "offense", "defense", "rules")
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - updated: Whether the knowledge was successfully updated
        - concepts_added: List of concepts that were added
        - knowledge_area: The area these concepts belong to
        - error_message: Error details if status is "error"
    """
    import traceback
    from typing import Optional
    
    try:
        # Parse concepts
        if not concepts_learned:
            return {
                "status": "error",
                "updated": False,
                "error_message": "No concepts provided"
            }
        
        concepts = [c.strip() for c in concepts_learned.split(',') if c.strip()]
        
        if not concepts:
            return {
                "status": "error",
                "updated": False,
                "error_message": "No valid concepts provided"
            }
        
        # This stores to agent memory via the response
        # The agent's memory block will be updated by the calling agent
        
        return {
            "status": "ok",
            "updated": True,
            "concepts_added": concepts,
            "knowledge_area": knowledge_area or "general",
            "message": f"Added {len(concepts)} concepts to user knowledge tracking: {', '.join(concepts)}"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "updated": False,
            "error_message": f"Error updating knowledge: {str(e)}\n{traceback.format_exc()}"
        }


def log_game_session(
    game_id: str,
    game_name: str,
    duration_minutes: int,
    insights_delivered: int,
    questions_asked: int,
    final_score: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log a completed game watching session for future reference.
    
    Records session metrics and outcome for analytics and to help
    improve the companion experience over time.
    
    Args:
        game_id: ESPN game ID
        game_name: Matchup name (e.g., "Patriots vs Bills")
        duration_minutes: How long the session lasted
        insights_delivered: Total insights pushed during session
        questions_asked: Number of questions the user asked
        final_score: Final score if game completed (e.g., "Patriots 24, Bills 17")
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - logged: Whether the session was successfully logged
        - session_id: Unique ID for this session record
        - summary: Brief summary of the session
        - error_message: Error details if status is "error"
    """
    import traceback
    import uuid
    from datetime import datetime
    from typing import Optional
    
    try:
        session_id = str(uuid.uuid4())[:8]
        
        session_record = {
            "session_id": session_id,
            "game_id": game_id,
            "game_name": game_name,
            "duration_minutes": duration_minutes,
            "insights_delivered": insights_delivered,
            "questions_asked": questions_asked,
            "final_score": final_score,
            "logged_at": datetime.now().isoformat()
        }
        
        summary = f"Watched {game_name} for {duration_minutes} minutes. "
        summary += f"Delivered {insights_delivered} insights, answered {questions_asked} questions."
        if final_score:
            summary += f" Final: {final_score}"
        
        return {
            "status": "ok",
            "logged": True,
            "session_id": session_id,
            "summary": summary,
            "record": session_record
        }
        
    except Exception as e:
        return {
            "status": "error",
            "logged": False,
            "error_message": f"Error logging session: {str(e)}\n{traceback.format_exc()}"
        }

