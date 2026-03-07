from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_group_type(mock_call):
    mock_call.return_value = {"groupType": "parallel"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "group-type", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTaskGroupType", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_set_group_type(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "set-group-type", "t-1", "--type", "sequential"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["groupType"] == "sequential"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_group_type(mock_call):
    mock_call.return_value = {"groupType": "sequential"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "project", "group-type", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getProjectGroupType", {"projectId": "p-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_set_group_type(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "set-group-type", "p-1", "--type", "parallel"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["projectId"] == "p-1"
    assert params["groupType"] == "parallel"
