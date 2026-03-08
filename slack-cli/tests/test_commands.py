import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from slack_cli.cli import cli


def _mock_client():
    mock = MagicMock()
    mock.call.return_value = {"ok": True}
    mock.paginate.return_value = [{"ok": True}]
    return mock


@patch("slack_cli.cli.SlackClient")
def test_chat_post_message(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "postMessage", "--channel", "C0123ABCDEF", "--text", "hello"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_chat_post_message_body(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"channel":"C0123ABCDEF","text":"hi"}', "chat", "postMessage"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_users_info(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "info", "--user", "U0123ABCDEF"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_users_lookup_by_email(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "lookupByEmail", "--email", "test@example.com"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_reactions_add(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["reactions", "add", "--channel", "C0123ABCDEF", "--timestamp", "1234567890.123456", "--name", "thumbsup"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_search_messages(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "messages", "--query", "test query"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_files_list(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["files", "list"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_pins_list(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["pins", "list", "--channel", "C0123ABCDEF"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_bookmarks_list(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["bookmarks", "list", "--channel-id", "C0123ABCDEF"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_reminders_add(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["reminders", "add", "--text", "Buy milk", "--time", "in 30 minutes"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_team_info(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["team", "info"])
    assert result.exit_code == 0
