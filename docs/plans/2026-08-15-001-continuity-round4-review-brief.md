---
status: proposed
parent: docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
reviews: 27b12dbe (base 017f85c5)
evidence: docs/followups/2026-08-13-continuity-final-review-findings.md
---

# Brief: round-4 review of M1 Unit 5

Branch `feat/msc-app-server-sole-owner`. Scope: `clients/letta-continuity-core` and
`clients/letta-terminal`, the single commit `27b12dbe` against base `017f85c5`.

This is the **decision gate**, not another remediation round. Its output decides whether Unit 5 can
close or whether the approach is wrong.

## Why a fourth review is worth running

Three rounds each found a comparable defect set on a green suite. Round 4's work did not fix more
bugs harder — it changed the instruments: every fix now carries a mutation that reverts exactly
that component and names the test which must fail (`clients/tools/mutate.mjs`, 47/47 caught, 2
retired), and the doubles gained the three shapes whose absence made the previous round
unfalsifiable. **The question this review answers is whether that worked**, and the honest answer
may be no.

## What must be different about this review

Rounds 1–3 read the code and reported what looked wrong. That produced real findings and also a
steady rate of findings that the suite could not have caught either way — which is how three
"verified" rounds shipped defective. Two rules change that:

1. **A finding must arrive with one of two things.** Either (a) a mutation — a concrete edit to
   `clients/tools/mutations.mjs` — that survives `node tools/mutate.mjs`, proving no test binds the
   property; or (b) an explicit demonstration that the harness *cannot express* the finding. Case
   (b) is the more valuable outcome, not a failure: it means the instrument has a blind spot, and
   naming it is worth more than the defect. A finding with neither is a reading, and readings are
   what the last three rounds already supplied.
2. **There must be a "run the binary" leg.** The two sharpest defects found in round 4 were
   invisible to every in-process test *by construction* — an array-backed sink never closes, never
   fills and never reports a write error, so an asynchronous `EPIPE` and a stdout/stderr routing
   leak could not be seen from inside the process. At least one reviewer must drive
   `npx tsx src/main.ts` against a live App Server through real pipes, real redirects and a real
   TTY, and report what it does rather than what the code says it does.

## Settled facts — do not re-derive these

Each was captured live and each has been got wrong at least once by someone re-reasoning from the
code. Re-opening one requires a fresh live capture, not an argument.

- **Approvals are answered UNCONDITIONALLY and always denied.** The server broadcasts each request
  to every subscriber and settles the race itself; the loser is told "no longer pending". The only
  dangerous outcome is nobody answering. Do not propose gating on run ownership.
- **A tool-using reply spans SEVERAL runs, and the run our send starts is never closed.** No
  `turn_finished` for it, ever. Anything keyed on "our run finished" hangs on most real replies.
- **`WAITING_ON_INPUT` precedes `turn_finished`** on the tool-using path, and ownership is released
  at the idle. Sample attribution at `turn_start` and remember it; asking later reads empty. This
  has bitten the codebase four times, most recently as a flaky live test.
- **Live delta ids (`letta-msg-*`) and snapshot ids (`ui-msg-*`) are disjoint namespaces.** Catch-up
  dedup therefore does nothing on a real server. That is M1 Unit 7's problem and the live gate
  asserts the mismatch so it cannot be quietly "fixed" by re-tuning a mock.
- **The inverse dequeue ordering is undecidable from the wire.** Live and inverse produce
  frame-for-frame identical sequences. Under the inverse ordering an armed claim binds the next
  run, whoever started it. This is documented, asserted as the real behaviour, and not fixable
  client-side; the live gate fails if the server stops emitting the dequeue first.

## Known and accepted — report only if the reasoning is wrong

- **Two fixes were RETIRED** (deleted) because no mutation of them could ever fail:
  `reconnect()`'s `previous.close()` and `routeFrame`'s identity guard. Reasoning is in
  `mutations.mjs` under ids 6 and 21. Challenge the reasoning if it is wrong — but "there is no
  identity guard on routeFrame" on its own is the finding that reasoning already answers.
- **`--json` escapes control characters rather than stripping them.** Deliberate: a machine
  consumer needs the real bytes.
- **The docs agent cannot complete a turn** (its model group 404s at the provider). Outside these
  packages. Use `clients/tools/scratch-agent.mjs` to mint a live target.

## Where the author is least confident

Offered because a reviewer told where the author is unsure spends effort better than one told
nothing. None of these is a known defect; all are places where the blast radius is wide and the
evidence is thinner than elsewhere.

1. **Continuation-run inheritance** (`ownership.ts::onRunObserved` → `soleActiveTurn`). A new
   behavioural rule that can attribute a run no claim bound. Bounded by `onIdle()`, which depends
   on `WAITING_ON_INPUT` arriving. If the server emits that mid-turn in any flow not yet captured,
   ownership releases early; if it never arrives (a wedged runtime), inheritance runs until the
   reaper. On a bridge the failure mode is one consumer receiving another's reply.
2. **The connection stability window** (`connection.ts`). The reconnect budget now resets only
   after a connection survives `stabilityMs`, defaulting to `maxDelayMs` (15s). A server that
   restarts every 20s rearms; one that flaps every 5s does not. That threshold is reasoned, not
   measured. Also worth checking: `disconnected()` resets the attempt counter, and exhaustion
   deliberately does not route through it.
3. **The sanitizer was rewritten** from capped regexes to a linear scanner
   (`letta-terminal/src/sanitize.ts`). It is a security boundary, and the previous implementation
   had survived 42 adversarial payloads while this one has a much smaller table. It deserves an
   adversarial pass in its own right: reassembly across chunk boundaries, nested and interleaved
   introducers, and the interaction between the input bound and the scanner.
4. **`guardedWriter` exits 0 when stdout closes** (`letta-terminal/src/main.ts`). Correct for
   `| head`; possibly wrong when the session was already failing, since it discards the exit code
   the run had earned.
5. **`createConnection` is new public API** on `ContinuityCoreConfig`. It exists so a write fault
   can be injected and so Unit 6 can supply a browser transport. Is that seam in the right place,
   and does it widen anything it should not?
6. **`FaultyWsConnection` overrides `send` but not `rawSend`**, so RPCs and the hello are immune to
   the injected fault. Deliberate — but it means "writes fail" is narrower than it sounds, and any
   property that depends on an RPC failing mid-flight is still unasserted.

## How to run it

```bash
cd clients/letta-continuity-core && npm run check     # 195 passed, 4 skipped
cd ../letta-terminal            && npm run check     # 93 passed
cd ..                           && node tools/mutate.mjs   # 47/47 caught, 2 retired

# Live: mint a disposable agent, because the docs agent's model is down.
ID=$(node tools/scratch-agent.mjs)
cd letta-continuity-core
LETTA_LIVE_WS=1 LETTA_LIVE_WS_AGENT=$ID \
  LETTA_LIVE_WS_EXPECT_VERSION=$(…running server version…) npm run check:live
cd .. && node tools/scratch-agent.mjs delete "$ID"
```

The running App Server may be an older build than the one on disk (0.30.19 vs 0.30.20 as of
2026-08-14); both are in `VALIDATED_SERVER_VERSIONS`, which is why the expected version is an input.

**Reviewers must not write files into the packages under review.** Round 3 had reviewer agents
leaving scratch tests behind, after which two other reviewers reported those files as defects in the
baseline. Use a git worktree or a scratch directory.

## The decision

- **Few findings, each carrying a surviving mutation or a named harness blind spot** → the
  instruments work. Unit 5 can close — that tick is Chad's, separately.
- **A comparable defect set again** → stop fixing. Concretely: **two or more S1-class defects** — a
  hang, a silent blackout, a wrong origin label on a shared conversation, or a crash — means the
  approach is wrong rather than the code, and the next move is a design conversation, not a round 5.

## Out of scope

M1 Unit 6 (web client), Unit 7 (catch-up dedup), Unit 8 (deploy/cutover), the docs agent's model
outage, and ticking Unit 5's checkbox in the parent plan.
