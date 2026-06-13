import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from twitter_cli.cli import cli


def test_schema_lists_all_commands():
    """Schema command returns all read and write commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "read" in data
    assert "write" in data
    read_cmds = [c["command"] for c in data["read"]]
    assert "read feed" in read_cmds
    assert "read user" in read_cmds


def test_schema_specific_command():
    """Schema for a specific command returns its details."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "read feed"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "read feed"
    assert "count" in data["params"]


def test_schema_unknown_command():
    """Schema for unknown command returns error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "read nonexistent"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["status"] == "error"


def test_schema_includes_list_commands():
    """Schema advertises the list discovery + timeline commands to agents."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    data = json.loads(result.output)
    read_cmds = [c["command"] for c in data["read"]]
    assert "read lists" in read_cmds
    assert "read list-tweets" in read_cmds


def test_read_lists():
    """`read lists` returns the user's lists from get_my_lists."""
    runner = CliRunner()
    fake = MagicMock()
    fake.get_my_lists.return_value = [
        {"id": "1", "name": "Key Peeps", "member_count": 50, "owner": "chaddorsey"}
    ]
    with patch("twitter_cli.cli._get_client", return_value=fake):
        result = runner.invoke(cli, ["read", "lists"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "Key Peeps"
    fake.get_my_lists.assert_called_once()


def test_read_list_tweets_default_unwraps_to_list():
    """Default `read list-tweets` returns a bare tweet list (no paging envelope)."""
    runner = CliRunner()
    fake = MagicMock()
    fake.get_list_tweets.return_value = {
        "tweets": [{"id": "9", "text": "hi"}], "next_cursor": "CURSOR",
    }
    with patch("twitter_cli.cli._get_client", return_value=fake):
        result = runner.invoke(cli, ["read", "list-tweets", "123"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["text"] == "hi"
    fake.get_list_tweets.assert_called_once_with("123", count=20, cursor=None)


def test_read_list_tweets_honors_count_when_unwrapped():
    """Default `read list-tweets --count N` truncates to N (timeline ignores small page hints)."""
    runner = CliRunner()
    fake = MagicMock()
    fake.get_list_tweets.return_value = {
        "tweets": [{"id": str(i)} for i in range(100)], "next_cursor": "C",
    }
    with patch("twitter_cli.cli._get_client", return_value=fake):
        result = runner.invoke(cli, ["read", "list-tweets", "123", "--count", "3"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 3


def test_read_list_tweets_paged_keeps_envelope():
    """`--paged` keeps the {tweets, next_cursor} envelope for pagination."""
    runner = CliRunner()
    fake = MagicMock()
    fake.get_list_tweets.return_value = {
        "tweets": [{"id": "9", "text": "hi"}], "next_cursor": "CURSOR",
    }
    with patch("twitter_cli.cli._get_client", return_value=fake):
        result = runner.invoke(cli, ["read", "list-tweets", "123", "--paged"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["next_cursor"] == "CURSOR"
    assert data["tweets"][0]["text"] == "hi"
