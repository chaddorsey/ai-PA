"""Tests for thread registry service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gmail_watch.services.registry import ThreadRegistry


@pytest.fixture
def mock_session():
    """Create a mock database session.

    The session.execute() is async and returns a Result object.
    The Result object has sync methods: scalar_one_or_none(), scalars(), all().
    """
    session = AsyncMock()
    # execute returns a MagicMock (Result object) with sync methods
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_watch_thread_creates_record(mock_session):
    """watch_thread creates a new WatchedThread record."""
    registry = ThreadRegistry(mock_session)

    # Get the mock result object and configure it
    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.watch_thread(
        thread_id="thread_abc123",
        subject="Test Subject",
        recipients=["user@example.com"],
    )

    assert result["status"] == "ok"
    assert result["thread_id"] == "thread_abc123"
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_watch_thread_already_watching(mock_session):
    """watch_thread returns already_watching for active watched thread."""
    registry = ThreadRegistry(mock_session)

    # Mock existing active thread
    mock_thread = MagicMock()
    mock_thread.is_active = True

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.watch_thread(
        thread_id="thread_abc123",
        subject="Test Subject",
    )

    assert result["status"] == "already_watching"
    assert result["thread_id"] == "thread_abc123"


@pytest.mark.asyncio
async def test_watch_thread_reactivates_inactive(mock_session):
    """watch_thread reactivates an inactive watched thread."""
    registry = ThreadRegistry(mock_session)

    # Mock existing inactive thread
    mock_thread = MagicMock()
    mock_thread.is_active = False

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.watch_thread(
        thread_id="thread_abc123",
        subject="Test Subject",
    )

    assert result["status"] == "reactivated"
    assert result["thread_id"] == "thread_abc123"
    assert mock_thread.is_active is True


@pytest.mark.asyncio
async def test_unwatch_thread_deactivates(mock_session):
    """unwatch_thread sets is_active to False."""
    registry = ThreadRegistry(mock_session)

    # Mock existing thread
    mock_thread = MagicMock()
    mock_thread.is_active = True

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.unwatch_thread("thread_abc123")

    assert result["status"] == "ok"
    assert mock_thread.is_active is False


@pytest.mark.asyncio
async def test_unwatch_thread_not_found(mock_session):
    """unwatch_thread returns not_found for unknown thread."""
    registry = ThreadRegistry(mock_session)

    # Mock no existing thread
    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.unwatch_thread("thread_unknown")

    assert result["status"] == "not_found"
    assert result["thread_id"] == "thread_unknown"


@pytest.mark.asyncio
async def test_list_watched_returns_active_threads(mock_session):
    """list_watched returns only active threads by default."""
    registry = ThreadRegistry(mock_session)

    mock_thread = MagicMock()
    mock_thread.thread_id = "thread_abc123"
    mock_thread.subject = "Test"
    mock_thread.is_active = True
    mock_thread.reply_received = False
    mock_thread.created_at = MagicMock()
    mock_thread.created_at.isoformat.return_value = "2026-02-01T00:00:00"
    mock_thread.followup_days = None
    mock_thread.followup_due_at = None

    mock_result = mock_session.execute.return_value
    mock_result.scalars.return_value.all.return_value = [mock_thread]

    result = await registry.list_watched()

    assert result["status"] == "ok"
    assert len(result["threads"]) == 1


@pytest.mark.asyncio
async def test_get_watch_status_returns_details(mock_session):
    """get_watch_status returns full thread details."""
    registry = ThreadRegistry(mock_session)

    mock_thread = MagicMock()
    mock_thread.thread_id = "thread_abc123"
    mock_thread.subject = "Test Subject"
    mock_thread.is_active = True
    mock_thread.reply_received = False
    mock_thread.reply_received_at = None
    mock_thread.created_at = MagicMock()
    mock_thread.created_at.isoformat.return_value = "2026-02-01T00:00:00"
    mock_thread.followup_days = 3
    mock_thread.followup_due_at = None
    mock_thread.followup_notified = False
    mock_thread.message_count = 1
    mock_thread.extra_data = None

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.get_watch_status("thread_abc123")

    assert result["status"] == "ok"
    assert result["thread_id"] == "thread_abc123"
    assert result["subject"] == "Test Subject"
    assert result["followup_days"] == 3


@pytest.mark.asyncio
async def test_get_watch_status_not_found(mock_session):
    """get_watch_status returns not_found for unknown thread."""
    registry = ThreadRegistry(mock_session)

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.get_watch_status("thread_unknown")

    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_active_thread_ids(mock_session):
    """get_active_thread_ids returns set of active thread IDs."""
    registry = ThreadRegistry(mock_session)

    mock_result = mock_session.execute.return_value
    mock_result.all.return_value = [
        ("thread_1",),
        ("thread_2",),
        ("thread_3",),
    ]

    result = await registry.get_active_thread_ids()

    assert result == {"thread_1", "thread_2", "thread_3"}


@pytest.mark.asyncio
async def test_mark_reply_received_updates_thread(mock_session):
    """mark_reply_received updates thread state."""
    registry = ThreadRegistry(mock_session)

    mock_thread = MagicMock()
    mock_thread.is_active = True
    mock_thread.reply_received = False
    mock_thread.message_count = 1

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.mark_reply_received(
        thread_id="thread_abc123",
        message_id="msg_xyz789",
    )

    assert result is not None
    assert mock_thread.reply_received is True
    assert mock_thread.reply_message_id == "msg_xyz789"
    assert mock_thread.message_count == 2


@pytest.mark.asyncio
async def test_mark_reply_received_already_replied(mock_session):
    """mark_reply_received returns None for already replied thread."""
    registry = ThreadRegistry(mock_session)

    mock_thread = MagicMock()
    mock_thread.is_active = True
    mock_thread.reply_received = True  # Already received

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.mark_reply_received(
        thread_id="thread_abc123",
        message_id="msg_xyz789",
    )

    assert result is None


@pytest.mark.asyncio
async def test_mark_reply_received_not_found(mock_session):
    """mark_reply_received returns None for unknown thread."""
    registry = ThreadRegistry(mock_session)

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.mark_reply_received(
        thread_id="thread_unknown",
        message_id="msg_xyz789",
    )

    assert result is None


@pytest.mark.asyncio
async def test_mark_reply_received_inactive_thread(mock_session):
    """mark_reply_received returns None for inactive thread."""
    registry = ThreadRegistry(mock_session)

    mock_thread = MagicMock()
    mock_thread.is_active = False  # Inactive
    mock_thread.reply_received = False

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = mock_thread

    result = await registry.mark_reply_received(
        thread_id="thread_abc123",
        message_id="msg_xyz789",
    )

    assert result is None
