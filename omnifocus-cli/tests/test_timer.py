from unittest.mock import patch

from click.testing import CliRunner

from omnifocus_cli.cli import cli


@patch("omnifocus_cli.timer._timer_call")
def test_timer_status_idle(mock_call):
    mock_call.return_value = {"state": "idle"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "status"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTimerStatus")


@patch("omnifocus_cli.timer._timer_call")
def test_timer_start(mock_call):
    mock_call.return_value = {"state": "running", "taskId": "abc-123"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "start", "abc-123"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("startTimer", {"taskId": "abc-123"})


@patch("omnifocus_cli.timer._timer_call")
def test_timer_stop(mock_call):
    mock_call.return_value = {"state": "idle", "elapsed": 300}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "stop"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("stopTimer")


@patch("omnifocus_cli.timer._timer_call")
def test_timer_pause(mock_call):
    mock_call.return_value = {"state": "paused"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "pause"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("pauseTimer")


@patch("omnifocus_cli.timer._timer_call")
def test_timer_resume(mock_call):
    mock_call.return_value = {"state": "running"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "resume"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("resumeTimer")


@patch("omnifocus_cli.timer._timer_call")
def test_timer_history(mock_call):
    mock_call.return_value = [{"taskId": "abc-123", "duration": 600}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "history", "abc-123"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTimerHistory", {"taskId": "abc-123"})
