"""Tests for watch manager orchestrator."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_session_with_sync_state(sync_state):
    """Create a mock session that returns the given sync state on execute."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sync_state
    mock_session.execute.return_value = mock_result
    return mock_session


@pytest.mark.asyncio
async def test_watch_manager_process_notifications():
    """WatchManager processes Pub/Sub notifications correctly."""
    from gmail_watch.services.watch_manager import WatchManager

    # Create mocks
    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_registry = AsyncMock()
    mock_notifier = AsyncMock()

    # Mock sync state exists
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )
    manager._registry = mock_registry
    manager._notifier = mock_notifier

    # Mock puller returning a notification
    mock_puller.pull_messages.return_value = [
        {"history_id": 12345, "email": "user@example.com"}
    ]

    # Mock registry returning watched thread IDs
    mock_registry.get_active_thread_ids.return_value = {"thread_abc123"}

    # Mock Gmail history returning a message in watched thread
    mock_gmail.get_history.return_value = [
        {
            "messagesAdded": [
                {"message": {"id": "msg_123", "threadId": "thread_abc123"}}
            ]
        }
    ]

    # Mock getting message details
    mock_gmail.get_message.return_value = {
        "id": "msg_123",
        "threadId": "thread_abc123",
        "snippet": "Thanks for your email",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Re: Test"},
            ]
        }
    }

    # Mock registry returning the thread
    mock_thread = MagicMock()
    mock_thread.thread_id = "thread_abc123"
    mock_registry.mark_reply_received.return_value = mock_thread

    # Mock notifier
    mock_notifier.notify_reply_received.return_value = {"status": "ok"}

    # Run
    result = await manager.process_notifications()

    # Verify
    assert result["status"] == "ok"
    mock_puller.pull_messages.assert_called_once()
    mock_registry.mark_reply_received.assert_called_once()
    mock_notifier.notify_reply_received.assert_called_once()


@pytest.mark.asyncio
async def test_watch_manager_initialize_watch():
    """WatchManager initializes Gmail watch correctly."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_session = create_mock_session_with_sync_state(None)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    # Mock Pub/Sub topic name
    mock_puller.get_topic_name.return_value = "projects/my-project/topics/gmail-watch"

    # Mock Gmail watch response
    expiration_ts = (datetime.now(timezone.utc) + timedelta(days=7)).timestamp()
    expiration_time = int(expiration_ts * 1000)
    mock_gmail.setup_watch.return_value = {
        "history_id": 12345,
        "expiration": expiration_time,
    }

    result = await manager.initialize_watch()

    assert result["status"] == "ok"
    assert result["history_id"] == 12345
    mock_gmail.setup_watch.assert_called_once_with("projects/my-project/topics/gmail-watch")


@pytest.mark.asyncio
async def test_watch_manager_check_watch_expiration_not_expired():
    """WatchManager correctly identifies non-expired watch."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state with future expiration
    mock_sync_state = MagicMock()
    mock_sync_state.watch_expiration = datetime.now(timezone.utc) + timedelta(days=3)
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.check_watch_expiration()

    assert result["needs_renewal"] is False
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_watch_manager_check_watch_expiration_expired():
    """WatchManager correctly identifies expired watch."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state with past expiration
    mock_sync_state = MagicMock()
    mock_sync_state.watch_expiration = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.check_watch_expiration()

    assert result["needs_renewal"] is True
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_watch_manager_check_watch_expiration_soon():
    """WatchManager flags watches expiring within threshold."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state expiring in 12 hours (less than default 1 day threshold)
    mock_sync_state = MagicMock()
    mock_sync_state.watch_expiration = datetime.now(timezone.utc) + timedelta(hours=12)
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.check_watch_expiration()

    assert result["needs_renewal"] is True


@pytest.mark.asyncio
async def test_watch_manager_process_notifications_no_notifications():
    """WatchManager handles no notifications gracefully."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    # No notifications
    mock_puller.pull_messages.return_value = []

    result = await manager.process_notifications()

    assert result["status"] == "ok"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_watch_manager_process_notifications_filters_unwatched():
    """WatchManager filters out messages from unwatched threads."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_registry = AsyncMock()

    # Mock sync state
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )
    manager._registry = mock_registry

    mock_puller.pull_messages.return_value = [
        {"history_id": 12345, "email": "user@example.com"}
    ]

    # Only watching thread_abc123
    mock_registry.get_active_thread_ids.return_value = {"thread_abc123"}

    # But history returns message from different thread
    mock_gmail.get_history.return_value = [
        {
            "messagesAdded": [
                {"message": {"id": "msg_123", "threadId": "thread_other"}}
            ]
        }
    ]

    result = await manager.process_notifications()

    assert result["status"] == "ok"
    # Should not have tried to mark reply
    mock_registry.mark_reply_received.assert_not_called()


@pytest.mark.asyncio
async def test_watch_manager_error_handling():
    """WatchManager handles errors gracefully and records them."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_sync_state.error_count = 0
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    # Make puller raise an error
    mock_puller.pull_messages.side_effect = Exception("Pub/Sub connection failed")

    result = await manager.process_notifications()

    assert result["status"] == "error"
    assert "Pub/Sub connection failed" in result["error"]


@pytest.mark.asyncio
async def test_watch_manager_uses_lazy_registry():
    """WatchManager lazily initializes registry."""
    from gmail_watch.services.registry import ThreadRegistry
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_session = create_mock_session_with_sync_state(None)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    # Access registry property
    registry = manager.registry
    assert isinstance(registry, ThreadRegistry)


@pytest.mark.asyncio
async def test_watch_manager_uses_lazy_notifier():
    """WatchManager lazily initializes notifier."""
    from gmail_watch.services.agent_notifier import AgentNotifier
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_session = create_mock_session_with_sync_state(None)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    # Access notifier property
    notifier = manager.notifier
    assert isinstance(notifier, AgentNotifier)


@pytest.mark.asyncio
async def test_watch_manager_no_sync_state():
    """WatchManager handles missing sync state."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_session = create_mock_session_with_sync_state(None)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.process_notifications()

    assert result["status"] == "error"
    assert "no sync state" in result["error"].lower()


@pytest.mark.asyncio
async def test_watch_manager_logs_notification():
    """WatchManager logs notifications to database."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_registry = AsyncMock()
    mock_notifier = AsyncMock()

    # Mock sync state
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )
    manager._registry = mock_registry
    manager._notifier = mock_notifier

    mock_puller.pull_messages.return_value = [
        {"history_id": 12345, "email": "user@example.com"}
    ]

    mock_registry.get_active_thread_ids.return_value = {"thread_abc123"}

    mock_gmail.get_history.return_value = [
        {
            "messagesAdded": [
                {"message": {"id": "msg_123", "threadId": "thread_abc123"}}
            ]
        }
    ]

    mock_gmail.get_message.return_value = {
        "id": "msg_123",
        "threadId": "thread_abc123",
        "snippet": "Reply text",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Re: Test"},
            ]
        }
    }

    mock_thread = MagicMock()
    mock_thread.thread_id = "thread_abc123"
    mock_registry.mark_reply_received.return_value = mock_thread

    mock_notifier.notify_reply_received.return_value = {"status": "ok"}

    await manager.process_notifications()

    # Verify session.add was called (for logging notification)
    mock_session.add.assert_called()


@pytest.mark.asyncio
async def test_watch_manager_extracts_headers_correctly():
    """WatchManager extracts From header correctly."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_registry = AsyncMock()
    mock_notifier = AsyncMock()

    # Mock sync state
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 10000
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )
    manager._registry = mock_registry
    manager._notifier = mock_notifier

    mock_puller.pull_messages.return_value = [
        {"history_id": 12345, "email": "user@example.com"}
    ]

    mock_registry.get_active_thread_ids.return_value = {"thread_abc123"}

    mock_gmail.get_history.return_value = [
        {
            "messagesAdded": [
                {"message": {"id": "msg_123", "threadId": "thread_abc123"}}
            ]
        }
    ]

    # Simulate Gmail message with specific From header
    mock_gmail.get_message.return_value = {
        "id": "msg_123",
        "threadId": "thread_abc123",
        "snippet": "Reply text",
        "payload": {
            "headers": [
                {"name": "From", "value": "John Doe <john@example.com>"},
                {"name": "Subject", "value": "Re: Test"},
            ]
        }
    }

    mock_thread = MagicMock()
    mock_thread.thread_id = "thread_abc123"
    mock_registry.mark_reply_received.return_value = mock_thread

    mock_notifier.notify_reply_received.return_value = {"status": "ok"}

    await manager.process_notifications()

    # Verify the From address was passed correctly
    notify_call = mock_notifier.notify_reply_received.call_args
    assert notify_call[1]["from_address"] == "John Doe <john@example.com>"


@pytest.mark.asyncio
async def test_watch_manager_get_sync_status():
    """WatchManager get_sync_status returns formatted sync state."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()

    # Mock sync state with all fields
    mock_sync_state = MagicMock()
    mock_sync_state.history_id = 12345
    mock_sync_state.watch_expiration = datetime(
        2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc
    )
    mock_sync_state.last_pull_at = datetime(
        2025, 6, 8, 10, 30, 0, tzinfo=timezone.utc
    )
    mock_sync_state.error_count = 2
    mock_session = create_mock_session_with_sync_state(mock_sync_state)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.get_sync_status()

    assert result["history_id"] == 12345
    assert result["watch_expiration"] == "2025-06-15T12:00:00+00:00"
    assert result["last_pull_at"] == "2025-06-08T10:30:00+00:00"
    assert result["error_count"] == 2


@pytest.mark.asyncio
async def test_watch_manager_get_sync_status_no_state():
    """WatchManager get_sync_status handles missing sync state."""
    from gmail_watch.services.watch_manager import WatchManager

    mock_gmail = MagicMock()
    mock_puller = MagicMock()
    mock_session = create_mock_session_with_sync_state(None)

    manager = WatchManager(
        gmail_client=mock_gmail,
        pubsub_puller=mock_puller,
        session=mock_session,
    )

    result = await manager.get_sync_status()

    assert result["history_id"] is None
    assert result["watch_expiration"] is None
    assert result["last_pull_at"] is None
    assert result["error_count"] == 0
