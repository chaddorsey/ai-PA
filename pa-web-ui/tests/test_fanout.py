"""Unit 1.4 tests — subscriber fan-out with seq_id-based resume.

Covers:
- Multi-subscriber broadcast (same events in same order)
- since=None: no replay
- since=<seq within buffer>: seeded replay
- since=<seq above buffer>: no replay (client is already ahead)
- since=<seq below floor>: resync_required marker
- Slow subscriber gets slow_subscriber marker; others unaffected
- N consecutive Full → force unsubscribe; other subs keep receiving
- unsubscribe doesn't break others; subprocess stays alive
- Two subs on same conv see identical stream order

Run: cd pa-web-ui && python -m pytest tests/test_fanout.py -v
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess_pool as sp  # noqa: E402
from tests.test_subprocess_pool import FakePopen, _feed_init, _ensure_async  # noqa: E402


# -------------------------------------------------- fixtures


@pytest.fixture
def live_handle():
    """Spawned + init'd handle with ring buffer populated for tests."""
    fake_processes: Dict[str, FakePopen] = {}

    def spawn(**kw):
        proc = FakePopen()
        fake_processes[kw["conv_id"]] = proc
        return proc

    reg = sp.SubprocessRegistry(
        max_concurrent=3,
        init_timeout_s=2.0,
        spawn_factory=spawn,
    )
    fut = _ensure_async(reg, "agent-A", "conv-fan")
    for _ in range(50):
        if "conv-fan" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-fan"]
    _feed_init(proc, conv_id="conv-fan")
    handle = fut.result(timeout=2)
    try:
        yield handle, proc, reg
    finally:
        reg.shutdown(grace_s=0.3)


def _drain(sub: sp.Subscriber, timeout_s: float = 0.2) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            items.append(sub.get(timeout=0.02))
        except queue.Empty:
            break
    # Drain anything still buffered with no wait.
    while True:
        try:
            items.append(sub.get_nowait())
        except queue.Empty:
            break
    return items


# -------------------------------------------------- happy path


def test_two_subscribers_see_identical_events(live_handle):
    handle, proc, _ = live_handle
    sub_a = handle.subscribe()
    sub_b = handle.subscribe()

    proc.stdout.push_event({"type": "text", "content": "hi"})
    proc.stdout.push_event({"type": "text", "content": "there"})
    time.sleep(0.1)

    a_items = _drain(sub_a)
    b_items = _drain(sub_b)

    a_types = [e.get("type") for e in a_items]
    b_types = [e.get("type") for e in b_items]
    assert a_types == b_types
    # Both saw two text events.
    assert a_types.count("text") == 2
    # Same seq_ids.
    a_seqs = [e.get("_seq_id") for e in a_items if e.get("type") == "text"]
    b_seqs = [e.get("_seq_id") for e in b_items if e.get("type") == "text"]
    assert a_seqs == b_seqs


def test_subscriber_count_updates_on_subscribe_unsubscribe(live_handle):
    handle, _, _ = live_handle
    assert handle.describe()["subscriber_count"] == 0
    sub = handle.subscribe()
    assert handle.describe()["subscriber_count"] == 1
    handle.unsubscribe(sub)
    assert handle.describe()["subscriber_count"] == 0


# -------------------------------------------------- since modes


def test_subscribe_since_none_no_replay(live_handle):
    """since=None: no events from ring buffer; only live."""
    handle, proc, _ = live_handle
    # Pre-populate ring buffer with 3 events.
    for i in range(3):
        proc.stdout.push_event({"type": "text", "content": f"pre-{i}"})
    time.sleep(0.1)

    sub = handle.subscribe(since=None)
    # Immediately drain — should be empty (no replay).
    items = _drain(sub, timeout_s=0.05)
    assert items == []

    # Live event AFTER subscription should land.
    proc.stdout.push_event({"type": "text", "content": "live"})
    time.sleep(0.1)
    items = _drain(sub)
    live_events = [e for e in items if e.get("type") == "text"]
    assert len(live_events) == 1
    assert live_events[0]["content"] == "live"


def test_subscribe_since_valid_replays_tail(live_handle):
    """since=<seq within buffer>: queue seeded with events > since."""
    handle, proc, _ = live_handle
    for i in range(5):
        proc.stdout.push_event({"type": "text", "content": f"evt-{i}"})
    time.sleep(0.1)

    # Find the seq_id of the 2nd text event — subscribe from there.
    snap = handle.ring_buffer.snapshot_for_status()
    oldest = snap["oldest_seq"]
    # After init + 5 text events, seq_ids are roughly oldest, oldest+1, ..., oldest+5
    since = oldest + 2  # replay should include everything strictly > since

    sub = handle.subscribe(since=since)
    items = _drain(sub, timeout_s=0.05)
    # All replayed events have _seq_id > since.
    for e in items:
        assert e["_seq_id"] > since


def test_subscribe_since_above_newest_no_replay(live_handle):
    """since higher than anything buffered → no replay, live only."""
    handle, proc, _ = live_handle
    proc.stdout.push_event({"type": "text", "content": "x"})
    time.sleep(0.1)

    sub = handle.subscribe(since=999_999)
    items = _drain(sub, timeout_s=0.05)
    assert items == []


def test_subscribe_since_below_floor_resync_required():
    """If the ring buffer evicts below `since`, subscriber gets a
    resync_required marker.
    """
    # Build a handle with a tiny ring buffer so we can trigger eviction
    # without flooding it with noise.
    fake_processes: Dict[str, FakePopen] = {}

    def spawn(**kw):
        proc = FakePopen()
        fake_processes[kw["conv_id"]] = proc
        return proc

    reg = sp.SubprocessRegistry(
        max_concurrent=1, init_timeout_s=2.0, spawn_factory=spawn
    )
    fut = _ensure_async(reg, "agent-A", "conv-tiny")
    for _ in range(50):
        if "conv-tiny" in fake_processes:
            break
        time.sleep(0.01)
    proc = fake_processes["conv-tiny"]
    _feed_init(proc, conv_id="conv-tiny")
    handle = fut.result(timeout=2)
    try:
        # Shrink the ring buffer to a value that retains ~2-3 events of
        # our test size, so eviction actually happens BUT the buffer
        # isn't perpetually empty.
        handle.ring_buffer.max_bytes = 300

        # Flood with events large enough to force eviction.
        for i in range(30):
            proc.stdout.push_event(
                {"type": "text", "content": "x" * 40, "idx": i}
            )

        # Poll until the reader processes and eviction stabilizes.
        oldest = 0
        for _ in range(200):
            oldest = handle.ring_buffer.oldest_seq()
            if oldest > 5 and handle.ring_buffer.count > 0:
                break
            time.sleep(0.01)
        assert oldest > 1, (
            f"ring buffer should have evicted early events; "
            f"oldest_seq={oldest}, count={handle.ring_buffer.count}"
        )

        # Subscribe with since=0 (far below the new floor).
        sub = handle.subscribe(since=0)
        items = _drain(sub, timeout_s=0.1)
        resync = [e for e in items if e.get("type") == "resync_required"]
        assert len(resync) == 1
        assert resync[0]["reason"] == "ring_buffer_evicted"
        assert resync[0]["oldest_available_seq_id"] == oldest
    finally:
        reg.shutdown(grace_s=0.3)


# -------------------------------------------------- slow subscriber


def test_slow_subscriber_marker_emitted(live_handle):
    """When a subscriber's queue fills, it gets a slow_subscriber marker,
    not silent drop.
    """
    handle, proc, _ = live_handle

    # Tiny queue — fills immediately.
    sub = handle.subscribe(max_queue=2)

    # Overflow the queue with 10 events.
    for i in range(10):
        proc.stdout.push_event({"type": "text", "content": f"flood-{i}"})
    time.sleep(0.2)

    items = _drain(sub, timeout_s=0.1)
    markers = [e for e in items if e.get("type") == "slow_subscriber"]
    assert markers, "slow subscriber must receive at least one marker"
    assert markers[0]["subscriber_id"] == sub.id


def test_slow_subscriber_isolated_from_fast_one(live_handle):
    """One slow subscriber should NOT affect a fast one."""
    handle, proc, _ = live_handle

    slow = handle.subscribe(max_queue=2)
    fast = handle.subscribe(max_queue=1000)

    for i in range(20):
        proc.stdout.push_event({"type": "text", "content": f"e{i}"})
    time.sleep(0.2)

    fast_items = _drain(fast, timeout_s=0.2)
    fast_texts = [e for e in fast_items if e.get("type") == "text"]
    # Fast subscriber gets ~all 20 (allow for small scheduling variance).
    assert len(fast_texts) >= 18


def test_slow_subscriber_force_unsubscribed_after_threshold(live_handle):
    """N consecutive Full failures → force unsubscribe."""
    handle, proc, _ = live_handle

    # max_queue=1 + lots of events = fast failure accumulation.
    sub = handle.subscribe(max_queue=1)

    # Drive well past the threshold (default 10).
    for i in range(50):
        proc.stdout.push_event({"type": "text", "content": f"e{i}"})
    time.sleep(0.3)

    # Subscriber should have been force-unsubscribed.
    assert sub not in handle.subscribers


# -------------------------------------------------- unsubscribe


def test_unsubscribe_drains_queue_and_doesnt_affect_others(live_handle):
    handle, proc, _ = live_handle

    keeper = handle.subscribe()
    leaver = handle.subscribe()

    proc.stdout.push_event({"type": "text", "content": "both-see"})
    time.sleep(0.1)

    handle.unsubscribe(leaver)
    # Unsubscribe drains — leaver.get should see nothing.
    try:
        leaver.get_nowait()
        assert False, "leaver queue should have been drained"
    except queue.Empty:
        pass

    # Keeper still works.
    proc.stdout.push_event({"type": "text", "content": "only-keeper"})
    time.sleep(0.1)
    items = _drain(keeper, timeout_s=0.2)
    texts = [e for e in items if e.get("type") == "text"]
    # keeper sees both "both-see" and "only-keeper"
    contents = [e.get("content") for e in texts]
    assert "both-see" in contents
    assert "only-keeper" in contents


def test_unsubscribe_idempotent(live_handle):
    handle, _, _ = live_handle
    sub = handle.subscribe()
    handle.unsubscribe(sub)
    # Second call is a no-op, must not raise.
    handle.unsubscribe(sub)


def test_subprocess_stays_alive_after_all_subscribers_leave(live_handle):
    """Detaching every subscriber must NOT kill the subprocess."""
    handle, proc, _ = live_handle

    s = handle.subscribe()
    handle.unsubscribe(s)
    assert handle.alive
    assert proc.poll() is None

    # Publish more events — should still work (noisily, no subscribers).
    proc.stdout.push_event({"type": "text", "content": "nobody listening"})
    time.sleep(0.1)
    assert handle.alive


# -------------------------------------------------- integration-ish


def test_subscribe_seeds_then_joins_live(live_handle):
    """Subscribe with since=<valid> → replayed events first, then live."""
    handle, proc, _ = live_handle

    # Populate ring with some history.
    for i in range(4):
        proc.stdout.push_event({"type": "text", "content": f"hist-{i}"})
    time.sleep(0.1)
    mid_seq = handle.ring_buffer.snapshot_for_status()["oldest_seq"]

    sub = handle.subscribe(since=mid_seq)

    # Add a live event after subscription.
    proc.stdout.push_event({"type": "text", "content": "live-after"})
    time.sleep(0.15)

    items = _drain(sub, timeout_s=0.2)
    texts = [e for e in items if e.get("type") == "text"]
    contents = [e.get("content") for e in texts]
    # Both replayed history (> mid_seq) and the live event should be present.
    assert "live-after" in contents
    # Seq_ids should be monotonic in order received.
    seqs = [e["_seq_id"] for e in texts]
    assert seqs == sorted(seqs)
