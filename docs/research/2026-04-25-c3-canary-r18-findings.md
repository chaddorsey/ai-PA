---
date: 2026-04-25
status: definitive — answers R18 from the migration plan
canary: memfs-canary-rest (torn down post-test)
parent-plan: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
phase: 4 — Canary C3
---

# C3 Canary Findings — REST writes vs memfs-enabled agents

## Summary

The R18 question — "what happens to external REST writes when an agent has `git-memory-enabled` set?" — is now empirically answered.

**Three findings, all with major migration-design implications:**

1. **Pre-existing attached blocks get soft-deleted on first sync.** Any block attached to an agent BEFORE the `git-memory-enabled` tag is set will be removed by the first `sync-from-git` call (per Fimeg patch 02 — delete propagation). The canary's `awareness-c3` block disappeared from the agent's attached-blocks list immediately after first sync.

2. **External `PATCH /v1/blocks/<id>` returns HTTP 500 on memfs-enabled agent blocks.** Server traceback: `subprocess.CalledProcessError: Command '['git', 'reset', '--hard']' returned non-zero exit status 128` from `letta/services/memory_repo/git_operations.py:45`. The patched server tries to commit the change back to a working memfs checkout, but in the external-Gitea pattern the server only has bare repos at `/root/.letta/memfs/repository/{org}/{agent}/repo.git`. There IS no working tree to reset, so the operation fails. **This is not an intentional refusal — it's a hard incompatibility between Postgres-block PATCH semantics and the bare-repo-only server-side memfs storage.**

3. **Brand-new blocks created and attached AFTER memfs enable get wiped on next sync.** R18-B test: created a new block via `POST /v1/blocks/`, attached via `PATCH /v1/agents/<id>/core-memory/blocks/attach/<bid>` (HTTP 200, attach succeeded), then ran `sync-from-git` — block was soft-deleted because it wasn't in the memfs tree. Delete-propagation is **unconditional**: every block not in the tree gets removed.

## Combined consequence

**Memfs-enabled agents are pure-memfs.** Every block the agent has must originate from a memfs file. There is no "memfs for some blocks, Postgres for others" within a single agent. There is no graceful coexistence with external PATCH writers.

The migration eligibility model that emerges:

- **Agent has zero externally-mutated blocks** → memfs migration is straightforward (just represent each block as `system/<label>.md`)
- **Agent has externally-mutated blocks** → memfs migration requires either:
  - (a) Redirecting every external writer to push the change to Gitea via git instead of PATCH /v1/blocks (substantial re-architecture per writer)
  - (b) Detaching the externally-mutated blocks from the agent and moving them to a shadow agent that stays on Postgres
  - (c) Skipping memfs migration for this agent entirely

## Per-agent migration eligibility (current ecosystem)

Based on this finding, here's the inventory:

### Cannot migrate (without writer re-architecture)

- **Tasks agent (`agent-dd154...`)** — has 6 Class-B shared queue blocks attached, with 6 external writers (gmail-watch, slackbot, scheduling-orchestrator, drive-rag, spark-drain, etc.). Migration requires either redirecting all 6 writers to git push (large) or detaching all 6 queue blocks (which destroys the IPC pattern).

### Audit needed

- **MC** — has 5 attached blocks: `assistant_role_playbook`, `important_people`, `rover_status_log_202603a`, `shared_context`, `laptop_execution_preference`. Need to identify which (if any) have external writers.
- **Calendar / Email / Pulse / Media / Docs / scheduler agents** — each needs the same audit before migration eligibility is decided.

### Eligible (likely)

- **Agents with only persona/human blocks** (which are agent-self-mutated only via the agent's memory tools or letta-code's bash/Edit) → straightforward migration.
- **Throwaway/disposable agents** — letta-code default agents, MC-rogue forks, work-packet-assembler if it doesn't have external writers.

## What this means for the migration plan

The Phase 4.5 Migration Impact Analysis template's section 5.4 ("Writer impact per row of §2") just became the single most important section. **Before any production agent is migrated, we must enumerate every external writer to its blocks and decide for each: redirect, detach-and-shadow, or block migration.**

The plan's R20 (six Class-B blocks stay on Postgres permanently) was already correct, but the implication is sharper now: **any agent attached to those Class-B blocks cannot be memfs-migrated without breaking those writers**. Tasks agent in particular is essentially memfs-incompatible in its current form.

## Updated migration scope

The plan's "Path A — minimal scope" already centered on MC + letta-code clients. With the C3 finding:

- **Path A still viable** if MC's 5 attached blocks are all agent-self-mutated (audit pending)
- **Path B (full migration)** is now harder than I'd assumed — every REST-only agent needs a writer audit + redirect plan
- **Path C (universal via consolidator pattern)** — also affected. Consolidators write to memfs files via bash/Edit, but if the consolidator subagent attaches a NEW block via REST, that block gets wiped on next sync. Consolidator pattern must be: agent self-edits memfs files only, never attaches new Postgres blocks.

## Test artifacts

- `letta/.letta/canaries/c3-snapshot/c3-memfs-final.tgz` — final memfs state of the C3 canary, preserved for forensic review.
- `letta/.letta/canaries/memfs-canary-rest.agent_id.torn-down` — record of the torn-down canary's ID.

## Recommended next steps

1. **C4 (multi-channel canary)** — proceed; the constraint that REST writes don't work means the multi-channel test is mostly about read-side concurrent behavior, not write conflicts.
2. **C5 (consolidator canary)** — proceed; explicitly test that scheduler-driven Task invocations correctly produce memfs file edits (not Postgres block creates).
3. **MC block audit** — before any MC impact analysis can be filled in, we need to know which of MC's 5 attached blocks have external writers.
4. **Writer-redirect feasibility study** — out of scope for this canary, but worth scoping: would `gmail-watch-service` find it tractable to push commits to a Tasks-agent memfs Gitea repo instead of PATCH'ing a Postgres block? The cost-benefit determines whether memfs is ever feasible for the Tasks agent.
