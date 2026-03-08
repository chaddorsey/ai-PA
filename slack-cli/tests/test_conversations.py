import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from slack_cli.cli import cli


def _mock_client():
    mock = MagicMock()
    mock.call.return_value = {"ok": True, "channels": [{"id": "C123", "name": "general"}]}
    mock.paginate.return_value = [{"ok": True, "channels": [{"id": "C123"}]}]
    return mock


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_with_body(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"limit": 5}', "conversations", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["ok"] is True


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_with_flags(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "list", "--limit", "5"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_info_with_body(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "channel": {"id": "C0123ABCDEF", "name": "general"}}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "info"])
    assert result.exit_code == 0


def test_conversations_list_dry_run():
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{"limit": 5}', "conversations", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "conversations.list"
    assert parsed["validation"] == "passed"


def test_conversations_list_dry_run_validation_error():
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{"bogus_field": 1}', "conversations", "list"])
    assert result.exit_code == 2


@patch("slack_cli.cli.SlackClient")
def test_conversations_history(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "messages": [{"text": "hello", "ts": "1234567890.123456"}]}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "history"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_create(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "channel": {"id": "C999"}}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "create", "--name", "test-channel"])
    assert result.exit_code == 0


def test_conversations_invalid_json_body():
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", "not-json", "conversations", "list"])
    assert result.exit_code == 2


@patch("slack_cli.cli.SlackClient")
def test_fields_masking(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "channels": [{"id": "C123", "name": "general", "topic": "stuff"}]}
    runner = CliRunner()
    result = runner.invoke(cli, ["--fields", "ok,channels", "conversations", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "ok" in parsed
    assert "channels" in parsed


@patch("slack_cli.cli.SlackClient")
def test_conversations_archive(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "archive"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_unarchive(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "unarchive"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_invite(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "invite", "--channel", "C0123ABCDEF", "--users", "U0123ABCDEF"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_kick(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF", "user": "U0123ABCDEF"}', "conversations", "kick"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_join(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "join"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_leave(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "leave"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_open(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "channel": {"id": "D0123ABCDEF"}}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "open", "--users", "U0123ABCDEF"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_close(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "close"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_members(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True, "members": ["U0123ABCDEF"]}
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel": "C0123ABCDEF"}', "conversations", "members"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_rename(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "rename", "--channel", "C0123ABCDEF", "--name", "new-name"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_set_purpose(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "setPurpose", "--channel", "C0123ABCDEF", "--purpose", "New purpose"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_set_topic(mock_cls):
    mock_cls.return_value = _mock_client()
    mock_cls.return_value.call.return_value = {"ok": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "setTopic", "--channel", "C0123ABCDEF", "--topic", "New topic"])
    assert result.exit_code == 0


def test_body_overrides_flags_with_warning():
    """When both --body and flags are provided, --body wins and a warning is emitted."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{"limit": 5}', "conversations", "list", "--limit", "10"])
    assert result.exit_code == 0
    # Warning line is written to stderr (mixed into output by CliRunner)
    lines = result.output.strip().split("\n")
    assert any("Warning" in line for line in lines)
    # Find the JSON portion (skip the warning line)
    json_lines = [l for l in lines if not l.startswith("Warning")]
    parsed = json.loads("\n".join(json_lines))
    assert parsed["params"]["limit"] == 5


@patch("slack_cli.cli.SlackClient")
def test_page_all(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["--page-all", "--body", '{"limit": 5}', "conversations", "list"])
    assert result.exit_code == 0
    mock_cls.return_value.paginate.assert_called_once()


def test_conversations_list_required_field_missing_dry_run():
    """conversations.info requires 'channel' - missing it should fail validation."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{}', "conversations", "info"])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert parsed["ok"] is False
    assert parsed["error"] == "validation_failed"
