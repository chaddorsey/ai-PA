"""Unit 2.5 — LLM auto-naming tests.

Exercises _maybe_autoname_conversation with a mocked litellm client
and a mocked DB. Covers:
- flag off → no call
- default conv_id → no call
- user_renamed=TRUE → no call, no UPDATE
- label not matching timestamp pattern → no call (user set at create time)
- happy path → UPDATE fires, returns new label
- race with user rename: UPDATE WHERE user_renamed=FALSE touches 0 rows
- litellm timeout / 500 → silent fail, no UPDATE
- malformed response → silent fail

Run: cd pa-web-ui && python -m pytest tests/test_autoname.py -v
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_resp(status: int, body: Any):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    else:
        r.raise_for_status.return_value = None
    return r


class FakeHttpClient:
    def __init__(self):
        self.last_post_args = None
        self.next_post_response = None
        self.raise_on_next = False

    def post(self, url: str, **kwargs):
        self.last_post_args = (url, kwargs)
        if self.raise_on_next:
            self.raise_on_next = False
            raise Exception("simulated network error")
        return self.next_post_response

    def get(self, url: str, **kwargs):
        return _make_resp(200, [])

    def delete(self, url: str, **kwargs):
        return _make_resp(200, None)


class FakeDB:
    """Tracks meta rows + executions for race-safety verification."""

    def __init__(self):
        self.meta: Dict[str, Dict[str, Any]] = {}
        self.executions: List[tuple] = []

    def seed(self, conv_id: str, *, label: str, user_renamed: bool = False):
        self.meta[conv_id] = {"label": label, "user_renamed": user_renamed}

    def _make_cursor(self):
        db = self

        class Cursor:
            def __init__(self):
                self._rows: List[Any] = []
                self.rowcount = 0

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def execute(self, sql: str, params: tuple = ()):
                db.executions.append((sql.strip(), params))
                u = sql.strip().upper()
                if u.startswith("SELECT LABEL, USER_RENAMED"):
                    cid = params[0]
                    row = db.meta.get(cid)
                    self._rows = [(row["label"], row["user_renamed"])] if row else []
                    return
                if u.startswith("UPDATE PA_WEB.CONVERSATION_META"):
                    new_label, _ts, cid = params[0], params[1], params[2]
                    row = db.meta.get(cid)
                    if row and not row["user_renamed"]:
                        row["label"] = new_label
                        self.rowcount = 1
                    else:
                        self.rowcount = 0
                    return

            def fetchone(self):
                return self._rows[0] if self._rows else None

        return Cursor()

    @contextmanager
    def connect(self):
        db = self

        class Conn:
            def cursor(self, **_):
                return db._make_cursor()

            def commit(self):
                pass

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        yield Conn()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PA_WEB_UI_AUTONAME_ENABLED", "true")
    monkeypatch.setenv("PA_WEB_UI_AUTONAME_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost:65535/x")
    monkeypatch.setenv("LITELLM_URL", "http://fake-litellm:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test")
    yield


@pytest.fixture
def autoname_env(monkeypatch):
    """Fresh import of app.py with swapped http_client and get_db_connection.

    Returns (maybe_autoname, fake_http, fake_db, app_module) for direct
    helper-level testing.
    """
    sys.modules.pop("app", None)
    sys.modules.pop("ingress_guard", None)
    sys.modules.pop("subprocess_pool", None)
    import app as app_module

    fake_http = FakeHttpClient()
    fake_db = FakeDB()
    monkeypatch.setattr(app_module, "http_client", fake_http)
    monkeypatch.setattr(app_module, "get_db_connection", fake_db.connect)

    return app_module._maybe_autoname_conversation, fake_http, fake_db, app_module


# ----------------------------------------------------------- flag gates


def test_flag_off_returns_none(autoname_env, monkeypatch):
    autoname, fake_http, fake_db, app_module = autoname_env
    monkeypatch.setattr(app_module, "PA_WEB_UI_AUTONAME_ENABLED", False)
    fake_db.seed("conv-abc-uuid-1111", label="New conversation 2026-04-20 09:00")
    assert autoname("conv-abc-uuid-1111", "hello") is None
    assert fake_http.last_post_args is None


def test_default_conv_id_returns_none(autoname_env):
    autoname, fake_http, _, _ = autoname_env
    assert autoname("default", "hello") is None
    assert fake_http.last_post_args is None


def test_empty_message_returns_none(autoname_env):
    autoname, fake_http, _, _ = autoname_env
    assert autoname("conv-abc", "") is None
    assert fake_http.last_post_args is None


# ----------------------------------------------------------- skip conditions


def test_user_renamed_true_skips(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-xx-1", label="Already renamed", user_renamed=True)
    assert autoname("conv-xx-1", "tell me about DSLP") is None
    assert fake_http.last_post_args is None


def test_non_default_label_pattern_skips(autoname_env):
    """If the label doesn't match the 'New conversation YYYY-MM-DD' or
    'Fork YYYY-MM-DD' pattern, assume the user named it and skip.
    """
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-xx-2", label="My custom name")
    assert autoname("conv-xx-2", "hello") is None
    assert fake_http.last_post_args is None


def test_missing_meta_row_skips(autoname_env):
    autoname, fake_http, _, _ = autoname_env
    assert autoname("conv-never-existed", "hello") is None
    assert fake_http.last_post_args is None


# ----------------------------------------------------------- happy path


def test_happy_path_updates_label(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-happy", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": "DSLP Draft Review"}}]
    })
    result = autoname("conv-happy", "Can we discuss the DSLP draft?")
    assert result == "DSLP Draft Review"
    assert fake_db.meta["conv-happy"]["label"] == "DSLP Draft Review"
    # Verify the litellm call went out.
    assert fake_http.last_post_args is not None
    url, kwargs = fake_http.last_post_args
    assert "chat/completions" in url
    assert kwargs["json"]["model"] == "gpt-5.4-mini"
    assert kwargs["timeout"] == 3.0
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_fork_default_label_also_matches(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-fork", label="Fork 2026-04-20 10:30")
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": "Alternate task list"}}]
    })
    assert autoname("conv-fork", "Let's try a different plan") == "Alternate task list"


def test_new_label_stripped_of_quotes_and_trailing_period(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-quotes", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": '"DSLP draft review."'}}]
    })
    assert autoname("conv-quotes", "DSLP draft") == "DSLP draft review"


def test_label_truncated_to_80_chars(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-long", label="New conversation 2026-04-20 09:15")
    long_label = "A" * 200
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": long_label}}]
    })
    result = autoname("conv-long", "anything")
    assert len(result) == 80


# ----------------------------------------------------------- error paths


def test_litellm_timeout_silent_fail(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-timeout", label="New conversation 2026-04-20 09:15")
    fake_http.raise_on_next = True
    assert autoname("conv-timeout", "hello") is None
    # Label unchanged.
    assert fake_db.meta["conv-timeout"]["label"] == "New conversation 2026-04-20 09:15"


def test_litellm_500_silent_fail(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-500", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(500, {"error": "boom"})
    assert autoname("conv-500", "hello") is None
    assert fake_db.meta["conv-500"]["label"] == "New conversation 2026-04-20 09:15"


def test_malformed_response_no_choices_silent_fail(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-bad", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(200, {"choices": []})
    assert autoname("conv-bad", "hello") is None


def test_empty_content_silent_fail(autoname_env):
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-empty", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": ""}}]
    })
    assert autoname("conv-empty", "hello") is None
    assert fake_db.meta["conv-empty"]["label"] == "New conversation 2026-04-20 09:15"


# ----------------------------------------------------------- race safety


def test_user_renames_mid_call_race_safe(autoname_env):
    """Simulate: pre-check passes (user_renamed=FALSE), litellm call
    fires, WHILE the call is in flight the user manually renames. Our
    UPDATE WHERE user_renamed=FALSE touches 0 rows — the user wins.
    """
    autoname, fake_http, fake_db, _ = autoname_env
    fake_db.seed("conv-race", label="New conversation 2026-04-20 09:15")

    # Monkey-patch the POST to flip user_renamed BEFORE returning —
    # simulating the user's manual rename landing between our pre-check
    # and UPDATE.
    def racing_post(url, **kwargs):
        fake_db.meta["conv-race"]["user_renamed"] = True
        fake_db.meta["conv-race"]["label"] = "User's own label"
        return _make_resp(200, {
            "choices": [{"message": {"content": "LLM's label"}}]
        })
    fake_http.post = racing_post

    result = autoname("conv-race", "hello")
    assert result is None
    # User's label preserved.
    assert fake_db.meta["conv-race"]["label"] == "User's own label"
    assert fake_db.meta["conv-race"]["user_renamed"] is True


# ----------------------------------------------------------- model env var


def test_model_env_var_overrides(autoname_env, monkeypatch):
    autoname, fake_http, fake_db, app_module = autoname_env
    monkeypatch.setattr(app_module, "PA_WEB_UI_AUTONAME_MODEL", "gpt-4.1-mini")
    fake_db.seed("conv-model", label="New conversation 2026-04-20 09:15")
    fake_http.next_post_response = _make_resp(200, {
        "choices": [{"message": {"content": "A title"}}]
    })
    autoname("conv-model", "hello")
    _, kwargs = fake_http.last_post_args
    assert kwargs["json"]["model"] == "gpt-4.1-mini"
