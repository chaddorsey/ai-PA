"""
Task execution analysis tool for Main Agent.

Enables guided refinement by analyzing execution patterns.
"""

from typing import Dict, Any, Optional


def analyze_task_executions(
    task_type: str,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyze recent executions of a task type for refinement.

    Use this to review how a task type is performing and identify
    opportunities for improvement.

    Args:
        task_type: Name of the task type to analyze (e.g., "meeting_prep")
        limit: Optional number of recent executions to analyze (default: 10)

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - executions: Number of executions analyzed
        - avg_time_ms: Average coordination time
        - agent_stats: Per-agent contribution statistics
        - question_patterns: Which questions were asked most often
        - recommendations: Suggested improvements based on patterns
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import requests
    import traceback
    import os

    try:
        # Get routing handler URL
        routing_handler_url = os.getenv(
            "PA_ROUTING_HANDLER_URL",
            "http://pa-routing-handler:5201"
        )

        # Build query params
        params = {"task_type": task_type}
        if limit:
            params["limit"] = limit

        # Call analysis endpoint
        response = requests.get(
            f"{routing_handler_url}/v1/coordinate/analysis",
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Analysis failed: {response.status_code}"
            }

        data = response.json()

        # Check for error in response
        if "error" in data:
            return {
                "status": "error",
                "error_message": data["error"]
            }

        # Generate recommendations based on patterns
        recommendations = []

        agent_stats = data.get("agent_stats", {})
        for agent, stats in agent_stats.items():
            dispatches = stats.get("dispatches", 0)
            contributions = stats.get("contributions", 0)
            if dispatches > 0:
                contribution_rate = contributions / dispatches * 100
                if contribution_rate < 50:
                    recommendations.append(
                        f"Consider disabling '{agent}' - only {contribution_rate:.0f}% contribution rate"
                    )

        question_patterns = data.get("question_patterns", {})
        executions = data.get("executions", 0)
        for question, count in question_patterns.items():
            if count == executions and executions >= 3:
                recommendations.append(
                    f"Question '{question}' asked every time - consider making it required or auto-detecting"
                )

        return {
            "status": "ok",
            "executions": data.get("executions", 0),
            "avg_time_ms": data.get("avg_time_ms", 0),
            "agent_stats": agent_stats,
            "question_patterns": question_patterns,
            "recommendations": recommendations
        }

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error_message": "Analysis request timed out"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }
