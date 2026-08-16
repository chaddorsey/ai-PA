---
title: "Continuity Controller cutover (terminal-first) — runbook"
status: REHEARSED-ON-CLONE (2026-08-16); live execution is a separate operator-attended goal
origin: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md (Unit C10b)
---

# Continuity Controller cutover — terminal-first (R19/G7)

Scope per the execution goal (`docs/plans/2026-08-15-007-…-goal.md`): **terminal-first** —
App Server + controller live, scheduler re-pointed, `lc-local-backend` writers quiesced.
pa-web-ui continues on the Docker backend in parallel; the web flip and its chat-transport
retirement land with C9 in the follow-on goal.

Everything below was REHEARSED on the clone stack (`:4599` server, `:4610` surface, `:4611`
ingress, state in `/private/tmp/continuity-clone-state`) during C1–C8; the rehearsal evidence
is linked per step. **Live execution requires the operator present** and the two
NEEDS-OPERATOR-REVIEW decisions resolved.

## 0. Semantics changes to acknowledge before starting

- **202-on-accept**: after the re-point, a scheduler execution record means *delivered to the
  controller*, not *turn completed*. Turn outcome lives in the controller journal
  (`continuity-controller queue`, `turn_events`). This is a deliberate design decision.
- **Detach semantics invert**: leaving the terminal mid-turn no longer cancels the turn (the
  anchor+worker hold every hot runtime). The old raw-WS caveat applies only under break-glass.
- **Break-glass posture**: `letta-continuity --direct` (or a flag'd `--url`) attaches straight
  to the App Server WS. While it is in use, single-submitter ownership and attribution
  guarantees are SUSPENDED — it exists for controller-down emergencies and says so on startup.

## 1. Preconditions (all green on clone, 2026-08-16)

- [x] C1 spike GO (`docs/plans/2026-08-15-006-controller-spike-findings.md`)
- [x] C3 soak: launchd worker+anchor ≥1h, dual subscriptions, fresh liveness
- [x] C4 P3/P4 live (controller kill mid-tool → exactly-once ordered journal; server kill
      mid-turn → FAILED-VISIBLE, queue continues)
- [x] C5 P5 live on permission-flipped clone (approval held with zero surfaces, survives
      restart via the anchor, answerable on attach)
- [x] C6 terminal transport swap (UX contract green; detach-inversion live)
- [x] C7 10:55 live (real scheduler job → ingress → unseen → presented+consumed on attach;
      unauthenticated POST → 401 journaled)
- [x] C8 direct lane live (1ms accept→submit; zero Kinara turns in window; digest batched)
- [x] **DECIDED (operator, 2026-08-16): PATH-TOKEN** for the ingress secret — config-only
      re-point; the secret's appearance in local scheduler logs is accepted; revisit bearer
      when `actions.py` is next touched. Job dispositions:
      `docs/plans/2026-08-15-006-scheduler-job-inventory.md` (zero active `route=letta` jobs).
- [x] **DECIDED (operator, 2026-08-16): quiesce tiers approved; Tier-3 = option (a)** —
      bootout the runner at cutover, re-point the two `route=local` self-check jobs to the
      controller ingress in the same sitting, and land the memfs-sync/extension-tools
      migration as the first post-cutover unit. Rollback posture verified: no data migration
      anywhere (process swaps over unchanged state); whole-stack rollback ≈1 minute; runner
      rollback implies whole-stack rollback (single-writer tripwire), which is acceptable at
      that cost.

## 2. Cutover steps (terminal-first)

Each step names its clone rehearsal. Total attended time ≈ 20 min.

1. **Snapshot**: `./deployment/scripts/backup.sh --verbose`; note `git rev-parse HEAD`.
   Add the controller state dir to backup.sh host-data section if not yet merged.
2. **Quiesce the incumbent `lc-local-backend` writers.** Discovered live 2026-08-16
   (process table + plist env + lsof), in three tiers:

   **Tier 1 — replaced by the cutover itself:**
   - `scripts/restore-letta-app-server.py` (the stopgap; it is the PARENT of today's :4577
     `letta server --backend local --openai-api`) → kill both; the supervised sole owner
     (`com.ai-pa.letta-app-server`) takes over. `letta-push-receiver` (enrichment) stays —
     it is a `/v1/responses` CLIENT of :4577, not a writer.

   **Tier 2 — straightforward quiesce:**
   - **Letta Desktop's local-backend client** (`letta.js remote … --backend local`, the
     PID that holds the `crons.json` scheduler lease — lease tasks are EMPTY): quit
     Letta.app (or kill the child). Keep it closed until it is re-pointed or retired.
   - **Interactive fleet TUIs** in tmux (`agent-supervise` × kinara/mc, email, tasks,
     calendar, pulse → `~/bin/letta-<slug>` → `letta --backend local --agent …`): each is a
     direct writer. Close the sessions; the Kinara/MC surface is replaced by
     `letta-continuity` immediately; the other agents' TUIs reopen as `letta-continuity
     --agent <id> --conversation <registry-thread>` or stay closed.

   **Tier 3 — THE operator decision: `com.ai-pa.letta-local-runner` (:8920).** Its plist
   pins `LETTA_LOCAL_BACKEND_DIR=lc-local-backend`; every invocation spawns a
   `letta --backend local` writer. It is also the fleet's execution substrate: the two
   active `route=local` scheduler self-checks, the pa-tools extension-tool bridge, the
   memfs Gitea sync wrapper, and warm-pool recipes all ride it. Options:
   (a) **bootout the runner at cutover and accept those flows paused** until they re-point
   (scheduler jobs → controller ingress as `route=letta`; memfs-sync/extension-tools
   migration = a follow-up unit) — cleanest single-writer posture; (b) defer cutover until a
   runner migration lands; (c) leaving it running is NOT an option — the supervisor's
   foreign-writer tripwire will (correctly) fight it. **DECIDED (operator, 2026-08-16):
   option (a).** Enrichment is unaffected either way (it rides `/v1/responses`, which both
   the old and new server serve; the swap gap is 503-retried).

   **Confirmed NON-writers (no action):** `letta-teams-daemon` (Docker `:8283`), `letta-cleanup`
   (repo dir only), `letta-code-verify`, Claude sessions. The supervisor's flock tripwire +
   foreign-writer rescan backstops stragglers either way.
3. **Load the App Server plist** (`letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist`
   → `~/Library/LaunchAgents`, hand-synced per repo convention) and verify
   `app_server_info` on :4577 reports the pinned version. Retire the
   `scripts/restore-letta-app-server.py` stopgap (unload/remove its trigger).
   *Rehearsed: the clone server served C1–C8 throughout.*
4. **Seed the controller registry** (production state dir
   `~/Library/Application Support/continuity-controller`):
   `continuity-controller registry add --agent <id> --label <label> [--default]` per hot
   runtime (creates REAL conversations — the `default` alias is banned by design, C1 S3).
   Registry rows to create: Kinara/MC default thread (+ any standing specialist threads).
   *Rehearsed: clone registry, two runtimes, default stamp.*
5. **Set the ingress secret**: generate, store in the worker plist env
   (`CONTINUITY_INGRESS_SECRET`); without it the ingress stays down (fail-closed).
   *Rehearsed: clone plist env.*
6. **Load the controller plists** (`clients/continuity-controller/launchd/*.plist` →
   `~/Library/LaunchAgents`, production copies WITHOUT the clone env overrides). Verify:
   liveness file fresh; `launchctl list` shows both; logs under
   `~/Library/Logs/continuity-controller/`. *Rehearsed: full clone soak.*
7. **Re-point the scheduler**: edit `LETTA_CALLBACK_URL` in the compose env to
   `http://host.docker.internal:4611/t/<secret>/v1/agents/{agent_id}/messages`
   (**path-token form — operator decision 2026-08-16**). Recreate only the
   scheduler container (`docker-compose up -d --no-deps scheduler-service`).
   *Rehearsed: a real scheduler job delivered through the clone ingress with the bearer (C7).*
8. **Flip the terminal**: deploy `clients/letta-terminal/bin/letta-continuity` → `~/bin`
   (controller transport is the default; token file resolves to the production state dir).
   *Rehearsed: all C6/C8 live scenarios ran through the real binary.*
9. **Verification checklist** (all rehearsed on clone 2026-08-16, see §3):
   - [ ] P1 `live.detach-hold.contract.test.ts` against :4577 (scratch agent)
   - [ ] P2 `live.contract.test.ts` (protocol + permission pin)
   - [ ] C4 gate `live.controller.contract.test.ts`
   - [ ] P3/P4 scripted (kill worker mid-tool; restart App Server mid-turn) — journal
         exactly-once + FAILED-VISIBLE
   - [ ] P5 stays clone-only (permission flip is not for live); the unrestricted pin is the
         production tripwire
   - [ ] 10:55: one-off scheduler job with zero surfaces → unseen → presented on attach
   - [ ] `@specialist` direct exchange + digest
10. **Announce**: new semantics (202-accept, detach inversion, /approve·/deny, @alias,
    /bind) to the operator surfaces that care.

## 3. Rollback (< 1 minute, rehearsed)

```
launchctl unload ~/Library/LaunchAgents/com.ai-pa.continuity-controller.plist \
                 ~/Library/LaunchAgents/com.ai-pa.continuity-anchor.plist
# scheduler: restore the previous LETTA_CALLBACK_URL env and recreate the container
# terminal: `letta-continuity --direct` works immediately (break-glass, guarantees suspended)
```

Clone rehearsal 2026-08-16: unload → break-glass one-shot (exit 0, banner shown) → reload
measured **1s total**; liveness fresh again within one probe interval. The controller's state (registry,
journal, queue, routes) is SQLite — nothing to roll back; a re-load resumes from it
(recovery reconciles in-flight turns via the transcript, proven as P3/P4).

## 4. Operational notes

- Liveness: `<state>/liveness.json` (atomic; stale = unhealthy — the probe is a real `sync`
  round-trip). Journal/queue inspection: `continuity-controller queue`, `routes list`,
  `registry list`.
- The journal grows unbounded for now: retention/compaction is deliberately deferred to the
  post-cutover soak or the first size threshold (plan, Key Technical Decisions).
- Backup: include `~/Library/Application Support/continuity-controller` in
  `deployment/scripts/backup.sh` host-data (pending its next edit).
- Known risks accepted by operator decision 2026-08-15: uncapped `notify_operator` /
  `manage_routes` / fan-out levers (journal audit only); controller-down = operator lockout
  except break-glass.
