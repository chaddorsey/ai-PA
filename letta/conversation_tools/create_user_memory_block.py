"""
Create user memory blocks with naming convention enforcement.

This tool creates new memory blocks for emergent user preferences,
using naming conventions to enable per-user block discovery.

Architecture Note (2026-01-26):
- Permission enforcement is "soft" via naming conventions
- `tool_variables` does not exist in Letta 0.16.3
- Agent is trusted to pass correct user_id via system prompt instructions
- Blocks are created and attached to the agent for the specified user
"""

from typing import Dict, Any, Optional


def create_user_memory_block(
    user_id: str,
    category: str,
    value: str,
    purpose: Optional[str] = None,
    agent_specific: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Create a new memory block for emergent user preferences.

    This tool is called by the agent when it learns something new about a user
    that should be persisted. The block is created with a naming convention
    that enables later discovery via find_user_blocks.

    Naming conventions:
    - Cross-agent: {category}_{user_id}[_{purpose}]
    - Agent-specific: {agent_name}_{category}_{user_id}[_{purpose}]

    Args:
        user_id: The user identifier (e.g., Slack user ID like "U12345678")
        category: Block category (e.g., "preferences", "calendar", "context")
        value: Initial block content (max 2000 characters)
        purpose: Optional specific purpose (e.g., "meeting_duration", "timezone")
        agent_specific: If True, prefix with agent name (only this agent sees it). Default: False.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - block_id: ID of created block (if successful)
        - label: Label of created block (if successful)
        - error_message: Error message if status is "error"

    Example:
        >>> create_user_memory_block(
        ...     user_id="U12345678",
        ...     category="preferences",
        ...     value="Prefers 30 minute meetings in the morning",
        ...     purpose="meeting_duration"
        ... )
        {"status": "ok", "block_id": "block-abc123", "label": "preferences_U12345678_meeting_duration"}
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
        if agent_specific is None:
            agent_specific = False

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
                "error_message": f"Invalid user_id format: {user_id}. Must be alphanumeric with underscores/hyphens."
            }

        if not re.match(r'^[a-zA-Z0-9_-]+$', category):
            return {
                "status": "error",
                "error_message": f"Invalid category format: {category}. Must be alphanumeric with underscores/hyphens."
            }

        if purpose and not re.match(r'^[a-zA-Z0-9_-]+$', purpose):
            return {
                "status": "error",
                "error_message": f"Invalid purpose format: {purpose}. Must be alphanumeric with underscores/hyphens."
            }

        if len(value) > 2000:
            return {
                "status": "error",
                "error_message": f"Block value too long ({len(value)} chars). Maximum is 2000 characters."
            }

        # BUILD LABEL BASED ON NAMING CONVENTION
        if agent_specific:
            label = f"{agent_name}_{category}_{user_id}"
        else:
            label = f"{category}_{user_id}"

        if purpose:
            label += f"_{purpose}"

        # Normalize label
        label = label.lower().replace(" ", "_")

        if len(label) > 200:
            return {
                "status": "error",
                "error_message": f"Block label too long ({len(label)} chars). Maximum is 200 characters."
            }

        # GET LETTA CLIENT (inline, no helper function)
        if Letta is None:
            return {
                "status": "error",
                "error_message": "Letta client not available. Check LETTA_BASE_URL configuration."
            }

        client = Letta(base_url=letta_base_url)

        # CREATE THE BLOCK
        description = f"{category} for {user_id}"
        if purpose:
            description += f": {purpose}"

        block = client.blocks.create(
            label=label,
            value=value,
            description=description,
            limit=2000
        )

        # ATTACH BLOCK TO AGENT
        client.agents.blocks.attach(
            agent_id=letta_agent_id,
            block_id=block.id
        )

        return {
            "status": "ok",
            "block_id": block.id,
            "label": label
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to create block: {str(e)}\n{traceback.format_exc()}"
        }
