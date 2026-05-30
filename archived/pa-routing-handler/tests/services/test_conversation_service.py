"""Tests for conversation service."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestConversationService:
    """Tests for user conversation management."""

    @pytest.fixture
    def mock_letta_client(self):
        """Create mock Letta client."""
        client = MagicMock()
        client.conversations = MagicMock()
        client.identities = MagicMock()
        client.agents = MagicMock()
        client.agents.blocks = MagicMock()
        client.blocks = MagicMock()
        return client

    @pytest.fixture
    def mock_supabase_client(self):
        """Create mock Supabase client."""
        client = MagicMock()
        client.table = MagicMock(return_value=client)
        client.select = MagicMock(return_value=client)
        client.eq = MagicMock(return_value=client)
        client.execute = MagicMock()
        client.insert = MagicMock(return_value=client)
        client.update = MagicMock(return_value=client)
        return client

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing_conversation(
        self, mock_letta_client, mock_supabase_client
    ):
        """Returns existing conversation if found in database."""
        from pa_routing.services.conversation_service import ConversationService

        mock_supabase_client.execute.return_value.data = [{
            "conversation_id": "conv-123",
            "identity_id": "identity-456"
        }]

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        result = await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        assert result["conversation_id"] == "conv-123"
        assert result["created"] is False

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_conversation(
        self, mock_letta_client, mock_supabase_client
    ):
        """Creates new conversation when none exists."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "new-conv-789"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock identity creation
        mock_identity = MagicMock()
        mock_identity.id = "new-identity-abc"
        mock_letta_client.identities.create.return_value = mock_identity

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-pref-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        result = await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc",
            display_name="Test User",
            email="test@example.com"
        )

        assert result["conversation_id"] == "new-conv-789"
        assert result["created"] is True

        # Verify conversation was created with correct agent_id
        mock_letta_client.conversations.create.assert_called_once()
        call_kwargs = mock_letta_client.conversations.create.call_args[1]
        assert call_kwargs["agent_id"] == "agent-abc"

    @pytest.mark.asyncio
    async def test_creates_initial_blocks_on_new_conversation(
        self, mock_letta_client, mock_supabase_client
    ):
        """Creates initial preference blocks when onboarding new user."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "new-conv"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock identity creation
        mock_identity = MagicMock()
        mock_identity.id = "new-identity"
        mock_letta_client.identities.create.return_value = mock_identity

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Verify blocks were created with user_id naming convention
        assert mock_letta_client.blocks.create.called
        call_args = mock_letta_client.blocks.create.call_args_list
        labels = [c[1].get("label", c[0][0] if c[0] else None) for c in call_args]
        # At least one block should have the user_id in its label
        assert any("U123" in str(label) for label in labels if label)

    @pytest.mark.asyncio
    async def test_stores_mapping_in_supabase(
        self, mock_letta_client, mock_supabase_client
    ):
        """Stores user-conversation mapping in Supabase."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "new-conv-xyz"
        mock_letta_client.conversations.create.return_value = mock_conversation

        mock_identity = MagicMock()
        mock_identity.id = "identity-xyz"
        mock_letta_client.identities.create.return_value = mock_identity

        mock_block = MagicMock()
        mock_block.id = "block-xyz"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Verify insert was called with correct mapping
        insert_calls = [
            call for call in mock_supabase_client.insert.call_args_list
        ]
        assert len(insert_calls) >= 1
        insert_data = insert_calls[0][0][0]
        assert insert_data["user_id"] == "U123"
        assert insert_data["user_source"] == "slack"
        assert insert_data["conversation_id"] == "new-conv-xyz"

    @pytest.mark.asyncio
    async def test_update_last_active(
        self, mock_letta_client, mock_supabase_client
    ):
        """Updates last_active_at timestamp for conversation."""
        from pa_routing.services.conversation_service import ConversationService

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        await service.update_last_active(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Verify update was called
        mock_supabase_client.update.assert_called()
        mock_supabase_client.eq.assert_any_call("user_id", "U123")

    @pytest.mark.asyncio
    async def test_handles_supabase_lookup_error_gracefully(
        self, mock_letta_client, mock_supabase_client
    ):
        """Returns None for conversation_id when Supabase lookup fails."""
        from pa_routing.services.conversation_service import ConversationService

        # Simulate Supabase error
        mock_supabase_client.execute.side_effect = Exception("Connection failed")

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        result = await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should return error or fallback behavior
        assert result is not None
        # Either has error or creates new conversation
        assert "error" in result or "conversation_id" in result

    @pytest.fixture
    def mock_identity_service(self):
        """Create mock IdentityService."""
        service = MagicMock()
        service.find_by_property = MagicMock(return_value=None)
        service.find_by_identifier_key = MagicMock(return_value=None)
        service.create_external_user = MagicMock()
        service.get_property = MagicMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_resolves_staff_identity_by_slack_id(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Resolves existing staff identity when messaging from Slack."""
        from pa_routing.services.conversation_service import ConversationService

        # Staff identity exists
        staff_identity = MagicMock()
        staff_identity.id = "identity-staff-123"
        staff_identity.name = "Dan Damelin"
        mock_identity_service.find_by_property.return_value = staff_identity

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-new"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="U0303SG91",  # Dan's Slack ID
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should have looked up by slack_id
        mock_identity_service.find_by_property.assert_called_with("slack_id", "U0303SG91")
        # Should use existing identity, NOT create new one
        mock_letta_client.identities.create.assert_not_called()
        assert result["identity_id"] == "identity-staff-123"

    @pytest.mark.asyncio
    async def test_creates_external_identity_for_unknown_user(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Creates external identity for unknown Slack user."""
        from pa_routing.services.conversation_service import ConversationService

        # No staff identity found
        mock_identity_service.find_by_property.return_value = None
        mock_identity_service.find_by_identifier_key.return_value = None

        # External identity created
        external_identity = MagicMock()
        external_identity.id = "identity-external-999"
        mock_identity_service.create_external_user.return_value = external_identity

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-new"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="U99999999",  # Unknown user
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should create external identity
        mock_identity_service.create_external_user.assert_called_once()
        assert result["identity_id"] == "identity-external-999"
