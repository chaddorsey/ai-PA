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
