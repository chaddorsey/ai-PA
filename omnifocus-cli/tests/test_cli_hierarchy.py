from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_subtasks(mock_call):
    mock_call.return_value = [{"id": "st-1", "name": "Subtask A"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "subtasks", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTaskSubtasks", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_add_subtask(mock_call):
    mock_call.return_value = {"id": "st-new", "name": "Do sub-thing"}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "add-subtask", "t-1", "--name", "Do sub-thing"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["name"] == "Do sub-thing"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_hierarchy(mock_call):
    mock_call.return_value = {"id": "t-1", "children": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "hierarchy", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTaskHierarchy", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_flatten(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "flatten", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("flattenTaskHierarchy", {"taskId": "t-1"})
