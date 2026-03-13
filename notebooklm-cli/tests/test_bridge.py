"""Bridge tests — unit tests mock the NotebookLMClient, integration tests need auth."""
from __future__ import annotations

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock

from notebooklm_cli.bridge import call, serialize


def test_serialize_dataclass():
    """Dataclasses with __dict__ should serialize to plain dicts."""

    @dataclass
    class Fake:
        id: str
        title: str

    result = serialize(Fake(id="abc", title="Test"))
    assert result == {"id": "abc", "title": "Test"}


def test_serialize_list_of_dataclasses():
    @dataclass
    class Fake:
        id: str

    result = serialize([Fake(id="a"), Fake(id="b")])
    assert result == [{"id": "a"}, {"id": "b"}]


def test_serialize_none():
    assert serialize(None) is None


def test_serialize_dict_passthrough():
    d = {"key": "value"}
    assert serialize(d) == d


def test_serialize_nested_dataclass():
    @dataclass
    class Inner:
        x: int

    @dataclass
    class Outer:
        name: str
        inner: Inner

    result = serialize(Outer(name="test", inner=Inner(x=42)))
    assert result == {"name": "test", "inner": {"x": 42}}


def test_serialize_enum():
    from enum import Enum

    class Color(Enum):
        RED = "red"

    assert serialize(Color.RED) == "red"


def test_call_unknown_group():
    """Unknown group should return error without hitting notebooklm-py."""
    result = call("bogus.action", {})
    assert result["status"] == "error"
    assert "Unknown group" in result["error_message"]


def test_call_invalid_method_format():
    result = call("noperiod", {})
    assert result["status"] == "error"
    assert "Invalid method format" in result["error_message"]


def test_call_unknown_action():
    """Known group but unknown action should error."""
    mock_client = AsyncMock()
    mock_api = AsyncMock()
    mock_api.nonexistent_action = None
    del mock_api.nonexistent_action  # ensure getattr returns None
    mock_client.notebooks = mock_api
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("notebooklm_cli.bridge._create_client", new_callable=lambda: lambda: AsyncMock(return_value=mock_client)):
        result = call("notebook.nonexistent_action", {})
    assert result["status"] == "error"


def test_call_auth_refresh_on_expired():
    """If first call raises expired auth, bridge should retry once after refresh."""
    mock_client = AsyncMock()
    mock_client.notebooks.list = AsyncMock(
        side_effect=[ValueError("Authentication expired"), []]
    )
    mock_client.refresh_auth = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("notebooklm_cli.bridge._create_client", return_value=mock_client):
        result = call("notebook.list", {})
        assert result["status"] == "ok"
        mock_client.refresh_auth.assert_called_once()


def test_call_path_traversal_rejected():
    """File path params with traversal should be rejected before calling client."""
    result = call("source.add-file", {"notebookId": "nb1", "filePath": "../../etc/passwd"})
    assert result["status"] == "error"
    assert ".." in result["error_message"]
