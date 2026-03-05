from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list(mock_call):
    mock_call.return_value = [{"id": "p-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listProjects", {"completion": "active"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_all(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--all"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["completion"] == "all"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_by_folder(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--folder", "f-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["folderId"] == "f-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_get(mock_call):
    mock_call.return_value = {"id": "p-1", "name": "Work", "taskCount": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "get", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getProjectById", {"projectId": "p-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_create_minimal(mock_call):
    mock_call.return_value = {"projectId": "p-new", "projectName": "New Project"}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "create", "--name", "New Project"])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "createProject"
    assert call_args[1]["name"] == "New Project"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_create_full(mock_call):
    mock_call.return_value = {"projectId": "p-new"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "project", "create",
        "--name", "Q2 Goals",
        "--folder", "f-1",
        "--sequential",
        "--due", "2026-06-30",
        "--defer", "2026-04-01",
        "--flag",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["name"] == "Q2 Goals"
    assert params["folderId"] == "f-1"
    assert params["properties"]["sequential"] is True
    assert params["properties"]["dueDate"] == "2026-06-30"
    assert params["properties"]["deferDate"] == "2026-04-01"
    assert params["properties"]["flagged"] is True


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_update_status(mock_call):
    mock_call.return_value = {"updated": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "update", "p-1", "--status", "onHold"])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "setProjectProperties"
    assert call_args[1]["projectId"] == "p-1"
    assert call_args[1]["properties"]["status"] == "onHold"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_folders(mock_call):
    mock_call.return_value = [{"id": "f-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "folders"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listFolders", {})
