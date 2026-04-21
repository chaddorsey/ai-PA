"""Phase 3 — inline /btw side-query route tests.

Covers the POST /api/conversations/<parent>/btw route:
- flag gating
- input validation (invalid conv id, missing question)
- parent resolution (conv_meta hit, Letta fallback, parent-missing 410)
- Letta fork failure → 502
- happy path → 200 SSE stream starting with btw_start
- subprocess spawned with BTW_DISALLOWED_TOOLS override
- handle invalidated + delete scheduled after stream completes
"""

from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------- fakes


class FakeLettaClient:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.default_get_response: Any = None
        self.default_post_response: Any = None
        self.default_delete_response: Any = None
        self.raise_post: bool = False

    def get(self, url: str, **kwargs):
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self.default_get_response

    def post(self, url: str, **kwargs):
        self.calls.append({"method": "POST", "url": url, **kwargs})
        if self.raise_post:
            self.raise_post = False
            raise Exception("simulated network error")
        return self.default_post_response

    def delete(self, url: str, **kwargs):
        self.calls.append({"method": "DELETE", "url": url, **kwargs})
        return self.default_delete_response


def _make_resp(status: int, json_body: Any):
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=json_body)
    r.raise_for_status = MagicMock(
        side_effect=(None if status < 400 else Exception(f"HTTP {status}"))
    )
    return r


# ---------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PA_WEB_UI_PHASE_2_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost:65535/x")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test-secret")
    # Short idle TTL so sliding-timer cleanup fires quickly in tests.
    monkeypatch.setenv("PA_WEB_UI_BTW_IDLE_TTL_S", "0.05")
    yield


@pytest.fixture
def fake_letta():
    return FakeLettaClient()


@pytest.fixture
def fake_db():
    store: Dict[str, Dict[str, Any]] = {"meta": {}}

    class FakeCursor:
        def __init__(self):
            self._last_rows: List[Any] = []
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql: str, params: tuple = ()):
            sql_upper = sql.strip().upper()
            if "SELECT AGENT_ID FROM PA_WEB.CONVERSATION_META" in sql_upper:
                cid = params[0]
                row = store["meta"].get(cid)
                self._last_rows = [(row["agent_id"],)] if row else []

        def fetchone(self):
            return self._last_rows[0] if self._last_rows else None

        def fetchall(self):
            return list(self._last_rows)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self, cursor_factory=None):
            return FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    store["FakeConn"] = FakeConn
    return store


@pytest.fixture
def app(monkeypatch, fake_letta, fake_db):
    sys.modules.pop("app", None)
    sys.modules.pop("ingress_guard", None)
    sys.modules.pop("subprocess_pool", None)
    import app as app_module

    monkeypatch.setattr(app_module, "http_client", fake_letta)

    @contextmanager
    def fake_get_db():
        yield fake_db["FakeConn"]()

    monkeypatch.setattr(app_module, "get_db_connection", fake_get_db)

    # Fake registry — ensure() records the disallowed_tools_override it got.
    fake_registry = MagicMock()
    fake_registry._handles = {}
    fake_registry.ensure_calls: List[Dict[str, Any]] = []

    def fake_ensure(agent_id, conv_id, disallowed_tools_override=None):
        fake_registry.ensure_calls.append({
            "agent_id": agent_id,
            "conv_id": conv_id,
            "disallowed_tools_override": disallowed_tools_override,
        })
        handle = MagicMock()
        handle.subscribe = MagicMock(return_value=MagicMock())
        handle.unsubscribe = MagicMock()
        return handle

    fake_registry.ensure = fake_ensure
    fake_registry.send = MagicMock()
    fake_registry.invalidate = MagicMock()
    monkeypatch.setattr(app_module, "subprocess_registry", fake_registry)

    # Short-circuit the streaming translator so tests don't need a real
    # subprocess. Yields one event and stops.
    def fake_stream(subscriber, session_id, request_id, conv_id, first_user_message):
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    monkeypatch.setattr(app_module, "_stream_direct_generator", fake_stream)

    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_2_ENABLED", True)
    app_module._PHASE2_BACKFILL_COMPLETE.set()

    app_module._test_registry = fake_registry  # exposed for assertions
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    return resp.get_json()["csrf_token"]


def _auth_headers(csrf: str) -> Dict[str, str]:
    return {
        "Host": "localhost:5200",
        "Origin": "http://localhost:5200",
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------- tests


def test_flag_off_blocks_btw(monkeypatch, app, client, csrf):
    import app as app_module
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_2_ENABLED", False)
    resp = client.post(
        "/api/conversations/conv-aaaaaaaa-1111-2222-3333-444444444444/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "hi"}),
    )
    assert resp.status_code == 503


def test_invalid_conv_id_rejected(app, client, csrf):
    resp = client.post(
        "/api/conversations/1bad-id/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "hi"}),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_conversation_id"


def test_missing_question_rejected(app, client, csrf):
    resp = client.post(
        "/api/conversations/conv-aaaaaaaa-1111-2222-3333-444444444444/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({}),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "question_required"


def test_parent_not_found_returns_410(app, client, csrf, fake_letta):
    fake_letta.default_get_response = _make_resp(404, {})
    resp = client.post(
        "/api/conversations/conv-missing1-1111-2222-3333-444444444444/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "hi"}),
    )
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "parent_not_found"


def test_letta_fork_failure_returns_502(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent07-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.raise_post = True
    resp = client.post(
        f"/api/conversations/{parent}/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "hi"}),
    )
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "letta_fork_failed"


def test_btw_malformed_fork_response_502(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent08-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.default_post_response = _make_resp(200, {"oops": "no id"})
    resp = client.post(
        f"/api/conversations/{parent}/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "hi"}),
    )
    assert resp.status_code == 502


def test_btw_happy_path_streams_and_spawns_restricted_subprocess(
    app, client, csrf, fake_letta, fake_db
):
    import app as app_module
    parent = "conv-parent09-aaaa-bbbb-cccc-dddddddddddd"
    fork_id = "conv-fork0001-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.default_post_response = _make_resp(200, {
        "id": fork_id,
        "agent_id": "agent-MC",
    })
    # DELETE will fire after the stream ends (delay=0 via env).
    fake_letta.default_delete_response = _make_resp(200, {})

    resp = client.post(
        f"/api/conversations/{parent}/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "what time is it"}),
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # First event must be btw_start, carrying both ids.
    assert 'btw_start' in body
    assert fork_id in body
    assert parent in body

    # Subprocess was spawned with the BTW disallowed-tools override.
    calls = app_module._test_registry.ensure_calls
    assert len(calls) == 1
    assert calls[0]["conv_id"] == fork_id
    assert calls[0]["disallowed_tools_override"] == app_module.BTW_DISALLOWED_TOOLS

    # send() was invoked with the question.
    assert app_module._test_registry.send.called
    args, kwargs = app_module._test_registry.send.call_args
    # Signature: send(handle, message, device_id=...)
    assert args[1] == "what time is it"

    # Sliding idle timer should fire promptly (TTL=0.05s in tests) and
    # tear down the fork — both DELETE on Letta and invalidate().
    import time as _time
    deadline = _time.time() + 2.0
    while _time.time() < deadline:
        if app_module._test_registry.invalidate.called:
            break
        _time.sleep(0.02)
    assert app_module._test_registry.invalidate.called, "idle timer did not fire"
    assert app_module._test_registry.invalidate.call_args[0][0] == fork_id


def test_btw_continue_unknown_fork_returns_410(app, client, csrf):
    resp = client.post(
        "/api/conversations/conv-unknown2-aaaa-bbbb-cccc-dddddddddddd/btw/continue",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "follow up"}),
    )
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "btw_fork_expired"


def test_btw_continue_requires_question(app, client, csrf, fake_letta, fake_db):
    """First do a /btw so the fork is registered, then call /continue with
    no question."""
    import app as app_module
    parent = "conv-parent20-aaaa-bbbb-cccc-dddddddddddd"
    fork_id = "conv-fork0020-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.default_post_response = _make_resp(200, {"id": fork_id, "agent_id": "agent-MC"})
    fake_letta.default_delete_response = _make_resp(200, {})
    # Use a long TTL just for this test so the fork stays registered.
    app_module.BTW_IDLE_TTL_S = 60
    r1 = client.post(f"/api/conversations/{parent}/btw",
                     headers=_auth_headers(csrf),
                     data=json.dumps({"question": "hi"}))
    assert r1.status_code == 200
    # Consume the stream so the finally: clause runs and arms the timer.
    r1.get_data(as_text=True)

    r2 = client.post(f"/api/conversations/{fork_id}/btw/continue",
                     headers=_auth_headers(csrf),
                     data=json.dumps({}))
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "question_required"
    app_module._btw_force_end(fork_id)


def test_btw_continue_happy_path(app, client, csrf, fake_letta, fake_db):
    import app as app_module
    parent = "conv-parent21-aaaa-bbbb-cccc-dddddddddddd"
    fork_id = "conv-fork0021-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.default_post_response = _make_resp(200, {"id": fork_id, "agent_id": "agent-MC"})
    fake_letta.default_delete_response = _make_resp(200, {})
    app_module.BTW_IDLE_TTL_S = 60

    r1 = client.post(f"/api/conversations/{parent}/btw",
                     headers=_auth_headers(csrf),
                     data=json.dumps({"question": "initial"}))
    r1.get_data(as_text=True)

    # Reset recorded ensure/send calls so the continue-turn assertions are clean.
    app_module._test_registry.ensure_calls.clear()
    app_module._test_registry.send.reset_mock()

    r2 = client.post(f"/api/conversations/{fork_id}/btw/continue",
                     headers=_auth_headers(csrf),
                     data=json.dumps({"question": "follow up"}))
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert "btw_continue" in body
    # Continue reuses the fork_conv_id — ensure() called on the fork, not parent.
    assert app_module._test_registry.ensure_calls[0]["conv_id"] == fork_id
    assert app_module._test_registry.ensure_calls[0]["disallowed_tools_override"] \
        == app_module.BTW_DISALLOWED_TOOLS
    assert app_module._test_registry.send.call_args[0][1] == "follow up"
    app_module._btw_force_end(fork_id)


def test_btw_end_tears_down_fork(app, client, csrf, fake_letta, fake_db):
    import app as app_module
    parent = "conv-parent22-aaaa-bbbb-cccc-dddddddddddd"
    fork_id = "conv-fork0022-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC"}
    fake_letta.default_post_response = _make_resp(200, {"id": fork_id, "agent_id": "agent-MC"})
    fake_letta.default_delete_response = _make_resp(200, {})
    app_module.BTW_IDLE_TTL_S = 60

    r1 = client.post(f"/api/conversations/{parent}/btw",
                     headers=_auth_headers(csrf),
                     data=json.dumps({"question": "hi"}))
    r1.get_data(as_text=True)

    r2 = client.post(f"/api/conversations/{fork_id}/btw/end",
                     headers=_auth_headers(csrf),
                     data="")
    assert r2.status_code == 200
    assert r2.get_json()["ended"] is True
    assert app_module._test_registry.invalidate.called
    # Second /end is idempotent: returns ended=False (not known anymore).
    r3 = client.post(f"/api/conversations/{fork_id}/btw/end",
                     headers=_auth_headers(csrf),
                     data="")
    assert r3.status_code == 200
    assert r3.get_json()["ended"] is False


def test_btw_falls_back_to_letta_lookup_when_no_meta_row(
    app, client, csrf, fake_letta, fake_db
):
    """Parent has no conversation_meta row (pre-existing Letta conv) —
    route should fetch agent_id via GET /v1/conversations/<parent>/."""
    parent = "conv-parent10-aaaa-bbbb-cccc-dddddddddddd"
    fork_id = "conv-fork0002-aaaa-bbbb-cccc-dddddddddddd"
    # No meta row seeded.
    fake_letta.default_get_response = _make_resp(200, {"agent_id": "agent-LKP"})
    fake_letta.default_post_response = _make_resp(200, {
        "id": fork_id,
        "agent_id": "agent-LKP",
    })
    fake_letta.default_delete_response = _make_resp(200, {})

    resp = client.post(
        f"/api/conversations/{parent}/btw",
        headers=_auth_headers(csrf),
        data=json.dumps({"question": "check this"}),
    )
    assert resp.status_code == 200
    # Verify we GETted the parent to resolve agent_id.
    get_calls = [c for c in fake_letta.calls if c["method"] == "GET"]
    assert any(parent in c["url"] for c in get_calls)
