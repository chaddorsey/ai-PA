"""Shared fixtures.

Tests mock asyncio.create_subprocess_exec — no real letta-code processes
are spawned. Filesystem ops (JSONL logs) use pytest tmp_path.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, patch

import pytest

from letta_local_runner.invoker import Invoker
from letta_local_runner.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Real settings pointed at temp paths. letta_bin is a placeholder
    that mocked subprocess calls never actually exec."""
    return Settings(
        letta_bin="/usr/bin/false",
        backend_dir=tmp_path / "backend",
        log_dir=tmp_path / "logs",
        default_timeout_seconds=30,
        race_recovery_delay_seconds=0.01,  # speed tests up
        listen_host="127.0.0.1",
        listen_port=0,
    )


@pytest.fixture
def invoker(settings: Settings) -> Invoker:
    return Invoker(settings)


# ---- subprocess mock helpers -------------------------------------------------


def make_fake_process(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
    delay: float = 0.0,
) -> AsyncMock:
    """Return a mock that mimics asyncio.subprocess.Process for one invocation."""
    proc = AsyncMock()

    async def communicate():
        if delay:
            await asyncio.sleep(delay)
        return (stdout, stderr)

    proc.communicate = communicate
    proc.returncode = returncode
    proc.kill = lambda: None

    async def wait():
        return returncode

    proc.wait = wait
    return proc


@pytest.fixture
def patch_subprocess() -> Callable[..., Any]:
    """Return a context-manager factory: with patch_subprocess(stdout=...): ..."""

    def _factory(**kwargs):
        proc = make_fake_process(**kwargs)
        return patch(
            "letta_local_runner.invoker.asyncio.create_subprocess_exec",
            return_value=proc,
        )

    return _factory


@pytest.fixture
def patch_subprocess_sequence() -> Callable[..., Any]:
    """Multiple subprocess calls in sequence, with different responses each.

    Usage:
        with patch_subprocess_sequence([
            {"stdout": b"", "returncode": 0},        # race-loss
            {"stdout": b"recovered", "returncode": 0},  # retry succeeds
        ]):
            ...
    """

    def _factory(call_specs: list[dict]):
        procs = [make_fake_process(**spec) for spec in call_specs]
        return patch(
            "letta_local_runner.invoker.asyncio.create_subprocess_exec",
            side_effect=procs,
        )

    return _factory
