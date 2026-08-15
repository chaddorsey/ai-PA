---
status: proposed
kind: design-conversation brief
parent: docs/plans/2026-08-15-002-continuity-round4-review-findings.md
inputs:
  - docs/followups/2026-08-15-app-server-docs-vs-implementation.md   # READ FIRST
  - docs/followups/2026-08-15-continuity-ownership-live-captures.md
  - docs/followups/captures/*.jsonl
  - docs/plans/2026-08-15-004-continuity-fix-forward-closeout.md
branch: feat/msc-app-server-sole-owner
packages: clients/letta-continuity-core, clients/letta-terminal
gates: M1 Unit 5 sign-off, Unit 6 (web), Unit 7 (catch-up dedup), Unit 8 (cutover)
date: 2026-08-15
---

# Design brief: run attribution and turn completion in the continuity clients

## The decision this conversation owns

**How does a client on a shared conversation know (a) which run is answering ITS submission, and
(b) when that turn is over — and is the M1 Unit 6 bridge safely buildable on the answer?**

Everything else in root cause A follows from those two. Nothing else is in scope.

## Read this first, because the problem statement may have changed

Round 4 concluded that attribution is inferred from stream position and released on a shared idle,
that the two are incompatible in combination, and that a redesign was required. That conclusion
was reached **without reading the App Server documentation or the protocol type declarations that
ship in the package**. Both have since been read, and
`docs/followups/2026-08-15-app-server-docs-vs-implementation.md` records what changed.

The single most important item: **turn completion is documented as a per-run `stop_reason` delta**
(`delta.message_type: "stop_reason"`), explicitly excepting `stop_reason: "requires_approval"`,
which is a continuation boundary. Round 4 concluded the opposite — that no per-run completion
signal existed — and built idle-based termination to compensate. Our own capture shows the signal
discriminating correctly on the exact shape we called undecidable:

```
run=local-run-574   stop_reason="requires_approval"    ← continuation
run=local-run-575   stop_reason="end_turn"             ← completion
```

**So this conversation must begin by establishing what problem is actually left.** It is a
legitimate and welcome outcome to conclude that no redesign is needed and that the fix is "adopt
the documented signals." Do not preserve the redesign framing out of momentum.

> **But do not over-correct either.** That commentary has itself been adversarially reviewed, and
> the review tempered its headline: the `stop_reason` delta replaces the **termination edge**, not
> the attribution model. It fires for peers' turns too, it arrives on a run we did not start, and
> it is **ephemeral across a reconnect seam** (no `delta.id`, absent from snapshot and replay). The
> corrected reading is *"use it live, keep idle for seams, add `loop_error.is_terminal` for faults,
> keep attribution for peers"*. Read the **CORRECTED AFTER REVIEW** blocks in the commentary before
> relying on any of its claims — several of my first-draft inferences did not survive.

## Phase 0 — establish the premises (do not skip; do not trust this brief)

Four premises. Each is either confirmed, corrected, or killed **with evidence**, before any design
work. Where a live capture settles it, take the capture: the harness is
`clients/tools/capture-ownership.mjs`, the server is up on :4577 (0.30.20), and
`clients/tools/scratch-agent.mjs` mints and deletes a disposable agent.

| # | Premise | How to settle it | If TRUE |
|---|---------|------------------|---------|
| **P1** | Turn completion = per-run `stop_reason` delta, except `requires_approval`. | Capture: a tool-using turn and a plain turn; confirm every run carries one and that `requires_approval` always precedes a continuation. **Also confirm what an ERRORED turn emits** — it may emit none. | The live-path termination edge is solved by adoption. **Not** the attribution model, and **not** the seam (see below). |
| **P2** | A parked approval reports `WAITING_ON_APPROVAL`, not `WAITING_ON_INPUT`. | Needs a runtime that gates tools — the M1 runtime is `unrestricted` and cannot produce one (see below). | Finding A6 is retired. **Currently unsettled: A6 CANNOT be retired without this capture** — the review showed the alternative explanation fails. |
| **P3** | `sync` (with `recover_approvals`) replays state a reconnecting client missed — including a queue transition it never saw. | Capture: reproduce `queue-replay2`, then send `sync` after reconnect and diff. | **Expect NO.** Transitions are emitted *on mutation*; the replay is a *snapshot* and was observed carrying `removed: []`. Take the capture anyway, but do not plan around a yes. |
| **P4** | `idempotency_key` is a sufficient dedup key across a reconnect seam. | Capture: compare `idempotency_key` for the same logical event across a replay. | Unit 7 is a small change. Note it dedups *events per connection*; the cross-seam *transcript* question may still need the message-id watermark. |
| **P5** | **ANSWERED — detaching the last subscribed client cancels the active turn.** | Already captured (`captures/q5-detach-cancels.jsonl`) and documented: *"If no other subscribed client can take over an active runtime, App Server requests cancellation of its active turn."* | **This is a fact the design must absorb, not a question.** It means "leave and let the turn finish" is not available to a single-surface client — which is most of M1 terminal usage. |

**P2 has a precondition that is itself a decision.** Producing a gated approval requires changing
the runtime's permission mode away from `unrestricted`, and `live.contract.test.ts` currently
*pins* `unrestricted` as an M1 precondition. Do not flip it casually — that is a live,
constant-on runtime and every attached surface sees the change. If P2 cannot be settled without
that, say so and leave A1/A6 recorded as **conditional on permission mode**, which is where the
capture document already puts them.

## Phase 1 — the design questions, given verified premises

Answer in this order. Later answers depend on earlier ones.

**Q1. Attribution: inferred, or carried?**
Can a client identify its own run from the frames, or must it infer from stream position? Relevant
facts already established: `request_id` correlation is **connection-local and may be reused across
clients** (integration-patterns); our core happens to mint nonce-prefixed ids, which is a property
we have rather than one the protocol guarantees; `active_run_ids` was empty on all but one of 34
frames in a live capture. Decide whether attribution is a solved problem, a bounded-risk
inference, or genuinely undecidable.

**Q2. Termination: what does a one-shot wait for?**
Given P1, specify exactly. The review established that this is a **disjunction, not a replacement**:

- the per-run `stop_reason` delta on the live path (excluding `requires_approval`, which is a
  continuation boundary — and which fires even when **no approval is pending**, observed in
  `unrestricted` mode with no `control_request`);
- **plus** `loop_error.is_terminal`, because an errored turn may emit no `stop_reason` delta at all;
- **plus** loop-status idle retained as the **seam-safe fallback** — the `stop_reason` delta carries
  no `delta.id`, so it is absent from both the snapshot and the reconnect replay, and a client that
  disconnects across it would otherwise wait forever;
- **filtered by `subagent_id`**, or a subagent finishing mid-turn is mistaken for the turn ending.

Also decide which of the **13** stop reasons are terminal (`StopReasons` models 3 — commentary C3).

**Q3. The reconnect seam: what may a client still believe?**
A4 established that a queued message cancelled while its socket was away is not discoverable by
inspection — the declaration says transitions "cannot be inferred from absence". Given P3's
answer, decide what a client may keep across a seam: an armed claim, a queued claim, nothing.
"Resubmit on reconnect" is a legitimate answer, but it is a **product** decision (a duplicate turn
on a shared conversation) and must be named as one, not smuggled in as a retry.

**Q4. Is the Unit 6 bridge safely buildable — and what shape is even permitted?**
This is the milestone-level call, and one option has been eliminated since the brief was drafted:

> **A browser cannot connect to the App Server directly.** Origin-bearing upgrades are rejected
> unless auth is configured, and *"the standard browser WebSocket API cannot set the required
> `Authorization` header, so authenticated browser applications need a trusted backend or WebSocket
> proxy."* A browser `WebSocket` always sends `Origin`. **A bridge or proxy is mandated by the
> transport rules, not chosen on design grounds.**

So Q4 is no longer "bridge or direct?" but "what does the mandated bridge own?". Established facts
to design against: two inputs on one socket are **both acked `started`** (the server defers the
second ack rather than queueing), so the `queued → dequeued → armed` chain `ownership.ts` is built
around is **never exercised on a single socket**; the docs tell controllers to hold their own
per-runtime turn lock and queue locally; `request_id` is connection-local and may be reused across
clients. Decide whether the bridge holds one core per consumer or one core with a real local queue.

**Q4b. What does P5 do to the surfaces?** If detaching the last client cancels the running turn,
then a bridge that drops to zero consumers kills in-flight work, and a terminal user who walks away
loses their turn. Decide whether any surface must hold a keep-alive subscription, and say plainly
whether that is a product requirement or an accepted limitation.

**Q5. What do the doubles have to be able to falsify?**
Round 4's deepest finding was that the test doubles encoded the same wrong model as the client, so
the suite certified agreement between two copies of a mistake. Whatever model is chosen, state how
its doubles are held to the server — the standing recommendation is a compile-time conformance
check against `@letta-ai/letta-code/app-server-protocol` (types-only, no runtime, browser-safe;
commentary Part D).

## What "done" looks like

A design document that contains, at minimum:

1. **A premise ledger** — P1-P4, each marked confirmed / corrected / killed / unsettled, with the
   evidence for each. Unsettled is acceptable; unsettled-and-unmarked is not.
2. **The chosen model for attribution and termination**, stated as rules a reader can implement
   without inferring intent — including what the client does when a signal is absent.
3. **A disposition for each root-cause-A finding** (A1-A8): retired, reduced to a bug, or carried
   into the new model. A8 is already killed as written by a live capture; A6 is probably retired
   by P2. Do not silently drop any.
4. **The Unit 6 verdict** with its reasoning.
5. **The falsifiability plan** — what mutation, contract test, or compile-time check binds each new
   rule. A rule without one is how three rounds shipped green.
6. **What was NOT decided**, and what would settle it.

## Out of scope

- The fix-forward work already landed (tiers 0-3, commits `bd11ee30`, `121e0d25`, `f01435dd`).
  It is done and mutation-bound; do not reopen it. If a design decision *contradicts* one of those
  fixes, say so explicitly rather than quietly reverting it.
- The sanitizer, the process-level harness, the mutation instrument. All sound.
- Unit 7 and Unit 8 mechanics, beyond noting what this decision forces on them.
- The App Server deployment situation (`scripts/restore-letta-app-server.py` is a stopgap; the
  real plist is Unit 8's call). Operational, not design.

## Anti-patterns, earned the hard way

This project has shipped a comparable defect set **three times with a green suite**, and today
added a fourth failure mode. Guard specifically against:

1. **Agreeing with a plausible model.** The failure here has never been sloppiness; it has been
   coherent reasoning from a premise nobody checked. Prefer a capture or a declaration to an
   argument, every time.
2. **Treating "settled facts" as unverifiable.** The fix-forward goal told the implementer not to
   re-derive settled facts. That was read as licence not to verify them, and produced a shipped
   inversion of the `loop_error` / `error_message` id rules. Settled means "do not waste time
   re-deriving" — it never means "do not check against the spec."
3. **Reasoning from our own code.** `protocol.ts` is a hand-maintained transcription of a
   published type surface. It is evidence of what we believed, not of what the server does.
4. **Accepting a conclusion because a review round produced it.** Round 4 was thorough, used 11
   reviewers, and reached at least one confidently wrong conclusion (no per-run completion signal)
   because every reviewer shared the same unread specification.

## Note on scale

This is a decision brief, not a research project. If Phase 0 shows P1 and P3 both hold, the honest
output may be short: adopt the documented signals, retire most of root cause A, and Unit 6 becomes
buildable. Do not manufacture a redesign to justify the conversation. Equally, if Q4 comes back
"not safely buildable", that is a milestone-level finding and should be stated plainly rather than
softened into follow-up work.

**Unit 5's checkbox does not get ticked by this conversation either** — it is gated on the outcome,
and the round-4 review's answer ("do not tick it") stands until this brief's questions are answered.
