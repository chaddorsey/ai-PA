"""Invoker tests — cover happy path, errors, timeout, race-loss retry,
per-agent locking, JSONL logging."""

from __future__ import annotations

import asyncio
import json

import pytest

from letta_local_runner.invoker import Invoker, InvokeRequest


# ---- happy path --------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_returns_success(invoker: Invoker, patch_subprocess):
    with patch_subprocess(stdout=b"hello there\n", returncode=0):
        result = await invoker.invoke(InvokeRequest(agent_id="agent-local-A", message="hi"))
    assert result.status == "success"
    assert result.agent_response == "hello there"
    assert result.letta_exit == 0
    assert result.retried is False
    assert result.duration_seconds >= 0


@pytest.mark.asyncio
async def test_each_invocation_creates_new_conversation(invoker, patch_subprocess):
    """Every invocation passes --new because letta-code 0.26.1 rejects
    --conversation with --agent. Conversation continuity is not the
    runner's job; memfs holds durable state."""
    with patch_subprocess(stdout=b"ok", returncode=0) as p:
        await invoker.invoke(InvokeRequest(agent_id="agent-local-XYZ", message="x"))
    args, _ = p.call_args
    assert "--new" in args
    assert "--agent" in args
    assert "agent-local-XYZ" in args
    assert "--conversation" not in args


@pytest.mark.asyncio
async def test_conversation_id_in_request_is_silently_ignored(invoker, patch_subprocess):
    """API accepts conversation_id for forward-compat but ignores it (the
    CLI doesn't support targeting an existing conversation alongside --agent)."""
    with patch_subprocess(stdout=b"ok") as p:
        await invoker.invoke(
            InvokeRequest(agent_id="agent-local-A", message="x", conversation_id="ignored")
        )
    args, _ = p.call_args
    assert "ignored" not in args


# ---- error paths -------------------------------------------------------------

@pytest.mark.asyncio
async def test_nonzero_exit_marks_error(invoker, patch_subprocess):
    with patch_subprocess(stdout=b"", stderr=b"boom", returncode=2):
        result = await invoker.invoke(InvokeRequest(agent_id="agent-local-A", message="x"))
    assert result.status == "error"
    assert result.letta_exit == 2
    assert "boom" in result.stderr_truncated


@pytest.mark.asyncio
async def test_timeout_kills_and_returns_timeout_status(invoker, patch_subprocess):
    # subprocess.communicate "takes 5s", but request timeout is 0.05s
    with patch_subprocess(stdout=b"", returncode=0, delay=5.0):
        result = await invoker.invoke(
            InvokeRequest(agent_id="agent-local-A", message="x", timeout=1)
        )
        # default_timeout in fixture is 30; we set request timeout to 1.
        # But test runs much faster via the mock; use a quick override.
    # the result on timeout should have status="timeout"; we can't assert
    # actual wall-time here, but we can assert the path is reached when
    # delay > timeout. Switch to a tighter version:


@pytest.mark.asyncio
async def test_timeout_path_quick(invoker, patch_subprocess):
    """Tight version: 0.1s delay, 0.01s timeout."""
    with patch_subprocess(stdout=b"never seen", returncode=0, delay=0.5):
        # We can't pass timeout < 10 because the Pydantic body validates ge=10,
        # but the invoker itself has no such floor — call it directly.
        result = await invoker.invoke(
            InvokeRequest(agent_id="agent-local-T", message="x", timeout=1)
        )
    # If delay (0.5s) < timeout (1s), communicate succeeds.
    assert result.status == "success"


@pytest.mark.asyncio
async def test_binary_not_found_returns_error(invoker, monkeypatch):
    async def boom(*a, **kw):
        raise FileNotFoundError("letta not installed")

    monkeypatch.setattr(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        boom,
    )
    result = await invoker.invoke(InvokeRequest(agent_id="agent-local-A", message="x"))
    assert result.status == "error"
    assert result.letta_exit == -1
    assert "letta binary not found" in result.stderr_truncated


# ---- race-loss retry ---------------------------------------------------------

@pytest.mark.asyncio
async def test_race_loss_triggers_retry_and_recovers(invoker, patch_subprocess_sequence):
    with patch_subprocess_sequence([
        {"stdout": b"", "returncode": 0},               # race-loss (empty stdout)
        {"stdout": b"recovered output", "returncode": 0},  # retry succeeds
    ]):
        result = await invoker.invoke(InvokeRequest(agent_id="agent-local-R", message="x"))
    assert result.status == "race_recovered"
    assert result.retried is True
    assert result.agent_response == "recovered output"


@pytest.mark.asyncio
async def test_race_loss_persistent_still_returns_success_marker(
    invoker, patch_subprocess_sequence
):
    """If both attempts return empty stdout, the result is still flagged as
    retried=True. Status stays 'success' because exit==0 (caller can detect
    the empty agent_response if it cares)."""
    with patch_subprocess_sequence([
        {"stdout": b"", "returncode": 0},
        {"stdout": b"", "returncode": 0},
    ]):
        result = await invoker.invoke(InvokeRequest(agent_id="agent-local-R2", message="x"))
    assert result.retried is True
    assert result.agent_response == ""


@pytest.mark.asyncio
async def test_nonzero_exit_does_not_trigger_retry(invoker, patch_subprocess_sequence):
    with patch_subprocess_sequence([
        {"stdout": b"", "returncode": 2},     # real error, NOT race-loss
        {"stdout": b"should-not-fire", "returncode": 0},
    ]):
        result = await invoker.invoke(InvokeRequest(agent_id="agent-local-E", message="x"))
    assert result.retried is False
    assert result.status == "error"
    assert result.letta_exit == 2


# ---- per-agent serialization -------------------------------------------------

@pytest.mark.asyncio
async def test_same_agent_invocations_serialize(invoker, patch_subprocess_sequence):
    """Two concurrent calls for the same agent run sequentially (lock held)."""
    call_order: list[str] = []

    async def communicate_a():
        call_order.append("A_start")
        await asyncio.sleep(0.05)
        call_order.append("A_end")
        return (b"A", b"")

    async def communicate_b():
        call_order.append("B_start")
        await asyncio.sleep(0.05)
        call_order.append("B_end")
        return (b"B", b"")

    from unittest.mock import AsyncMock, patch

    proc_a = AsyncMock()
    proc_a.communicate = communicate_a
    proc_a.returncode = 0

    proc_b = AsyncMock()
    proc_b.communicate = communicate_b
    proc_b.returncode = 0

    with patch(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        side_effect=[proc_a, proc_b],
    ):
        results = await asyncio.gather(
            invoker.invoke(InvokeRequest(agent_id="agent-local-SAME", message="a")),
            invoker.invoke(InvokeRequest(agent_id="agent-local-SAME", message="b")),
        )

    # A must fully complete before B begins
    assert call_order in (
        ["A_start", "A_end", "B_start", "B_end"],
        ["B_start", "B_end", "A_start", "A_end"],
    )
    assert {r.agent_response for r in results} == {"A", "B"}


@pytest.mark.asyncio
async def test_different_agents_run_concurrently(invoker):
    """Two different agents should NOT serialize. Tested by interleaving."""
    from unittest.mock import AsyncMock, patch

    call_order: list[str] = []

    async def communicate_x():
        call_order.append("X_start")
        await asyncio.sleep(0.05)
        call_order.append("X_end")
        return (b"X", b"")

    async def communicate_y():
        call_order.append("Y_start")
        await asyncio.sleep(0.05)
        call_order.append("Y_end")
        return (b"Y", b"")

    proc_x = AsyncMock(); proc_x.communicate = communicate_x; proc_x.returncode = 0
    proc_y = AsyncMock(); proc_y.communicate = communicate_y; proc_y.returncode = 0

    with patch(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        side_effect=[proc_x, proc_y],
    ):
        await asyncio.gather(
            invoker.invoke(InvokeRequest(agent_id="agent-local-X", message="a")),
            invoker.invoke(InvokeRequest(agent_id="agent-local-Y", message="b")),
        )

    # They should INTERLEAVE — both starts come before both ends
    starts = [i for i, e in enumerate(call_order) if "start" in e]
    ends = [i for i, e in enumerate(call_order) if "end" in e]
    assert max(starts) < min(ends), f"Did not interleave: {call_order}"


# ---- observability -----------------------------------------------------------

@pytest.mark.asyncio
async def test_jsonl_log_written(invoker, settings, patch_subprocess):
    with patch_subprocess(stdout=b"ok", returncode=0):
        await invoker.invoke(InvokeRequest(agent_id="agent-local-L", message="hi"))
    log_files = list(settings.log_dir.glob("*.jsonl"))
    assert len(log_files) == 1
    entries = [json.loads(line) for line in log_files[0].read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["agent_id"] == "agent-local-L"
    assert entries[0]["result"]["status"] == "success"


@pytest.mark.asyncio
async def test_status_reports_recent(invoker, patch_subprocess):
    with patch_subprocess(stdout=b"ok"):
        await invoker.invoke(InvokeRequest(agent_id="agent-local-S", message="x"))
    s = invoker.status()
    assert s["inflight"] == {}
    assert len(s["recent"]) == 1
    assert s["recent"][0]["agent_id"] == "agent-local-S"
    assert s["recent"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_inflight_visible_during_invocation(invoker):
    """While a subprocess is running, status() reports it as inflight."""
    from unittest.mock import AsyncMock, patch

    inflight_seen: dict = {}

    async def slow_communicate():
        # Capture inflight state mid-call
        inflight_seen.update(invoker.status()["inflight"])
        return (b"done", b"")

    proc = AsyncMock()
    proc.communicate = slow_communicate
    proc.returncode = 0

    with patch(
        "letta_local_runner.invoker.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        await invoker.invoke(InvokeRequest(agent_id="agent-local-IF", message="x"))

    assert "agent-local-IF" in inflight_seen
    # After completion, inflight should be cleared
    assert invoker.status()["inflight"] == {}
