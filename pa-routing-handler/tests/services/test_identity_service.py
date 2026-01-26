"""Tests for IdentityService."""

import pytest
from unittest.mock import MagicMock, patch


class TestIdentityService:
    """Tests for identity lookup and management."""

    @pytest.fixture
    def mock_letta_client(self):
        """Create mock Letta client with identities namespace."""
        client = MagicMock()
        client.identities = MagicMock()
        return client

    @pytest.fixture
    def sample_identities(self):
        """Sample identity objects for testing."""
        dan = MagicMock()
        dan.id = "identity-dan-123"
        dan.identifier_key = "ddamelin@concord.org"
        dan.name = "Dan Damelin"
        dan.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
            {"key": "slack_id", "value": "U0303SG91", "type": "string"},
            {"key": "calendar_id", "value": "ddamelin@concord.org", "type": "string"},
            {"key": "email", "value": "ddamelin@concord.org", "type": "string"},
        ]

        scott = MagicMock()
        scott.id = "identity-scott-456"
        scott.identifier_key = "scytacki@concord.org"
        scott.name = "Scott Cytacki"
        scott.properties = [
            {"key": "colloquial_name", "value": "Scott", "type": "string"},
            {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
            {"key": "calendar_id", "value": "scytacki@concord.org", "type": "string"},
            {"key": "email", "value": "scytacki@concord.org", "type": "string"},
        ]

        return [dan, scott]

    def test_find_by_identifier_key_found(self, mock_letta_client, sample_identities):
        """Finds identity by exact identifier_key (email)."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("ddamelin@concord.org")

        assert result is not None
        assert result.id == "identity-dan-123"
        assert result.name == "Dan Damelin"

    def test_find_by_identifier_key_not_found(self, mock_letta_client, sample_identities):
        """Returns None when identifier_key not found."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("unknown@example.com")

        assert result is None

    def test_find_by_property_slack_id(self, mock_letta_client, sample_identities):
        """Finds identity by slack_id property."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_property("slack_id", "U02V82YB9")

        assert result is not None
        assert result.id == "identity-scott-456"

    def test_find_by_colloquial_name(self, mock_letta_client, sample_identities):
        """Finds identity by colloquial_name property."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("Dan")

        assert result is not None
        assert result.id == "identity-dan-123"

    def test_find_by_colloquial_name_case_insensitive(self, mock_letta_client, sample_identities):
        """Colloquial name search is case-insensitive."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("dan")

        assert result is not None
        assert result.id == "identity-dan-123"

    def test_find_by_colloquial_name_fallback_to_first_name(self, mock_letta_client):
        """Falls back to first name of full name if no colloquial_name match."""
        from pa_routing.services.identity_service import IdentityService

        # Identity without colloquial_name property
        person = MagicMock()
        person.id = "identity-new-789"
        person.identifier_key = "newperson@concord.org"
        person.name = "New Person"
        person.properties = [
            {"key": "email", "value": "newperson@concord.org", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [person]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("New")

        assert result is not None
        assert result.id == "identity-new-789"

    def test_create_external_user(self, mock_letta_client):
        """Creates external identity for unknown users."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-external-999"
        mock_letta_client.identities.create.return_value = mock_identity

        service = IdentityService(letta_client=mock_letta_client)
        result = service.create_external_user(
            platform="slack",
            platform_id="U99999999",
            display_name="External User"
        )

        assert result.id == "identity-external-999"
        mock_letta_client.identities.create.assert_called_once()

    def test_get_property_helper(self, mock_letta_client, sample_identities):
        """Helper extracts property value from identity."""
        from pa_routing.services.identity_service import IdentityService

        service = IdentityService(letta_client=mock_letta_client)
        dan = sample_identities[0]

        assert service.get_property(dan, "slack_id") == "U0303SG91"
        assert service.get_property(dan, "calendar_id") == "ddamelin@concord.org"
        assert service.get_property(dan, "nonexistent") is None
