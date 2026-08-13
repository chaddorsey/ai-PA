# Follow-up: continuity-core approval correlation + reconnect dedup fail-open

Date: 2026-08-13
Origin: Unit 4 code review (`clients/letta-continuity-core/`, commit on `feat/msc-app-server-sole-owner`)
Status: open — needs a design decision, not a mechanical fix (deferred out of Unit 4)

Unit 4's `/code-review` surfaced four findings that were **not** auto-fixed because they
require a protocol/design decision that risks regressing the passing tests. The one clearly-safe
fix (reconnect double-schedule + failed-socket leak, plus wiring `maxReconnectAttempts`) WAS
applied and covered by a regression test. The rest are tracked here.

## 1. Approval fail-closed correlation is fragile (HIGH)

`ContinuityCore.pendingSelfTurns` is a bare counter: `send()` increments it, and **any**
`turn_finished` decrements it (`src/index.ts` routeFrame). Because the server serializes turns
on a shared conversation, a *foreign* turn's `turn_finished` can zero the counter before the
injector's own approval arrives → the injector does **not** auto-`deny` → the approval-gated
turn hangs both surfaces (the exact stall the policy exists to prevent). Conversely, if the
injector loses its `turn_finished` across a reconnect, the counter stays >0 and the client will
auto-`deny` a **foreign** approval (violating "observers never respond" → duplicate deny).

**Root cause:** the client cannot currently distinguish its own `run_id` from a foreign one.
`input` gets no synchronous run-id echo in the captured protocol.

**Fix direction (needs a probe):** determine whether `input` returns/echoes a correlating id
(e.g. `client_message_id` → run mapping, seen in `update_queue`) so the core can track the set
of `run_id`s it initiated and gate approvals + boundary bookkeeping on that set instead of a
counter. Probe the App Server for the echo; if none exists, decide the M1 tradeoff explicitly
(prefer over-deny/duplicate-deny — still fail-closed — over hang). Land with Unit 5/6 approval
scenarios where a real foreign turn can be exercised (the current single-injector approval unit
test never exercises a concurrent foreign turn, so it passes while the guarantee is weak).

## 2. Reconnect dedup fails OPEN (MEDIUM)

On reconnect, if `conversation_messages_list` returns `success:false` (observed live for the
`default` conv: "Agent agent-local-default not found") or times out, `fetchSnapshot()` returns
null and `liveDedup` is left null → replayed messages render a **second** time (duplicates).
A watchdog stall-restart drops all clients at once, which is exactly when the snapshot RPC is
most stressed, so this is not a rare edge.

**Fix direction:** treat a failed snapshot as a recoverable error (retry the snapshot within the
reconnect, bounded), or fail *closed* on dedup (suppress live render until a valid snapshot is
obtained) rather than silently doubling the transcript. Decide with Unit 7 acceptance (the
"no vanishing / no duplicated messages" criterion).

## 3. Post-reconnect boundary frames not message-keyed (LOW/PLAUSIBLE)

Dedup drops a replayed `stream_delta` (message-keyed) but the accompanying `turn_finished`/
`loop_status` for an already-completed snapshot turn are not message-keyed, so they fall through
and can emit a phantom turn boundary (and spuriously touch `pendingSelfTurns`). Tie the fix to
finding 1 (run-id-aware boundary bookkeeping) once correlation exists.

## Applied in Unit 4 (for reference)

- Reconnect no longer double-schedules; the failed socket is closed (no leak, no second
  `handleClose`); `maxReconnectAttempts` is now honored. Regression test:
  "bounded reconnect: a server that stays down ends in disconnected … no storm".
