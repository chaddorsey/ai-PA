---
title: Letta Code local-mode investigation + migration assessment
date: 2026-05-25
status: track 1 complete; canary (track 2 step 1) complete; remaining unknowns under active investigation
last-updated: 2026-05-25
revision-log:
  - 2026-05-25 (initial plan written before any work)
  - 2026-05-25 (canary update — 5-step support-agent checklist complete; track 1 complete and committed)
  - 2026-05-25 (cron-integration unknown resolved — letta-local-runner deployed; scheduler-service route=local executor; end-to-end smoke through scheduler-service → host bridge → letta → canary verified)
related:
  - docs/followups/2026-04-29-pa-web-stability-todos.md (will get #99/#100 entry)
  - docs/runbooks/agent-memfs-conventions.md
  - docs/runbooks/memfs-migration-per-agent.md
  - letta-code-patched/README.md
  - letta-memfs-patches/patches/
queue-ref: pa-web-stability-todos #99 (to be added)
effort-estimate: 1-2 days for canary; production migration is multi-week
---

# Letta Code Local Mode — Investigation + Migration Assessment

## Motivation

Letta has shifted the actively-maintained personal-deployment path from
Docker server to **Letta Code local mode**. Per the Letta docs:

- "MemFS is available through the Letta API and Local mode. If you are
  using a Docker server, your agent will use the legacy memory blocks
  system." (https://docs.letta.com/letta-code/memory)
- Docker server is documented as legacy and no longer the recommended
  surface for new local deployments
  (https://docs.letta.com/guides/docker).

This matters for our stack because we just spent significant effort
in March-April 2026 building memfs onto our Docker server via a custom
external-git routing patch (`PATCH-MEMFS-GIT`) and a sidecar service
(`memfs-sync-relay`). Local mode appears to provide memfs as a
first-class native feature without those scaffolds.

This plan scopes the **investigation** — not the migration. Migration
decisions are gated on what the canary surfaces.

## Current state — what we have today

### letta-code versions in play

| Where | Version | Notes |
|---|---|---|
| Global npm (`~/.local/bin/letta`) | `@letta-ai/letta-code@0.25.8` | newest installed; used for some host-side scripts |
| `letta-code-patched/` (pinned + patched) | `0.24.2` | used by pa-web-ui subprocess pool |
| `letta-code/` | bare README; not built | placeholder, no source |

### Patches against the pinned bundle

| Patch | Purpose | Status under local mode |
|---|---|---|
| `PATCH-3205` (handle-fix) | Fixes `POST /v1/agents/` `HandleNotFoundError` during subagent spawn against self-hosted Docker server | May be moot in local mode (no central server doing handle resolution). **Check whether it landed upstream in 0.25.x — if yes, drop entirely.** |
| `PATCH-MEMFS-GIT` (external-git memfs) | Routes memfs git ops to `LETTA_MEMFS_GIT_URL` (our Gitea) instead of Letta server's `/v1/git/` proxy | **Becomes irrelevant in local mode.** Local-mode memfs is plain disk at `~/.letta/lc-local-backend/memfs/<agent-id>/memory/`, no git proxy needed. |

### Architecture comparison

```
┌─ TODAY (Docker server + patched memfs)──────────────────────────────┐
│ pa-web-ui → letta-code (0.24.2 patched, --backend remote)           │
│        ↓                                                            │
│ ai-pa-letta-1 (Docker, port 8283)                                   │
│        ↓                                                            │
│ memory: legacy memory blocks + PATCH-MEMFS-GIT routes memfs git     │
│        ↓                                                            │
│ Gitea: agents/agent-XXXX.git ← memfs-sync-relay (sidecar) syncs     │
└─────────────────────────────────────────────────────────────────────┘

┌─ LOCAL MODE (target)────────────────────────────────────────────────┐
│ letta-code (0.25.8+, --backend local)                               │
│        ↓                                                            │
│ embedded local backend (no Docker server)                           │
│        ↓                                                            │
│ memory: ~/.letta/lc-local-backend/memfs/<agent-id>/memory/          │
│        ↓                                                            │
│ git-backed locally (commit on edit; no external sync)               │
│        ↓                                                            │
│ provider: letta --backend local connect <ollama|openai|anthropic|…> │
│   ("agent state stays local, prompts still go to remote provider")  │
└─────────────────────────────────────────────────────────────────────┘
```

### What we'd retire if local mode wins

- Docker container: `ai-pa-letta-1`
- Docker container: `memfs-sync-relay`
- Docker container: `letta-bg-fix-sidecar` (verify whether silent-stall
  bug exists in local mode — probably no, but confirm)
- Gitea agent repos under `/data/git/repositories/agents/agent-*.git`
  (Gitea itself stays for human-facing repos)
- `PATCH-MEMFS-GIT` (definitely)
- `PATCH-3205` (probably, if landed upstream)
- `scripts/memfs-helpers/` (most of it — relay/external-git tooling)

### What stays the same

- pa-web-ui (still spawns letta-code subprocess per conversation)
- pa-routing-handler (still routes user input to the right agent)
- All non-Letta services (drive-rag, scheduler-service, slackbot, etc.)
- MCP servers (graphiti, slack-tools, omnifocus, etc.) — though their
  *attachment* mechanism changes (config file vs Letta-server config)

## What's unknown — investigation must answer

These are the questions blocking a go/no-go decision:

1. **Cron / scheduler integration.** Today, 39 active scheduler-service
   jobs target the Docker letta server (`http://letta:8283/v1/agents/.../messages/`).
   Does local mode expose a comparable HTTP endpoint, or do crons need
   to invoke `letta --backend local agents send-message ...` via Bash?

2. **MCP server attachment.** `letta/letta_mcp_config.json` configures
   6 MCP servers (slack-tools, graphiti, rag, calendly, scheduler, omnifocus)
   against the Docker server. What's the local-mode equivalent?
   Per-agent config file? Same file in a new path?

3. **Multi-agent invocation.** pa-routing-handler and pa-web-ui spawn
   letta-code subprocesses against the Docker server. In local mode,
   each subprocess has its own embedded backend — do they share state?
   Or does local mode assume single-user, single-process at a time?

4. **Sandbox / custom tool execution.** Letta Docker server runs custom
   Letta tools in a sandbox venv at `/app/tools/letta/env`. Where does
   local mode put this? Same path? Different mechanism?

5. **Provider routing.** Today: litellm proxy normalizes
   Anthropic/OpenAI/Gemini/etc. behind one endpoint, Letta server points
   at litellm. In local mode: `letta --backend local connect <provider>`
   per provider. Can we still funnel through litellm, or does local
   mode bypass it?

6. **Migrating ~20 existing agents.** Each Docker agent has:
   - System prompt + persona memory blocks (legacy)
   - Memfs repo in Gitea
   - Attached tools (Letta tools registered via Python scripts)
   - Attached MCP servers
   - Possibly attached shared blocks
   
   What's the migration path? Letta CLI import? Hand-copy markdown?
   Re-register tools from scratch?

7. **PATCH-3205 status.** Did the upstream fix land in 0.25.x? If yes,
   one patch removed. If no, may need a port to the new bundle.

8. **Letta API option.** Docs mention "Letta API" as the third path
   alongside Docker and local. Is that a hosted SaaS? Self-hostable
   via a non-Docker binary? Worth at least understanding before
   committing to local.

## Update 2026-05-25 — Track 1 complete; Track 2 step-1 canary complete

### Track 1 — letta-code-patched 0.24.10 → 0.26.1 — COMPLETE

Committed across `b67f8ee2`, `c553470d`, `57b43b74`, `b2595e53`. Key
adjustments needed on top of the original plan:

- **PATCH-MEMFS-GIT change 3 anchor refactor**: 0.26.x replaced
  `isMemfsRemoteUrlForAgent` with `isRepairableMemfsRemoteUrl` in the
  `maybeUpdateMemoryRemoteOrigin` guard. One-line port of the patch
  script's `OLD_3` anchor.
- **PATCH-3205 client scoping**: `const client = await getClient()`
  moved AFTER the patch's insertion point in 0.26.x, putting `client`
  in temporal dead zone when the patch runs. Fixed by calling
  `getClient()` directly inside the patch (stored as `_patch3205_client`
  to avoid shadowing). Marker count went 8 → 10 (extra comment lines).
- **Container missing `git`**: pa-web-ui Dockerfile never installed
  the system git binary. The bundle's memfs commit/push path uses
  `runGit3()` which shells out to system git. Every pa-web-ui memfs
  write had silently no-op'd since cycle-1; surfaced by the upgrade
  smoke test. Fixed by adding `git` to the apt install list.

All 5 smoke tests pass end-to-end against the patched 0.26.1 bundle:
identity load, memfs Read, memfs Edit+commit, Bash with approval,
subagent spawn.

### Track 2 step 1 — local-mode canary — COMPLETE

5-step plan from Letta support agent executed against
`/tmp/letta-canary-1779727677` with global letta-code 0.25.8 (note:
NOT the patched 0.26.1 bundle; canary uses unpatched global). Agent
`agent-local-d06e9bf7-1a75-4558-a1fe-1454bb5b2ec7` created with
OpenAI gpt-4o-mini and seeded from a Gitea snapshot of
`calendar-agent_copy/system/`. Persistence verified: agent edited
`scheduling_context.md`, fresh CLI invocation read back the change.

**Surfaced gotchas for the migration runbook:**

1. **Frontmatter is mandatory in local mode.** Every `*.md` under
   memory/ needs `---\n...\n---\n` with at least a `description:` field.
   Gitea memfs was more permissive. Calendar-agent_copy had 4 stub
   files without frontmatter (historical/migrated markers); they failed
   validation and were removed before commit. Migration runbook needs
   a pre-import audit for missing frontmatter.

2. **`read_only: true` is a protected frontmatter field.** The agent
   itself can't set it. `agent_info.md` from calendar-agent_copy had it;
   stripped before commit. Runbook needs to strip protected fields.

3. **First-run transcript migration**: if any prior conversation
   activity exists in the backend dir (even a failed run), local mode
   requires `letta local-backend migrate-transcripts --storage-dir <dir>`
   once before subsequent runs. Runbook needs this as a "if you see
   `unversioned legacy transcripts` error" step.

4. **Edit tool does NOT auto-commit.** Same behavior as Docker mode —
   agent must explicitly run `git commit` via Bash. Working-tree edits
   persist across restarts even without commit (so persistence works,
   but git history lags reality). Runbook should set expectation that
   agents need an explicit commit step in routines that care about
   audit history.

5. **Bundle ships a hard-coded "Letta Code" system prompt** that is
   sent on every turn in addition to pinned `system/*.md` files. The
   imported `persona.md` supplements but doesn't fully replace the
   baseline letta-code framing. In practice the agent self-identifies
   correctly using imported persona, but the prompt is bigger than the
   memfs files alone suggest. Open question: can the baseline be
   overridden via flag or config?

6. **Agent ID prefix differs** — local-mode agents use
   `agent-local-<uuid>` (vs `agent-<uuid>` in Docker). May or may not
   matter for downstream tooling that assumes a prefix.

### Status of the 8 original unknowns after canary

| # | Unknown | Status |
|---|---|---|
| 1 | Cron / scheduler integration | **RESOLVED** — letta-local-runner + scheduler-service `route=local` deployed; end-to-end verified |
| 2 | MCP server attachment | **Under active investigation (next)** |
| 3 | Multi-agent / subagent invocation | Still unknown |
| 4 | Sandbox / custom Letta tool execution | Still unknown |
| 5 | Provider routing — litellm vs native | Partial: native `letta connect openai` skips litellm entirely; can still point at litellm-as-OpenAI-compat if needed |
| 6 | Migration path for ~20 existing agents | Partial: snapshot+import works for system/; per-agent cleanup needed; archival/tools/MCPs still TBD |
| 7 | PATCH-3205 upstream status | Resolved during Track 1: not landed, patch still required and now ported to 0.26.x |
| 8 | Letta API (third path) option | Still unknown — not blocking; defer |

### Cron integration — design + deployment summary (2026-05-25)

The Letta Docker server's `http://letta:8283/v1/agents/...` endpoint
goes away under local mode. Replacement architecture committed as
`letta-local-runner/` + `scheduler-service/route=local`:

```
scheduler-service (Docker, unchanged orchestrator)
  → action_type=agent_message, route=local
  → _send_via_local_runner POSTs to host.docker.internal:8920/invoke
  → letta-local-runner (host, launchd, FastAPI/uvicorn)
  → per-agent asyncio.Lock acquired (prevents the empirically-verified
     local-mode concurrent-invocation race)
  → subprocess: `letta --backend local --new --agent <id> -p <msg>`
  → race-loss heuristic retry on exit==0 + empty stdout
  → response captured, returned to scheduler-service
```

**Runner shelf-life:** 6-18 months. Retire when Letta either fixes
concurrent same-backend invocation safety in the binary, or ships
a `letta server --backend local` HTTP mode.

**Verified end-to-end 2026-05-25:**
- scheduler-service creates a one-off job with `route=local`
- Job fires at the scheduled time
- Runner forks letta against the canary backend dir
- Canary agent replies `E2E-OK`
- scheduler-service marks the execution `succeeded` (4.61s round-trip)
- JSONL log on the host records the invocation

**Commits:** 8c456987 (runner), 7c544069 (scheduler executor),
82f11dc6 (launchd wrapper).

**Operational follow-ups during agent migration (per agent, one at a time):**
- Update job records: `route=letta` → `route=local`, swap agent_id from
  Docker UUID to local-mode `agent-local-*` UUID.
- Update plist `LETTA_LOCAL_BACKEND_DIR` to point at the production
  backend dir (currently set to canary for testing — installed copy
  at `~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist`).
- Update any agent system protocols that reference scheduler-mcp tools
  to use Bash+curl against scheduler-service REST API (matches
  feedback_capability_pattern_choice memory note).

### Agent fleet inventory snapshot (from canary investigation)

44 total agent records in Letta server, but operational set is small:

- **Load-bearing (8):** Mission Control, pulse-monitor-agent_copy,
  daily-schedule-agent-sleeptime, tasks-agent, calendar-agent_copy,
  work-packet-assembler, email-agent, docs-and-transcripts-agent.
- **Domain (3-4):** sports_and_media_maven, auto_madden_agent,
  main-assistant-agent-kinara, steward.
- **Sleeptime variants (6):** Several `*-sleeptime` agents whose
  post-memfs purpose is unclear. May not be needed under local mode.
- **Retired / clutter (26):** 10× "Letta Code" leftover subagents,
  3× MC-rogue strays, 4× XXX-Ignore, 7× XXX-ARCHIVE, plus old
  calendar-agent, retired pulse-monitor predecessors.

Realistic final-state fleet under local mode: **8-12 agents**, plus
ephemeral subagents that don't persist records.

## Two-track plan

### Track 1 — Upgrade letta-code-patched 0.24.2 → 0.25.8 (independent)

This is needed regardless of local-mode decision. Pa-web subprocess
is on a pinned old version; bringing it current is hygiene.

**Steps:**
1. Bump `letta-code-patched/package.json` dependency to `0.25.8` (verify
   that's still the newest; check npm registry for 0.26+ on the day)
2. Run `./build.sh`
3. If `apply_letta_code_self_hosted_handle_fix.py` fails to find markers,
   investigate whether PATCH-3205 landed upstream (good outcome — fewer
   patches to maintain). Drop the patch if landed.
4. If `apply_letta_code_memfs_external_git.py` fails markers, port the
   patch against the new bundle shape (still needed for Docker server
   mode until/unless we move to local).
5. Verify both patches yield expected marker counts, `--version` returns
   the new pinned version.
6. Smoke test in a one-shot pa-web-ui subprocess against current Docker
   letta server. Confirm:
   - Subprocess spawns cleanly
   - Memfs Read/Edit roundtrips through Gitea
   - A simple agent message completes end-to-end
7. If smoke passes: `docker-compose up -d --build pa-web-ui`
   (build-time install per WIP item #91 decision)
8. Monitor pa-web-ui for a day; rollback to 0.24.2 if regressions.

**Effort:** ~half day if both patches re-apply cleanly. 1-2 days if
either patch needs porting against new bundle shape.

**Risk:** low — pinned reversal is one git revert + rebuild.

### Track 2 — Local-mode canary (depends on track 1)

Following the Letta support agent's 5-step critical path:

**Step 1: Disposable isolation.**
```bash
export LETTA_LOCAL_BACKEND_DIR=/tmp/letta-canary-$(date +%s)
mkdir -p "$LETTA_LOCAL_BACKEND_DIR"
```
Verify global `letta` binary (0.25.8+) recognizes `--backend local`.
Do NOT touch `~/.letta/lc-local-backend/`.

**Step 2: Verify local-mode basics.**
- `letta --backend local connect anthropic` (or openai — whatever has a
  key in `.env` already)
- `letta --backend local agents create --name canary-1`
- Open a session, send "hello," confirm response
- Inspect `$LETTA_LOCAL_BACKEND_DIR/memfs/<agent-id>/memory/` — verify
  it materializes
- Have the agent edit a memfs file via its `Edit` tool; confirm commit
- Have the agent invoke a basic tool (Bash); confirm it works

**Step 3: Import one agent's system memory.**
Candidate: **calendar-agent_copy** (`agent-892a2d58-b9f6-4baf-84f3-c431fe46487d`)
- Already battle-tested through the cycle-1 canary
- Small system/ surface
- Non-critical if reset

```bash
# Export from Gitea
docker exec gitea git --git-dir=/data/git/repositories/agents/agent-892a2d58-b9f6-4baf-84f3-c431fe46487d.git \
  archive --format=tar HEAD > /tmp/calendar-export.tar

# Extract just system/ into the local-mode canary agent's memfs
mkdir /tmp/calendar-export
tar -xf /tmp/calendar-export.tar -C /tmp/calendar-export
cp -r /tmp/calendar-export/system/ "$LETTA_LOCAL_BACKEND_DIR/memfs/<canary-agent-id>/memory/system/"
```

Restart the canary agent, confirm it loads the imported system/ files
into its prompt.

**Step 4: System memory only first pass.**
Defer to a second pass:
- Archival memory (Letta passages)
- Tool attachments (Letta tools registered via Python scripts)
- MCP server attachments
- Cron job integration

**Step 5: Persistence canary.**
- Agent reads its `system/scheduling_protocol.md`
- Agent edits one memory file via `Edit`
- Kill the letta binary, restart it, resume the canary agent
- Confirm the edit survives

**Effort:** 1 day if basics work as documented. 2-3 days if any of the
unknowns above (especially #1 cron integration, #3 multi-agent) reveal
showstoppers.

**Risk:** zero to production — fully isolated under a temp
`LETTA_LOCAL_BACKEND_DIR`.

## Decision gates

Before any production work:

**Gate A — Track 1 complete.**
- letta-code-patched at 0.25.8 in pa-web-ui
- pa-web-ui stable for ≥48h post-deploy
- Patch maintenance picture clarified (which patches still needed)

**Gate B — Local mode minimally viable.**
- Canary steps 1-5 all pass
- Cron integration question (unknown #1) has an answer
- MCP attachment question (unknown #2) has an answer
- Multi-agent question (unknown #3) has an answer

**Gate C — Migration plan reviewed.**
- A second plan doc (`docs/plans/YYYY-MM-DD-letta-local-mode-migration.md`)
  drafted with per-agent migration runbook
- Decision: full migration, hybrid (some agents local, some Docker), or
  abandon (stay Docker)
- User reviews and approves before any production change

## Suggested sequencing

1. **This week:** Track 1 (upgrade letta-code-patched).
2. **Next week:** Track 2 (local-mode canary).
3. **After canary:** Write the migration plan doc, gated review, then
   either start migration or formally close investigation.

Track 2 work is small and isolated enough that it can happen in
opportunistic windows; doesn't need to block other queue items.

## Out of scope

- Migration of production agents — handled in a separate plan doc once
  the canary clarifies feasibility
- Letta API (hosted/cloud) evaluation — note it as a third option but
  not the focus of this investigation
- Multi-user / multi-machine deployment of local mode — single-user
  single-machine only

## References

- Letta Code overview: https://docs.letta.com/letta-code
- MemFS docs: https://docs.letta.com/letta-code/memory
- Models / providers: https://docs.letta.com/letta-code/models
- Providers detail: https://docs.letta.com/letta-code/providers
- Docker (legacy): https://docs.letta.com/guides/docker
- PR #2043 (embedded-backend historical anchor): letta-ai/letta-code#2043
- Upstream source to inspect when needed: `src/backend/local/`,
  provider registry, memory filesystem code
