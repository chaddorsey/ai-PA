---
status: active
parent: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md
origin: docs/brainstorms/2026-08-15-continuity-controller-requirements.md
evidence: docs/plans/2026-08-15-006-controller-spike-findings.md (created at C1), docs/plans/2026-08-15-006-salvage-map.md (created at C2)
---

# Goal: the Continuity Controller live, terminal-first — the 10:55 reminder finally lands

## The useful end

A scheduled or agent-initiated turn fires with nobody attached, **completes**, and is visibly
waiting when the operator next attaches — on the real system, not a clone. The terminal is a
thin surface of the resident controller; detaching it mid-turn no longer kills the turn; a
message typed, scheduled, or streamed is delivered or visibly failed, never silently lost.

Scope is the continuity core: **plan units C1–C8, the cutover rehearsal, and a terminal-first
execution of C10b** (App Server + controller supervised live, scheduler re-pointed, incumbent
`lc-local-backend` writers quiesced). The web surface (C9) and pattern registry (C10a) are a
follow-on goal — pa-web-ui runs against the separate Docker backend and continues untouched in
parallel, so nothing is lost by landing terminal continuity first. This staging is consistent
with the parent plan's C10b ("flip terminal then web"); the web flip and pa-web-ui chat-transport
retirement move to the follow-on goal.

## How this runs

`/ce:work` against the parent plan, in dependency order: **C1 + C2 (parallel) → C3 → C4 → C5 →
C6 → C7 → C8 → cutover rehearsal → [operator checkpoint] → C10b terminal-first**. Each unit ends
at its Verification block with its mutation entries landed (a fix without a failing mutation is
not done — the 2026-08-14 standard, no exceptions), and is committed as its own unit. Nothing
before the checkpoint touches live `lc-local-backend` writers; all live-ish testing runs on a
clone backend with scratch agents.

## Where the operator is needed

Four checkpoints; everything else proceeds autonomously against the completion metrics.

1. **C1 verdict — only if it is not a clean GO.** GO on the pre-stated criteria (a second
   subscriber holds a detached turn; tool-call fate understood; no per-socket head-of-line
   blocking; `client_message_id` recoverable) proceeds without you. A NO-GO or an ambiguous
   capture stops the work: the fallback (restart-cancels-turns, journal-marked) changes what
   G2/G3 promise, and accepting that is your call, not mine.
2. **Scheduler job disposition (async).** Before C10b, the `route=letta` job inventory becomes
   a small table — each job: map to local agent / keep on Docker / retire. You skim and amend
   it; no meeting required, a marked-up table is enough.
3. **The cutover window (present).** C10b quiesces your daily tools (terminal wrappers, the
   Desktop app's writer, the local runner) and re-points the scheduler. You should be at a
   terminal for it: the rollback is instant, but only you can verify the felt experience — and
   only you should authorize retiring the `restore-letta-app-server.py` stopgap.
4. **Soak sign-off.** After the agreed soak (default: 48h), you confirm the success criteria
   held, and the goals document's statuses (G1, G2, G3, G5, G7) get their new reality-check
   date. The parent plan's checkboxes for C1–C8/C10b are ticked then, not before.

## Completion metrics

1. **C1 findings doc** exists with capture-file evidence answering all six scenarios (S1–S6),
   and S1 ("a second subscriber holds a detached turn alive") is landed as a permanent,
   version-gated live contract test. Explicit GO/NO-GO recorded.
2. **Salvage map** (C2): every source file in both client packages appears exactly once with a
   destination and justification; the direct raw-WS terminal path is preserved as the
   break-glass client, and retiring modules' mutation entries are retired with them.
3. **Controller skeleton** (C3): runs under launchd against the clone for ≥1 hour; dual
   anchor+worker subscriptions held for the hot set; deltas flow with the anchor absent and
   vice versa; liveness file fresh; logs under `~/Library/Logs/continuity-controller/`; zero
   writes to the live backend.
4. **Turn pipeline** (C4): proofs **P3** (controller killed mid-stream → journal holds each
   event exactly once, in order) and **P4** (App Server killed mid-turn → no non-terminal
   turns, no silence) pass live on the clone, each with a named reverting mutation; the
   wedged-turn path (timeout → `abort_message` → FAILED-VISIBLE → next message runs) is
   tested; the crash-between-write-and-ack reconciliation does not double-submit.
5. **Surface protocol** (C5): the scripted two-surface session shows origin success criterion 1
   (interchangeable use, nothing lost, gapless replay); proof **P5** passes on the
   permission-flipped clone (approval with zero surfaces attached → held, recovered across
   controller restart, answerable on attach).
6. **Terminal** (C6): the existing UX contract (stdout/stderr split, sanitization incl. all
   controller-supplied strings, exit codes, `--json` NDJSON) passes unchanged through the
   transport swap; detaching the terminal mid-turn and re-attaching finds the turn completed —
   the live inverse of the q5 capture.
7. **The 10:55 test** (C7): on the clone stack with a real scheduler-service job — a scheduled
   turn arrives with zero surfaces attached, completes, sets the unseen marker, and is
   presented on next attach with correct landing (tag → default) and awareness tier.
   Unauthenticated ingress POSTs are rejected and journaled.
8. **Direct lane** (C8): an `@specialist` exchange shows zero model invocations before the
   specialist's own turn (timestamped capture); the exchange lives in the specialist's thread,
   rendered inline, correctly attributed; the digest lands as a batched, muted turn in the
   route-origin Kinara thread and never precedes a pending operator message.
9. **Cutover rehearsal**: full runbook executed on the clone — including the job-disposition
   table applied, the `LETTA_CALLBACK_URL` re-point with bearer secret, and a rollback
   restoring incumbents in under a minute — with the P1–P5 checklist green.
10. **Live, terminal-first** (contingent on checkpoint 3): both services supervised on the real
    backend; the operator's terminal is a controller surface; a real scheduled turn survives
    zero-attachment and is seen (origin success criterion 2); rollback demonstrated available;
    after checkpoint 4's soak, the goals doc updated.

## Boundaries

**In:** `clients/continuity-controller/` (new), the two client packages per the salvage map,
the two launchd service definitions + `scripts/` wrappers, the cutover runbook, the
scheduler-side config change (env only), the goals-doc status update at the end.

**Out:** C9 (web surface) and C10a (pattern registry) — follow-on goal; phone/glasses;
relevance-inferred landing; the staged guardrail hardening recorded in the plan's risk entry
(rate caps, budgets, confirmation gates — documented risk, deliberately not built); Docker
Letta decommission; any change to enrichment's `/v1/responses` path.

**Do not:** touch live `lc-local-backend` or its writers before checkpoint 3; tick any parent
plan checkbox before its verification (and for C10b, checkpoint 4) passes; `git add -A` (ever,
in this repo); treat a green suite as done where a mutation cannot be bound — that is a
bail-out, not a footnote.

## Bail-out criteria

Stop and raise it rather than pressing on when:

- **C1/S1 is NO-GO or ambiguous** — the anchor premise fails and the G2/G3 wording changes;
  operator decision before any Phase B code.
- **S6 shows per-socket head-of-line blocking across runtimes** — the single-worker-socket
  shape is wrong; sharding is a design decision to make explicitly before C3, not to improvise
  inside it.
- **S3 shows `client_message_id` is not recoverable from the transcript** — the exactly-once
  reconciliation as designed is unbuildable; C4 must not proceed on a guessed seam.
- **A settled protocol fact turns out wrong on the clone** (this team has been surprised four
  review rounds running) — re-probe live and update the findings doc before writing code
  against the corrected fact.
- **A mutation cannot be made to fail any test** for a load-bearing fix — the property is not
  bound; stop fixing and repair the instrument, per the 2026-08-14 goal's lesson.
- **Any unit leaves the branch red beyond one working session** — land the smaller piece that
  is green rather than carrying a broken tree.
- **The cutover rehearsal fails twice for the same cause** — do not iterate into the live
  cutover; bring the cause to checkpoint 3 as a blocker.
