---
status: proposed
parent: docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
evidence: docs/followups/2026-08-13-continuity-final-review-findings.md
---

# Goal: bind the continuity clients' tests to their properties, then fix what surfaces

Branch `feat/msc-app-server-sole-owner`. Packages `clients/letta-continuity-core` and
`clients/letta-terminal`. All findings, probes and the mutation table live in the evidence doc
above (§Round 3). Blocks **M1 Unit 5** closure; **M1 Unit 6 must not start** until metric 5 passes.

## Why this is not a bug-fix task

Three remediation rounds each shipped a comparable defect set with a green suite. The cause is
measured: **13 mutations that revert a load-bearing fix leave the suite passing** — including the
approval send/record ordering, where restoring the pre-fix "nobody answers" hang gives 155 passed.

Two mechanical reasons. Tests were written from the fix rather than the property, and verified by
reverting whole *commits* (which proves the commit is load-bearing and nothing about the
component). And the doubles contradict our own captured protocol: `MockAppServer` always closes the
run it started, while live, the run our send starts is never closed; `dropAllConnections()` uses
`terminate()`, so the lingering superseded socket three fixes guard against cannot be produced.

Fix the measuring instruments first, or round 4 produces a round 5.

## Completion metrics

1. All 13 mutations in the evidence doc fail, each for its stated reason.
2. Every changed fix has a mutation reverting **only that component** that fails its own test. No
   exceptions — a fix without a failing mutation is not done.
3. `MockAppServer` can produce an orphan run (start N, finish N+1, never close N), a gracefully
   closed superseded socket, and a throwing `ws.send`; each is used by at least one test.
4. Both suites green, live gate green, and a live end-to-end on the **docs** agent covering:
   interactive, piped one-shot, a **tool-using** one-shot, `--json` parsed line-by-line, and
   `conversations create --write-pointer`.
5. One core with two origins routes a **tool-using** reply back to the origin that sent it.
6. `main.ts` is importable and covered for: one-shot termination, timeout, fatal→exit 1,
   undelivered→exit 1, and NDJSON purity.

## Boundaries

**In:** the two client packages only.
**Out:** reconnect catch-up dedup (M1 Unit 7); App Server deploy or cutover (M1 Unit 8); live
approval capture (needs a `permission_mode` change on the deployment); any new surface or feature.
**Do not** tick the parent plan's Unit 5 checkbox as part of this work — that decision is Chad's,
separately, once these metrics pass.

## Bail-out criteria

Stop and raise it rather than pressing on when:

- Metric 5 cannot be met without changing the wire protocol or opening a second connection. That is
  a design question for Unit 6, not a fix.
- Fixing the doubles shows a settled protocol fact is wrong. Re-probe live before writing code.
- Units 1–2 (doubles + test re-derivation) leave the branch red beyond one working session — land
  the doubles alone rather than carrying a broken tree.
- Per-fix mutation testing costs more than the fixes themselves across three consecutive fixes.
  Script it or renegotiate the criterion out loud; dropping it silently is how we got here.
- A fourth review round finds a comparable defect set. Stop fixing: the approach is wrong, not the
  code.
