"""
Conversation service for managing user->conversation mappings.

Handles:
- Looking up existing conversations for user+agent pairs
- Creating new conversations with Letta Conversations API
- Resolving user identity via IdentityService before conversation creation
- Creating initial user blocks on onboarding (with identity-based naming)
- Tracking conversation activity via last_active_at

Architecture Note (2026-01-26):
- Uses IdentityService to recognize known staff by platform ID
- Falls back to creating external identity for unknown users
- Block naming uses identity_id for cross-platform coherence
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = structlog.get_logger()

SCHEDULER_AGENT_ID = "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"
AGENT_NAME = "meeting_scheduler"


class ConversationService:
    """Manages Letta Conversations for multi-user agent access."""

    def __init__(
        self,
        letta_client: Any,
        supabase_client: Any,
        identity_service: Optional[Any] = None
    ):
        self.letta = letta_client
        self.supabase = supabase_client
        self.identity_service = identity_service

    async def get_or_create_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get existing conversation or create new one for user+agent pair."""
        # Try to find existing conversation
        existing = await self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            logger.info("conversation_found", user_id=user_id, conversation_id=existing["conversation_id"])
            return {
                "conversation_id": existing["conversation_id"],
                "identity_id": existing.get("identity_id"),
                "created": False
            }

        # Resolve identity before creating conversation
        identity = await self._resolve_identity(user_id, user_source, display_name, email)

        # Create new conversation
        logger.info(
            "conversation_creating",
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            identity_id=identity.id if identity else None
        )
        return await self._onboard_user(
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            identity=identity,
            display_name=display_name or user_id,
            email=email
        )

    async def _resolve_identity(
        self,
        user_id: str,
        user_source: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[Any]:
        """Resolve user identity from platform ID."""
        if not self.identity_service:
            return None

        property_key = f"{user_source}_id"  # e.g., "slack_id"

        # Try to find existing identity by platform ID
        identity = self.identity_service.find_by_property(property_key, user_id)
        if identity:
            logger.info(
                "staff_identity_found",
                user_id=user_id,
                identity_id=identity.id,
                identity_name=getattr(identity, 'name', 'Unknown')
            )
            return identity

        # Try by email if provided
        if email:
            identity = self.identity_service.find_by_identifier_key(email)
            if identity:
                logger.info("staff_identity_found_by_email", user_id=user_id, email=email, identity_id=identity.id)
                return identity

        # Create external identity for unknown user
        try:
            identity = self.identity_service.create_external_user(
                platform=user_source,
                platform_id=user_id,
                display_name=display_name
            )
            logger.info("external_identity_created", user_id=user_id, identity_id=identity.id)
            return identity
        except Exception as e:
            logger.warning("identity_resolution_failed", error=str(e), user_id=user_id)
            return None

    async def _lookup_conversation(
        self, user_id: str, user_source: str, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up existing conversation in Supabase."""
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
        identity: Optional[Any],
        display_name: str,
        email: Optional[str]
    ) -> Dict[str, Any]:
        """Create conversation and initial resources for new user."""
        identity_id = identity.id if identity else None
        block_user_key = identity_id if identity_id else user_id
        block_ids = []

        # Create preference block with identity-based naming
        try:
            pref_block = self.letta.blocks.create(
                label=f"preferences_{block_user_key}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {display_name}",
                limit=2000
            )
            block_ids.append(pref_block.id)
            self.letta.agents.blocks.attach(agent_id=agent_id, block_id=pref_block.id)
            logger.info("preference_block_created", user_id=user_id, block_id=pref_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="preferences")

        # Create calendar block with identity-based naming
        try:
            cal_block = self.letta.blocks.create(
                label=f"calendar_{block_user_key}",
                value="Calendar integration pending configuration.",
                description=f"Calendar integration for {display_name}",
                limit=2000
            )
            block_ids.append(cal_block.id)
            self.letta.agents.blocks.attach(agent_id=agent_id, block_id=cal_block.id)
            logger.info("calendar_block_created", user_id=user_id, block_id=cal_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="calendar")

        # Create conversation
        try:
            conversation = self.letta.conversations.create(
                agent_id=agent_id,
                label=f"{display_name} - {user_source.capitalize()}"
            )
            conversation_id = conversation.id
            logger.info("conversation_created", user_id=user_id, conversation_id=conversation_id)
        except Exception as e:
            logger.error("conversation_creation_failed", error=str(e), user_id=user_id)
            return {"error": f"Failed to create conversation: {str(e)}", "created": False}

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
            logger.error("conversation_mapping_insert_failed", error=str(e), user_id=user_id, conversation_id=conversation_id)

        logger.info("user_onboarded", user_id=user_id, conversation_id=conversation_id, identity_id=identity_id, block_count=len(block_ids))
        return {"conversation_id": conversation_id, "identity_id": identity_id, "created": True}

    async def update_last_active(self, user_id: str, user_source: str, agent_id: str) -> None:
        """Update last_active_at timestamp for a conversation."""
        try:
            self.supabase.table("user_conversations").update({
                "last_active_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("user_source", user_source).eq("agent_id", agent_id).execute()
            logger.debug("last_active_updated", user_id=user_id)
        except Exception as e:
            logger.warning("last_active_update_failed", error=str(e), user_id=user_id)
