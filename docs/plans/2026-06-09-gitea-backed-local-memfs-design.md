---
date: 2026-06-09
status: DESIGN (brainstorming output) — pending user review → writing-plans
topic: Make local-runner agents' per-agent memfs Gitea-backed (hub-hosted), as the standard always-on infra
decision: Approach A (hub-as-source-of-truth, pull-on-start/push-on-write, canary-first, coordination deferred)
related:
  - docs/plans/2026-06-08-distributed-ecosystem-offline-online-sync-sketch.md  # the trip; same substrate
  - docs/followups/2026-06-08-slackbot-conversational-migration-thinking.md
---

# Gitea-backed local-agent memfs — design

## Goal
Make each local-runner agent's per-agent **memfs** a **Gitea-hosted git repo** (the hub), so every letta-code instance that runs that agent — the host **local-runner** (crons/Telegram), **pa-web-ui**, and eventually the **laptop** — shares **one canonical memory per agent**. This establishes the standard, always-on-connected infrastructure. The trip/offline case and a shared-files plane are deferred; they build on this substrate.

## Scope
**In:** per-agent memfs → Gitea repo; configure the instances to use it; seed existing memory safely; roll out canary-first; document the concurrency model and defer coordination until evidence demands it.
**Out (deferred):** trip/offline sync; shared-files plane; a coordination/lock layer (until concurrency is proven to need it); **shared conversation history + cross-surface search** (captured as notes at the end — explicitly a separate plane).

## Current state (verified this session)
- **Local agents:** working copy at `~/.letta/lc-local-backend/memfs/<agent-id>/memory` — a real git repo, branch `main`, **no remote**, not in Gitea. The `memfs-sync-relay` regex `^agent-[0-9a-f-]{36}$` **excludes** `agent-local-*`, and it refreshes the **Docker** Letta server cache (`/v1/agents/{id}/memory/sync-from-git`), which local agents don't use.
- **Mechanism:** letta-code git-backs memfs via env `LETTA_MEMFS_GIT_URL` (a `{agentId}`-templated Gitea URL) + `LETTA_MEMFS_LOCAL=1`, plus `--memfs` / `--memfs-startup <blocking|background|skip>` (pull policy). `letta install` puts skills into a memfs repo. **pa-web sets these** (`gitea:3000` from inside Docker, its own backend at `/app/.letta`); the **local-runner sets none** — which is the only reason its agents are git-but-local-only.
- **pa-web will ultimately run the same `agent-local-*` agents** (user-confirmed) → the model is **multi-instance sharing one hub repo per agent**, not single-writer.
- **Gitea `agents` org:** hosts `agent-<36hex>` repos + `agents-canonical`. **No `agent-local-*` repos exist yet.**
- **Addressing:** `localhost` resolves IPv6 (`::1`) first; Gitea binds IPv4 only → use **`127.0.0.1:3030`** on the host, `gitea:3000` inside Docker, Tailscale hostname cross-host (later). Never `localhost`.

## Architecture (Approach A)
- **Hub = Gitea.** One repo per agent: `agents/agent-local-<id>` (consistent with existing `agents/agent-<hex>`). This is the **single source of truth** for that agent's memory.
- **Each instance keeps its own working clone** (separate backend dirs: runner `~/.letta/lc-local-backend`, pa-web `/app/.letta`, later the laptop), all pointed at the same `{agentId}` template, **addressed per network context** (`127.0.0.1:3030` runner, `gitea:3000` pa-web).
- **Consistency:** `--memfs-startup blocking` → each run pulls latest from the hub before acting; **push-on-write** propagates changes back. Eventual consistency via git.
- **Canonical** (`agents-canonical`) is already hub-hosted — unchanged.
- **Local agents bypass the relay** — letta-code's own `--memfs-startup` pull handles inbound; the relay's Docker-server cache refresh doesn't apply.

## Migration approach — seed-then-configure, canary-first
Per agent, in this exact order (order is safety-critical):
1. **Backup** the current working copy (tar the `memory/` dir).
2. **Create** the Gitea repo `agents/agent-local-<id>` (empty).
3. **Seed:** push the existing working copy's **full history** → the Gitea repo. **This must happen BEFORE any instance is pointed at the repo** — otherwise letta-code's startup pull from an empty remote could reset/wipe the working copy and lose accumulated memory.
4. **Configure** the instance(s): add `LETTA_MEMFS_GIT_URL` (templated, `127.0.0.1:3030` for the runner / `gitea:3000` for pa-web, token in URL) + `LETTA_MEMFS_LOCAL=1` + `--memfs-startup blocking`; reload.
5. **Verify:** instance pulls from Gitea, reads memfs correctly (system/ instructions intact, history present), a write pushes back, Gitea reflects it. Confirm no memory loss vs the backup.
6. **Canary instrumentation (the pivot):** explicitly test **contended-push behavior** — make two instances diverge on the same agent and observe letta-code's reaction: graceful (merge/rebase/retry) vs lossy (force-push/last-write-wins) vs fail. This single fact decides whether a coordination layer is needed and how soon.

**Canary agent:** a **low-stakes one first** — `docs` (`agent-local-3898b33a`) or `pulse` (`agent-local-d48b128a`) — not MC/calendar/tasks. Full verify incl. the contended-push test, then roll the rest.

## Concurrency model + mitigation ladder (coordination deferred)
Conflicts only occur when two instances write the **same agent's same file** in the **same window**. That surface is narrow (different agents/files auto-merge; an agent is usually active in one place at a time; high-churn rolling state — the digest — is already isolated from stable `system/`). Adopt only as needed:
1. **pull-on-start + push-on-write** (baseline).
2. **file-namespace hygiene** — rolling state in its own files (mostly already true).
3. **push-rebase-retry** — on rejected push, pull+rebase+repush.
4. **per-agent cross-instance lock** — only if 1–3 prove insufficient. (The runner already serializes same-agent runs internally; the gap is cross-instance, closed by a small advisory lock.)
**Pivot:** letta-code's contended-push behavior (canary). If lossy → move up the ladder sooner; **contingency** = a thin sync wrapper around letta-code (pull-rebase before, push-retry after) instead of relying on `--memfs-startup`.

## Connection to the trip (same substrate)
The multi-instance-on-server problem and the trip (server + laptop) are the **same problem** — N instances, own working copies, one hub repo per agent, needing reconciliation. The only differences are connectivity (always-on vs intermittent) and divergence window (seconds vs hours/days). **So Approach A is step 1 of the trip:** it proves the hub + pull + push model in the easy always-connected case; the trip later adds offline tolerance + heavier conflict reconciliation on the identical substrate, and reuses whatever coordination this work produces.

## Letta-grain caveat
Letta's local mode assumes a single owner per agent; their paid server is what's "meant" to do multi-agent reconciliation. With A we build **lightweight reconciliation on git/Gitea ourselves** (avoiding lock-in / the for-pay path) — which means **we own the sync/merge logic**. If letta-code fights a shared remote, the contingency wrapper above applies.

## Success criteria
- Each migrated agent's memfs is hosted in Gitea, **seeded with full prior history (zero memory loss vs backup)**.
- The runner (and pa-web) read/write the agent via the shared Gitea repo; pull-on-start + push-on-write verified end-to-end.
- The canary's **contended-push behavior is characterized**, and the coordination decision is made on that evidence (not assumption).
- Per-agent backup + rollback exist; all addressing uses `127.0.0.1` (no IPv6 trap).

## Risks
- **Seed-order memory wipe** → backup + seed-before-configure + verify-against-backup.
- **letta-code force-push under concurrency** → canary test → wrapper/lock.
- **pa-web + runner writing the same agent** → characterize on canary; mitigation ladder.
- **Addressing (IPv6)** → `127.0.0.1`.

## Rollback
Per agent: point the instance back to local-only (remove `LETTA_MEMFS_GIT_URL` / restore the pre-migration working copy from backup) and reload. The Gitea repo can stay (harmless) or be deleted. Nothing else depends on it until the rest of the fleet migrates.

---

## NOTES (separate plane, not in this spec): multi-agent conversation history & search in a shared model
*Captured per request; this spec shares **memfs (curated memory)**, NOT conversations or search.*

- **What shared memfs gives you:** a shared **brain** (the agent's durable, curated memory) across instances/surfaces. What it does **not** share: **conversation history** and **search**.
- **Conversations are per-backend file dirs** (`conversations/<id>/messages.jsonl` + meta), so they're **fragmented across instances/surfaces** — a DM thread in pa-web isn't visible to the runner's cron instance or the laptop. Shared memfs ≠ shared conversation history.
- **Design tension to resolve later:** do we even *want* one unified conversation across surfaces, or **separate threads per surface + unified memory/search**? Likely the latter — a DM thread, a Telegram thread, and a cron "conversation" are genuinely different contexts; merging them into one transcript is probably undesirable *and* the messiest to git-merge (high churn, append-heavy).
- **Search** (`conversation_search`, archival/vector search) is currently per-instance/local — an agent on the runner can't search a pa-web conversation, and local-mode archival storage isn't centralized. **Cross-surface search needs a shared index** (transcripts + archival memory): e.g., a shared **Postgres + pgvector** store all instances write to and query, or git-backed transcripts + a hub-reading search tool.
- **Options for when we design this plane:**
  - (a) **Git-back conversations too** (like memfs) — simplest mechanically, but high-churn merges and forces the "one unified thread?" question; probably wrong default.
  - (b) **Keep conversations surface-local; flow durable learnings into shared memfs** — aligns with "memory is the product, conversation is the process"; the shared brain accrues understanding regardless of which surface the conversation happened on.
  - (c) **A separate shared conversation/archival *index*** for cross-surface search, while live session state stays surface-local — best of both: unified search/recall without forcing unified live threads.
- **Recommended seed-stance:** treat **memfs (this spec) as the shared brain**; treat **conversation-history + search as a distinct future plane built as a shared *index* (option c)**, not by git-merging live transcripts. Decide unified-vs-per-surface threading when we design it.
- **Trip tie-in:** the laptop needs to **search past memory/conversations offline**, which resurfaces this exact question — so the shared-index design should be offline-aware when we get to it.
