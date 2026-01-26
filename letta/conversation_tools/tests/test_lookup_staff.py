"""Tests for lookup_staff agent tool."""

import sys
import pytest
from unittest.mock import MagicMock, patch

# Force import of the module first, then get it from sys.modules
# (the __init__.py exports a function with same name, shadowing the module)
import conversation_tools.lookup_staff
lookup_staff_module = sys.modules['conversation_tools.lookup_staff']
from conversation_tools.lookup_staff import lookup_staff


class TestLookupStaff:
    """Tests for staff lookup by colloquial name or email."""

    @pytest.fixture
    def sample_identity(self):
        """Sample staff identity."""
        identity = MagicMock()
        identity.id = "identity-dan-123"
        identity.identifier_key = "ddamelin@concord.org"
        identity.name = "Dan Damelin"
        identity.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
            {"key": "slack_id", "value": "U0303SG91", "type": "string"},
            {"key": "calendar_id", "value": "ddamelin@concord.org", "type": "string"},
            {"key": "email", "value": "ddamelin@concord.org", "type": "string"},
        ]
        return identity

    def test_lookup_by_colloquial_name(self, sample_identity):
        """Finds staff by colloquial name."""
        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = sample_identity

        with patch.object(lookup_staff_module, '_get_identity_service', return_value=mock_service):
            result = lookup_staff(name_or_email="Dan")

        assert result["name"] == "Dan Damelin"
        assert result["identity_id"] == "identity-dan-123"
        assert result["slack_id"] == "U0303SG91"
        assert result["calendar_id"] == "ddamelin@concord.org"

    def test_lookup_by_email(self, sample_identity):
        """Finds staff by email address."""
        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = None
        mock_service.find_by_identifier_key.return_value = sample_identity

        with patch.object(lookup_staff_module, '_get_identity_service', return_value=mock_service):
            result = lookup_staff(name_or_email="ddamelin@concord.org")

        assert result["name"] == "Dan Damelin"
        assert result["email"] == "ddamelin@concord.org"

    def test_lookup_not_found(self):
        """Returns error when staff not found."""
        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = None
        mock_service.find_by_identifier_key.return_value = None

        with patch.object(lookup_staff_module, '_get_identity_service', return_value=mock_service):
            result = lookup_staff(name_or_email="Unknown")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_lookup_case_insensitive(self, sample_identity):
        """Lookup is case-insensitive."""
        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = sample_identity

        with patch.object(lookup_staff_module, '_get_identity_service', return_value=mock_service):
            result = lookup_staff(name_or_email="dan")

        assert result["name"] == "Dan Damelin"
