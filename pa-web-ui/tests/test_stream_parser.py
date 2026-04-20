"""Unit 1.3 tests — merge_tool_args, RingBuffer, enriched event envelope,
tool-call batching.

Fixture-driven: pushes canned events through the reader to verify the
same stream-json semantics as LettaBot's session-manager.

Run: cd pa-web-ui && python -m pytest tests/test_stream_parser.py -v
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess_pool as sp  # noqa: E402
from tests.test_subprocess_pool import FakePopen, _feed_init, _ensure_async  # noqa: E402


# ======================================================================
# merge_tool_args
# ======================================================================


class TestMergeToolArgs:
    def test_empty_incoming_returns_existing(self):
        assert sp.merge_tool_args('{"a":1', "") == '{"a":1'

    def test_empty_existing_returns_incoming(self):
        assert sp.merge_tool_args("", '{"a":1}') == '{"a":1}'

    def test_identical_returns_same(self):
        assert sp.merge_tool_args('{"a":1}', '{"a":1}') == '{"a":1}'

    def test_cumulative_chunking(self):
        """Each incoming chunk contains all prior text plus more."""
        assert sp.merge_tool_args('{"a":1', '{"a":1,"b":2}') == '{"a":1,"b":2}'

    def test_delta_chunking(self):
        """Each incoming chunk is new bytes to append."""
        assert sp.merge_tool_args('{"a":1', ',"b":2}') == '{"a":1,"b":2}'

    def test_redundant_delta_returns_existing(self):
        """A new chunk is a proper suffix of existing — ignore it."""
        assert sp.merge_tool_args('{"a":1,"b":2}', '"b":2}') == '{"a":1,"b":2}'

    def test_repeated_cumulative_growth(self):
        args = ""
        for piece in ['{"a":', '{"a":1', '{"a":1,"b":', '{"a":1,"b":2}']:
            args = sp.merge_tool_args(args, piece)
        assert args == '{"a":1,"b":2}'

    def test_repeated_delta_growth(self):
        chunks = ['{"a":', "1,", '"b":', "2}"]
        args = ""
        for c in chunks:
            args = sp.merge_tool_args(args, c)
        assert args == '{"a":1,"b":2}'


# ======================================================================
# RingBuffer
# ======================================================================


class TestRingBuffer:
    def test_append_and_count(self):
        rb = sp.RingBuffer(max_bytes=10_000)
        rb.append(1, {"type": "text", "content": "hello"})
        rb.append(2, {"type": "text", "content": "world"})
        assert rb.count == 2
        assert rb.oldest_seq() == 1
        assert rb.newest_seq() == 2

    def test_eviction_at_byte_cap(self):
        rb = sp.RingBuffer(max_bytes=100)
        for i in range(20):
            rb.append(i, {"type": "text", "content": "x" * 30})
        # Only the latest few events fit in ~100 bytes.
        assert rb.count < 20
        assert rb.size_bytes <= 100 + 100  # headroom for a partial overshoot
        assert rb.newest_seq() == 19

    def test_events_since_returns_later_events(self):
        rb = sp.RingBuffer()
        for i in range(1, 6):
            rb.append(i, {"type": "text", "content": f"e{i}"})
        events, resync = rb.events_since(2)
        assert resync is False
        assert [e["content"] for e in events] == ["e3", "e4", "e5"]

    def test_events_since_none_returns_empty_no_resync(self):
        rb = sp.RingBuffer()
        for i in range(1, 4):
            rb.append(i, {"type": "text"})
        events, resync = rb.events_since(None)
        assert events == []
        assert resync is False

    def test_resync_required_when_since_before_floor(self):
        """Evict everything but a few newest; client asking for older seq
        must get resync_required.
        """
        rb = sp.RingBuffer(max_bytes=50)
        for i in range(100):
            rb.append(i, {"type": "text", "content": "x" * 20})
        oldest = rb.oldest_seq()
        events, resync = rb.events_since(oldest - 10)
        assert resync is True
        assert events == []

    def test_turn_boundary_markers_pruned_with_eviction(self):
        rb = sp.RingBuffer(max_bytes=60)
        for i in range(1, 11):
            rb.append(
                i,
                {"type": "text", "content": "z" * 10},
                is_turn_boundary=(i % 3 == 0),
            )
        snap = rb.snapshot_for_status()
        # Every boundary still in snap must be >= oldest seq.
        oldest = rb.oldest_seq()
        assert all(b >= oldest for b in snap["turn_boundaries"])


# ======================================================================
# Enriched event envelope
# ======================================================================


@pytest.fixture
def live_handle(fake_processes=None):
    """A spawned-and-init'd handle, ready to feed events into."""
    fake_processes = {}

    def spawn(**kw):
        proc = FakePopen()
        fake_processes[kw["conv_id"]] = proc
        return proc

    reg = sp.SubprocessRegistry(
        max_concurrent=2,
        init_timeout_s=2.0,
        spawn_factory=spawn,
    )
    fut = _ensure_async(reg, "agent-A", "conv-envelope")
    for _ in range(50):
        if "conv-envelope" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-envelope"]
    _feed_init(proc, conv_id="conv-envelope")
    handle = fut.result(timeout=2)
    try:
        yield handle, proc, reg
    finally:
        reg.shutdown(grace_s=0.3)


def test_emitted_events_carry_envelope(live_handle):
    handle, proc, _ = live_handle
    proc.stdout.push_event({"type": "text", "content": "hi"})
    proc.stdout.push_event({"type": "text", "content": "there"})
    time.sleep(0.1)

    events, _resync = handle.ring_buffer.events_since(None)
    # events_since(None) returns [] by design; use a large-enough since.
    events, _resync = handle.ring_buffer.events_since(0)
    # Filter to our text events.
    texts = [e for e in events if e.get("type") == "text"]
    assert len(texts) == 2
    for e in texts:
        assert "_seq_id" in e
        assert "_emitted_at" in e
    assert texts[0]["_seq_id"] < texts[1]["_seq_id"]


def test_result_event_marks_turn_boundary(live_handle):
    handle, proc, _ = live_handle
    proc.stdout.push_event({"type": "text", "content": "working..."})
    proc.stdout.push_event({
        "type": "result", "subtype": "success", "run_ids": ["r1"],
    })
    time.sleep(0.1)

    snap = handle.ring_buffer.snapshot_for_status()
    assert snap["turn_boundaries"], "result event should be flagged as turn boundary"


# ======================================================================
# Tool-call batching via stream_event
# ======================================================================


def test_stream_event_tool_call_delta_merged(live_handle):
    """Tool-call deltas across multiple stream_events merge into a single
    tool_call event on the subscriber stream, flushed on boundary.
    """
    handle, proc, _ = live_handle

    # Attach a subscriber queue manually (Unit 1.4 will do this via API).
    sub: "queue.Queue" = queue.Queue()
    with handle.subscriber_lock:
        handle.subscribers.append(sub)

    # Three incremental deltas for one tool call.
    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-1",
            "tool_name": "Bash",
            "arguments_delta": '{"command":"',
        },
    })
    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-1",
            "arguments_delta": 'echo hello',
        },
    })
    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-1",
            "arguments_delta": '"}',
        },
    })
    # Non-stream_event triggers flush.
    proc.stdout.push_event({"type": "text", "content": "after"})
    time.sleep(0.1)

    # Drain subscriber; expect: (init), tool_call (merged), text.
    items: List[Dict[str, Any]] = []
    while True:
        try:
            items.append(sub.get_nowait())
        except queue.Empty:
            break
    tool_calls = [e for e in items if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool_call_id"] == "tc-1"
    assert tool_calls[0]["tool_name"] == "Bash"
    assert tool_calls[0]["arguments"] == '{"command":"echo hello"}'


def test_stream_event_cumulative_mode(live_handle):
    handle, proc, _ = live_handle
    sub: "queue.Queue" = queue.Queue()
    with handle.subscriber_lock:
        handle.subscribers.append(sub)

    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-2",
            "tool_name": "Read",
            "arguments": '{"path":"/',
        },
    })
    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-2",
            "arguments": '{"path":"/etc/hosts"}',
        },
    })
    proc.stdout.push_event({"type": "text", "content": "done"})
    time.sleep(0.1)

    items: List[Dict[str, Any]] = []
    while True:
        try:
            items.append(sub.get_nowait())
        except queue.Empty:
            break
    tool_calls = [e for e in items if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["arguments"] == '{"path":"/etc/hosts"}'


def test_stream_event_without_tool_call_id_pass_through(live_handle):
    """Unknown stream_event shapes fall through to subscribers unchanged."""
    handle, proc, _ = live_handle
    sub: "queue.Queue" = queue.Queue()
    with handle.subscriber_lock:
        handle.subscribers.append(sub)

    proc.stdout.push_event({
        "type": "stream_event",
        "event": {"event_type": "something_new", "data": 42},
    })
    time.sleep(0.05)

    items: List[Dict[str, Any]] = []
    while True:
        try:
            items.append(sub.get_nowait())
        except queue.Empty:
            break
    matches = [e for e in items if e.get("type") == "stream_event"]
    assert len(matches) == 1


def test_pending_flush_on_result(live_handle):
    """Pending tool-calls must flush before the result event fires."""
    handle, proc, _ = live_handle
    sub: "queue.Queue" = queue.Queue()
    with handle.subscriber_lock:
        handle.subscribers.append(sub)

    proc.stdout.push_event({
        "type": "stream_event",
        "event": {
            "tool_call_id": "tc-flush",
            "tool_name": "Grep",
            "arguments_delta": '{"pattern":"foo"}',
        },
    })
    proc.stdout.push_event({
        "type": "result",
        "subtype": "success",
        "run_ids": ["r-flush"],
    })
    time.sleep(0.1)

    items: List[Dict[str, Any]] = []
    while True:
        try:
            items.append(sub.get_nowait())
        except queue.Empty:
            break
    types_in_order = [e.get("type") for e in items]
    # Expected order includes a tool_call BEFORE the result.
    assert "tool_call" in types_in_order
    assert "result" in types_in_order
    assert types_in_order.index("tool_call") < types_in_order.index("result")


# ======================================================================
# Robustness: non-JSON / partial lines
# ======================================================================


def test_reader_skips_non_json_lines(live_handle):
    """A mix of JSON and non-JSON lines shouldn't crash the reader."""
    handle, proc, _ = live_handle

    # Non-JSON noise.
    proc.stdout._q.put(b"[debug] warming up...\n")
    proc.stdout._q.put(b"\n")  # blank line
    proc.stdout.push_event({"type": "text", "content": "after noise"})
    time.sleep(0.1)

    # Handle should still be alive; the text event should have landed.
    assert handle.alive
    events, _ = handle.ring_buffer.events_since(0)
    texts = [e for e in events if e.get("type") == "text"
             and e.get("content") == "after noise"]
    assert texts, "text event after non-JSON noise should still reach ring"
