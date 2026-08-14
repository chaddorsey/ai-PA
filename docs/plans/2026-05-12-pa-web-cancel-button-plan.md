---
date: 2026-05-12
task: 102
title: pa-web-ui Stop button — cancel in-flight MC runs
status: pending
---

# Stop button: cancel in-flight MC runs from pa-web-ui

## Problem

When MC (or any pa-web-routed agent) enters a long-running turn — multi-step tool
chains, model thinking jags, or silently-stalled runs (#99 family) — there is
no user-facing way to interrupt it. The only options today are restarting
pa-web-ui (kills all conversations) or waiting until the subprocess times out.
Letta exposes a native cancel endpoint already; we just need to wire it through.

## Scope

In scope:
- A Stop button in pa-web-ui that cancels the current conversation's in-flight run.
- Backend route translating the click into `POST /v1/conversations/{conv_id}/cancel`.
- Subprocess handle wind-down so `in_flight` clears and the UI re-enables send.

Out of scope:
- Telegram / slackbot routes (no UI surface for cancel; revisit later).
- Per-tool-call cancellation (Letta granularity is per-run, not per-tool).
- Auto-cancel-and-retry on detected stalls (would be a separate feature; #99
  monitor already alerts on these).

## Approach

Letta's `POST /v1/conversations/{conv_id}/cancel` is Redis-backed (we have
`pa-redis`) and best-effort terminates the active run at the next checkpoint.
The pa-web-ui flow is:

1. User clicks **Stop** in the chat UI.
2. Frontend POSTs `/api/conversations/<conv_id>/cancel`.
3. Backend calls Letta's cancel endpoint, logs a `cancel_requested` lifecycle
   event, and returns `{status: "requested"}`.
4. Letta server flips the run to `cancelled`. The letta-code subprocess's
   stream closes; its reader loop emits a terminal event.
5. pa-web-ui's `SubprocessHandle.in_flight` flips back to `false`. The card
   transitions to a `cancelled` state. Send button re-enables.

## Implementation units

### Unit 1 — Backend route

**Files**: `pa-web-ui/app.py`

- Add `POST /api/conversations/<conv_id>/cancel` route.
- Validate `conv_id` with existing `_is_valid_conv_id`.
- Look up the `SubprocessHandle`; verify the calling device/session owns the
  conversation (mirror existing turn-lock ownership checks in `fork_conversation`).
- Forward to `LETTA_BASE_URL/v1/conversations/{conv_id}/cancel`.
- Call `log_lifecycle("cancel_requested", conv_id=conv_id, requested_by=...)`.
- Return `{status, conv_id, requested_at}` immediately. Do not wait for the
  subprocess to wind down — cancellation is asynchronous.

**Decision needed**: should we also auto-deny any pending approvals on the
subprocess (Option A) or leave them as orphans for manual recovery (Option B)?
**Recommendation: Option A.** "Stop" should mean stop — no half-states. Implement
by calling `handle.send_control_response_error(...)` with a synthetic deny for
each pending approval request before returning.

### Unit 2 — Subprocess handle wind-down

**Files**: `pa-web-ui/subprocess_pool.py`

- In `_reader_loop`, when the upstream stream closes with no terminal
  `stop_reason` event (the cancel-induced close pattern), emit a synthetic
  `event_type: cancelled` to subscribers and reset `handle.in_flight=False`,
  `handle.in_flight_device_id=None`.
- Add a 30-second watchdog: after a cancel is requested, if `in_flight` is
  still true at +30s, force-clear it and log a `cancel_timeout` warning. This
  protects against edge cases where Letta acks the cancel but the subprocess
  hangs on a tool waiting for I/O.
- The handle stays alive — we only invalidate runs, not subprocesses. Next
  user turn re-uses the same subprocess.

### Unit 3 — Frontend Stop button

**Files**: `pa-web-ui/static/js/chat.js`, `pa-web-ui/templates/index.html`,
`pa-web-ui/static/css/chat.css`

- Add a Stop button in the composer area, hidden by default.
- Show it when `this.inFlightRequests` is non-empty for the active conv (mirror
  existing `streaming` class logic).
- Wire onclick to POST `/api/conversations/${this.conversationId}/cancel`, then
  call the existing `AbortController.abort()` on the `/stream` fetch.
- On 2xx response, add a `cancelled` class to the streaming card so it visually
  distinguishes from a successful turn end.
- Replace-or-position decision: replace Send when in-flight, OR sit alongside
  Send disabled. **Recommendation: replace** — clearer affordance, matches
  ChatGPT/Claude.ai precedent. Send re-appears when card transitions out of
  streaming state.

### Unit 4 — Telemetry + observability

**Files**: `pa-web-ui/app.py`, `scheduler-service/scripts/bg-stall-monitor.py`

- `log_lifecycle` events: `cancel_requested`, `cancel_completed`, `cancel_timeout`.
- Update bg-stall-monitor (#99 family) to distinguish user-cancelled runs
  from silent-stall runs so it doesn't falsely page on intentional stops.
  Mechanism: read the conversation_meta or log stream for a recent
  `cancel_requested` event before flagging the run as stalled.

## Test plan

Manual end-to-end (pa-web-ui sees real letta-code, real MC):

1. **Happy path mid-stream**: send a long-running message ("draft a 1000-word
   summary of …"), click Stop ~3s in. Expect: card transitions to cancelled,
   no further tokens render, send re-enables in <5s, server-side run shows
   `status=cancelled`.
2. **Cancel mid-tool-call**: send a message that triggers an external tool
   (run_gws / Bash long-running curl). Click Stop while the tool is executing.
   Expect: tool may or may not complete server-side, but the run terminates,
   no further reasoning/tool calls happen, conversation persists what got
   through.
3. **Cancel during approval prompt**: trigger a turn that requires approval
   (any non-yolo Bash tool). When the approval card appears, click Stop.
   Expect: synthetic deny fires for each pending approval (Option A),
   subprocess returns to idle, no orphan stop_reason=requires_approval.
4. **Cancel with no in-flight run**: click Stop when nothing's running.
   Expect: button isn't visible / 4xx response.
5. **Cancel timeout edge case** (hard to trigger naturally — simulate by
   pausing letta-code subprocess with `kill -STOP`): Expect bigger-than-30s
   wait, then watchdog clears `in_flight`, UI re-enables with a warning.

## Risks and tradeoffs

- **Orphan tool results**: a tool call already executing server-side may
  complete and its result land after the run is marked cancelled. Letta's
  behavior here is to discard the result. Acceptable.
- **Approval state leakage** (Option B): if we don't auto-deny pending
  approvals, the agent could be left waiting forever. **Choosing Option A
  closes this.**
- **Concurrent cancels**: two devices viewing the same conversation could
  both click Stop. Letta cancel is idempotent; only first request does work.
  No special handling needed.
- **Subprocess subscriber leaks**: SSE subscribers on `/stream` are tied to
  the AbortController; aborting on cancel cleans them up automatically.

## Open questions

1. **Approval handling on cancel: A (auto-deny) vs B (leave orphan)?**
   Default in this plan: A. Confirm.
2. **Visual state for cancelled cards**: collapse to "Cancelled at T+X" vs
   preserve partial output? Default: preserve partial output with a
   "cancelled" badge.
3. **CLI escape hatch**: `bin/pa-cancel <conv_id>` for headless recovery?
   Default: skip for v1, revisit if pa-web ever becomes unreachable.
4. **Telegram parity** (memory tag re: agent-native parity): no UI to surface
   cancel on Telegram side. Acceptable to defer; document as known gap.

## Sequencing

Unit 1 → Unit 2 → Unit 3 → Unit 4. Units 1 + 2 can be tested with curl alone.
Unit 3 is the user-visible piece. Unit 4 closes the observability loop.

Single PR, ~1 afternoon of focused work.
