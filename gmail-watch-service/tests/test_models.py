"""Tests for database models."""

from gmail_watch.models import Notification, SyncState, WatchedThread


def test_watched_thread_model_exists():
    """WatchedThread model can be instantiated."""
    thread = WatchedThread(
        thread_id="abc123",
        subject="Test Subject",
    )
    assert thread.thread_id == "abc123"
    assert thread.is_active is True
    assert thread.reply_received is False


def test_sync_state_model_exists():
    """SyncState model can be instantiated."""
    state = SyncState(history_id=12345)
    assert state.history_id == 12345


def test_notification_model_exists():
    """Notification model can be instantiated."""
    notification = Notification(
        thread_id="abc123",
        notification_type="reply_received",
    )
    assert notification.thread_id == "abc123"
