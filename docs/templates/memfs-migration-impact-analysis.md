---
date: YYYY-MM-DD
agent: <agent-name>
agent-id: <agent-...>
status: draft | reviewed | approved | migrated | rolled-back
reviewer: <user>
parent-plan: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
phase: 4.5 — required gate before any production agent migrates to memfs
---

# Memfs Migration Impact Analysis — `<agent-name>`

> **Purpose**: A required, written, reviewed artifact that surfaces the full per-agent blast radius before that agent is migrated to memfs. The plan's R17–R19 + Phase 4.5 gate this document on every production migration. No agent migrates without an approved impact analysis on file.

> **How to use**: Copy this file to `docs/migrations/<YYYY-MM-DD>-impact-analysis-<agent-name>.md`, fill in every section. Sections marked **REQUIRED** must be complete before sign-off. Sections marked **CONDITIONAL** can be omitted with a one-line "N/A — <reason>" if genuinely not applicable.

---

## 1. Agent identity (REQUIRED)

| Field | Value |
|---|---|
| Name | `<agent-name>` |
| Agent ID | `<agent-...>` |
| Created | `<ISO date from POST /v1/agents/{id}>` |
| Description | `<from agent record>` |
| Tags | `<list of tags>` |
| Hidden | `<bool>` |

**LLM config** (verbatim from `GET /v1/agents/{id}` → `llm_config`):
```json
{
  "model": "...",
  "model_endpoint_type": "...",
  "model_endpoint": "...",
  "provider_name": "...",
  "handle": "...",
  "context_window": ...,
  "max_tokens": ...
}
```

**Embedding config** (verbatim):
```json
{ ... }
```

**Tool list** (from `GET /v1/agents/{id}/tools`):
- `<tool-name>` — purpose, source (built-in / MCP / custom Letta tool / client-side)
- ...

**Memory blocks attached** (from `GET /v1/agents/{id}/core-memory/blocks`):
| Label | Block ID | Size (bytes) | Last modified | Description | Class |
|---|---|---|---|---|---|
| persona | block-... | ... | ... | ... | A (per-agent) |
| ... | | | | | |

> **Class A** = per-agent core memory (persona, human, agent-specific awareness blocks). Migrates to memfs cleanly.
> **Class B** = shared queue / IPC blocks (the six in R20). **Stays as Postgres blocks**. Lists for inventory only.
> **Class C** = cross-agent coordination blocks (pa-routing-handler patterns). Stays as Postgres.

---

## 2. Current writers (REQUIRED)

Enumerate **every external service or human-driven path that writes to this agent's memory or messages.** Be explicit — missing one here is the most common cause of post-migration drift.

| Writer | Surface (REST endpoint / SDK / direct DB) | Frequency | Target | Write semantics |
|---|---|---|---|---|
| gmail-watch-service | `PATCH /v1/blocks/<id>` | per-incoming-email (1-30/day) | `block-e64dcb37-...` (queued_tasks_from_email) | append |
| (example — adapt) | | | | |

For each writer, also note:
- **What block / message field it touches**
- **Whether it cares about the response shape** (some writers fire-and-forget; some read back)
- **What happens if the write fails** (retry? alert? silent loss?)

> Empirical question to answer per writer (carried over from C3 canary verdict): when the agent has `git-memory-enabled` tag, will this writer's REST call still succeed against the Postgres-cached block? If yes, it's safe to leave as-is. If no, this writer needs redirection (separate scope).

---

## 3. Current readers (REQUIRED)

Enumerate **every consumer of this agent's memory blocks or messages.**

| Reader | Surface | Frequency | Reads | What it does with the data |
|---|---|---|---|---|
| pa-web-ui sidebar | `GET /v1/blocks/block-90300b77-...` | every 30s while sidebar open | extracted_tasks block | renders draft list |
| (example — adapt) | | | | |

---

## 4. Current invocation patterns (REQUIRED)

Every way the agent receives messages / triggers / runs.

| Invoker | Path | Cadence | Notes |
|---|---|---|---|
| pa-web-ui chat | `POST /v1/agents/{id}/messages` via letta-code subprocess | user-initiated | client_tools approval flow |
| LettaBot Telegram | `POST /v1/agents/{id}/messages` via letta-code subprocess | user-initiated, Telegram-mediated | LettaBot still on stock 0.18.2 letta-code |
| scheduling-orchestrator | `POST /v1/agents/{id}/messages` direct REST | cron-driven, several times/day | bypasses letta-code |
| (example — adapt) | | | |

For each invoker, mark whether it goes through:
- **letta-code (with our patches)** — subagents work, Task available
- **stock letta-code** — patches not in effect
- **direct REST** — no letta-code at all; subagents NOT available; only memory_*/server-side tool calls

---

## 5. Memfs migration impact — section by section (REQUIRED)

Walk through every item in §1–§4 and answer: **what changes for this item after `git-memory-enabled` is set?** Reference the canary verdicts from C3 (REST writes), C4 (multi-channel), C5 (consolidator) by name where they apply.

### 5.1 LLM/embedding config impact
- Does the patched server image (`letta-local:0.16.7-memfs-v1`) handle this agent's `llm_config.handle` correctly? (Should — but verify on canary.)
- Is the agent's `compaction_settings.model` an auto-mode handle that won't resolve on self-hosted? If yes: pre-migration step to PATCH it to a real registered handle.

### 5.2 Tool surface impact
- For each tool in §1, will it still work after migration?
- Specifically: does the agent rely on `core_memory_replace` / `core_memory_append`? These work on Postgres blocks; under memfs, the agent's filesystem tools (bash/Edit) become the primary editing primitive. **If the agent has no filesystem tools and no letta-code subprocess client, it loses the ability to self-edit memory.** This is the central design constraint.

### 5.3 Per-block migration plan
For each Class-A block in §1, decide:
- **Migrate to memfs as `system/<label>.md`** — pinned in context, `description` from block, `value` becomes file content
- **Migrate as non-system memfs file** — visible in tree but not pinned (use sparingly; agent has to remember to read it)
- **Stay on Postgres** — for blocks that external writers must continue to mutate (Class B style — but if any writer in §2 is THIS agent's domain, that's a flag for "this might not actually be a clean memfs candidate")

For each Class-B block in §1: stays on Postgres. **Document it but do not migrate.** R20 in the parent plan is canonical.

### 5.4 Writer impact (per row of §2)
- Does each writer still successfully write under `git-memory-enabled`? (Reference C3 canary verdict.)
- Are there any writers whose semantics break (e.g. expects to mutate a block that's now memfs-backed)?
- For writers we keep as-is: how does drift between their Postgres writes and the agent's memfs file get reconciled? **This is potentially the biggest risk surface.**

### 5.5 Reader impact (per row of §3)
- Same question as 5.4: do they still get correct data?
- For readers like pa-web-ui sidebar that poll a block: does the polling cadence vs. the memfs sync cadence introduce visible lag?

### 5.6 Invoker impact (per row of §4)
- For invokers going through patched letta-code: subagents now work, Task available. Are there flows that weren't using subagents before but might start now? (Cost / latency impact.)
- For direct-REST invokers: their experience is unchanged — they still POST messages, server still routes. Only the agent's memory back-end differs.

---

## 6. Risks specific to this agent (REQUIRED)

List failure modes that are **unique to this agent's role/usage**. Generic risks (e.g. "the patch might have a bug") belong in the parent plan; this section is for things that wouldn't apply to a different agent.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| (example) Email agent depends on extracted_tasks block being readable from pa-web-ui every 30s; if memfs adds latency to block reads, sidebar refresh may stall | Medium | High UX | Verify polling latency in Phase 4 C5 canary before migrating Email |

---

## 7. Pre-migration prerequisites (REQUIRED)

Things that must be true / done before we tag the agent with `git-memory-enabled`.

- [ ] Phase 4 C1-C5 canaries all passed
- [ ] C3 verdict on REST writes is **"writes succeed and are observable post-migration"** (or, if not, every relevant writer in §2 has been redirected)
- [ ] C4 verdict on multi-client behavior is **clean** for this agent's invoker pattern
- [ ] If agent depends on subagents post-migration: C5 consolidator verdict is green
- [ ] Agent's current `compaction_settings.model` is not an auto-mode handle (or has been PATCHed to a real handle)
- [ ] If migrating to a Gitea-backed memfs: the per-agent repo exists at `gitea://agents/<agent-id>.git`
- [ ] Backups verified current — last successful backup includes this agent's blocks AND the gitea-data volume

---

## 8. Migration steps (REQUIRED)

Concrete, ordered, copy-pasteable steps for the actual migration. Should match the parent plan's Phase 5 / 6+ patterns.

```bash
# 1. Snapshot current state
curl -s "http://localhost:8283/v1/agents/<agent-id>" > /tmp/pre-migration-snapshot-<agent>.json

# 2. Pre-migration handle fix (if compaction_settings.model is auto-mode)
# (only if checked-off in §7)

# 3. Initialize Gitea repo
./scripts/memfs-init-agent-repo.sh <agent-id>

# 4. Tag agent with git-memory-enabled
# (use the GET-append-PATCH-replace-safe pattern per the plan; do NOT just PATCH tags=[...] which clobbers)

# 5. Run /memfs enable via a one-time letta-code session
LETTA_CODE_BIN=<patched> letta --agent <agent-id> -- /memfs enable

# 6. Verify initial sync
curl -s -X POST "http://localhost:8283/v1/agents/<agent-id>/memory/sync-from-git?recompile=true"

# 7. Run /doctor for memory reorganization
LETTA_CODE_BIN=<patched> letta --agent <agent-id> -- /doctor
```

(Adapt to specific agent.)

---

## 9. Post-migration verification (REQUIRED)

Within 1 hour of migration:

- [ ] Agent responds to a normal message via its primary invoker (§4 row #1)
- [ ] Class-B writers in §2 still successfully write
- [ ] Class-A blocks now appear as `.md` files in `~/.letta/agents/<agent-id>/memory/`
- [ ] Git log on the agent's memfs repo shows initial commit attributable to `/memfs enable`
- [ ] No HandleNotFoundError, no [DBG-3205] errors in Letta server logs
- [ ] No regression in latency on the primary invoker path (compare to pre-migration baseline)

Within 24 hours:

- [ ] Agent has self-edited at least one memfs file via bash/Edit (or, for REST-only agents, scheduler-driven consolidator has run)
- [ ] No errors in the agent's runs that reference memory operations
- [ ] No regression observed by user in agent's behavior

---

## 10. Agent-specific rollback (REQUIRED)

NOT the generic "switch image" rollback — this is what to do for THIS agent specifically if the migration goes wrong.

```bash
# 1. Remove git-memory-enabled tag (use GET-append-PATCH-replace-safe pattern)

# 2. Re-attach Postgres blocks if they were detached during /memfs enable
# (verify which blocks were detached; reattach them)

# 3. Validate via primary invoker
```

If rollback succeeds, file a follow-up note here describing what failed + why, before attempting re-migration.

---

## 11. Go/no-go criteria (REQUIRED)

What conditions must be true to proceed with the migration?

- [ ] All §7 pre-migration prerequisites checked off
- [ ] User has reviewed and signed §12
- [ ] No active production incident on this agent (check ops dashboards)
- [ ] User has 30+ minutes of attention available to monitor §9 verification

If any are false, do not migrate.

---

## 12. Reviewer sign-off (REQUIRED)

Reviewer fills in before migration proceeds.

- **Reviewer**: `<name>`
- **Date**: `<YYYY-MM-DD>`
- **Decision**: ☐ Approve — proceed with migration  ☐ Approve with conditions (list below)  ☐ Defer — concerns documented below
- **Conditions / concerns** (if any):

  > _Write any conditions, concerns, or revisions required before migration proceeds._

- **Approved migration window**: `<date / time / duration>`

---

## 13. Post-migration retrospective (CONDITIONAL — fill in after migration)

After migration is complete + 7-day soak, fill in:

- **Migration date / actual time taken**: ...
- **Issues encountered during steps in §8**: ...
- **Issues encountered during §9 verification window**: ...
- **Surprises (things not anticipated in §5 or §6)**: ...
- **What we'd do differently next time**: ...
- **Status**: ☐ Stable ☐ Rolled back ☐ Re-migrated after fixes

This section becomes input for the next agent's impact analysis (compounding institutional knowledge).
