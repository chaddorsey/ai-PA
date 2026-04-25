---
date: 2026-04-24
topic: letta-memfs-upgrade
---

# Letta External MemFS Upgrade

## Problem Frame

The ai-PA Letta ecosystem stores agent memory as Postgres-backed memory blocks. Letta is migrating toward a git-backed "Context Repositories" / MemFS model where agent memory lives as markdown files in a git repo, and Letta itself ships official guidance on Context Repositories as the successor to both memory blocks and archival memory. Long-term direction from Letta: "Legacy server memory tools like `core_memory_replace` will be removed in favor of straightforward filesystem operations on git-backed context repositories."

Self-hosted Letta does **not** ship built-in git-host support; official docs point at a `git http-backend` sidecar labeled "not officially supported." The community-maintained `letta-external-memfs` repo (Fimeg) provides the recommended self-host path via a small set of patches and has been **endorsed by the Letta team** as the recommended self-hosted memfs approach. Our Letta server (0.16.7) and letta-code client (0.23.8) both meet the minimum supported versions (0.16.6+ server, 0.19.6+ client).

Motivation for upgrading now:
- Align with Letta's direction before `core_memory_*` tool deprecation lands.
- Gain git-audit history, external editability, and conflict-aware concurrent subagent memory writes.
- Unlock the pa-web-ui letta-code subprocess path (shipped 2026-04-20) to the full memfs experience it's designed for.

The upgrade is non-trivial because (a) Letta's memfs model is per-agent and filesystem-tool-oriented, which doesn't fit every agent in our ecosystem, and (b) we have multiple external services writing directly to Postgres blocks as a shared-state IPC mechanism.

## Requirements

**Memfs host infrastructure**
- R1. Stand up a self-hosted Gitea instance on `pa-internal` as the external git host for agent memory repos.
- R2. Gitea runs in `docker-compose.yml` on port 3030 (verified free), using a persistent Docker volume.
- R3. Gitea data is included in the nightly backup pipeline alongside Postgres, Letta volumes, and other services (`deployment/scripts/backup.sh`).
- R4. The server-side memfs storage volume (`/root/.letta/memfs`) is persisted and backed up (it holds bare repos sync-from-git reads from).

**Patched Letta server image**
- R5. Fork `letta-ai/letta` at the pinned 0.16.7 commit and apply all three server patches from `letta-external-memfs`:
  - `server_memory_sync_endpoint.patch` (required — exposes `POST /v1/agents/{id}/memory/sync-from-git`)
  - `server_sync_delete_propagation.patch` (hardening — makes sync delete orphan Postgres blocks when their git file is removed)
  - `server_system_only_blocks.patch` (hardening — gates which `.md` paths become blocks via `LETTA_MEMFS_BLOCK_PATH_PREFIXES`)
- R6. Server runs with `LETTA_MEMFS_SERVICE_URL=local` and `LETTA_MEMFS_BLOCK_PATH_PREFIXES=system/`.
- R7. Server image is built and tagged under our own name (e.g. `letta-local:0.16.7-memfs-v1`) and referenced from `docker-compose.yml`. The existing `letta:pg-0.16.7` image remains available for rollback.

**Patched letta-code client**
- R8. Install a patched letta-code into a project-local directory (e.g. `~/code/letta-code-memfs/`) with `memoryGit.ts.patch` applied, built via `bun run build`. Homebrew-installed `/opt/homebrew/bin/letta` remains untouched.
- R9. Project-local letta-code is used by pa-web-ui subprocesses and LettaBot's letta-code subprocess spawner. The choice of binary is controlled by an env var so rollback is a config change, not a rebuild.
- R10. Client env vars:
  - `LETTA_MEMFS_GIT_URL=https://token@gitea.pa-internal/agents/{agentId}.git`
  - `LETTA_MEMFS_LOCAL=1` (same-network optimization)
- R11. The Gitea access token is stored in `.env` (gitignored) and scoped to the memory-repos organization only.

**Pilot validation (canary)**
- R12. A dedicated pilot agent (either existing candidate TBD or a fresh `memfs-canary`) runs through all validation scenarios before any production agent is migrated.
- R13. The canary is exercised via **only** the letta-code CLI — no Telegram, no Slack, no pa-web-ui, no scheduling-orchestrator — so failures cannot cascade.
- R14. The canary is seeded with **duplicated** (copy-by-value, not attached) versions of real production blocks (e.g. a duplicate of `extracted_tasks`, a duplicate awareness block) so the test load resembles real-world memory shape and size.
- R15. Six validation tests pass before MC is touched:
  1. **Smoke**: tag agent with `git-memory-enabled` → write a file under `system/` via bash → confirm block appears in Postgres via `/v1/blocks?agent_id=…`.
  2. **Round-trip**: agent edits a `system/` file via its bash tool → git push → run `sync-from-git` → verify block content matches.
  3. **External edit**: commit to Gitea via web UI or direct `git push` from the host → run `sync-from-git` → verify block updates.
  4. **Delete propagation**: `git rm system/notes.md` → push → run `sync-from-git` → verify the corresponding block is deleted (validates `server_sync_delete_propagation.patch`).
  5. **Path filter**: add `reference/noise.md` with `LETTA_MEMFS_BLOCK_PATH_PREFIXES=system/` set → run `sync-from-git` → verify no block is created for `reference/noise` (validates `server_system_only_blocks.patch`).
  6. **Binary handling**: push a file matching `._*` or a PDF → verify graceful failure or skip, not a 500 (validates binary-file robustness).
- R16. After tests pass, the canary runs for a minimum of 48 hours with daily editing activity before any production agent is migrated.

**Production agent migration (Path A — Minimal scope)**
- R17. The initial production migration scope is **MC only** (`agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef`). Tasks, Calendar, Email, Docs-and-Transcripts, Pulse, Media, and the scheduling-orchestrator agents all **remain on Postgres blocks** in this phase.
- R18. MC migration requires pre-verified compatibility on all three client paths: pa-web-ui letta-code subprocess, LettaBot Telegram letta-code subprocess, and scheduling-orchestrator REST calls. See Outstanding Questions (Phase 5 criteria).
- R19. MC migration has an explicit rollback: remove the `git-memory-enabled` tag, switch `docker-compose.yml` back to the pre-memfs image, restart letta.

**Shared state preservation (explicit non-migration)**
- R20. The following production blocks **remain as Postgres blocks permanently** (or until their external writers are re-architected). They are lightweight IPC between external services and agents and do not fit memfs's per-agent model:

| Label | ID | Writers | Readers |
|---|---|---|---|
| `queued_tasks_from_email` | `block-e64dcb37-aae3-416f-8565-5f2a23f53325` | gmail-watch-service | Tasks agent |
| `queued_tasks_from_slack` | `block-033a720d-1f13-44a2-a5cb-b5edde418ea1` | slackbot shortcuts | Tasks agent |
| `queued_tasks_from_meetings` | `block-809efd9b-e2ca-4d11-af89-9a1c7710716c` | scheduling-orchestrator | Tasks agent |
| `queued_tasks_from_drive` | `block-cfbba10b-5796-408d-8540-72a7b31bcb97` | drive-rag-service | Tasks agent |
| SPARK queue | `block-534bb56d-f7f1-4ea4-b2d9-20dc75eca03a` | slackbot, spark-queue-drain | Tasks agent |
| `extracted_tasks` | `block-90300b77-6b72-42cb-8e67-c74fbb497cf6` | Tasks agent | pa-web-ui sidebar, Tasks agent |

- R21. `pa-routing-handler`'s coordination-handler cross-agent block orchestration stays on Postgres blocks — the pattern (attach/detach shared blocks across agents for coordinated conversations) cannot be expressed in memfs's per-agent model.

**Operational hygiene**
- R22. Server patch hygiene follows Vee's verified guidance — sync must target the bare repo path `/root/.letta/memfs/repository/{org_id}/{agent_id}/repo.git/` with `--git-dir=…` and `--update-head-ok`, not any working checkout. The README's pre-fix minimal pattern is **wrong** and must not be used.
- R23. `org_id` for self-hosted is `org-00000000-0000-4000-8000-000000000000` and must be parameterized in all scripts (auto-discoverable via `GET /v1/agents/{id}`'s `organization_id` field).
- R24. Sync invocations default to `?recompile=false`; `?recompile=true` only runs when `system/` tree actually changed (diff-gated pattern from Fimeg README).
- R25. `.gitignore` in every memory repo excludes `._*`, `.DS_Store`, and non-markdown extensions to sidestep the upstream UTF-8 decode crash on binary files.

## Success Criteria

- MC carries the `git-memory-enabled` tag, its `system/` memory is authored as git files, and all three production client paths (pa-web-ui, Telegram via LettaBot, scheduling-orchestrator) continue to work without regression for ≥ 7 days post-migration.
- `git log` in MC's memory repo shows a real audit trail of its own memory edits, editable from any machine we run letta-code on.
- Nightly backup includes Gitea data and the Letta memfs volume; a restore from the most recent backup reproduces the memfs state.
- None of the six Postgres-block shared queues (R20) are disrupted by the migration.
- Rollback path is exercised at least once on the canary: tag removed → image reverted → agent returns to pre-memfs memory behavior with no data loss.

## Scope Boundaries

- **Not migrating in this round**: Tasks, Calendar, Email, Docs-and-Transcripts, Pulse, Media, scheduling-orchestrator's agents, pa-routing-handler's coordinated agents. Revisit after MC has been on memfs for 2+ weeks with no issues.
- **Not building**: a generic "migrate any REST agent to memfs" abstraction. Per-agent migrations are one-off with human review.
- **Not changing**: the six shared queue blocks (R20) or the external services that write to them.
- **Not replacing**: the existing `letta:pg-0.16.7` image — we run the patched image alongside, flag-gated by docker-compose image selection.
- **Not using**: GitHub as the git host for this phase (tokens leaving the network, tokens-in-URL exposure). Gitea local-only.
- **Not imposing**: a rigid directory structure on agent memfs beyond `LETTA_MEMFS_BLOCK_PATH_PREFIXES=system/`. Agents curate their own `reference/`, `notes/`, `projects/`, etc.

## Key Decisions

- **Git host: Gitea in docker-compose, not GitHub or the official sidecar.** Rationale: all-local, no tokens leaving the network, backup fits our existing pipeline, and the `letta-external-memfs` patches already target this shape.
- **Patched binaries live alongside, not in place of, stable ones.** Rationale: rollback is a config change, not a rebuild; Homebrew `letta` stays usable for non-PA work.
- **Path A (MC + letta-code clients only) for initial migration, not universal migration.** Rationale: memfs only becomes useful with filesystem tools; REST-only agents (Tasks, Calendar, etc.) would lose self-editing ability without gaining anything.
- **Six shared queue blocks explicitly do not migrate.** Rationale: they are external-service → agent IPC, not agent memory; memfs's per-agent model cannot express their write semantics.
- **Canary is exercised only via letta-code CLI.** Rationale: the point of a canary is that failures cannot cascade into production paths.
- **Canary is seeded with duplicated real blocks, not attached.** Rationale: attaching would couple canary edits to production shared state; duplicates give realistic shape without coupling.
- **`LETTA_MEMFS_BLOCK_PATH_PREFIXES=system/` from the start.** Rationale: without it, every `.md` anywhere in the repo becomes a Postgres block, polluting the block namespace and defeating the point of letting the agent curate freely.

## Dependencies / Assumptions

- Letta server 0.16.7 Postgres schema is compatible with the patched image without migrations (the patches modify request routing and sync logic, not schema). **Needs verification before image swap.**
- pa-web-ui and LettaBot's letta-code subprocesses can be pointed at the patched letta-code via env var / path selection without code changes. **Needs verification.**
- `GitEnabledBlockManager` is wired up on the server when `LETTA_MEMFS_SERVICE_URL=local` is set; otherwise the sync-from-git endpoint returns 409. (Stated in the server patch.)
- Vee's Letta-source verification at clone-head (paths `local.py:27`, `block_manager_git.py:564-596`, `path_mapping.py:20-25`, `git_operations.py:37-41,77-80`) applies to 0.16.7 as well as 0.16.6; patches use diff context rather than hash pinning, so they should apply cleanly.
- The pre-existing Apr 22 restarts of letta/letta-code/pa-web-ui/gws-bridge (documented in session history) are unrelated to this upgrade and do not need to be reverted.

## Outstanding Questions

### Resolve Before Planning
- _(none — canary resolved to fresh `memfs-canary`; Phase 5 criteria deferred to a standalone user discussion separate from planning)_

### Resolved
- **R12 canary identity**: Create a fresh `memfs-canary` agent for Phase 1. Minimal tool surface, connected only via letta-code CLI, disposable. Decided 2026-04-24.

### Deferred to User Discussion (not blocking this plan)
- **Phase 5 MC go/no-go criteria**: User wants to discuss independently of this plan. Placeholder criteria in R18/R19 of this doc are not yet binding; the plan document defers Phase 5 detailed work until these criteria are agreed.

### Deferred to Planning
- **[Affects R8, R9][Technical]** How do we build and version-pin letta-code from source? Is there a `bun run build` output we can install into `~/code/letta-code-memfs/` and reference by absolute path, or does it need to be on PATH?
- **[Affects R2, R3][Technical]** Gitea docker-compose shape: `gitea:latest` with SQLite backend, on `pa-internal` network, persistent volume at `/var/lib/gitea`, admin user bootstrapped via env vars. Needs concrete YAML + backup-script delta.
- **[Affects R5, R7][Technical]** Fork-and-build workflow for the patched Letta image: do we maintain a forked repo at `letta-ai/letta@0.16.7 + our patches` on GitHub, or build directly from a local checkout in `deployment/` with patches re-applied on every rebuild?
- **[Affects R18][Needs research]** When MC has `git-memory-enabled` and a scheduling-orchestrator REST call arrives wanting to append to an MC block, what actually happens? Does the REST call succeed and write to Postgres (which then drifts from git) or fail? The "`/memfs` detaches the memory tool" wording in the blog is about the agent-facing tool, but external writers to `/v1/blocks/{id}` are a different surface. Needs an empirical test on the canary.
- **[Affects R14][Technical]** Block duplication tooling: write a small script that, given a source block ID and a target agent, copies the block content into a new block labeled identically but attached only to the target. Needed before canary tests.
- **[Affects R15, R16][Technical]** Exact bash snippets for each of the six validation tests, with pass/fail assertions that can be wrapped in a small test runner.
- **[Affects R22, R24][Technical]** Sync automation: a per-agent sync wrapper (`scripts/memfs-sync.sh` or similar) that implements the diff-gated `?recompile=false` default with `?recompile=true` only when `system/` tree actually changed. Should be runnable manually and schedulable via scheduler-service if we want auto-sync on external edits.

## Next Steps

→ `/ce:plan` for Phases 0–4 implementation sequencing. Phase 5 (MC migration) stays at roadmap level until user-discussion-level criteria are agreed separately.
