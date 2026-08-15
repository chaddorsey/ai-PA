---
status: complete
parent: docs/plans/2026-08-15-001-continuity-round4-review-brief.md
reviews: 27b12dbe (base 017f85c5)
evidence: docs/followups/2026-08-13-continuity-final-review-findings.md
method: 11 Opus reviewers (8 persona + agent-native + learnings + live-binary) + 1 Opus mutation-verification wave; synthesis by Fable
date: 2026-08-15
---

# Round-4 decision-gate review of M1 Unit 5 — findings, verdict, and next steps

## Verdict

**STOP. The gate's stop condition is met.** The brief's rule was "two or more S1-class
defects → the approach is wrong rather than the code; the next move is a design conversation,
not a round 5." We confirmed **well more than two S1-class defects, several by running the
binary against the live App Server and the rest by measured surviving mutations** — not by
re-reading the code. The decision is not close.

But "the approach is wrong" is too blunt to act on, and two reviewers reached the same sharper
reading independently (the adversarial reviewer by measurement, the agent-native reviewer by
running the binary). The confirmed defects separate into **two root causes that need opposite
responses**, and conflating them would send round 5 down the wrong road:

1. **A design fault in the ownership/attribution model** (a real design conversation). Attribution
   is *inferred from stream position* and *released on a shared idle signal*. Each component is
   individually correct and individually asserted; they are incompatible in combination; and the
   test doubles encode the same wrong model as the client, so the suite certifies agreement between
   two copies of the mistake. No amount of bug-fixing helps here because the client is deciding
   something the wire cannot decide. **This is the design conversation, and it is one conversation
   for all of these defects.**

2. **A test-boundary fault** (fix-forward, not a redesign). The `TerminalIO` seam that made
   everything else testable carved `nodeIO()` and the error-rendering path out of *all* coverage.
   Every defect that only appeared when someone ran the binary lives in that hole. This is fixable
   by extending the process-level test leg and adding an error-turn fixture — the approach is sound;
   the coverage boundary was drawn in the wrong place.

**Did the round-4 instruments work?** Partly, and the honest answer matters. The mutation harness
is real: the verification wave applied 10 predicted-survival mutations by hand and **all 10
survived** against the true baseline, so no reviewer over-claimed this round — a first. The
sanitizer rewrite is **sound** (fuzzed 200k control-heavy inputs live, zero escapes; verified
against a real adversarial payload on a pty). Origin labelling is **correct under live peer
contention** on the happy path. But the instrument has three specific blind spots that let an
S1-heavy defect set ship green again: (a) it never runs the binary, (b) it never binds the doubles
to the real protocol, and (c) in two cases it *asserts the defective behaviour as correct*.

**Unit 5's checkbox** (out of scope per the brief): the review's answer is unambiguous — **do not
tick it.**

## Baseline correction

The brief states "195 passed, 4 skipped" for the core suite. The true figure on this host is
**194 passed / 5 skipped**. The fifth skip is `version-pin.test.ts` self-disabling because its
hard-coded probe path `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/package.json` does not
exist (the directory was refreshed 2026-08-15 but has no `package.json`). The gate meant to catch
the 0.30.19-vs-0.30.20 server/on-disk drift the brief itself flags is **currently a no-op reporting
green** (finding C7).

---

## Confirmed defects, grouped by root cause

Severity uses the brief's S1 vocabulary (hang / silent blackout / wrong origin label on a shared
conversation / crash) → P0/P1. "Verified" = a live binary run or a measured surviving mutation,
not a reading. Line numbers are at `27b12dbe`.

### Root cause A — Ownership/attribution model (DESIGN)

Attribution inferred from stream position, released on a shared idle. The design conversation owns
all of these.

| ID | Defect | Sev | Verified | Evidence |
|----|--------|-----|----------|----------|
| **A1** | An approval-parked run is never released; `onIdle()` exempts parked runs, but `WAITING_ON_INPUT` precedes `turn_finished`, so the continuation is swept before the parent's finish arrives and the parked parent stays owned forever. Every later run — **including a peer's** — inherits our origin for up to 15 min (reaper). | P1 | probe captured `peer-run-900 attribution: mine`; mutation M1 SURVIVED | `ownership.ts:343` (onIdle), `:316` (finish lookup misses) |
| **A2** | `onReconnect()` demotes armed claims but deliberately keeps `owned` runs; the new `soleActiveTurn()` inheritance reads that map, so the first run after a watchdog seam — plausibly a peer's — inherits our origin. Watchdog restart *kills the runtime mid-turn*, so the orphaned-owned state is the ordinary case, not an edge. | P1 | mutation M2 SURVIVED (194 green with `owned.clear()` added) | `ownership.ts:410` |
| **A3** | The sole *bound* on continuation inheritance is the `onIdle()` call site in `routeFrame`, and **no test asserts the core ever calls it** — deleting it leaves 194/194 green. Component test (`onIdle` unit) passes while the integration point is unbound: the exact failure round 4 exists to kill. | P1 | mutations M3 + adversarial-112 both SURVIVED | `index.ts:638` |
| **A4** | Bridge cross-consumer leak: `onRunObserved` tries the armed-claim branch *before* the continuation branch, so with two browsers on one core (the Unit 6 shape), consumer A's continuation binds consumer B's claim — B receives A's reply under B's origin, A receives nothing. | P1 | blind spot: the harness **asserts the leak as correct** (`ownership.test.ts:364,:533`); both candidate reverts were CAUGHT | `ownership.ts:248` vs `:270` |
| **A5** | A duplicate `turn_start` (synthetic; re-emitted because `activeRunId` clears at *both* `WAITING_ON_INPUT` and `turn_finished`) re-attributes a run after ownership was released; all three origin caches *overwrite* rather than keep the first sample, defeating "sample at turn_start and remember it." | P2 | 4 mutations (101/102/113/114) MEASURED SURVIVED | `session.ts:107`, `render.ts:182`, `main.ts:151`, `stream.ts:107/112` |
| **A6** | The one-shot terminates on the first `WAITING_ON_INPUT` after `sawOurTurn` — but the runtime reports idle *while a turn is parked on an approval*. M1 auto-denies every approval, so any client-side-tool reply exits 0 with the reply missing. | P1 | RAN binary: exit 0, reply absent; mutation 108 SURVIVED | `main.ts:124` |
| **A7** | After any reconnect, `attributionLost` latches true and never clears; nothing can be "positively foreign" while a demoted claim is outstanding, so the next **peer** turn ends the one-shot at exit 0 with the peer's reply as the answer. | P2 | mutation 115 SURVIVED | `main.ts:118` |
| **A8** | A replayed `update_queue` removal (benign server redelivery after reconnect) re-arms a reconnect-demoted `lost` claim — the consumed-id guard is only checked on the claim-*absent* branch — and it then binds a peer's run. | P2 | blind spot: asserted correct at `ownership.test.ts:415`; server-side answer needed | `ownership.ts:205` |

### Root cause B — The `nodeIO()` / error-delta test boundary (FIX-FORWARD)

The `TerminalIO` seam excluded the one component where hangs and blackouts live; the error path has
no fixture. Every defect here was found by running the binary.

| ID | Defect | Sev | Verified | Evidence |
|----|--------|-----|----------|----------|
| **B1** | An errored turn renders as an **empty successful turn** and exits 0: `renderDelta` drops `error_message` and `loop_error` deltas, and no `turn_finished` arrives so the stop-reason notice never fires. Lands on the commonest real fault — a provider outage. **No static reviewer caught this.** | P0 | RAN binary vs a 404-model agent: exit 0, empty stdout; `--json` trace shows both error deltas *present on the wire and dropped* | `render.ts:233` |
| **B2** | Headless attach never terminates: `letta-continuity --json < /dev/null` (the canonical headless invocation) attaches, streams, and hangs forever — `readPipedMessage` drains stdin to EOF, then `interactive` builds a readline over an already-ended stream. No `--follow`/`--for`/`--until-idle`. | P0 | RAN binary: killed at budget; an earlier run sat 3 min | `main.ts:327`, `:416` |
| **B3** | A closed stdout (`\| head`, `\| grep -m1`, `\| less` quit) discards the exit code the run earned: `guardedWriter`'s `onGone` calls `process.exit(0)` unconditionally, and the failure notice never reaches stderr either. Failing session → exit 0 on all three channels. | P1 | RAN binary: `CODE=1` unpiped vs `CODE=0` piped; mutations 114 + M-adjacent SURVIVED | `main.ts:407` |
| **B4** | The one-shot hangs the full `--timeout` (default 180s) on an errored turn that emits `turn_finished{error}` *without* a following idle, then exits 1 with the misleading `— timed out …`. Different server path from B1; the client mishandles both error shapes. | P1 | RAN binary: 20.32s at `--timeout 20` | `main.ts:124` |
| **B5** | `guardedWriter` rethrows any non-EPIPE stream error from inside an EventEmitter `error` listener → uncaughtException → process death, including on stderr whose contract says losing it is survivable. Reachability (EIO/ECONNRESET/ENOSPC) not forced live. | P2 | mutations M6 + adversarial-116 SURVIVED | `main.ts:392` |

### Root cause C — Instrument / harness gaps (the "trust the instruments" holes)

| ID | Defect | Sev | Verified |
|----|--------|-----|----------|
| **C1** | The doubles are a second, unversioned copy of the protocol bound to `protocol.ts` by nothing (29+ raw literals, 3 of which — `SENDING_API_REQUEST`, `EXECUTING_CLIENT_SIDE_TOOL`, `tool_call_message` — don't exist in `protocol.ts` at all). Drifting the mock's `tool_call_message` leaves the suite green; the 4 skipped live tests are the only fidelity check and `mutate.mjs` never runs them; no mutation targets `mockServer.ts`. | P2 | mutation M10 SURVIVED; WAITING_ON_INPUT/turn_finished swap demonstrated green |
| **C2** | The **default** stability window (15s) is executed by zero tests; `reconnectDelayMs` maps onto `maxDelayMs` which is the `stabilityMs` default, so the whole suite runs a 20ms window and a consumer setting `reconnectDelayMs` silently shrinks the crash-loop guard. | P1 | mutation M4 (`stabilityMs ?? 0`) SURVIVED |
| **C3** | `disconnected()`'s `attempts = 0` is the only path back from exhaustion and is asserted by nothing; `start()`-after-fatal inherits an exhausted budget, and `openConnection()` overwrites `this.ws` without closing the incumbent (second wired socket). | P2 | mutation M5 SURVIVED |
| **C4** | `mutate.mjs` matches `expect` against the whole vitest output, so 4 entries (ids 8, 13, 22, 42) can be "caught" by any unrelated failure in the same file — the precise "load-bearing ≠ property-bound" conflation the tool exists to eliminate. | P3 | reasoned from `mutate.mjs:99` |
| **C5** | Mutation 19 reverts four `start()` components at once; its `expect` binds only the watermark, leaving three per-connection resets unbound — including `answeredApprovals`, whose loss reproduces the "nobody answers, every surface parks" hang on a third path. | P2 | reasoned; no stop→start approval-redelivery test exists |
| **C6** | Sanitizer *code* is sound but *coverage* is thin: the final C1 backstop is unbound (M7), bidi isolates U+2066–2069 are unbound (M8), and mutation 37 is too coarse (4/5 8-bit introducers + `ESC X` individually unbound). | P2/P3 | mutations M7, M8 SURVIVED |
| **C7** | `version-pin.test.ts` self-disables when its hard-coded probe path misses and the suite still reports green — the server/on-disk drift gate is off on this host. | P2 | live: skip count 5 not 4 |
| **C8** | `frameEventSeq`'s range check is an equivalent mutant (unreachable — `validateInboundFrame` validated `event_seq` upstream) kept while ids 6/21 were retired for exactly that. | P3 | mutation M9 SURVIVED |

### Root cause D — Injection paths outside the (sound) sanitizer

| ID | Defect | Sev | Verified |
|----|--------|-----|----------|
| **D1** | The argument-parse error path writes `err.message` to stderr **unsanitized** (every sibling diagnostic sanitizes) — OSC-52 clipboard hijack via `letta-continuity $'\x1b]52;c;…\x07'` → `unknown option: <ESC>]52;…`, or title spoof via `--url $'\x1b]0;pwned\x07'` through `TrustBoundaryError`. Fires before any socket opens; env-driven, and agents write this repo's env. | P2 | concrete payloads given; structurally invisible to `mutate.mjs` (missing guard) |
| **D2** | `conversations list` builds TSV using `\t`/`\n` — exactly the two chars the sanitizer preserves by design — over server-supplied `id`/`updated_at` validated only as `typeof === "string"`. A hostile id injects records into Unit 8's cutover-script parsing. | P3 | concrete payload given |

### Root cause E — API seam / Unit-6 forward risk

| ID | Defect | Sev | Verified |
|----|--------|-----|----------|
| **E1** | `createConnection` is typed to the concrete `WsConnection` class, whose 8 private members make the type nominal — so **the browser transport it exists for cannot implement it** (only a subclass can, dragging the Node-only `ws` package into a browser). Half its stated purpose is false today; `export { WsConnection }` has no consumer; `ws` is pinned into the public module graph. | P2 | compile-verified (scratch `BrowserTransport` fails `TS2322`) |
| **E2** | The loopback trust boundary is unbound at the core level (`allowRemote: true` survives, 194 green) and the `createConnection` seam bypasses `assertLoopbackUrl` entirely — a security boundary on a server with **no client auth**, enforced only inside the object the factory replaces. | P2 | mutation ran, SURVIVED |
| **E3** | `filter((c): c is ConversationSummary …)` asserts six fields on the evidence of one; deleting the other five from every returned summary leaves the suite green — a type predicate that reads as validated but is strictly worse than a cast. | P2 | mutation ran, SURVIVED |
| **E4** | Dead/duplicated code the round added or touched: `OwnedRun.parent` written-never-read; `RenderContext.isOwnRun` no consumer (round 4 "fixed" its dead branch); `attachJson`'s `originByRun` unbounded on the `--json` bridge path (leaks one entry per tool-using turn, forever); `evictOldest` duplicated at 4 sites; `--json` re-implements the send path and already diverges on `/exit` and whitespace. | P3 | greps + reasoning |

### Process notes (not code defects, but they bear on trusting the round)

- **`mutate.mjs` mutates tracked source in place and restores only in a `finally`.** A SIGINT or crash
  mid-run leaves reverted load-bearing source in the working tree — the same "reviewer left files
  behind" class the brief calls out from round 3, now on real source rather than scratch tests. It
  does not refuse a dirty tree before starting.
- **`scratch-agent.mjs` speaks four wire strings (`agent_create`/`agent_delete` + responses) outside
  `protocol.ts`** with no drift gate. On a rename, an unrecognised frame falls through and presents as
  a 60s "timed out waiting for the App Server" — the exact "one outage read as protocol drift"
  confusion this round was convened to remove.
- **R2's "every fix was verified to fail against unfixed code" claim was false** for at least
  `reconnect()`'s `previous.close()`, which round 4 correctly proved unreachable and retired
  (mutation id 6). Worth stating because that claim is why R2 was believed.

---

## The design conversation (root cause A) — what it must decide

The ownership model asks the wire two questions it cannot answer:

1. **"Whose run is this?"** — inferred from stream position (armed claim vs. sole active turn), on a
   transport where a tool-using reply spans several runs, our send's run never closes, and on a bridge
   two consumers' claims are armed at once. A4/A8 show the inference binding a peer's run to our
   origin; A1/A2 show it surviving state (park, reconnect) that should invalidate it.
2. **"Is the turn over?"** — inferred from a *shared* `WAITING_ON_INPUT` idle, which also fires while a
   turn is parked on an approval (A6) and is emitted before `turn_finished` on the tool-using path,
   re-attributing runs after release (A5). The one-shot terminates on it; a peer's idle ends our
   command (A7).

Concrete questions for the conversation:

- **Can attribution be carried on the frames themselves** (an origin/claim token the server echoes)
  rather than inferred from position? The brief's settled fact that "the inverse dequeue ordering is
  undecidable from the wire" already concedes the wire cannot disambiguate; A4/A8 are the same concession
  reaching a live failure. If the server cannot echo identity, the bridge (Unit 6) may be
  **unbuildable safely** on this model, which is a milestone-level decision.
- **Should turn termination key on a per-run signal** rather than a shared idle? A6/A7 are both "someone
  else's idle ended our wait." A `turn_finished` for *our* run would fix them — but the settled fact is
  that our send's run never closes, so this needs a server-side turn-completion signal that today does
  not exist.
- **The doubles must be able to falsify the model.** A4 and A8 are asserted *as correct* by the current
  tests; C1 shows the doubles are a second copy of the protocol bound to nothing. Whatever model is
  chosen, its doubles have to be generated from — or contract-tested against — `protocol.ts` and a live
  capture, or the next round green-lights the next wrong model too.

Recommended input to the conversation: a **live capture** answering the three questions the adversarial
reviewer flagged as promotable-or-killable by one capture each — (1) does the server emit
`WAITING_ON_INPUT` while a turn is parked on an approval; (2) can two `input` frames on one socket both
be acked `started`/`submitting`; (3) does the server re-broadcast `update_queue` removals after a
reconnect. Each capture either kills a finding or promotes it to a hard requirement for the redesign.

---

## Fix-forward work that does NOT need the design decision

These are Opus-implementable now, independent of the attribution redesign. Each names the file, the fix,
and the mutation/test that must bind it so the fix is falsifiable. **Do not run these as "round 5" under
the current instrument** — pair each with the test that makes the surviving mutation fail, or it is not
done.

**Tier 1 — S1 code bugs, no design dependency:**

1. **B1 (P0): render error deltas.** In `render.ts:233`, stop discarding `error_message`/`loop_error`;
   render them as a turn-failed notice and set a nonzero exit. Fixture: a mock turn that emits
   `loop_error` + `error_message` then `WAITING_ON_INPUT` with no `turn_finished`. Mutation: revert the
   render → the fixture's "an errored turn is shown and exits nonzero" test must fail. *(This is also the
   docs-agent-404 case the brief scopes out — the outage is out of scope, but the client silently
   eating it is not.)*
2. **B2 (P0): headless hang.** Resolve `readPipedMessage`/`interactive` when `process.stdin.readableEnded`,
   or add an explicit `--follow`/`--for <sec>`/`--until-idle` and make bare `< /dev/null` exit. Test:
   **spawn the process** with `< /dev/null` and assert it exits (an array-sink test cannot see this).
3. **B3 (P1): stdout-close exit code.** `guardedWriter`'s `onGone` should `process.exit(process.exitCode ?? 0)`,
   not literal 0. Test: spawn a **failing** run piped to `head`, read `${PIPESTATUS[0]}` under
   `set -o pipefail`, assert nonzero. (The existing pipe test reads `head`'s status — fix the test too.)
4. **B4 (P1): errored-turn hang.** Make the one-shot terminate on `turn_finished{stopReason:error}`,
   not only on idle. Fixture: a turn that ends on error without a following idle. Mutation: revert →
   "an errored turn exits without waiting for the timeout" must fail.
5. **B5 (P2): non-EPIPE rethrow.** Don't `throw` from the `error` listener; mark the stream gone (swallow
   for stderr, record exit code for stdout). Test: inject a non-EPIPE error on the stream.

**Tier 2 — instrument repairs (do these before any further remediation round, or the round is blind):**

6. **C1: bind the doubles to `protocol.ts`.** Have `mockServer.ts` import every frame string from
   `protocol.ts`; add the three missing wire strings (`SENDING_API_REQUEST`, `EXECUTING_CLIENT_SIDE_TOOL`,
   `tool_call_message`) to `protocol.ts` by its own rule; add a double-fidelity contract test whose
   failure is the live gate. Add a small class of `mockServer.ts` mutations whose `tests` are `check:live`.
7. **C7: version-pin gate.** Fix the probe path (or read the installed version robustly) so the gate runs;
   assert it *ran* rather than skip-if-missing. Record the true "194/5" baseline.
8. **C4 + C5 + C8: harness hygiene.** Switch `mutate.mjs` to `--reporter=json` and match `expect` against
   failing test *ids*; split mutation 19 into per-component entries (19a/b/c) and add the stop→start
   approval-redelivery test; retire or bind the `frameEventSeq` equivalent mutant. Make `mutate.mjs`
   refuse a dirty tree and restore on SIGINT.
9. **C2 + C3: reconnect budget.** Give `stabilityMs` its own named default independent of
   `reconnectDelayMs`; add a test that builds a core with **no** `connectionStabilityMs` and asserts the
   crash-loop bound holds; assert `disconnected()`'s reset and close the incumbent socket in
   `openConnection()`. (The 15s threshold remains *reasoned, not measured* — a live watchdog-restart
   profile would settle it; note this as an accepted open risk if not measured.)
10. **C6: sanitizer coverage.** Add a table-driven test iterating both introducer constants and the
    invisible ranges (bidi isolates, the C1 backstop, per-introducer 8-bit + `ESC X`); split mutation 37.
    The code is sound — this only closes the coverage that made 47/47 read as more complete than it is.

**Tier 3 — security and Unit-6 seam (before Unit 6 starts):**

11. **D1 (P2): sanitize the arg-parse error path** at `main.ts:250` like every sibling; sanitize the two
    `writePointer` echoes; add a control-bearing-argv test.
12. **D2 (P3): delimiter-safe `conversations list`** — strip `\t`/`\n` from `id`/`updated_at` or emit NDJSON.
13. **E2 (P2): enforce the loopback boundary in the core** (`ContinuityCore.newConnection()` before the
    factory), add the two core-level trust tests.
14. **E1 (P2): re-type `createConnection` to a minimal `ContinuityTransport` interface** the browser can
    implement without `ws`/`Buffer`; add a compile-only fixture that implements it without importing `ws`;
    drop the unused `export { WsConnection }`. Correct the doc-comment. *(Do this before Unit 6 builds
    against a seam that will reject its transport.)*
15. **E3 (P2): make the `ConversationSummary` predicate check what it asserts**, or build the objects
    explicitly; **E4:** delete the dead `parent`/`isOwnRun`, bound `attachJson`'s `originByRun`, dedupe
    `evictOldest`, unify the `--json` send path.

---

## What is genuinely working (do not relitigate)

- The **sanitizer rewrite is sound** — 200k-input live fuzz, zero escapes; brief items (a)–(d) all answer
  negatively against the current code; `--json` escaping is complete for terminal-actionable bytes.
- **Origin labelling is correct under live peer contention** on the happy path (peer turns render `peer ›`,
  own turns `self`, no interleave corruption).
- **The multi-run tool reply terminates on runtime idle, not "our run finished"** — bound by a test *and*
  a mutation (id 32); the single most important agent property, and it holds.
- **stdout/stderr split is clean** on the one-shot path; `--allow-remote` reaches the core; approvals have
  a real machine representation and the auto-deny policy is identical for human and agent.
- The **live contract gate passes 4/4** against the running 0.30.19 server.
- The retirements of mutations 6 and 21 are **correct** (both proved unreachable).

## Cleanup

Two review worktrees under `.claude/worktrees/` (verification wave, live-binary leg) are left clean and
can be pruned with `git worktree prune`. The main checkout `clients/` tree was verified untouched
throughout.
