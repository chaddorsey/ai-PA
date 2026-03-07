from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_analytics_health(mock_call):
    mock_call.return_value = {"score": 85}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "analytics", "health"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getProjectHealth", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_analytics_workload(mock_call):
    mock_call.return_value = {"total": 42}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "analytics", "workload"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getWorkloadSummary", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_analytics_trends(mock_call):
    mock_call.return_value = {"completed": 10}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "analytics", "trends"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTrendInsights", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_analytics_summary(mock_call):
    mock_call.return_value = {"overview": "all good"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "analytics", "summary"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getAnalyticsSummary", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_system_health(mock_call):
    mock_call.return_value = {"status": "healthy", "version": "1.0"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "health"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("health", {})
