from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_perspective_list(mock_call):
    mock_call.return_value = [{"id": "pe-1", "name": "Forecast"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "perspective", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once()


@patch("omnifocus_cli.cli.call_omnifocus")
def test_perspective_get(mock_call):
    mock_call.return_value = {"id": "pe-1", "name": "Forecast"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "perspective", "get", "pe-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getPerspective", {"perspectiveId": "pe-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_perspective_switch_by_id(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["perspective", "switch", "--id", "pe-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["perspectiveId"] == "pe-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_perspective_switch_by_name(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["perspective", "switch", "--name", "Forecast"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["perspectiveName"] == "Forecast"
