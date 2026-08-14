---
status: proposed
supersedes: none
parent: docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
---

# Goal: make the continuity clients' tests bind to their properties, then fix what that reveals

Date: 2026-08-14
Branch: `feat/msc-app-server-sole-owner`
Blocks: **M1 Unit 5 closure**, and **M1 Unit 6 (web client) should not start until Unit 3 below lands**

---

## The problem is not the bug list

Three rounds have now run on these two packages:

| Round | Outcome |
|---|---|
| Unit 5 built, marked done | 11-agent review: the approval safety property it advertised was **absent** |
| 12-unit remediation | 11-agent review: a **comparable** defect set, including a *new* "nobody answers" hang |
| P1/P2/agent-native remediation | 5-agent review: **again** a comparable set |

Tests were green at every step. That is the actual finding. A fourth round that just fixes the
current list will produce a fifth.

The cause is now measured rather than suspected. **Thirteen mutations that revert a load-bearing
fix leave the suite green**, including the headline fix of the last round:

| Mutation (revert one fix) | Result |
|---|---|
| Approval deny: record-before-send (the exact pre-fix hang) | **155 passed** ← verified directly |
| Claim→run binding FIFO → LIFO | 155 passed |
| Six of seven `fanOut` sites → bare loops | 155 passed |
| Unknown queue disposition: park → drop the claim | 155 passed |
| `handleClose` identity guard → pre-fix form | 155 passed |
| `reconnect()`'s `previous.close()` → leak the socket | 155 passed |
| `openConnection`'s failed-connect cleanup removed | 155 passed |
| All four `writeErr` diagnostics → stdout | 64 passed |
| `ownsAnyMessage` ignores its `origin` argument | 155 passed |
| Per-origin request-id nonce reverted | 155 passed |
| `sentApprovalResponses` reconnect clear removed | unchanged |
| Sanitizer `SEQ_BODY` → the quadratic lazy wildcard | passed ← verified directly |
| Flapping-server budget property (snapshot **succeeds**, then socket dies) | 81 handshakes vs a budget of 2 |

Two root causes, both mechanical and both fixable:

1. **Tests were written from the fix, not from the property.** Verification was done by reverting
   the whole commit, which proves the commit is load-bearing and says nothing about the component.
   The flapping test suppresses `conversation_messages_list`, so it binds to a rethrow rather than
   to "the budget cannot be rearmed". The ReDoS tests bind to input pre-truncation rather than to
   the regex. The multi-origin test calls `.sort()`, which makes a full A↔B swap indistinguishable
   from correct attribution.
2. **The doubles contradict the captured protocol.** `MockAppServer.broadcastTurn` always emits
   `turn_finished` for the run it started — but the live capture (recorded as settled fact in
   `docs/followups/2026-08-13-continuity-final-review-findings.md`) shows a multi-step reply spans
   several runs and *the run our send starts is never closed*. Every attribution and reaper test
   therefore runs against a model our own evidence says is wrong. `dropAllConnections()` uses
   `socket.terminate()`, so a lingering superseded socket — the precondition for three separate
   lifecycle fixes — is not merely untested but **unproducible**.

---

## Verified defects

Each was reproduced by a probe. ✓ marks the ones re-verified personally rather than taken from an
agent report.

### Severity 1

- ✓ **`stop()` → `start()` on one core is a silent total blackout.** The assembler watermark is
  reset only in `reconnect()`, so a restarted core drops every frame: connected, accepting input,
  rendering nothing. `start()` sets `stopped = false`, so restart is an intended operation. Probe:
  second session produced **zero** render events.
- ✓ **The approval send/record ordering has no test.** Reverting to the pre-fix form leaves 155
  passing. This is the M1 hang — a `ws.send` that throws during a watchdog restart marks the id
  answered, the redelivery is suppressed, nobody answers, every surface parks.
- ✓ **`"lost"` is a terminal claim state.** After `onReconnect()` demotes an armed claim, nothing
  resolves it — a later dequeue is rejected as an anomaly and `pending` stays 1 forever.
- ✓ **The idle reaper cannot fire on a live conversation.** `lastActivity` is global and bumped by
  *peer* frames. Probe: 12 peer turns at one-third of the idle budget → `{claims:0, runs:0}`, the
  orphaned run still owned, a peer run attributing `unknown` instead of `foreign`.
- **A flapping App Server still rearms the reconnect budget** whenever the catch-up snapshot
  *succeeds* before the socket dies. 81 handshakes against a budget of 2.
- **One-shot hangs after a mid-turn reconnect.** The demoted claim never binds, so `sawOurTurn`
  never sets: the reply renders in full, then the process times out and exits 1.
- **Origin threading stops at the first run.** `onRunObserved` binds an origin only via an armed
  claim, so the continuation run that carries the actual reply gets none. **The Unit 6 blocker is
  therefore still open**, for exactly the multi-run case we documented as normal.
- **Claim→run binding order is unconstrained.** LIFO passes the suite. In a bridge this routes each
  browser's reply to the wrong browser — a cross-user content leak.
- **`main.ts` has zero tests** and grew 235 lines last round; three S1 defects live in it.

### Severity 2

- `routeFrame` has no connection-identity guard (`handleClose` does), and `WsConnection.close()`
  detaches no listeners — a superseded socket can latch the fresh assembler's `event_seq`.
- `--json` stdout is unparseable: the `you › …` echo goes to stdout in one-shot mode.
- `process.exit()` truncates piped stdout — 122 of 20,000 lines survived a slow reader, at exit 0.
- Inverse dequeue ordering leaves a stale armed claim that binds a **peer's** next run as `"mine"`
  with our origin. The test asserting this "must never happen" stops one turn short of it.
- `--allow-remote` is parsed, documented, validated, and never forwarded to the core, so it cannot
  work. (Fails closed.)
- `--json` emits raw C1 bytes: `JSON.stringify` escapes ESC but not `U+009B`/`U+009D`/`U+009C`/DEL.
- A failed `start()` leaves a live reconnect timer the caller has no handle on.
- `ContinuityFatalError` carries neither `request_id` nor `origin`, so a bridge cannot tell whose
  send was rejected; and `input-rejected` is not session-fatal, so the classification is wrong.

### Severity 3

- Sanitizer bodies over the new 4096 cap survive as visible text (boundary flips at exactly 4097).
  Not a sequence-execution hole — the per-codepoint filter still strips actionable bytes — but it
  contradicts "strips DCS/APC/PM payloads entirely".
- Invisible-character class misses Variation Selectors Supplement (U+E0100–E01EF), the current
  canonical smuggling range, plus U+FFF9–FFFB.
- `--timeout` above ~24.8 days overflows `setTimeout` and fires in ~4ms.
- `renderDelta` treats `TurnOrigin | undefined` as `self`, reintroducing a confident wrong label.
- `SessionCore`'s conformance assertion does not catch the bivariance it claims to (verified: method
  syntax compares parameters bivariantly; property syntax makes it bite).
- NDJSON drops `loop_status.status` — the very signal one-shot termination depends on.
- `conversation_*` responses are narrowed by cast; `--write-pointer` can clobber a good pointer.

---

## Work

Ordered by dependency. Units 1–2 exist so the rest is *visible*; doing them last would repeat the
mistake.

**Unit 1 — Make the doubles model the captured protocol.**
`MockAppServer` gains: an orphan-run mode (start run N, stream, start and finish run N+1, never
close N); `dropAllConnections({graceful})` using `socket.close()` so a superseded socket lingers;
and an injectable send failure so `ws.send` can throw mid-frame. No production change.

**Unit 2 — Re-derive the mis-bound tests from their properties.**
The thirteen mutations above become the acceptance list: each must fail after this unit. Includes
dropping `.sort()` from the multi-origin assertion, driving the flapping test through a *successful*
snapshot, and giving the ReDoS tests a large explicit `maxLength` so the regex sees the payload.

**Unit 3 — Ownership and attribution.** *(gates M1 Unit 6)*
Resolve `"lost"`; per-claim rather than global idle stamps; release or bound orphaned owned runs;
carry origin at **turn** scope so continuation runs attribute; refuse to bind a claim armed after
its run was first seen; cap `owned`.

**Unit 4 — Connection lifecycle.**
Reset per-connection state in `openConnection` (fixes stop→start); gate the attempt-counter reset on
proven uptime (fixes flapping); identity-guard `routeFrame` and make `close()` inert; clear the
reconnect timer on failed `start()`.

**Unit 5 — Approval path.**
Bind the send/record ordering with a test that makes `send` throw; cap `sentApprovalResponses`;
carry `requestId`/`origin` on the fatal; reclassify `input-rejected` off the session-fatal channel.
Note the residual: approval frames still have no live capture.

**Unit 6 — Terminal testability and one-shot correctness.**
Make `main.ts` injectable and testable; stop gating one-shot termination on exact ownership; drain
stdout before exit; keep `--json` pure and C1-escaped; wire `--allow-remote`; clamp `--timeout`.

**Unit 7 — Sanitizer boundary and residue.**
Boundary tests at 4095/4096/4097; decide cap-vs-second-pass for over-long bodies; extend the
invisible class; correct the docstring's "entirely".

**Unit 8 — Independent re-review**, mutation-focused, on the whole range.

---

## Acceptance criteria

1. **Every fix is mutation-tested individually.** Revert the component — not the commit — and watch
   its test fail for the stated reason. A fix without a failing mutation is not done. This is the
   single criterion that was missing in all three prior rounds.
2. The thirteen mutations tabulated above all fail.
3. No test asserts a property its double cannot produce. Where a double is extended, the extension
   matches a captured live shape and cites it.
4. Both suites green plus the live gate, and a live end-to-end on the **docs** agent covering:
   interactive, piped one-shot, a **tool-using** one-shot, `--json` parsed line-by-line, and
   `conversations create --write-pointer`.
5. Unit 3's acceptance explicitly answers: can a bridge route a tool-using reply back to the
   browser that asked for it? If no, M1 Unit 6 stays blocked.

## Out of scope

- Reconnect catch-up dedup (`letta-msg-*` vs `ui-msg-*` disjoint namespaces) — **M1 Unit 7**.
- Deploying or cutting over the App Server — **M1 Unit 8**.
- Live approval capture, which needs a `permission_mode` change on the deployment.
- Any new surface. This is corrective work only.

## Risks

- **Scope creep into Unit 7's territory.** The orphan-run work touches catch-up adjacent code; stop
  at attribution and leave dedup alone.
- **Unit 1 changes the doubles, so some currently-green tests will start failing.** That is the
  point, but it means Unit 1 and Unit 2 land together or the branch is red in between.
- **Mutation testing is manual here.** If it proves slow, consider a scripted harness rather than
  quietly dropping the criterion — dropping it is how we got here.
