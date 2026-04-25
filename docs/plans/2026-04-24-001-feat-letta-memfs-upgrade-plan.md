---
date: 2026-04-24
status: active
origin: docs/brainstorms/2026-04-24-memfs-upgrade-requirements.md
---

# Letta External MemFS Upgrade — Implementation Plan

## Problem Frame

Upgrade our self-hosted Letta (0.16.7) + letta-code (0.23.8) stack to the `letta-external-memfs` model so MC can eventually author its memory as git-backed markdown files rather than Postgres blocks. This plan covers Phases 0–4: infrastructure prep, patched image/client builds, block-duplication tooling, canary agent validation. Phase 5 (MC migration) is intentionally roadmap-only pending user-agreed go/no-go criteria (see origin doc).

## Scope Boundary

**In scope**: Gitea infrastructure, patched Letta server image, patched letta-code client build, block-duplication helper, `memfs-canary` agent creation, six validation tests, backup integration.

**Out of scope for this plan**: production agent migration (MC and others), changes to any of the six preserved shared-queue blocks (R20 in origin), changes to pa-routing-handler coordination, GitHub-based git hosting, removal of the existing `letta:pg-0.16.7` image.

## Requirements Traceability

This plan implements R1–R16 and R22–R25 from the origin doc. R17–R21 (production migration) are covered at roadmap level in Phase 5 only.

## High-Level Technical Design

*Directional guidance for review, not implementation specification.*

```
External surface                                Internal
─────────────────                               ────────
                     ┌─ Gitea (new, :3030) ←──── letta-code
                     │    pa-internal           (patched, project-local)
                     │    backed up nightly         │
                     │                              │ LETTA_MEMFS_GIT_URL
                     ▼                              │
  agents/<agent>.git  ◄─── fetch ───┐               │ clones on session init
                                    │               │
                                    │               ▼
                     ┌──────────────┴──────────────────────────┐
                     │ letta-server (patched image)            │
                     │  /root/.letta/memfs/repository/         │
                     │    <org>/<agent>/repo.git (bare)        │
                     │                                         │
                     │  POST /v1/agents/{id}/memory/           │
                     │       sync-from-git?recompile=…         │
                     │    ─→ GitEnabledBlockManager            │
                     │    ─→ rebuild Postgres blocks           │
                     │       (add/update/DELETE, gated by      │
                     │        LETTA_MEMFS_BLOCK_PATH_PREFIXES) │
                     └──────────────┬──────────────────────────┘
                                    ▼
                            Postgres (block cache)
```

The old image (`letta:pg-0.16.7`) and the Homebrew-installed `letta` binary remain untouched so a rollback is a `docker-compose.yml` image edit + `docker-compose up -d letta`, no rebuild.

## Implementation Units

### Phase -1 — Reconcile Task tool disablement (REVISED 2026-04-25)

**Why this is Phase -1**: Every consolidation pattern in the sibling brainstorm depends on `Task(...)` invocations working. Task is currently in our `--disallowedTools`.

**Reference**: Final source-grounded diagnosis at:
- `docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md` (definitive)
- Earlier docs (`-diagnosis.md`, `-wire-capture.md`) carry SUPERSEDED headers but show the diagnostic chain

**Final root cause** (after milestone capture + registry refresh + Q3 confirmation):

`POST /v1/agents/` rejects model handles that aren't registered in `provider_models`. Letta-code's subagent agent-creation passes `model: "<handle>"` (string), forcing handle resolution. Our agents use `litellm/X` handles (custom convention) which aren't in the registry under any provider — LiteLLM's `/v1/models` exposes bare model names that Letta prefixes with provider name (`openai-proxy/X`), not `litellm/X`. Subagent POST → 404 HandleNotFoundError → subagent process exits silently → parent's stdout parser sees nothing → `Failed to parse subagent output: Unexpected end of JSON input` → LLM observes failure, retries, eventually gives up.

The chain of misattribution:
- Initial framing: server-side approval-state corruption (#3205's original symptom)
- Wire capture proved the server's approval flow is fine
- Then framing: letta-code's `--new-agent -p` silently fails in headless
- Milestone capture proved it's specifically a 404 on `POST /v1/agents/`
- Server traceback proved the 404 is `HandleNotFoundError` for `letta/auto` and our `litellm/*` handles

**Pre-conditions already addressed (2026-04-24/25)**:
1. Base tools (`web_search`, `fetch_webpage`, `run_code`, `semantic_search_files`) missing — populated via `POST /v1/tools/add-base-tools`. One-time fix.
2. `openai-proxy` provider registry stale (last sync 2026-03-14) — refreshed via `PATCH /v1/providers/{id}/refresh`. 23→39 active rows. Zero unintended deletions. Now reflects current LiteLLM catalog including `kimi-k2p6`, all gpt-5.4 models, fireworks models.

**These pre-conditions alone do NOT fix Task** — our agents still use `litellm/X` handles which aren't (and won't be) in the registry under any provider. The actual fix is Path C below.

#### Path C — letta-code patch: send `llm_config` object on subagent POST (CHOSEN)

**Why this is the right fix**: Per Letta team agent's source verification (Q3, 2026-04-25), `server.py:540`'s `if request.llm_config is None:` guard short-circuits handle resolution entirely when a full `llm_config` object is sent. Inner `handle` field is stored verbatim. So sending `llm_config: parentAgent.llm_config` bypasses the registry mismatch without requiring agent renames or SQL inserts.

- [x] **C1.1 Patch artifact locked** (2026-04-25)
  - At `letta-memfs-patches/patches/letta_code_self_hosted_handle_fix.md`
  - Applied via `letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py` (idempotent Python script, atomic write, byte-exact match-and-replace)
  - All five outstanding questions resolved (see resolved-questions section in patch artifact)

- [x] **C1.2 Project-local letta-code installed and patched, restructured into repo** (2026-04-25)
  - Initial install: `npm install @letta-ai/letta-code@0.24.2` into `~/code/letta-code-memfs/`
  - **Step 1 restructure (2026-04-25 evening)**: moved to `/Volumes/main-drive/ai-PA/letta-code-patched/` so the artifact lives under repo + backup umbrella alongside the patch script
  - Build flow: `letta-code-patched/build.sh` runs `npm install` + applies `letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py` idempotently
  - `package.json` pins `@letta-ai/letta-code@0.24.2`
  - `.gitignore` excludes `node_modules/` (artifact reproducible from build.sh, not committed)
  - Backup `letta.js.original` retained alongside patched `letta.js` for rollback
  - Patch applied: 2 createAgentRequestBase blocks replaced, 8 `[PATCH-3205]` markers in file
  - Binary verified: `node --check` passes, `--version` returns `0.24.2 (Letta Code)`, end-to-end Task call against a `litellm/X`-handle pilot succeeds (`STEP1-VERIFY` file written by subagent)

- [x] **C1.3 Wrapper script for LETTA_CODE_BIN** (2026-04-25)
  - At `letta-memfs-patches/letta-patched-wrapper.sh`
  - Resolves repo root via `BASH_SOURCE` so it works regardless of where the repo lives
  - Subagent spawns inherit via the existing `LETTA_CODE_BIN` env-var mechanism (already built into letta-code via `resolveLettaInvocation` + `ensureLettaShimDir`)
  - Set `LETTA_CODE_BIN=<wrapper-path>` and parent + all subagent descendants use the patched copy

- [x] **C1.4 Validated on a fresh pilot agent** (2026-04-25)
  - Pilot created with `litellm/gpt-4.1-mini` handle (matches production agents)
  - Task workload: `Use Task subagent_type=general-purpose to write 'PATH-C-WORKS-V2' to /tmp/path-c-test.txt`
  - Result: subagent_status=success, file written correctly, no HandleNotFoundError, no retry cascade
  - Pilot + subagent cleaned up post-test

- [x] **C1.5 Validate all four `INTERACTIVE_APPROVAL_TOOLS` + recall + nested** (2026-04-25)
  - Test 1: Task single subagent — ✅ 1× Agent, file written, 2 turns, success
  - Test 2: Task chained (3 sequential subagents) — ✅ 3× Agent + 1× Bash, all 3 files written, 5 turns, success
  - Test 3: TodoWrite — ✅ 1× TodoWrite, list created with mixed states, 2 turns, success. **Memory note saying TodoWrite was permanently broken is stale; it works in 0.24.2 with Path C.**
  - Test 4: AskUserQuestion — ⚠️ LLM did not pick AskUserQuestion despite directive prompt (chose Skill or Agent). `--yolo` headless mode likely doesn't expose AskUserQuestion to the LLM since there's no user to ask; not a Path C concern. Will verify in interactive pa-web-ui mode at C1.6.
  - Test 5: EnterPlanMode/ExitPlanMode — ✅ 1× EnterPlanMode + 1× ExitPlanMode + Read/Grep/Glob, 15 turns, success
  - Test 6: Task(recall) fork-based — ✅ 1× Agent (recall variant), forked successfully, returned report, 2 turns, success
  - Test 7: Nested Task — ✅ 1× Agent, nested file produced (`/tmp/c15-nested.txt`, 1004 bytes summarizing prior test activity), 2 turns, success
  - Test 8: Sustained 5-Task workload — ✅ 5× Agent, all 5 files written (`/tmp/c15-sustained-1..5.txt`), 6 turns, 45s, no retry cascades
  - **Aggregate**: 0 HandleNotFoundError in server logs across all 9 tests. 0 PATCH-3205 errors. All `result.subtype=success`.

- [ ] **C1.6 Re-enable Task in production clients**
  - Adjust `lettabot/lettabot.yaml` to remove `Task` from `disallowedTools`
  - If C1.5 validates other tools too, also remove `EnterPlanMode`, `AskUserQuestion`. Keep `TodoWrite` blocked per memory note (separate `manage_todo` tool replaces it)
  - Adjust pa-web-ui's letta-code subprocess invocation flags
  - Switch pa-web-ui and LettaBot to `LETTA_CODE_BIN=<patched>` so production goes through the patch
  - Watch for any new failure patterns over 24h before declaring stable

- [ ] **C1.7 Coordinate with upstream**
  - Letta team agent (per 2026-04-25) is drafting a GitHub issue body covering the empty-`provider_models`-for-base-providers issue + the `model: <string>` vs `llm_config: <object>` POST asymmetry
  - Cameron reviews/files
  - Once filed: link from this plan + add comment with our patch as a candidate workaround
  - Track upstream resolution. If/when a server-side `sync_base_providers` fix lands, our patch becomes unnecessary; remove it on next letta-code upgrade cycle

#### Path A — SQL stopgap (interim only, if Task needs to work BEFORE Path C ships)

- [ ] **A1.1 Run `scripts/letta-handle-stopgap/apply.sql`** to insert `litellm/X` mirror rows
- [ ] **A1.2 Verify** via `verify.sql`
- [ ] **A1.3 Document the operational footnote**: "do not run `PATCH /v1/providers/{id}/refresh` while these rows are needed; if you do, re-run apply.sql afterward"
- [ ] **A1.4 Roll back via `rollback.sql`** once Path C ships

This is a band-aid, not a fix. Use only if blocked.

#### Path R — Resolve `--new-agent -p` headless silent failure (DEPRECATED — was a wrong-direction earlier draft)

- [ ] **R1.1 File upstream issue against `letta-ai/letta-code`**
  - Repo: `letta-ai/letta-code` (separate from `letta-ai/letta`)
  - Title: "letta --new-agent -p exits silently in headless mode on self-hosted Letta server"
  - Include: exact command, env vars (LETTA_BASE_URL, LETTA_API_KEY), observed (6s exit, no output, no agent created, no network connection to configured server before exit), confirmation that `letta --agent <existing-id> -p` works fine, version 0.24.2 still exhibits

- [ ] **R1.2 Investigate what `--new-agent -p` actually does**
  - Inspect `letta.js` for the headless-mode entry path (around `exitHeadless`, `processTurn`, `--new-agent` flag handling)
  - Identify the silent-exit path — likely a startup-time gate that returns 0 with no message
  - Could be: profile-selector requires TTY, OAuth check fails silently, model-resolver fails silently, etc.
  - If we find the bug location, attempt a minimal-edit local patch

- [ ] **R1.3 Update GitHub #3205 with corrective comment**
  - Post: "On further investigation, the Task-tool symptom we initially attributed to #3205 is caused by a separate `letta-code` client bug, not server approval state corruption. Filing follow-up at letta-ai/letta-code. Closing the loop on this issue thread to reduce noise."
  - Reduces upstream noise on a closed issue

#### Path B — Bypass `--new-agent` in subagent spawning (workaround if R fails)

- [ ] **B1.1 Locally patch `buildSubagentArgs` in letta-code**
  - File: `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/letta.js` line 72554-72570 area
  - Modify the `else` branch (fresh subagent path) to: (a) call Letta REST API to create the agent first, (b) replace `--new-agent --system <type>` with `--agent <new-id> --new`, (c) preserve `--no-memfs` and other flags
  - The patch must persist across letta-code auto-updates — vendor it as `letta-code-memfs-patches/patches/letta_code_buildSubagentArgs_bypass.patch` and apply at install time

- [ ] **B1.2 Validate Task on patched letta-code**
  - Run the same five-step progression: explore Task, general-purpose Task with filesystem write, chained Tasks, moderate workload, sustained 5-Task workload
  - Success: all complete with subagent results visible in conversation, no LLM retry cascades
  - Failure: collect logs, iterate

- [ ] **B1.3 Coordinate with the external-memfs patch toolchain**
  - Add the letta-code patch to the same vendored-patches set used for the memfs upgrade (`letta-memfs-patches/patches/`)
  - Update Phase 2 of this plan to include applying both patches at letta-code build time

#### Path A — Accept Task remains disabled, ship Path A scope only (last resort)

- [ ] **A1.1 Document acceptance**
  - Create `docs/decisions/2026-04-24-task-tool-deferred.md` capturing: we tried Path R and Path B, neither worked, Task stays in `--disallowedTools`, consolidator patterns are deferred
  - Sibling consolidation brainstorm gets a new "BLOCKED" status section

- [ ] **A1.2 Re-scope consolidation brainstorm**
  - Update `docs/brainstorms/2026-04-24-memory-consolidation-patterns-requirements.md` to mark Task-dependent patterns as deferred
  - Memfs migration plan (this doc) remains valid for Path A scope (MC + letta-code clients, no consolidators)

#### Common to all paths

- [ ] **-1.X Re-enable Task in production clients (only after Path R or B succeeds)**
  - Adjust `lettabot/lettabot.yaml` to remove `Task` from `disallowedTools`
  - Adjust pa-web-ui's letta-code subprocess invocation flags
  - Verify pa-web-ui chat behavior is unchanged
  - Watch for any new failure patterns over 24h before declaring stable

**Gate**: Phases 0–3 may run in parallel with Phase -1. Phase 4 (canaries) cannot start C2 until either Path R or Path B succeeds, OR until we explicitly choose Path A and re-scope. Phase 6+ (universal migration via consolidators) is **hard-gated on Task working**, which is hard-gated on Path R or Path B.

**Decision needed from user**: Pick R or B as the active path. R is cleaner but slower (depends on upstream or our own deep investigation). B is a vendored patch we control, faster to ship.

### Phase 0 — Gitea infrastructure

- [ ] **0.1 Add Gitea service to docker-compose.yml**
  - Modify: `docker-compose.yml` — add `gitea` service on `pa-internal`, port 3030, persistent volume, environment-based admin bootstrap
  - Create: `gitea/` directory with `gitea/app.ini.template` only if we need to override defaults (avoid if possible — prefer env-var config)
  - Image: `docker.io/gitea/gitea:1.22` (current stable at time of writing — verify latest in implementation)
  - Volume: named volume `gitea-data` mounted at `/data`
  - Network: `pa-internal`
  - Healthcheck: `curl -fs http://localhost:3000/api/healthz || exit 1` (internal Gitea port is 3000; we expose 3030 on host)
  - Verification: `docker compose up -d gitea && curl -s http://localhost:3030/api/healthz`

- [ ] **0.2 Bootstrap Gitea admin + organization + agent-memory tokens**
  - Create: `scripts/gitea-bootstrap.sh` — idempotent; creates admin user (if missing), creates `agents` organization, generates a scoped PAT with repo:read/write on that org
  - Output: writes `GITEA_MEMFS_TOKEN=...` to `.env` (gitignored) and prints the token URL shape `https://$USER:$TOKEN@gitea:3000/agents/{agentId}.git`
  - Verification: `curl -u user:token https://…/api/v1/orgs/agents` returns 200

- [ ] **0.3 Extend nightly backup to include Gitea**
  - Modify: `deployment/scripts/backup.sh` — add a Gitea leg: `docker exec gitea gitea dump -c /data/gitea/conf/app.ini -f /tmp/gitea-dump.zip` then `docker cp gitea:/tmp/gitea-dump.zip $BACKUP_PATH/`
  - Modify: `deployment/scripts/backup.sh` — add a volume dump for `letta-memfs` (the patched-server's `/root/.letta/memfs` volume) via `docker run --rm -v letta-memfs:/src -v $BACKUP_PATH:/dst alpine tar czf /dst/letta-memfs.tgz -C /src .`
  - Verification: run backup manually; confirm both artifacts present and reasonable size

- [ ] **0.4 Test full Gitea restore path**
  - Create: `deployment/scripts/gitea-restore.sh` — minimal script that takes a `gitea-dump.zip` and restores via `gitea restore-repo`
  - Test: take a backup, delete the `gitea-data` volume, restore, confirm orgs/repos/tokens survive
  - Verification: documented in the script's own help output

**Test file**: `tests/integration/test_memfs_backup_restore.sh` — a shell test that exercises 0.3 + 0.4 end to end on a throwaway compose project.

**Test scenarios**:
1. Backup runs cleanly with Gitea up, produces `gitea-dump.zip` and `letta-memfs.tgz`
2. Restore from dump into a fresh Gitea instance reproduces the orgs + repos
3. Backup runs cleanly when Gitea is *down* (should skip with a warning, not fail the whole backup)

### Phase 1 — Patched Letta server image

- [ ] **1.1 Vendor the patches locally**
  - Create: `letta-memfs-patches/` directory at repo root containing a git submodule or direct-checkout of `github.com/Fimeg/letta-external-memfs` at a pinned commit
  - Pin: record the commit SHA in `letta-memfs-patches/PINNED_COMMIT.txt` so rebuilds are reproducible
  - Rationale: avoid depending on upstream main moving under us

- [ ] **1.2 Create forked Letta source build directory**
  - Create: `letta-memfs-build/` directory with a `Dockerfile` that (a) clones `letta-ai/letta` at 0.16.7, (b) applies all three server patches from `letta-memfs-patches/patches/`, (c) builds the server image
  - Base: `FROM letta/letta:pg-0.16.7` if we can overlay, else build from source — verify which is feasible
  - Dockerfile pattern: COPY patches → `RUN cd /app && patch -p1 < ...` → entrypoint unchanged
  - Output tag: `letta-local:0.16.7-memfs-v1`
  - Verification: `docker build -t letta-local:0.16.7-memfs-v1 letta-memfs-build/ && docker run --rm letta-local:0.16.7-memfs-v1 python -c "import letta; print(letta.__version__)"`

- [ ] **1.3 Wire the patched image into docker-compose.yml behind a flag**
  - Modify: `docker-compose.yml` — change `letta.image` from hardcoded `letta/letta:pg-0.16.7` to `${LETTA_IMAGE:-letta/letta:pg-0.16.7}`. Default stays on unpatched for safety.
  - Modify: `.env.example` (and `.env`) — add `LETTA_IMAGE=letta-local:0.16.7-memfs-v1` commented out by default
  - Verification: `LETTA_IMAGE=letta-local:0.16.7-memfs-v1 docker compose up -d letta && docker inspect ai-pa-letta-1 --format '{{.Config.Image}}'` shows the patched tag
  - Rollback: comment `LETTA_IMAGE` in `.env`, restart; unpatched image runs with zero change to Postgres state

- [ ] **1.4 Add memfs env vars to the letta service config**
  - Modify: `docker-compose.yml` under `letta.environment` — add `LETTA_MEMFS_SERVICE_URL: local`, `LETTA_MEMFS_BLOCK_PATH_PREFIXES: system/`
  - These are active only when the patched image runs; unpatched image ignores them
  - Verification: `docker exec ai-pa-letta-1 printenv | grep LETTA_MEMFS` shows both

- [ ] **1.5 Add persistent memfs volume**
  - Modify: `docker-compose.yml` — add named volume `letta-memfs` mounted at `/root/.letta/memfs` on the letta service
  - Verification: `docker volume ls | grep letta-memfs`; after a restart, `ls /root/.letta/memfs/` inside the container is preserved

- [ ] **1.6 Verify patch-check runs without conflicts before each rebuild**
  - Create: `letta-memfs-build/verify-patches.sh` — runs `patch --dry-run` for each patch and fails fast if any won't apply cleanly
  - Called from the Dockerfile before the real `patch` step
  - Verification: intentionally corrupt a patch and confirm build fails with a clear message

**Test scenarios** (once image is built):
1. Patched image starts healthy and serves `/health` like the unpatched one
2. `POST /v1/agents/nonexistent/memory/sync-from-git` returns a clean 404 or 422 (not 500)
3. `POST /v1/agents/<real-agent>/memory/sync-from-git` on an agent without `git-memory-enabled` returns 409 (as the patch intends)
4. Postgres schema is unchanged (patches don't touch schema — verify via `docker exec supabase-db pg_dump -s letta | md5` compared before/after)

### Phase 2 — Patched letta-code client

- [ ] **2.1 Clone letta-code into a project-local directory**
  - Location: `~/code/letta-code-memfs/` (outside this repo — it's a separate project)
  - Pin: letta-code 0.23.8 (matching what's currently installed)
  - Apply: `patch -p1 < /Volumes/main-drive/ai-PA/letta-memfs-patches/patches/memoryGit.ts.patch`
  - Build: `bun install && bun run build`
  - Output: `~/code/letta-code-memfs/dist/` with a runnable CLI entry

- [ ] **2.2 Add a thin wrapper script so pa-web-ui / LettaBot can choose the binary**
  - Create: `scripts/letta-code-wrapper.sh` in *this* repo — resolves to `$LETTA_CODE_BIN` if set, else falls back to `/opt/homebrew/bin/letta`
  - Modify: `pa-web-ui/app.py` — where it spawns letta-code, use the wrapper instead of a hardcoded path
  - Modify: `lettabot/` (whatever spawns letta-code subprocesses) — same treatment
  - Env-var default (`.env`): `LETTA_CODE_BIN=/opt/homebrew/bin/letta` (unchanged behavior)
  - For memfs sessions: `LETTA_CODE_BIN=~/code/letta-code-memfs/bin/letta`

- [ ] **2.3 Client env vars for memfs**
  - Modify: `.env` — add `LETTA_MEMFS_GIT_URL=https://user:$GITEA_MEMFS_TOKEN@gitea:3000/agents/{agentId}.git` (commented by default)
  - Modify: `.env` — add `LETTA_MEMFS_LOCAL=1` (commented by default)
  - These are only set for sessions targeting memfs-enabled agents; Phase 4 exercises this

- [ ] **2.4 Verify the client patch doesn't break non-memfs sessions**
  - Run patched letta-code against an existing non-memfs agent (pick any current agent) with `LETTA_MEMFS_GIT_URL` **unset**
  - Expect: identical behavior to the Homebrew binary
  - Verification: diff the stderr/stdout of a simple `/help` invocation between the two binaries; should be identical modulo timestamps

**Test scenarios**:
1. Patched binary + memfs env vars unset → behaves like stock letta-code
2. Patched binary + `LETTA_MEMFS_GIT_URL` set but agent has no tag → clones from the server proxy as usual (patch is additive, per patches/README)
3. Patched binary + agent has tag → clones from Gitea URL (Phase 4 validates)

### Phase 3 — Block duplication helper

- [ ] **3.1 Create `scripts/letta-duplicate-block.sh`**
  - Input: `SOURCE_BLOCK_ID`, `TARGET_AGENT_ID`, optional `NEW_LABEL` (defaults to source label)
  - Action: `GET /v1/blocks/$SOURCE_BLOCK_ID` → `POST /v1/blocks/` with same value and label → `PATCH /v1/agents/$TARGET_AGENT_ID/core-memory/blocks/attach/$NEW_BLOCK_ID`
  - Idempotent: if the target agent already has a block with the same label, skip with a warning
  - Output: prints the new block ID

- [ ] **3.2 Test the helper against throwaway blocks**
  - Create a throwaway block, duplicate it to a throwaway agent, verify the duplicate is a distinct block (different ID), same content
  - Edit the duplicate and verify the source is untouched
  - Verification: `curl /v1/blocks/$SOURCE` and `/v1/blocks/$NEW` show different IDs, same content after creation, divergent after edit

**Test file**: `tests/integration/test_letta_duplicate_block.sh`

**Test scenarios**:
1. Duplicate a single block — verify new block, attach to target
2. Duplicate when target already has same-label block — verify skip with warning
3. Duplicate a block with non-ASCII content — verify encoding survives

### Phase 4 — Staged canaries (C1–C5)

**Restructure rationale**: a single canary cannot validate the orthogonal dimensions that matter — infrastructure, Task tool behavior, REST-only agent migration, multi-channel agent migration, consolidator pattern. Conflating them means failures get mis-attributed and rollback is muddied. Each stage has its own canary, success criteria, and explicit teardown.

#### C1 — Infrastructure canary (`memfs-canary-infra`)
**Validates**: Gitea up, three server patches apply correctly, sync endpoint works, six base validation tests pass, rollback works. **No agent behavior tested.**

- [ ] **4.1 Create the `memfs-canary-infra` agent**
  - Create: `scripts/canary-manage.sh` — generic canary lifecycle script supporting `create <name>`, `tag <name> <tag>`, `attach-block <name> <block-id>`, `snapshot <name>`, `teardown <name>`. Used for all C1–C5.
  - Provisions via `POST /v1/agents/` with minimal toolset (send_message, core_memory_append, core_memory_replace initially; bash/Edit/Read/grep come via letta-code client)
  - Name: `memfs-canary-infra`
  - Description: `"C1 — Infrastructure validation canary for letta-external-memfs. Disposable. Tear down at end of C1."`
  - Model: `gpt-4.1-mini/old` via litellm (cheap, readily available)
  - No shared blocks attached initially
  - Output: prints agent ID; writes to `.letta/canaries/memfs-canary-infra.agent_id` (gitignored) for later scripts

- [ ] **4.2 Seed canary with duplicated real blocks**
  - Using the Phase 3 helper: duplicate one awareness block + one persona-shaped block to the canary
  - Do **not** duplicate any of the six shared-queue blocks (R20 in origin) — they are irrelevant to memfs testing and would pollute the canary's block namespace
  - Verification: `GET /v1/agents/<canary>/core-memory/blocks` shows the duplicates, each with distinct IDs from the originals

- [ ] **4.3 Create an empty Gitea repo for the canary**
  - Create: `scripts/memfs-init-agent-repo.sh $AGENT_ID` — creates `agents/$AGENT_ID.git` in Gitea via API, initializes with an empty `main` branch, seeds an empty `system/.gitkeep`
  - Verification: `git clone https://user:token@gitea:3000/agents/$AGENT_ID.git /tmp/check` succeeds

- [ ] **4.4 Tag the canary with `git-memory-enabled`**
  - Command documented in brainstorm R19 (PATCH agent tags — but **careful**: memory says `PATCH /v1/agents/{id}` with tags REPLACES the tag list, so GET first, append, PATCH back)
  - Reference: `MEMORY.md` → `feedback_block_ids_replace.md` pattern
  - Verification: `GET /v1/agents/<canary>` shows `git-memory-enabled` in tags

- [ ] **4.5 Connect patched letta-code to the canary**
  - `LETTA_CODE_BIN=~/code/letta-code-memfs/bin/letta LETTA_MEMFS_GIT_URL=https://... LETTA_MEMFS_LOCAL=1 letta --agent <canary-id>`
  - Verify the client clones from Gitea, not from the server proxy
  - Verification: `~/.letta/agents/<canary-id>/memory/` contains a `.git/` directory with `origin` pointing to Gitea

- [ ] **4.6 Run validation tests 1–6** (defined in origin R15)
  - Create: `tests/integration/test_memfs_canary.sh` — runs all six scenarios in sequence, each with clear pass/fail assertion and the Vee-corrected sync pattern (`--git-dir=.../repo.git fetch ... --update-head-ok`)
  - Test 1 — Smoke: tag + write `system/test.md` via bash → verify block
  - Test 2 — Round-trip: agent bash edit → push → sync-from-git → verify
  - Test 3 — External edit: `git push` from host → sync-from-git → verify
  - Test 4 — Delete propagation: `git rm system/notes.md` → sync → verify block deleted (validates `server_sync_delete_propagation.patch`)
  - Test 5 — Path filter: `reference/noise.md` → sync → verify no block created (validates `server_system_only_blocks.patch`)
  - Test 6 — Binary handling: push a `._*` file → verify graceful handling, no 500
  - Test 7 — Recall subagent works against the canary: invoke `Task(subagent_type: "recall", prompt: "summarize last 5 exchanges")` → verify a forked-conversation subagent runs and returns a useful summary. Validates that fork-based history access functions in our patched stack — prerequisite for any future consolidator pattern (see `docs/brainstorms/2026-04-24-memory-consolidation-patterns-requirements.md`).
  - Test 8 — `/doctor` post-migration cleanup: run `/doctor` on the canary → verify it proposes reasonable memory reorganization and applies it without errors. Confirms the canonical post-migration step works.
  - Output: machine-readable JSON summary at `tests/integration/memfs_canary_results.json`

- [ ] **4.7 48-hour soak test**
  - After all six tests pass, leave canary running with daily real-feeling memory edits (persona updates, notes, etc.) for ≥ 48h
  - Monitor: `docker stats` for memory growth on letta + gitea; `docker compose logs letta gitea --since 24h | grep -i error`
  - No production agent is touched in this period
  - Exit criterion: no error-class log entries, no memory leaks, no failed syncs

- [ ] **4.8 Rollback dry-run on C1**
  - Remove `git-memory-enabled` tag (using the GET-append-PATCH-replace-safe pattern from memory)
  - Switch `LETTA_IMAGE` back to unpatched in `.env`, `docker compose up -d letta`
  - Verify canary's existing blocks (from 4.2) still readable, memfs-era history preserved in Gitea for forensic purposes
  - Re-enable by reversing
  - This proves R19's rollback path works before we ever touch a real-shape agent

- [ ] **4.9 C1 teardown**
  - Snapshot final memfs state to `tests/integration/canary-c1-final-snapshot.tgz` for forensic record
  - Delete the `memfs-canary-infra` agent via `DELETE /v1/agents/{id}`
  - Delete its Gitea repo
  - Mark `.letta/canaries/memfs-canary-infra.agent_id` as torn-down
  - **Gate to C2**: all 8 tests passed + 48h soak clean + rollback dry-run clean + Phase -1 (Task reconciliation) complete

#### C2 — Task tool canary (`memfs-canary-task`)
**Validates**: Task tool invocations work in our patched + Task-reconciled environment. Particularly fork-based subagents (recall, custom fork: true), nested Task calls (subagent → Task), and REST-initiated Task invocations.

- [ ] **4.10 Create C2 agent** with same baseline as C1, plus Task in allowed tools
- [ ] **4.11 Test 1: Direct Task invocation from letta-code session** — `Task(subagent_type: "general-purpose", prompt: "...")`, verify clean completion
- [ ] **4.12 Test 2: Recall via Task** — `Task(subagent_type: "recall", prompt: "search last 5 messages for X")`, verify fork inherits history
- [ ] **4.13 Test 3: Custom subagent via Task** — define `~/.letta/agents/test-consolidator.md` with bash + Edit, invoke via Task, verify it can edit memfs files
- [ ] **4.14 Test 4: Nested Task** — custom subagent that itself invokes `Task(subagent_type: "recall", ...)` — validates the consolidator pattern
- [ ] **4.15 Test 5: REST-initiated Task** — `POST /v1/agents/{id}/messages` with a message instructing the agent to call Task; verify the resulting Task call executes correctly. **This is the empirical answer to whether scheduler-service-driven consolidators will work.**
- [ ] **4.16 C2 teardown** — same shape as 4.9. Gate to C3: all 5 tests passed.

#### C3 — REST-only agent canary (`memfs-canary-rest`)
**Validates**: A purpose-built REST-only agent (no live letta-code session) can be migrated to memfs without breaking external writers; whether REST writes to its blocks drift from git after migration. **Answers sibling R18.**

- [ ] **4.17 Create C3 agent** — same baseline as C1; explicitly NOT connected via letta-code TUI
- [ ] **4.18 Attach a duplicated awareness-style block** — simulates what a real REST-only agent (Email, Calendar) has
- [ ] **4.19 Migrate to memfs** — tag with `git-memory-enabled`, run `/memfs enable` via a one-time letta-code session, then disconnect letta-code
- [ ] **4.20 Test: external REST write** — `PATCH /v1/blocks/{id}` modifying the block from outside (simulating gmail-watch-style writer); verify what happens. Three possible outcomes documented:
  - **A**: write succeeds, block updates, git stays out of sync (drift) → REST-only agents can keep using Postgres-block writes; consolidators handle git
  - **B**: write succeeds, block updates, sync-from-git on next pass overwrites the change → REST writes are *lost*; we must redirect external writers
  - **C**: write fails entirely → REST writes blocked; we must redirect external writers immediately
- [ ] **4.21 Test: agent-internal write via REST** — `POST /v1/agents/{id}/messages` instructing core_memory_append; verify behavior under memfs
- [ ] **4.22 C3 teardown** — same shape. Gate to C4: outcomes from 4.20 and 4.21 documented; user reviews before C4 begins. **The verdict here determines the entire shape of REST-only-agent migration.**

#### C4 — Multi-channel agent canary (`memfs-canary-multichannel`)
**Validates**: An agent with multiple client paths handles memfs correctly when different clients write through different code paths. **Rehearsal for MC migration.**

- [ ] **4.23 Create C4 agent** — purpose-built MC-shaped agent (NOT a real `MC-rogue-*` fork — fresh agent so we know its history is clean)
- [ ] **4.24 Attach two duplicated awareness-style blocks** + one duplicated persona-shape block
- [ ] **4.25 Wire up THREE simulated client paths**: (a) a letta-code TUI session, (b) a scripted REST client simulating LettaBot's pattern, (c) a scripted REST client simulating scheduling-orchestrator
- [ ] **4.26 Migrate to memfs** while all three clients are aware
- [ ] **4.27 Test concurrent multi-client behavior** — letta-code edits a file, REST client A writes a block, REST client B reads the block. Verify consistency, sync, no lost writes.
- [ ] **4.28 Test client-disconnect scenarios** — what happens when letta-code disconnects mid-session? Mid-edit?
- [ ] **4.29 C4 teardown** — same shape. Gate to C5: all multi-client scenarios documented with verdicts; this output feeds the MC migration impact analysis (Phase 4.5).

#### C5 — Consolidator canary (`memfs-canary-consolidator`)
**Validates**: A custom consolidator subagent invoked on a cadence (scheduler-service → Task) actually works end-to-end on a real-shape agent. Foundational test for Phase 6+.

- [ ] **4.30 Create C5 agent** — REST-only shape (closer to most production agents)
- [ ] **4.31 Author a minimal consolidator** at `~/.letta/agents/canary-consolidator.md` — fork: false, tools: Read, Edit, Write, Bash, persona instructs it to summarize last N messages into `system/recent-summary.md`
- [ ] **4.32 Wire scheduler-service to invoke consolidator** — register a job that fires `POST /v1/agents/{id}/messages` instructing a Task call hourly
- [ ] **4.33 Generate synthetic activity** — script that sends a few messages to the agent over 4-6 hours
- [ ] **4.34 Verify consolidator runs** — git log in C5's memfs repo shows hourly commits attributable to the consolidator; the file content is meaningful
- [ ] **4.35 Verify failure handling** — temporarily break the consolidator (invalid frontmatter), verify scheduler-service surfaces the failure rather than silently passing
- [ ] **4.36 C5 teardown** — same shape. Gate to Phase 4.5 (Migration Impact Analysis) for first real production agent.

#### Phase 4.5 — Migration Impact Analysis (REQUIRED GATE before any production migration)

**This is a discrete required artifact, not just process discipline.** Before any production agent is migrated, we produce and review a written impact analysis for that specific agent. No production agent is touched until its analysis is signed off.

- [ ] **4.37 Create the impact analysis template** at `docs/templates/memfs-migration-impact-analysis.md`. Template includes the following required sections:
  - **Agent identity**: ID, name, model, current tag set, current tool list (verbatim from `/v1/agents/{id}`)
  - **Current memory inventory**: every block currently attached (ID, label, last-modified, size, value-summary), distinguishing per-agent blocks from shared blocks
  - **Current writers**: enumerate every external service or human-driven path that writes to this agent's memory or messages — gmail-watch, slackbot, scheduling-orchestrator, pa-routing-handler, pa-web-ui sidebar, direct API, etc. For each: write frequency, write target (which block / message), write semantics (append / replace / structured)
  - **Current readers**: enumerate every consumer of this agent's memory blocks — pa-web-ui (sidebar reads `extracted_tasks`), other agents via attached blocks, etc.
  - **Current invocation patterns**: every way the agent is invoked — REST messages from scheduler, REST from pa-web-ui, REST from pa-routing-handler, Telegram via LettaBot, direct Letta SDK calls
  - **Tool surface**: every tool currently attached (built-in + MCP + custom Letta tools), with notes on which depend on memory blocks vs. message history vs. external state
  - **Memfs migration impact**: section-by-section walkthrough of what changes. For every item in the inventories above, what happens after `git-memory-enabled` is set? Verified outcomes from C2/C3/C4 referenced.
  - **Risks specific to this agent**: failure modes that are unique to this agent's role/usage — e.g. "Email agent depends on extracted_tasks block being readable from pa-web-ui every 30s; if memfs adds latency to block reads, sidebar refresh may stall"
  - **Mitigations**: for each risk, the mitigation
  - **Rollback for THIS agent**: agent-specific rollback steps, not just "switch the image"
  - **Go/no-go criteria**: explicit conditions that must be true to proceed
  - **Reviewer sign-off**: a section the user fills in before migration proceeds
- [ ] **4.38 First impact analysis is for MC** (highest-stakes, validates the template). Produced AFTER C4 completes so it can reference the multi-channel verdicts.
- [ ] **4.39 User reviews and signs off MC's analysis** before any actual MC migration is scheduled.

**Test scenarios** (across all canaries): see 4.6, 4.11–4.15, 4.20–4.21, 4.27–4.28, 4.34–4.35.

### Phase 5 — MC migration (roadmap-level only)

*Not detailed in this plan. Will be planned as a separate document once Phase 5 go/no-go criteria are agreed with user, per origin doc's "Deferred to User Discussion" section. Expected scope:*

- Verify scheduling-orchestrator's REST writes to MC blocks behave correctly under `git-memory-enabled` — likely the gating empirical test
- Tag-on / single Telegram message / tag-off dry-run
- Switch to patched image + tag, observe 7+ days
- Run `/doctor` post-migration to reorganize block-shaped memory into filesystem-shaped memory
- Document the rollback procedure in `docs/runbooks/memfs-mc-rollback.md`

### Phase 6+ — Universal migration (roadmap-level only)

*Per Letta forum thread (2026-04-24, Ezra/DC9753), every agent in the ecosystem is migration-eligible via the consolidator-subagent pattern, not just letta-code-attached agents. Detailed consolidation architecture (per-agent consolidators, cross-agent org-observer, cadence ownership) lives in:*

→ `docs/brainstorms/2026-04-24-memory-consolidation-patterns-requirements.md`

*That sibling doc covers the WHAT of consolidation. Per-agent migration plans (Tasks, Calendar, Email, etc.) get their own implementation plans once the consolidation patterns brainstorm is converged.*

## Dependencies & Sequencing

```
Phase -1 (Task reconciliation) ──────────────┐
                                             │
Phase 0 (Gitea)        ┐                     │
Phase 1 (server image) ├─→ Phase 4 C1 ─→ C2 ─┴→ C3 ─→ C4 ─→ C5 ─→ Phase 4.5 ─→ Phase 5 ─→ Phase 6+
Phase 2 (client patch) │       (infra)  (Task) (REST) (multi-) (consol-)  (impact   (MC mig)  (universal)
Phase 3 (block dup)    ┘                              channel) (idator)   analysis)
```

- **Phases 0–3** run in parallel; independent.
- **Phase -1** runs in parallel with 0–3 but must complete before C2.
- **C1** depends on Phases 0, 1, 2, 3.
- **C2** depends on C1 + Phase -1 complete.
- **C3** depends on C2 (need Task working to run consolidator-style verifications).
- **C4** depends on C3 (need to know REST-write outcome before testing multi-client).
- **C5** depends on C4 (consolidator pattern depends on knowing multi-channel behavior is sound).
- **Phase 4.5 (Impact Analysis)** depends on C1–C5 complete; produces a written, signed artifact per migrating agent.
- **Phase 5 (MC migration)** depends on Phase 4.5's MC analysis being signed off + user-agreed go/no-go criteria.
- **Phase 6+ (universal migration)** depends on Phase 5 success + per-agent impact analyses.
- Backup changes (0.3) must ship before C1 starts so the 48h soak in C1 is covered by nightly backups.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Server patches don't apply cleanly to 0.16.7 (they're pinned against 0.16.6) | Low — patches use diff context, not hash | Medium | 1.6 verify-patches step fails fast; if it fires, we pin to 0.16.6 for now and defer 0.16.7 |
| Patched image runs but `GitEnabledBlockManager` not wired | Low | High (blocks Phase 4) | Test 4.6 #3 on an agent without tag — 409 confirms the manager is wired |
| Letta-code patched build breaks bash tool plumbing | Low — patch is additive-only per patches/README | High (would corrupt canary agent behavior) | 2.4 comparison run against Homebrew binary; abort if stderr/stdout diverges for non-memfs sessions |
| Gitea backup/restore loses repo HEAD references | Medium — Gitea dump semantics can be subtle | Medium | 0.4 explicit restore test before Phase 4.6 starts |
| External REST writes to MC blocks silently drift from git after migration | Unknown — this is R18's empirical question | Critical for Phase 5 | Explicit test in Phase 5 (not this plan); if confirmed, MC migration is deferred until remediated |
| `letta-memfs` volume grows unbounded over time | Low-medium | Low (observability issue) | Monitor in 4.7 soak; add Prometheus exporter later if cAdvisor proposal lands |
| Canary agent's toolset drifts from what memfs actually needs | Low | Low | 4.5 verification step re-checks tool list; adjust 4.1 if we find a missing tool |
| **#3205 not actually fixed in any reachable Letta version** | Unknown until -1.1 research | **Critical** — gates entire Phase 5+ universe | Phase -1.2 documents three resolution branches; if all fail, consolidation work pauses indefinitely and we ship Path A (memfs without consolidators) only |
| **REST writes to memfs-enabled agent blocks behave unexpectedly (C3 outcome B or C)** | Unknown | High — could require redirecting every external block writer | C3 produces explicit verdict; user reviews before C4. If outcome forces external-writer redirection, that's a separate plan, not this one |
| **Multi-channel concurrent write conflicts (C4)** | Unknown | High for MC | C4 isolates this with a fresh fake-MC agent so we hit it on a canary, not on real MC |
| **Consolidator invocation from scheduler-service is non-trivial (C5)** | Medium | Medium | C5 explicitly tests this; if scheduler-driven Task fails, we fall back to in-agent self-cadence |
| **Migration Impact Analysis surfaces blocking issues per-agent that didn't appear on canaries** | Medium | High | The point of 4.5 — surface them BEFORE migration; if surfaced, that agent does not migrate until remediated |

## Verification Strategy

Each phase has its own verification commands inline. Rollup smoke at end of each phase:
- Phase 0: Gitea healthcheck green, backup artifact present, restore reproduces
- Phase 1: patched image starts, Postgres unchanged, sync endpoint returns 409 for non-tagged agents
- Phase 2: patched client runs against non-memfs agent without regression
- Phase 3: block duplication produces distinct IDs with same content
- Phase 4: all 6 tests pass + 48h soak clean + rollback dry-run clean

## Files Created / Modified

**Created**:
- `letta-memfs-patches/` (vendored submodule or pinned checkout)
- `letta-memfs-build/Dockerfile`
- `letta-memfs-build/verify-patches.sh`
- `gitea/` only if overriding defaults
- `scripts/gitea-bootstrap.sh`
- `scripts/letta-code-wrapper.sh`
- `scripts/letta-duplicate-block.sh`
- `scripts/create-memfs-canary.sh`
- `scripts/memfs-init-agent-repo.sh`
- `deployment/scripts/gitea-restore.sh`
- `tests/integration/test_memfs_backup_restore.sh`
- `tests/integration/test_letta_duplicate_block.sh`
- `tests/integration/test_memfs_canary.sh`
- `tests/integration/memfs_canary_results.json` (generated artifact)
- `.letta/memfs-canary.agent_id` (gitignored)

**Modified**:
- `docker-compose.yml` — add gitea service, `LETTA_IMAGE` env indirection, memfs env vars, `letta-memfs` volume
- `deployment/scripts/backup.sh` — add gitea + letta-memfs volume backup legs
- `.env` (and `.env.example`) — new vars for memfs configuration
- `pa-web-ui/app.py` — letta-code binary selection via wrapper
- Whatever file in `lettabot/` spawns letta-code subprocesses — same wrapper integration

## Rollback Plan

Whole-plan rollback: revert the `LETTA_IMAGE` env var to the stock tag, `docker compose up -d letta`, remove `git-memory-enabled` tag from canary. Gitea stays up (no cost) but becomes unused. Patches stay vendored but inactive.

Per-phase rollback is documented inline in each phase's verification step.

## Success Criteria for Plan Completion

- Phase -1 (Task reconciliation) resolved with documented verdict
- All Phase 0–4 checkboxes green
- All five canaries (C1–C5) reached their gating criteria and torn down cleanly
- Phase 4.5 impact analysis template exists at `docs/templates/memfs-migration-impact-analysis.md`
- 48h canary soak is clean (C1)
- Canary rollback dry-run is clean (C1)
- Nightly backup demonstrably includes Gitea + letta-memfs volume
- No change to any of the six Class B Postgres blocks (R20) observed during or after the work
- The C3 REST-write verdict is documented and user-reviewed
- The C4 multi-channel verdict is documented and user-reviewed
- MC's impact analysis (Phase 4.38) is produced and ready for user sign-off
- User agrees Phase 5 planning should begin
