# Followup brief for Ezra — pattern decomposition + open questions

Following up on your shared-coordination-repo recommendation (your option 1 from our last exchange). I've now done a comprehensive audit of memory-block usage across my ecosystem (44 agents, 326 attached blocks, ~12 blocks shared across 3+ agents, 6 hardcoded block IDs in service code). Trying to lock the architecture before migrating anything — would value your read on whether the decomposition I'm landing on is right and where the rough edges are.

## My five distinct activity patterns

After the audit, what's currently in memory blocks decomposes into five distinct usage patterns, each with different semantics:

1. **Cross-agent shared knowledge** — `important_people` (12 agents), `human` (6), `task_extraction_tool_use_guidelines` (12), `agent_info` (4), `three_month_priorities` (4). Stable reference data. Mutation cadence: rare (manual updates). Reads: every turn by every agent that has it attached.

2. **Cross-agent IPC queues** — six hardcoded block IDs: `queued_tasks_from_email`, `queued_tasks_from_slack`, `queued_tasks_from_meetings`, `queued_tasks_from_drive`, SPARK queue, plus `extracted_tasks` (which is partially this). External non-Letta services (gmail-watch-service, slackbot, scheduling-orchestrator, drive-rag-service) PATCH these via HTTP. Mutation cadence: high (multiple times per day). Single consuming agent processes + clears.

3. **Per-agent self-mutating memory** — persona, human (per-agent variant), agent-specific awareness blocks, role playbooks. Agent updates via `core_memory_replace` or custom tools. Mutation cadence: per-turn potentially.

4. **Coordination state** (pa-routing-handler pattern) — `coordination_task_default`, `coordination_gathered_default`, dynamically-created `coordination_task_<task_id>` blocks. Lifecycle: pa-routing-handler `attach`es the same block to N agents for a meeting-prep / multi-agent task, agents write outputs, handler aggregates, then `detach`es. Per-task lifetime is minutes-to-hours.

5. **Lifecycle data** — `extracted_tasks` block (block-90300b77, shared across 8 agents). pa-web-ui has a full CRUD surface against it (transition, merge, delete, reassemble, omnifocus-create) plus polls every 30s for a sidebar render. Agent-side `add_extracted_tasks` tool also writes to it from any agent. Multiple writers, multiple readers, rich lifecycle.

## My current synthesis: four-substrate decomposition

Based on the patterns + your guidance + the C3 canary finding (memfs-enabled agents are pure-memfs: external PATCH on memfs-backed blocks fails with `git reset --hard` 500, pre-existing attached blocks soft-delete on first sync, post-tag-attached blocks wipe on next sync — confirmed empirically), I'm landing on this destination architecture:

| Substrate | What it holds | Patterns |
|---|---|---|
| **memfs (per-agent Gitea repo)** | per-agent identity + self-mutating memory | Pattern 3 |
| **Shared Gitea repo** outside any agent's memfs | stable cross-agent reference state | Pattern 1 (your option 1) |
| **Postgres direct** (DB tables, NOT memory blocks) | transactional/queue state with multiple external writers | Patterns 2 + 5 |
| **Task-based messaging** (`Task(agent_id=..., conversation_id=...)`) | reactive cross-agent coordination | Pattern 4 (your option 3) |

The takeaway I'm drawing: memory blocks today are doing four genuinely different jobs, and the new paradigm decomposes them into four substrates that each have better fit for one of those jobs. Memfs is the right substrate ONLY for Pattern 3.

## Where I'm confident

- **Pattern 3 → memfs**: clean fit, this is what memfs was designed for.
- **Pattern 1 → shared coordination repo**: your recommendation, plus the audit confirms it's stable reference data for which git's mental model is appropriate. Skill wraps the pull/edit/commit/push convention.
- **Pattern 4 → either direct REST message injection or Task-based messaging**: avoids cross-agent attach/detach entirely.

## Where I'm less sure (open questions for you)

### Q1. Pattern 2 (high-cadence external-writer queues) — git push or Postgres direct?

Your option 1 says shared Gitea repo, but your framing was about "shared coordination state" with humans-or-handful-of-agents cadence. My queue blocks are different: gmail-watch-service hits one multiple times per day from a non-Letta-aware service, slackbot fires on every shortcut invocation, etc. Each is a high-cadence, multi-writer, single-consumer transactional pattern. Two specific concerns:

- **Concurrent push conflicts**: with 4-5 external services pushing entries to the same queue repo, conflicts on shared files seem inevitable. git's "designed for multiple writers" applies to humans on different timezones, not 5 services updating the same file in the same minute. What does the conflict-resolution flow look like in practice for that cadence?
- **Decoupling argument**: queues aren't really "memory" — they're transactional inbox state. Moving them to a Postgres `pa_web.task_queue` table feels architecturally cleaner: external services INSERT, consumer SELECT/DELETE. Do you actively recommend keeping queues in git-as-substrate (consistent with your option 1), or do you separately distinguish "stable reference shared state" (git fits) from "high-cadence transactional shared state" (Postgres fits better)?

### Q2. Pattern 5 (`extracted_tasks` lifecycle data) — out of Letta entirely?

This block has 8 agent readers + a rich CRUD surface in pa-web-ui (transition, merge, delete, reassemble) + agent-side `add_extracted_tasks` tool writers. pa-web-ui's sidebar polls every 30s. Migration to a shared git repo would mean every CRUD becomes a pull/edit/commit/push cycle, latency goes from ~10ms to seconds, and the polling cascades sync-from-git work across 8 agents.

My read: this block is structured operational data masquerading as memory. The right move is **`pa_web.tasks` table direct in Postgres**, with both `add_extracted_tasks` (agent-side) and pa-web-ui CRUD going through SQL/REST against that table. Reading agents get a small "fetch_tasks" tool that queries the table.

Is this a sane move, or am I missing a Letta-blessed way to handle "structured shared lifecycle data" that I should consider?

### Q3. Shared Gitea repo — operational rough edges in practice

For your option 1 — what failure modes have you seen in the wild? Specific concerns:

- **Concurrent edit conflicts**: two agents pull, both edit the same file, both push. Second push fails with `git rejected non-fast-forward`. Recovery: rebase + retry? Skill swallows it transparently? Or surfaces to the agent for resolution?
- **Stale reads**: agent pulls at turn-start, processes for a while, another agent pushes, original agent's "current" view is stale by the time it makes a decision. How is this handled — pull-immediately-before-write only? Optimistic-concurrency check?
- **Namespacing**: how do you suggest dividing a single `agents-shared-coordination.git` to avoid conflicts? Per-agent subdirs (`tasks-agent/`, `email-agent/`)? Per-topic subdirs (`important_people/`, `priorities/`)? Free-for-all with naming conventions? Does it matter?
- **Sync cadence**: should the skill auto-pull on every turn start? Only when the agent reasons it's needed? Polling-style background pull?

### Q4. Identity-vs-coordination boundary — where exactly is it?

You said "a memfs tree represents that agent's own self-modifying prompt context. Shared coordination data isn't part of any one agent's identity." That's the principle I'm trying to apply, but the boundary is fuzzier in practice. Some examples from my ecosystem where I'd value your judgment:

- **`important_people` block** — shared across 12 agents. Clearly Pattern 1 / shared-coordination repo, agreed. But — is it also valid for an individual agent to have its OWN `important_people.md` in `system/` that's its private working knowledge of who matters to ITS specific role, separate from the shared one? Or is duplication an antipattern?
- **`agent_info` block** — currently shared, holds metadata about who the other agents are. This feels like infrastructure rather than knowledge. Is this still shared-coordination-repo territory, or does it belong somewhere else (config file? environment vars?)?
- **`task_extraction_tool_use_guidelines` block** — currently shared, basically an operations manual. This is identical-content-pinned-to-many-agents'-context. Becomes a small skill instead, or stays as shared coordination repo content?

### Q5. ADE visibility tradeoff for shared state

You called out: "no native ADE visibility into shared state, no automatic recompilation when shared files change." For my use case where I run an Agent Development Environment-equivalent occasionally for inspection but not as primary surface — is this just a "nice to have, gone for now" or is there an operational impact I should plan for? Specifically: if I edit a shared coordination file directly via Gitea web UI, do my agents need an explicit signal to re-read, or do they pick it up at next turn naturally because the skill pulls?

### Q6. LET-8217 trajectory

You said no ETA either way. Two specific sub-questions:

- If LET-8217 lands as "point N agents at one repo URL," does that mean the application-layer shared-coordination-repo pattern becomes obsolete and we should expect to migrate to it? Or do they coexist (shared-coordination-repo for fully-decoupled state, LET-8217 for state Letta wants to know about)?
- Is there a way to architect today's shared-coordination-repo pattern so that *if* LET-8217 lands, transitioning to it is mechanical rather than a re-architecture?

## What I'd love from you

If your answers to Q1-Q6 don't take long, the architecture locks in cleanly. If any answer surfaces design considerations I haven't seen, that's the highest-leverage signal I can get before committing to migration shape.

I'm not on a hard deadline; better to design once than migrate twice.

---

**Reference for context**: Audit lives in my repo at `docs/research/memfs-audit-2026-04-25/AUDIT.md` if at any point a more detailed breakdown of any specific block / agent / pattern would be useful — happy to share excerpts or specific block topology.
