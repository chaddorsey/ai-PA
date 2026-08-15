---
status: reviewed-and-corrected
review: Fable adversarial review, 2026-08-15. Verdict — "trustworthy enough to base a design
  conversation on", with three required corrections (A4's mechanism, A2's dismissal of A6, A1's
  inference) and two material omissions (D2.1, D2.2). All are applied inline and marked
  **CORRECTED AFTER REVIEW** / **TEMPERED AFTER REVIEW**; nothing was silently rewritten.
audience: adversarial reviewer (Fable) — please challenge the readings, not just the conclusions
branch: feat/msc-app-server-sole-owner
packages: clients/letta-continuity-core, clients/letta-terminal, clients/tools
sources:
  - https://docs.letta.com/platform/app-server
  - https://docs.letta.com/platform/app-server/quickstart
  - https://docs.letta.com/platform/app-server/protocol-lifecycle
  - https://docs.letta.com/platform/app-server/integration-patterns
  - https://docs.letta.com/platform/app-server/external-tools
  - /opt/homebrew/lib/node_modules/@letta-ai/letta-code/dist/types/types/protocol_v2.d.ts
  - /opt/homebrew/lib/node_modules/@letta-ai/letta-code/dist/types/types/queue-update-protocol.d.ts
  - /opt/homebrew/lib/node_modules/@letta-ai/letta-code/node_modules/@letta-ai/letta-client/resources/agents/messages.d.ts
  - /opt/homebrew/lib/node_modules/@letta-ai/letta-code/node_modules/@letta-ai/letta-client/resources/runs/runs.d.ts
date: 2026-08-15
---

# The App Server protocol as documented, versus what we built

## Why this document exists

The M1 continuity clients (`clients/letta-continuity-core`, `clients/letta-terminal`) were built,
reviewed four times, and remediated **without anyone reading the App Server documentation or the
protocol type declarations that ship inside the package**. Every "settled fact" in the round-4
review and its fix-forward goal was derived from live packet captures and from reading our own
code. That method is not worthless — it found real defects — but it is *inference about a
specification that was written down all along*, and it has now been shown to produce confidently
wrong conclusions.

Two things made the gap invisible for longer than it should have been:

1. A half-finished `npm install -g @letta-ai/letta-code@0.30.20` had left the on-disk package
   without `letta.js`, `package.json` or `docs/`. An early grep for `loop_error` in `dist/` found
   nothing and was read as "the strings are not on disk". They were; the package was broken. (It
   is repaired; see `scripts/restore-letta-app-server.py` for that incident.)
2. The fix-forward goal said *"settled facts the implementer must not re-derive"*. That was
   intended to stop wasteful re-litigation. It was instead treated as licence not to **verify**,
   which is a different thing.

**What the reviewer should do with this document:** the readings below are mine and several
overturn conclusions that three review rounds accepted. Attack the readings. Where I claim the
docs say something, check the quoted string. Where I claim our code does something, check the
file and line. I have been wrong about this protocol in exactly this way once already today.

**Confidence key:** ✅ documented + verified against our code · ⚠️ documented, our behaviour
differs, impact argued · ❓ documented but not yet confirmed against a live server.

---

## Part A — Findings that INVALIDATE prior conclusions

These are the high-value ones. Each contradicts something the round-4 review concluded or the
codebase asserts in a comment.

### A1 ⚠️ Turn completion is a per-run `stop_reason` DELTA. We invented idle-based termination.

**Documented** (protocol-lifecycle, "Stream & Completion"):

> "A turn is complete when a `stream_delta` carries `delta.message_type: "stop_reason"`, except
> for `stop_reason: "requires_approval"`." … "Approval acts as a continuation boundary."

**What we do:** `clients/letta-terminal/src/main.ts` `runOneShot()` terminates on
`loop_status === WAITING_ON_INPUT` — a *runtime-wide* signal — guarded by a `sawOurTurn` flag
inferred from run attribution. `clients/letta-continuity-core/src/stream.ts:117` sets
`stopReason` **only** from `turn_finished` frames; the `stop_reason` delta is passed through as an
ordinary delta and never surfaced as completion.

**Why this matters more than any other item here.** The round-4 review's central design question
was *"Is the turn over?"*, and it concluded:

> "A `turn_finished` for *our* run would fix them — but the settled fact is that our send's run
> never closes, so this needs a server-side turn-completion signal that today does not exist."

That conclusion appears to be **false**. The documented completion signal is not `turn_finished`;
it is the `stop_reason` delta, which is per-run (`run_id` on the delta) and arrives on the run that
is actually ending. Our own live captures show it on every turn — including the tool-using
multi-run shape, where `local-run-574` and `local-run-575` each carry their own `stop_reason`
delta. We were watching it go past and rendering it as nothing.

**The evidence is already in our own captures.** Re-reading `captures/q1-approval-park.jsonl` —
the tool-using turn recorded today — for `stop_reason` deltas:

```
run=local-run-574   stop_reason="requires_approval"   has_id=false
run=local-run-575   stop_reason="end_turn"            has_id=false
```

That is the documented rule mapping *exactly* onto the multi-run shape we have been calling
undecidable:

- `local-run-574` (our send's run, the one that "never closes") ends `requires_approval` — the
  documented **continuation boundary**, i.e. "not finished, more is coming";
- `local-run-575` (the continuation carrying the reply) ends `end_turn` — the documented
  **completion**.

So the wire distinguished "this run is a continuation" from "this turn is done", per run, on every
turn, throughout — and the client rendered neither. The round-4 settled fact *"the run our send
starts is never closed"* is true about `turn_finished` and **misleading**, because a different
frame carried the answer.

Note also `has_id=false`: the `stop_reason` delta carries no `delta.id`, which is why it is in
`CONTROL_DELTA_TYPES` — the one piece of this we already had right.

A wrinkle for the reviewer: run-574 reported `requires_approval` even though **no
`control_request` was ever sent** (the runtime is `unrestricted` and auto-ran the tool). So
`requires_approval` marks a tool-call continuation boundary, not necessarily a human approval.
Any implementation keying on it must not assume a pending approval exists.

> **TEMPERED AFTER REVIEW.** The facts above all survived checking. My *inference* did not, and the
> corrected version is materially less exciting:
>
> - **It replaces the termination EDGE, not the attribution model.** The `stop_reason` delta fires
>   for every turn on the conversation, including a peer's. Distinguishing ours still needs the
>   `input_accepted` → disposition → dequeue → run-adoption machinery that exists today. Part F
>   question 1 has a deflationary answer: not much of the attribution model exists only to
>   compensate for this.
> - **The completing delta belongs to a run we do not own** — `end_turn` arrives on run-575 while
>   our send started run-574. That is the *identical* objection round 4 raised against
>   `turn_finished`. What the delta genuinely adds is the `requires_approval` marker on 574, which
>   lets a client *chain* runs — and that chaining is sound only because the server serialises
>   turns per conversation. It is inference from serialisation, not a wire-level link. Nothing on
>   run-575 names run-574.
> - **The signal is ephemeral and dies at the seam.** It carries no `delta.id`, so it can never
>   appear in the `conversation_messages_list` snapshot, and the reconnect replay contains only
>   status frames (verified in `q3-queue-replay.jsonl`). A client that disconnects between emission
>   and receipt never sees it. **Loop-status idle IS in the replay** — so idle-based termination
>   must be RETAINED as the seam-safe fallback, and "we invented idle-based termination" should
>   read "we used only the fallback and missed the precise live signal".
> - **An errored turn may never emit it.** `main.ts` records that no idle follows an error on one
>   server path, and `LoopErrorMessage` carries its own `stop_reason` plus `is_terminal`. A rule of
>   "stop_reason delta ≠ requires_approval" alone plausibly hangs on the commonest real fault. The
>   rule must be a disjunction with `loop_error.is_terminal`.
> - **Subagents could forge it.** `StreamDeltaMessage` has an optional `subagent_id`
>   (`protocol_v2.d.ts:437`) that neither `protocol.ts` nor `stream.ts` reads. If subagent streams
>   are forwarded, a subagent finishing mid-turn delivers an `end_turn` that a naive implementation
>   takes as completion. Any adoption must filter on `subagent_id`.
>
> **Corrected claim:** the wire distinguishes continuation from completion per run, and we ignored
> it. Use it to chain runs and terminate promptly on the live path; keep loop-status idle for
> seams; add `loop_error.is_terminal` for faults; keep attribution for peers. Round 4's sentence is
> still falsified — a per-run signal exists — but the discovery does not collapse the redesign.

Part of root cause A is still **self-inflicted**: we inferred turn completion from a shared idle
without knowing a per-run signal existed. But "part", not "a large part".

**Reviewer, please attack this specifically.** It is the single highest-impact claim in this
document, and it is the one I most want a second opinion on before a redesign is planned around it.
Particularly: does `requires_approval` as a continuation boundary interact correctly with the
multi-run tool shape, and is the `stop_reason` delta reliably scoped to the run we care about?

### A2 ⚠️ `WAITING_ON_APPROVAL` is a distinct loop status. Finding A6's premise looks wrong.

**Documented** (`protocol_v2.d.ts:312`):

```ts
export type LoopStatus = "SENDING_API_REQUEST" | "WAITING_FOR_API_RESPONSE"
  | "RETRYING_API_REQUEST" | "PROCESSING_API_RESPONSE" | "EXECUTING_CLIENT_SIDE_TOOL"
  | "EXECUTING_COMMAND" | "WAITING_ON_APPROVAL" | "WAITING_ON_INPUT";
```

**Round-4 finding A6 said:** "the runtime reports idle *while a turn is parked on an approval*. M1
auto-denies every approval, so any client-side-tool reply exits 0 with the reply missing."

There is a dedicated `WAITING_ON_APPROVAL` status. A parked turn has its own state and is not
reported as `WAITING_ON_INPUT`. A6's premise is therefore **suspect**, but —

> **CORRECTED AFTER REVIEW.** I originally guessed that A6's "exit 0, reply absent" observation was
> "fully explained by A1". **My own capture contradicts that.** In `q1-approval-park.jsonl` the
> statuses between run-574 and run-575 run
> `EXECUTING_CLIENT_SIDE_TOOL → SENDING_API_REQUEST → WAITING_FOR_API_RESPONSE →
> PROCESSING_API_RESPONSE` — with **no `WAITING_ON_INPUT` between the runs at all**. No shared idle
> fires mid-reply in the captured shape, so the alternative explanation I offered does not work.
>
> A6 was recorded as verified by running the binary against an auto-**denied** approval. No capture
> on disk reproduces that shape: our runtime is `unrestricted`, which auto-**ran** the tool and
> never sent a `control_request`. **A6 cannot be retired on this evidence.** It needs one capture of
> a genuinely parked or denied approval, which requires a permission mode we have pinned as an M1
> precondition — see P2 in the design brief.

Our `LoopStatuses` constant declares only `waitingOnInput`, `sendingApiRequest`,
`executingClientSideTool` — three of the eight. We never see the other five as anything but
opaque strings.

### A3 ✅ "Treat `loop_error` and `error_message` deltas as failures" is documented. B1 was in the docs.

**Documented** (protocol-lifecycle, "Stream & Completion"): "Treat `loop_error` and
`error_message` deltas as failures."

B1 — the P0 that "no static reviewer caught", found by running the binary against a 404-model
agent — is one sentence of the documentation. This is the clearest single illustration of the cost
of the method: a P0 defect was discovered empirically, at the cost of a live capture and a review
round, and it was written down.

The fix has landed (`render.ts` renders both, exit code goes nonzero) and is bound by mutations
46/47. But note the id-rule inversion I shipped and then corrected in `58492ddf` — I got
`loop_error` and `error_message` backwards because I was working from a capture summary rather
than from `protocol_v2.d.ts`. Same root cause, one layer down.

### A4 ✅ Queue transitions "cannot be inferred from absence" — this CONFIRMS the live Q3 finding and makes it worse

**Documented** (`protocol_v2.d.ts:349-357`):

```ts
/**
 * Full queue snapshot plus exact dequeue/cancellation transitions. Emitted on
 * mutation; transitions are ordered and cannot be inferred from absence.
 */
export interface QueueUpdateMessage extends RuntimeEnvelope {
    type: "update_queue";
    queue: QueueMessage[];
    removed: QueueRemovalTransition[];   // disposition: "dequeued" | "cancelled"
}
```

My live capture showed that when a peer's socket drops while its message is queued, the message is
**cancelled**, and the reconnecting client sees `queue: [] removed: []`.

> **CORRECTED AFTER REVIEW.** I originally wrote that the transition is delivered "only to the
> dying socket". That is **not supported by the capture and is probably false**: the `cancelled`
> frame is logged at 869ms, ~3ms *after* peer B terminated at ~866ms, so a live socket — the
> surviving peer A — received it. My capture format carries no per-socket labels, so it cannot
> actually attribute a line to a socket. The defensible rule is narrower: **the transition is not
> replayed to a client that subscribes later.** A peer that stays attached throughout does see it.
> A re-capture with per-socket labels would settle it in minutes and has not been done.
>
> **Also corrected:** I presented the cancellation as an undocumented discovery. It is documented.
> Protocol-lifecycle states: *"Disconnect cleanup removes that connection's pending approvals, tool
> callbacks, terminals, and queued input."* The behaviour is specified; only our ignorance of it
> was novel.

The declaration still says transitions **cannot be inferred from absence**, and the reconnecting
client still sees nothing. But the hazard is smaller and better-founded than I first wrote:

> **A client that reconnects with an outstanding queued message is not told what happened to it.**
> It does not need to be told, because the fate is deterministic *a priori* from the documented
> cleanup rule: a queued, not-yet-started message whose submitting connection drops is cancelled.
> The design question is therefore not "how do we recover the unknowable" but **"does the client
> assume cancellation and resubmit, or drop the claim?"** — and resubmission is a product decision
> about duplicate turns on a shared conversation.

This is still a real input to the design conversation. It is no longer the dramatic one.

---

## Part B — Documented mechanisms we reimplemented or ignored

Each of these is a place where we built something the protocol already provides. None is
necessarily wrong to have built, but all were built without knowing the alternative existed.

### B1 ⚠️ `sync` — the documented state-replay and gap-recovery command. We have no implementation.

**Documented** (protocol-lifecycle, "Sync"; integration-patterns, "Missed Event Recovery"):

```json
{ "type": "sync", "request_id": "sync-1",
  "runtime": {...}, "recover_approvals": false, "force_device_status": true }
```

> "track `event_seq` independently for each connection when present, deduplicate events carrying
> an `idempotency_key`, and request `sync` when a sequence gap" indicates missed updates.

**What we do:** `ContinuityCore.reconnect()` calls `fetchSnapshot()`, which issues
`conversation_messages_list` and builds a `LiveDedup` over message ids (`catchup.ts`). `sync`
appears nowhere in `clients/` (verified by grep).

> **CORRECTED AFTER REVIEW.** I wrote that "`sync` is the documented answer to the exact problem
> `catchup.ts` was written to solve". **That is wrong.** `catchup.ts` solves *transcript* dedup
> across a seam; `sync` replays *runtime state*. The distinction is visible in my own capture: the
> reconnect replay carried device_status, loop_status, queue and subagent_state — **zero stream
> deltas, zero messages**. The `conversation_messages_list` snapshot remains the only transcript
> source, so it is not redundant and B3 below is wrong to hint that it might be.
>
> My "single most valuable thing to test next" (does `sync` replay a missed queue transition) also
> has a predictable answer: transitions are emitted *on mutation*, the replay is a *snapshot*, and
> the observed replay carried `removed: []`. Expect **no**. Still worth one capture, but it is not
> the linchpin I called it.
>
> **And a correction that cuts the other way:** `recover_approvals` **defaults to `true` on
> `runtime_start`** (`protocol_v2.d.ts:631`, and the docs' runtime-state table says "Defaults to
> `true`"). So approval recovery on reconnect is *already happening* without our asking — which
> bears directly on what `answeredApprovals` and mutations 1/19c are actually protecting against.

What survives: `sync` exists, we do not implement it, and it is the documented way to force a state
replay and to recover approvals on an established connection without reconnecting.

### B2 ⚠️ `idempotency_key` is the documented dedup mechanism. We ignore it and dedup on message ids.

**Documented** (protocol-lifecycle, "Event Ordering & Idempotency"): "`idempotency_key`:
Deduplicates replayed or retried events." Every broadcast carries one — our own mock emits
`idempotency_key: idem(type, seq)` because the captures showed it, and *nothing in the client
reads it*.

`catchup.ts` carries this comment:

> "⚠️ UNVERIFIED PREMISE (Unit 5 live capture, 2026-08-13). This was written believing that all
> deltas of one message share a single `delta.id`. They do NOT…"

An unverified premise was documented as a risk and left in place, while the field designed for the
job sat unused in every frame. Unit 7 ("catch-up dedup") is scoped to revisit this; it should
start from `idempotency_key`.

### B3 ⚠️ `runtime_start` auto-replays state. We may be double-fetching.

**Documented**: "A successful `runtime_start` automatically replays the subscribed runtime's
current state after its response." And for recovery: "After transport loss, open a new WebSocket
and send `runtime_start` again to restore subscriptions."

Our reconnect does `runtime_start` **and then** `conversation_messages_list`.

> **CORRECTED AFTER REVIEW — this item pointed the wrong way.** I suggested the snapshot RPC "may
> be redundant". It is not: the automatic replay carries **no transcript** (verified in my own
> capture — status frames only). `conversation_messages_list` is the sole transcript source and
> must stay.
>
> What is genuinely worth having here is `runtime_start.wait_for_replay`
> (`protocol_v2.d.ts:635`), which resolves the hello only *after* the initial replay is emitted.
> That bears directly on the replay↔snapshot race that the `liveDedup` window (mutation 19b)
> exists to absorb — a documented way to close the window rather than defend against it.

### B4 ❓ `abort_message` exists; we cannot cancel a turn.

**Documented**: `abort_message` / `abort_message_response`, replacing deprecated `cancel_run`.

The terminal has no way to stop a running turn — Ctrl-C detaches the client and leaves the turn
running, which is documented behaviour in our own `--help` and was a deliberate M1 choice. Worth
recording that the protocol supports the other choice.

### B5 ⚠️ `client_tool_allowlist` is a stronger, more direct control than `exclude_interactive_tools`.

**Documented** (protocol-lifecycle, "input: create_message"): `client_tool_allowlist` "Narrows
locally executed tools; empty array disables them."

`buildInput` sets `exclude_interactive_tools: true` and carries a long comment about it being
"Leg 1 of the M1 approval policy". An **empty `client_tool_allowlist` disables local tool
execution entirely** — which is a much closer fit to what M1 actually wants on a shared
conversation, and would make the approval path unreachable rather than merely auto-denied.

Worth a design decision, not a silent change: it alters what the agent can do, not just what the
client displays.

---

## Part C — Statements in our code that the documentation contradicts

### C1 ⚠️ "The App Server takes no client authentication" — false.

`clients/letta-continuity-core/src/trust.ts:4` states:

> "The App Server takes no client authentication. It is safe only because it binds 127.0.0.1"

and `trust.ts:44` puts the same claim in a user-facing error message; `index.ts:188` repeats it.

**Documented**: non-loopback listeners support `--ws-auth capability-token` and
`--ws-auth signed-bearer-token`, with clients sending `Authorization: Bearer …` on upgrade. HTTP
requests with an `Origin` header are rejected unless auth is configured.

The loopback default is still correct and the trust boundary is still the right default. But the
*reason* we give is wrong, and it is wrong in the direction that forecloses an option: a remote
Unit 6 deployment is a supported configuration with a documented auth mode, not the unprotected
exposure our error message describes. The message should say loopback is the default trust
boundary **and** that remote use requires configuring `--ws-auth` on the server.

### C2 ⚠️ `request_id` is connection-local and may be reused across clients.

**Documented** (integration-patterns): request correlation "is scoped to individual connections
rather than globally unique… different clients may independently reuse the same `request_id`."

Our `ownership.ts` correlates claims by `request_id` from `input_accepted`. On a single connection
that is sound. For the **Unit 6 bridge** — N browser consumers multiplexed onto one core and one
socket — this is a constraint worth stating explicitly in the design: correlation is safe only
because the core mints its own nonce-prefixed ids (`nextRequestId("rpc", clientNonce)`). That is a
property we happen to have, not one the protocol guarantees.

### C3 ⚠️ We model 3 of 13 stop reasons, and B4 terminates on only one of them.

**Documented** (`runs.d.ts:109`):

```
'end_turn' | 'error' | 'llm_api_error' | 'invalid_llm_response' | 'invalid_tool_call'
| 'max_steps' | 'max_tokens_exceeded' | 'no_tool_call' | 'tool_rule' | 'cancelled'
| 'insufficient_credits' | 'requires_approval' | 'context_window_overflow_in_system_prompt'
```

Our `StopReasons` has `end_turn`, `requires_approval`, `error`.

The renderer is fine (it shows "turn ended: X" for anything that is not `end_turn`). **B4 is not**:
the one-shot terminates early only on `stop_reason === "error"`, so a turn ending in
`max_steps`, `max_tokens_exceeded`, `llm_api_error`, `cancelled`, or
`context_window_overflow_in_system_prompt` still waits out the full `--timeout`. That is the same
defect B4 fixed, surviving on five other paths.

This is a concrete, low-risk follow-up: terminate on any terminal stop reason, i.e. everything
except `requires_approval` (which the docs explicitly call a continuation boundary).

### C4 ✅ Our `submitting` disposition note is CORRECT — worth recording as a win for the method.

`InputDispositions` comments that `submitting` "is absent from the server's published typedef but
is emitted by the bundle." The declaration confirms it exactly:

```ts
disposition?: "started" | "queued";
```

An empirical observation, correctly recorded as diverging from the typedef, and still true. This
is what the capture method is *good* at, and the reviewer should weigh it against Part A.

---

## Part D — Bind to the vendor types instead of transcribing them

`@letta-ai/letta-code` publishes a **types-only** entry point (`package.json` `exports`):

```json
"./app-server-protocol": { "types": "./dist/types/types/app-server-protocol.d.ts" }
```

which re-exports `protocol_v2`, `app-server-info`, `conversation-fork-protocol` and
`queue-update-protocol`. Types-only means **no runtime import and no `ws` dependency** — it is
safe for the browser client (Unit 6) and costs nothing at runtime.

Our `protocol.ts` is a hand-maintained transcription of this. Round 4's finding C1 was that the
*test double* was an unversioned second copy of the wire vocabulary; the deeper version is that
**`protocol.ts` itself is one**, and `double-fidelity.test.ts` only proves the double agrees with
our copy — not that our copy agrees with the server.

**Recommendation, for the reviewer to challenge:** add a compile-time conformance check that our
interfaces are assignable to the vendor's (`protocol_v2.TurnFinishedMessage`,
`QueueUpdateMessage`, `InputAcceptedResponseMessage`, `LoopStatus`, `StopReasonType`, …), in the
same spirit as the existing `SessionCoreConformance` assertion in `session.ts`. That converts a
whole class of drift from "caught by a live gate, if someone runs it" into "does not compile".

The risk to weigh: the version on disk is not necessarily the version running (that is now checked
— see the new live drift test), and pinning to vendor types couples our build to an install. A
reviewer should say whether that coupling is acceptable or whether a generated-and-committed
snapshot is better.

---

## Part D2 — What this document MISSED, found by adversarial review

Added after a Fable review of the first draft. These were not in the original at all. The first is
the most consequential thing on this page.

### D2.1 ⚠️ Detaching the last client CANCELS the running turn — and we ship the opposite claim

**Documented** (protocol-lifecycle, verified verbatim):

> "Disconnect cleanup removes that connection's pending approvals, tool callbacks, terminals, and
> queued input. **If no other subscribed client can take over an active runtime, App Server
> requests cancellation of its active turn.**"

**What we shipped:** `main.ts` printed `— detached (the conversation continues on the server)` and
`cli.ts`'s `--help` said Ctrl-C leaves "the conversation and any running turn continue on the
server". In ordinary terminal use, our client **is** the only subscribed client.

**Verified live** (`captures/q5-detach-cancels.jsonl`): a turn executing `sleep 25` via the Bash
tool, confirmed running (`EXECUTING_CLIENT_SIDE_TOOL`, `active_run_ids: ["local-run-8"]`), socket
dropped, reconnected 6 seconds later — runtime `WAITING_ON_INPUT`, `active_run_ids: []`, no further
output over 20s. The turn was dead with ~19s of its tool left to run.

A first attempt at this capture was **inconclusive and is worth recording as method**: a
"count to 60" prompt finished in 2.4s, so the socket was dropped after `turn_finished` and nothing
was cancelled. The scenario had to force a genuinely long turn before it proved anything.

This is a user-facing correctness bug, not a design question: the client told the operator the
opposite of what was happening at the moment it printed. Both strings are corrected.

It also deflates A4 — the queue cancellation I treated as a discovery is the same documented
cleanup rule, applied to queued input rather than an active turn.

### D2.2 ⚠️ A browser cannot connect to the App Server at all without a proxy — a hard Unit 6 constraint

**Documented:** "HTTP requests carrying an `Origin` header are rejected" unless auth is configured,
and **"The standard browser WebSocket API cannot set the required `Authorization` header, so
authenticated browser applications need a trusted backend or WebSocket proxy."**

A browser `WebSocket` always sends `Origin`. So the "browser talks directly to loopback" option
that E1's transport re-typing was partly meant to enable **does not exist**. A bridge or proxy is
mandated by the vendor's transport rules, not merely preferred on design grounds.

This should be settled *before* Unit 6 architecture is chosen, and it makes C1's correction sharper:
remote access is supported, but never directly from page JavaScript.

### D2.3 ❓ Other declarations we do not read

- **`stream_delta.subagent_id`** (`protocol_v2.d.ts:437`) — absent from our `StreamDeltaFrame`. See
  the A1 caveat: unfiltered, a subagent's completion could be mistaken for the turn's.
- **`recover_approvals` defaults to `true` on `runtime_start`** (`protocol_v2.d.ts:631`).
- **`remove_queue_item`** (`protocol_v2.d.ts:2190`) — clients can withdraw a queued item, which is
  directly relevant to any queue-claim lifecycle in the redesign.
- **`abort_message` takes an optional `run_id`**, and `abort_message_response.aborted` distinguishes
  "interrupted something" from a no-op.
- **`LoopState.active_run_ids` is plural**; `frameRunId` reads only `[0]`. The vendor's comment on
  `executing_tool_call_ids` — that it is authoritative and self-healing, unlike pairing
  start/end lifecycle events which are "unrecoverable if a frame is lost" — is design guidance
  aimed squarely at our seam problem.
- **`@letta-ai/letta-code/app-server-client`** ships a *runtime* client with `browser`, `import`
  and `require` entries. Whatever the round-4 SDK rejection covered, Part D should weigh this when
  deciding bind-to-vendor-types versus a committed snapshot.
- **Unexplained doubled frames** in single-socket captures (q1: two identical
  `EXECUTING_CLIENT_SIDE_TOOL` at 1354ms). Unexplained, and it is the same ambiguity that makes
  A4's socket attribution undecidable from these files.

## Part E — What holds up

Not everything needs revisiting, and the reviewer should not spend time here:

- **The sanitizer.** Nothing in the protocol docs bears on it; it is a terminal-safety concern and
  it is sound (200k-input live fuzz, per-member coverage since Tier 2).
- **`event_seq` handling.** Documented as "monotonically increasing per connection" — exactly what
  `StreamAssembler` implements, including the reset-per-connection rule that mutation 19a binds.
- **Loopback as the default trust boundary.** Correct posture; only the stated reason is wrong (C1).
- **`is_terminal` on `LoopErrorMessage`** is a genuine per-run signal we do not read. (An earlier
  draft also listed "the multi-run tool shape — our captures match the documented model" here.
  That was self-contradictory: A1 says we render that shape's completion signal as nothing. The
  *captures* match the documented model; the *client* does not.)
- **`disposition: "dequeued" | "cancelled"`** matches `QueueRemovalTransition` exactly.
- **The instrument** (mutation harness, process-level spawn tests, double-fidelity gate). None of
  this document's findings suggest the tooling is wrong — they suggest it was pointed at the wrong
  reference. The gate that compares the double to `protocol.ts` is still worth having; it just
  needs `protocol.ts` compared to the vendor (Part D).

---

## Part F — What I want the reviewer to decide or challenge

1. **Is A1 right?** Does terminating on the per-run `stop_reason` delta (except
   `requires_approval`) actually resolve the "is the turn over?" half of root cause A? If yes, how
   much of the attribution model exists only to compensate for not having it?
2. **Does `sync` (B1) solve the unknowable-cancellation hazard (A4)?** This is testable in one
   capture against the live server and would materially shrink the design conversation.
3. **Is A2 enough to retire finding A6**, or does the "RAN binary: exit 0, reply absent"
   observation still need its own explanation?
4. **Part D coupling:** bind to vendor types at compile time, or generate-and-commit a snapshot?
5. **Given A1–A4, is the ownership/attribution redesign still a redesign** — or is it now a much
   smaller change (adopt `stop_reason` + `sync` + `idempotency_key`, keep the rest)?
6. **What else in this repo was built by inference from captures** where a specification exists?
   The continuity clients are unlikely to be the only place.

## Appendix — method note

Docs were read on 2026-08-15 from the five URLs in the frontmatter. Type declarations were read
from the installed 0.30.20 package after repairing a broken install; the running server is now
also 0.30.20 (previously 0.30.19, drifted — see the live-captures document). Every claim about our
code was checked against the file at the commit on `feat/msc-app-server-sole-owner` as of this
writing. Claims marked ❓ have not been confirmed against a running server and should not be
treated as established.
