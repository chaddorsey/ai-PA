"""Tests for semantic validation (UUID, date, name) wired into the CLI execution path."""

import json

from click.testing import CliRunner

from omnifocus_cli.cli import cli


def test_body_uuid_validation_rejects_bad_task_id():
    runner = CliRunner()
    # task get requires a positional TASK_ID even with --body; supply a dummy
    result = runner.invoke(cli, [
        "--body", '{"taskId": "abc?123"}',
        "task", "get", "dummy",
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert any(e["field"] == "taskId" for e in parsed["errors"])


def test_body_date_validation_rejects_bad_date():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "Test", "dueDate": "next Friday"}',
        "task", "create",
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert any(e["field"] == "dueDate" for e in parsed["errors"])


def test_body_name_validation_rejects_control_chars():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", json.dumps({"name": "Bad\x00name"}),
        "task", "create",
    ])
    assert result.exit_code == 2


def test_convenience_flag_uuid_validation():
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "get", "abc?123"])
    assert result.exit_code == 2


def test_convenience_flag_date_validation():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create", "--name", "Test", "--due", "not-a-date",
    ])
    assert result.exit_code == 2
