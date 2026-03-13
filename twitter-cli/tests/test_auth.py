import json
import tempfile
from pathlib import Path
from twitter_cli.auth import load_cookies


def test_load_cookies_from_smaug_config():
    """Load auth_token and ct0 from Smaug config JSON."""
    config = {"twitter": {"authToken": "test_auth_token", "ct0": "test_ct0"}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        cookies = load_cookies(f.name)
    assert cookies["auth_token"] == "test_auth_token"
    assert cookies["ct0"] == "test_ct0"


def test_load_cookies_missing_file():
    """Return empty cookies when config file doesn't exist."""
    cookies = load_cookies("/nonexistent/path.json")
    assert cookies["auth_token"] == ""
    assert cookies["ct0"] == ""


def test_load_cookies_env_override(monkeypatch):
    """Environment variables take precedence over config file."""
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "env_auth")
    monkeypatch.setenv("TWITTER_CT0", "env_ct0")
    cookies = load_cookies("/nonexistent/path.json")
    assert cookies["auth_token"] == "env_auth"
    assert cookies["ct0"] == "env_ct0"
