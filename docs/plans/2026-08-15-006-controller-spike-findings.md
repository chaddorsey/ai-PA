---
title: "C1 platform spike findings — anchor viability and multiplex shape"
type: findings
status: complete
date: 2026-08-15
plan: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md
harness: clients/tools/capture-controller-spike.mjs
---

# C1 platform spike findings — anchor viability and multiplex shape

**Verdict: GO for Phase B.** Every load-bearing assumption survived contact with the platform;
several came back *stronger* than the plan assumed. No bail-out criterion triggered.

Environment: clone backend at `/private/tmp/lc-clone-c1` (agents/providers/memfs/tool-deps
copied from `~/.letta/lc-local-backend`, empty conversations), served by
`LETTA_LOCAL_BACKEND_DIR=… letta server --backend local --listen ws://127.0.0.1:4599`.
Running server self-reported `letta_code_version 0.30.20`, `protocol_version 1`
(`app_server_info`). Scratch agents `agent-local-bb3fd276…` and `agent-local-67cb834c…`
(`lmstudio/gpt-5.4-nano`), minted with `clients/tools/scratch-agent.mjs`. The live sole-owner
at :4577 was never touched; the harness refuses `:4577` without `SPIKE_ALLOW_LIVE=1`.

All captures under `docs/followups/captures/controller-spike-*.jsonl` — raw frames stamped
with elapsed-ms and the connection they arrived on.

## S1 — a second subscriber holds a detached turn alive: **YES (GO)**

`controller-spike-s1.jsonl`. A started a 25s foreground Bash execution
(`EXECUTING_CLIENT_SIDE_TOOL` observed), A's socket was terminated mid-execution, and B — a
plain second subscriber on the same runtime, no input ever sent — received the entire
remainder: tool return at ~28.6s, final assistant message, `stop_reason: end_turn`, clean
`turn_finished`. The anchor premise of the plan's Key Technical Decisions holds exactly as
hypothesized: "no other subscribed client can take over" means a second subscriber *prevents
cancellation*.

- **S1proc** (`controller-spike-s1proc.jsonl` + `-child.jsonl`): identical result with B in a
  **separate OS process** — the shape the real anchor will have. GO.
- **Promoted to a permanent gate:** `clients/letta-continuity-core/test/`
  `live.detach-hold.contract.test.ts` — opt-in (`LETTA_LIVE_WS=1`), version-gated against the
  *running* server's `app_server_info` (`letta_code_version` + `protocol_version` pins), run at
  every server version bump. Verified passing against the clone (24.4s); instrument-checked by
  running with `LETTA_LIVE_WS_EXPECT_VERSION=9.9.9` → fails on the version arm, and offline →
  skips. Cancellation-on-detach is behaviour, not shape — the vendor-type binding can never
  catch this changing, which is why the pin exists.

## S2 — late subscriber: **also holds the turn**

`controller-spike-s2.jsonl`. B subscribed only *after* A's tool execution had started; A then
dropped; B still received the completion (`end_turn`, tool output present). A late subscriber
can rescue an already-running turn. Implication for C3: the "worker-only window" on a
freshly-warmed runtime is even narrower than planned — if the worker dies mid-turn on such a
runtime, a restarted worker (or the anchor reacting to the hot-set signal) can still attach in
time as long as it beats the turn's end. The dual-subscription rule stays (it removes the race
entirely), but the exposure is a race with a wide-open rescue path, not a cliff.

## S3 — one-socket serialization + `client_message_id` recoverability: **CLEAN / RECOVERABLE**

`controller-spike-s3.jsonl`. Controller-style local queue (submit №2 only on №1's
terminality) serializes cleanly. The mapping C4's exactly-once reconciliation needs is real:

- `conversation_messages_list` returns the submitted `client_message_id` as **`otid` on the
  `user_message` row** (`otid: "cm-s3-1"`), and the same value is in the on-disk
  `messages.jsonl`. Reconciliation by `client_message_id → otid` is **buildable as designed**.
- **Null-`otid` classes observed:** `assistant_message` rows come back with `otid: null` from
  the RPC (the plan's fallback key — snapshot message id + role — applies to those, but the
  reconciliation seam only needs the *user* rows, which carry it).
- **Gotcha (first-class, journaled here):** `conversation_messages_list` **cannot resolve the
  `default` conversation alias** — it fails with `Agent agent-local-default not found` (it
  parses the composite `<name>:<agent-id>` key wrongly for bare names; on-disk directories are
  base64 of `default:<agent-id>`). Real ids (`local-conv-N`) work. **C4 rule: the controller
  reconciles only via real conversation ids from the registry**; `default` threads must be
  registered under their resolved id at `runtime_start` time (`runtime_start_response.runtime`
  echoes the id the server will use — note it echoes `default` back, so for default threads the
  transcript-reconciliation path is *unavailable* until the runtime is re-homed onto a created
  conversation. Registry design consequence: **controller-managed threads are always created
  conversations, never the `default` alias.**)
- Also pinned: after №1's `stop_reason` delta, an immediate submit is acked
  `disposition: queued` and dequeued when `turn_finished` lands ~3ms later — submitting on the
  stop_reason arm is safe (server queues, then runs), but the journal must not treat the
  previous turn's late `turn_finished` as the new turn's terminality (the harness itself hit
  this: run-ids must be terminalized exactly once).

## S4 — the Q3 loss mode, both halves: **CONFIRMED / CLOSED**

- `controller-spike-s4server.jsonl`: B's message, queued **at the server** behind A's running
  turn, was removed with `disposition: "cancelled"` the moment B's socket died — observed on
  A's connection at 1512ms. The hazard is real on this build, reconfirming the live-capture Q3
  result on the clone.
- `controller-spike-s4local.jsonl`: the identical message held in a **controller-style local
  queue** survived B's death trivially, was submitted by B's replacement after A's turn
  terminality, ran, and completed. The controller-local queue closes Q3.

## S5 — external tool orphaned by registrar death: **ERRORS CLEANLY, TURN SURVIVES**

`controller-spike-s5.jsonl`. A registered `controller_probe` via `runtime_start.external_tools`,
the model called it, and A was terminated with the call in flight while B stayed subscribed:

- **Orphan fate: no hang, no cancellation.** ~1s after the kill the server synthesized
  `tool_return_message: "External tool execution error: Listener connection closed"`
  (`status: error`) on the in-flight call, the model saw the error, and the turn continued to a
  clean `stop_reason: end_turn` + `turn_finished` — all observed on B.
- **Re-registration works:** a fresh connection re-registered the same tool via
  `runtime_start.external_tools`; the next call was routed to the new connection
  (`external_tool_call_request` on A2 only), answered, and the turn completed.
- **Shape for C3/C4:** worker reconnect re-registers all external tools (confirmed viable);
  an in-flight `external_tool_call_request` orphaned by a worker restart needs no abort — the
  server already fails it visibly into the transcript; the controller journals the turn's
  tool-error and marks the *tool call* FAILED-VISIBLE, while the turn itself reaches ordinary
  terminality. No pending `control_request` approval was observed in the orphan window (mode
  `unrestricted`; approval interplay stays conditional per the settled facts).

## S6 — two runtimes, one socket: **PER-RUNTIME CONCURRENCY, NO SHARDING**

`controller-spike-s6.jsonl` (one agent, two conversations — the R29 shape) and
`controller-spike-s6b.jsonl` (two agents). In both: two 15s foreground tool turns submitted
back-to-back on ONE socket were both acked `disposition: started` within ~9ms, executed
**fully concurrently** (tool starts ~1.4s, tool returns ~17.7–17.9s, i.e. overlapping for the
whole 15s), and terminalized independently. Per-connection `event_seq` stayed strictly
increasing throughout (76/77 enveloped frames). Q2's deferred-ack serialization is
**per-runtime, not per-socket** — there is no head-of-line blocking across runtimes.
**Decision: one worker socket (+ anchor), no sharding**, exactly the plan's default. The
bail-out criterion ("S6 per-socket HOL blocking") did not trigger.

## Incidental platform facts worth keeping (all in the captures)

- **`stop_reason` deltas are per-run, and `requires_approval` fires as a *continuation marker*
  before every client-side tool execution** even under `unrestricted` (smoke, s5, s6). The
  terminality disjunction's "ignore `requires_approval`" clause is load-bearing on every turn
  with tools, not only on approval-gated ones.
- **A turn is a chain of runs** (`local-run-N`, one per model step); terminality must
  de-duplicate per run id — a run's `turn_finished` can arrive *after* the next input's
  `queued` ack (s3), and `turn_finished` for run N follows run N's own `stop_reason` delta by
  milliseconds-to-seconds.
- **The agent-side harness blocks foreground `sleep`** ("Foreground `sleep` is blocked"), and
  the model then improvises with background tasks — long deterministic turns in tests must use
  something else (`caffeinate -t N` here).
- Assistant text deltas are chunked mid-word; completion evidence must concatenate content
  (or match `tool_return_message`, whose text arrives whole).
- `conversation_create` over WS works with `body: { agent_id, title }` and returns real ids
  (`local-conv-N`); `conversation_list` for an agent does **not** include the `default` alias
  conversation.

## Decisions recorded (consumed by C3/C4/C7)

| Question | Answer | Consequence |
|---|---|---|
| Anchor viable? (P1) | **GO** — second subscriber (separate process, even late) holds turns | C3 builds anchor+worker dual subscription as planned |
| S5 orphan fate | Tool call errors visibly; turn survives to normal terminality | C3 re-registers tools on reconnect; C4 journals tool-error, no abort needed |
| S3 mapping | `client_message_id` → `user_message.otid`, real conversation ids only | C4 reconciliation buildable; registry uses created conversations, never `default` |
| S6 sharding | Per-runtime concurrency on one socket | No sharding; one worker socket + anchor |
| S4 | Server-queue dies with socket; local queue survives | C4's controller-local durable queue is the design, confirmed load-bearing |

Scratch agents and the clone server are left running for Phase B development; they are torn
down at the C10b rehearsal teardown (tracked there).
