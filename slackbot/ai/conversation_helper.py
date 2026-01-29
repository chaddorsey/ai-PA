"""
Conversation helper for multi-user Letta Conversations.

Handles looking up and creating conversations for users across platforms,
enabling per-identity context isolation in the scheduler agent.

Architecture (2026-01-28):
- ONE conversation per identity per agent (shared across all platforms)
- Identity resolved from platform-specific ID (Slack ID, email, etc.)
- Falls back to legacy agent-level messaging if identity cannot be resolved
- Conversations stored in Supabase user_conversations table, keyed by identity_id

Cross-Platform Support:
- Same identity messaging from Slack and Web shares one conversation
- Memory blocks and conversation history unified across platforms
- Platform tracking is external (for analytics), not in Letta
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
    Helper for managing Letta Conversations by identity.

    Key principle: ONE conversation per identity per agent, shared across
    all platforms (Slack, Web, etc.). This ensures unified context.

    Falls back to legacy agent-level messaging when:
    - Identity cannot be resolved (unknown user)
    - Supabase is not configured
    - Any error occurs during lookup/creation
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._supabase_available = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

        if not self._supabase_available:
            self.logger.warning(
                "Supabase not configured - conversations will use legacy agent-level messaging"
            )

    def get_or_create_conversation(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        user_source: str = "slack",
    ) -> Optional[str]:
        """
        Get existing conversation or create new one for user's identity.

        Flow:
        1. Resolve platform user_id to Letta identity
        2. If no identity found → return None (fall back to legacy)
        3. Look up conversation by identity_id + agent_id
        4. If found → return existing conversation_id
        5. If not found → create new conversation for this identity

        Args:
            user_id: Platform-specific user ID (Slack ID, email, etc.)
            agent_id: Letta agent ID (defaults to scheduler agent)
            user_source: Platform name for identity resolution ("slack", "web", "email")

        Returns:
            conversation_id if successful, None to fall back to legacy behavior
        """
        if not self._supabase_available:
            self.logger.debug("Supabase not available, using legacy agent messaging")
            return None

        agent_id = agent_id or SCHEDULER_AGENT_ID

        # Step 1: Resolve identity from platform user_id
        identity = self._resolve_identity(user_id, user_source)
        if not identity or not identity.get("id"):
            self.logger.info(
                "No identity found for %s user %s, using legacy agent messaging",
                user_source,
                user_id
            )
            return None

        identity_id = identity["id"]
        identity_name = identity.get("name")

        # Step 2: Look up existing conversation by identity_id + agent_id
        existing = self._lookup_conversation(identity_id, agent_id)
        if existing:
            self.logger.info(
                "Found existing conversation for %s (identity %s): %s",
                identity_name or user_id,
                identity_id,
                existing
            )
            # Update last_active_at (fire and forget)
            self._update_last_active(identity_id, agent_id)
            return existing

        # Step 3: Create new conversation for this identity
        self.logger.info(
            "Creating new conversation for %s (identity %s)",
            identity_name or user_id,
            identity_id
        )
        return self._create_conversation(
            identity_id=identity_id,
            identity_name=identity_name,
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id
        )

    def _resolve_identity(self, user_id: str, user_source: str) -> Optional[Dict[str, Any]]:
        """
        Resolve platform user ID to Letta identity.

        Looks up the identity by the appropriate property based on user_source:
        - slack: looks up by slack_id property
        - web/email: looks up by identifier_key (email)

        Args:
            user_id: Platform-specific user ID (Slack ID, email, etc.)
            user_source: Platform name ("slack", "web", "email")

        Returns:
            Identity dict with 'id', 'name', and 'email' keys, or None if not found
        """
        try:
            # Fetch all identities from Letta
            response = requests.get(
                f"{LETTA_BASE_URL}/v1/identities/",
                timeout=5.0
            )
            response.raise_for_status()
            identities = response.json()

            # Search by appropriate property based on source
            for identity in identities:
                # For Slack, look up by slack_id property
                if user_source == "slack":
                    for prop in identity.get("properties", []):
                        if prop.get("key") == "slack_id" and prop.get("value") == user_id:
                            self.logger.info(
                                "Resolved Slack user %s to identity %s (%s)",
                                user_id,
                                identity.get("id"),
                                identity.get("name")
                            )
                            return {
                                "id": identity.get("id"),
                                "name": identity.get("name"),
                                "email": identity.get("identifier_key")
                            }

                # For web/email, look up by identifier_key
                elif user_source in ("web", "email"):
                    if identity.get("identifier_key", "").lower() == user_id.lower():
                        self.logger.info(
                            "Resolved email %s to identity %s (%s)",
                            user_id,
                            identity.get("id"),
                            identity.get("name")
                        )
                        return {
                            "id": identity.get("id"),
                            "name": identity.get("name"),
                            "email": identity.get("identifier_key")
                        }

            self.logger.debug("No identity found for %s user %s", user_source, user_id)
            return None

        except Exception as e:
            self.logger.warning("Identity resolution failed for %s: %s", user_id, e)
            return None

    def _lookup_conversation(
        self,
        identity_id: str,
        agent_id: str
    ) -> Optional[str]:
        """Look up existing conversation by identity_id + agent_id."""
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            params = {
                "select": "conversation_id",
                "identity_id": f"eq.{identity_id}",
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
        identity_id: str,
        identity_name: Optional[str],
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[str]:
        """Create new conversation via Letta API and store mapping."""
        try:
            # Create initial preference block with naming convention
            # Use identity_id in label for uniqueness across platforms
            self._create_user_block(
                identity_id=identity_id,
                agent_id=agent_id,
                label=f"preferences_{identity_id}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {identity_name or identity_id}"
            )

            # Build conversation label - just use name (no platform since shared)
            label = identity_name or identity_id

            # Create conversation via Letta
            letta_url = f"{LETTA_BASE_URL}/v1/conversations/"
            params = {"agent_id": agent_id}
            body = {"label": label}

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

            # Store mapping in Supabase (keyed by identity_id)
            self._store_conversation_mapping(
                identity_id=identity_id,
                user_id=user_id,
                user_source=user_source,
                agent_id=agent_id,
                conversation_id=conversation_id
            )

            self.logger.info(
                "Created conversation %s for identity %s (%s)",
                conversation_id,
                identity_id,
                identity_name or "unknown"
            )
            return conversation_id

        except Exception as e:
            self.logger.error("Failed to create conversation: %s", e)
            return None

    def _create_user_block(
        self,
        identity_id: str,
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
                self.logger.info("Created and attached block %s for identity %s", label, identity_id)
                return block_id

            return None

        except Exception as e:
            self.logger.warning("Failed to create user block: %s", e)
            return None

    def _store_conversation_mapping(
        self,
        identity_id: str,
        user_id: str,
        user_source: str,
        agent_id: str,
        conversation_id: str
    ) -> bool:
        """Store identity-conversation mapping in Supabase.

        Args:
            identity_id: Letta identity ID (primary lookup key)
            user_id: Platform-specific user ID (for reference/debugging)
            user_source: Platform name (for reference/debugging)
            agent_id: Letta agent ID
            conversation_id: Letta conversation ID
        """
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            body = {
                "identity_id": identity_id,
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
        identity_id: str,
        agent_id: str
    ) -> None:
        """Update last_active_at timestamp (fire and forget)."""
        try:
            url = f"{SUPABASE_URL}/user_conversations"
            params = {
                "identity_id": f"eq.{identity_id}",
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


def get_conversation_helper(logger: Optional[logging.Logger] = None) -> ConversationHelper:
    """Get or create the conversation helper singleton."""
    global _conversation_helper
    if _conversation_helper is None:
        _conversation_helper = ConversationHelper(logger=logger)
    return _conversation_helper


def get_conversation_for_user(
    user_id: str,
    agent_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    user_source: str = "slack"
) -> Optional[str]:
    """
    Convenience function to get conversation_id for a user.

    Args:
        user_id: Platform-specific user ID (Slack ID, email, etc.)
        agent_id: Optional agent ID (defaults to scheduler)
        logger: Optional logger
        user_source: Platform name for identity resolution

    Returns:
        conversation_id or None (to use legacy agent messaging)
    """
    helper = get_conversation_helper(logger)
    return helper.get_or_create_conversation(user_id, agent_id, user_source)
