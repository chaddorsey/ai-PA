import json
from unittest.mock import patch
from omnifocus_cli.formatters import output_result, output_error, should_use_json


def test_output_result_json(capsys):
    data = {"id": "abc", "name": "Test Task"}
    output_result(data, json_output=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == data


def test_output_result_human_dict(capsys):
    data = {"id": "abc-123", "name": "Buy milk", "flagged": True}
    output_result(data, json_output=False)
    captured = capsys.readouterr()
    assert "abc-123" in captured.out
    assert "Buy milk" in captured.out


def test_output_result_human_list(capsys):
    data = [{"id": "1", "name": "Task A"}, {"id": "2", "name": "Task B"}]
    output_result(data, json_output=False)
    captured = capsys.readouterr()
    assert "Task A" in captured.out
    assert "Task B" in captured.out


def test_output_error_json(capsys):
    output_error("Something broke", json_output=True)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err)
    assert parsed["error"] == "Something broke"


def test_output_error_human(capsys):
    output_error("Something broke", json_output=False)
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Something broke" in captured.err


def test_should_use_json_explicit_true():
    assert should_use_json(format_flag="json") is True


def test_should_use_json_explicit_false():
    assert should_use_json(format_flag="text") is False


@patch("sys.stdout.isatty", return_value=False)
def test_should_use_json_auto_non_tty(mock_tty):
    assert should_use_json(format_flag=None) is True


@patch("sys.stdout.isatty", return_value=True)
def test_should_use_json_auto_tty(mock_tty):
    assert should_use_json(format_flag=None) is False
