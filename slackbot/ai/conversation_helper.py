"""
Conversation helper for multi-user Letta Conversations.

Handles looking up and creating conversations for Slack users,
enabling per-user context isolation in the scheduler agent.

Architecture Note (2026-01-26):
- Uses tool-based permission approach since isolated_block_labels
  doesn't provide memory isolation (confirmed bug in Letta 0.16.3)
- Conversations are looked up/stored in Supabase user_conversations table
- Falls back to legacy agent-level messaging if lookup/creation fails
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Default scheduler agent - configurable via env var
DEFAULT_SCHEDULER_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
SCHEDULER_AGENT_ID = os.getenv("LETTA_SCHEDULER_AGENT_ID", DEFAULT_SCHEDULER_AGENT_ID)


class ConversationHelper:
    """
    Helper for managing Letta Conversations for Slack users.

    Provides conversation lookup and creation with graceful fallback
    to legacy agent-level messaging when Supabase/Letta fails.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self._supabase_available = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

        if not self._supabase_available:
            self.logger.warning(
                "Supabase not configured - conversations will use legacy agent-level messaging"
            )

    def get_or_create_conversation(
        self,
        user_id: str,
        agent_id: str | None = None,
    ) -> Optional[str]:
        """
        Get existing conversation or create new one for user.

        Args:
            user_id: Slack user ID (e.g., "U12345678")
            agent_id: Letta agent ID (defaults to scheduler agent)

        Returns:
            conversation_id if successful, None to fall back to legacy behavior
        """
        if not self._supabase_available:
            self.logger.debug("Supabase not available, using legacy agent messaging")
            return None

        agent_id = agent_id or SCHEDULER_AGENT_ID
        user_source = "slack"

        # Try to find existing conversation
        existing = self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            self.logger.info(
                "Found existing conversation for user %s: %s",
                user_id,
                existing
            )
            # Update last_active_at in background (fire and forget)
            self._update_last_active(user_id, user_source, agent_id)
            return existing

        # Create new conversation
        self.logger.info("Creating new conversation for user %s", user_id)
        return self._create_conversation(user_id, user_source, agent_id)

    def _lookup_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[str]:
        """Look up existing conversation in Supabase."""
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            params = {
                "select": "conversation_id",
                "user_id": f"eq.{user_id}",
                "user_source": f"eq.{user_source}",
                "agent_id": f"eq.{agent_id}",
                "limit": "1"
            }
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, params=params, headers=headers, timeout=5.0)
            response.raise_for_status()

            data = response.json()
            if data and len(data) > 0:
                return data[0].get("conversation_id")
            return None

        except Exception as e:
            self.logger.warning("Conversation lookup failed: %s", e)
            return None

    def _create_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[str]:
        """Create new conversation via Letta API and store mapping."""
        try:
            # Create initial preference block with naming convention
            self._create_user_block(
                user_id=user_id,
                agent_id=agent_id,
                label=f"preferences_{user_id}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {user_id}"
            )

            # Create conversation via Letta
            letta_url = f"{LETTA_BASE_URL}/v1/conversations/"
            params = {"agent_id": agent_id}
            body = {"label": f"{user_id} - Slack"}

            response = requests.post(
                letta_url,
                params=params,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
            response.raise_for_status()

            conversation_data = response.json()
            conversation_id = conversation_data.get("id")

            if not conversation_id:
                self.logger.error("Letta returned no conversation ID")
                return None

            # Store mapping in Supabase
            self._store_conversation_mapping(
                user_id=user_id,
                user_source=user_source,
                agent_id=agent_id,
                conversation_id=conversation_id
            )

            self.logger.info(
                "Created conversation %s for user %s",
                conversation_id,
                user_id
            )
            return conversation_id

        except Exception as e:
            self.logger.error("Failed to create conversation: %s", e)
            return None

    def _create_user_block(
        self,
        user_id: str,
        agent_id: str,
        label: str,
        value: str,
        description: str
    ) -> Optional[str]:
        """Create a user-specific block and attach to agent."""
        try:
            # Create block
            create_url = f"{LETTA_BASE_URL}/v1/blocks/"
            block_body = {
                "label": label,
                "value": value,
                "description": description,
                "limit": 2000
            }

            response = requests.post(
                create_url,
                json=block_body,
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
            response.raise_for_status()

            block_data = response.json()
            block_id = block_data.get("id")

            if block_id:
                # Attach to agent via core-memory endpoint (PATCH method)
                attach_url = f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}"
                attach_response = requests.patch(
                    attach_url,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0
                )
                attach_response.raise_for_status()
                self.logger.info("Created and attached block %s for user %s", label, user_id)
                return block_id

            return None

        except Exception as e:
            self.logger.warning("Failed to create user block: %s", e)
            return None

    def _store_conversation_mapping(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        conversation_id: str
    ) -> bool:
        """Store user-conversation mapping in Supabase."""
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            body = {
                "user_id": user_id,
                "user_source": user_source,
                "agent_id": agent_id,
                "conversation_id": conversation_id
            }

            response = requests.post(url, json=body, headers=headers, timeout=5.0)
            response.raise_for_status()
            return True

        except Exception as e:
            self.logger.warning("Failed to store conversation mapping: %s", e)
            return False

    def _update_last_active(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> None:
        """Update last_active_at timestamp (fire and forget)."""
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            params = {
                "user_id": f"eq.{user_id}",
                "user_source": f"eq.{user_source}",
                "agent_id": f"eq.{agent_id}"
            }
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            body = {"last_active_at": datetime.now(timezone.utc).isoformat()}

            requests.patch(url, params=params, json=body, headers=headers, timeout=2.0)
        except Exception:
            pass  # Fire and forget


# Module-level singleton
_conversation_helper: Optional[ConversationHelper] = None


def get_conversation_helper(logger: logging.Logger | None = None) -> ConversationHelper:
    """Get or create the conversation helper singleton."""
    global _conversation_helper
    if _conversation_helper is None:
        _conversation_helper = ConversationHelper(logger=logger)
    return _conversation_helper


def get_conversation_for_user(
    user_id: str,
    agent_id: str | None = None,
    logger: logging.Logger | None = None
) -> Optional[str]:
    """
    Convenience function to get conversation_id for a Slack user.

    Args:
        user_id: Slack user ID
        agent_id: Optional agent ID (defaults to scheduler)
        logger: Optional logger

    Returns:
        conversation_id or None (to use legacy agent messaging)
    """
    helper = get_conversation_helper(logger)
    return helper.get_or_create_conversation(user_id, agent_id)
