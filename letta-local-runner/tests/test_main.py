"""FastAPI endpoint tests with TestClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from letta_local_runner.main import app
from letta_local_runner.invoker import Invoker
from letta_local_runner.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """TestClient with a fresh Invoker scoped to a tmp backend dir."""
    settings = Settings(
        letta_bin="/usr/bin/false",
        backend_dir=tmp_path / "backend",
        log_dir=tmp_path / "logs",
        default_timeout_seconds=30,
        race_recovery_delay_seconds=0.01,
        listen_host="127.0.0.1",
        listen_port=0,
    )
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = settings
    app.state.invoker = Invoker(settings)
    return TestClient(app)


def _fake_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    proc = AsyncMock()

    async def communicate():
        return (stdout, stderr)

    proc.communicate = communicate
    proc.returncode = returncode
    proc.kill = lambda: None
    return proc


def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert body["active"] == 0


def test_status_endpoint_empty(client: TestClient):
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["inflight"] == {}
    assert body["recent"] == []


def test_invoke_happy_path(client: TestClient):
    with patch(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        return_value=_fake_proc(stdout=b"agent says hi"),
    ):
        r = client.post(
            "/invoke",
            json={"agent_id": "agent-local-A", "message": "hello"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["agent_response"] == "agent says hi"
    assert body["letta_exit"] == 0


def test_invoke_validation_rejects_short_timeout(client: TestClient):
    r = client.post(
        "/invoke",
        json={"agent_id": "agent-local-A", "message": "x", "timeout": 5},
    )
    assert r.status_code == 422  # Pydantic ge=10


def test_invoke_validation_rejects_huge_timeout(client: TestClient):
    r = client.post(
        "/invoke",
        json={"agent_id": "agent-local-A", "message": "x", "timeout": 99999},
    )
    assert r.status_code == 422  # Pydantic le=3600


def test_invoke_validation_rejects_missing_agent(client: TestClient):
    r = client.post("/invoke", json={"message": "x"})
    assert r.status_code == 422


def test_invoke_error_returns_500_with_detail(client: TestClient):
    with patch(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        return_value=_fake_proc(stderr=b"crash", returncode=2),
    ):
        r = client.post(
            "/invoke",
            json={"agent_id": "agent-local-E", "message": "x"},
        )
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail["status"] == "error"
    assert detail["letta_exit"] == 2
    assert "crash" in detail["stderr_truncated"]
