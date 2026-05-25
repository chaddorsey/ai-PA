---
title: Letta Code local-mode investigation + migration assessment
date: 2026-05-25
status: planning — investigation not started
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
