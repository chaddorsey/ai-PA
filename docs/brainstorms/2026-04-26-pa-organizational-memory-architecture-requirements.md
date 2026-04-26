---
date: 2026-04-26
topic: pa-organizational-memory-architecture
sibling: docs/brainstorms/2026-04-24-memory-consolidation-patterns-requirements.md
related-research:
  - docs/research/memfs-audit-2026-04-25/AUDIT.md
  - docs/research/memfs-audit-2026-04-25/letta-followup-brief.md
  - docs/research/memfs-audit-2026-04-25/rehearsal-results.md
  - docs/research/memfs-audit-2026-04-25/issue-4-root-cause-and-workaround.md
  - "Ezrs-system-design-thread-2026-4-25.pdf (in letta-shared-files)"
implementing-plan: TBD (created after this brainstorm converges)
---

# Organizational Memory Architecture for the ai-PA ecosystem

## Problem Frame

The ai-PA ecosystem is migrating its working agents from Letta v1
attached-blocks to memfs. Today most cross-agent state lives in shared
memory blocks attached to multiple agents (`important_people` on 12,
`extracted_tasks` on 8+, `task_extraction_tool_use_guidelines` on 12,
queue blocks like `queued_tasks_from_email` written by external services
via PATCH). External services (gmail-watch, slackbot, drive-rag,
granola-ingest, task-completion-service, omnifocus-sync, pa-web-ui task
sidebar) depend on this block layer for queues, signals, and operational
state. Several agents also use Letta archival memory (per-agent vector
store) for task records, meeting summaries, and analytics history.

The migration to memfs introduces both a substrate change and an
architectural opportunity. Per Ezra's guidance (substrate decomposition
in `letta-followup-brief.md`, refined in the long architecture thread
2026-04-25), memory blocks were doing several distinct jobs because
they were the only Letta-native cross-agent surface. The new paradigm
cleanly separates them across distinct substrates per layer.

Doing the migration well requires deciding **where each existing
pattern lives in the new architecture**, **in what order to evolve the
patterns**, and **what minimum substrate must exist before the first
production agent (MC) migrates**. Moving piecemeal without that frame
risks either (a) migrating MC into a substrate that lacks the
operational layer it needs, or (b) building speculative architecture
that doesn't match how the system actually wants to behave.

This brainstorm captures the architectural decisions; planning
(`/ce:plan`) sequences and details the build.

## Requirements

### Substrate decomposition (the five-layer model)

- **R1.** Memory state is decomposed into five layers, each on a
  specific substrate:
  1. **Canonical external facts** → shared Gitea repo (slow-changing,
     human/agent-edited reflectively) OR Postgres (relational/queryable
     when needed)
  2. **Transactional/operational state** → Postgres (queues, tasks,
     meetings, proposals)
  3. **Per-agent projections of canonical data** → that agent's memfs
     `reference/` (progressive, on-demand)
  4. **Per-agent identity/behavior** → that agent's memfs `system/`
     (durable, pinned) + skills
  5. **Cross-agent signals/digests** → shared Gitea repo `signals/`
     subtree (agent-produced, commonly-readable, agent-tagged)
- **R2.** Where each existing pattern goes is locked per the mapping in
  Key Decisions.

### Pattern 2 — external-writer queues

- **R3.** External services (gmail-watch, slackbot, drive-rag,
  granola-ingest) stop PATCHing `queued_tasks_from_*` memory blocks and
  write to per-source Postgres tables (`pa_web.task_queue_email`,
  `pa_web.task_queue_slack`, `pa_web.task_queue_drive`,
  `pa_web.task_queue_meetings`).
- **R4.** Consuming agents use a shared agent-side custom tool
  `consume_queue(source, limit)` that SELECTs available rows and marks
  them claimed/processed.
- **R5.** External services no longer require Letta API tokens; they
  become simple SQL writers.
- **R6.** Per-source schemas may differ, capturing each source's native
  fields. A future consolidation to a single `pa_web.task_queue` table
  is allowed but not required.

### Pattern 5 — extracted_tasks

- **R7.** The `extracted_tasks` shared memory block is replaced by a
  `pa_web.tasks` Postgres table (minimal-translation schema preserving
  the existing pa-web-ui workflow states: source, source_ref, raw_text,
  extracted_by, status, merged_into, omnifocus_id, due/priority/owner
  metadata).
- **R8.** Agent-side `add_extracted_tasks` tool writes to Postgres
  instead of the block.
- **R9.** pa-web-ui task review sidebar reads/writes from Postgres
  directly instead of polling the block.
- **R10.** Cutover uses the **read-shadow pattern**: Postgres becomes
  canonical for writes immediately; a small process keeps the
  `extracted_tasks` block in sync (writes-from-Postgres) so that
  not-yet-migrated agents continue to read valid block content. Each
  agent's persona/tools migration to the SQL-backed `fetch_tasks` tool
  happens per agent.
- **R11.** Block stays alive throughout the read-shadow window;
  retirement is a per-agent decision after that agent is migrated.

### Archival use cases

- **R12.** Archival use cases that are subsumed by Pattern 5 (task-
  completion records, prepare_follow_up lookups, omnifocus-sync writes)
  migrate to direct `pa_web.tasks` SELECT/UPDATE; the consuming
  services stop writing archival entries.
- **R13.** Granola meeting content uses a two-tier storage:
  (a) `pa_web.meetings` table for metadata (id, date, title, attendees,
  source, source_ref, transcript_path, summary_short) — supports
  relational queries like "all meetings with Danielle in last 30 days,"
  "meetings tied to task X."
  (b) Granola MCP serves the semantic-search-over-transcripts use case
  in the near term. A local vector index (qmd or own choice) is the
  fallback path if Granola MCP becomes a constraint or non-Granola
  sources need indexed.
- **R14.** `canonical/people/<name>.md` and similar shared canonical
  entries may include reference pointers to recent meetings (e.g., "see
  meetings: search Granola for attendee=<name>") for key recurring
  entities. Not every meeting reference belongs in canonical; only those
  that constitute recurring identity context.
- **R15.** Slackbot's current `_write_dm_to_archival` code path is
  deprecated and removed (slackbot does not currently answer DMs
  independently on the user's behalf; this signal-emission path is
  obsolete).
- **R16.** Pulse-monitor analytics briefings move from archival to the
  signal substrate (R17 below).

### Layer 5 — cross-agent signals/digests substrate

- **R17.** Cross-agent signals/digests live in the shared canonical
  Gitea repo at `signals/YYYY-MM-DD/<source>-<short-slug>.md`.
- **R18.** Each signal file uses YAML frontmatter with the
  platform-canonical `description` field (one-line digest, surfaces in
  consuming agent's prompt) plus custom fields for coordinator scan
  logic: `source`, `attention_level`
  (low/normal/high/urgent), `mentioned_entities`.
- **R19.** Producing agents write to `signals/` (e.g., pulse-monitor
  emits analytics briefings here; weekly digests go here; granola
  summaries may emit here if classified as cross-agent-relevant).
- **R20.** Consuming agents (notably MC's plate-digest) read from
  `signals/` via the same shared-repo skill that handles canonical
  pulls.
- **R21.** The substrate may be promoted to a Postgres `signals` table
  later if cadence and query-shape demand it; the frontmatter fields
  are chosen so promotion is mechanical (frontmatter keys become
  columns).

### Shared canonical store seed and operation

- **R22.** A separate Gitea repo (working name `agents-canonical.git`)
  serves as the cross-agent shared canonical store, accessed via a
  thin per-agent skill that wraps pull/edit/commit/push.
- **R23.** Day-1 seed contents are extracted from existing shared
  memory blocks:
  - `people/<name>.md` — split from existing `important_people`
    (12-agent shared block); one file per person
  - `priorities/<period>.md` — split from existing
    `three_month_priorities` (4-agent shared block)
  - `playbooks/task-extraction.md` — extracted from existing
    `task_extraction_tool_use_guidelines` (12-agent shared block)
- **R24.** The `projects/` directory is intentionally empty at seed
  time; populated by reflection→steward emergence as projects come up.
- **R25.** `agent_info`-style infrastructure config does NOT live in
  the canonical store (per Ezra: it's config not memory; keep in env
  vars or service repo).
- **R26.** Per-user `preferences_*` content stays in each consuming
  agent's memfs `reference/users/<id>.md` unless multi-agent
  consumption emerges; not promoted to canonical at seed time.
- **R27.** Branch discipline: single `main` branch, agents pull-rebase-
  push via the skill with bounded retry. Per-agent branches are not
  used initially; reserved as an escalation path if write contention
  surfaces.
- **R28.** Future evolution to canonical content is agent-suggested
  via the reflection→steward path (R32–R34).
- **R29.** The shared-repo workaround is documented as in service of
  LET-8217 (multi-agent shared memfs, not yet shipped); directory
  layout is chosen so transition to LET-8217 is mechanical (lowercase
  hyphenated names; do not use `system/` as a top-level shared-repo
  dir name; one file per logical unit; thin skill that's easy to
  delete the day Letta makes it native).

### Three-tier agency model

- **R30.** Every change in the system falls into one of three tiers:
  - **Free-evolution zone**: agent's own memfs (excluding identity
    files in `system/persona.md`, `system/role.md`, `system/policies/*`),
    agent's own progressive files (`reference/*`, `signals/*`),
    agent's own draft skills. Agent updates whenever it learns. No
    approval.
  - **Proposal zone**: shared canonical content, cross-agent skills,
    signal-schema changes. Agent proposes via reflection inbox; steward
    reviews; approved changes are applied.
  - **Hard zone**: agent identity (`system/persona.md`, role files),
    agent provisioning, Postgres schema changes, tool definitions,
    security-relevant config. User changes only; agents may propose
    but never apply.
- **R31.** The three-tier model is codified as a skill
  (`agency-rules.md`) loaded by every agent.

### Reflection inbox + steward

- **R32.** Each agent has `reflections/inbox.md` in its own memfs.
  Entries are appended as the agent works, tagged by scope:
  `[self]`, `[canonical]`, `[system]`.
- **R33.** Steward is a **dedicated agent** (not a scripted process)
  to leave room for reasoning about ambiguous proposals and aggregation
  patterns that evolve. The steward agent owns processing the proposal
  queue and producing the daily summary.
- **R34.** The proposal queue lives in the **shared canonical Gitea
  repo** at `proposals/<agent>/<timestamp>.md` (not Postgres), since
  proposals are general/free-form in nature and benefit from
  human-browsable history.
- **R35.** Worker agents process their own inboxes via reflection
  subagents (work-driven, parent-memory-aware) — apply `[self]` items
  to own memfs, push `[canonical]` and `[system]` items to the steward
  queue.
- **R36.** Steward runs daily via scheduler (e.g., 6am cron) — reads
  the proposal queue, auto-applies safe `[canonical]` updates that
  pass schema validation, queues conflicts and `[system]` proposals
  for user review.
- **R37.** User review surface is a **CLI** initially
  (`pa-proposals list`, `pa-proposals approve <id>`, etc.). Cadence
  and shape of proposals will inform whether to graduate to a
  pa-web-ui tab or Slack interface later.

### MC plate-digest (the unified-executive linchpin)

- **R38.** MC has a heartbeat-refreshed `reference/current-plate.md`
  file (NOT in `system/` — it's volatile and pinning would thrash KV
  cache). The file is ~200-300 tokens distilled from Postgres tasks +
  recent signals + canonical priorities.
- **R39.** Refresh is performed by an agent-side `refresh-plate` tool
  that queries Postgres, reads recent signals, reads top canonical
  priorities, and writes the digest. Tool is callable on demand and
  fired by MC's heartbeat.
- **R40.** MC's standing instructions in `system/` direct it to read
  `reference/current-plate.md` at turn start.
- **R41.** Detail beyond the digest is pulled on demand: when MC needs
  to drill down ("what's on Project X specifically?"), it calls the
  appropriate query tool against Postgres or canonical.

### Heartbeat / reflection / scheduler mechanism mapping

- **R42.** MC's plate-refresh heartbeat runs via the existing
  scheduler service (port 8087) on a cadence of 15-30 minutes during
  waking hours; can vary by time-of-day.
- **R43.** Worker agent housekeeping uses **reflection subagents**
  (work-driven, ephemeral, parent-memory-aware) — not scheduled
  heartbeats. Trigger is step-count based (e.g., every 20 turns of
  work), not wall-clock.
- **R44.** Steward daily aggregation runs via the scheduler service
  (cron expression).
- **R45.** Future-self prompts (agents scheduling themselves into the
  future) and any cross-agent scheduling flow exclusively through the
  scheduler service.
- **R46.** Heartbeat and reflection prompts are
  **stable, skill-invoking, file-driven** (cache-friendly): e.g.,
  `Run skill mc-heartbeat. Scope: full.` rather than dynamic-data-laden
  prose. Skills do the data loading internally.

### Migration pattern evolution sequence

- **R47.** Pattern evolution proceeds in the order
  **Pattern 2 → Pattern 5 → archival use-case-by-use-case**.
  This order minimizes blast radius per stage (decoupling first,
  central operational state second, per-agent archival last).
- **R48.** External services migrate first (Pattern 2) — they no
  longer write to memory blocks, become SQL writers. This shrinks
  the agent-side coupling to legacy patterns before any agent
  migrates.
- **R49.** Pattern 5 (extracted_tasks) lands as read-shadow before
  any agent-side `fetch_tasks` migration; Postgres is canonical day 1.
- **R50.** Archival use-cases migrate per-case as each consuming
  agent migrates to memfs. Subsumed cases (R12) move to Postgres
  alongside the agent. Meeting + signal cases land per R13/R17.

### Agent migration scope

- **R51.** In-scope agents for this migration cycle are the MC-related
  working set:
  - MC (Mission Control)
  - tasks-agent
  - email-agent
  - pulse-monitor-agent (live instance to be disambiguated from the 4
    existing copies pre-migration)
  - docs-and-transcripts-agent
  - calendar-agent_copy (the active one)
- **R52.** Daily-schedule-agent's briefing function is reframed as a
  scheduled skill — its existing 11 cron jobs continue to fire via the
  scheduler against a simpler agent (or a stateless tool invocation),
  rather than relying on a sleeptime variant.
- **R53.** Out-of-scope for this cycle: companion, auto_madden,
  sports_and_media_maven, work-packet-assembler,
  main-assistant-agent-kinara (overlap with MC to be disambiguated),
  and pa-routing-handler coordination patterns (deprecated and unused).
- **R54.** Sleeptime variants (sleeptime_agent type) are not migrated
  individually; they collapse into the reflection subagent pattern as
  part of each agent's migration.

### Migration sequencing relative to substrate buildout

- **R55.** Substrate buildout proceeds **before** any in-scope agent
  migrates (path 2 / pattern-evolve-first). Specifically: Pattern 2 +
  Pattern 5 read-shadow + shared canonical store seed + signal
  substrate + steward + agency-rules skill + MC plate-digest tool exist
  before MC migration begins.
- **R56.** MC migrates first among the working agents, exercising the
  full substrate. After MC soaks satisfactorily, Tier 2 agents migrate
  one at a time.
- **R57.** Each agent's migration follows the per-agent runbook
  (`docs/runbooks/memfs-migration-per-agent.md`), augmented with
  agent-specific block detach/preserve plan based on its current
  memory block usage.

## Success Criteria

- The full in-scope working set (R51) is migrated to memfs without
  loss of operational continuity for any external service or
  user-facing surface (Telegram via MC, pa-web-ui task sidebar,
  scheduler-driven analytics pipeline).
- MC operates with the unified-executive feel — its plate-digest
  refreshes at heartbeat, agents emit signals it consumes, canonical
  facts are shared cleanly across the working set.
- The system grows planned-yet-emergent: agents propose canonical
  changes via reflection; the steward auto-applies safe ones and
  surfaces the rest for daily user review; the user's daily touchpoint
  is bounded (~5-10 minutes for steward summary).
- No loss of historically captured information: archival content that
  matters has been migrated to its appropriate substrate (Postgres,
  canonical, or signals) before the source archival store is
  decommissioned.
- Substrate decisions survive contact with reality for at least 4
  weeks after MC migration. Drift surfaces via reflections and the
  steward review loop, not via emergency redesign.

## Scope Boundaries

- Single-user system (Chad). Not designing for multi-tenant.
- Not designing the full final-state system; designing the substrate so
  it can evolve via the reflection→steward loop (planned-yet-emergent).
- Not migrating: companion, auto_madden, sports_and_media_maven,
  work-packet-assembler, main-assistant-agent-kinara,
  pa-routing-handler coordination patterns, sleeptime mechanics
  individually (R53, R54).
- Not building a local vector index over meeting transcripts in this
  cycle — Granola MCP serves that need (R13). Local index is a future
  fallback.
- Not building Slack/web review surface for steward initially — CLI
  first, graduate later if cadence justifies (R37).
- Not promoting signals to Postgres initially — files in shared repo,
  promote later if cadence/query-shape demands (R21).
- Not building a Letta-native shared-memfs feature (LET-8217 upstream
  responsibility); using shared-Gitea-repo workaround with directory
  layout chosen for mechanical transition when LET-8217 lands.

## Key Decisions

- **Five-layer substrate model** instead of original four-substrate
  decomposition. The added layer is "agent-produced signals/digests"
  as a distinct concern from canonical facts. Rationale: same shared
  store can hold both (different subtrees), but the lifecycle and
  ownership rules differ — facts are cross-agent canonical; signals
  are agent-produced and agent-tagged for cross-agent consumption.
- **Pattern evolution order: Pattern 2 → Pattern 5 → archival**
  (decoupling-first). Rationale: minimizes blast radius per stage;
  external services lose Letta coupling before agents migrate; central
  operational state lands while agents still read legacy block via
  read-shadow; per-agent archival migrates with each agent.
- **Read-shadow cutover for Pattern 5**. Rationale: Postgres is
  canonical day 1 (no dual-write drift); agent migrations happen one at
  a time without urgency; rollback is per-agent.
- **Per-source queue tables (option A) for Pattern 2**. Rationale:
  matches existing per-source mental model; clear ownership; safest
  horizontal migration. Consolidation to single `task_queue` table is
  a future optimization.
- **Minimal-translation `pa_web.tasks` schema (option A) for
  Pattern 5**. Rationale: preserves existing pa-web-ui workflow state
  without invention; minimum design risk; richer relational schema is
  a future evolution if relational queries justify the cost.
- **Granola MCP serves semantic search over meeting transcripts in
  the near term**. Rationale: working surface today; defers local
  index work; promotion path exists if MCP becomes a constraint.
- **Signals as markdown files in shared repo, NOT Postgres
  initially**. Rationale: cadence is moderate and signals are
  free-form; greppable + Gitea-browsable; promotion to Postgres is
  mechanical via frontmatter-as-columns when justified by data.
- **Steward as a dedicated agent (option A), not scripted process**.
  Rationale: leaves room for reasoning about ambiguous proposals and
  aggregation patterns that evolve.
- **Proposal queue in shared repo, not Postgres**. Rationale:
  proposals are general/free-form; benefit from human-browsable
  history; cadence likely low.
- **CLI for steward review surface initially**. Rationale: simplest
  to build; cadence not yet known; can graduate to pa-web-ui tab or
  Slack interface once shape is clear.
- **Substrate buildout precedes MC migration (path 2)**. Rationale:
  MC needs the operational layer (canonical store, signals, plate-
  digest) to function as the unified-executive hub; piecemeal
  migration would degrade MC during the transition.
- **MC migrates first among working agents**, then Tier 2 one at a
  time. Rationale: MC's pattern coupling is shallowest among Tier 2
  agents; its successful migration validates the full substrate before
  more complex migrations begin.
- **Daily-schedule-agent reframed as scheduled skill, not sleeptime
  agent**. Rationale: its work is genuinely scheduled (15-min cadence
  during workday) and produces deterministic output; an agent persona
  is overkill for what's effectively a templating function.

## Dependencies / Assumptions

- Letta server v3 patched image (Fimeg patches 1-3 + scoped delete +
  fetch-before-sync) is in place and validated.
- letta-code is patched (Path C handle resolution + memfs-git URL
  substitution) and patches survive auto-updates via `bin/letta-patched`
  wrapper + `DISABLE_AUTOUPDATER=1`.
- Gitea is deployed; `agents` org exists; per-agent repos exist for
  migrated agents; the new `agents-canonical.git` repo will be
  provisioned as part of substrate buildout.
- `memfs-sync-relay` is deployed; Gitea webhook fires it on push;
  patch 05's auto-fetch closes the loop bare-repo → Postgres.
- pa_web Postgres schema namespace is available (pa_web.tasks already
  planned per consolidation-patterns brainstorm).
- Existing scheduler service at port 8087 supports the cron + interval
  cadences described; agent-message and HTTP action types both work.

## Outstanding Questions

### Resolve Before Planning

(none — all blocking decisions resolved during brainstorm)

### Deferred to Planning

- **[Affects R25-R26][Technical]** Specific schema for canonical store
  frontmatter (`people`, `priorities`, `playbooks` files): list of
  required fields, optional fields, validation rules. Sized work for
  the planning phase to define concretely.
- **[Affects R3-R6][Technical]** Per-source queue table schemas:
  match each source's existing block content to a column set; design
  the `consume_queue(source)` tool's row-claim semantics
  (transactional isolation, idempotency on retry).
- **[Affects R7-R11][Technical]** `pa_web.tasks` exact column list +
  indexes to support pa-web-ui sidebar polling cadence + the
  read-shadow writer process design.
- **[Affects R13][Technical]** Local vector index choice if/when
  Granola MCP becomes a constraint (qmd vs. own Postgres pgvector vs.
  other) — defer until the constraint actually materializes.
- **[Affects R51][User decision]** Disambiguation of pulse-monitor's
  4 instances and main-assistant-agent-kinara vs MC overlap — needs a
  small audit pass against current usage before pulse-monitor and any
  Kinara-related migration. Could be done as part of pre-flight per
  agent.
- **[Affects R29][Needs research]** Whether LET-8217's exact landing
  shape allows mechanical transition from our shared-Gitea-repo
  pattern. Track via Letta forum; revisit substrate decisions if
  shape diverges from the three plausible designs Ezra outlined.
- **[Affects R31, R36][Technical]** `agency-rules.md` skill content
  + steward agent's persona/skill set. The exact reasoning the steward
  does and the validation it applies to `[canonical]` proposals.
  Sized work for planning + early operational tuning.
- **[Affects R45][Technical]** Cross-agent scheduling APIs: what
  exactly the `schedule-future-prompt` MCP tool exposes to agents
  (parameters, callback semantics, identity propagation).
- **[Affects R57][User decision]** Per-agent migration plans for each
  in-scope agent: which blocks detach pre-port, which migrate to which
  substrate, what skill content needs to live in their post-migration
  persona.

## Next Steps

→ `/ce:plan` for structured implementation planning. The plan should
sequence the substrate buildout (Pattern 2 + Pattern 5 read-shadow +
shared canonical store seed + signal substrate + steward + agency-rules
skill + MC plate-digest tool) before MC migration, then sequence the
per-agent migrations of the in-scope working set with each agent's
specific block-handling plan.
