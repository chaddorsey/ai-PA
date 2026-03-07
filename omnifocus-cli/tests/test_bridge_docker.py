import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from omnifocus_cli.bridge import call_omnifocus


def _make_http_response(body: dict) -> MagicMock:
    """Create a mock HTTP response that works as a context manager."""
    raw = json.dumps(body).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_bridge_uses_http_when_osascript_unavailable():
    """When osascript is not available, call_omnifocus should use HTTP transport."""
    inner_result = {"tasks": [{"id": "t-1", "name": "Test"}]}
    bridge_response = {"success": True, "result": json.dumps(inner_result)}
    mock_resp = _make_http_response(bridge_response)

    with (
        patch("omnifocus_cli.bridge.shutil.which", return_value=None),
        patch("omnifocus_cli.bridge.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen,
    ):
        result = call_omnifocus("queryTasks", {"projectId": "p-1"})

    # Verify HTTP POST was made with correct payload
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert req.get_method() == "POST"
    assert req.full_url == "http://host.docker.internal:8889/execute"
    sent_body = json.loads(req.data.decode("utf-8"))
    assert sent_body["command"] == "queryTasks"
    assert sent_body["args"] == {"projectId": "p-1"}

    # Verify double-encoded JSON was correctly unwrapped
    assert result == inner_result


def test_bridge_uses_osascript_when_available():
    """When osascript is available, call_omnifocus should use osascript transport."""
    osascript_output = json.dumps({"result": {"id": "t-1", "name": "Test"}})

    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = osascript_output
    mock_run_result.stderr = ""

    with (
        patch("omnifocus_cli.bridge.shutil.which", return_value="/usr/bin/osascript"),
        patch("omnifocus_cli.bridge.subprocess.run", return_value=mock_run_result) as mock_run,
    ):
        result = call_omnifocus("getTask", {"taskId": "t-1"})

    # Verify osascript was called
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/usr/bin/osascript"

    # Verify result was extracted
    assert result == {"id": "t-1", "name": "Test"}


def test_http_bridge_custom_url():
    """OMNIFOCUS_BRIDGE_URL env var overrides default bridge URL."""
    bridge_response = {"success": True, "result": json.dumps({"ok": True})}
    mock_resp = _make_http_response(bridge_response)

    with (
        patch("omnifocus_cli.bridge.shutil.which", return_value=None),
        patch("omnifocus_cli.bridge.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen,
        patch.dict("os.environ", {"OMNIFOCUS_BRIDGE_URL": "http://localhost:9999"}),
    ):
        call_omnifocus("health", {})

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "http://localhost:9999/execute"


def test_http_bridge_error_raises():
    """HTTP bridge error response should raise RuntimeError."""
    bridge_response = {"error": "Plugin not found"}
    mock_resp = _make_http_response(bridge_response)

    with (
        patch("omnifocus_cli.bridge.shutil.which", return_value=None),
        patch("omnifocus_cli.bridge.urllib.request.urlopen", return_value=mock_resp),
    ):
        try:
            call_omnifocus("getTask", {"taskId": "bad"})
            assert False, "Expected RuntimeError"
        except RuntimeError as exc:
            assert "Plugin not found" in str(exc)
