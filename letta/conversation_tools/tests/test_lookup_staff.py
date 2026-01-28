"""Tests for lookup_staff agent tool."""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestLookupStaff:
    """Tests for staff lookup by colloquial name, email, or Slack ID."""

    @pytest.fixture
    def sample_identity_dict(self):
        """Sample staff identity as dictionary (API response format)."""
        return {
            "id": "identity-dan-123",
            "identifier_key": "ddamelin@concord.org",
            "name": "Dan Damelin",
            "properties": [
                {"key": "colloquial_name", "value": "Dan"},
                {"key": "slack_id", "value": "U0303SG91"},
                {"key": "calendar_id", "value": "ddamelin@concord.org"},
            ]
        }

    @pytest.fixture
    def mock_response(self, sample_identity_dict):
        """Mock requests.get response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [sample_identity_dict]
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_lookup_by_colloquial_name(self, mock_response):
        """Finds staff by colloquial name."""
        with patch("requests.get", return_value=mock_response):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"
        assert result["identity_id"] == "identity-dan-123"
        assert result["slack_id"] == "U0303SG91"
        assert result["calendar_id"] == "ddamelin@concord.org"

    def test_lookup_by_email(self, mock_response):
        """Finds staff by email address."""
        with patch("requests.get", return_value=mock_response):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="ddamelin@concord.org")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"
        assert result["email"] == "ddamelin@concord.org"

    def test_lookup_by_slack_id(self, mock_response):
        """Finds staff by Slack ID."""
        with patch("requests.get", return_value=mock_response):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="U0303SG91")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"
        assert result["identity_id"] == "identity-dan-123"
        assert result["slack_id"] == "U0303SG91"

    def test_lookup_not_found(self):
        """Returns error when staff not found."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="Unknown")

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    def test_lookup_case_insensitive(self, mock_response):
        """Lookup is case-insensitive."""
        with patch("requests.get", return_value=mock_response):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="dan")

        assert result["status"] == "ok"
        assert result["name"] == "Dan Damelin"

    def test_lookup_by_first_name(self):
        """Finds staff by first name when no colloquial_name property exists."""
        identity = {
            "id": "identity-scott-456",
            "identifier_key": "scytacki@concord.org",
            "name": "Scott Cytacki",
            "properties": [
                {"key": "slack_id", "value": "U02V82YB9"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [identity]
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="Scott")

        assert result["status"] == "ok"
        assert result["name"] == "Scott Cytacki"
        assert result["identity_id"] == "identity-scott-456"

    def test_handles_api_error(self):
        """Returns error when API call fails."""
        import requests

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Connection refused")
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "error"
        assert "Connection refused" in result["error_message"] or "connect" in result["error_message"].lower()

    def test_extracts_all_properties(self):
        """Extracts all properties from identity."""
        identity = {
            "id": "identity-dan-123",
            "identifier_key": "ddamelin@concord.org",
            "name": "Dan Damelin",
            "properties": [
                {"key": "colloquial_name", "value": "Dan"},
                {"key": "slack_id", "value": "U0303SG91"},
                {"key": "calendar_id", "value": "ddamelin@concord.org"},
                {"key": "working_hours", "value": "9-5"},
                {"key": "working_week", "value": "Mon-Fri"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [identity]
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="Dan")

        assert result["status"] == "ok"
        assert result["working_hours"] == "9-5"
        assert result["working_week"] == "Mon-Fri"

    def test_slack_id_not_found(self):
        """Returns error when Slack ID not found in any identity."""
        identity = {
            "id": "identity-dan-123",
            "identifier_key": "ddamelin@concord.org",
            "name": "Dan Damelin",
            "properties": [
                {"key": "slack_id", "value": "U0303SG91"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [identity]
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from conversation_tools.lookup_staff import lookup_staff
            result = lookup_staff(name_or_email="UNOTEXIST123")

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()
