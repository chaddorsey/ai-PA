"""Unit tests for subprocess_pool.py (Unit 1.2).

The tests use a fake subprocess transport to exercise the registry and
handle behavior without spawning a real letta-code. A real-spawn
integration test lives in test_subprocess_env.py.

Run: cd pa-web-ui && python -m pytest tests/test_subprocess_pool.py -v
"""

from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess_pool as sp  # noqa: E402


# ----------------------------------------------------------------- fakes


class FakeStdin:
    """A lock-free byte sink with an inspectable backing buffer."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self._buffer = bytearray()
        self.closed_flag = False

    def write(self, chunk: bytes) -> int:
        if self.closed_flag:
            raise BrokenPipeError("closed")
        self._buffer.extend(chunk)
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self.lines.append(line.decode("utf-8"))
            self._buffer = bytearray(rest)
        return len(chunk)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed_flag = True


class FakeStdout:
    """A blocking byte stream fed by `push_event` calls."""

    def __init__(self) -> None:
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._residue = b""

    def push_event(self, event: Dict[str, Any]) -> None:
        line = (json.dumps(event) + "\n").encode("utf-8")
        self._q.put(line)

    def close_eof(self) -> None:
        self._q.put(None)

    def readline(self) -> bytes:
        # Block until a line arrives or EOF is signaled.
        chunk = self._q.get()
        if chunk is None:
            return b""  # EOF
        return chunk


class FakePopen:
    """Minimal Popen stand-in matching the attributes subprocess_pool uses."""

    def __init__(self) -> None:
        self.pid = os.getpid()
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.stderr = io.BytesIO()
        self._returncode: Optional[int] = None
        self._terminated = threading.Event()

    def poll(self) -> Optional[int]:
        return self._returncode

    def terminate(self) -> None:
        self._returncode = -15
        self._terminated.set()
        self.stdout.close_eof()
        self.stdin.close()

    def kill(self) -> None:
        self._returncode = -9
        self._terminated.set()
        self.stdout.close_eof()
        self.stdin.close()

    def wait(self, timeout: Optional[float] = None) -> int:
        if timeout is None:
            self._terminated.wait()
        else:
            if not self._terminated.wait(timeout):
                raise subprocess.TimeoutExpired([], timeout)
        return self._returncode or 0

    def finish_clean(self) -> None:
        self._returncode = 0
        self._terminated.set()
        self.stdout.close_eof()


# ----------------------------------------------------------------- fixtures


@pytest.fixture
def fake_processes() -> Dict[str, FakePopen]:
    """Tracks every FakePopen the factory has handed out, keyed by conv_id."""
    return {}


@pytest.fixture
def spawn_factory(fake_processes: Dict[str, FakePopen]) -> Callable[..., FakePopen]:
    def _factory(**kwargs: Any) -> FakePopen:
        conv_id = kwargs["conv_id"]
        proc = FakePopen()
        fake_processes[conv_id] = proc
        return proc

    return _factory


@pytest.fixture
def registry(spawn_factory: Callable[..., FakePopen]) -> sp.SubprocessRegistry:
    """A per-test registry with the fake spawn factory wired in."""
    reg = sp.SubprocessRegistry(
        max_concurrent=3,
        init_timeout_s=2.0,
        send_timeout_s=2.0,
        spawn_factory=spawn_factory,
    )
    yield reg
    reg.shutdown(grace_s=0.5)


def _feed_init(proc: FakePopen, **extra: Any) -> None:
    """Push a system/init event that unblocks a pending ensure()."""
    payload = {
        "type": "system",
        "subtype": "init",
        "agent_id": extra.get("agent_id", "agent-test"),
        "memfs_enabled": True,
        "conversation_id": extra.get("conv_id", "test-conv"),
        "model": "gpt-5.2",
        "tools": ["Bash", "Read"],
    }
    payload.update(extra)
    proc.stdout.push_event(payload)


def _ensure_async(
    registry: sp.SubprocessRegistry, agent_id: str, conv_id: str
) -> "concurrent.futures.Future[sp.SubprocessHandle]":
    """Spawn ensure() in a background thread so the main thread can drive the fake."""
    from concurrent.futures import Future

    fut: Future = Future()

    def _run() -> None:
        try:
            fut.set_result(registry.ensure(agent_id, conv_id))
        except Exception as exc:
            fut.set_exception(exc)

    threading.Thread(target=_run, daemon=True).start()
    return fut


# ----------------------------------------------------------------- tests


def test_spawn_and_init(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-A")

    # Wait for spawn to happen and pick up the fake process.
    for _ in range(50):
        if "conv-A" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-A"]

    # The registry should have written the initialize control_request.
    time.sleep(0.05)
    assert any("initialize" in line for line in proc.stdin.lines), (
        f"expected initialize line in stdin, got {proc.stdin.lines}"
    )

    _feed_init(proc, conv_id="conv-A")
    handle = fut.result(timeout=2)

    assert handle.alive
    assert handle.init_state["agent_id"] == "agent-test"
    assert handle.init_state["memfs_enabled"] is True


def test_ensure_returns_same_handle_for_same_conv(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-A")
    for _ in range(50):
        if "conv-A" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-A"], conv_id="conv-A")
    h1 = fut.result(timeout=2)

    h2 = registry.ensure("agent-A", "conv-A")
    assert h1 is h2
    # Exactly one FakePopen was created.
    assert len(fake_processes) == 1


def test_creation_lock_coalesces_concurrent_spawns(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut1 = _ensure_async(registry, "agent-A", "conv-B")
    fut2 = _ensure_async(registry, "agent-A", "conv-B")

    for _ in range(50):
        if "conv-B" in fake_processes:
            break
        time.sleep(0.01)
    # Only ONE subprocess should have been spawned.
    assert len(fake_processes) == 1

    _feed_init(fake_processes["conv-B"], conv_id="conv-B")

    h1 = fut1.result(timeout=2)
    h2 = fut2.result(timeout=2)
    assert h1 is h2


def test_distinct_convs_spawn_distinct_subprocesses(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut_a = _ensure_async(registry, "agent-A", "conv-A")
    fut_b = _ensure_async(registry, "agent-A", "conv-B")

    for _ in range(50):
        if "conv-A" in fake_processes and "conv-B" in fake_processes:
            break
        time.sleep(0.01)

    _feed_init(fake_processes["conv-A"], conv_id="conv-A")
    _feed_init(fake_processes["conv-B"], conv_id="conv-B")

    h_a = fut_a.result(timeout=2)
    h_b = fut_b.result(timeout=2)

    assert h_a is not h_b
    assert h_a.process is not h_b.process


def test_init_timeout_kills_subprocess(spawn_factory: Callable[..., FakePopen]) -> None:
    reg = sp.SubprocessRegistry(
        max_concurrent=2,
        init_timeout_s=0.2,
        spawn_factory=spawn_factory,
    )
    try:
        with pytest.raises(sp.SpawnTimeoutError):
            reg.ensure("agent-A", "conv-timeout")
    finally:
        reg.shutdown(grace_s=0.2)


def test_send_writes_user_message(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-S")
    for _ in range(50):
        if "conv-S" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-S"]
    _feed_init(proc, conv_id="conv-S")
    handle = fut.result(timeout=2)

    registry.send(handle, "hello world", device_id="dev-1")

    # Last stdin line should be the user message in the SDK-compatible shape.
    time.sleep(0.05)
    assert len(proc.stdin.lines) >= 2, proc.stdin.lines
    last = json.loads(proc.stdin.lines[-1])
    assert last["type"] == "user"
    assert last["message"] == {"role": "user", "content": "hello world"}


def test_turn_lock_rejects_second_send(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-T")
    for _ in range(50):
        if "conv-T" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-T"], conv_id="conv-T")
    handle = fut.result(timeout=2)

    registry.send(handle, "first", device_id="dev-A")

    with pytest.raises(sp.TurnLockedException) as exc_info:
        registry.send(handle, "second", device_id="dev-B")

    assert exc_info.value.conv_id == "conv-T"
    assert exc_info.value.current_device_id == "dev-A"


def test_turn_lock_released_on_result(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-R")
    for _ in range(50):
        if "conv-R" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-R"]
    _feed_init(proc, conv_id="conv-R")
    handle = fut.result(timeout=2)

    registry.send(handle, "first", device_id="dev-A")
    # Subprocess emits result → turn lock should release.
    proc.stdout.push_event({
        "type": "result",
        "subtype": "success",
        "run_ids": ["run-1"],
    })
    # Wait for reader to process.
    for _ in range(50):
        if not handle.in_flight:
            break
        time.sleep(0.01)
    assert not handle.in_flight, "turn lock should release after result event"
    assert "run-1" in handle.last_completed_run_ids


def test_stale_run_events_dropped(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-Stale")
    for _ in range(50):
        if "conv-Stale" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-Stale"]
    _feed_init(proc, conv_id="conv-Stale")
    handle = fut.result(timeout=2)

    # Complete a turn.
    proc.stdout.push_event({"type": "result", "subtype": "success", "run_ids": ["run-X"]})
    for _ in range(50):
        if "run-X" in handle.last_completed_run_ids:
            break
        time.sleep(0.01)

    ring_before = len(handle.ring_buffer)

    # Late event from the completed run → should be dropped.
    proc.stdout.push_event({"type": "text", "run_id": "run-X", "content": "late"})
    time.sleep(0.1)

    # Ring buffer should NOT have grown for the stale event.
    # (The result event did increase it; we compare post-result baseline.)
    stale_events = [e for e in handle.ring_buffer if e.get("run_id") == "run-X"
                    and e.get("type") == "text"]
    assert not stale_events, "stale-run event should have been dropped"


def test_control_request_can_use_tool_allowed(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-CT")
    for _ in range(50):
        if "conv-CT" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-CT"]
    _feed_init(proc, conv_id="conv-CT")
    handle = fut.result(timeout=2)

    proc.stdout.push_event({
        "type": "control_request",
        "request_id": "req-1",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {}},
    })
    time.sleep(0.1)

    # Backend should have written a control_response allowing the tool.
    responses = [
        json.loads(l) for l in proc.stdin.lines
        if '"control_response"' in l
    ]
    assert responses, f"expected control_response, got {proc.stdin.lines}"
    last = responses[-1]
    assert last["response"]["request_id"] == "req-1"
    assert last["response"]["response"]["behavior"] == "allow"


def test_control_request_interactive_tool_denied(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-CD")
    for _ in range(50):
        if "conv-CD" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-CD"]
    _feed_init(proc, conv_id="conv-CD")
    handle = fut.result(timeout=2)

    proc.stdout.push_event({
        "type": "control_request",
        "request_id": "req-2",
        "request": {
            "subtype": "can_use_tool",
            "tool_name": "AskUserQuestion",
            "input": {},
        },
    })
    time.sleep(0.1)

    responses = [
        json.loads(l) for l in proc.stdin.lines
        if '"control_response"' in l
    ]
    assert responses
    last = responses[-1]
    assert last["response"]["request_id"] == "req-2"
    assert last["response"]["response"]["behavior"] == "deny"


def test_control_request_unknown_subtype_error(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-CU")
    for _ in range(50):
        if "conv-CU" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-CU"]
    _feed_init(proc, conv_id="conv-CU")
    handle = fut.result(timeout=2)

    proc.stdout.push_event({
        "type": "control_request",
        "request_id": "req-3",
        "request": {"subtype": "probably_not_real"},
    })
    time.sleep(0.1)

    errors = [
        json.loads(l) for l in proc.stdin.lines
        if '"control_response"' in l and '"error"' in l
    ]
    assert errors, f"expected error response, got {proc.stdin.lines}"


def test_lru_eviction_skips_in_flight(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    """Fill to max_concurrent=3, mark one in-flight, add a 4th.
    The in-flight one must survive; a different one evicts.
    """
    # Spawn 3 handles.
    handles = []
    for name in ["a", "b", "c"]:
        fut = _ensure_async(registry, "agent-A", f"conv-{name}")
        for _ in range(50):
            if f"conv-{name}" in fake_processes:
                break
            time.sleep(0.01)
        _feed_init(fake_processes[f"conv-{name}"], conv_id=f"conv-{name}")
        handles.append(fut.result(timeout=2))

    # Make conv-a OLDEST but in-flight. conv-b is middle. conv-c is newest.
    time.sleep(0.01)
    handles[0].last_used_at = 100.0  # oldest
    handles[1].last_used_at = 200.0
    handles[2].last_used_at = 300.0
    handles[0].in_flight = True  # in-flight → must survive eviction

    # Add a fourth conv → eviction should fire.
    fut4 = _ensure_async(registry, "agent-A", "conv-d")
    for _ in range(50):
        if "conv-d" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-d"], conv_id="conv-d")
    fut4.result(timeout=2)

    remaining = {h["conv_id"] for h in registry.list_handles()}
    assert "conv-a" in remaining, "in-flight conv must not be evicted"
    assert "conv-d" in remaining
    # conv-b (next-oldest non-active) should be the victim.
    assert "conv-b" not in remaining


def test_invalidate_bumps_generation(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-I")
    for _ in range(50):
        if "conv-I" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-I"], conv_id="conv-I")
    h1 = fut.result(timeout=2)

    registry.invalidate("conv-I")
    # Now ensure() should respawn.
    fut2 = _ensure_async(registry, "agent-A", "conv-I")

    for _ in range(50):
        if "conv-I" in fake_processes and fake_processes["conv-I"] is not h1.process:
            break
        time.sleep(0.01)

    _feed_init(fake_processes["conv-I"], conv_id="conv-I")
    h2 = fut2.result(timeout=2)

    assert h1 is not h2
    assert h2.generation > h1.generation


def test_shutdown_terminates_all_subprocesses(
    spawn_factory: Callable[..., FakePopen],
    fake_processes: Dict[str, FakePopen],
) -> None:
    reg = sp.SubprocessRegistry(
        max_concurrent=5,
        init_timeout_s=2.0,
        spawn_factory=spawn_factory,
    )
    try:
        handles = []
        for name in ["a", "b"]:
            fut = _ensure_async(reg, "agent-A", f"conv-{name}")
            for _ in range(50):
                if f"conv-{name}" in fake_processes:
                    break
                time.sleep(0.01)
            _feed_init(fake_processes[f"conv-{name}"], conv_id=f"conv-{name}")
            handles.append(fut.result(timeout=2))

        reg.shutdown(grace_s=0.5)

        for h in handles:
            assert not h.alive
            # Fake poll should return a set returncode after terminate.
            assert h.process.poll() is not None
    finally:
        pass  # already shut down


def test_env_scrub_in_default_spawn_factory(monkeypatch) -> None:
    """R30: the default spawn factory must not pass container env vars."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-password")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dangerous-key")

    captured: Dict[str, Any] = {}
    original_popen = subprocess.Popen

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        captured["cwd"] = kwargs.get("cwd")
        # Return a fake that won't actually run.
        return FakePopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    sp.SubprocessRegistry._default_spawn_factory(
        agent_id="agent-X",
        conv_id="conv-X",
        cwd="/workspace-safe",
        letta_binary="letta",
        letta_base_url="http://letta:8283",
        allowed_tools=("Bash", "Read"),
        disallowed_tools=("Task", "TodoWrite"),
        yolo=True,
    )

    env = captured["env"]
    assert "POSTGRES_PASSWORD" not in env, "container secret leaked into env!"
    assert "OPENAI_API_KEY" not in env
    assert env["LETTA_BASE_URL"] == "http://letta:8283"
    assert env["PATH"].startswith("/usr/local/bin")
    assert env["HOME"] == "/root"

    args = captured["args"]
    assert "--yolo" in args
    assert "--agent" in args and "agent-X" in args
    assert "--conversation" in args and "conv-X" in args
    assert "--output-format" in args and "stream-json" in args
    assert "Task,TodoWrite" in args


def test_describe_reports_state(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-desc")
    for _ in range(50):
        if "conv-desc" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-desc"], conv_id="conv-desc")
    handle = fut.result(timeout=2)

    snapshot = handle.describe()
    assert snapshot["conv_id"] == "conv-desc"
    assert snapshot["alive"] is True
    assert snapshot["in_flight"] is False
    assert snapshot["subscriber_count"] == 0
    assert snapshot["init_state"]["memfs_enabled"] is True


def test_broken_pipe_on_write_marks_dead(
    registry: sp.SubprocessRegistry, fake_processes: Dict[str, FakePopen]
) -> None:
    fut = _ensure_async(registry, "agent-A", "conv-BP")
    for _ in range(50):
        if "conv-BP" in fake_processes:
            break
        time.sleep(0.01)
    _feed_init(fake_processes["conv-BP"], conv_id="conv-BP")
    handle = fut.result(timeout=2)

    # Simulate stdin close.
    fake_processes["conv-BP"].stdin.close()
    fake_processes["conv-BP"]._returncode = 1

    with pytest.raises(sp.SubprocessDeadError):
        registry.send(handle, "hello", device_id="dev-1")
    assert not handle.alive
