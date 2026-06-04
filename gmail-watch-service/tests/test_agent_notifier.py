"""Tests for agent_notifier.

Migrated 2026-06-04 to validate the letta-push-receiver transport
(POST /push with a `source` slug). The pre-migration tests asserted
URL+payload against /v1/agents/<id>/messages on a Docker-Letta server;
that path is gone. Now we assert:

- correct source slug per notify_* method (drives owner-agent routing)
- httpx POST goes to PUSH_RECEIVER_URL with priority + prompt body
- error/connection failures return status='error' without raising
- _format_* helpers preserve the agent-facing message shape (unchanged
  by the transport migration; valuable to keep covered)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gmail_watch.models import WatchedThread
from gmail_watch.services.agent_notifier import AgentNotifier, PUSH_RECEIVER_URL


# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_httpx():
    """Mock httpx.AsyncClient used by _send_to_agent."""
    with patch("gmail_watch.services.agent_notifier.httpx.AsyncClient") as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client
        yield client


@pytest.fixture
def mock_queue_writer():
    """Stub out the pa_web.task_queue async write so tests don't need
    asyncpg / a live database. The push-to-receiver path is what we're
    testing here; the queue write is verified separately."""
    with patch.object(
        AgentNotifier, "_write_watch_event_to_queue", new_callable=AsyncMock,
    ) as m:
        m.return_value = None
        yield m


def _watched_thread(**overrides):
    """Build a MagicMock WatchedThread with sensible defaults."""
    t = MagicMock(spec=WatchedThread)
    t.thread_id = "thread_123"
    t.subject = "Test Subject"
    t.original_recipients = ["user@example.com"]
    t.created_at = datetime(2026, 1, 28, tzinfo=timezone.utc)
    t.message_count = 2
    t.reply_message_id = "msg_abc"
    t.followup_seconds = None
    t.followup_due_at = None
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def _ok_response(json_body=None):
    """Build a mock httpx Response with .status_code=200 and .json()."""
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_body or {"status": "accepted"}
    return r


# ─── routing — each notify_* picks the right source slug ─────────────────────


@pytest.mark.asyncio
async def test_notify_reply_received_routes_to_email_watch(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()

    await notifier.notify_reply_received(
        thread=_watched_thread(),
        new_message_id="msg_abc",
        from_address="sender@example.com",
        preview="Thanks…",
    )

    mock_httpx.post.assert_called_once()
    url = mock_httpx.post.call_args[0][0]
    body = mock_httpx.post.call_args[1]["json"]
    assert url == PUSH_RECEIVER_URL
    assert body["source"] == "email-watch"
    assert body["priority"] == "normal"
    assert "Thanks" in body["prompt"]


@pytest.mark.asyncio
async def test_notify_followup_needed_routes_to_email_watch(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()
    thread = _watched_thread(
        followup_seconds=259200,
        followup_due_at=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    await notifier.notify_followup_needed(thread=thread)

    body = mock_httpx.post.call_args[1]["json"]
    assert body["source"] == "email-watch"


@pytest.mark.asyncio
async def test_notify_watch_started_routes_to_email_watch(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()

    await notifier.notify_watch_started(thread=_watched_thread())

    body = mock_httpx.post.call_args[1]["json"]
    assert body["source"] == "email-watch"


@pytest.mark.asyncio
async def test_notify_task_queued_routes_to_email_source(mock_httpx):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()

    await notifier.notify_task_queued(
        entries=[
            {"message_id": "m1", "subject": "Draft proposal",
             "from": "bob@x.com", "has_notes": False,
             "marker_type": "explicit", "task_hint": "Send Bob the draft"},
        ],
    )

    body = mock_httpx.post.call_args[1]["json"]
    assert body["source"] == "email"


@pytest.mark.asyncio
async def test_notify_spark_queue_routes_to_caller_source(mock_httpx):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()

    await notifier.notify_spark_queue(
        entries=[{"ref_id": "x"}],
        source="slack",  # caller-specified — receiver routes slack → pulse
    )

    body = mock_httpx.post.call_args[1]["json"]
    assert body["source"] == "slack"


@pytest.mark.asyncio
async def test_notify_drive_task_queued_routes_to_docs(mock_httpx):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()

    await notifier.notify_drive_task_queued(
        entries=[
            {"comment_id": "c1", "doc_title": "Strategy 2027",
             "comment_text": "Please review", "marker_type": "explicit",
             "task_hint": "Review strategy doc"},
        ],
    )

    body = mock_httpx.post.call_args[1]["json"]
    assert body["source"] == "google-docs-comment"


# ─── prompt body content — agent-facing message shape ───────────────────────


@pytest.mark.asyncio
async def test_reply_prompt_includes_thread_context(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    mock_httpx.post.return_value = _ok_response()
    thread = _watched_thread(subject="Important Meeting", message_count=3)

    await notifier.notify_reply_received(
        thread=thread,
        new_message_id="msg_abc",
        from_address="boss@company.com",
        preview="Sounds good, let's proceed.",
    )

    prompt = mock_httpx.post.call_args[1]["json"]["prompt"]
    assert "Important Meeting" in prompt
    assert "boss@company.com" in prompt
    assert "Sounds good, let's proceed." in prompt
    assert "msg_abc" in prompt


# ─── failure modes — receiver down/error returns status='error' ─────────────


@pytest.mark.asyncio
async def test_receiver_5xx_returns_error(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    err_resp = MagicMock()
    err_resp.status_code = 502
    err_resp.text = "Bad Gateway"
    mock_httpx.post.return_value = err_resp

    result = await notifier.notify_reply_received(
        thread=_watched_thread(),
        new_message_id="msg_abc",
        from_address="x@y.com",
        preview="hi",
    )

    assert result["status"] == "error"
    assert "502" in result["error"]


@pytest.mark.asyncio
async def test_receiver_unreachable_returns_error(mock_httpx, mock_queue_writer):
    notifier = AgentNotifier()
    mock_httpx.post.side_effect = Exception("Connection refused")

    result = await notifier.notify_reply_received(
        thread=_watched_thread(),
        new_message_id="msg_abc",
        from_address="x@y.com",
        preview="hi",
    )

    assert result["status"] == "error"
    assert "Connection refused" in result["error"]


# ─── _format_* helpers — pure message formatting (unchanged by migration) ───


def test_format_reply_message_truncates_long_preview():
    notifier = AgentNotifier()
    thread = _watched_thread(subject="No-x subject")
    long_preview = "Q" * 1000  # unique sentinel char that won't appear elsewhere

    msg = notifier._format_reply_message(
        thread=thread,
        from_address="alice@example.com",
        preview=long_preview,
    )

    # Truncation happened: "..." marker present, sentinel cut to 500.
    assert "..." in msg
    assert msg.count("Q") == 500
    # And it actually truncated — the full 1000 didn't sneak through.
    assert "Q" * 1000 not in msg


def test_format_reply_message_handles_none_subject():
    notifier = AgentNotifier()
    thread = _watched_thread(subject=None)

    msg = notifier._format_reply_message(
        thread=thread,
        from_address="user@example.com",
        preview="hello",
    )

    assert "(no subject)" in msg


def test_format_reply_message_handles_none_recipients():
    notifier = AgentNotifier()
    thread = _watched_thread(original_recipients=None)

    msg = notifier._format_reply_message(
        thread=thread,
        from_address="user@example.com",
        preview="hello",
    )

    assert "unknown" in msg


# ─── constructor signature — backward compat ────────────────────────────────


def test_agent_notifier_accepts_legacy_kwargs():
    """letta_base_url + agent_id args are kept for back-compat with
    existing callers (watch_manager). They're no longer used for routing
    but must not raise."""
    notifier = AgentNotifier(
        letta_base_url="http://letta:8283",
        agent_id="agent-anything-goes",
    )
    assert notifier.letta_base_url == "http://letta:8283"
    assert notifier.agent_id == "agent-anything-goes"


def test_agent_notifier_no_args_ok():
    notifier = AgentNotifier()
    # Defaults pulled from settings; they may be None — that's fine
    # because routing is via PUSH_RECEIVER_URL + source slug now.
    assert hasattr(notifier, "letta_base_url")
    assert hasattr(notifier, "agent_id")
