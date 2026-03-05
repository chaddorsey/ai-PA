from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_list(mock_call):
    mock_call.return_value = [{"id": "i-1", "name": "Random thought"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inbox", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listInbox", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_list_with_limit(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "list", "--limit", "5"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["limit"] == 5


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_process_to_project(mock_call):
    mock_call.return_value = {"success": True, "operations": ["assign_project"]}
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "process", "i-1", "--project", "proj-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "i-1"
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_process_with_tags(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "inbox", "process", "i-1",
        "--project", "proj-1",
        "--tag", "tag-1",
        "--tag", "tag-2",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["tagIds"] == ["tag-1", "tag-2"]
