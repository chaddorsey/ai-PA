# Final review findings — continuity remediation (`bf46d004`…`cc270edb`)

Date: 2026-08-13
Branch: `feat/msc-app-server-sole-owner`
Scope reviewed: `clients/letta-continuity-core/`, `clients/letta-terminal/` — base `e5079323`
Team: 11 agents (4 always-on, learnings, agent-native, security, reliability, api-contract,
kieran-typescript, adversarial)

**Verdict: NOT ready. M1 Unit 5 must stay open.**

> **STATUS 2026-08-13 — all eight P1 items below are FIXED** (`741e638d`…`7d91749a`, see
> `git log`). Every fix carries a test that was **verified to fail against the unfixed code** —
> reverting each fix individually was confirmed to break its test, and the specific failure is
> recorded per item. Suites after: **145 core + 4 skipped, 54 terminal, 4 live**, plus a live
> terminal round-trip. The P2/P3 sections below are **not** addressed and remain open.
>
> **STATUS 2026-08-14 — the P2/P3 set below is now FIXED too** (`69ec98db`…`9ffe6fa9`). Suites:
> **151 core + 4 skipped, 58 terminal, 4 live**, plus a live terminal round-trip. Each fix again
> carries a test verified to fail against the unfixed code — notably the origin bound, which the
> reviewer had proven passed with BOTH eviction loops disabled and now fails at "expected 2000 to
> be less than or equal to 512".
>
> **One earlier claim narrowed by this work.** ownership.ts was described as "hardening against"
> the inverse dequeue ordering. Driving that ordering end-to-end for the first time showed what
> the hardening actually buys: the claim is still `queued` when the run is first seen, so nothing
> binds and attribution degrades to `unknown`. It does **not** still attribute correctly. That is
> acceptable only because the live server was captured emitting the dequeue first, and there is
> now a test saying so rather than leaving the stronger reading in place.
>
> **STATUS 2026-08-14 — the agent-native gaps and the Unit 6 nonce blocker are FIXED too**
> (`8d4fe081`, `de07d2a3`). Suites: **155 core + 4 skipped, 64 terminal, 4 live**.
> `send(text, {origin})` returns a correlation handle and `runOrigin()` reports the submitting
> origin, so a one-core/N-browser bridge can attribute each run — settled *before* Unit 6 rather
> than during it. The terminal gained one-shot (`--message`, or any non-TTY stdin), meaningful
> exit codes, an stdout/stderr split, `--json` NDJSON, and `conversations list|create
> [--write-pointer]`, which closes Unit 8's seed loop.
>
> **New protocol fact, captured live — matters for M1 Unit 7.** A multi-step agentic reply spans
> SEVERAL runs, and the run our send starts never emits `turn_finished`:
>
> ```
> turn_start    local-run-320  owns=true     ← our send
> loop_status   EXECUTING_CLIENT_SIDE_TOOL
> turn_start    local-run-321  owns=false    ← a NEW run
> loop_status   WAITING_ON_INPUT
> turn_finished local-run-321  end_turn      ← only 321 ever finishes
> ```
>
> Consequences: (a) any wait keyed on "our run finished" hangs on every tool-using reply — the
> one-shot path now terminates on `WAITING_ON_INPUT` instead; (b) such a run is **never released
> from ownership**, so the idle reaper added earlier is what stops attribution degrading
> permanently, not a nicety; (c) continuation runs are genuinely unattributable, which is why the
> terminal renders them `agent?` rather than claiming a peer sent them.

The remediation fixed the defect the previous review named. It also left, and in three places
introduced, a comparable set — including a **new "nobody answers" path in the very approval code
that was rewritten to eliminate that outcome**. Baseline was green throughout (134/4 skipped, 51,
4 live), which is the point: none of the findings below is visible from a passing suite.

Every P1 below was reproduced — by me, by the reporting agent against the committed mock, or by
reading the letta-code 0.30.20 bundle. Findings that could not be reproduced were dropped.

---

## P1 — the approval path is still broken, differently

The three compound. Together they mean approvals are noisy in the common case and can hang every
surface in the uncommon one.

### A1. A deny lost in a socket drop is never retried → turn parks forever

`index.ts:317-328`. `answeredApprovals.add(id)` runs **before** `this.ws.send(...)`, with no
try/catch, and the set is never cleared on reconnect. So the mark means "we intended to answer",
not "the server received an answer".

Sequence: `control_request` arrives → the watchdog kills the runtime → `add(id)` → `send()` either
throws (socket CLOSING) or succeeds into a dead socket → reconnect → the server re-broadcasts the
still-pending request → `answeredApprovals.has(id)` is true → **skipped, and `emitApproval` is
skipped too, so the user is not even told**. Nobody answers. `ownership.onTurnFinished` explicitly
ignores `requires_approval`, so the run is never released either. On a single-surface deployment
the conversation is hung until the client restarts.

This is the exact inverse of the ordering fixed 130 lines above in the same file, where `send()`
carries the comment *"Register the claim only once the frame is actually on the wire. Registering
first leaves a claim for a send that threw."* The reasoning was applied to the claim path (failure
mode: a mislabelled turn) and not to the approval path (failure mode: a hang).

**Fix:** send first, record second, wrap in try/catch; clear `answeredApprovals` at the top of
`reconnect()`. Server-side at-most-once makes re-answering strictly the safe direction.

### A2. The validator rejects the ack the real server sends on every approval

`protocol.ts:576-579` requires a `disposition` string whenever `accepted` is true. Confirmed
against the bundle — `dist/types/types/protocol_v2.d.ts:550` declares `disposition?: "started" |
"queued"` (**optional**), and the approval path calls `acknowledgeInput(handled, …)` with no third
argument. `acknowledgeInput(true)` on the teleport path likewise.

So a healthy server trips the drift detector: every approval this client answers emits
`ProtocolError: input_accepted: accepted ack missing 'disposition'` to the user, **and the ack is
dropped** (`ws.ts` returns after `failPending` + `emitError`). The drift gate that `protocol.ts`
exists to provide is poisoned — the operator is trained to see a ProtocolError on every approval
against a correct server, so a real rename arrives as noise.

`protocol.contract.test.ts:398` pins the wrong rule as the contract. The fixture corpus has no
approval-ack shape at all.

**Fix:** make `disposition` optional in the validator to match the server typedef; add the missing
fixture; invert that contract test. Note the bundle's union is `"started" | "queued"` only —
`"submitting"` appears in our types and in `ownership.ts:119` but not in the server's typedef.

### A3. The benign race loser is reported as a hard error

`index.ts:290-296` turns any `input_accepted{accepted:false}` into
`Error("input rejected by the server: …")`. On a shared conversation — M1's entire target state —
the server settles each approval race by answering the loser
`"Approval request is no longer pending"`. So the **normal** path prints a red
`— input rejected by the server: …` on N-1 surfaces per approval, indistinguishable from a real
rejection of the user's own turn.

**Fix:** track the `appr-*` request ids and route their non-accepted acks to `onWarn` / an
`onApproval` outcome, not `emitError`.

---

## P1 — connection lifecycle

### B1. A drop during catch-up resets the reconnect budget → unbounded reconnect storm

`index.ts:391-393`. `fetchSnapshot` swallows **every** error including a socket-close rejection and
returns `null`; `reconnect()` then calls `connectionState.connected()` unconditionally, which sets
`attempts = 0`.

If the socket dies while the catch-up RPC is in flight, the core marks itself **connected on a dead
socket and rearms its own budget**. Backoff never grows past the base delay; the attempt cap is
never reached. Reproduced against the committed mock: 68 connect-and-die cycles in 2 s with
`maxReconnectAttempts: 2`, ending in state `connected` with zero live connections. A second agent
independently measured 29 `runtime_start` frames against a budget of 3.

This defeats what Unit 10 claimed to deliver, in precisely the crash-loop scenario it was written
for. The existing "bounded reconnect … no storm" test only covers a server that is fully **down**,
which never reaches this path. The user meanwhile sees "connected" and types into a dead socket.

**Fix:** capture a connection epoch before `await ws.connect()`; after each await, bail unless
`this.ws === ws && !this.stopped`. Have `fetchSnapshot` rethrow on close-class errors so the
attempt counts against the budget.

### B2. A superseded socket's late close tears down the healthy one → double transcript

`index.ts:276` registers `ws.onClose(() => this.handleClose())` — identity-free — and
`handleClose` guards on `this.ws?.isClosedByUs`, i.e. the **current** connection, not the one that
closed. The `ws` package waits up to 30 s for a close handshake, so a failed attempt's socket can
emit `close` long after `this.ws` has been replaced. The guard then consults the healthy
connection, sees `closedByUs === false`, and schedules a reconnect against a live socket —
which replaces `this.ws` **without closing the old one**. Both remain wired to `routeFrame`: every
delta ingests twice on two independent `event_seq` sequences, and the transcript double-prints.
Each subsequent stale close repeats the leak.

**Fix:** `ws.onClose(() => this.handleClose(ws))`; return unless `source === this.ws`. Close the
outgoing connection in `reconnect()` before assigning the new one.

### B3. A throwing consumer listener kills the process

None of the four emit loops isolates listener exceptions — `ws.ts:328`, `index.ts:432`,
`index.ts:436`, `stream.ts:132`. All run synchronously inside the socket's `message` handler, so a
throw becomes an `uncaughtException`; the terminal installs no handler. Proven by probe.

The terminal's listeners all end in `process.stdout.write`, so `letta-continuity | head -40`
**kills the client on EPIPE** rather than degrading. `session.ts:130` already documents this hazard
for the readline path; the frame path was left open.

**Fix:** try/catch each listener invocation, reporting through `onWarn`.

---

## P1 — security

### C1. ReDoS in the sanitizer: relayed content blocks the event loop

`sanitize.ts:42-46`. The four string-sequence patterns use an unrestricted lazy payload
`[\s\S]*?` before a required ST terminator. Many introducers with no terminator restart the
forward scan at each position — O(n²). `maxLength` is applied at line 88, **after** the regex pass,
so it protects nothing here.

Measured on this machine, against the real module:

| hostile input | time |
|---|---|
| 16 KB of `ESC ]` | 53 ms |
| 31 KB | 202 ms |
| 63 KB | 834 ms |
| **125 KB** | **3,336 ms** |
| 63 KB of `ESC P` (DCS) | 825 ms |
| 1 MB of plain `a` | 32 ms |

Clean 4×-input/16×-time scaling. The agent relays third-party content — a mail body, a Slack
message, a fetched page — so this is attacker-reachable by sending the user an email. During the
stall the client reads no frames, **answers no `control_request`**, and accepts no input: exactly
the "looks hung while the conversation continues elsewhere" failure the module docstring says the
file exists to prevent. Cost is additive across a chunked stream.

**Fix:** bound the input before any pass, and replace the lazy payload with a bounded negated class
that cannot backtrack past a terminator. The reporting agent validated a concrete pattern at
1,000,000 introducers → 0.53 ms with all existing test expectations byte-identical.

### C2. The loopback boundary is enforced one package away from the socket

`assertLoopbackUrl` lives in `letta-terminal/src/cli.ts` and is unreachable from the core.
`ContinuityCore.newConnection()` passes `config.url` straight to `new WebSocket(...)` with no
check. The core is the published seam and M1 Unit 6's web client is its next consumer, which will
have nothing signalling that a check is required. Loopback *is* this design's trust boundary — the
App Server takes no client auth.

**Fix:** move the check into the core, gated by an explicit `allowRemote` option; have the CLI
import it rather than own it.

*(No bypass was found in the check itself — 23 URL forms probed, including userinfo confusion,
IDNA, decimal/hex encodings, and IPv4-mapped IPv6. It is correct; it is just in the wrong place.)*

---

## P2 — stream integrity, dead code, and standards

- **`event_seq` poisoning** (`stream.ts:81`): validation checks only `typeof === "number"`. One
  frame with `MAX_SAFE_INTEGER` latches the watermark past every future frame — connected,
  accepting input, rendering nothing, reporting nothing, with no reset outside a reconnect. Proven.
  Fix: require `Number.isSafeInteger(seq) && seq >= 0`.
- **`reapIdle` is never called** (`ownership.ts:249`) — flagged independently by six reviewers.
  The only `src/` occurrence is its own definition. One lost `input_accepted` or `turn_finished`
  therefore strands a claim forever, `hasOutstanding()` stays true for the process lifetime, the
  `positivelyForeign` branch is permanently disabled, and **every subsequent peer turn attributes
  as "unknown"** — which `ownsRun` maps to false, so a solo user's own turns start rendering as
  `peer ›`. Unit 10 claimed to "bound the growing state"; `MAX_REMEMBERED_RUNS` and
  `MAX_TRACKED_ORIGINS` are genuinely wired, the claim-expiry path is not.
- **`liveDedup` is stale across reconnect** (`index.ts:392`): assigned only after a successful
  snapshot, never nulled, so each reconnect filters live frames against the *previous* watermark
  for up to `rpcTimeoutMs`. Latent only because the id namespaces are disjoint — which is exactly
  what M1 Unit 7 will change.
- **`start()` failure leaks a socket and a zombie reconnect loop**: `openConnection` has no
  try/catch, and `connect()` cleans up only on the open-timeout path. The terminal masks it by
  calling `stop()`; the core offers no such guarantee to Unit 6.
- **`answeredApprovals` and `consumedMessageIds` are uncapped** on a client designed to run for
  days, while every neighbouring collection got a cap in this same diff.
- **Wire literals still live outside `protocol.ts`** — `"requires_approval"` has two definitions
  (`protocol.ts:89` and `ownership.ts:50`), plus bare `"started"`/`"submitting"`/`"dequeued"`. The
  trailing `| string` on the disposition unions means a typo compiles. Unit 11's "sole home of wire
  strings *again*" is not true, and `CLAUDE.md` states the invariant as fact.
- **`UntrustedText` enforces nothing**: `string & { readonly __untrusted?: unique symbol }` — the
  brand is **optional**, so it is a bidirectional alias for `string`. `untrusted()` has zero call
  sites, and `RenderEvent.text` is plain `string`, so the brand is erased at the first hop. The
  web client it was written to protect will receive relayed third-party content typed `string`.
- **`MAX_TRACKED_ORIGINS = 512` is declared twice** (`session.ts:25`, `render.ts:44`), with a
  comment acknowledging they must match and nothing enforcing it.
- **Invisible-character gaps**: U+061C (Arabic Letter Mark, sibling of the U+200F that *is*
  stripped), the U+E0000–E007F tag block, soft hyphen, Hangul fillers, variation selectors all
  survive. Escape-sequence stripping itself had **no bypass** across 42 adversarial payloads
  including reassembly attacks.

---

## Test integrity — why none of this was caught

Four findings are about the suite's ability to disprove the client. These matter most, because
they are why a green baseline meant so little.

1. **`expect(true).toBe(true)`** — `core.integration.test.ts:511`. The two-client approval test
   builds the exact settled-race scenario, waits for both surfaces to answer, then asserts a
   tautology. Adding error listeners to it surfaces both A2 and A3 immediately.
2. **"origin tracking is bounded" is vacuous** — `session.test.ts:285`. Proven: with **both**
   eviction loops disabled the terminal suite still passed 25/25. It asserts only that a string
   appears, which holds whether or not eviction happens.
3. **The queued→armed→owned path has zero end-to-end coverage** — the mock's `drain()` emits the
   dequeue notice *after* the whole turn, the inverse of the live capture, so the ordering the
   client will actually meet is never exercised through the wire. The `inputDisposition` knob
   exists and no test uses it. Driving it shows a queued send attributes as `"unknown"` with a
   claim dangling forever.
4. **`sanitize.test.ts` is binary to git** — raw `0x00` and `0x7f` on line 54. `git diff` renders
   it `Bin 0 -> 3594 bytes`. The terminal's security-boundary test cannot be read in any diff,
   including the one handed to these eleven reviewers. The file's own header claims it uses `\u`
   escapes precisely so this cannot happen.

Also unused: the mock's `messagesSuccess`/`messagesError` knobs, leaving both catch-up degradation
branches untested.

---

## Agent-native gaps (pre-existing, out of Unit 5's charter but relevant to Unit 8)

- **No one-shot mode.** Sending a turn is reachable only through interactive readline, and with
  piped stdin readline closes ~1 ms after the line, so the process exits before the reply arrives.
  Reproduced: `printf '…' | letta-continuity` delivers the turn and prints no answer. **The e2e
  command in the closeout doc uses `sleep 25`, which is a workaround for this, not a test
  convenience** — I had encoded the workaround as the verification procedure without noticing.
- **Exit codes are always 0**, including after reconnect-budget exhaustion and server-side input
  rejection. A supervisor cannot tell a clean detach from a dead session.
- Diagnostics (errors, approval notices, connection state) are written to **stdout**, mixed into
  the transcript, while `onWarn` alone goes to stderr.
- `readPointer`/`writePointer` are not exported and the `exports` map blocks deep import, so
  Unit 8's seed step has no supported way to write the pointer it is told to write.
- `ContinuityCore.send()` mints ids from a single construction-time `clientNonce` and returns
  nothing, so **one core fanning out to N browsers cannot distinguish which browser sent a turn** —
  contradicting `protocol.ts`'s own stated justification for `nextRequestId(prefix, nonce)`. This
  needs settling *before* Unit 6 starts.

---

## Process notes

- **Reviewer agents wrote files into the package under review** (`test/zz-probe.test.ts`,
  `__probe.test.ts`, `zz-scratch-repro*.test.ts`) while building reproductions, and cleaned up
  afterwards. Two reviewers then reported the *other* reviewers' scratch files as a defect in the
  baseline. The tree is clean and the 134/4 baseline was measured before any agent started, so it
  is reproducible — but nominally read-only reviewers mutating the checkout is worth knowing.
- **Commit `0182e732` swept in 17 unrelated documents** (~3,400 lines: memfs audits, a fox-cam
  plan, calendar runbooks) alongside its four continuity files. No secrets; branch never pushed.
  The files belong in git eventually — the damage is a misleading commit message, not exposure.

---

## What this means for M1 Unit 5

Leave it **open**. The unit's advertised property was approval safety. After remediation the
approval path still has a route to "nobody answers" (A1), emits a false drift error on every
approval against a correct server (A2), and reports the expected outcome as a red error (A3).
Re-closing now would repeat the original mistake — ticking a box for a safety property that is not
there.

The reconnect findings (B1, B2) similarly undercut Unit 10's stated deliverable, and C1 is a
remotely-reachable stall on the security boundary Unit 9 introduced.

---

# Round 3 — review of the remediation (2026-08-14)

Scope `9080608e..HEAD`, `clients/` only. Five agents (correctness, adversarial, testing, security,
kieran-typescript). This round reviewed the fixes for everything above, which had been verified
only by their author. Suites were green throughout: 155 core / 4 skipped, 64 terminal, 4 live.

Goal for the corrective work: `docs/plans/2026-08-14-001-fix-continuity-test-binding-goal.md`.

## The 13 mutations (the goal's metric 1)

Each reverts ONE component of a landed fix. All leave the suite green unless noted. ✓ = re-verified
personally rather than taken from an agent report.

| # | Mutation | Result |
|---|---|---|
| 1 | ✓ Approval deny: record-before-send (the exact pre-fix hang) — `src/index.ts` routeFrame | 155 passed |
| 2 | Claim→run binding FIFO → LIFO — `ownership.ts` `onRunObserved` | 155 passed |
| 3 | Six of seven `fanOut` sites → bare loops | 155 passed |
| 4 | Unknown queue disposition: park → drop the claim — `ownership.ts` `onQueueRemovals` | 155 passed |
| 5 | `handleClose` identity guard → pre-fix `this.ws`-reading form | 155 passed |
| 6 | `reconnect()`'s `previous.close()` → leak the outgoing socket | 155 passed |
| 7 | `openConnection`'s failed-connect cleanup removed | 155 passed |
| 8 | All four `writeErr` diagnostics → stdout — `session.ts` | 64 passed |
| 9 | `ownsAnyMessage` ignores its `origin` argument | 155 passed |
| 10 | Per-origin request-id nonce reverted — `index.ts` `send()` | 155 passed |
| 11 | `sentApprovalResponses` reconnect clear removed | unchanged |
| 12 | ✓ Sanitizer `SEQ_BODY` → the quadratic lazy wildcard | sanitize tests passed (111ms) |
| 13 | Flapping budget where the snapshot SUCCEEDS then the socket dies | 81 handshakes vs a budget of 2 |

Mutations 1–12 mean the property is unasserted. 13 means the property is absent: the committed
test suppresses `conversation_messages_list`, so it binds to `fetchSnapshot`'s rethrow rather than
to "the budget cannot be rearmed".

## Verified defects

**S1** — ✓ `stop()`→`start()` is a silent total blackout (watermark reset only in `reconnect()`;
second session rendered **zero** events) · ✓ approval send/record ordering unasserted (see #1) ·
✓ `"lost"` is a terminal claim state (a later dequeue is rejected as an anomaly; `pending` stays 1
forever) · ✓ the idle reaper cannot fire on a live conversation (global `lastActivity` is bumped by
*peer* frames; 12 peer turns at ⅓ of the budget → `{claims:0,runs:0}`) · flapping server still
rearms the budget · one-shot hangs after a mid-turn reconnect (reply renders in full, exits 1) ·
origin threading stops at the first run, so a bridge cannot route a tool-using reply — **the M1
Unit 6 blocker is still open** · claim→run binding order unconstrained (in a bridge, a cross-user
content leak) · `main.ts` has zero tests and holds three S1 defects.

**S2** — `routeFrame` lacks the identity guard `handleClose` has, and `close()` detaches no
listeners · `--json` stdout unparseable (the `you › ` echo) · `process.exit()` truncates piped
stdout (122 of 20,000 lines, at exit 0) · inverse dequeue ordering binds a *peer's* run as `"mine"`
with our origin (the test asserting this "must never happen" stops one turn short) ·
`--allow-remote` never reaches the core · `--json` emits raw C1 (`JSON.stringify` escapes ESC but
not U+009B/9C/9D/DEL) · failed `start()` leaves a live reconnect timer · `ContinuityFatalError`
carries no `request_id`/`origin`, and `input-rejected` is not session-fatal.

**S3** — sanitizer bodies over 4096 survive as visible text (flips at 4097) · invisible class misses
U+E0100–E01EF and U+FFF9–FFFB · `--timeout` above ~24.8 days overflows and fires in ~4ms ·
`renderDelta` treats an `undefined` origin as `self` · `SessionCore`'s conformance assertion does
not catch the bivariance it claims · NDJSON drops `loop_status.status` · `conversation_*` results
narrowed by cast, and `--write-pointer` can clobber a good pointer.

---

# Round 4 — the corrective work (2026-08-14)

Goal: `docs/plans/2026-08-14-001-fix-continuity-test-binding-goal.md`. Instruments first, then
fixes. Suites after: **195 core + 4 skipped, 93 terminal, 4 live**.

## The instruments

**`tools/mutate.mjs` + `tools/mutations.mjs`.** Every fix in these two packages now has a table
entry that reverts exactly that component and names the test which must fail when it does. The
harness applies each in turn, runs the owning suite, checks it failed *for the stated reason*, and
restores. `node tools/mutate.mjs` — **47/47 caught, 2 retired**. This is what replaces
revert-the-whole-commit, which proved a commit was load-bearing and nothing about any component.

**The doubles now model what the wire does.** `MockAppServer` gained the three shapes whose
absence made the previous round unfalsifiable:

- `toolUse` — the captured MULTI-RUN reply: our send starts run N, a tool suspends it, a NEW run
  N+1 carries the answer and only N+1 finishes. **N is never closed, ever.**
- `closeAllConnections()` + `holdCloseHandshakes()`/`releaseCloseHandshakes()` — a polite close,
  and a close handshake deferred on cue, which is the only way to produce a superseded-but-open
  socket deterministically. `dropAllConnections()` (terminate) remains for the killed-process case.
- `FaultyWsConnection` — an injected WRITE fault. No server-side action can produce one: the frame
  that triggers a send and the send itself run in the same tick.
- `suppressFirstResponseFor` / `holdFirstConnectionCloseAfter` / `dropFirstConnectionAfter` /
  `rejectInputWith` — first-connection-only failures, so "the attach failed, then the retry
  succeeded" is drivable against one server.

**Two fixes were RETIRED rather than kept.** Both survived every mutation because they were
unreachable, and an unfalsifiable guard is worse than none — it looks like coverage.

- `reconnect()`'s `previous.close()`. `reconnect()` is reached only from `handleClose` (which fires
  for a socket that already went away) or from its own catch (which now closes the *attempt* rather
  than `this.ws`, itself a fix — the old code could close a NEWER connection). `previous` was
  always already closed.
- `routeFrame`'s identity guard. It and `WsConnection.close()` detaching its listeners were two
  answers to one question, each masking the other. The lifecycle-side detach was kept because it
  protects every consumer, including Unit 6's web client; the consumer-side filter was removed.

## What the instruments then found

Fixes below are each bound by a numbered mutation. Highlights rather than the full list:

- **The approval send/record ordering is now assertable** (mutation 1). With the write fault, the
  pre-fix ordering fails: the deny is marked answered, the server's redelivery is skipped, nobody
  answers.
- **Continuation runs inherit attribution** — the reply to a tool-using turn arrives on a run no
  claim can bind, so origin threading stopped at the first run and a bridge had nothing to route
  by. Bounded by `onIdle()`: `WAITING_ON_INPUT` is the wire stating no turn is executing, which
  stops inheritance running away after a lost `turn_finished`, and releases the orphaned first run
  that never finishes.
- **The idle reaper works on a shared conversation.** It measured from one global `lastActivity`
  that every peer frame bumped, so on the only deployment where a stranded claim costs anything it
  could never fire. Ageing is now per claim and per run.
- **`lost` is no longer a terminal claim state** — a demoted claim can be resolved by its own
  dequeue notice, which is direct evidence rather than the positional inference a reconnect voids.
- **The reconnect budget cannot be rearmed by a server that accepts and dies.** A recovery is now a
  connection that SURVIVES `stabilityMs`, not one that merely opens.
- **`stop()` → `start()` was a total silent blackout** (the watermark was reset only in
  `reconnect()`), and an unknown frame type carrying `MAX_SAFE_INTEGER` could latch the watermark
  permanently — ordering is now restricted to an explicit allowlist of known broadcast types.
- **The sanitizer's capped regex became a linear scanner**, removing both the quadratic
  backtracking and the 4096-byte cliff past which a whole OSC payload survived as visible text.
- **`main.ts` is importable and covered.** The whole program is `run(argv, env, io)`; the process
  shell only exists behind an entry-point check.

## Two defects only a real process could show

Both were found AFTER the offline suite was green, by running the client against the live server —
and both are now covered by subprocess tests that spawn the CLI through an actual pipe.

1. **`--json | head -3` died with an unhandled EPIPE.** The listener-isolation fix could not have
   caught it: a failed pipe write is reported ASYNCHRONOUSLY, as an `error` event on the socket
   after `write()` returned. An array-backed test sink never closes, never fills and never errors,
   so no in-process test could see it either.
2. **`— subagents idle` was landing in the transcript**, between the echo and the reply. The
   stdout/stderr split existed for connection state and errors but not for anything the RENDERER
   produced, and the session tests gave the session ONE sink — so `writeErr` defaulted back to
   `write` and every routing assertion was vacuous. `Renderer.render` now returns
   `{transcript, notice}`; the newline that closes an open line stays with the transcript.

## Residual risks, stated rather than closed

**The inverse dequeue ordering is undecidable from the wire.** The previous round asserted that a
queued claim "degrades to unknown, never to a peer's run", and stopped one turn before the
interesting part. Driven further, the armed claim binds the NEXT run — whoever started it — and
labels a peer's turn as ours with our origin attached. The two orderings are frame-for-frame
identical:

```
live      [peer run starts, peer run finishes, OUR dequeue, our run starts]
inverse   [our run starts,  our run finishes,  OUR dequeue, next run starts]
```

Same shapes, same counts, same order; nothing in `input_accepted`, `update_queue` or the run stream
separates them. No client-side rule can fix this. What makes it acceptable is that the live server
emits the dequeue FIRST, and the live gate fails if that changes — `two peers on one conversation
each own exactly their own run` depends on it directly, since under the inverse ordering the queued
peer owns nothing. The exposure is a bridge (Unit 6) mislabelling one turn after an unnoticed
protocol change. The offline test now asserts the real behaviour and says so.

**The `--json` stream is escaped, not sanitized.** C1 and DEL are emitted as `\uXXXX`, so a
consumer still receives the real characters and a terminal on the other end of the pipe does not
act on them. A consumer that unescapes and prints to a TTY is on its own.

## Blocked: the live end-to-end could not run on the docs agent

The docs agent's model group **`deepseek-v4-flash` answers 404 at the provider** — "Model not
found, inaccessible, and/or not deployed" — so every turn on it ends `stop_reason: "error"`.
Diagnosis:

- Fireworks' own model list DOES contain `accounts/fireworks/models/deepseek-v4-flash`, using the
  key in `.env`.
- Through litellm the same model 404s, while `gpt-4.1-mini`, `gpt-5.4-nano`, `gpt-5.2` and
  `deepseek-v4-pro` all answer normally. So litellm is healthy and the fault is specific to that
  one model group — most likely the key inside the litellm container, or account access to that
  serverless deployment.
- **This is not a client defect and not in these packages.** It does mean the docs agent cannot
  complete a turn from any surface right now, which is worth knowing on its own.

The gate had hard-coded the agent, so an unrelated model outage read as protocol drift. It now
takes `LETTA_LIVE_WS_AGENT`, and `tools/scratch-agent.mjs` mints a disposable agent to be that
input. The full end-to-end below ran on such an agent, which was deleted afterwards.

## Live evidence (2026-08-14, App Server 0.30.19 running, 0.30.20 on disk)

Live gate: **4/4, four consecutive runs.** One flaky test was fixed on the way — the two-peer
ownership check polled `ownershipSnapshot()` on a 20ms interval for a state released the moment the
runtime goes idle, and failed one run in three while the property held. It now samples at
`turn_start`, which is what every comment in `ownership.ts` says to do.

| step | result |
|---|---|
| `conversations create --write-pointer` | exit 0; pointer written, previous saved to `.bak` |
| piped one-shot | exit 0; `agent › OK.` |
| **tool-using** one-shot (`--json`) | exit 0; **2 runs, NO `turn_finished` for either**, terminated on idle; reply `e2e-final-marker` |
| `--json` parsed line-by-line | 32/32 lines parsed; both runs attributed `self` — including the continuation run no claim could bind |
| interactive (over a pty) | exit 0; `you ›` → `agent › FINALOK.` → `/exit` → detached |
| `conversations list` | exit 0; 20 lines on stdout, **0 bytes on stderr** |

The tool-using run is the direct live confirmation of the protocol fact this round was built
around: `turn_finished` never arrives for either run, so the pre-fix wait would have hung, and the
answer lands on a continuation run that inherits its origin.
