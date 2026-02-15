import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(db_path=str(tmp_path / "test.db"))
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_status_initial(client):
    r = await client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "idle"
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_errors_empty(client):
    r = await client.get("/api/errors")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_push_vapid_key(client):
    r = await client.get("/api/push/vapid-key")
    assert r.status_code == 200
    assert "public_key" in r.json()


@pytest.mark.asyncio
async def test_push_subscribe(client):
    sub = {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "k", "auth": "a"}}
    r = await client.post("/api/push/subscribe", json=sub)
    assert r.status_code == 200
    assert r.json()["status"] == "subscribed"


@pytest.mark.asyncio
async def test_pause_when_not_running(client):
    r = await client.post("/api/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "not_running"
