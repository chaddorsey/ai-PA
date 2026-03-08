import os
import json
import tempfile
from unittest.mock import patch
from slack_cli.auth import resolve_token, TOKEN_TYPE_BOT, TOKEN_TYPE_USER


def test_resolve_bot_token_from_env():
    with patch.dict(os.environ, {"SLACK_CLI_TOKEN": "xoxb-test-token"}, clear=False):
        token = resolve_token(TOKEN_TYPE_BOT)
        assert token == "xoxb-test-token"


def test_resolve_user_token_from_env():
    with patch.dict(os.environ, {"SLACK_CLI_USER_TOKEN": "xoxp-test-token"}, clear=False):
        token = resolve_token(TOKEN_TYPE_USER)
        assert token == "xoxp-test-token"


def test_resolve_fallback_bot_token():
    env = {"SLACK_BOT_TOKEN": "xoxb-fallback"}
    with patch.dict(os.environ, env, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token(TOKEN_TYPE_BOT)
            assert token == "xoxb-fallback"


def test_resolve_fallback_user_token():
    env = {"SLACK_MCP_XOXP_TOKEN": "xoxp-fallback"}
    with patch.dict(os.environ, env, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token(TOKEN_TYPE_USER)
            assert token == "xoxp-fallback"


def test_resolve_from_config_file():
    config = {"bot_token": "xoxb-from-file", "user_token": "xoxp-from-file"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        with patch.dict(os.environ, {}, clear=True):
            with patch("slack_cli.auth.CONFIG_PATH", f.name):
                token = resolve_token(TOKEN_TYPE_BOT)
                assert token == "xoxb-from-file"
    os.unlink(f.name)


def test_resolve_either_prefers_bot():
    with patch.dict(os.environ, {
        "SLACK_CLI_TOKEN": "xoxb-bot",
        "SLACK_CLI_USER_TOKEN": "xoxp-user",
    }, clear=False):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token("either")
            assert token == "xoxb-bot"


def test_resolve_returns_none_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token(TOKEN_TYPE_BOT)
            assert token is None


def test_priority_cli_env_over_fallback():
    with patch.dict(os.environ, {
        "SLACK_CLI_TOKEN": "xoxb-cli",
        "SLACK_BOT_TOKEN": "xoxb-fallback",
    }, clear=False):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token(TOKEN_TYPE_BOT)
            assert token == "xoxb-cli"
