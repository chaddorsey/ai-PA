import json
from click.testing import CliRunner
from slack_cli.cli import cli


def test_schema_specific_method():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "chat.postMessage"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "chat.postMessage"
    assert "params" in parsed


def test_schema_list():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert "chat.postMessage" in parsed


def test_schema_group():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--group", "conversations"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert all(m.startswith("conversations.") for m in parsed)


def test_schema_not_found():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "bogus.method"])
    assert result.exit_code == 1


def test_schema_no_args_lists_groups():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "chat" in parsed
    assert "conversations" in parsed
