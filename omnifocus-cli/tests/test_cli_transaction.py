from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_transaction_begin(mock_call):
    mock_call.return_value = {"transactionId": "tx-1"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "transaction", "begin"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("beginTransaction", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_transaction_execute(mock_call):
    mock_call.return_value = {"results": []}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"operations": [{"method": "createTask", "params": {"name": "Test"}}]}',
        "transaction", "execute",
    ])
    assert result.exit_code == 0


def test_transaction_execute_requires_body():
    runner = CliRunner()
    result = runner.invoke(cli, ["transaction", "execute"])
    assert result.exit_code == 2


@patch("omnifocus_cli.cli.call_omnifocus")
def test_transaction_accept(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["transaction", "accept", "tx-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("acceptTransaction", {"transactionId": "tx-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_transaction_rollback(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["transaction", "rollback", "tx-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("rollbackTransaction", {"transactionId": "tx-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_transaction_history(mock_call):
    mock_call.return_value = [{"id": "tx-1"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "transaction", "history"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTransactionHistory", {})
