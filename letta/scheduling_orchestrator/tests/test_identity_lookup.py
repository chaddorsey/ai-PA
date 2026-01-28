"""Tests for identity lookup utilities."""

import pytest
from unittest.mock import patch, MagicMock

from scheduling_orchestrator.identity_lookup import (
    get_user_preferences_from_identity,
    _extract_scheduling_preferences,
    lookup_identity_by_property,
    resolve_participant_identifier,
)


class TestGetUserPreferencesFromIdentity:
    """Tests for get_user_preferences_from_identity function."""

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_fetches_identity_by_id(self):
        """Should fetch identity from Letta API using identity ID."""
        import sys

        # Set up the mock
        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "identity-123",
            "identifier_key": "user@example.com",
            "properties": [
                {"key": "preferred_times", "value": "morning,afternoon"},
                {"key": "avoid_days", "value": "Friday"},
            ]
        }
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = get_user_preferences_from_identity("identity-123")

        # Verify API was called correctly
        mock_client.get.assert_called_once_with(
            "http://localhost:8283/v1/identities/identity-123"
        )

        # Verify preferences were extracted
        assert result == {
            "preferred_times": ["morning", "afternoon"],
            "avoid_days": ["Friday"],
        }

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_returns_none_for_not_found(self):
        """Should return None when identity is not found (404)."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = get_user_preferences_from_identity("nonexistent-id")

        assert result is None

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_returns_none_on_api_error(self):
        """Should return None and log warning on API error."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = get_user_preferences_from_identity("identity-123")

        assert result is None

    def test_returns_none_for_empty_identity_id(self):
        """Should return None when identity_id is empty or None."""
        assert get_user_preferences_from_identity("") is None
        assert get_user_preferences_from_identity(None) is None

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_uses_custom_base_url(self):
        """Should use custom base URL when provided."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"properties": []}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        get_user_preferences_from_identity(
            "identity-123",
            letta_base_url="http://custom:9999"
        )

        mock_client.get.assert_called_once_with(
            "http://custom:9999/v1/identities/identity-123"
        )


class TestExtractSchedulingPreferences:
    """Tests for _extract_scheduling_preferences function."""

    def test_extracts_all_preference_types(self):
        """Should extract all four preference types."""
        identity = {
            "properties": [
                {"key": "preferred_times", "value": "morning,09:00-11:00"},
                {"key": "preferred_days", "value": "Monday,Tuesday"},
                {"key": "avoid_times", "value": "evening"},
                {"key": "avoid_days", "value": "Friday,Saturday,Sunday"},
            ]
        }

        result = _extract_scheduling_preferences(identity)

        assert result == {
            "preferred_times": ["morning", "09:00-11:00"],
            "preferred_days": ["Monday", "Tuesday"],
            "avoid_times": ["evening"],
            "avoid_days": ["Friday", "Saturday", "Sunday"],
        }

    def test_handles_empty_properties(self):
        """Should return empty dict when no properties."""
        assert _extract_scheduling_preferences({"properties": []}) == {}
        assert _extract_scheduling_preferences({}) == {}

    def test_ignores_non_preference_properties(self):
        """Should ignore properties that aren't scheduling preferences."""
        identity = {
            "properties": [
                {"key": "colloquial_name", "value": "Dan"},
                {"key": "preferred_times", "value": "morning"},
                {"key": "timezone", "value": "America/New_York"},
            ]
        }

        result = _extract_scheduling_preferences(identity)

        assert result == {"preferred_times": ["morning"]}
        assert "colloquial_name" not in result
        assert "timezone" not in result

    def test_handles_whitespace_in_values(self):
        """Should trim whitespace from comma-separated values."""
        identity = {
            "properties": [
                {"key": "avoid_days", "value": " Friday , Saturday , Sunday "},
            ]
        }

        result = _extract_scheduling_preferences(identity)

        assert result == {"avoid_days": ["Friday", "Saturday", "Sunday"]}

    def test_handles_empty_values(self):
        """Should handle empty or whitespace-only values."""
        identity = {
            "properties": [
                {"key": "preferred_times", "value": ""},
                {"key": "avoid_days", "value": "  "},
                {"key": "preferred_days", "value": "Monday"},
            ]
        }

        result = _extract_scheduling_preferences(identity)

        # Only preferred_days should be present
        assert result == {"preferred_days": ["Monday"]}

    def test_handles_single_value(self):
        """Should handle single value (no comma)."""
        identity = {
            "properties": [
                {"key": "preferred_times", "value": "morning"},
            ]
        }

        result = _extract_scheduling_preferences(identity)

        assert result == {"preferred_times": ["morning"]}


class TestLookupIdentityByProperty:
    """Tests for lookup_identity_by_property function."""

    MOCK_IDENTITIES = [
        {
            "id": "identity-123",
            "identifier_key": "user1@example.com",
            "name": "User One",
            "properties": [
                {"key": "slack_id", "value": "U0A7B9ZQ35Y"},
                {"key": "calendar_id", "value": "user1@example.com"},
            ]
        },
        {
            "id": "identity-456",
            "identifier_key": "user2@example.com",
            "name": "User Two",
            "properties": [
                {"key": "slack_id", "value": "U0AB18G54ET"},
            ]
        },
    ]

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_finds_identity_by_slack_id(self):
        """Should find identity by slack_id property."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.json.return_value = self.MOCK_IDENTITIES
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = lookup_identity_by_property("slack_id", "U0A7B9ZQ35Y")

        assert result is not None
        assert result["id"] == "identity-123"
        assert result["identifier_key"] == "user1@example.com"

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_finds_identity_by_email(self):
        """Should find identity by email (identifier_key)."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.json.return_value = self.MOCK_IDENTITIES
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = lookup_identity_by_property("email", "user2@example.com")

        assert result is not None
        assert result["id"] == "identity-456"

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_returns_none_when_not_found(self):
        """Should return None when no matching identity found."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.json.return_value = self.MOCK_IDENTITIES
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = lookup_identity_by_property("slack_id", "UNOTEXIST123")

        assert result is None

    def test_returns_none_for_empty_inputs(self):
        """Should return None for empty key or value."""
        assert lookup_identity_by_property("", "value") is None
        assert lookup_identity_by_property("key", "") is None
        assert lookup_identity_by_property(None, "value") is None


class TestResolveParticipantIdentifier:
    """Tests for resolve_participant_identifier function."""

    MOCK_IDENTITIES = [
        {
            "id": "identity-123",
            "identifier_key": "user@example.com",
            "properties": [
                {"key": "slack_id", "value": "U0A7B9ZQ35Y"},
            ]
        },
    ]

    def test_returns_email_directly(self):
        """Should return email addresses directly without lookup."""
        result = resolve_participant_identifier("user@example.com")
        assert result == "user@example.com"

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_resolves_slack_id_to_email(self):
        """Should resolve Slack ID to email address."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.json.return_value = self.MOCK_IDENTITIES
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = resolve_participant_identifier("U0A7B9ZQ35Y")

        assert result == "user@example.com"

    @patch.dict("sys.modules", {"httpx": MagicMock()})
    def test_returns_none_for_unknown_slack_id(self):
        """Should return None when Slack ID not found."""
        import sys

        mock_httpx = sys.modules["httpx"]
        mock_response = MagicMock()
        mock_response.json.return_value = self.MOCK_IDENTITIES
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        result = resolve_participant_identifier("UNOTEXIST123")

        assert result is None

    def test_returns_none_for_empty_input(self):
        """Should return None for empty identifier."""
        assert resolve_participant_identifier("") is None
        assert resolve_participant_identifier(None) is None
