import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    checkpoint = CheckpointDB(str(db_path))
    await checkpoint.initialize()
    yield checkpoint
    await checkpoint.close()


@pytest_asyncio.fixture
async def manager(db):
    mgr = NotificationManager(db)
    await mgr.initialize()
    return mgr


@pytest.mark.asyncio
async def test_vapid_keys_generated_on_init(manager):
    keys = await manager.get_vapid_keys()
    assert "public_key" in keys
    assert "private_key" in keys
    assert len(keys["public_key"]) > 20


@pytest.mark.asyncio
async def test_vapid_keys_persist(db):
    mgr1 = NotificationManager(db)
    await mgr1.initialize()
    keys1 = await mgr1.get_vapid_keys()

    mgr2 = NotificationManager(db)
    await mgr2.initialize()
    keys2 = await mgr2.get_vapid_keys()

    assert keys1["public_key"] == keys2["public_key"]


@pytest.mark.asyncio
async def test_add_subscription(manager, db):
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "key", "auth": "auth"}}
    await manager.add_subscription(sub)
    subs = await manager.get_subscriptions()
    assert len(subs) == 1
    assert json.loads(subs[0]["subscription_json"])["endpoint"] == sub["endpoint"]


@pytest.mark.asyncio
async def test_send_notification_no_subscribers(manager):
    """Should not raise when no subscribers."""
    await manager.send_notification("Test", "Body")


@pytest.mark.asyncio
async def test_send_notification_calls_webpush(manager):
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "key", "auth": "auth"}}
    await manager.add_subscription(sub)

    with patch("app.notifications.webpush") as mock_wp:
        await manager.send_notification("Title", "Body text")
        assert mock_wp.called
        call_kwargs = mock_wp.call_args
        payload = json.loads(call_kwargs[1]["data"])
        assert payload["title"] == "Title"
        assert payload["body"] == "Body text"
