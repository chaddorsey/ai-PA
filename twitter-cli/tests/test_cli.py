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
