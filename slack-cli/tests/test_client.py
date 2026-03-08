from unittest.mock import patch, MagicMock
from slack_cli.client import SlackClient
from slack_cli.error import SlackCliError


def _make_mock_response(data):
    """Create a mock Slack API response."""
    mock = MagicMock()
    mock.data = data
    mock.get = data.get
    mock.__getitem__ = lambda self, key: self.data[key]
    return mock


def test_client_calls_api():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = None
    client._force_user = False
    client._force_bot = False
    client._bot_client.api_call.return_value = _make_mock_response({"ok": True, "ts": "123.456"})
    result = client.call("chat.postMessage", {"channel": "C123", "text": "hi"})
    client._bot_client.api_call.assert_called_once_with("chat.postMessage", params={"channel": "C123", "text": "hi"})
    assert result["ok"] is True


def test_client_auto_selects_user_token():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = MagicMock()
    client._force_user = False
    client._force_bot = False
    client._user_client.api_call.return_value = _make_mock_response({"ok": True, "messages": []})
    result = client.call("search.messages", {"query": "test"}, token_type="user")
    client._user_client.api_call.assert_called_once()


def test_client_raises_on_no_token():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = None
    client._user_client = None
    client._force_user = False
    client._force_bot = False
    try:
        client.call("chat.postMessage", {"channel": "C123"}, token_type="bot")
        assert False, "Should have raised"
    except SlackCliError as e:
        assert e.error == "no_token"


def test_client_force_user():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = MagicMock()
    client._force_user = True
    client._force_bot = False
    client._user_client.api_call.return_value = _make_mock_response({"ok": True})
    client.call("chat.postMessage", {"channel": "C123"}, token_type="bot")
    client._user_client.api_call.assert_called_once()
    client._bot_client.api_call.assert_not_called()


def test_client_paginate():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = None
    client._force_user = False
    client._force_bot = False
    # First page has cursor, second doesn't
    client._bot_client.api_call.side_effect = [
        _make_mock_response({"ok": True, "channels": [{"id": "C1"}], "response_metadata": {"next_cursor": "abc123"}}),
        _make_mock_response({"ok": True, "channels": [{"id": "C2"}], "response_metadata": {"next_cursor": ""}}),
    ]
    pages = client.paginate("conversations.list", {"limit": 1}, max_pages=5)
    assert len(pages) == 2
    assert pages[0]["channels"][0]["id"] == "C1"
    assert pages[1]["channels"][0]["id"] == "C2"
