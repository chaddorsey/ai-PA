from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_review_list(mock_call):
    mock_call.return_value = [{"id": "p-1", "name": "Project A"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "review", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listProjectsNeedingReview", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_review_mark(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["review", "mark", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("markProjectReviewed", {"projectId": "p-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_review_next(mock_call):
    mock_call.return_value = {"nextReview": "2026-03-14"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "review", "next", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getProjectNextReview", {"projectId": "p-1"})
