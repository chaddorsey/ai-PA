# Follow-up: continuity-core approval correlation + reconnect dedup fail-open

Date: 2026-08-13
Origin: Unit 4 code review (`clients/letta-continuity-core/`, commit on `feat/msc-app-server-sole-owner`)
Status: **finding 1 RESOLVED 2026-08-13** (probe + implementation); findings 2 and 3 still open

Unit 4's `/code-review` surfaced four findings that were **not** auto-fixed because they
require a protocol/design decision that risks regressing the passing tests. The one clearly-safe
fix (reconnect double-schedule + failed-socket leak, plus wiring `maxReconnectAttempts`) WAS
applied and covered by a regression test. The rest are tracked here.

## 1. Approval fail-closed correlation is fragile (HIGH) — ✅ RESOLVED 2026-08-13

`ContinuityCore.pendingSelfTurns` was a bare counter: `send()` incremented it, and **any**
`turn_finished` decremented it. Because the server serializes turns on a shared conversation, a
*foreign* turn's `turn_finished` could zero the counter before the injector's own approval
arrived → the injector did **not** auto-`deny` → the approval-gated turn hung both surfaces.
Conversely, if the injector lost its `turn_finished` across a reconnect, the counter stayed >0
and the client would auto-`deny` a **foreign** approval (duplicate deny).

**The stated root cause was wrong.** The doc recorded that "`input` gets no synchronous run-id
echo in the captured protocol". A live probe (0.30.19, `:4577`) found `input` **does** get a
synchronous, `request_id`-correlated ack — Unit 4 simply never set a `request_id`, and the
server emits the ack *only* when one is present:

```json
{"type":"input_accepted","request_id":"REQ-A","runtime":{…},"accepted":true,"disposition":"started"}
```

It carries no `run_id`, but `disposition` plus `update_queue` is sufficient to attribute runs
exactly. Captured from a two-client concurrency probe on one conversation:

| | client A | client B |
|---|---|---|
| ack | `disposition: "started"` | `disposition: "queued"` |
| queue | — | `update_queue.queue` lists **`client_message_id: "CM-B"`** (B's own value) |
| claim | next new run = `local-run-251` | waits |
| dequeue | — | `removed: [{client_message_id:"CM-B", disposition:"dequeued"}]` → claims `local-run-252` |

Queue frames are broadcast to every subscriber, but each client only ever matches its **own**
`client_message_id`, which is what makes the attribution safe.

**Implemented** as `src/ownership.ts` (`RunOwnership`), replacing the counter:

- `send()` sets a `request_id` + `client_message_id` and registers a FIFO claim.
- `input_accepted` — `started`/`submitting` arm the claim; `queued` waits; `accepted:false` drops it.
- `update_queue.removed` — our `dequeued` arms the claim; `cancelled` drops it.
- the first sighting of a new `run_id` binds the oldest armed claim; `turn_finished` releases it.
- approvals are answered **only** for owned runs.

**Load-bearing assumption (documented in the module):** an armed claim takes the next new run id.
That is sound only because the server serializes turns per `{agent, conversation}` (Unit 1) — a
`started` ack means our run *is* the active one. If that guarantee ever changes, attribution must
be rebuilt on an explicit run id in the ack.

**Reconnect stays fail-CLOSED.** A gap may hide an ack, a dequeue, or a `turn_finished`, so
`onReconnect()` marks the tracker `degraded` while work is outstanding; an unattributable
approval is then denied (recoverable) rather than left to hang every surface (not recoverable).
Owned runs are kept across the seam because their `turn_finished` arrives on the new connection.

**Verification:** 16 unit tests covering both counter-bug directions explicitly, plus two
integration tests that exercise a real concurrent foreign turn (the gap the original review
named — the old single-injector test passed while the guarantee was weak), plus a live
end-to-end check: two real `ContinuityCore` peers injecting at once on one conversation each own
exactly one run, disjointly, neither degraded.

**Found while implementing:** `WsConnection` resolved its options by spreading the caller's
object over the defaults, so a forwarded-but-unset value (`openTimeoutMs: undefined`) overwrote
the default and produced `setTimeout(fn, undefined)` — a 0 ms bound that aborted the connect.
Every existing test passed explicit timeouts, so only a default-constructed core hit it. Fixed
(per-field `??`) with a regression test.

## 2. Reconnect dedup fails OPEN (MEDIUM) — still open

On reconnect, if `conversation_messages_list` returns `success:false` (observed live for the
`default` conv: "Agent agent-local-default not found") or times out, `fetchSnapshot()` returns
null and `liveDedup` is left null → replayed messages render a **second** time (duplicates).
A watchdog stall-restart drops all clients at once, which is exactly when the snapshot RPC is
most stressed, so this is not a rare edge.

**Fix direction:** treat a failed snapshot as a recoverable error (retry the snapshot within the
reconnect, bounded), or fail *closed* on dedup (suppress live render until a valid snapshot is
obtained) rather than silently doubling the transcript. Decide with Unit 7 acceptance (the
"no vanishing / no duplicated messages" criterion).

**⚠️ Added 2026-08-13 (Unit 5 live run) — the dedup design rests on a FALSE premise.**
`catchup.ts` documents: *"A single new message streams many deltas that all share one
`delta.id` (only `seq_id`/`event_seq` advance), so we must NOT add newly-seen live ids to the
drop-set."* Live capture on 0.30.19 shows the opposite — **every delta chunk carries a distinct
`delta.id`**: one assistant message streamed as `letta-msg-26735`, `-26736`, `-26737`, … (what
actually stays constant per message is `otid`, e.g. `provider-assistant-1-<uuid>`).

Consequence to settle in Unit 7, **before** trusting the "no duplicates" criterion: the snapshot
from `conversation_messages_list` returns *messages*, whose ids may not be the same values as the
per-chunk delta ids that `LiveDedup.admit()` tests against. If they differ, the watermark never
matches on replay and dedup silently does nothing. Verify what `conversation_messages_list`
actually returns for a streamed message, and consider keying the seam on `otid` (stable per
message) rather than `delta.id`. Also note control deltas (`stop_reason`) carry no id at all and
are now skipped by the dedup gate.

## 3. Post-reconnect boundary frames not message-keyed (LOW/PLAUSIBLE) — still open

Dedup drops a replayed `stream_delta` (message-keyed) but the accompanying `turn_finished`/
`loop_status` for an already-completed snapshot turn are not message-keyed, so they fall through
and can emit a phantom turn boundary.

**Now partly mitigated by finding 1's fix:** boundary bookkeeping is run-id-aware, so a phantom
`turn_finished` for a foreign or already-released run no longer disturbs approval state. The
*render* side (a spurious turn boundary reaching the UI) is unchanged and still needs Unit 7.

## Applied in Unit 4 (for reference)

- Reconnect no longer double-schedules; the failed socket is closed (no leak, no second
  `handleClose`); `maxReconnectAttempts` is now honored. Regression test:
  "bounded reconnect: a server that stays down ends in disconnected … no storm".
