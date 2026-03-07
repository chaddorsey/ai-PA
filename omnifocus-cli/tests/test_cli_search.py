from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_text(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "Dentist appt"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "search", "--text", "dentist"])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "searchTasks"
    assert call_args[1]["query"] == "dentist"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_due_before(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--due-before", "2026-03-10"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["dueBefore"] == "2026-03-10"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_flagged_in_project(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--flagged", "--project", "proj-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is True
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_by_tag(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--tag", "tag-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["tagId"] == "tag-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_available_only(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--available"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["isAvailable"] is True


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_defer_range(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, [
        "search", "--defer-after", "2026-03-01", "--defer-before", "2026-03-31"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["deferAfter"] == "2026-03-01"
    assert params["deferBefore"] == "2026-03-31"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_requires_at_least_one_filter(mock_call):
    runner = CliRunner()
    result = runner.invoke(cli, ["search"])
    assert result.exit_code != 0
