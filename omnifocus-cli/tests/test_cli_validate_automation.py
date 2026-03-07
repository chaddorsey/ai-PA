from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_validate_transaction(mock_call):
    mock_call.return_value = {"valid": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"operations": []}',
        "--format", "json",
        "validate", "transaction",
    ])
    assert result.exit_code == 0


@patch("omnifocus_cli.cli.call_omnifocus")
def test_validate_move(mock_call):
    mock_call.return_value = {"valid": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"taskId": "t-1", "targetProjectId": "p-1"}',
        "--format", "json",
        "validate", "move",
    ])
    assert result.exit_code == 0


@patch("omnifocus_cli.cli.call_omnifocus")
def test_validate_create(mock_call):
    mock_call.return_value = {"valid": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"name": "Test"}',
        "--format", "json",
        "validate", "create",
    ])
    assert result.exit_code == 0


@patch("omnifocus_cli.cli.call_omnifocus")
def test_automation_suggest(mock_call):
    mock_call.return_value = {"suggestions": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "automation", "suggest"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("suggestAutomation", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_automation_diagnose(mock_call):
    mock_call.return_value = {"issues": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "automation", "diagnose"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("diagnoseIssues", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_automation_cleanup(mock_call):
    mock_call.return_value = {"cleaned": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "automation", "cleanup"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("suggestCleanup", {})
