from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_create_minimal(mock_call):
    mock_call.return_value = {"id": "new-1", "name": "Buy milk"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "create", "--name", "Buy milk"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTask", {"name": "Buy milk"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_create_full(mock_call):
    mock_call.return_value = {"id": "new-2", "name": "Write report"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--name", "Write report",
        "--project", "proj-1",
        "--note", "Include charts",
        "--flag",
        "--due", "2026-03-10",
        "--defer", "2026-03-08",
        "--duration", "60",
        "--tag", "tag-1",
        "--tag", "tag-2",
    ])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "createTask"
    params = call_args[1]
    assert params["name"] == "Write report"
    assert params["projectId"] == "proj-1"
    assert params["note"] == "Include charts"
    assert params["flagged"] is True
    assert params["dueDate"] == "2026-03-10"
    assert params["deferDate"] == "2026-03-08"
    assert params["estimatedMinutes"] == 60
    assert params["tagIds"] == ["tag-1", "tag-2"]


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_get(mock_call):
    mock_call.return_value = {"id": "t-1", "name": "Test"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "get", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTask", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_complete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "complete", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("completeTask", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_update_flag_and_defer(mock_call):
    mock_call.return_value = {"id": "t-1", "name": "Updated", "flagged": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "update", "t-1",
        "--flag",
        "--defer", "2026-03-15",
        "--duration", "45",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["flagged"] is True
    assert params["deferDate"] == "2026-03-15"
    assert params["estimatedMinutes"] == 45


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_update_unflag(mock_call):
    mock_call.return_value = {"id": "t-1", "flagged": False}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "update", "t-1", "--no-flag"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is False


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_list_by_project(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "Task A"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "list", "--project", "proj-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_list_flagged(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--flagged"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is True
