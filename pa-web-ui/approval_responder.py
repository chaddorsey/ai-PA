"""Auto-approval responder for pa-web (works around letta-code 0.23.8 bug #90).

When the Letta server emits `approval_request_message` for a tool call, the
canonical letta-code client should respond with an `ApprovalCreate` message
to either approve or deny the call. Letta-code 0.23.8 (and 0.24.10) instead
panics and exits the headless subprocess when the run-state's `approvals`
array comes back empty in the streaming response — leaving the run stranded
server-side. See task #90 for full diagnosis.

This module bypasses the broken letta-code path: it watches for
`approval_request_message` events flowing through the subprocess pool and
posts `POST /v1/agents/{agent_id}/messages` with the appropriate
`ApprovalCreate` body. The Letta server then resumes the run.

Policy mirrors `subprocess_pool.DEFAULT_ALLOWED_TOOLS` and
`INTERACTIVE_APPROVAL_TOOLS`. Tools the pool would deny anyway are denied
here; everything else is auto-allowed (matches `--yolo` semantics for
non-interactive tools).

Idempotency: every approval is keyed by tool_call_id; we track which
tool_call_ids we've already responded to per (agent_id, conv_id) and skip
duplicates. This avoids racing with letta-code if it ever recovers
naturally.

Streaming: after POSTing the approval, we synthesize stream events from
the resumed run's response messages and re-emit them to the existing
subscribers via the pool's `_emit` path. This keeps chat.js in sync —
the user sees the resumed assistant output as if nothing went wrong.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
APPROVAL_RESPONDER_TIMEOUT_SECONDS = 30.0


@dataclass
class _ApprovalState:
    """Per-handle dedup state."""
    responded_tool_call_ids: Set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)


# One state per handle (keyed by agent_id+conv_id). Module-level OK because
# the SubprocessHandle is itself stateful — we use a weak association.
_state_by_handle: Dict[str, _ApprovalState] = {}
_state_by_handle_lock = threading.Lock()


def _get_state(key: str) -> _ApprovalState:
    with _state_by_handle_lock:
        s = _state_by_handle.get(key)
        if s is None:
            s = _ApprovalState()
            _state_by_handle[key] = s
        return s


def _classify(tool_name: str, allowed: Set[str], interactive: Set[str]) -> bool:
    """Decide approve/deny. Mirrors subprocess_pool._handle_control_request."""
    if tool_name in interactive:
        return False  # interactive tools always need a UI; we don't have one
    if not allowed:
        # No allow-list: --yolo-style allow-all (excluding interactive)
        return True
    return tool_name in allowed


def _extract_pending_calls(event: Dict[str, Any]) -> List[Dict[str, str]]:
    """Pull (tool_call_id, tool_name) pairs from an approval_request_message event.

    Server sometimes uses `tool_calls: [...]` (plural) and sometimes the
    deprecated `tool_call: {...}` singular. Handle both shapes.
    """
    calls: List[Dict[str, str]] = []
    plural = event.get("tool_calls")
    if isinstance(plural, list):
        for tc in plural:
            tcid = tc.get("id") or tc.get("tool_call_id")
            name = tc.get("name") or tc.get("tool_name") or ""
            if tcid:
                calls.append({"tool_call_id": tcid, "tool_name": name})
    if not calls:
        singular = event.get("tool_call")
        if isinstance(singular, dict):
            tcid = singular.get("id") or singular.get("tool_call_id")
            name = singular.get("name") or singular.get("tool_name") or ""
            if tcid:
                calls.append({"tool_call_id": tcid, "tool_name": name})
    return calls


def _get_run_state(run_id: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """Fetch a run's state. Used to disambiguate race-loss from crash-cleanup."""
    if not run_id:
        return None
    req = urllib.request.Request(
        f"{LETTA_BASE_URL}/v1/runs/{run_id}",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def classify_race_loss(run_state: Optional[Dict[str, Any]]) -> str:
    """Distinguish race-loss outcomes after Letta returns 'no tool call awaiting approval'.

    Returns:
      'letta_code_won': run is healthy/active/completed normally — original
                        path handled the approval. Responder is dormant.
      'subprocess_crashed': run is failed OR completed-with-requires_approval.
                            In both cases the tool/dispatch never completed:
                            either the subprocess died (empty-approvals bug),
                            or the streaming connection closed mid-approval
                            and the server marked the run completed while
                            stop_reason still carries the unresolved state.
                            User is in a dead-air state.
      'unknown': run state couldn't be fetched OR shape doesn't match any
                 pattern. Caller should warn-but-don't-retry.
    """
    if not run_state:
        return "unknown"
    status = run_state.get("status")
    stop_reason = run_state.get("stop_reason")
    # Healthy outcomes: active, or completed with a clean terminal reason
    if status in ("created", "running", "pending", "in_progress"):
        return "letta_code_won"
    if status == "completed" and stop_reason in ("end_turn", "max_steps", None):
        return "letta_code_won"
    # Crash signature: failed run (typically stop_reason=None or "error")
    if status == "failed":
        return "subprocess_crashed"
    # NOTE 2026-05-29 — `status == completed and stop_reason ==
    # requires_approval` used to return "subprocess_crashed", but in
    # practice this is the dominant FALSE POSITIVE: letta-code
    # auto-approves internally (--yolo / bypassPermissions), the run
    # finalizes with stop_reason=requires_approval as a transient,
    # and the subprocess advances to the next turn cleanly. The
    # responder's POST loses the race (Letta cleaned up the pending
    # approval) but the user is NOT in dead-air — they see streaming
    # responses immediately after. Emitting a synthetic "stranded"
    # error here scared users mid-good-conversation. Treat as
    # race-lost-to-letta-code (silent). True dead-air still surfaces
    # via `status == "failed"` above.
    if status == "completed" and stop_reason == "requires_approval":
        return "letta_code_won"
    return "unknown"


def _post_approval(
    agent_id: str,
    decisions: List[Dict[str, Any]],
    timeout: float = APPROVAL_RESPONDER_TIMEOUT_SECONDS,
) -> Optional[Dict[str, Any]]:
    """POST ApprovalCreate to Letta. Returns the parsed response or None on error."""
    body = {
        "messages": [
            {
                "type": "approval",
                "approvals": decisions,
            }
        ]
    }
    req = urllib.request.Request(
        f"{LETTA_BASE_URL}/v1/agents/{agent_id}/messages",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        # Wrap as a structured error so the caller can log it
        return {"_error": f"HTTP {e.code}: {err_body[:500]}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def maybe_handle_approval_request(
    handle: Any,
    event: Dict[str, Any],
    *,
    allowed_tools: Optional[Set[str]] = None,
    interactive_tools: Optional[Set[str]] = None,
    emit_callback: Any = None,
) -> bool:
    """Inspect an outbound stream event; if it's an approval_request_message,
    post auto-approvals to Letta.

    Args:
      handle: SubprocessHandle (must expose .agent_id, .conv_id, and a
              logger-compatible attribute path; we keep coupling minimal).
      event:  the raw stream event being emitted.
      allowed_tools / interactive_tools: policy sets. If allowed_tools is
              None, treat as allow-all (--yolo).
      emit_callback: optional callable(handle, synthetic_event) used to
              forward the resumed run's messages back to subscribers. If
              None, the resumed-run output is consumed silently and the
              user must re-fetch via the messages API.

    Returns True if this event was an approval_request_message and we
    issued an auto-approval; False otherwise (caller should continue
    normal stream forwarding).
    """
    # Both shapes exist depending on which layer emits the event.
    is_approval = (
        event.get("message_type") == "approval_request_message"
        or event.get("type") == "approval_request_message"
    )
    if not is_approval:
        return False

    pending = _extract_pending_calls(event)
    if not pending:
        return False

    state_key = f"{handle.agent_id}::{handle.conv_id}"
    state = _get_state(state_key)
    interactive = interactive_tools or set()

    decisions: List[Dict[str, Any]] = []
    classified: List[Dict[str, str]] = []
    with state.lock:
        for call in pending:
            tcid = call["tool_call_id"]
            if tcid in state.responded_tool_call_ids:
                continue
            tool_name = call["tool_name"]
            approve = _classify(tool_name, allowed_tools or set(), interactive)
            decisions.append({
                "type": "approval",
                "tool_call_id": tcid,
                "approve": approve,
                **(
                    {"reason": "auto-allow (--yolo non-interactive policy)"}
                    if approve
                    else {"reason": f"auto-deny: {tool_name} requires interactive UI"}
                ),
            })
            classified.append({"tool_call_id": tcid, "tool_name": tool_name, "approve": approve})
            state.responded_tool_call_ids.add(tcid)

    if not decisions:
        return False  # already handled (race with another thread)

    # Capture run_id from the event for crash-detection on race-loss.
    # ApprovalRequestMessage schema includes optional run_id; if absent the
    # diagnosis falls back to "unknown".
    run_id = event.get("run_id") or ""

    # Fire the POST in a daemon thread; do NOT block the stream emit path.
    def _run() -> None:
        result = _post_approval(handle.agent_id, decisions)
        # Best-effort logging via the standard Python logger (subprocess_pool
        # uses structlog; this module uses stdlib to avoid coupling).
        import logging
        log = logging.getLogger("pa_web.approval_responder")
        if result is None:
            log.error("approval_responder_post_failed agent=%s conv=%s decisions=%s", handle.agent_id, handle.conv_id, classified)
            return
        if "_error" in result:
            err = result["_error"]
            # Race-loss case: Letta returns 400 "No tool call is currently
            # awaiting approval". This means EITHER:
            #   - letta-code's own approval path completed it (happy case), OR
            #   - subprocess crashed from the empty-approvals bug, Letta
            #     cleaned up the dangling approval, but the original tool
            #     dispatch never completed (silent dead-air).
            # Disambiguate by inspecting the run state.
            if "No tool call is currently awaiting approval" in err:
                run_state = _get_run_state(run_id) if run_id else None
                outcome = classify_race_loss(run_state)
                if outcome == "subprocess_crashed":
                    log.error(
                        "approval_responder_subprocess_crashed agent=%s conv=%s run=%s decisions=%s "
                        "(crash-cleanup; tool dispatch did NOT complete; user is in dead-air)",
                        handle.agent_id, handle.conv_id, run_id, classified,
                    )
                    # Synthesize a visible error event so chat.js can surface it
                    # to the user instead of leaving them staring at silence.
                    if emit_callback is not None:
                        try:
                            synthetic = {
                                "type": "error",
                                "message": (
                                    "The agent's tool dispatch stranded due to a "
                                    "letta-code subprocess crash. The original action did "
                                    "NOT execute. Please retry your last request."
                                ),
                                "_synthesized_by": "approval_responder",
                                "_run_id": run_id,
                                "_decisions": classified,
                            }
                            emit_callback(handle, synthetic)
                        except Exception as e:
                            log.error("approval_responder_emit_crash_event_failed agent=%s err=%s", handle.agent_id, e)
                elif outcome == "letta_code_won":
                    log.info(
                        "approval_responder_race_loss agent=%s conv=%s decisions=%s (letta-code won — original path worked)",
                        handle.agent_id, handle.conv_id, classified,
                    )
                else:
                    log.warning(
                        "approval_responder_race_loss_unknown agent=%s conv=%s run=%s decisions=%s "
                        "(could not disambiguate race-loss outcome — run_state=%s)",
                        handle.agent_id, handle.conv_id, run_id, classified, run_state,
                    )
            else:
                log.error("approval_responder_post_error agent=%s conv=%s err=%s decisions=%s", handle.agent_id, handle.conv_id, err, classified)
            return
        log.info("approval_responder_post_ok agent=%s conv=%s decisions=%s response_messages=%d", handle.agent_id, handle.conv_id, classified, len(result.get("messages") or []))

        # If a callback was provided, forward the resumed run's messages
        # back to subscribers as synthetic stream events.
        if emit_callback is not None:
            for msg in result.get("messages") or []:
                try:
                    synthetic = {
                        "type": "message",
                        **msg,
                        "_synthesized_by": "approval_responder",
                    }
                    emit_callback(handle, synthetic)
                except Exception as e:
                    log.error("approval_responder_emit_failed agent=%s err=%s", handle.agent_id, e)

    t = threading.Thread(
        target=_run,
        name=f"approval-responder-{handle.agent_id[-12:]}",
        daemon=True,
    )
    t.start()
    return True
