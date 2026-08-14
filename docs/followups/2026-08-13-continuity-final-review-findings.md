# Final review findings — continuity remediation (`bf46d004`…`cc270edb`)

Date: 2026-08-13
Branch: `feat/msc-app-server-sole-owner`
Scope reviewed: `clients/letta-continuity-core/`, `clients/letta-terminal/` — base `e5079323`
Team: 11 agents (4 always-on, learnings, agent-native, security, reliability, api-contract,
kieran-typescript, adversarial)

**Verdict: NOT ready. M1 Unit 5 must stay open.**

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
