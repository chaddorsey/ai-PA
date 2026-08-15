# @ai-pa/letta-continuity-core

Raw-WS client-core for the **sole-owner Letta App Server** (Multi-Surface Agent Continuity, Milestone 1 — Unit 4). Both M1 clients (terminal, web) import this one module; it speaks the App Server's full `/ws` protocol on a **single ordered connection**.

- Plan: `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md` (M1 Unit 4)
- Remediation: `docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md`
- Protocol (empirical, verified against `letta` 0.30.19 **and** 0.30.20, `ws://127.0.0.1:4577/ws`):
  `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md` §C/§E, plus
  `docs/plans/2026-08-13-approval-contract-findings.md` for the approval and attribution contract

## Why raw-WS-primary

Unit 1 proved a single `/ws` connection receives **all** broadcasts for a subscribed `{agent, conversation}` — own turns, foreign turns, and `update_subagent_state` — each frame carrying a per-connection monotonic `event_seq`. There is **no second observer connection and no cross-stream merge**. The `@letta-ai/letta-agent-sdk` covers only runtime/session/stream (not conversation CRUD, approvals, or subagent state), so the core speaks raw WS directly. **No SDK dependency.**

## Modules

| File | Responsibility |
|------|----------------|
| `src/protocol.ts` | **The sole home of every frame string + shape.** Builders, parsers, strict `validateInboundFrame` drift guards, extractors, the exported wire vocabulary (`DeltaMessageTypes`, `StopReasons`, `LoopStatuses`), and `assertServerIdentity`. Nothing framing-related lives elsewhere in either package's `src/`. |
| `src/ws.ts` | One loopback WS connection: hello handshake, `request_id`-keyed RPC, **every wait bounded** (open/hello/RPC timeouts). No retry loop. |
| `src/stream.ts` | One ordered event stream keyed by per-connection `event_seq`; turn boundaries from `turn_finished`/`loop_status`. Renders own **and foreign** turns identically. |
| `src/catchup.ts` | Reconnect snapshot (`conversation_messages_list`) + **message-id watermark dedup** (`delta.id`, never `event_seq` — it resets per connection). |
| `src/connection.ts` | `connected` / `reconnecting` / `disconnected` state machine with a **bounded** reconnect budget. |
| `src/pointer.ts` | Reads the durable `{agent, conversation}` state file (a real UUID — never `default`, never recency). |
| `src/ownership.ts` | Attributes runs to this client (`attribute() → mine \| foreign \| unknown`) for origin labelling, and bounds claim/run state. **Not** safety-critical — see the approval note below. |
| `src/index.ts` | `ContinuityCore` facade wiring it all together, incl. the approval responder and reconnect→catch-up. |

## Approval policy (M1)

Two legs, in order of preference:

1. **Prevent.** Every `input` sets `exclude_interactive_tools: true`, so the server drops
   `AskUserQuestion`-class tools from the turn — the class that inherently blocks on a human
   answer cannot be selected on a shared conversation. Permission-gated approvals depend on the
   runtime's permission mode, which the client cannot set, so it is *verified* instead by the live
   gate (`docs/runbooks/continuity-conversation-preconditions.md`).
2. **Answer.** An approval arrives as a top-level **`control_request`** frame
   (`request_id = "perm-" + tool_call_id`); the response rides an `input` with
   `payload.kind: "approval_response"` and `decision: {behavior: "deny", message}`. Deny-only is
   enforced by the *signature* of `buildApprovalDeny`, which takes no decision parameter.

**Answering does not consult run ownership**, and that is deliberate: the server broadcasts each
approval to every subscriber and settles the race itself, so a duplicate response is harmless
while nobody answering hangs every surface. An earlier design gated on attribution to avoid
duplicates — a problem that does not exist — and could have produced the only outcome that
matters. Every approval and every auto-deny is surfaced to consumers, because a deny nobody sees
is indistinguishable from the agent declining to use a tool.

## Server-version assertion

The `app_server_info` RPC reports `letta_code_version`, `protocol_version`, and a capability map,
and answers *before* `runtime_start` — so `assertServerIdentity` runs as a pre-hello gate on every
connect and reconnect. A missing required capability always throws; a version or protocol mismatch
follows `versionPolicy` (`refuse` throws, `warn` warns); a server too old to answer the RPC at all
degrades to a warning, since refusing would lock out older builds.

`VALIDATED_SERVER_VERSIONS` lists the versions the live contract test has actually passed against.
`test/version-pin.test.ts` fails the **ordinary** suite when the installed `letta` binary leaves
that set, so an upgrade cannot land unnoticed: clone the backend, run `npm run check:live`
against the candidate, then add the version deliberately.

## Contract test = the upgrade gate

`test/protocol.contract.test.ts` round-trips a canonical fixture of every used frame and **fails loudly** on drift (renamed/removed field). On a `letta` server upgrade, updating the fixtures is the deliberate, reviewed step that unblocks it — silent mis-parse is impossible.

## Commands

```bash
npm install
npm run typecheck   # tsc --noEmit
npm run lint        # biome check
npm test            # vitest — deterministic, offline
npm run check       # all three
npm run check:live  # opt-in gate against a REAL App Server (see below)
```

Run `check:live` against a **candidate server on a clone backend**, never a second writer on the
live one:

```bash
LETTA_LIVE_WS=1 LETTA_LIVE_WS_URL=ws://127.0.0.1:4599/ws \
  LETTA_LIVE_WS_EXPECT_VERSION=0.30.20 npm run check:live
```

`LETTA_LIVE_WS_AGENT` chooses which agent to gate against; it defaults to the low-stakes docs
agent. It is an input rather than a constant because a gate that hard-codes an agent cannot tell
"the protocol drifted" from "that one agent's model is down" — which is exactly what happened on
2026-08-14, when the docs agent's model group started answering 404 at the provider and three of
the four checks failed with nothing wrong at the protocol layer. `../tools/scratch-agent.mjs`
mints a disposable agent to be that input, and deletes it again.

The default suite is fully offline against an in-process mock App Server
(`test/helpers/mockServer.ts`). The mock reproduces the server's **command guards** — a
guard-failing frame is dropped silently, exactly as the real server drops it — because a double
that answers any shape rubber-stamps a malformed builder, which is how `conversation_create`
once shipped with an envelope the server ignored. It also produces the shapes a healthy server
cannot be asked for on cue: an ORPHAN run (`toolUse` — the captured tool-using reply, whose first
run never emits `turn_finished`), a gracefully closed socket whose close handshake is deferred
(`closeAllConnections` + `holdCloseHandshakes`), and an injected write fault
(`FaultyWsConnection`). Those three exist because without them the properties that matter most —
approval send/record ordering, one-shot termination, continuation-run attribution — could not be
disproved by any test.

## Every fix carries a mutation

`../tools/mutations.mjs` holds one entry per fix in this package and in `letta-terminal`: a revert
of exactly that component, plus the test that must fail when it is applied.

```bash
node ../tools/mutate.mjs          # apply each, run the owning suite, expect a failure, restore
node ../tools/mutate.mjs --list
```

This exists because three remediation rounds shipped with a green suite: tests had been written
from the fix rather than from the property, and "verified" by reverting whole commits, which proves
a commit is load-bearing and nothing about any component. A fix whose mutation leaves the suite
green is not done — it is either untested or unnecessary, and both are findings.

### Known gap

Reconnect catch-up dedup is **not** functional against a real server, and the tests say so rather
than hiding it. Live delta ids (`letta-msg-*`) and `conversation_messages_list` ids (`ui-msg-*`)
are disjoint namespaces with zero overlap, so `LiveDedup` never matches. The live gate asserts
that mismatch so the day it changes, it is noticed. The fix belongs to M1 Unit 7 — see
`docs/followups/2026-08-13-continuity-core-approval-correlation.md` finding #2.
