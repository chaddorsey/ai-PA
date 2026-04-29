"""Unit tests for the auto-approval responder (task #90)."""
from __future__ import annotations

import threading
import time
from unittest.mock import patch, MagicMock

from approval_responder import (
    _classify,
    _extract_pending_calls,
    classify_race_loss,
    maybe_handle_approval_request,
)


class FakeHandle:
    def __init__(self, agent_id="agent-test", conv_id="conv-test"):
        self.agent_id = agent_id
        self.conv_id = conv_id


# -------------------- _classify --------------------

def test_classify_interactive_always_denied():
    assert _classify("AskUserQuestion", {"AskUserQuestion"}, {"AskUserQuestion"}) is False


def test_classify_allowlisted_approved():
    assert _classify("Bash", {"Bash", "Task"}, {"AskUserQuestion"}) is True


def test_classify_unlisted_with_explicit_allow_set_denied():
    assert _classify("CustomTool", {"Bash"}, {"AskUserQuestion"}) is False


def test_classify_yolo_mode_empty_allowlist_approves_all():
    assert _classify("AnyTool", set(), {"AskUserQuestion"}) is True


def test_classify_yolo_still_denies_interactive():
    assert _classify("AskUserQuestion", set(), {"AskUserQuestion"}) is False


# -------------------- _extract_pending_calls --------------------

def test_extract_plural_tool_calls():
    ev = {
        "tool_calls": [
            {"id": "call_1", "name": "Task"},
            {"id": "call_2", "name": "Bash"},
        ]
    }
    assert _extract_pending_calls(ev) == [
        {"tool_call_id": "call_1", "tool_name": "Task"},
        {"tool_call_id": "call_2", "tool_name": "Bash"},
    ]


def test_extract_singular_tool_call_fallback():
    ev = {"tool_call": {"id": "call_solo", "name": "Read"}}
    assert _extract_pending_calls(ev) == [
        {"tool_call_id": "call_solo", "tool_name": "Read"}
    ]


def test_extract_empty_returns_empty_list():
    assert _extract_pending_calls({}) == []


def test_extract_handles_tool_call_id_field_variant():
    ev = {"tool_calls": [{"tool_call_id": "alt_1", "tool_name": "Glob"}]}
    assert _extract_pending_calls(ev) == [
        {"tool_call_id": "alt_1", "tool_name": "Glob"}
    ]


# -------------------- maybe_handle_approval_request --------------------

def test_non_approval_event_returns_false():
    handle = FakeHandle()
    handled = maybe_handle_approval_request(
        handle,
        {"message_type": "assistant_message", "content": "hi"},
    )
    assert handled is False


def test_approval_event_with_no_calls_returns_false():
    handle = FakeHandle()
    handled = maybe_handle_approval_request(
        handle,
        {"message_type": "approval_request_message"},
    )
    assert handled is False


def test_approval_event_fires_post(monkeypatch):
    handle = FakeHandle(agent_id="agent-AAA", conv_id="conv-AAA")
    posted = []

    def fake_post(agent_id, decisions, timeout=30):
        posted.append((agent_id, decisions))
        return {"messages": []}

    monkeypatch.setattr("approval_responder._post_approval", fake_post)

    handled = maybe_handle_approval_request(
        handle,
        {
            "message_type": "approval_request_message",
            "tool_calls": [{"id": "tc_1", "name": "Task"}],
        },
        allowed_tools={"Task", "Bash"},
        interactive_tools={"AskUserQuestion"},
    )
    assert handled is True

    # Wait for the daemon thread
    deadline = time.time() + 2.0
    while not posted and time.time() < deadline:
        time.sleep(0.01)

    assert len(posted) == 1
    agent_id, decisions = posted[0]
    assert agent_id == "agent-AAA"
    assert decisions == [
        {"type": "approval", "tool_call_id": "tc_1", "approve": True, "reason": "auto-allow (--yolo non-interactive policy)"}
    ]


def test_approval_event_denies_interactive_tool(monkeypatch):
    handle = FakeHandle(agent_id="agent-deny", conv_id="conv-deny")
    posted = []

    def fake_post(agent_id, decisions, timeout=30):
        posted.append((agent_id, decisions))
        return {"messages": []}

    monkeypatch.setattr("approval_responder._post_approval", fake_post)

    maybe_handle_approval_request(
        handle,
        {
            "message_type": "approval_request_message",
            "tool_calls": [{"id": "tc_X", "name": "AskUserQuestion"}],
        },
        allowed_tools={"Task", "Bash"},
        interactive_tools={"AskUserQuestion", "EnterPlanMode"},
    )

    deadline = time.time() + 2.0
    while not posted and time.time() < deadline:
        time.sleep(0.01)

    assert len(posted) == 1
    _, decisions = posted[0]
    assert decisions[0]["approve"] is False
    assert "interactive" in decisions[0]["reason"]


def test_dedup_skips_already_responded_tool_call_id(monkeypatch):
    handle = FakeHandle(agent_id="agent-dedup", conv_id="conv-dedup")
    posted = []

    def fake_post(agent_id, decisions, timeout=30):
        posted.append(decisions)
        return {"messages": []}

    monkeypatch.setattr("approval_responder._post_approval", fake_post)

    ev = {
        "message_type": "approval_request_message",
        "tool_calls": [{"id": "shared_tcid", "name": "Bash"}],
    }
    h1 = maybe_handle_approval_request(handle, ev, allowed_tools={"Bash"}, interactive_tools=set())
    # second call with same tool_call_id: should be dedup-skipped
    h2 = maybe_handle_approval_request(handle, ev, allowed_tools={"Bash"}, interactive_tools=set())

    deadline = time.time() + 2.0
    while not posted and time.time() < deadline:
        time.sleep(0.01)

    assert h1 is True
    assert h2 is False
    assert len(posted) == 1


# -------------------- classify_race_loss --------------------

def test_classify_race_loss_no_state_is_unknown():
    assert classify_race_loss(None) == "unknown"
    assert classify_race_loss({}) == "unknown"


def test_classify_race_loss_active_run_is_letta_code_won():
    assert classify_race_loss({"status": "running"}) == "letta_code_won"
    assert classify_race_loss({"status": "in_progress"}) == "letta_code_won"
    assert classify_race_loss({"status": "created"}) == "letta_code_won"


def test_classify_race_loss_completed_clean_is_letta_code_won():
    assert classify_race_loss({"status": "completed", "stop_reason": "end_turn"}) == "letta_code_won"
    assert classify_race_loss({"status": "completed", "stop_reason": None}) == "letta_code_won"
    assert classify_race_loss({"status": "completed", "stop_reason": "max_steps"}) == "letta_code_won"


def test_classify_race_loss_failed_is_subprocess_crashed():
    # The empty-approvals bug fingerprint: failed run with stop_reason=None
    assert classify_race_loss({"status": "failed", "stop_reason": None}) == "subprocess_crashed"
    # Also failed with stop_reason=error
    assert classify_race_loss({"status": "failed", "stop_reason": "error"}) == "subprocess_crashed"


def test_classify_race_loss_completed_requires_approval_is_subprocess_crashed():
    # Stranded signature: streaming closed mid-approval; server says completed
    # but stop_reason still reflects the unresolved approval state.
    assert classify_race_loss({"status": "completed", "stop_reason": "requires_approval"}) == "subprocess_crashed"


def test_classify_race_loss_unrecognized_status_is_unknown():
    assert classify_race_loss({"status": "weird-state"}) == "unknown"


# -------------------- crash-detection path --------------------

def test_race_loss_crash_emits_synthetic_error(monkeypatch):
    handle = FakeHandle(agent_id="agent-crash", conv_id="conv-crash")
    forwarded = []

    def fake_post(agent_id, decisions, timeout=30):
        return {"_error": "HTTP 400: No tool call is currently awaiting approval"}

    def fake_get_run(run_id, timeout=10.0):
        return {"status": "failed", "stop_reason": None}

    def emit_cb(h, ev):
        forwarded.append(ev)

    monkeypatch.setattr("approval_responder._post_approval", fake_post)
    monkeypatch.setattr("approval_responder._get_run_state", fake_get_run)

    handled = maybe_handle_approval_request(
        handle,
        {
            "message_type": "approval_request_message",
            "tool_calls": [{"id": "tc_dead", "name": "Task"}],
            "run_id": "run-died",
        },
        allowed_tools={"Task"},
        interactive_tools=set(),
        emit_callback=emit_cb,
    )
    assert handled is True

    deadline = time.time() + 2.0
    while not forwarded and time.time() < deadline:
        time.sleep(0.01)

    assert len(forwarded) == 1
    err = forwarded[0]
    assert err["type"] == "error"
    assert err["_synthesized_by"] == "approval_responder"
    assert err["_run_id"] == "run-died"
    assert "stranded" in err["message"].lower() or "subprocess crash" in err["message"].lower()


def test_race_loss_letta_code_won_does_not_emit(monkeypatch):
    handle = FakeHandle(agent_id="agent-clean", conv_id="conv-clean")
    forwarded = []

    def fake_post(agent_id, decisions, timeout=30):
        return {"_error": "HTTP 400: No tool call is currently awaiting approval"}

    def fake_get_run(run_id, timeout=10.0):
        return {"status": "completed", "stop_reason": "end_turn"}

    def emit_cb(h, ev):
        forwarded.append(ev)

    monkeypatch.setattr("approval_responder._post_approval", fake_post)
    monkeypatch.setattr("approval_responder._get_run_state", fake_get_run)

    maybe_handle_approval_request(
        handle,
        {
            "message_type": "approval_request_message",
            "tool_calls": [{"id": "tc_clean", "name": "Bash"}],
            "run_id": "run-clean",
        },
        allowed_tools={"Bash"},
        interactive_tools=set(),
        emit_callback=emit_cb,
    )

    # Wait briefly to give the daemon thread a chance
    time.sleep(0.3)

    # Letta-code won the race — no synthetic error emitted
    assert len(forwarded) == 0


def test_emit_callback_forwards_resumed_messages(monkeypatch):
    handle = FakeHandle(agent_id="agent-emit", conv_id="conv-emit")
    forwarded = []

    def fake_post(agent_id, decisions, timeout=30):
        return {
            "messages": [
                {"message_type": "reasoning_message", "reasoning": "approved"},
                {"message_type": "assistant_message", "content": "done"},
            ]
        }

    def emit_cb(h, ev):
        forwarded.append(ev)

    monkeypatch.setattr("approval_responder._post_approval", fake_post)

    maybe_handle_approval_request(
        handle,
        {
            "message_type": "approval_request_message",
            "tool_calls": [{"id": "tc_emit", "name": "Read"}],
        },
        allowed_tools={"Read"},
        interactive_tools=set(),
        emit_callback=emit_cb,
    )

    deadline = time.time() + 2.0
    while len(forwarded) < 2 and time.time() < deadline:
        time.sleep(0.01)

    assert len(forwarded) == 2
    assert forwarded[0]["_synthesized_by"] == "approval_responder"
    assert forwarded[0]["message_type"] == "reasoning_message"
    assert forwarded[1]["message_type"] == "assistant_message"
