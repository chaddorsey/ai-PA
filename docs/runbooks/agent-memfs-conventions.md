# Agent memfs Conventions — Cycle 1

Status: living document
Last updated: 2026-04-28

## Purpose

Define what belongs in each agent's memfs (the per-agent Gitea repo
mounted as the agent's file-backed memory) and what does NOT, so that:

1. Agents have what they need without dragging the rest of the system in.
2. Layer drift (declared capabilities vs. actual capabilities) is visible.
3. Cross-agent consumption flows through Layer-5 canonical signals,
   not through reading another agent's memfs.

## Cache-discipline rule (READ THIS FIRST)

Anything under `system/` is **recursively pinned** into the model's
prompt prefix. Pinning is what makes the file always-available without
a tool call — but rewriting a pinned file **invalidates the prefix
cache** for every subsequent turn. Letta's prompt cache TTL is 5 min;
busting it costs latency + tokens + money on every turn that follows.

Rule: **`system/` is for files that do not get rewritten in normal
operation.** Rolling projections, digests, and any file rewritten on
a schedule MUST live OUTSIDE `system/` so they're lazy-loaded via
`Read` / `read_memory_file` and don't sit in the prefix.

Concrete pattern in MC's memfs:

| File | Path | Pinned? | Rewritten? |
|---|---|---|---|
| Persona, playbook, protocols | `system/*.md` | yes | no — stable instructions |
| Today's schedule (5×/day) | `schedule/today.md` | no | yes — cron-driven |
| Today's signal digest (3×/day) | `digest/recent_signals.md` | no | yes — protocol-driven |
| Dated archives | `schedule/2026-04-26.md` etc. | no | append-only, never overwritten |

If you find yourself wanting to write to a `system/` file more than
once after creation, that's a signal it belongs elsewhere.

## What memfs IS for

memfs is **per-agent identity, behavior, and projections**:

- **Layer 4 — Identity / behavior** (durable, slow-changing):
  - `system/persona.md` — role, voice, taste, hard rules.
  - `system/required_tools.md` — declarative list of tools this agent
    is expected to have attached, with a one-line purpose for each.
    Drift from this file vs. the agent's actual `tools` is what a
    steward / boot-time check should flag.
  - `system/known_external_breakages.md` — facts about external systems
    this agent talks to that have changed shape (CLI subcommand removed,
    API field renamed). Pinned so the agent doesn't rediscover and
    improvise around them on every encounter.
  - Process / workflow files: `*_use_guidelines.md`,
    `*_reporting_process.md`, `*_priorities.md`. These are
    skill-adjacent — they're how-the-agent-works text the agent reads
    each turn that the role applies.

- **Layer 3 — Per-agent projections** of canonical state, kept up to date
  by the agent itself:
  - Rolling latest-only files (lazy-loaded — NOT under `system/`):
    `schedule/today.md`, `digest/recent_signals.md`,
    `plate/current.md`. These get overwritten each refresh — the agent
    Reads them as a working view but they don't sit in the prefix cache.
    `system/daily_analytics_briefing.md` is a legacy exception (rewritten
    daily but currently pinned); migrate to `briefing/daily.md` next pass.
  - Reference snapshots derived from canonical: `slack_channels_list.md`,
    `drive_analytics_averages.md`, etc. Refreshed periodically.

## What memfs is NOT for

- **Layer 1 — Canonical external facts** (Drive activity, calendar
  events, OmniFocus task records). Leave those in their canonical
  store; project a summary into memfs only when the agent needs a
  view it returns to repeatedly.
- **Layer 2 — Transactional / operational state** (`pa_web.task_queue`,
  `analytics.daily_snapshots`, scheduler-service jobs). DB.
- **Layer 5 — Cross-agent signals**. Even when the *same agent* emits
  it, the durable record lives in `agents-canonical/signals/`.
  The agent may keep a Layer-3 projection of its *own* recent signals
  in memfs (e.g., `system/daily_vibe_check_<DATE>.md`) for
  iterative refinement, but consumers read from canonical.
- **Historical archive**. Per-day vibe-check files going back months
  are NOT what memfs is for. Once a vibe check is in canonical
  signals, the per-day memfs copy can be pruned (steward task).
  Agents iterate on the latest 1-2; consumers query canonical.
- **Anything other agents need**. If MC needs to read a vibe check,
  it reads from `agents-canonical/signals/<date>/pulse-monitor-slack-vibe.md`,
  not from pulse-monitor's memfs. Treat memfs as agent-private.

## Dual-write pattern: memfs + canonical signal

When an agent produces output that is *both* an iterative working artifact
*and* something other agents should consume, dual-write:

- **memfs copy** (Layer 3): rolling, agent-private, used for refinement
  loops. Path is the agent's choice.
- **Canonical signal** (Layer 5): dated, agent-public, immutable per emission
  (idempotent overwrite for same slug+source+date). Path is
  `signals/<DATE>/<source>-<slug>.md` via `emit_canonical_signal`.

Examples:
- Vibe check → memfs `system/daily_vibe_check_<DATE>.md` + canonical
  `signals/<DATE>/pulse-monitor-slack-vibe.md`.
- Morning briefing → memfs `system/daily_analytics_briefing.md` (rolling)
  + canonical `signals/<DATE>/pulse-monitor-analytics-morning.md`.
- Schedule digest → memfs `schedule/today.md` (rolling) + canonical
  `signals/<DATE>/calendar-agent-schedule.md`.

## Per-agent expected contents (cycle-1 baseline)

Each migrated agent should have at minimum:

```
system/
  persona.md                    # who I am, what I do, hard rules
  required_tools.md             # tools I expect to have attached
  known_external_breakages.md   # external-system contract facts (start empty if none known)
```

Plus role-specific Layer-3/4 files. See per-agent sections below.

### Mission Control

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`
- `system/signals_protocol.md` (pinned, stable — instructions for digest refresh)
- `plate/current.md` (rolling — NOT under `system/` — refreshed by `refresh_plate`)
- `schedule/today.md`, `schedule/today.json` (rolling — NOT under `system/` — written by `generate_daily_briefing`)
- `digest/recent_signals.md` (rolling — NOT under `system/` — refreshed by the signals protocol; gives MC's working view of what worker agents have surfaced lately)

### pulse-monitor

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`
- `system/monitoring_priorities.md`, `system/three_month_priorities.md`
- `system/slack_channels_list.md`, `system/slack_pulse_reporting_process.md`,
  `system/slack_tool_use_guidelines.md`
- `system/drive_analytics_averages.md`, `_config.md`, `_personal.md`,
  `_workspace.md`, `_mentions.md`
- `system/drive_tool_use_guidelines.md`
- `briefing/daily_analytics.md` (rolling latest — NOT under `system/`)
  *(legacy: currently lives at `system/daily_analytics_briefing.md`; migrate next pass)*
- `vibe/daily_<DATE>.md` (1-2 most recent only — NOT under `system/`;
  steward prunes older)
  *(legacy: currently `system/daily_vibe_check_<DATE>.md`; migrate next pass)*

### calendar-agent_copy

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`
- `system/calendar_query_patterns.md` (gold-standard query phrasings)
- `system/working_hours.md`

### tasks-agent

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`
- `system/task_extraction_rubric.md`
- `system/quarantine_review_process.md`

### email-agent

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`

### docs-and-transcripts-agent

- `system/persona.md`
- `system/required_tools.md`
- `system/known_external_breakages.md`
- `system/granola_extraction_rules.md` (Granola marker handling, etc.)

## Maintenance

- Adding a new tool: update `system/required_tools.md` *first*, then
  attach the tool. The file is the source of truth for "what this
  agent should have"; the Letta DB is the source of truth for
  "what this agent does have." The steward (or a boot-time check)
  reconciles.
- Removing a tool: remove from `required_tools.md` AND detach.
- External system contract changes: add a line to
  `known_external_breakages.md` describing the change, the date
  it was discovered, and the workaround if any. Remove the line
  once the breakage is permanently fixed.
