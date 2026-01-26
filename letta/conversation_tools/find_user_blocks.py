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

from typing import Dict, Any, List, Optional


def find_user_blocks(
    user_id: str,
    scope: Optional[str] = None
) -> Dict[str, Any]:
    """
    Discover all memory blocks for a user via naming convention.

    This tool is called by the agent to find blocks belonging to a specific user.
    Blocks are identified by naming convention: {category}_{user_id} or
    {agent_name}_{category}_{user_id}_{purpose}.

    Args:
        user_id: The user identifier (e.g., Slack user ID like "U12345678")
        scope: Filter scope - "all" (default), "cross_agent", or "agent_specific".
               "all" returns all blocks matching user_id.
               "cross_agent" returns only blocks WITHOUT agent name prefix (shared).
               "agent_specific" returns only blocks WITH agent name prefix.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - blocks: List of dicts with block info {id, label, value_preview}
        - count: Number of blocks found
        - error_message: Error message if status is "error"

    Example:
        >>> find_user_blocks(user_id="U12345678", scope="all")
        {
            "status": "ok",
            "blocks": [
                {"id": "block-abc", "label": "preferences_U12345678", "value_preview": "Prefers morning..."},
                {"id": "block-def", "label": "calendar_U12345678", "value_preview": "Calendar synced..."}
            ],
            "count": 2
        }
    """
    # IMPORTS FIRST - inside function for Letta tool extraction
    import os
    import re
    import traceback

    try:
        from letta_client import Letta
    except ImportError:
        try:
            from letta import Letta
        except ImportError:
            Letta = None

    # TRY-EXCEPT WRAPPER
    try:
        # SET DEFAULTS
        if scope is None:
            scope = "all"

        # CONFIGURATION - inside function for Letta tool extraction
        agent_name = os.getenv("AGENT_NAME", "meeting_scheduler")
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        letta_agent_id = os.getenv(
            "LETTA_AGENT_ID",
            os.getenv("SCHEDULER_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")
        )

        # INPUT VALIDATION
        if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
            return {
                "status": "error",
                "blocks": [],
                "count": 0,
                "error_message": f"Invalid user_id format: {user_id}. Must be alphanumeric with underscores/hyphens."
            }

        if scope not in ("all", "cross_agent", "agent_specific"):
            return {
                "status": "error",
                "blocks": [],
                "count": 0,
                "error_message": f"Invalid scope: {scope}. Must be 'all', 'cross_agent', or 'agent_specific'."
            }

        # GET AGENT BLOCKS (inline, no helper function)
        if Letta is None:
            return {
                "status": "error",
                "blocks": [],
                "count": 0,
                "error_message": "Letta client not available"
            }

        client = Letta(base_url=letta_base_url)
        agent = client.agents.retrieve(agent_id=letta_agent_id)
        all_blocks = agent.memory.blocks if agent.memory else []

        # FILTER BY USER_ID IN LABEL
        # Match patterns: {category}_{user_id} or {prefix}_{user_id}_{suffix}
        user_blocks = []
        for block in all_blocks:
            label = getattr(block, 'label', '') or ''
            # Check if user_id appears in label (either as suffix or in middle)
            if f"_{user_id}" in label or f"_{user_id}_" in label or label.endswith(f"_{user_id}"):
                user_blocks.append(block)

        # APPLY SCOPE FILTERING
        agent_prefix = f"{agent_name}_"

        if scope == "cross_agent":
            # Exclude blocks that start with agent name
            user_blocks = [b for b in user_blocks if not (getattr(b, 'label', '') or '').startswith(agent_prefix)]
        elif scope == "agent_specific":
            # Include only blocks that start with agent name
            user_blocks = [b for b in user_blocks if (getattr(b, 'label', '') or '').startswith(agent_prefix)]
        # scope == "all" returns everything matching user_id

        # FORMAT RESPONSE WITH VALUE PREVIEW
        result_blocks = []
        for block in user_blocks:
            value = getattr(block, 'value', '') or ''
            preview = value[:100] + "..." if len(value) > 100 else value
            result_blocks.append({
                "id": block.id,
                "label": getattr(block, 'label', ''),
                "value_preview": preview
            })

        return {
            "status": "ok",
            "blocks": result_blocks,
            "count": len(result_blocks)
        }

    except Exception as e:
        return {
            "status": "error",
            "blocks": [],
            "count": 0,
            "error_message": f"Failed to find user blocks: {str(e)}\n{traceback.format_exc()}"
        }
