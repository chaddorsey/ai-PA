from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_list(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "urgent"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "tags", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listTags", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_create(mock_call):
    mock_call.return_value = {"tagId": "t-new", "tagName": "ai-generated", "created": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "create", "--name", "ai-generated"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTag", {"name": "ai-generated"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_create_nested(mock_call):
    mock_call.return_value = {"tagId": "t-new", "created": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "tags", "create", "--name", "sub-tag", "--parent", "t-parent"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["parentTagId"] == "t-parent"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_rename(mock_call):
    mock_call.return_value = {"tagId": "t-1", "updated": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "rename", "t-1", "--name", "new-name"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("updateTag", {"tagId": "t-1", "name": "new-name"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_delete(mock_call):
    mock_call.return_value = {"tagId": "t-1", "deleted": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "delete", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("deleteTag", {"tagId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_delete_force(mock_call):
    mock_call.return_value = {"tagId": "t-1", "deleted": True, "tasksAffected": 3}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "delete", "t-1", "--force"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["force"] is True
