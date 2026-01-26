"""
Conversation service for managing user→conversation mappings.

Handles:
- Looking up existing conversations for user+agent pairs
- Creating new conversations with Letta Conversations API
- Creating initial user blocks on onboarding (with naming conventions)
- Tracking conversation activity via last_active_at

Architecture Note (2026-01-26):
- Uses tool-based permission approach since `isolated_block_labels` doesn't
  provide memory isolation (confirmed bug in Letta 0.16.3)
- `tool_variables` does not exist in Letta 0.16.3 API
- Blocks are created with naming convention: {category}_{user_id}
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = structlog.get_logger()

# Default scheduler agent ID
SCHEDULER_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
AGENT_NAME = "meeting_scheduler"


class ConversationService:
    """
    Manages Letta Conversations for multi-user agent access.

    Each user gets a unique conversation with the agent, enabling:
    - Isolated message history (context) per user
    - Per-user memory blocks via naming conventions
    - Activity tracking for potential TTL/cleanup
    """

    def __init__(self, letta_client: Any, supabase_client: Any):
        """
        Initialize the conversation service.

        Args:
            letta_client: Letta client instance
            supabase_client: Supabase client instance
        """
        self.letta = letta_client
        self.supabase = supabase_client

    async def get_or_create_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get existing conversation or create new one for user+agent pair.

        This is the main entry point for conversation resolution. If a mapping
        exists in Supabase, returns the existing conversation_id. Otherwise,
        creates a new conversation and onboards the user.

        Args:
            user_id: External user identifier (e.g., Slack user ID "U12345678")
            user_source: Source platform ("slack", "email", "web")
            agent_id: Letta agent ID to converse with
            display_name: Optional user display name for identity
            email: Optional user email for identity

        Returns:
            dict with keys:
            - conversation_id: The Letta conversation ID
            - identity_id: The Letta identity ID (if created)
            - created: bool indicating if this is a new conversation
            - error: Only present if there was an error
        """
        # Try to find existing conversation
        existing = await self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            logger.info(
                "conversation_found",
                user_id=user_id,
                conversation_id=existing["conversation_id"]
            )
            return {
                "conversation_id": existing["conversation_id"],
                "identity_id": existing.get("identity_id"),
                "created": False
            }

        # Create new conversation
        logger.info(
            "conversation_creating",
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id
        )
        return await self._onboard_user(
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            display_name=display_name or user_id,
            email=email
        )

    async def _lookup_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Look up existing conversation in Supabase.

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID

        Returns:
            dict with conversation_id and identity_id if found, None otherwise
        """
        try:
            result = (
                self.supabase.table("user_conversations")
                .select("conversation_id, identity_id")
                .eq("user_id", user_id)
                .eq("user_source", user_source)
                .eq("agent_id", agent_id)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("conversation_lookup_failed", error=str(e), user_id=user_id)
            return None

    async def _onboard_user(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: str,
        email: Optional[str]
    ) -> Dict[str, Any]:
        """
        Create conversation and initial resources for new user.

        This creates:
        1. Initial preference block with naming convention
        2. Initial calendar block with naming convention
        3. Letta identity (optional, for future identity linking)
        4. Letta conversation
        5. Supabase mapping record

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID
            display_name: User display name
            email: Optional user email

        Returns:
            dict with conversation_id, identity_id, and created=True
        """
        identity_id = None
        block_ids = []

        # Create initial preference block with naming convention
        try:
            pref_block = self.letta.blocks.create(
                label=f"preferences_{user_id}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {user_id}",
                limit=2000
            )
            block_ids.append(pref_block.id)

            # Attach to agent
            self.letta.agents.blocks.attach(
                agent_id=agent_id,
                block_id=pref_block.id
            )
            logger.info("preference_block_created", user_id=user_id, block_id=pref_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="preferences")

        # Create initial calendar block with naming convention
        try:
            cal_block = self.letta.blocks.create(
                label=f"calendar_{user_id}",
                value="Calendar integration pending configuration. This block stores calendar context for this user.",
                description=f"Calendar integration for {user_id}",
                limit=2000
            )
            block_ids.append(cal_block.id)

            # Attach to agent
            self.letta.agents.blocks.attach(
                agent_id=agent_id,
                block_id=cal_block.id
            )
            logger.info("calendar_block_created", user_id=user_id, block_id=cal_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="calendar")

        # Create Letta identity (optional, for future identity linking)
        try:
            identity_properties = {"source": user_source}
            if email:
                identity_properties["email"] = email

            identity = self.letta.identities.create(
                identifier_key=user_id,
                name=display_name,
                identity_type="user",
                properties=identity_properties
            )
            identity_id = identity.id
            logger.info("identity_created", user_id=user_id, identity_id=identity_id)
        except Exception as e:
            logger.warning("identity_creation_failed", error=str(e), user_id=user_id)

        # Create conversation
        try:
            conversation = self.letta.conversations.create(
                agent_id=agent_id,
                label=f"{user_id} - {user_source.capitalize()}"
            )
            conversation_id = conversation.id
            logger.info("conversation_created", user_id=user_id, conversation_id=conversation_id)
        except Exception as e:
            logger.error("conversation_creation_failed", error=str(e), user_id=user_id)
            return {
                "error": f"Failed to create conversation: {str(e)}",
                "created": False
            }

        # Store mapping in Supabase
        try:
            self.supabase.table("user_conversations").insert({
                "user_id": user_id,
                "user_source": user_source,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "identity_id": identity_id
            }).execute()
            logger.info("mapping_stored", user_id=user_id, conversation_id=conversation_id)
        except Exception as e:
            logger.error(
                "conversation_mapping_insert_failed",
                error=str(e),
                user_id=user_id,
                conversation_id=conversation_id
            )
            # Don't fail the whole operation - conversation was created successfully
            # The mapping can be retried or recovered manually

        logger.info(
            "user_onboarded",
            user_id=user_id,
            conversation_id=conversation_id,
            identity_id=identity_id,
            block_count=len(block_ids)
        )

        return {
            "conversation_id": conversation_id,
            "identity_id": identity_id,
            "created": True
        }

    async def update_last_active(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> None:
        """
        Update last_active_at timestamp for a conversation.

        This is called after each message to track activity for potential
        TTL/cleanup operations.

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID
        """
        try:
            self.supabase.table("user_conversations").update({
                "last_active_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("user_source", user_source).eq("agent_id", agent_id).execute()
            logger.debug("last_active_updated", user_id=user_id)
        except Exception as e:
            logger.warning("last_active_update_failed", error=str(e), user_id=user_id)
