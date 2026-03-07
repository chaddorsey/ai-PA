from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_list(mock_call):
    mock_call.return_value = [{"id": "f-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listFolders", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_get(mock_call):
    mock_call.return_value = {"id": "f-1", "name": "Work", "projectCount": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "get", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderById", {"folderId": "f-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_create(mock_call):
    mock_call.return_value = {"id": "f-new", "name": "New Folder"}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "create", "--name", "New Folder"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createFolder", {"name": "New Folder"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_create_nested(mock_call):
    mock_call.return_value = {"id": "f-new"}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "create", "--name", "Sub", "--parent", "f-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["parentFolderId"] == "f-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_delete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "delete", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("deleteFolder", {"folderId": "f-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_tree(mock_call):
    mock_call.return_value = {"folders": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "tree"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderHierarchy", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_tree_from_root(mock_call):
    mock_call.return_value = {"folders": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "tree", "--root", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderHierarchy", {"folderId": "f-1"})
