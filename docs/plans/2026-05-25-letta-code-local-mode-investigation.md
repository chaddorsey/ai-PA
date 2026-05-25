---
title: Letta Code local-mode migration plan
date: 2026-05-25
status: track 1 complete; cron + MCP unknowns resolved; subagent + sandbox still under investigation; migration not yet started
last-updated: 2026-05-25
revision-log:
  - 2026-05-25 (initial plan written before any work)
  - 2026-05-25 (canary update — 5-step support-agent checklist complete; track 1 complete and committed)
  - 2026-05-25 (cron-integration unknown resolved — letta-local-runner deployed; scheduler-service route=local executor; end-to-end smoke through scheduler-service → host bridge → letta → canary verified)
  - 2026-05-25 (MCP attachment unknown resolved — local mode does NOT support MCP attachment in 0.26.1; only path forward is skill/CLI conversion; locks in the long-standing preference per feedback_capability_pattern_choice memory note)
  - 2026-05-25 (reframed from investigation to migration plan; added Calendly reconstitution roadmap as part of the skill/CLI conversion work)
  - 2026-05-25 (W6 subagent invocation resolved — Task tool works in local mode but with three caveats: subagents are ephemeral, no memfs inheritance, separate backend context)
related:
  - docs/followups/2026-04-29-pa-web-stability-todos.md (will get #99/#100 entry)
  - docs/runbooks/agent-memfs-conventions.md
  - docs/runbooks/memfs-migration-per-agent.md
  - letta-code-patched/README.md
  - letta-memfs-patches/patches/
queue-ref: pa-web-stability-todos #99 (to be added)
effort-estimate: 1-2 days for canary; production migration is multi-week
---

# Letta Code Local Mode — Migration Plan

> **Document scope evolution.** Started 2026-05-25 as an investigation
> doc with 8 unknowns. By end of day 2026-05-25, 2 unknowns were resolved
> (cron, MCP) and the infrastructure for both was committed. The doc has
> been rolling forward into a true migration plan. Subagent invocation
> and sandbox/custom-tool execution remain the two open unknowns gating
> the per-agent migration runbook.

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
| 2 | MCP server attachment | **RESOLVED — local mode does NOT support MCP attachment in 0.26.1; skill/CLI is the only path** |
| 3 | Multi-agent / subagent invocation | **Under active investigation (next)** |
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

### MCP attachment — design + audit summary (2026-05-25)

**Local mode does not support MCP attachment in letta-code 0.26.1.**
Bundle inspection: every `connectMcpServer` callsite POSTs to a remote
`/v1/tools/mcp/servers/connect` and requires `LETTA_API_KEY`. There
is no config-file path, no CLI subcommand, and no local backend
equivalent for declaring MCPs. The skill/CLI direction matches the
long-standing user preference in `feedback_capability_pattern_choice`
("Default to Skill + CLI-via-Bash over registering a new Letta tool"),
so this is the intended migration path.

**Audit of all 44 agents for actual MCP-domain tool usage:**

| MCP configured | Agents using related tools | Status |
|---|---|---|
| slack-tools | 6 agents (Mission Control, kinara, pulse-monitor +copy, tasks-agent, tasks-sleeptime) — but mostly via `run_slack` CLI tool, not MCP-prefixed ones | **Mixed** — 4 agents already on CLI; 2 (pulse-monitor original, tasks-sleeptime) still on MCP tools |
| graphiti-tools | **0 agents** | **DEPRECATE** — drop from `letta_mcp_config.json` immediately |
| rag-tools | **0 agents** | **DEPRECATE** — drop from `letta_mcp_config.json` immediately |
| calendly-tools | **0 agents** | **DEPRECATE** — 3 documentation references in calendar-agent_copy memory blocks ("offer Calendly links when external scheduling needed"), but no agent has a Calendly tool. The actual links are stored as facts; querying availability is not an active capability today. |
| scheduler-tools | 2 agents (daily-schedule, kinara) — 14 tool invocations | **CONVERT** to Bash+curl skill against scheduler-service REST API (already what `route=local` uses) |
| granola-tools | 2 agents (MC, docs-and-transcripts) — 4 tools | **CONVERT** to `run_granola` CLI or skill — modest scope |
| atlassian-tools (supergateway) | 2 agents (pulse-monitor +copy) — 4 tools | **CONVERT** to `run_atlassian` CLI — auth complexity warrants binary; service currently broken anyway (per 2026-05-24 diagnostic) |

**Implications:**

- Three MCPs (graphiti, rag, calendly) can be removed today regardless
  of migration timing — they have zero users. Pure cleanup.
- Scheduler MCP conversion is the highest-impact migration step
  (daily-schedule is one of the most active agents and the new
  `route=local` REST recipe already exists).
- Granola and Atlassian conversions are net-new CLI work; both
  could be deferred until those agents themselves migrate.

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

## Migration Workstream — Calendly Reconstitution (`run_calendly` CLI)

### State today

Calendly capability is built but dormant:

- Code lives in `calendly-mcp-server/src/` (production candidate) and
  `calendly-scraper/` (initial exploration with multiple scraper
  variants).
- `letta_mcp_config.json` still references `calendly-mcp-server:8086`
  but the Docker container is NOT running (verified `docker ps -a`
  shows nothing matching `calendly`).
- Zero of 44 Letta agents have any Calendly tools attached.
- Three tools were implemented:
  1. `calendly_slots` — scrape a Calendly page for available time
     slots. Requires JavaScript-rendered DOM, so Playwright (not
     plain BeautifulSoup) is the reliable approach. Calendly's public
     pages hydrate slots via JS after initial HTML load.
  2. `calendly_create_booking_link` — build a pre-filled booking URL
     the user clicks. URL-construction only, no scraping. Reliable.
  3. `calendly_book_slot` — fully automated booking. CAPTCHA-blocked.
     **Abandoned** per `calendly-mcp-server/BOOKING_SOLUTION.md`.

The team's documented decision is:
> LLM uses `calendly_slots` to find times → LLM calls
> `calendly_create_booking_link` to generate pre-filled URL → User
> clicks link → booking complete with one confirmation tap.

### Why this matters for migration

Memory blocks in `calendar-agent_copy/system/calendar_preferences.md`
direct the agent to "offer Calendly links for external scheduling,
new contacts." Today that's prose-only — the agent shares pre-known
URLs from memory. Under the local-mode target architecture, this
should become a live, agent-callable capability via Bash.

### Target shape: `run_calendly` CLI

Match the pattern already used by `run_slack`, `run_gws`,
`run_omnifocus`, `run_twitter`, `run_notebooklm` on MC. One CLI
binary, multiple subcommands, JSON output by default.

Proposed subcommands:

```
run_calendly slots <event-url> [--date-range 60]
    → returns JSON: list of {datetime, duration_minutes, slot_url}

run_calendly link <slot-url> --name "Chad Dorsey" --email "..." \
    [--question-0 "Meeting title"] [--question-1 "..."]
    → returns a pre-filled booking URL the user clicks

run_calendly profile <calendly-user-url>
    → returns JSON: list of {event-type-url, title, duration}
       (so the agent can discover what events exist for a person)
```

### Reconstitution plan

| Step | Task | Effort |
|---|---|---|
| 1 | **Pull the working scraper logic** from `calendly-mcp-server/src/calendly_slots.py` and `calendly_booking_link.py`. These are the production candidates; ignore `calendly-scraper/initial_testing/`. | 0.5h |
| 2 | **Pull the profile-discovery logic** from `calendly-scraper/calendly_profile_autodiscover_to_hours.py`. The MCP version didn't ship a profile-listing tool; this fills the gap. | 0.5h |
| 3 | **Repackage as a CLI**. Click or Typer-based. Match the conventions of existing `run_*` CLIs (subcommand structure, JSON output, `--format` flag). | 2h |
| 4 | **Keep Playwright as the slot-scraper engine**. Calendly's page hydrates JS-side; BeautifulSoup-only attempts in `calendly_url_to_times_bsoup.py` are unreliable. The CLI's `slots` subcommand should bundle a headless Chromium via Playwright. Auto-install browser on first run, OR document `playwright install chromium` as a prereq. | 1h (mostly Playwright setup + first-run UX) |
| 5 | **Drop `calendly_book_slot`**. CAPTCHA-blocked, documented as abandoned. Don't carry forward. | 0h |
| 6 | **Install on host PATH**. Match `run_slack` etc. — should be invokable as `run_calendly` from any local-mode agent's Bash. | 0.5h |
| 7 | **Write a system protocol skill** (`system/calendly_use_protocol.md` for agents that should know about it): "When user asks for external scheduling, use `run_calendly profile` to discover event types, `run_calendly slots <event-url>` to find times, present 2-3 options, then `run_calendly link` with their selection." | 0.5h |
| 8 | **Attach to relevant agents**: calendar-agent (after its migration), MC. Just appears in their Bash environment; no Letta-side attachment needed. | 0.25h |
| 9 | **Update `calendar-agent`'s `system/calendar_preferences.md`** to reference the new CLI instead of relying on prose memory. | 0.25h |
| 10 | **Drop calendly-mcp-server from docker-compose.yml** + remove `calendly-tools` from `letta_mcp_config.json`. The MCP server was never load-bearing; once the CLI ships there's no reason to keep the configuration. Container archive only. | 0.25h |
| 11 | **Add smoke test** — invoke each subcommand against a known stable Calendly URL (Zarek's test set was used historically, `calendly-scraper/zarek_slots.json` confirms). | 0.5h |

**Total estimated effort: ~6 hours.** Self-contained workstream; no
dependencies on the rest of the migration. Can ship anytime after
the migration framework is up.

### Sequencing relative to other migrations

This is **not on the migration critical path**. Calendar-agent uses
prose-only Calendly references today; that prose works the same way
under local mode (memory blocks load identically). The `run_calendly`
CLI can ship before, during, or after calendar-agent's migration to
local mode — they don't gate each other.

Recommended timing: **after MC migrates** (because MC is the agent
most likely to use Calendly conversationally), and at the same time
as the broader `run_*` CLI ecosystem audit per #98 in the WIP queue.

### Open questions for the reconstitution

- **Headless Chromium footprint.** Playwright + Chromium is ~250 MB.
  Acceptable for a CLI on the host, but worth flagging — `run_slack`
  and friends are <10 MB each. Document the size as a cost.
- **Rate limits.** Calendly may rate-limit scraping. The dormant code
  doesn't appear to handle this; reconstitution should add a polite
  default (1 req/sec) and a `--no-rate-limit` escape hatch for
  interactive use.
- **Auth.** Public Calendly pages don't need auth, but private/team
  links may. The current code is anonymous-only; flag this if any
  use case needs auth and plan a Calendly OAuth flow as a follow-up.

## Migration Workstreams Summary

This plan now describes multiple workstreams. Status snapshot:

| # | Workstream | Status |
|---|---|---|
| W1 | Track 1: letta-code-patched 0.24.10 → 0.26.1 | **COMPLETE** |
| W2 | Track 2 step 1: Local-mode canary (5-step support-agent check) | **COMPLETE** |
| W3 | Cron path: letta-local-runner + scheduler-service `route=local` | **COMPLETE** |
| W4 | MCP audit + skill/CLI conversion direction lock-in | **COMPLETE** (direction set; per-MCP work below) |
| W5 | Calendly reconstitution (`run_calendly` CLI) | **PLANNED** (this section) |
| W6 | Subagent invocation in local mode (unknown #3) | **IN PROGRESS** (next) |
| W7 | Sandbox / custom Letta tool execution (unknown #4) | Not yet started |
| W8 | Drop graphiti-tools + rag-tools + calendly-tools from `letta_mcp_config.json` (zero users) | **PLANNED** — 5 min cleanup, no dependencies |
| W9 | Convert scheduler-tools to Bash+curl skill (highest-impact MCP conversion) | Not yet started; recipe already exists from W3 |
| W10 | Convert granola-tools to `run_granola` CLI/skill | Not yet started |
| W11 | Convert atlassian-tools to `run_atlassian` CLI | Not yet started; currently broken anyway |
| W12 | Per-agent migration runbook | Not yet drafted; gated on W6 + W7 |
| W13 | Actual agent migrations, one at a time | Gated on W12 |

## W6 — Subagent invocation in local mode (RESOLVED 2026-05-25)

### Test

Canary spawned a subagent via the Task tool:
```
Use the Task tool to spawn a general-purpose subagent that reads
your system/persona.md and reports back its first 2 lines verbatim.
```

Tool result:
```
subagent_type=general-purpose
subagent_id=subagent-1779751092645-1
subagent_status=success
agent_id=agent-local-ab824141-bae7-4085-b2c0-a83eb019559f
```

Subagent then reported: `cat: /Users/dorseyhomeserver/.letta/system/persona.md: No such file or directory`.

The parent's actual persona.md lives at the canary backend dir
(`/tmp/letta-canary-1779727677/memfs/<canary>/memory/system/persona.md`).
Subagent looked at the wrong path.

### Findings

1. **Task tool works.** No PATCH-3205-style failure in local mode —
   there's no central server doing handle resolution. Just spawns.

2. **Subagents are ephemeral.** From the bundle (line 167118):
   ```js
   function scheduleCompletedSubagentCleanup(id2) {
     ...
     const timer = setTimeout(() => {
       store2.agents.delete(id2);  // in-memory Map
     }, completedSubagentRetentionMs);
   }
   ```
   ID format `subagent-{timestamp}-{counter}`. No disk record, no
   memfs dir, no persistence beyond the parent process lifetime
   plus the retention timeout.

3. **No memfs inheritance.** Subagents have their own backend
   context separate from the parent. They cannot Read parent's
   memfs files.

### Migration consequences for MC's current Task tool patterns

| Current pattern | Local-mode compatibility |
|---|---|
| Web search delegation (large result) | ✅ Works |
| Bash command delegation | ✅ Works |
| File-content summary (parent reads → passes content inline) | ✅ Works |
| File-content summary (subagent reads file from parent's memfs) | ❌ Need to refactor — parent must Read first, pass content as message |
| Cross-agent messaging (MC → daily-schedule-agent via Task) | ❌ Subagent is ephemeral; not the same as the real daily-schedule-agent. Use scheduler-service `route=local` (we built that — W3) for true cross-agent invocation. |
| Long-running background work | ⚠️ Tied to parent's lifetime; if parent exits, subagent state is lost |

### Two questions deferred

- **`subagent_type=fork`**: the bundle exposes this variant which is
  supposed to inherit parent's context. Could be the workaround for
  the memfs-inheritance gap. Not tested here.
- **Subagent tool surface**: does the subagent inherit parent's CLI
  access (Bash + `run_*` tools)? Probably yes since those are
  host-level, but not explicitly tested.

### Update to W12 (per-agent migration runbook)

For any agent migrating that uses the Task tool, the runbook needs
a step: **audit current Task tool delegations** and refactor any
that depend on subagent reading from parent's memfs. Pattern is
"parent Reads file → parent passes content as message to subagent
via Task" instead of "Task subagent → subagent Reads file."

For MC specifically: review the system prompt + protocol files for
any Task-tool-based "delegate this file analysis" pattern. The
Cisco/Danielle work-packet-assembler trigger flow uses Task; needs
specific review.
