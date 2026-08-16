---
status: active
parent: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md
origin: docs/brainstorms/2026-08-15-continuity-controller-requirements.md
---

# Goal: Continuity Controller built and proven on clone — cutover-ready

Branch `feat/msc-app-server-sole-owner`. Execute the parent plan's units via `/ce:work`, order:
C1+C2 (parallel) → C3 → C4 → C5 → C6 → C7 → C8 → C10b rehearsal. All testing on a CLONE backend
(alt port, scratch agents via `clients/tools/scratch-agent.mjs`); never touch live
`~/.letta/lc-local-backend` or its writers. Each unit ends at its plan Verification, one commit,
one named reverting mutation per fix (none = not done). Live cutover (C10b terminal-first) =
a separate operator-attended goal.

## Completion metrics

1. C1: `docs/plans/2026-08-15-006-controller-spike-findings.md` answers S1–S6 with capture
   files; S1 (second subscriber holds a detached turn) landed as a permanent version-gated
   live contract test; GO recorded.
2. C2: `docs/plans/2026-08-15-006-salvage-map.md` maps every source file in
   `clients/letta-continuity-core` + `clients/letta-terminal` exactly once
   (controller / surface / retire); direct raw-WS terminal kept as break-glass.
3. C3: controller runs under launchd vs clone ≥1h; anchor+worker DUAL subscriptions
   held; deltas flow with either connection absent; liveness file fresh; logs in
   `~/Library/Logs/`.
4. C4: P3 (controller killed mid-stream → journal exactly-once, ordered) and P4 (App Server
   killed mid-turn → no non-terminal turn, no silence) pass live-on-clone with mutations;
   wedged turn → timeout → `abort_message` → FAILED-VISIBLE → next message runs; write→ack
   crash never double-submits.
5. C5: scripted two-surface session — turn in one appears in the other, gapless replay,
   nothing lost; P5 on the permission-flipped clone (approval, zero surfaces → held, survives
   controller restart, answerable on attach).
6. C6: terminal UX contract (stream split, sanitizer on ALL controller strings, exit codes,
   NDJSON) green through the transport swap; detach mid-turn, re-attach → turn completed.
7. C7, the 10:55 test: a real scheduler job on the clone fires with zero surfaces
   attached → completes, unseen marker set, presented on next attach, landing tag→default;
   unauthenticated ingress POST → 401, journaled.
8. C8: `@specialist` exchange with zero model calls before the specialist's own turn
   (timestamped); renders inline in the specialist's thread, attributed; digest = batched
   muted turn in the route-origin Kinara thread, never ahead of a pending operator message.
9. Rehearsal: `docs/runbooks/continuity-controller-cutover.md` executed on clone — job
   disposition table drafted, marked NEEDS-OPERATOR-REVIEW; bearer-secret re-point; rollback
   <1min; P1–P5 checklist green.

## Boundaries

In: new `clients/continuity-controller/`, the two client packages per salvage map, launchd
reference plists + `scripts/` wrappers, the runbook. Out: live cutover; C9 web; C10a patterns;
guardrail hardening (documented risk); enrichment `/v1/responses`; Docker Letta. Do not: tick
parent-plan checkboxes beyond C1–C8; touch the live backend or its writers; `git add -A`.

## Bail-out criteria — stop, record in findings doc, end goal

- S1 NO-GO/ambiguous: anchor premise fails; G2/G3 wording becomes operator decision.
- S6 per-socket head-of-line blocking across runtimes: decide sharding before C3.
- S3: `client_message_id` unrecoverable from transcript — C4's exactly-once seam unbuildable.
- A settled protocol fact proves wrong on clone: re-probe and record before coding.
- A load-bearing fix's mutation cannot be made to fail any test: repair the instrument first.
- Branch red beyond one working session: land the green subset.
- Rehearsal fails twice for the same cause: record as a cutover blocker.
