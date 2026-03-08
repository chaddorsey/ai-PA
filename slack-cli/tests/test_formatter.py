import json
import sys
from unittest.mock import patch
from slack_cli.formatter import format_output, apply_field_mask, should_use_json


def test_should_use_json_default_tty():
    with patch.object(sys.stdout, "isatty", return_value=True):
        assert should_use_json(None) is False


def test_should_use_json_default_pipe():
    with patch.object(sys.stdout, "isatty", return_value=False):
        assert should_use_json(None) is True


def test_should_use_json_explicit():
    assert should_use_json("json") is True
    assert should_use_json("text") is False


def test_format_output_json():
    data = {"id": "C123", "name": "general"}
    result = format_output(data, "json")
    parsed = json.loads(result)
    assert parsed == data


def test_format_output_json_compact_when_not_tty():
    data = {"id": "C123"}
    with patch.object(sys.stdout, "isatty", return_value=False):
        result = format_output(data, "json")
    assert "\n" not in result


def test_apply_field_mask_dict():
    data = {"id": "C123", "name": "general", "topic": "stuff"}
    result = apply_field_mask(data, ["id", "name"])
    assert result == {"id": "C123", "name": "general"}


def test_apply_field_mask_list():
    data = [{"id": "C1", "name": "a", "extra": 1}, {"id": "C2", "name": "b", "extra": 2}]
    result = apply_field_mask(data, ["id", "name"])
    assert result == [{"id": "C1", "name": "a"}, {"id": "C2", "name": "b"}]


def test_apply_field_mask_none():
    data = {"id": "C123", "name": "general"}
    assert apply_field_mask(data, None) == data


def test_format_output_csv_list():
    data = [{"id": "C1", "name": "a"}, {"id": "C2", "name": "b"}]
    result = format_output(data, "csv")
    lines = result.strip().splitlines()
    assert lines[0] == "id,name"
    assert lines[1] == "C1,a"


def test_format_output_yaml():
    data = {"id": "C123", "name": "general"}
    result = format_output(data, "yaml")
    assert "id:" in result
    assert "C123" in result
