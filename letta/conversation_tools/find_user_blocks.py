"""
Find user memory blocks via naming convention filtering.

This tool discovers memory blocks for a user by filtering all agent blocks
based on naming conventions (e.g., "preferences_{user_id}").

Architecture Note (2026-01-26):
- Permission enforcement is "soft" via naming conventions
- `tool_variables` does not exist in Letta 0.16.3
- Agent is trusted to pass correct user_id via system prompt instructions
- This tool filters blocks but cannot prevent agent from requesting other users
"""

import os
import re
from typing import Dict, Any, List, Union

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        Letta = None


# Agent name for filtering agent-specific blocks
AGENT_NAME = os.getenv("AGENT_NAME", "meeting_scheduler")
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_AGENT_ID = os.getenv(
    "LETTA_AGENT_ID",
    os.getenv("SCHEDULER_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")
)


def _get_agent_blocks() -> List[Any]:
    """
    Fetch all memory blocks attached to the current agent.

    Returns list of block objects from Letta API.
    """
    if Letta is None:
        return []

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        agent = client.agents.retrieve(agent_id=LETTA_AGENT_ID)
        return agent.memory.blocks if agent.memory else []
    except Exception:
        return []


def find_user_blocks(
    user_id: str,
    scope: str = "all"
) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """
    Discover all memory blocks for a user via naming convention.

    This tool is called by the agent to find blocks belonging to a specific user.
    Blocks are identified by naming convention: {category}_{user_id} or
    {agent_name}_{category}_{user_id}_{purpose}.

    Args:
        user_id: The user identifier (e.g., Slack user ID like "U12345678")
        scope: Filter scope:
            - "all": Return all blocks matching user_id
            - "cross_agent": Only blocks WITHOUT agent name prefix (shared across agents)
            - "agent_specific": Only blocks WITH agent name prefix (this agent only)

    Returns:
        List of dicts with block info: {id, label, value_preview}
        Or dict with "error" key on validation failure.

    Example:
        >>> find_user_blocks(user_id="U12345678", scope="all")
        [
            {"id": "block-abc", "label": "preferences_U12345678", "value_preview": "Prefers morning..."},
            {"id": "block-def", "label": "calendar_U12345678", "value_preview": "Calendar synced..."}
        ]
    """
    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": f"Invalid user_id format: {user_id}. Must be alphanumeric with underscores/hyphens."}

    if scope not in ("all", "cross_agent", "agent_specific"):
        return {"error": f"Invalid scope: {scope}. Must be 'all', 'cross_agent', or 'agent_specific'."}

    # Fetch all blocks attached to agent
    try:
        all_blocks = _get_agent_blocks()
    except Exception as e:
        return {"error": f"Failed to retrieve blocks: {str(e)}"}

    # Filter by user_id in label
    # Match patterns: {category}_{user_id} or {prefix}_{user_id}_{suffix}
    user_blocks = []
    for block in all_blocks:
        label = getattr(block, 'label', '') or ''
        # Check if user_id appears in label (either as suffix or in middle)
        if f"_{user_id}" in label or f"_{user_id}_" in label or label.endswith(f"_{user_id}"):
            user_blocks.append(block)

    # Apply scope filtering
    agent_prefix = f"{AGENT_NAME}_"

    if scope == "cross_agent":
        # Exclude blocks that start with agent name
        user_blocks = [b for b in user_blocks if not b.label.startswith(agent_prefix)]
    elif scope == "agent_specific":
        # Include only blocks that start with agent name
        user_blocks = [b for b in user_blocks if b.label.startswith(agent_prefix)]
    # scope == "all" returns everything matching user_id

    # Format response with value preview
    result = []
    for block in user_blocks:
        value = getattr(block, 'value', '') or ''
        preview = value[:100] + "..." if len(value) > 100 else value
        result.append({
            "id": block.id,
            "label": block.label,
            "value_preview": preview
        })

    return result
