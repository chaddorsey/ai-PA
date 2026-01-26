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

import os
import re
from typing import Dict, Any, Optional

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        Letta = None


# Configuration from environment
AGENT_NAME = os.getenv("AGENT_NAME", "meeting_scheduler")
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_AGENT_ID = os.getenv(
    "LETTA_AGENT_ID",
    os.getenv("SCHEDULER_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")
)


def _get_letta_client():
    """
    Get Letta client instance.

    Returns Letta client or None if unavailable.
    """
    if Letta is None:
        return None
    try:
        return Letta(base_url=LETTA_BASE_URL)
    except Exception:
        return None


def create_user_memory_block(
    user_id: str,
    category: str,
    value: str,
    purpose: Optional[str] = None,
    agent_specific: bool = False
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
        agent_specific: If True, prefix with agent name (only this agent sees it)

    Returns:
        dict with block_id and label on success.
        dict with "error" key on failure.

    Example:
        >>> create_user_memory_block(
        ...     user_id="U12345678",
        ...     category="preferences",
        ...     value="Prefers 30 minute meetings in the morning",
        ...     purpose="meeting_duration"
        ... )
        {"block_id": "block-abc123", "label": "preferences_U12345678_meeting_duration"}
    """
    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": f"Invalid user_id format: {user_id}. Must be alphanumeric with underscores/hyphens."}

    if not re.match(r'^[a-zA-Z0-9_-]+$', category):
        return {"error": f"Invalid category format: {category}. Must be alphanumeric with underscores/hyphens."}

    if purpose and not re.match(r'^[a-zA-Z0-9_-]+$', purpose):
        return {"error": f"Invalid purpose format: {purpose}. Must be alphanumeric with underscores/hyphens."}

    if len(value) > 2000:
        return {"error": f"Block value too long ({len(value)} chars). Maximum is 2000 characters."}

    # Build label based on naming convention
    if agent_specific:
        label = f"{AGENT_NAME}_{category}_{user_id}"
    else:
        label = f"{category}_{user_id}"

    if purpose:
        label += f"_{purpose}"

    # Normalize label
    label = label.lower().replace(" ", "_")

    if len(label) > 200:
        return {"error": f"Block label too long ({len(label)} chars). Maximum is 200 characters."}

    # Get Letta client
    client = _get_letta_client()
    if client is None:
        return {"error": "Letta client not available. Check LETTA_BASE_URL configuration."}

    # Create the block
    try:
        description = f"{category} for {user_id}"
        if purpose:
            description += f": {purpose}"

        block = client.blocks.create(
            label=label,
            value=value,
            description=description,
            limit=2000
        )

        # Attach block to agent
        client.agents.blocks.attach(
            agent_id=LETTA_AGENT_ID,
            block_id=block.id
        )

        return {
            "block_id": block.id,
            "label": label
        }

    except Exception as e:
        return {"error": f"Failed to create block: {str(e)}"}
