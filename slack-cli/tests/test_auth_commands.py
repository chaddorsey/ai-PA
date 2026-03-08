import json
import os
from unittest.mock import patch
from click.testing import CliRunner
from slack_cli.cli import cli


def test_auth_status_no_tokens():
    with patch.dict(os.environ, {}, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent"):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "status"])
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["bot_token"] == "not configured"
            assert parsed["user_token"] == "not configured"


def test_auth_status_with_token():
    with patch.dict(os.environ, {"SLACK_CLI_TOKEN": "xoxb-test"}, clear=False):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "status"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "SLACK_CLI_TOKEN" in parsed["bot_token"]


def test_auth_store_no_input():
    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "store"])
    assert result.exit_code == 2
