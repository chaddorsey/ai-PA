import json
from unittest.mock import patch, MagicMock
import importlib


def _load_tool(module_name: str, func_name: str):
    mod = importlib.import_module(f"letta_tools.{module_name}")
    return getattr(mod, func_name)


@patch("subprocess.run")
def test_omnifocus_task_create(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='{"id":"t-1","name":"Buy milk"}', stderr="")
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="create", params='{"name": "Buy milk"}')
    assert result["status"] == "ok"
    args = mock_run.call_args[0][0]
    assert args[:3] == ["omnifocus-cli", "task", "create"]
    assert "--body" in args


@patch("subprocess.run")
def test_omnifocus_task_with_fields(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[{"id":"t-1","name":"A"}]', stderr="")
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="list", fields="id,name")
    args = mock_run.call_args[0][0]
    assert "--fields" in args
    assert "id,name" in args


@patch("subprocess.run")
def test_omnifocus_search(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_search", "omnifocus_search")
    result = fn(params='{"query": "milk"}', fields="id,name")
    assert result["status"] == "ok"
    args = mock_run.call_args[0][0]
    assert args[:2] == ["omnifocus-cli", "search"]


@patch("subprocess.run")
def test_omnifocus_project(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_project", "omnifocus_project")
    result = fn(action="list", fields="id,name")
    assert result["status"] == "ok"


@patch("subprocess.run")
def test_omnifocus_inbox(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_inbox", "omnifocus_inbox")
    result = fn(action="list")
    assert result["status"] == "ok"


@patch("subprocess.run")
def test_omnifocus_tags(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_tags", "omnifocus_tags")
    result = fn(action="list")
    assert result["status"] == "ok"


@patch("subprocess.run")
def test_tool_returns_error_on_nonzero_exit(mock_run):
    mock_run.return_value = MagicMock(returncode=2, stdout='{"error":"validation_failed"}', stderr="")
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="create", params='{"flagged": "yes"}')
    assert result["status"] == "error"


def test_tool_has_correct_docstring():
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    assert "Args:" in fn.__doc__
    assert "action" in fn.__doc__
