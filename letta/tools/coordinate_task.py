"""
Coordination task tool for Main Agent.

Allows Main Agent to trigger multi-agent coordination
after gathering context conversationally.
"""

from typing import Dict, Any, Optional


def coordinate_task(
    task_type: str,
    context: str,
    questions_asked: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute multi-agent coordination for a defined task type.

    Call this after gathering sufficient context through conversation.
    Available task types can be found in docs/task-types/.

    Args:
        task_type: Name of the task type (e.g., "meeting_prep", "project_status")
        context: JSON string with task-specific context gathered from conversation.
                 Example: {"meeting_identifier": "Board Meeting tomorrow 2pm",
                          "focus_areas": ["participants", "documents"]}
        questions_asked: Optional JSON array of question IDs asked before execution.
                        Example: ["which_meeting", "focus_areas"]

    Returns:
        Dictionary with:
        - status: "complete", "partial", or "error"
        - synthesis: Synthesized response text
        - findings: Dict of agent name to contribution
        - agents_completed: List of agents that contributed
        - agents_failed: List of agents that failed/timed out
        - coordination_time_ms: Total coordination time
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import json
    import requests
    import traceback
    import os

    try:
        # Parse context JSON
        if isinstance(context, str):
            context_dict = json.loads(context)
        else:
            context_dict = context

        # Parse questions if provided
        questions = []
        if questions_asked:
            if isinstance(questions_asked, str):
                questions = json.loads(questions_asked)
            else:
                questions = questions_asked

        # Get routing handler URL from environment
        routing_handler_url = os.getenv(
            "PA_ROUTING_HANDLER_URL",
            "http://pa-routing-handler:5201"
        )

        # Get identity ID from environment or use default
        identity_id = os.getenv("CURRENT_IDENTITY_ID", "identity-default")

        # Call coordination endpoint
        response = requests.post(
            f"{routing_handler_url}/v1/coordinate",
            json={
                "identity_id": identity_id,
                "task_type": task_type,
                "context": context_dict,
                "questions_asked": questions
            },
            timeout=120  # 2 minute timeout for full coordination
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Coordination failed: {response.status_code} - {response.text[:500]}"
            }

        result = response.json()

        return {
            "status": result.get("status", "unknown"),
            "synthesis": result.get("synthesis", ""),
            "findings": result.get("findings", {}),
            "agents_completed": result.get("agents_completed", []),
            "agents_failed": result.get("agents_failed", []),
            "coordination_time_ms": result.get("coordination_time_ms")
        }

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error_message": f"Invalid JSON in context: {str(e)}"
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error_message": "Coordination timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }
