"""
Request agent follow-up tool for Main Agent evaluation phase.

No-op tool that the orchestrator reads from the Letta API response
to extract follow-up instructions for specialist agents.
"""

from typing import Dict, Any


def request_agent_followup(agent_name: str, followup_prompt: str) -> Dict[str, Any]:
    """
    Request a follow-up search from a specialist agent during meeting prep evaluation.

    Call this tool for each agent that should refine its search based on your evaluation
    of the initial round of findings. The orchestrator will read these tool calls and
    dispatch the follow-up prompts to the specified agents.

    Valid agent names: calendar, document, email, pulse

    Args:
        agent_name: Name of the specialist agent to send follow-up to (calendar, document, email, pulse)
        followup_prompt: Specific instructions for what the agent should search for in the next round

    Returns:
        Dictionary confirming the follow-up was queued.
    """
    import traceback

    try:
        valid_agents = {"calendar", "document", "email", "pulse"}
        agent_lower = agent_name.strip().lower()

        if agent_lower not in valid_agents:
            return {
                "status": "error",
                "error_message": f"Invalid agent_name '{agent_name}'. Must be one of: {', '.join(sorted(valid_agents))}"
            }

        return {
            "status": "ok",
            "agent_name": agent_lower,
            "followup_prompt": followup_prompt,
            "message": f"Follow-up queued for {agent_lower} agent. The orchestrator will dispatch this."
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
