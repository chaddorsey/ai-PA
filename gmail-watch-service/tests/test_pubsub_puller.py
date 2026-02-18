"""Tests for Pub/Sub puller service."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from gmail_watch.services.pubsub_puller import PubSubPuller


@pytest.fixture
def mock_subscriber():
    """Create mock subscriber client."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock:
        yield mock.return_value


def test_pubsub_puller_initialization(mock_subscriber):
    """PubSubPuller can be instantiated."""
    puller = PubSubPuller("test-project", "test-subscription")
    assert puller is not None
    assert puller.project_id == "test-project"
    assert puller.subscription_id == "test-subscription"


def test_pubsub_puller_builds_subscription_path(mock_subscriber):
    """PubSubPuller builds correct subscription path."""
    puller = PubSubPuller("my-project", "my-subscription")
    expected = "projects/my-project/subscriptions/my-subscription"
    assert puller.subscription_path == expected


def test_pubsub_puller_lazy_loads_client(mock_subscriber):
    """PubSubPuller lazily loads the subscriber client."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        puller = PubSubPuller("test-project", "test-subscription")

        # Client not created yet
        mock_class.assert_not_called()

        # Access client property
        _ = puller.client
        mock_class.assert_called_once()


def test_pubsub_puller_caches_client(mock_subscriber):
    """PubSubPuller caches the subscriber client after first access."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        puller = PubSubPuller("test-project", "test-subscription")

        # Access multiple times
        _ = puller.client
        _ = puller.client
        _ = puller.client

        # Only created once
        mock_class.assert_called_once()


def test_parse_notification_extracts_history_id(mock_subscriber):
    """parse_notification extracts historyId from message."""
    puller = PubSubPuller("test-project", "test-subscription")

    data = {"emailAddress": "user@example.com", "historyId": "12345"}
    encoded = base64.b64encode(json.dumps(data).encode()).decode()

    mock_message = MagicMock()
    mock_message.data = encoded.encode()

    result = puller.parse_notification(mock_message)

    assert result["history_id"] == 12345
    assert result["email"] == "user@example.com"


def test_parse_notification_handles_string_data(mock_subscriber):
    """parse_notification handles string data (not bytes)."""
    puller = PubSubPuller("test-project", "test-subscription")

    data = {"emailAddress": "test@example.com", "historyId": "67890"}
    encoded = base64.b64encode(json.dumps(data).encode()).decode()

    mock_message = MagicMock()
    mock_message.data = encoded  # String, not bytes

    result = puller.parse_notification(mock_message)

    assert result["history_id"] == 67890
    assert result["email"] == "test@example.com"


def test_parse_notification_handles_invalid_data(mock_subscriber):
    """parse_notification returns error dict for invalid data."""
    puller = PubSubPuller("test-project", "test-subscription")

    mock_message = MagicMock()
    mock_message.data = b"not valid json or base64"

    result = puller.parse_notification(mock_message)

    assert result["history_id"] == 0
    assert result["email"] == ""
    assert "error" in result


def test_parse_notification_handles_missing_fields(mock_subscriber):
    """parse_notification handles messages with missing fields."""
    puller = PubSubPuller("test-project", "test-subscription")

    # Empty JSON object
    data = {}
    encoded = base64.b64encode(json.dumps(data).encode()).decode()

    mock_message = MagicMock()
    mock_message.data = encoded.encode()

    result = puller.parse_notification(mock_message)

    assert result["history_id"] == 0
    assert result["email"] == ""
    assert "error" not in result


def test_pull_messages_returns_parsed_notifications(mock_subscriber):
    """pull_messages returns list of parsed notifications."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # Create mock received messages
        data1 = {"emailAddress": "user1@example.com", "historyId": "100"}
        encoded1 = base64.b64encode(json.dumps(data1).encode()).decode()

        data2 = {"emailAddress": "user2@example.com", "historyId": "200"}
        encoded2 = base64.b64encode(json.dumps(data2).encode()).decode()

        mock_msg1 = MagicMock()
        mock_msg1.message.data = encoded1.encode()
        mock_msg1.ack_id = "ack_id_1"

        mock_msg2 = MagicMock()
        mock_msg2.message.data = encoded2.encode()
        mock_msg2.ack_id = "ack_id_2"

        mock_response = MagicMock()
        mock_response.received_messages = [mock_msg1, mock_msg2]
        mock_client.pull.return_value = mock_response

        puller = PubSubPuller("test-project", "test-subscription")
        result = puller.pull_messages(max_messages=10)

        assert len(result) == 2
        assert result[0]["history_id"] == 100
        assert result[0]["email"] == "user1@example.com"
        assert result[0]["ack_id"] == "ack_id_1"
        assert result[1]["history_id"] == 200
        assert result[1]["email"] == "user2@example.com"
        assert result[1]["ack_id"] == "ack_id_2"


def test_pull_messages_acknowledges_messages(mock_subscriber):
    """pull_messages acknowledges received messages."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # Create mock received message
        data = {"emailAddress": "user@example.com", "historyId": "100"}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()

        mock_msg = MagicMock()
        mock_msg.message.data = encoded.encode()
        mock_msg.ack_id = "ack_id_123"

        mock_response = MagicMock()
        mock_response.received_messages = [mock_msg]
        mock_client.pull.return_value = mock_response

        puller = PubSubPuller("test-project", "test-subscription")
        puller.pull_messages()

        # Verify acknowledge was called with correct ack_ids
        mock_client.acknowledge.assert_called_once()
        call_kwargs = mock_client.acknowledge.call_args.kwargs
        assert call_kwargs["ack_ids"] == ["ack_id_123"]


def test_pull_messages_handles_empty_response(mock_subscriber):
    """pull_messages handles empty response gracefully."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.received_messages = []
        mock_client.pull.return_value = mock_response

        puller = PubSubPuller("test-project", "test-subscription")
        result = puller.pull_messages()

        assert result == []
        # Should not call acknowledge when there are no messages
        mock_client.acknowledge.assert_not_called()


def test_pull_messages_uses_correct_parameters(mock_subscriber):
    """pull_messages passes correct parameters to pull call."""
    with patch("gmail_watch.services.pubsub_puller.SubscriberClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.received_messages = []
        mock_client.pull.return_value = mock_response

        puller = PubSubPuller("test-project", "test-subscription")
        puller.pull_messages(max_messages=25)

        mock_client.pull.assert_called_once_with(
            subscription="projects/test-project/subscriptions/test-subscription",
            max_messages=25,
            timeout=10,
        )


def test_get_topic_name(mock_subscriber):
    """get_topic_name returns correctly formatted topic name."""
    puller = PubSubPuller("my-gcp-project", "my-subscription")
    topic_name = puller.get_topic_name()

    assert topic_name == "projects/my-gcp-project/topics/gmail-watch"


def test_get_topic_name_uses_project_id(mock_subscriber):
    """get_topic_name uses the puller's project ID."""
    puller1 = PubSubPuller("project-a", "sub-1")
    puller2 = PubSubPuller("project-b", "sub-2")

    assert puller1.get_topic_name() == "projects/project-a/topics/gmail-watch"
    assert puller2.get_topic_name() == "projects/project-b/topics/gmail-watch"
