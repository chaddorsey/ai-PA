import asyncio
import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from scheduler_service.services.actions import execute_action, ActionExecutionError
from scheduler_service.settings import settings


@pytest.mark.asyncio
async def test_execute_http_action_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"ok": True})
    result = await execute_action(
        "http",
        {
            "method": "GET",
            "url": "https://example.com/api",
        },
    )
    assert result["status"] == "success"
    assert result["output"]["data"] == {"ok": True}


@pytest.mark.asyncio
async def test_execute_http_action_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=500)
    with pytest.raises(ActionExecutionError):
        await execute_action(
            "http",
            {
                "method": "POST",
                "url": "https://example.com/api",
                "json": {"foo": "bar"},
                "retries": 0,
            },
        )


@pytest.mark.asyncio
async def test_execute_script_action_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    script_file = script_dir / "echo.sh"
    script_file.write_text("#!/bin/bash\necho $1")
    script_file.chmod(0o755)

    monkeypatch.setattr(settings, "allowlist_script_dir", str(script_dir))

    result = await execute_action(
        "script",
        {
            "script": "echo.sh",
            "args": ["hello"],
        },
    )
    assert result["status"] == "success"
    assert result["output"]["stdout"] == "hello"
    assert "started_at" in result["output"]
    assert "completed_at" in result["output"]


@pytest.mark.asyncio
async def test_execute_script_action_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    monkeypatch.setattr(settings, "allowlist_script_dir", str(script_dir))

    with pytest.raises(ActionExecutionError):
        await execute_action(
            "script",
            {
                "script": "missing.sh",
            },
        )


@pytest.mark.asyncio
async def test_execute_unknown_action() -> None:
    with pytest.raises(ActionExecutionError):
        await execute_action("unknown", {})


# ---- route=local (letta-local-runner) ----------------------------------------

@pytest.mark.asyncio
async def test_agent_message_route_local_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://host.docker.internal:8920/invoke",
        json={
            "status": "success",
            "agent_response": "ack",
            "duration_seconds": 1.5,
            "letta_exit": 0,
            "retried": False,
            "stdout_truncated": "ack\n",
            "stderr_truncated": "",
            "log_path": "/tmp/...jsonl",
        },
    )
    result = await execute_action(
        "agent_message",
        {
            "route": "local",
            "agent_id": "agent-local-abc",
            "message": "hi",
            "timeout": 30,
        },
    )
    assert result["status"] == "success"
    out = result["output"]
    assert out["route"] == "local"
    assert out["agent_id"] == "agent-local-abc"
    assert out["agent_response"] == "ack"
    assert out["runner_status"] == "success"
    assert out["retried"] is False


@pytest.mark.asyncio
async def test_agent_message_route_local_race_recovered(httpx_mock: HTTPXMock) -> None:
    """Runner reports it had to retry. Action still succeeds; the
    retried flag propagates so callers can observe."""
    httpx_mock.add_response(
        method="POST",
        url="http://host.docker.internal:8920/invoke",
        json={
            "status": "race_recovered",
            "agent_response": "ack",
            "duration_seconds": 4.0,
            "letta_exit": 0,
            "retried": True,
            "stdout_truncated": "ack\n",
            "stderr_truncated": "",
            "log_path": "/tmp/...jsonl",
        },
    )
    result = await execute_action(
        "agent_message",
        {"route": "local", "agent_id": "agent-local-r", "message": "x"},
    )
    assert result["output"]["runner_status"] == "race_recovered"
    assert result["output"]["retried"] is True


@pytest.mark.asyncio
async def test_agent_message_route_local_missing_agent_id() -> None:
    with pytest.raises(ActionExecutionError) as ei:
        await execute_action(
            "agent_message",
            {"route": "local", "message": "x"},
        )
    assert "agent_id" in str(ei.value)


@pytest.mark.asyncio
async def test_agent_message_route_local_runner_returned_500(httpx_mock: HTTPXMock) -> None:
    """Runner returned 500 (letta crashed or other error). Surface it
    cleanly via ActionExecutionError so scheduler-service records the
    failure."""
    httpx_mock.add_response(
        method="POST",
        url="http://host.docker.internal:8920/invoke",
        status_code=500,
        json={"detail": {"status": "error", "letta_exit": 2, "stderr_truncated": "boom"}},
    )
    with pytest.raises(ActionExecutionError) as ei:
        await execute_action(
            "agent_message",
            {"route": "local", "agent_id": "agent-local-e", "message": "x"},
        )
    assert "local-runner" in str(ei.value)
    assert "500" in str(ei.value)


@pytest.mark.asyncio
async def test_agent_message_route_local_runner_unreachable(httpx_mock: HTTPXMock) -> None:
    """Runner is down. ActionExecutionError surfaced for scheduler retry."""
    import httpx as httpx_lib
    httpx_mock.add_exception(httpx_lib.ConnectError("no runner"))
    with pytest.raises(ActionExecutionError) as ei:
        await execute_action(
            "agent_message",
            {"route": "local", "agent_id": "agent-local-u", "message": "x"},
        )
    assert "local-runner" in str(ei.value).lower() or "no runner" in str(ei.value)


@pytest.mark.asyncio
async def test_agent_message_route_local_explicit_runner_url(httpx_mock: HTTPXMock) -> None:
    """config.runner_url overrides settings.local_runner_url."""
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:9999/invoke",
        json={
            "status": "success",
            "agent_response": "from-override",
            "duration_seconds": 0.5,
            "letta_exit": 0,
            "retried": False,
            "stdout_truncated": "",
            "stderr_truncated": "",
            "log_path": "",
        },
    )
    result = await execute_action(
        "agent_message",
        {
            "route": "local",
            "agent_id": "agent-local-o",
            "message": "x",
            "runner_url": "http://127.0.0.1:9999",
        },
    )
    assert result["output"]["agent_response"] == "from-override"
