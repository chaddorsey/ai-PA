"""Tests for lookup_staff agent tool."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock


class TestLookupStaff:
    """Tests for staff lookup by colloquial name or email."""

    @pytest.fixture(autouse=True)
    def setup_letta_mock(self):
        """Set up letta_client mock in sys.modules before each test."""
        # Create a mock letta_client module
        self.mock_letta_module = MagicMock()
        self.mock_client = MagicMock()
        self.mock_letta_module.Letta.return_value = self.mock_client

        # Save original if it exists
        self.original_letta_client = sys.modules.get('letta_client')
        self.original_letta = sys.modules.get('letta')

        # Install mock
        sys.modules['letta_client'] = self.mock_letta_module
        sys.modules['letta'] = self.mock_letta_module

        yield

        # Restore original
        if self.original_letta_client is not None:
            sys.modules['letta_client'] = self.original_letta_client
        elif 'letta_client' in sys.modules:
            del sys.modules['letta_client']

        if self.original_letta is not None:
            sys.modules['letta'] = self.original_letta
        elif 'letta' in sys.modules:
            del sys.modules['letta']

    @pytest.fixture
    def sample_identity(self):
        """Sample staff identity."""
        identity = MagicMock()
        identity.id = "identity-dan-123"
        identity.identifier_key = "ddamelin@concord.org"
        identity.name = "Dan Damelin"
        identity.properties = [
            {"key": "colloquial_name", "value": "Dan"},
            {"key": "slack_id", "value": "U0303SG91"},
            {"key": "calendar_id", "value": "ddamelin@concord.org"},
            {"key": "email", "value": "ddamelin@concord.org"},
        ]
        return identity

    def test_lookup_by_colloquial_name(self, sample_identity):
        """Finds staff by colloquial name."""
        self.mock_client.identities.list.return_value = [sample_identity]

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"
        assert result["identity_id"] == "identity-dan-123"
        assert result["slack_id"] == "U0303SG91"
        assert result["calendar_id"] == "ddamelin@concord.org"

    def test_lookup_by_email(self, sample_identity):
        """Finds staff by email address."""
        self.mock_client.identities.list.return_value = [sample_identity]

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="ddamelin@concord.org")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"
        assert result["email"] == "ddamelin@concord.org"

    def test_lookup_not_found(self):
        """Returns error when staff not found."""
        self.mock_client.identities.list.return_value = []

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Unknown")

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    def test_lookup_case_insensitive(self, sample_identity):
        """Lookup is case-insensitive."""
        self.mock_client.identities.list.return_value = [sample_identity]

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="dan")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"

    def test_lookup_by_first_name(self):
        """Finds staff by first name when no colloquial_name property exists."""
        identity = MagicMock()
        identity.id = "identity-scott-456"
        identity.identifier_key = "scytacki@concord.org"
        identity.name = "Scott Cytacki"
        identity.properties = [
            {"key": "slack_id", "value": "U02V82YB9"},
        ]
        self.mock_client.identities.list.return_value = [identity]

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Scott")

        assert result["status"] == "ok"
        assert result["name"] == "Scott Cytacki"
        assert result["identity_id"] == "identity-scott-456"

    def test_returns_error_when_client_unavailable(self):
        """Returns error when Letta client not available."""
        # Set Letta to None to simulate unavailable client
        self.mock_letta_module.Letta = None
        sys.modules['letta_client'] = self.mock_letta_module
        sys.modules['letta'] = self.mock_letta_module

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "error"
        assert "client not available" in result["error_message"].lower()

    def test_handles_api_error(self):
        """Returns error when API call fails."""
        self.mock_client.identities.list.side_effect = Exception("Connection refused")

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "error"
        assert "Connection refused" in result["error_message"]

    def test_extracts_all_properties(self, sample_identity):
        """Extracts all properties from identity."""
        # Add additional properties
        sample_identity.properties.append({"key": "working_hours", "value": "9-5"})
        sample_identity.properties.append({"key": "working_week", "value": "Mon-Fri"})
        self.mock_client.identities.list.return_value = [sample_identity]

        from conversation_tools.lookup_staff import lookup_staff
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "ok"
        assert result["working_hours"] == "9-5"
        assert result["working_week"] == "Mon-Fri"
