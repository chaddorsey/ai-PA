---
date: 2026-04-25
status: comprehensive — input for memfs migration design brainstorm
parent-plan: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
sibling-research: docs/research/2026-04-25-c3-canary-r18-findings.md
---

# Memfs Migration — Comprehensive Audit

## Why this exists

C3 canary findings established that **memfs-enabled agents are pure-memfs**: no external PATCH writes work, no pre-existing/post-tag-attached blocks survive sync. To know which agents are migration-eligible (and at what cost), we need the full inventory of every block-touching operation across the ecosystem.

This document is the **input** for the design brainstorm: how do we persist the activities currently shared via memory blocks within a memfs paradigm? Migration target is to move the entire ecosystem off memory blocks before they're deprecated upstream.

## Headline numbers

- **44 active agents** in production
- **500 blocks** in the system, of which **326 attached** to ≥1 agent and **174 orphaned** (historical churn)
- **~12 of those 326 blocks are SHARED across 3+ agents** (sharing is widespread, not edge-case)
- **6 hardcoded block IDs** in service code (the original "Class B" set was incomplete; the actual hardcoded set is slightly different)
- **~10 distinct services** touch blocks, plus pa-web-ui, plus several agent-side custom tools

## Axis 1 — Agent inventory

44 agents broken down by category:

| Category | Count | Examples |
|---|---|---|
| Production primary agents | ~9 | `main-assistant-agent-kinara` (MC), `tasks-agent`, `calendar-agent_copy`, `email-agent`, `pulse-monitor-agent`, `docs-and-transcripts-agent`, `sports_and_media_maven`, `auto_madden_agent`, `daily-schedule-agent` |
| Sleeptime variants | ~7 | `tasks-agent-sleeptime`, `calendar-agent_copy` (sleeptime is the active calendar agent), `email-agent-sleeptime`, `pulse-monitor-agent-sleeptime`, `companion-sleeptime_copy`, `auto_madden_sleeptime`, `sports_and_media_maven_sleeptime` |
| Letta Code throwaways | ~10 | `Letta Code` (multiple — auto-named CLI sessions) |
| MC-rogue forks | 3 | `MC-rogue-44eda`, `MC-rogue-a5f37`, `MC-rogue-e119f` |
| Archived/deprecated | several | `XXX-ARCHIVE-*`, `Rover` (deprecating per user) |
| Specialized | ~5 | `work-packet-assembler`, `scheduler-agent` variants |

Full per-agent dump at `docs/research/memfs-audit-2026-04-25/agents-summary.txt`.

## Axis 2 — Block inventory + sharing topology

### Most-shared blocks (potential migration blockers)

| Block | Label | # agents attached | Externally written? |
|---|---|---|---|
| `block-7bff4e45-...` | extracted_tasks | **15** | No (agent-tool only) |
| `block-02add39d-...` | important_people | 12 | No |
| `block-e8bf985e-...` | task_extraction_tool_use_guidelines | 12 | No |
| `block-90300b77-...` | extracted_tasks | **8** | YES — agent-tool + pa-web-ui |
| `block-e5a68c10-...` | human | 6 | No |
| `block-c4d76867-...` | coordination_task_smoke-v2-test3 | 6 | No (test artifact) |
| `block-4a532465-...` | three_month_priorities | 4 | No |
| `block-61809ff0-...` | agent_info | 4 | No |
| `block-ec381d6a-...` | important_people (different ID) | 3 | No |
| `block-3d75c464-...` | coordination_task_default | 3 | YES — pa-routing-handler |
| `block-26e3b427-...` | coordination_gathered_default | 3 | YES — pa-routing-handler |

**Two distinct `extracted_tasks` blocks** with different IDs: one shared across 15 agents (the older one, label-only) and one shared across 8 agents (the active one, hardcoded as `EXTRACTED_TASKS_BLOCK_ID` in pa-web-ui). This is itself a migration concern — duplication / staleness.

### Orphan blocks

174 blocks have **zero attachment** to any agent. Most are presumably historical: created during agent-shape changes, never cleaned up. They represent zero migration cost (just delete) but signal the system has been accumulating cruft.

## Axis 3 — Block writers

### External services that write to blocks

Direct hits on `PATCH /v1/blocks/<id>` (block content mutation, not attach/detach):

| Service | Path | Target block | Pattern |
|---|---|---|---|
| **gmail-watch-service** | `gmail-watch-service/src/gmail_watch/services/task_queue_writer.py:148, 272` | env-var `BLOCK_ID` (queued_tasks_from_email + SPARK queue) | Async PATCH appending to `value` |
| **slackbot** | `slackbot/listeners/shortcuts/send_to_tasks.py:276` | env-var `SPARK_QUEUE_BLOCK_ID` | Sync PATCH appending to `value` |
| **pa-web-ui** | `pa-web-ui/app.py:3706, 3815, 4260` | `EXTRACTED_TASKS_BLOCK_ID` (block-90300b77-...) | PATCH on task lifecycle ops (delete-line, transition, merge) |

### Block ATTACH/DETACH (per-agent block routing — a different surface, less destructive)

| Service | Path | Operation |
|---|---|---|
| pa-routing-handler | `pa-routing-handler/src/pa_routing/services/coordination_handler.py:245, 275` | attach/detach coordination blocks during /mprep flow |
| slackbot | `slackbot/ai/conversation_helper.py:322` | attach memory blocks for new agent provisioning |
| Setup scripts (one-shot) | `letta/implement_shared_memory_blocks.py`, `letta/setup_*.py`, `letta/attach_*.py` | system bootstrap — ran during initial setup, not during normal operation |
| `scripts/letta-duplicate-block.sh` | this audit's helper | canary work only |
| `scripts/bootstrap_letta_memory.sh` | initial setup | not during normal ops |

### Agent-side custom tools that mutate blocks

These are tools attached to agents and invoked BY THE AGENT during reasoning. They mutate blocks via the same `PATCH /v1/blocks/<id>` surface. **Important**: under memfs, these tools' write semantics break the same way external writers do. Need redirection to file-based equivalents.

| Tool | File | What it does |
|---|---|---|
| `update_tasks_section` | `letta/update_tasks_section_tool.py` | Patches a per-agent tasks-section block |
| `add_extracted_tasks` | `letta/extracted_tasks_tool.py` | Appends to the SHARED `extracted_tasks` block from any agent that has it attached |
| `process_spark_queue` | `letta/process_spark_queue_tool.py` | Reads/clears spark queue block; calls add_extracted_tasks |
| `create_user_memory_block` | `letta/conversation_tools/create_user_memory_block.py` | Creates per-user memory blocks (MC pattern) |

### pa-web-ui's full task-lifecycle block surface

pa-web-ui acts on `EXTRACTED_TASKS_BLOCK_ID` (the shared block-90300b77-...) via:
- `GET /api/tasks` (line 3713) — reads the block
- `GET /api/tasks/<ref_id>` (3731) — reads
- `PATCH /api/tasks/<ref_id>` (3745) — internally PATCHes the block
- `POST /api/tasks/<ref_id>/transition` (3825) — mutates lifecycle state in the block
- `POST /api/tasks/<ref_id>/reassemble-work-packet` (4086) — rewrites work packet within the block
- `POST /api/tasks/merge` (4154) — merges multiple tasks within the block
- `POST /api/tasks/omnifocus-create` (4315) — read-then-PATCH
- `POST /api/tasks/widget-queue` (4352) — write to a widget queue block

This is **a complete CRUD surface on the shared `extracted_tasks` block** that the sidebar UI depends on, polling every 30s. Migrating this to memfs requires: either redirecting all pa-web-ui CRUD to git pushes against a memfs file (substantial refactor), or moving `extracted_tasks` to a non-memfs persistence shape (e.g., a Postgres table direct), or accepting that the agent owning `extracted_tasks` stays on Postgres blocks indefinitely.

## Axis 4 — Block readers

### Direct readers (`GET /v1/blocks/<id>`)

| Reader | Surface | Frequency |
|---|---|---|
| pa-web-ui sidebar | reads `EXTRACTED_TASKS_BLOCK_ID` via `/api/tasks` polling | every 30s while sidebar is open |
| Setup/bootstrap scripts | one-shot |
| Backup pipeline (`deployment/scripts/backup.sh`) | `GET /v1/blocks?limit=1000` for full enumeration | nightly |

### Per-agent readers (`GET /v1/agents/<id>/core-memory/blocks`)

- `pa-routing-handler/coordination_handler.py:61` — reads agent's blocks during coordination routing
- `scripts/create_awareness_blocks.py` — bootstrap
- `scripts/letta-duplicate-block.sh` — this audit's helper
- (~12 scratch files in `letta/tmp*.py` — these are old SDK-extraction temp files, can be cleaned up)

### Indirect readers — agents themselves

Every agent reads ALL its attached blocks every turn (Letta core memory injection). With 326 attachments across 44 agents, the average agent reads ~7 blocks per turn. The shared blocks (`extracted_tasks`, `important_people`, `task_extraction_tool_use_guidelines`) get read by 8-15 agents on every turn each.

## Activity-pattern inventory (the WHAT, not just the WHERE)

Critical — the design brainstorm needs to know what work these blocks DO, not just where they live. Synthesizing from labels + values:

### Pattern 1: Cross-agent shared knowledge
**Blocks**: `important_people`, `human`, `task_extraction_tool_use_guidelines`, `agent_info`, `three_month_priorities`
**What it does**: Stable reference data that ~all production agents need (who the user is, who key people are, what the user's priorities are, how to use shared tools, what other agents exist).
**Mutation cadence**: Rarely — these are bootstrap-time content that gets occasional manual updates.
**Migration shape under memfs**: Cleanest pattern — these become a **shared Gitea repo** (e.g., `agents/shared.git`) cloned into every agent's memfs as `system/shared/<file>.md` or attached via `block_ids` referencing a primary "shared" repo. **OR** (if cross-agent shared blocks remain a viable Letta pattern) keep these as Postgres blocks for these specific items, just as a stable reference layer.

### Pattern 2: Cross-agent IPC queues
**Blocks**: `queued_tasks_from_email` (block-e64dcb37), `queued_tasks_from_slack` (block-033a720d), `queued_tasks_from_meetings` (block-809efd9b), `queued_tasks_from_drive` (block-cfbba10b), SPARK queue (block-534bb56d), `extracted_tasks` (block-90300b77)
**What it does**: External writers append entries; the consuming agent (Tasks/Pulse/etc) processes them then clears.
**Mutation cadence**: High — gmail-watch-service hits this multiple times/day, slackbot on every shortcut invocation, pa-web-ui on every task-lifecycle action.
**Migration shape under memfs**: Most challenging. Three viable patterns:
  - **(2a) Move to Postgres direct (non-memory-block)**: a `pa_web.task_queue` table with same semantics. External writers `INSERT`, agent consumer `SELECT/DELETE`. Removes Letta from the IPC path entirely. Most decoupled.
  - **(2b) Each writer pushes a commit to the consuming agent's memfs**: gmail-watch service grows a git push capability targeting `agents/<tasks-agent>.git`, writing to `system/queue/email-N.md`. Each entry is a separate file. Atomic commit per entry. Consumer reads the directory.
  - **(2c) Keep as Postgres blocks, agent stays unmigrated**: the simplest answer for the consuming agent — Tasks agent stays on Postgres blocks specifically, while other agents migrate to memfs. Not all agents have to migrate at the same time.

### Pattern 3: Per-agent self-mutating memory
**Blocks**: persona, human (per-agent variant), agent-specific awareness blocks, role playbooks, scratch state
**What it does**: The agent itself updates these via `core_memory_replace` or custom tools.
**Mutation cadence**: Per-turn potentially.
**Migration shape under memfs**: Cleanest fit — these are EXACTLY what memfs is designed for. Becomes `system/persona.md`, `system/human.md`, etc., agent uses bash/Edit tool calls. **THIS IS THE NATURAL MEMFS MIGRATION TARGET.**

### Pattern 4: Coordination state (pa-routing-handler)
**Blocks**: `coordination_task_default`, `coordination_gathered_default`, dynamically-created coordination_task_<task_id> blocks
**What it does**: pa-routing-handler attaches to relevant agents for a meeting-prep / multi-agent coordination flow, agents write outputs, handler aggregates, then detaches.
**Mutation cadence**: Per-coordination-task — minutes to hours per task.
**Migration shape under memfs**: Most complex pattern because it depends on `attach`/`detach` of shared blocks across agents. Memfs has no equivalent of "attach this same block to multiple agents." Three viable patterns:
  - **(4a) pa-routing-handler creates per-task Gitea repos**, each agent's memfs gets a temporary `coordination/<task-id>/` directory pointing at the shared repo via git submodule (clunky, may not work cleanly with letta-code's flow)
  - **(4b) pa-routing-handler aggregates via direct REST**, calling each agent's `core_memory_replace` to inject coordination context, then reading agent responses, all without touching shared blocks. Memfs-compatible because it goes through agent message paths, not block paths.
  - **(4c) Keep coordination on Postgres blocks**: the routing-handler's agents stay on Postgres, only "primary" agents migrate to memfs.

### Pattern 5: Lifecycle data (extracted_tasks specifically)
This is its own pattern because pa-web-ui + Letta tools BOTH mutate it AND it's shared across 8 agents.
**What it does**: Tasks extraction tool appends entries (from various sources); pa-web-ui CRUDs entries (transition, merge, delete); 8 agents read it for "what tasks does the user have."
**Mutation cadence**: Multiple times daily.
**Migration shape under memfs**: This is the most painful migration target because:
- 8 readers means it's broadly shared
- pa-web-ui's CRUD surface is rich (transition, merge, delete, reassemble)
- Multiple agents write via `add_extracted_tasks` tool

  Cleanest path: **migrate `extracted_tasks` out of Letta entirely** — into Postgres directly as a `pa_web.tasks` table. Both the Letta `add_extracted_tasks` tool and pa-web-ui write via SQL/REST. Decouples the agent ecosystem from the task data store. This is the cleanest architectural answer regardless of memfs.

## Per-agent migration disposition (preliminary)

Based on writer/reader analysis of attached blocks per agent:

| Agent | Attached blocks (significant) | Has external writers? | Migration disposition |
|---|---|---|---|
| **MC** (`agent-90b2e860-...`) | assistant_role_playbook, important_people, rover_status_log_202603a, shared_context, laptop_execution_preference | Need to verify per-block | likely eligible after writer audit; awaiting audit |
| **tasks-agent** | `extracted_tasks`, `agent_info`, `human`, queue blocks | YES (gmail-watch, slackbot, pa-web-ui all write attached blocks) | NOT eligible without major writer redirect |
| **calendar-agent_copy** (active) | various — needs lookup | Need to verify | likely eligible |
| **email-agent** | extracted_tasks, queue blocks | YES | NOT eligible without redirect |
| **pulse-monitor-agent** | extracted_tasks, three_month_priorities | YES (extracted_tasks read+write) | NOT eligible without redirect |
| **docs-and-transcripts-agent** | extracted_tasks (read), important_people | Read-only on shared blocks; depends on whether IT writes | likely eligible |
| **sports_and_media_maven** | extracted_tasks (read), media-specific | Need lookup | likely eligible |
| **auto_madden_agent** | extracted_tasks (read), domain-specific | Need lookup | likely eligible |
| **daily-schedule-agent-sleeptime** | three_month_priorities, agent_info, current_daily_schedule | YES (`current_daily_schedule_and_available_time` appears to be externally written) | depends on writer-redirect |
| **work-packet-assembler** | unknown; needs lookup | likely no | likely eligible |
| **MC-rogue-** forks | persona, human only | No | trivially eligible |
| **Letta Code** auto-agents | persona, human only | No | trivially eligible (or just delete) |
| **Archived agents** | various | No | not migration targets — delete or leave |

## Cleanup-as-prerequisite

Before any migration design is locked, several cleanup operations should happen:

1. **Decide and execute `extracted_tasks` consolidation**: there are TWO blocks with this label. Either deduplicate them OR explicitly differentiate (e.g., one as `extracted_tasks_archived` and one as `extracted_tasks_active`). The current state confuses anyone reading the audit.
2. **Delete the 174 orphan blocks**: zero migration value, only audit noise.
3. **Delete the `tmp*.py` files** in `/letta/`: these are old SDK extraction scratchpads, all touching the same `core-memory/blocks` URL but representing zero current functionality.
4. **Decide on archived agents**: do `XXX-ARCHIVE-*` agents get hard-deleted or stay? They show up in every block-attachment query.
5. **Test agent cleanup**: scratch agents from this session and earlier sessions still around. The canary-management script we built can be repurposed to track + sweep these.

## Open design questions for the brainstorm

These are the things the brainstorm session needs to resolve:

### Q1: Cross-agent shared knowledge (Pattern 1)
Do we keep `important_people` / `human` / `task_extraction_tool_use_guidelines` as cross-agent shared Postgres blocks, or migrate them to a shared Gitea repo cloned into every agent's memfs?

### Q2: Task data store (Pattern 5 — `extracted_tasks`)
Do we move `extracted_tasks` out of Letta entirely (to Postgres `pa_web.tasks`)? If so, what's the agent-side API to it?

### Q3: External writer redirect feasibility (Pattern 2 — queues)
For each external writer (gmail-watch, slackbot, pa-routing-handler, etc.), is it feasible to switch from `PATCH /v1/blocks/<id>` to `git push` against the consuming agent's Gitea repo? What's the cost per writer?

### Q4: Coordination flow (Pattern 4 — pa-routing-handler)
Can pa-routing-handler's `attach`/`detach` flow be replaced with direct-REST message-injection that avoids block sharing entirely? If yes, is the agent UX equivalent?

### Q5: Migration sequencing
Do we migrate "leaf" agents first (no shared blocks, no external writers — likely Calendar, Docs, sports_and_media_maven) and progressively pull in more central ones? Or do we redesign the shared-block patterns first, then migrate everything together?

### Q6: Hybrid coexistence
Is it acceptable to have SOME agents on memfs and SOME on Postgres-blocks indefinitely? What's the operational cost of running both modes long-term?

### Q7: MC's specific path
MC is the user's primary daily interface. It has 5 attached blocks: `assistant_role_playbook`, `important_people`, `rover_status_log_202603a`, `shared_context`, `laptop_execution_preference`. Need to verify which are exclusive to MC vs shared, and which have external writers. Likely it's the cleanest production migration target.

### Q8: Letta team consultation
Several patterns may have Letta-blessed answers we don't know. Worth raising with the support agent:
  - Cross-agent shared knowledge: best practices for memfs era?
  - External-writer-mutated blocks: official guidance?
  - Coordination/attach-detach pattern: what replaces it?

## Files in this audit

- `agents-raw.json` — full `/v1/agents/?limit=200` dump
- `agents-summary.txt` — human-readable per-agent inventory
- `blocks-raw.json` — full `/v1/blocks/?limit=500` dump
- `blocks-inventory.txt` — blocks ranked by attachment count, with attached-agents
- `code-writers-patch.txt` — every PATCH /v1/blocks invocation in code
- `code-writers-content.txt`, `code-writers-sdk.txt`, `code-writers-broad.txt` — narrowing searches
- `code-referenced-block-ids.txt` — every hardcoded block ID in code
- `code-referenced-block-resolution.txt` — those IDs resolved to label + attached agents

## Recommended next step

This audit is **input**, not a decision. The next step is the design brainstorm — work through Q1-Q8 above (and likely more that emerge), with Letta agent input where useful, and produce a coherent migration architecture. The brainstorm should NOT prescribe the answer here; it should run as `ce:brainstorm` with explicit alternatives weighed.
