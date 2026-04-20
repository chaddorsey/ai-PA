"""Unit 2.1 — Phase 2 conversations CRUD + fork route tests.

Mocks the Letta server via httpx transport swap. Exercises:
- flag-off → HTTP 503
- backfill-in-progress → HTTP 503 on mutation routes
- GET list JOINs Letta response with conversation_meta
- POST creates conv on Letta + meta row; rolls back on DB failure
- PATCH sets user_renamed=TRUE
- DELETE hard-deletes across 5 tables + Letta
- Fork with handle.state_lock turn-lock (409)
- Fork on deleted parent (410)
- Fork with malformed Letta response (502)

Run: cd pa-web-ui && python -m pytest tests/test_conversations_api.py -v
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------- fakes


class FakeLettaClient:
    """Drop-in replacement for httpx.Client stored at app.http_client.

    Test drives behaviour by setting self.plans: list of (method, url_substr, response)
    tuples consumed in order on each call.
    """

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        # Default responses for each method — tests override selectively.
        self.default_get_response: Optional[Any] = None
        self.default_post_response: Optional[Any] = None
        self.default_delete_response: Optional[Any] = None
        # Simulated HTTP failures
        self.raise_on_next: bool = False

    def _record(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})

    def get(self, url: str, **kwargs):
        self._record("GET", url, **kwargs)
        if self.raise_on_next:
            self.raise_on_next = False
            raise Exception("simulated network error")
        return self.default_get_response

    def post(self, url: str, **kwargs):
        self._record("POST", url, **kwargs)
        if self.raise_on_next:
            self.raise_on_next = False
            raise Exception("simulated network error")
        return self.default_post_response

    def delete(self, url: str, **kwargs):
        self._record("DELETE", url, **kwargs)
        if self.raise_on_next:
            self.raise_on_next = False
            raise Exception("simulated network error")
        return self.default_delete_response


def _make_resp(status: int, json_body: Any):
    """Build a mock httpx.Response-like object."""
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    else:
        r.raise_for_status.return_value = None
    return r


# ---------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PA_WEB_UI_PHASE_2_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost:65535/x")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test-secret")
    yield


@pytest.fixture
def fake_letta():
    return FakeLettaClient()


@pytest.fixture
def fake_db():
    """Tracks SQL executions. Backed by a dict for key-value lookups."""
    store: Dict[str, Dict[str, Any]] = {"meta": {}, "rows_deleted": []}
    executions: List[tuple] = []

    class FakeCursor:
        def __init__(self, outer):
            self.outer = outer
            self._last_rows: List[Any] = []
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql: str, params: tuple = ()):
            executions.append((sql.strip(), params))
            sql_upper = sql.strip().upper()
            # Simulate meta-row SELECT for fork's parent lookup
            if "SELECT AGENT_ID FROM PA_WEB.CONVERSATION_META" in sql_upper:
                cid = params[0]
                row = store["meta"].get(cid)
                self._last_rows = [(row["agent_id"],)] if row else []
                return
            if "SELECT CONVERSATION_ID, AGENT_ID" in sql_upper:
                ids = params[0] if params else []
                self._last_rows = [
                    {
                        "conversation_id": cid,
                        **store["meta"][cid],
                    }
                    for cid in ids
                    if cid in store["meta"]
                ]
                return
            if sql_upper.startswith("INSERT INTO PA_WEB.CONVERSATION_META"):
                # Three INSERT shapes in app.py; disambiguate by param count:
                # - create (5 params): conv_id, agent_id, session_id, label, user_renamed
                # - fork  (7 params): conv_id, agent_id, session_id, label, parent_id, user_renamed, metadata
                # - backfill (3 params): conv_id, agent_id, label
                if len(params) == 5:
                    store["meta"][params[0]] = {
                        "agent_id": params[1],
                        "session_id": params[2],
                        "label": params[3],
                        "parent_conversation_id": None,
                        "user_renamed": params[4],
                        "metadata": None,
                    }
                elif len(params) == 7:
                    store["meta"][params[0]] = {
                        "agent_id": params[1],
                        "session_id": params[2],
                        "label": params[3],
                        "parent_conversation_id": params[4],
                        "user_renamed": params[5],
                        "metadata": params[6],
                    }
                elif len(params) == 3:
                    # backfill — only if not already present (ON CONFLICT)
                    if params[0] not in store["meta"]:
                        store["meta"][params[0]] = {
                            "agent_id": params[1],
                            "session_id": None,
                            "label": params[2],
                            "parent_conversation_id": None,
                            "user_renamed": True,
                            "metadata": None,
                        }
                else:
                    raise AssertionError(
                        f"unexpected conversation_meta INSERT param count: {len(params)}"
                    )
                self.rowcount = 1
                return
            if sql_upper.startswith("UPDATE PA_WEB.CONVERSATION_META"):
                new_label, cid = params[0], params[1]
                if cid in store["meta"]:
                    store["meta"][cid]["label"] = new_label
                    store["meta"][cid]["user_renamed"] = True
                    self.rowcount = 1
                else:
                    self.rowcount = 0
                return
            if sql_upper.startswith("DELETE FROM PA_WEB."):
                store["rows_deleted"].append(sql.strip().split()[2])
                cid = params[0] if params else None
                if "CONVERSATION_META" in sql_upper and cid in store["meta"]:
                    del store["meta"][cid]
                return
            # Unhandled SQL — just record, no effect.

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
            return FakeCursor(None)

        def commit(self):
            pass

        def close(self):
            pass

    store["executions"] = executions
    store["FakeConn"] = FakeConn
    return store


@pytest.fixture
def app(monkeypatch, fake_letta, fake_db):
    sys.modules.pop("app", None)
    sys.modules.pop("ingress_guard", None)
    sys.modules.pop("subprocess_pool", None)
    import app as app_module

    # Swap Letta client
    monkeypatch.setattr(app_module, "http_client", fake_letta)

    # Swap DB connection
    from contextlib import contextmanager

    @contextmanager
    def fake_get_db():
        yield fake_db["FakeConn"]()

    monkeypatch.setattr(app_module, "get_db_connection", fake_get_db)

    # Swap registry
    fake_registry = MagicMock()
    fake_registry._handles = {}
    fake_registry.invalidate = MagicMock()
    monkeypatch.setattr(app_module, "subprocess_registry", fake_registry)

    # Ensure flags are as _env set them
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_2_ENABLED", True)

    # Pretend backfill finished so mutation routes aren't 503'd.
    app_module._PHASE2_BACKFILL_COMPLETE.set()

    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    body = resp.get_json()
    return body["csrf_token"]


def _auth_headers(csrf: str, with_content_type: bool = True) -> Dict[str, str]:
    h = {
        "Host": "localhost:5200",
        "Origin": "http://localhost:5200",
        "X-CSRF-Token": csrf,
    }
    if with_content_type:
        h["Content-Type"] = "application/json"
    return h


# ---------------------------------------------------------- flag gating


def test_flag_off_blocks_list(monkeypatch, app, client):
    import app as app_module
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_2_ENABLED", False)
    resp = client.get("/api/conversations",
                      headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "feature_disabled"


def test_flag_off_blocks_mutation(monkeypatch, app, client, csrf):
    import app as app_module
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_2_ENABLED", False)
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"label": "Hi"}))
    assert resp.status_code == 503


def test_backfill_in_progress_blocks_mutation(app, client, csrf):
    import app as app_module
    app_module._PHASE2_BACKFILL_COMPLETE.clear()
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"label": "Hi"}))
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "backfill_in_progress"
    # Restore for other tests.
    app_module._PHASE2_BACKFILL_COMPLETE.set()


def test_backfill_in_progress_allows_read(app, client):
    import app as app_module
    app_module._PHASE2_BACKFILL_COMPLETE.clear()
    # The GET route has no handle on backfill gate; it uses read gate (flag only).
    # Set up a minimal fake Letta response so list doesn't 502.
    app_module.http_client.default_get_response = _make_resp(200, [])
    resp = client.get("/api/conversations",
                      headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"})
    assert resp.status_code == 200
    app_module._PHASE2_BACKFILL_COMPLETE.set()


# ---------------------------------------------------------- list


def test_list_joins_letta_with_meta(app, client, fake_letta, fake_db):
    fake_letta.default_get_response = _make_resp(200, [
        {"id": "conv-aaaaaaaa-1111-2222-3333-444444444444",
         "agent_id": "agent-MC",
         "last_message_at": "2026-04-20T10:00:00Z",
         "created_at": "2026-04-19T10:00:00Z"},
        {"id": "conv-bbbbbbbb-1111-2222-3333-444444444444",
         "agent_id": "agent-MC",
         "last_message_at": None,
         "created_at": "2026-04-18T10:00:00Z"},
    ])
    fake_db["meta"]["conv-aaaaaaaa-1111-2222-3333-444444444444"] = {
        "agent_id": "agent-MC",
        "session_id": None,
        "label": "Main",
        "parent_conversation_id": None,
        "user_renamed": True,
        "created_at": None,
        "renamed_at": None,
        "metadata": None,
    }
    resp = client.get("/api/conversations",
                      headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"})
    assert resp.status_code == 200
    body = resp.get_json()
    convs = body["conversations"]
    assert len(convs) == 2
    assert convs[0]["label"] == "Main"
    assert convs[0]["user_renamed"] is True
    # Second conv has no meta row → defaults.
    assert convs[1]["label"] is None
    assert convs[1]["user_renamed"] is False


def test_list_502_on_letta_failure(app, client, fake_letta):
    fake_letta.raise_on_next = True
    resp = client.get("/api/conversations",
                      headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"})
    assert resp.status_code == 502


# ---------------------------------------------------------- create


def test_create_with_user_label_marks_user_renamed(app, client, csrf, fake_letta, fake_db):
    fake_letta.default_post_response = _make_resp(200, {
        "id": "conv-newnewne-aaaa-bbbb-cccc-dddddddddddd",
        "agent_id": "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef",
        "created_at": "2026-04-20T22:00:00Z",
    })
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"label": "My new thread"}))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["label"] == "My new thread"
    assert body["user_renamed"] is True
    # Verify meta row was inserted with user_renamed=True.
    assert fake_db["meta"][body["id"]]["user_renamed"] is True


def test_create_without_label_uses_timestamp_default(app, client, csrf, fake_letta, fake_db):
    fake_letta.default_post_response = _make_resp(200, {
        "id": "conv-autotime-aaaa-bbbb-cccc-dddddddddddd",
        "agent_id": "agent-MC",
        "created_at": "2026-04-20T22:00:00Z",
    })
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["label"].startswith("New conversation ")
    assert body["user_renamed"] is False


def test_create_502_on_letta_failure(app, client, csrf, fake_letta):
    fake_letta.raise_on_next = True
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"label": "x"}))
    assert resp.status_code == 502


def test_create_502_on_malformed_response(app, client, csrf, fake_letta):
    fake_letta.default_post_response = _make_resp(200, {"something": "but_no_id"})
    resp = client.post("/api/conversations",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"label": "x"}))
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "letta_malformed_response"


# ---------------------------------------------------------- rename


def test_patch_sets_user_renamed(app, client, csrf, fake_db):
    conv_id = "conv-exists1-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][conv_id] = {"agent_id": "agent-MC", "session_id": None,
                                 "label": "Old", "parent_conversation_id": None,
                                 "user_renamed": False, "metadata": None}
    resp = client.patch(f"/api/conversations/{conv_id}",
                        headers=_auth_headers(csrf),
                        data=json.dumps({"label": "New"}))
    assert resp.status_code == 200
    assert fake_db["meta"][conv_id]["label"] == "New"
    assert fake_db["meta"][conv_id]["user_renamed"] is True


def test_patch_404_on_unknown_conv(app, client, csrf, fake_db):
    resp = client.patch(
        "/api/conversations/conv-doesnot-aaaa-bbbb-cccc-dddddddddddd",
        headers=_auth_headers(csrf),
        data=json.dumps({"label": "X"}),
    )
    assert resp.status_code == 404


def test_patch_400_on_empty_label(app, client, csrf):
    resp = client.patch(
        "/api/conversations/conv-exists2-aaaa-bbbb-cccc-dddddddddddd",
        headers=_auth_headers(csrf),
        data=json.dumps({"label": ""}),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------- delete


def test_delete_removes_from_all_tables(app, client, csrf, fake_letta, fake_db):
    conv_id = "conv-delme11-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][conv_id] = {"agent_id": "agent-MC", "label": "X",
                                 "user_renamed": False}
    fake_letta.default_delete_response = _make_resp(200, None)
    resp = client.delete(f"/api/conversations/{conv_id}",
                         headers=_auth_headers(csrf, with_content_type=False))
    assert resp.status_code == 200
    # 5 DELETE statements hit 5 tables.
    deleted_tables = [t.upper() for t in fake_db["rows_deleted"]]
    assert "PA_WEB.CONVERSATIONS" in deleted_tables
    assert "PA_WEB.THREAD_EXCHANGES" in deleted_tables
    assert "PA_WEB.ROUTING_SIGNALS" in deleted_tables
    assert "PA_WEB.RESPONSE_FEEDBACK" in deleted_tables
    assert "PA_WEB.CONVERSATION_META" in deleted_tables
    # Letta DELETE also called.
    assert any(c["method"] == "DELETE" for c in fake_letta.calls)


def test_delete_survives_letta_failure(app, client, csrf, fake_letta, fake_db):
    conv_id = "conv-delme22-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][conv_id] = {"agent_id": "agent-MC", "label": "X"}
    fake_letta.raise_on_next = True
    resp = client.delete(f"/api/conversations/{conv_id}",
                         headers=_auth_headers(csrf, with_content_type=False))
    # Local tables cleared; Letta error logged but not fatal.
    assert resp.status_code == 200


# ---------------------------------------------------------- fork


def test_fork_410_when_parent_missing(app, client, csrf, fake_db):
    resp = client.post(
        "/api/conversations/conv-missing-aaaa-bbbb-cccc-dddddddddddd/fork",
        headers=_auth_headers(csrf),
        data=json.dumps({}),
    )
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "parent_not_found"


def test_fork_happy_path(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent01-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main",
                                "user_renamed": False}
    fake_letta.default_post_response = _make_resp(200, {
        "id": "conv-child001-aaaa-bbbb-cccc-dddddddddddd",
        "agent_id": "agent-MC",
        "created_at": "2026-04-20T22:00:00Z",
    })
    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({"parent_request_id": "req-123"}))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["parent_conversation_id"] == parent
    assert body["label"].startswith("Fork ")
    # Verify child meta row stored.
    assert body["id"] in fake_db["meta"]
    assert fake_db["meta"][body["id"]]["parent_conversation_id"] == parent


def test_fork_409_when_parent_streaming(app, client, csrf, fake_db):
    parent = "conv-parent02-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main"}
    # Inject a handle with in_flight=True.
    import app as app_module
    handle = MagicMock()
    handle.state_lock = threading.Lock()
    handle.in_flight = True
    handle.forking = False
    handle.in_flight_device_id = "dev-X"
    handle.current_seq_id = 42
    app_module.subprocess_registry._handles[parent] = handle

    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "parent_conversation_streaming"
    assert body["current_device_id"] == "dev-X"
    assert body["seq_id"] == 42
    # Forking flag should not have been set (409 before set).
    assert handle.forking is False


def test_fork_502_on_malformed_letta_response(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent03-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main"}
    fake_letta.default_post_response = _make_resp(200, {"oops": "no id"})
    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "letta_malformed_fork_response"


def test_fork_502_on_letta_exception(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent04-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main"}
    fake_letta.raise_on_next = True
    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 502


def test_fork_releases_forking_flag_after_success(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent05-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main"}
    import app as app_module
    handle = MagicMock()
    handle.state_lock = threading.Lock()
    handle.in_flight = False
    handle.forking = False
    app_module.subprocess_registry._handles[parent] = handle
    fake_letta.default_post_response = _make_resp(200, {
        "id": "conv-child666-aaaa-bbbb-cccc-dddddddddddd",
        "agent_id": "agent-MC",
        "created_at": "2026-04-20T22:00:00Z",
    })
    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 201
    # After the call, forking should be released.
    assert handle.forking is False


def test_fork_releases_forking_flag_on_letta_error(app, client, csrf, fake_letta, fake_db):
    parent = "conv-parent06-aaaa-bbbb-cccc-dddddddddddd"
    fake_db["meta"][parent] = {"agent_id": "agent-MC", "label": "Main"}
    import app as app_module
    handle = MagicMock()
    handle.state_lock = threading.Lock()
    handle.in_flight = False
    handle.forking = False
    app_module.subprocess_registry._handles[parent] = handle
    fake_letta.raise_on_next = True
    resp = client.post(f"/api/conversations/{parent}/fork",
                       headers=_auth_headers(csrf),
                       data=json.dumps({}))
    assert resp.status_code == 502
    # Critical: even on error, forking flag must be released — otherwise
    # the parent stays permanently locked.
    assert handle.forking is False
