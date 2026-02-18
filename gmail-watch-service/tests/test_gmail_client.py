"""Tests for Gmail API client."""

from unittest.mock import MagicMock, patch

import pytest

from gmail_watch.services.gmail_client import GmailClient


@pytest.fixture
def mock_gmail_service():
    """Create a mock Gmail API service."""
    service = MagicMock()
    # Set up the nested mock structure for Gmail API
    service.users.return_value = MagicMock()
    return service


@pytest.fixture
def gmail_client(mock_gmail_service):
    """Create a GmailClient with mocked dependencies."""
    with patch("gmail_watch.services.gmail_client.Credentials") as mock_creds:
        with patch("gmail_watch.services.gmail_client.build") as mock_build:
            mock_creds.from_authorized_user_file.return_value = MagicMock()
            mock_build.return_value = mock_gmail_service

            client = GmailClient("/path/to/credentials.json")
            # Access service to trigger lazy loading
            _ = client.service
            yield client, mock_gmail_service


def test_gmail_client_initialization():
    """GmailClient can be instantiated with credentials path."""
    with patch("gmail_watch.services.gmail_client.Credentials") as mock_creds:
        with patch("gmail_watch.services.gmail_client.build") as mock_build:
            mock_creds.from_authorized_user_file.return_value = MagicMock()
            mock_build.return_value = MagicMock()

            client = GmailClient("/path/to/credentials.json")
            # Access service property to trigger lazy loading
            _ = client.service

            assert client is not None
            mock_build.assert_called_once()


def test_gmail_client_lazy_loads_service():
    """GmailClient doesn't build service until accessed."""
    with patch("gmail_watch.services.gmail_client.Credentials"):
        with patch("gmail_watch.services.gmail_client.build") as mock_build:
            client = GmailClient("/path/to/credentials.json")

            # Service not built yet
            mock_build.assert_not_called()

            # Access service
            _ = client.service
            mock_build.assert_called_once()


def test_gmail_client_caches_service():
    """GmailClient caches the service after first access."""
    with patch("gmail_watch.services.gmail_client.Credentials") as mock_creds:
        with patch("gmail_watch.services.gmail_client.build") as mock_build:
            mock_creds.from_authorized_user_file.return_value = MagicMock()
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            client = GmailClient("/path/to/credentials.json")

            # Access multiple times
            _ = client.service
            _ = client.service
            _ = client.service

            # Build only called once
            mock_build.assert_called_once()


def test_get_watching_label_id_existing(gmail_client):
    """get_watching_label_id returns ID of existing 'Watching' label."""
    client, mock_service = gmail_client

    # Mock labels.list to return a Watching label
    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX"},
            {"id": "Label_123", "name": "Watching"},
        ]
    }

    label_id = client.get_watching_label_id()

    assert label_id == "Label_123"
    mock_labels.list.assert_called_once()


def test_get_watching_label_id_creates_if_missing(gmail_client):
    """get_watching_label_id creates label if it doesn't exist."""
    client, mock_service = gmail_client

    # Mock labels.list to return no Watching label
    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX"},
        ]
    }
    # Mock labels.create
    mock_labels.create.return_value.execute.return_value = {
        "id": "Label_new",
        "name": "Watching",
    }

    label_id = client.get_watching_label_id()

    assert label_id == "Label_new"
    mock_labels.create.assert_called_once()


def test_get_watching_label_id_caches(gmail_client):
    """get_watching_label_id caches the label ID after first lookup."""
    client, mock_service = gmail_client

    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_123", "name": "Watching"}]
    }

    # Call multiple times
    _ = client.get_watching_label_id()
    _ = client.get_watching_label_id()
    _ = client.get_watching_label_id()

    # Only one API call
    mock_labels.list.assert_called_once()


def test_setup_watch(gmail_client):
    """setup_watch registers push notifications with Gmail API."""
    client, mock_service = gmail_client

    # Mock get_watching_label_id
    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_123", "name": "Watching"}]
    }

    # Mock watch
    mock_watch = mock_service.users.return_value.watch.return_value
    mock_watch.execute.return_value = {
        "historyId": "12345",
        "expiration": "1704067200000",
    }

    result = client.setup_watch("projects/test/topics/gmail-notifications")

    assert result["history_id"] == 12345
    assert result["expiration"] == 1704067200000
    mock_service.users.return_value.watch.assert_called_once()


def test_stop_watch(gmail_client):
    """stop_watch calls Gmail API to stop push notifications."""
    client, mock_service = gmail_client

    mock_stop = mock_service.users.return_value.stop.return_value
    mock_stop.execute.return_value = {}

    client.stop_watch()

    mock_service.users.return_value.stop.assert_called_once_with(userId="me")


def test_get_history(gmail_client):
    """get_history retrieves mailbox history records."""
    client, mock_service = gmail_client

    # Mock get_watching_label_id
    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_123", "name": "Watching"}]
    }

    # Mock history.list
    mock_history = mock_service.users.return_value.history.return_value
    mock_history.list.return_value.execute.return_value = {
        "history": [
            {
                "id": "12346",
                "messagesAdded": [
                    {"message": {"id": "msg_1", "threadId": "thread_1"}}
                ],
            }
        ]
    }

    result = client.get_history(12345)

    assert len(result) == 1
    assert result[0]["id"] == "12346"


def test_get_history_with_pagination(gmail_client):
    """get_history handles paginated results."""
    client, mock_service = gmail_client

    # Mock get_watching_label_id
    mock_labels = mock_service.users.return_value.labels.return_value
    mock_labels.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_123", "name": "Watching"}]
    }

    # Mock history.list with pagination
    mock_history = mock_service.users.return_value.history.return_value
    mock_history.list.return_value.execute.side_effect = [
        {
            "history": [{"id": "12346"}],
            "nextPageToken": "page2",
        },
        {
            "history": [{"id": "12347"}],
            # No nextPageToken - last page
        },
    ]

    result = client.get_history(12345)

    assert len(result) == 2
    assert result[0]["id"] == "12346"
    assert result[1]["id"] == "12347"


def test_get_message(gmail_client):
    """get_message retrieves a message by ID."""
    client, mock_service = gmail_client

    mock_messages = mock_service.users.return_value.messages.return_value
    mock_messages.get.return_value.execute.return_value = {
        "id": "msg_123",
        "threadId": "thread_456",
        "payload": {"headers": []},
    }

    result = client.get_message("msg_123")

    assert result["id"] == "msg_123"
    mock_messages.get.assert_called_once_with(
        userId="me", id="msg_123", format="metadata"
    )


def test_get_message_with_format(gmail_client):
    """get_message can request different message formats."""
    client, mock_service = gmail_client

    mock_messages = mock_service.users.return_value.messages.return_value
    mock_messages.get.return_value.execute.return_value = {"id": "msg_123"}

    _ = client.get_message("msg_123", format="full")

    mock_messages.get.assert_called_once_with(
        userId="me", id="msg_123", format="full"
    )


def test_get_thread(gmail_client):
    """get_thread retrieves a thread by ID."""
    client, mock_service = gmail_client

    mock_threads = mock_service.users.return_value.threads.return_value
    mock_threads.get.return_value.execute.return_value = {
        "id": "thread_123",
        "messages": [{"id": "msg_1"}, {"id": "msg_2"}],
    }

    result = client.get_thread("thread_123")

    assert result["id"] == "thread_123"
    assert len(result["messages"]) == 2
    mock_threads.get.assert_called_once_with(
        userId="me", id="thread_123", format="metadata"
    )


def test_get_profile(gmail_client):
    """get_profile retrieves user profile for health checks."""
    client, mock_service = gmail_client

    mock_profile = mock_service.users.return_value.getProfile.return_value
    mock_profile.execute.return_value = {
        "emailAddress": "user@example.com",
        "historyId": "12345",
    }

    result = client.get_profile()

    assert result["emailAddress"] == "user@example.com"
    mock_service.users.return_value.getProfile.assert_called_once_with(userId="me")
