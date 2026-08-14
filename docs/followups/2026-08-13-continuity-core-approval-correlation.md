# Follow-up: continuity-core approval correlation + reconnect dedup fail-open

Date: 2026-08-13
Origin: Unit 4 code review (`clients/letta-continuity-core/`, commit on `feat/msc-app-server-sole-owner`)
Status: **findings 1 and 3 RESOLVED 2026-08-13**; finding 2 is now **ANSWERED but unfixed** (the
fix belongs to M1 Unit 7). See the remediation plan
`docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md`.

> **⚠️ Finding 1's stated root cause below was itself wrong.** It claimed `input` gets no
> synchronous correlating response. It does — `input_accepted`, which the client simply never
> requested because it sent no `request_id`. More importantly, the whole *premise* of finding 1
> was wrong: attribution is not what makes the approval policy safe, because the server broadcasts
> approvals to every subscriber and de-duplicates responses itself. The correlation work still
> stands (it drives origin labelling), but it is no longer safety-critical. The real contract is in
> `docs/plans/2026-08-13-approval-contract-findings.md`.

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
- ~~approvals are answered **only** for owned runs~~ — **SUPERSEDED.** Approvals are answered
  unconditionally; see the header note. `attribute()` now serves origin labelling only.

**Load-bearing assumption (documented in the module):** an armed claim takes the next new run id.
That is sound only because the server serializes turns per `{agent, conversation}` (Unit 1) — a
`started` ack means our run *is* the active one. If that guarantee ever changes, attribution must
be rebuilt on an explicit run id in the ack.

**Reconnect.** ~~fail-CLOSED on `degraded`~~ — **SUPERSEDED**, and it was wrong twice over: it
tested `seenRuns` *before* the degraded fallback, so the very case it existed for (an ack lost in
the gap) returned "not ours". With approvals decoupled, `degraded` is now a diagnostic only,
armed claims are demoted at the seam rather than carried (across a gap the "next new run" may
easily be a peer's), and claims expire on observed stream inactivity so nothing latches forever.

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

**⚠️ ANSWERED 2026-08-13 — the dedup is not merely fail-open, it is entirely non-functional.**
A single probe capturing one turn's live delta ids and then listing the same conversation:

```
LIVE delta ids:  letta-msg-27370, letta-msg-27371, letta-msg-27372  … (14)
SNAPSHOT ids:    ui-msg-7457, ui-msg-7456:assistant:1, ui-msg-7456:reasoning:0
OVERLAP:         0
```

`LiveDedup.admit()` compares `letta-msg-*` against a set of `ui-msg-*`. Disjoint namespaces, zero
overlap, so it never matches and dedup does nothing on any real reconnect. The tests that appeared
to prove otherwise passed only because the mock emitted one delta per message with a hand-matched
snapshot id; they have been retired and replaced with honest, narrower claims, and the live gate
now asserts the mismatch so the day it changes it is noticed. Note also that user messages persist
our `client_message_id` as `otid` but carry **no `run_id`**, so an otid→run mapping is not
available from the snapshot either.

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
