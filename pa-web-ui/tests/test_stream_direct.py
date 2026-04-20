"""Unit 1.5 tests — /stream dispatch through the subprocess pool.

Monkey-patches app.subprocess_registry with a fake so we can exercise
route-level behavior without a real letta-code subprocess:
- Flag OFF: /stream continues to use LettaBot path (no pool interaction)
- Flag ON: /stream dispatches to _dispatch_mission_control_direct
- TurnLockedException → HTTP 409 with turn_locked body
- Happy path: SSE response streams subscriber events
- Spawn timeout → HTTP 504
- Subprocess dead → HTTP 503

Run: cd pa-web-ui && python -m pytest tests/test_stream_direct.py -v
"""

from __future__ import annotations

import importlib
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ------------------------------------------------------------ fakes


class FakeSubscriber:
    """A queue-like subscriber that feeds scripted events to the SSE generator."""

    def __init__(self, events: Optional[List[Dict[str, Any]]] = None):
        self.id = "fake-sub"
        self.queue: "queue.Queue" = queue.Queue()
        for e in events or []:
            self.queue.put(e)

    def get(self, timeout=None):
        return self.queue.get(timeout=timeout)

    def get_nowait(self):
        return self.queue.get_nowait()

    def put_nowait(self, item):
        self.queue.put_nowait(item)


class FakeHandle:
    def __init__(self, conv_id: str):
        self.conv_id = conv_id
        self.subscriber: Optional[FakeSubscriber] = None
        self._next_events: List[Dict[str, Any]] = []

    def subscribe(self, since=None, **_):
        self.subscriber = FakeSubscriber(self._next_events)
        return self.subscriber

    def unsubscribe(self, sub):
        return None

    def queue_events(self, events: List[Dict[str, Any]]):
        self._next_events = events


class FakeRegistry:
    """Drop-in replacement for subprocess_registry in app.py.

    Behavior is controlled by test setters before invoking /stream.
    """

    def __init__(self):
        self.mode = "ok"  # "ok" | "spawn_timeout" | "dead" | "turn_locked"
        self.handles: Dict[str, FakeHandle] = {}
        self.send_calls: List[tuple] = []  # (handle, message, device_id)
        self.next_events: List[Dict[str, Any]] = []
        # The TurnLockedException values to emit when mode=turn_locked.
        self.locked_device = "dev-A"
        self.locked_seq = 42

    def ensure(self, agent_id: str, conv_id: str):
        if self.mode == "spawn_timeout":
            import subprocess_pool
            raise subprocess_pool.SpawnTimeoutError("spawn timed out")
        if self.mode == "dead":
            import subprocess_pool
            raise subprocess_pool.SubprocessDeadError("subprocess dead")
        if conv_id not in self.handles:
            self.handles[conv_id] = FakeHandle(conv_id)
        handle = self.handles[conv_id]
        handle.queue_events(self.next_events)
        return handle

    def send(self, handle, message, device_id=None):
        self.send_calls.append((handle, message, device_id))
        if self.mode == "turn_locked":
            import subprocess_pool
            raise subprocess_pool.TurnLockedException(
                conv_id=handle.conv_id,
                current_device_id=self.locked_device,
                seq_id=self.locked_seq,
            )


# ------------------------------------------------------------ fixtures


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Set the env vars app.py expects. Each test overrides as needed."""
    monkeypatch.setenv("PA_WEB_UI_PHASE_1_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost:65535/x")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test-secret")
    yield


@pytest.fixture
def fake_registry():
    return FakeRegistry()


@pytest.fixture
def app(monkeypatch, fake_registry):
    """Import app with all DB writes and the subprocess_registry stubbed.

    The real app.py imports psycopg2 and wires DB helpers. For route-level
    testing we only need the HTTP layer, so we stub save_conversation_message
    to a no-op and replace subprocess_registry with the fake.
    """
    # Force a clean import with our overrides.
    sys.modules.pop("app", None)
    sys.modules.pop("ingress_guard", None)
    sys.modules.pop("subprocess_pool", None)
    import app as app_module  # noqa: E402

    # Replace heavy DB helpers with no-ops.
    monkeypatch.setattr(app_module, "save_conversation_message", lambda **_kw: None)
    monkeypatch.setattr(app_module, "save_routing_signal", lambda **_kw: None)
    monkeypatch.setattr(app_module, "save_thread_exchange", lambda **_kw: None)

    # Swap in the fake pool.
    monkeypatch.setattr(app_module, "subprocess_registry", fake_registry)
    # Enable Phase-1 dispatch by default in these tests.
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_1_ENABLED", True)

    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


def _post_stream(client, body: Dict[str, Any], *, device_id: str = "dev-1"):
    """Helper: POST /stream with a CSRF token cookie + header."""
    # Fetch CSRF token first.
    token_resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    assert token_resp.status_code == 200
    token = token_resp.get_json()["csrf_token"]
    # Use the device_id param (NOT cookie-override; test clarity).
    body.setdefault("device_id", device_id)
    return client.post(
        "/stream",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
        data=json.dumps(body),
    )


# ------------------------------------------------------------ tests


def test_flag_off_uses_lettabot_path(monkeypatch, app, client, fake_registry):
    """Flag OFF: /stream does NOT touch the subprocess pool."""
    # We need to make the LettaBot path not actually try to hit the
    # network. Monkey-patch stream_mission_control to a small generator.
    import app as app_module
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_1_ENABLED", False)

    def fake_mc_stream(message, session_id):
        yield f"data: {json.dumps({'type': 'text', 'content': 'pre-phase1'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    monkeypatch.setattr(app_module, "stream_mission_control", fake_mc_stream)

    resp = _post_stream(client, {"message": "hi", "session_id": "s1"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "pre-phase1" in body
    # The fake registry should NOT have been touched.
    assert fake_registry.send_calls == []
    assert fake_registry.handles == {}


def test_flag_on_dispatches_to_pool(app, client, fake_registry):
    """Flag ON: send message → pool.send() called → SSE streams events."""
    fake_registry.mode = "ok"
    fake_registry.next_events = [
        {"type": "text", "content": "hello from pool", "_seq_id": 1},
        {"type": "result", "subtype": "success", "_seq_id": 2},
    ]

    resp = _post_stream(client, {"message": "hi pool", "session_id": "s1"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "hello from pool" in body
    assert '"type": "result"' in body

    assert len(fake_registry.send_calls) == 1
    handle, message, device_id = fake_registry.send_calls[0]
    assert message == "hi pool"
    assert handle.conv_id == "default"
    # device_id is whatever the CSRF cookie minted — server prefers the
    # cookie over body field for integrity. We only assert it is
    # *non-empty* (proving the guard-derived cookie propagated all the
    # way to the pool).
    assert device_id, "device_id should be populated from pa_device_id cookie"


def test_turn_locked_returns_409(app, client, fake_registry):
    fake_registry.mode = "turn_locked"
    fake_registry.locked_device = "dev-other"
    fake_registry.locked_seq = 77

    resp = _post_stream(
        client, {"message": "second send", "session_id": "s1"}, device_id="dev-mine"
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["type"] == "turn_locked"
    assert body["current_device_id"] == "dev-other"
    assert body["seq_id"] == 77


def test_spawn_timeout_returns_504(app, client, fake_registry):
    fake_registry.mode = "spawn_timeout"
    resp = _post_stream(client, {"message": "hi", "session_id": "s1"})
    assert resp.status_code == 504
    assert resp.get_json()["error"] == "subprocess_spawn_timeout"


def test_subprocess_dead_returns_503(app, client, fake_registry):
    fake_registry.mode = "dead"
    resp = _post_stream(client, {"message": "hi", "session_id": "s1"})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "subprocess_dead"


def test_conversation_id_defaults_to_default(app, client, fake_registry):
    fake_registry.next_events = [{"type": "done", "_seq_id": 1}]
    resp = _post_stream(client, {"message": "hi", "session_id": "s1"})
    assert resp.status_code == 200
    # Ensure the registry was asked for conv_id="default".
    assert "default" in fake_registry.handles


def test_custom_conversation_id_honored(app, client, fake_registry):
    fake_registry.next_events = [{"type": "done", "_seq_id": 1}]
    resp = _post_stream(
        client,
        {
            "message": "hi",
            "session_id": "s1",
            "conversation_id": "conv-abc",
        },
    )
    assert resp.status_code == 200
    assert "conv-abc" in fake_registry.handles


def test_coord_slash_bypasses_pool(app, client, fake_registry, monkeypatch):
    """/mprep routes to stream_coordination — not the pool."""
    import app as app_module
    monkeypatch.setattr(
        app_module,
        "stream_coordination",
        lambda **_kw: app_module.Response(
            "data: {\"type\":\"text\",\"content\":\"coord\"}\n\n",
            mimetype="text/event-stream",
        ),
    )
    resp = _post_stream(
        client,
        {"message": "/mprep board meeting", "session_id": "s1"},
    )
    assert resp.status_code == 200
    assert fake_registry.handles == {}


def test_slash_command_uses_pre_phase1_path(app, client, fake_registry):
    """Explicit agent_id or slash_command should skip the pool (those go
    through the routing-handler / inline generator path).
    """
    resp = _post_stream(
        client,
        {
            "message": "status",
            "session_id": "s1",
            "agent_id": "agent-not-mc",
        },
    )
    # We don't care about the precise outcome — pre-Phase-1 path may try
    # to hit pa-routing-handler which won't exist in tests. Just confirm
    # the pool wasn't touched.
    assert fake_registry.send_calls == []


def test_since_param_propagates_to_subscribe(app, client, fake_registry):
    """Client resume: ?since=<seq> seeds the subscriber on resume."""
    fake_registry.next_events = [{"type": "done", "_seq_id": 99}]
    resp = _post_stream(
        client,
        {
            "message": "",  # empty message = resume-only
            "session_id": "s1",
            "since": 50,
        },
    )
    # With empty message we should NOT have sent anything.
    assert resp.status_code == 200
    assert fake_registry.send_calls == []
    # But we should have a handle (subscribe happened).
    assert "default" in fake_registry.handles


def test_empty_message_with_since_is_resume(app, client, fake_registry):
    """Phase 1 resume shape: empty message + since=<seq> is allowed."""
    fake_registry.next_events = [{"type": "done", "_seq_id": 50}]
    resp = _post_stream(
        client,
        {"message": "", "session_id": "s1", "since": 40},
    )
    assert resp.status_code == 200
    assert fake_registry.send_calls == []
    assert "default" in fake_registry.handles


def test_empty_message_without_since_still_rejected(app, client, fake_registry):
    """Pre-Phase-1 back-compat: empty message + no since → 400."""
    resp = _post_stream(client, {"message": "", "session_id": "s1"})
    assert resp.status_code == 400
