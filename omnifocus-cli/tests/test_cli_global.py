import json
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_body_flag_creates_task(mock_call):
    mock_call.return_value = {"id": "new-1", "name": "Buy milk"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "Buy milk", "flagged": true}',
        "task", "create",
    ])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTask", {"name": "Buy milk", "flagged": True})


def test_body_flag_validation_rejects_bad_type():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "X", "flagged": "yes"}',
        "task", "create",
    ])
    assert result.exit_code == 2
    err = json.loads(result.output)
    assert err["error"] == "validation_failed"
    assert any(e["field"] == "flagged" for e in err["errors"])


def test_body_flag_validation_rejects_unknown_field():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "X", "bogus": 1}',
        "task", "create",
    ])
    assert result.exit_code == 2


def test_body_flag_validation_rejects_missing_required():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"flagged": true}',
        "task", "create",
    ])
    assert result.exit_code == 2


def test_dry_run_no_execution():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "Test"}',
        "--dry-run",
        "task", "create",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True
    assert parsed["method"] == "createTask"
    assert parsed["validation"] == "passed"


def test_dry_run_with_validation_error():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"flagged": "yes"}',
        "--dry-run",
        "task", "create",
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True
    assert "validation_errors" in parsed


@patch("omnifocus_cli.cli.call_omnifocus")
def test_fields_flag_filters_output(mock_call):
    mock_call.return_value = [
        {"id": "t-1", "name": "A", "note": "long", "flagged": True},
        {"id": "t-2", "name": "B", "note": "long", "flagged": False},
    ]
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--format", "json",
        "--fields", "id,name",
        "task", "list",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == [{"id": "t-1", "name": "A"}, {"id": "t-2", "name": "B"}]


@patch("omnifocus_cli.cli.call_omnifocus")
def test_format_json_flag(mock_call):
    mock_call.return_value = {"id": "t-1"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "get", "t-1"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"id": "t-1"}


@patch("omnifocus_cli.cli.call_omnifocus")
def test_body_wins_over_convenience_flags(mock_call):
    mock_call.return_value = {"id": "new-1", "name": "From body"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "From body"}',
        "task", "create",
        "--name", "From flag",
    ])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTask", {"name": "From body"})


def test_schema_command_shows_method():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "task.create"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "createTask"
    assert "name" in parsed["params"]


def test_schema_list():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    assert "task.create" in result.output
    assert "search" in result.output


def test_invalid_json_body():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{not valid json}',
        "task", "create",
    ])
    assert result.exit_code == 2
