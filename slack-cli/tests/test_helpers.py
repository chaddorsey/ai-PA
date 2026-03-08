import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from slack_cli.cli import cli


def _mock_client():
    mock = MagicMock()
    mock.call.return_value = {"ok": True}
    return mock


@patch("slack_cli.cli.SlackClient")
def test_chat_send_with_channel_name(mock_cls):
    client = _mock_client()
    # First call: conversations.list to resolve name
    # Second call: chat.postMessage
    client.call.side_effect = [
        {"ok": True, "channels": [{"id": "C0123ABCDEF", "name": "general"}]},
        {"ok": True, "ts": "1234567890.123456", "channel": "C0123ABCDEF"},
    ]
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "+send", "--channel", "general", "--text", "hello"])
    assert result.exit_code == 0
    assert client.call.call_count == 2


@patch("slack_cli.cli.SlackClient")
def test_chat_send_with_channel_id(mock_cls):
    client = _mock_client()
    client.call.return_value = {"ok": True, "ts": "1234567890.123456"}
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "+send", "--channel", "C0123ABCDEF", "--text", "hello"])
    assert result.exit_code == 0
    # Should only call postMessage (no resolve needed)
    client.call.assert_called_once()


@patch("slack_cli.cli.SlackClient")
def test_chat_send_channel_not_found(mock_cls):
    client = _mock_client()
    client.call.return_value = {"ok": True, "channels": []}
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "+send", "--channel", "nonexistent", "--text", "hello"])
    assert result.exit_code == 1


@patch("slack_cli.cli.SlackClient")
def test_conversations_find(mock_cls):
    client = _mock_client()
    client.call.return_value = {
        "ok": True,
        "channels": [
            {"id": "C1", "name": "project-alpha"},
            {"id": "C2", "name": "project-beta"},
            {"id": "C3", "name": "general"},
        ],
    }
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "+find", "--name", "project"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["count"] == 2


@patch("slack_cli.cli.SlackClient")
def test_users_whois_by_email(mock_cls):
    client = _mock_client()
    client.call.return_value = {"ok": True, "user": {"id": "U123", "name": "john"}}
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "+whois", "--email", "john@example.com"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["count"] == 1


@patch("slack_cli.cli.SlackClient")
def test_users_whois_by_name(mock_cls):
    client = _mock_client()
    client.call.return_value = {
        "ok": True,
        "members": [
            {"id": "U1", "name": "john", "real_name": "John Doe", "profile": {"display_name": "JD"}},
            {"id": "U2", "name": "jane", "real_name": "Jane Smith", "profile": {"display_name": "JS"}},
        ],
    }
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "+whois", "--name", "john"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["count"] == 1


def test_users_whois_no_input():
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "+whois"])
    assert result.exit_code == 2
