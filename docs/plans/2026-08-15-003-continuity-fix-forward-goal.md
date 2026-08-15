---
status: proposed
parent: docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
review: docs/plans/2026-08-15-002-continuity-round4-review-findings.md
evidence: docs/followups/2026-08-13-continuity-final-review-findings.md
branch: feat/msc-app-server-sole-owner
packages: clients/letta-continuity-core, clients/letta-terminal, clients/tools
---

# Goal: fix the continuity clients' non-attribution defects, and make the instrument able to see them

This goal is the **fix-forward half** of the round-4 review verdict
(`docs/plans/2026-08-15-002-continuity-round4-review-findings.md`). That review found >2 S1-class
defects and split them into two root causes. **The ownership/attribution model (root cause A) is a
design fault and is OUT of this goal** — it needs a design conversation and three live captures, not
code. **This goal is everything else**: the error-rendering path, the process/IO test boundary, the
measuring instrument, the injection paths outside the sanitizer, and the Unit-6 API seam. All of it
has a known-correct fix and is implementable by an Opus session under `ce:work` without any design
decision. Do the tiers in order — the instrument tier first, or this produces a round 5 exactly as
round 3 did.

## Why this is not an ordinary bug-fix task

The round-4 instrument (`clients/tools/mutate.mjs` + `mutations.mjs`) is real but blind in three
specific ways, and every S1 here slipped through one of them:

1. **It never runs the binary.** Array-backed test sinks never close, never fill, never error, so a
   hang, an EPIPE-masked exit code, and an errored turn that renders as empty success are all
   invisible in-process. Four defects only appeared when a reviewer spawned the CLI. **The first
   deliverable is a process-level test leg**; without it the Tier-1 fixes cannot be bound and "fixed"
   means nothing.
2. **It never binds the doubles to the protocol.** `mockServer.ts` is a second, unversioned copy of
   the wire vocabulary (drifting its `tool_call_message` string leaves the suite green), and the only
   fidelity check is the four `check:live` tests, which `mutate.mjs` does not run.
3. **It twice asserts a defect as correct**, and its `expect` matches against whole vitest output so
   four entries can be "caught" by any unrelated failure.

Also measured this round: the true baseline is **core 194 passed / 5 skipped** (not 195/4). The fifth
skip is `version-pin.test.ts` self-disabling because its probe path has no `package.json`, so the
server/on-disk drift gate is **off**. And `mutate.mjs` restores mutated source only in a `finally`, so
a kill mid-run leaves reverted load-bearing source in the tree.

Fix the instrument first, then the code, or the code fixes are unfalsifiable.

## Settled facts the implementer must not re-derive

Captured live; each has been got wrong by re-reasoning from the code. Re-opening one needs a fresh
live capture (`clients/tools/scratch-agent.mjs` mints a disposable agent — the docs agent's model
404s and cannot complete a turn).

- **An errored turn's payload is on the wire and dropped by the client.** The server sends both a
  `loop_error` delta and a human-readable `error_message` delta, then goes to `WAITING_ON_INPUT` with
  **no `turn_finished`**. `render.ts` drops both because they are not `assistant`/reasoning types.
- **A tool-using reply spans several runs; the run our send starts is never closed** (no
  `turn_finished` for it, ever).
- **`WAITING_ON_INPUT` precedes `turn_finished`** on the tool-using path.
- The sanitizer *code* is **sound** (200k-input live fuzz, zero escapes) — this goal only closes its
  *coverage*, never rewrites it.

## Completion metrics

Every fix lands with a mutation in `mutations.mjs` that reverts **only that component** and fails a
**named** test; a process-level failure must be bound by a test that **spawns the CLI**, not an
in-process sink. A fix whose mutation leaves the suite green is not done.

**Tier 0 — the instrument (do first; nothing else counts until these pass):**

1. A process-level test harness exists that spawns `main.ts` as a real process and can assert: exit
   code (via `${PIPESTATUS[0]}` under `set -o pipefail` where piped), stdout vs stderr bytes
   separately, and that the process **exits within a bounded time** (a hang fails the test). At least
   one test each drives `< /dev/null`, `| head`, and a pty.
2. `mockServer.ts` can emit an **errored turn** (`loop_error` + `error_message`, then `WAITING_ON_INPUT`,
   no `turn_finished`) and a turn that ends on `turn_finished{stopReason:error}` with no following idle.
   Both shapes are used by a test.
3. `mockServer.ts` imports every frame string from `protocol.ts`; the three strings it invents
   (`SENDING_API_REQUEST`, `EXECUTING_CLIENT_SIDE_TOOL`, `tool_call_message`) are added to `protocol.ts`
   by its own single-home rule; a double-fidelity contract test fails if a mock string is not from
   `protocol.ts`, and a `mockServer.ts` mutation whose `tests` are `check:live` exists.
4. `mutate.mjs` runs vitest with `--reporter=json` and matches each `expect` against the **ids of the
   tests that actually failed**; it refuses to start on a dirty tree and restores source on SIGINT.
   Mutation 19 is split into one entry per `start()` reset, including a stop→start approval-redelivery
   test for `answeredApprovals`.
5. `version-pin.test.ts` **runs** (resolves the installed version robustly) rather than skip-if-missing,
   and asserts it ran. The recorded baseline is corrected to 194/5→(new count).

**Tier 1 — S1 code bugs (each bound by a Tier-0 process or fixture test):**

6. **B1 (P0):** `render.ts:233` renders `error_message`/`loop_error` as a turn-failed notice and the
   run exits nonzero; an errored turn is shown, not swallowed. Mutation reverts the render → the
   errored-turn fixture test fails.
7. **B2 (P0):** `main.ts:327/:416` — `letta-continuity --json < /dev/null` **exits** (resolve on
   `process.stdin.readableEnded`, and/or an explicit `--follow`/`--for <sec>`/`--until-idle` for the
   observe case). Spawn test with `< /dev/null` asserts termination.
8. **B3 (P1):** `main.ts:407` — `guardedWriter`'s `onGone` exits with `process.exitCode ?? 0`, not
   literal 0. Spawn test pipes a **failing** run to `head` and asserts a nonzero `${PIPESTATUS[0]}`.
9. **B4 (P1):** `main.ts:124` — the one-shot **additionally** terminates on
   `turn_finished{stopReason:error}` (a per-run signal). **Additive only: do not touch idle-based
   termination or attribution** (that is root cause A, out of scope). Fixture: an errored turn with no
   following idle → the one-shot exits promptly, not at the timeout.
10. **B5 (P2):** `main.ts:392` — `guardedWriter` does not `throw` from the `error` listener; it marks
    the stream gone (swallow on stderr, record exit code on stdout). Test injects a non-EPIPE stream error.

**Tier 2 — instrument-adjacent code fixes (each bound by a new mutation):**

11. **C2 (P1):** `connection.ts:67` — `stabilityMs` gets a named default independent of
    `reconnectDelayMs`/`maxDelayMs`; a test builds a core with **no** `connectionStabilityMs` and
    asserts the crash-loop bound holds. Mutation `stabilityMs ?? 0` must now fail.
12. **C3 (P2):** `connection.ts:142` assert the `disconnected()` budget reset with a stop→spend→restart
    test; `index.ts:512` `openConnection()` closes the incumbent `this.ws` before replacing it.
13. **C6 (P2/P3):** table-driven sanitizer tests iterating both introducer constants
    (`sanitize.ts:53/:125`) and the invisible ranges, plus the C1 backstop (`:170`); split mutation 37
    per introducer. **Do not change `sanitize.ts` logic** beyond what a test demands.
14. **C8 (P3):** `protocol.ts:745` — retire the `frameEventSeq` equivalent-mutant with a recorded
    reason, or make it reachable and bind it.

**Tier 3 — security + Unit-6 seam (before Unit 6 starts):**

15. **D1 (P2):** `main.ts:250` sanitizes `err.message` like every sibling diagnostic; the two
    `writePointer` echoes (`:221/:230`) too. Test drives control-bearing argv/env and asserts no
    C0/C1/DEL on stderr.
16. **D2 (P3):** `main.ts:203` — `conversations list` strips `\t`/`\n` from `id`/`updated_at` (or emits
    NDJSON). Test with a hostile id asserts one record out.
17. **E1 (P2):** re-type `createConnection` (`index.ts:193`) to a minimal `ContinuityTransport`
    interface a browser can implement without `ws`/`Buffer`; add a **compile-only** fixture that
    implements it without importing `ws`; drop the unused `export { WsConnection }`; correct the
    doc-comment.
18. **E2 (P2):** enforce the loopback boundary in `ContinuityCore` before the factory call, not only in
    `WsConnection`; two core-level tests (`ws://evil…` rejects; `allowRemote:true` does not). Mutation
    `allowRemote: true` must now fail.
19. **E3 (P2):** `index.ts:403` — the `ConversationSummary` predicate checks every field it asserts, or
    builds the objects explicitly. **E4:** delete dead `OwnedRun.parent` (`ownership.ts:83`) and
    `RenderContext.isOwnRun` (`render.ts:80`/`session.ts:115`); bound `attachJson`'s `originByRun`
    (`main.ts:148`); dedupe `evictOldest`; unify the `--json` send path (`main.ts:428`).

## Boundaries

**In:** the two client packages and `clients/tools`.

**Out — do not touch, these belong to the design conversation (root cause A):** anything that changes
how a run is **attributed to an origin** or how a turn is judged **complete via a shared idle** —
i.e. `ownership.ts` inheritance/`onIdle`/`onReconnect`/claim precedence, the `soleActiveTurn` rule,
the `attributionLost` fallback, the duplicate-`turn_start` re-attribution, and the one-shot's
idle-based termination. B4 touches the one-shot but is *additive* (a per-run error signal); if it
cannot be done without altering idle termination, it is out too.

**Also out:** M1 Unit 6 (web client), Unit 7 (catch-up dedup), Unit 8 (deploy/cutover), the docs
agent's model outage, and **ticking Unit 5's checkbox** — Unit 5 does not close on this goal; the
design conversation gates that.

## Bail-out criteria

Stop and raise it rather than pressing on when:

- A fix-forward item turns out to require an **attribution or idle-termination semantics** change.
  Route it to the design track; do not half-fix a model that is being redesigned.
- Building the process-level harness (Tier 0.1) needs a redesign of `main.ts`'s IO seam rather than an
  extension of it. That is a design question, not a fix.
- Binding the doubles to `protocol.ts` (Tier 0.3) shows a settled protocol fact is wrong — re-capture
  live before writing code.
- A landed fix's mutation cannot be made to fail without also failing unrelated tests — the property
  is entangled; name it out loud rather than weakening the mutation.
- Tier 0 is not green within the working session — land the instrument alone rather than carrying code
  fixes on an instrument that cannot see them.
