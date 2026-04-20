"""Unit 1.6 tests — /api/subprocess/status endpoint + crash-log redaction.

Run: cd pa-web-ui && python -m pytest tests/test_observability.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess_pool as sp  # noqa: E402


# ================================================================== redactor


class TestRedactor:
    def test_openai_key_redacted(self):
        src = "Bash: echo OPENAI_API_KEY=sk-dangerous12345678901234567890"
        out = sp.redact_text(src)
        assert "sk-dangerous" not in out
        assert "[REDACTED:openai-key]" in out

    def test_anthropic_key_redacted(self):
        src = "ANTHROPIC_API_KEY=sk-ant-api03-AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPp"
        out = sp.redact_text(src)
        assert "sk-ant-api03-" not in out
        assert "[REDACTED:anthropic-key]" in out

    def test_slack_bot_token_redacted(self):
        src = "SLACK_BOT_TOKEN=xoxb-1234567890-12345-aaaaBBBBccccDDDDeeee"
        out = sp.redact_text(src)
        assert "xoxb-1234567890" not in out
        assert "[REDACTED:slack-bot]" in out

    def test_slack_app_token_redacted(self):
        src = "SLACK_APP_TOKEN=xapp-1-A01B2C3D4E5-0987654321-abcdefghijklmn"
        out = sp.redact_text(src)
        assert "[REDACTED:slack-app]" in out

    def test_bearer_token_redacted(self):
        src = "Authorization: Bearer abcdef1234567890deadbeef"
        out = sp.redact_text(src)
        assert "abcdef1234567890" not in out
        assert "Bearer [REDACTED]" in out

    def test_aws_access_key_redacted(self):
        src = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        out = sp.redact_text(src)
        assert "AKIAIOSFODNN7EXAMPLE" not in out
        assert "[REDACTED:aws-access]" in out

    def test_email_redacted(self):
        src = "admin@example.com and user.name+foo@domain.co.uk"
        out = sp.redact_text(src)
        assert "admin@example.com" not in out
        assert "user.name+foo@domain.co.uk" not in out
        assert out.count("[REDACTED:email]") == 2

    def test_long_hex_redacted(self):
        src = "commit=abcdef0123456789abcdef0123456789abcdef01"
        out = sp.redact_text(src)
        assert "abcdef0123456789abcdef0123456789abcdef01" not in out
        assert "[REDACTED:hex]" in out

    def test_env_values_replaced(self):
        env_values = {"super-secret-password", "s3cretDB"}
        src = "DB password is super-secret-password and s3cretDB too"
        out = sp.redact_text(src, env_values)
        assert "super-secret-password" not in out
        assert "s3cretDB" not in out
        assert out.count("[REDACTED:env]") == 2

    def test_empty_input_passes_through(self):
        assert sp.redact_text("") == ""
        assert sp.redact_text(None) is None  # type: ignore[arg-type]

    def test_non_secret_text_unchanged(self):
        src = "Hello world, nothing sensitive here."
        assert sp.redact_text(src) == src

    def test_mixed_secrets_all_redacted(self):
        src = (
            "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.AAAA' "
            "https://admin@example.com/api?key=sk-abcd12345678901234567890"
        )
        out = sp.redact_text(src)
        assert "eyJhbGciOiJIUzI1NiIs" not in out
        assert "admin@example.com" not in out
        assert "sk-abcd" not in out


# ================================================================== env deny


class TestLoadEnvDeny:
    def test_reads_values_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "POSTGRES_PASSWORD=super-secret-password\n"
            "OPENAI_API_KEY=sk-dangerous12345678\n"
            "# comment\n"
            "EMPTY=\n"
            'QUOTED="quoted-value-1234"\n'
        )
        deny = sp.load_env_deny_set(str(env_file))
        assert "super-secret-password" in deny
        assert "sk-dangerous12345678" in deny
        assert "quoted-value-1234" in deny
        # Empty value excluded.
        assert "" not in deny

    def test_missing_env_file_returns_empty(self):
        deny = sp.load_env_deny_set("/nonexistent/.env")
        assert deny == set()

    def test_short_values_ignored(self, tmp_path):
        """Values shorter than 8 chars are excluded to avoid false
        positives like redacting the word 'test' everywhere.
        """
        env_file = tmp_path / ".env"
        env_file.write_text("SHORT=ab\nLONG=this-is-long-enough\n")
        deny = sp.load_env_deny_set(str(env_file))
        assert "ab" not in deny
        assert "this-is-long-enough" in deny


# ================================================================== crash log


class TestWriteCrashLog:
    def test_writes_redacted_log(self, tmp_path):
        path = sp.write_crash_log(
            conv_id="conv-test-1",
            stdout_tail="Bash: cat /workspace/secret has sk-dangerous123456789012345678",
            stderr_tail="traceback: Bearer abcdef1234567890",
            returncode=1,
            log_dir=str(tmp_path),
        )
        assert path is not None
        contents = Path(path).read_text()
        assert "conv-test-1" in contents
        assert "returncode: 1" in contents
        # Secrets must be redacted.
        assert "sk-dangerous" not in contents
        assert "abcdef1234567890" not in contents
        assert "[REDACTED:openai-key]" in contents
        assert "Bearer [REDACTED]" in contents

    def test_env_values_also_redacted(self, tmp_path):
        path = sp.write_crash_log(
            conv_id="conv-envtest",
            stdout_tail="password=my-env-derived-secret",
            stderr_tail="",
            returncode=139,
            log_dir=str(tmp_path),
            env_values=["my-env-derived-secret"],
        )
        contents = Path(path).read_text()
        assert "my-env-derived-secret" not in contents
        assert "[REDACTED:env]" in contents

    def test_rotation_caps_at_keep_per_conv(self, tmp_path):
        for i in range(25):
            sp.write_crash_log(
                conv_id="conv-rot",
                stdout_tail=f"run-{i}",
                stderr_tail="",
                returncode=1,
                log_dir=str(tmp_path),
                keep_per_conv=10,
            )
            # Ensure rotation sees distinct timestamps.
            import time as _t
            _t.sleep(0.002)
        files = sorted(p.name for p in tmp_path.iterdir())
        # Rotation is sort-by-name; our names contain the timestamp.
        assert len(files) <= 10, f"expected at most 10 files, got {len(files)}"

    def test_writes_to_nonexistent_dir_succeeds(self, tmp_path):
        """Crash logger must not fail the first time — it creates the dir."""
        sub = tmp_path / "nested" / "logs"
        path = sp.write_crash_log(
            conv_id="conv-newdir",
            stdout_tail="ok",
            stderr_tail="",
            returncode=0,
            log_dir=str(sub),
        )
        assert path is not None
        assert Path(path).exists()

    def test_io_errors_swallowed_no_raise(self):
        # Point at a definitely-unwritable path.
        path = sp.write_crash_log(
            conv_id="conv-bad",
            stdout_tail="x",
            stderr_tail="y",
            returncode=1,
            log_dir="/proc/1/no-such-path/blocked",
        )
        assert path is None


# ================================================================== status route


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PA_WEB_UI_PHASE_1_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost:65535/x")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test-secret")
    yield


class FakeRegistry:
    def __init__(self, handles_payload: List[Dict[str, Any]]):
        self._payload = handles_payload

    def list_handles(self) -> List[Dict[str, Any]]:
        return self._payload


@pytest.fixture
def app(monkeypatch):
    sys.modules.pop("app", None)
    sys.modules.pop("ingress_guard", None)
    sys.modules.pop("subprocess_pool", None)
    import app as app_module  # noqa: E402

    monkeypatch.setattr(app_module, "save_conversation_message", lambda **_kw: None)
    monkeypatch.setattr(app_module, "save_routing_signal", lambda **_kw: None)
    monkeypatch.setattr(app_module, "save_thread_exchange", lambda **_kw: None)

    fake = FakeRegistry([
        {"conv_id": "default", "pid": 12345, "alive": True, "subscriber_count": 1},
        {"conv_id": "conv-abc", "pid": 12346, "alive": True, "subscriber_count": 0},
    ])
    monkeypatch.setattr(app_module, "subprocess_registry", fake)
    monkeypatch.setattr(app_module, "PA_WEB_UI_PHASE_1_ENABLED", True)

    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


def test_status_endpoint_requires_allowlisted_origin(client):
    resp = client.get(
        "/api/subprocess/status",
        headers={"Host": "localhost:5200", "Origin": "http://attacker.example.com"},
    )
    assert resp.status_code == 403


def test_status_endpoint_returns_handle_list(client):
    resp = client.get(
        "/api/subprocess/status",
        headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["phase_1_enabled"] is True
    assert body["mission_control_agent_id"].startswith("agent-")
    assert len(body["handles"]) == 2
    conv_ids = {h["conv_id"] for h in body["handles"]}
    assert {"default", "conv-abc"} == conv_ids


def test_status_endpoint_host_allowlist_enforced(client):
    resp = client.get(
        "/api/subprocess/status",
        headers={"Host": "evil.example.com"},
    )
    assert resp.status_code == 421
