---
date: 2026-04-26
status: deferred
trigger: post-cycle-1 (after MC migration + Tier-2 migrations stabilize)
related-plan: docs/plans/2026-04-26-001-feat-pa-organizational-memory-cycle1-plan.md
---

# Post-Cycle-1 Follow-up: Comprehensive Task Record

User requested mid-cycle-1 (2026-04-26) that the archived task row in
`pa_web.tasks` become a **comprehensive record** of the task and its
associated materials/resources — capturing the full lifecycle from initial
agent suggestion through user confirmation, refinement, work, and
completion. This document captures the schema additions already applied
and the process-side changes that remain deferred to post-cycle-1.

## Schema additions applied 2026-04-26 (cycle 1)

These are columns; no process changes needed to land them. Already in
both `pa_web.tasks` (live) and `pa-web-ui/app.py` `ensure_pa_web_schema()`
(fresh deploys):

| Column | Type | Purpose |
|---|---|---|
| `suggested_title` | TEXT | Agent's original proposed task title at extraction time |
| `confirmed_title` | TEXT | User-finalized title (from sidebar confirm flow) |
| `original_est_minutes` | INTEGER | Agent's first-pass time estimate (renamed from `est_minutes`) |
| `revised_est_minutes` | INTEGER | Updated estimate after user/agent refinement |
| `actual_minutes` | INTEGER | Measured actual time required |
| `started_at` | TIMESTAMPTZ | When work began (alongside existing `closed_at`) |

These columns will be NULL until process changes (below) populate them.

## Process changes deferred to post-cycle-1

Each item below requires modifying an existing flow or adding a new
touchpoint. Bundling them avoids cycle-1 scope creep + lets us design
against real reflection-inbox content from MC's soak.

### 1. Title lifecycle (suggested → confirmed)

**Current state:** `raw_description` is set once by the extracting agent;
no separate title field; sidebar UI shows `raw_description` directly.
There is no captured distinction between agent's initial suggestion and
user's confirmed final title.

**Process change needed:**
- Tasks-agent / extraction agents write `suggested_title` (concise, 6-10
  words) at task creation alongside `raw_description` (full sentence).
- pa-web-ui sidebar's confirm flow (`api_update_task` /
  `api_transition_task` when transitioning from triage to active) writes
  `confirmed_title` — defaulting to `suggested_title` if user doesn't
  edit, capturing the user's edit if they do.
- `extracted_tasks` block-line format gains a title slot (currently the
  block line carries description as freeform text).
- pa-web-ui sidebar UI shows confirmed_title when present, falls back to
  raw_description.

**Touch points:** tasks-agent persona/skill, `add_extracted_tasks_postgres`
tool (Unit 3), pa-web-ui `_extracted_tasks_block_render()` and CRUD
routes, sidebar.js display logic.

### 2. Time-estimate lifecycle (original / revised / actual)

**Current state:** Single `est_minutes` (renamed `original_est_minutes`)
captures whatever the agent guessed at extraction. No revision capture,
no actual-time tracking.

**Process change needed:**
- Sidebar UI: when user adjusts time estimate during triage or work,
  write `revised_est_minutes`.
- OmniFocus integration: capture actual elapsed time on completion.
  Options: (a) OmniFocus's own time-tracking if user enables it; (b)
  task-start/task-complete events recorded via the OmniFocus bridge
  (`omnifocus-mcp-letta` or `omnifocus-timer` plugin) which writes to
  `started_at` and computes `actual_minutes = closed_at - started_at`;
  (c) manual entry on completion ("how long did this take?").
- Recommend (b) — the existing `omnifocus-timer` plugin (per project
  memory `project_omnifocus_timer.md`) already tracks per-task timers
  with Caps Lock toggle. Wire it to write back to `pa_web.tasks` on
  start/stop.

**Touch points:** omnifocus-timer plugin, sidebar UI, possibly a new
`api_record_time` route.

### 3. Started_at capture

**Current state:** Task lifecycle has `created_at` (row insertion),
`updated_at` (last mutation), `omnifocus_pending_at`,
`omnifocus_created_at`, `closed_at` (completion). No "user started
working on this" timestamp.

**Process change needed:**
- Define what "started" means: first OF check-out / timer start / first
  user edit after confirm? Recommend: timer start (most consistent
  signal); fall back to `omnifocus_created_at` if no timer used.
- omnifocus-timer plugin writes `started_at` on first timer start
  (idempotent — only first start populates; subsequent starts don't
  overwrite).
- Sidebar UI displays "started Xh ago" alongside "due in Yd".

**Touch points:** omnifocus-timer plugin (start hook), sidebar.js display.

### 4. Comprehensive work-packet capture in archived task

**Current state:** Work packet flow at extraction time produces rich-text
OmniFocus note from `parse_archival_passage`'s `packet_info` dict
(context_brief, resources, related_tasks, knowns, unknowns, agent_notes,
mismatch_warning, source_text). MC enrichment runs via
`_dispatch_mc_work_packet` which calls tools like `backtrace_task`,
`stage_resource`, `write_packet_info` — this UPDATES the archival
passage's PACKET INFO section, then re-renders the OF note.

**However:**
- During work, user adds notes/links/attachments directly to the OF item.
  These do NOT round-trip back to the archive.
- Outcome notes ("turned out the budget delta was actually $52k after
  finance review") live only in OF.
- Resources discovered/used mid-task aren't appended to the archival
  passage automatically.
- Sub-tasks created in OF during work are not reflected in the archived
  record.

**Process change needed (closing the loop):**
- **At task completion** (transition to `done`/`archived`), pa-web-ui
  triggers a "completion sweep":
  - Pull final OF item state via the OmniFocus bridge: notes (full final
    text), attached files/URLs, sub-task list with completion status,
    actual time if tracked, completion comment.
  - Append/merge into `pa_web.tasks` columns:
    - `enrichment.packet_info_final` ← final PACKET INFO state
    - `enrichment.of_completion` ← `{notes, attachments, subtasks,
      completion_comment}`
    - `actual_minutes` ← measured elapsed
    - `closed_at` ← OF completion timestamp
  - Optionally trigger MC to write a brief "outcome summary" sentence
    into `enrichment.outcome_summary`.
- **Promote `packet_info` to a first-class JSONB column** (currently
  nested inside `enrichment`) so completed-task queries can filter on
  resources, sub-tasks, etc. without JSON path expressions.

**Touch points:**
- `omnifocus-mcp-letta`: ensure tools to fetch full item state including
  attachments and sub-tasks exist.
- pa-web-ui: new "completion sweep" route + UI button (or auto-fire on
  status transition to `done`).
- Possibly a new `extract_completion_summary` Letta tool MC invokes at
  completion.
- Schema: new column `packet_info JSONB NULL` (or keep nested in
  enrichment).

### 5. Unit 12 archival-lift implications

The Unit 12 archival-passage migration (per the cycle-1 plan) currently
maps:
- archival passage → `pa_web.tasks` row with `task_body`, `source_metadata`,
  `related_urls`, `agent_notes`, `enrichment`, etc.

**Verify post-migration that Unit 12 captures all `packet_info` subfields
into `enrichment` (or a new dedicated column).** The parser produces a
nested dict with context_brief / resources / related_tasks / knowns /
unknowns / mismatch_warning / source_text — these need to round-trip
into the new row faithfully.

If we add a dedicated `packet_info JSONB` column (item 4), Unit 12 must
populate it. Easier to add the column post-cycle-1 only if Unit 12 and
mirror writer's render logic both get updated.

## Sequencing recommendation

1. **Cycle 1 ships as planned** — Unit 12 stores `packet_info` inside
   `enrichment` JSONB; the new title/estimate/started_at columns stay
   NULL.
2. **After MC soak** (post Unit 16 + Unit 17), spec a small follow-up
   sub-cycle "Task Record v2" covering items 1–4 above. Likely 3–5
   implementation units; mostly UI + bridge plumbing, no architectural
   changes.
3. **omnifocus-timer integration** for `started_at` + `actual_minutes`
   is the cheapest item to land first in the sub-cycle (existing plugin,
   2 hooks).
4. **Title lifecycle** is mostly UI + persona-prompt work; second.
5. **Completion sweep** (item 4) is the largest; design last when MC's
   migrated state stabilizes the question of which agent owns the sweep.

## Notes / open questions for the sub-cycle

- Does the user want a manual "completion notes" prompt at archive time,
  or fully automated MC-summary?
- Should `actual_minutes` be backfillable from past OmniFocus history if
  OF retains creation/completion timestamps?
- For tasks completed BEFORE timer start (legacy / pre-instrumented),
  `actual_minutes` stays NULL — acceptable, document as such.
- `confirmed_title` defaulting to `suggested_title` on first confirm is
  the simplest path. Alternative: require explicit user edit (forces
  thoughtfulness; adds friction).
