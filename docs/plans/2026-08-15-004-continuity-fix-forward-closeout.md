---
status: complete
parent: docs/plans/2026-08-15-003-continuity-fix-forward-goal.md
review: docs/plans/2026-08-15-002-continuity-round4-review-findings.md
branch: feat/msc-app-server-sole-owner
packages: clients/letta-continuity-core, clients/letta-terminal, clients/tools
date: 2026-08-15
commits: bd11ee30 (tier 0+1), 121e0d25 (tier 2), f01435dd (tier 3)
---

# Closeout: the fix-forward half of the round-4 verdict

Everything in the goal landed. Root cause A (ownership/attribution) was not touched and remains
the design conversation. **Unit 5's checkbox is not ticked** — that was out of scope and stays
the design track's call.

## Where the numbers moved

| | before | after |
|---|---|---|
| core suite | 194 passed / 5 skipped | 211 passed / 4 skipped |
| terminal suite | 93 passed | 136 passed |
| mutation table | 54 entries | 81 entries (77 active, 3 retired, 1 live-only) |

The core's 4 remaining skips are `live.contract.test.ts`, which is opt-in by design
(`LETTA_LIVE_WS=1`). The fifth skip is gone: `version-pin.test.ts` now runs.

Full mutation run on a clean tree (`node tools/mutate.mjs`):

```
77/77 mutations caught, 3 retired, 1 deferred (--live)
```

The first full run reported **75/77 with two harness ERRORS** — mutations 42 and 58 could no
longer find the code they guard, because the B3/B5 fix reshaped `guardedWriter`'s callback and the
formatter rewrapped the sanitized arg-parse diagnostic. Both were repointed rather than deleted,
per the table's own rule. Worth recording as evidence the tool works: the old harness would have
reported those two as *caught* on any unrelated failure in the same file, and reporting them as
errors is exactly the discrimination `--reporter=json` bought.

## Tier 0 — the instrument

**The harness now runs the binary.** `clients/letta-terminal/test/helpers/spawnCli.ts` spawns
`main.ts` under `bash`, and reports what a shell reports:

- the **CLI's own** exit status via `${PIPESTATUS[0]}`, not the pipeline's. This is the distinction
  B3 turned on, and the suite's previous pipe test asserted `head`'s status while appearing to
  assert the client's;
- stdout and stderr as **separate** file descriptors, so "stdout carried nothing but NDJSON" is a
  meaningful claim;
- **bounded time**, so a hang is a failed assertion rather than a slow test.

Tests drive `< /dev/null`, `| head`, and a real pty (via `script(1)`). It found B2 and B3 on its
first run.

Two bugs inside the harness itself are worth recording, because both are the failure it exists to
detect, committed by the detector:

- `pipeline_status=$?` on its own line **rebuilt `PIPESTATUS`**, so the harness read the
  assignment's status array and reported 0 for a run that exited 2 — laundering the exit code
  while checking for laundered exit codes. Fixed by capturing both in one command.
- the pty leg discarded `script`'s own stderr, so a usage error presented as a bare "exit 1 after
  6ms" with nothing to diagnose. Its diagnostics are kept now.

**The doubles are bound to the protocol.** `mockServer.ts` was a second, unversioned transcription
of the wire vocabulary; drifting its `tool_call_message` left the whole suite green. Every wire
string now comes from `protocol.ts`, which gained the three the double had invented
(`SENDING_API_REQUEST`, `EXECUTING_CLIENT_SIDE_TOOL`, `tool_call_message`), the two an errored turn
is carried on (`loop_error`, `error_message`), and the single-word values that hide in plain sight
(`message`, `user`, `local`). `double-fidelity.test.ts` fails on any literal in the double that is
neither a protocol value nor explicitly declared non-wire — verified by injecting the exact drift
that used to pass.

Its scope, stated honestly: it gates wire **values**. Field **names** are unquoted object keys and
invisible to it; those are gated by `validateInboundFrame` and `check:live`. The chain is
mockServer → protocol.ts (this test) → the real server (`check:live`), and it needs both links.

**`mutate.mjs` matches failing test ids.** It runs vitest with `--reporter=json` and matches each
`expect` against the names of the tests that actually failed, rather than against the whole
console. It also refuses a dirty tree, restores source on SIGINT/SIGTERM/uncaught exception, and
rejects duplicate ids. All three caught real problems while landing this work — the duplicate-id
check because two new entries were appended as 42/43 when those ids already existed, and the
symptom was a selection error naming no ids at all.

The id matching immediately paid: mutation 45's `expect` named the wrong one of two fidelity
tests, which whole-output matching could not have distinguished.

**Mutation 19 is split.** It reverted four `start()` resets behind an `expect` bound only to the
watermark, so three were unasserted — including `answeredApprovals`, whose loss reproduces the
nobody-answers hang on a third path. Now 19a/19b/19c with a test each; **19d is retired with the
reason recorded**: `sentApprovalResponses` ids are unique for the life of the process, so clearing
them at `start()` is unobservable — the codebase already makes exactly this argument at
`index.ts:700` for the `reconnect()` path, and the rule is applied here rather than quietly
excepted. Same treatment as ids 6 and 21.

**The version-pin gate runs.** It had been a no-op reporting green. The cause was mundane and
would recur: an interrupted `npm install` left `@letta-ai/letta-code`'s `package.json` in its
staging directory (`@letta-ai/.letta-code-*`), so the package was installed and working but the
one hard-coded path the probe looked at was missing. It now probes every plausible location
(including staging directories and `npm root -g`), and **fails rather than skips** when it cannot
reach a verdict. The installed version is **0.30.20**, which is in `VALIDATED_SERVER_VERSIONS`.

## Tier 1 — the S1 bugs

| | fix | bound by |
|---|---|---|
| **B1** | `render.ts` renders `error_message`/`loop_error` as a turn-failed notice; the failure reaches the exit code on both the human and `--json` paths | errored-turn fixture; mutations 46, 47 |
| **B2** | `--json < /dev/null` exits — readline over an already-ended stdin never emits `close` | spawn test; mutation 48 |
| **B3** | a closed stdout exits `process.exitCode ?? 0`, not a literal 0 | spawn test; mutation 49 |
| **B4** | the one-shot also terminates on `turn_finished{stopReason:error}` | fixture; mutation 50 |
| **B5** | `guardedWriter` never throws from an `error` listener | unit test; mutation 51 |

B4 is **additive** as required: a per-run signal read from the frame, reusing the existing
`sawOurTurn` guard. Idle termination and attribution are untouched.

One thing B1 needed that the goal did not anticipate: `loop_error` carries no `delta.id`, and
`validateInboundFrame` rejects an id-less content delta as drift — so the frame would have been
dropped before the renderer ever saw it, leaving B1 "fixed" and still broken end to end. It is
now in `CONTROL_DELTA_TYPES` alongside `stop_reason`, and the mock emits it without an id so the
fixture is the stricter shape.

## Tier 2 and Tier 3

C2 (stability window decoupled from the retry delay, plus the one test that runs the shipped
default), C3 (`disconnected()`'s budget reset; `openConnection()` closes the incumbent socket), C6
(per-member sanitizer coverage — mutation 37 split into 37a-37j), C8 (`frameEventSeq` bound rather
than retired), D1, D2, E1, E2, E3, E4 all landed as specified. See the three commit messages for
the per-item reasoning.

Two notes worth carrying forward:

- **C6 changed no sanitizer logic.** The code was already sound (200k-input live fuzz). What was
  thin was coverage: each class was tested through one representative member, so four of the five
  8-bit introducers and `ESC X` were individually unbound.
- **C8 was bound, not retired.** Through the pipeline its guards are genuinely equivalent mutants,
  because `validateInboundFrame` range-checks the same six types first. It is bound anyway because
  `frameEventSeq` is *exported* — its contract is owed to every caller — and the coupling that
  makes it redundant is invisible and one `ORDERED_BROADCAST_TYPES` entry away from breaking.

## What is deliberately NOT closed

- **Root cause A** — attribution and idle-based turn completion. Untouched, as instructed.
- **Unit 5's checkbox.** Not ticked.
- **Mutation 44** (`protocol.ts` drift vs the real server) is **live-only** and was not run: it
  needs an App Server on :4577. `node tools/mutate.mjs --live 44` when one is up. The tool reports
  it as *deferred* rather than omitting it, so "not run" and "passed" cannot be confused.
- **A mockServer mutation bound to `check:live` does not exist, and cannot.** The goal asked for
  one; `live.contract.test.ts` does not import the double — it speaks to a real server through
  `protocol.ts`'s builders — so such a mutation could never fail. The equivalent binding that
  *does* work is mutation 44 (drift `protocol.ts`, watch the live gate fail), plus mutation 45
  offline. Recorded rather than faked.
- **E1 has no mutation.** Its failure mode is a compile error; `transport.compile.test.ts` is a
  typecheck-time fixture, and no runtime assertion can express it.
- **The 15s stability window remains reasoned, not measured.** Recorded in `connection.ts` as an
  accepted open risk. A live watchdog-restart profile would settle it.
- **`--follow`/`--for`/`--until-idle`** were listed as optional alternatives for B2. B2 was fixed
  by making the headless attach *exit*; there is consequently no way to observe a conversation
  headlessly without sending a message. If Unit 8's cutover wants that, it is a small additive
  flag, not a redesign.

## For whoever runs round 5

The three blind spots are closed, but the instrument is only as good as its newest test. The
habits that mattered here:

1. **If a defect is about a process, the test must spawn one.** Four defects were invisible to 287
   in-process tests and obvious the moment someone ran the binary.
2. **A test that passes for the wrong reason is worse than no test.** The first B3 test passed
   against unfixed code, because `head` closed the pipe long before the run had earned a nonzero
   code. It had to be staged in time to mean anything.
3. **When a new test fails, suspect the test.** Three did here — the C1-block assertion, the
   `liveDedup` scenario, and the `/exit` exit code — and in all three the code was right and the
   test's model of it was wrong. Each correction taught more than the original assertion would
   have.
