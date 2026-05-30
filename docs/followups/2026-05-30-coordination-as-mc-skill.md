---
date: 2026-05-30
status: design — implement at MC migration
related:
  - docs/migrations/local-mode/decommission-pa-routing-handler.md
  - docs/followups/2026-05-30-refactor-system-memfs-to-skills.md
  - docs/followups/2026-05-30-multi-agent-tui-workflow.md
---

# Coordination as MC skills (replacement for pa-routing-handler /v1/coordinate)

The pa-routing-handler `/v1/coordinate` endpoint encoded predefined
multi-agent workflows (e.g., `meeting_prep`) as task_type lookups in a
separate Flask service. That design was decommissioned 2026-05-30. The
**concept** — letting the user say "/mprep board meeting" and getting
back a synthesized briefing assembled from multiple specialist agents —
remains valuable.

The replacement pattern: **MC skills**. Each coordination workflow
becomes a skill that MC loads on demand and orchestrates by calling
sibling agents.

## Design

### Skill location

Global skills dir: `~/.letta/skills/<workflow-name>/SKILL.md`. Loaded by
MC when the user's request shape matches the skill's `description`.

### Dispatch substrate (two options)

1. **`Agent` tool (local-mode subagents)** — for sequential workflows
   where each step's output informs the next. Subagent has its own
   context budget; results return as text. Best for ≤3 specialist
   calls.

2. **`letta-teams` CLI via Bash** — for parallel fan-out across many
   agents at once. The skill shells out:
   ```bash
   letta-teams dispatch calendar="prep query" docs="prep query" pulse="prep query" -w
   ```
   Best for fan-out where parallelism matters (4+ specialists, latency
   sensitive).

   See `~/.skills/letta-teams/SKILL.md` for the full CLI surface.

### Inter-agent identity

Sub-agents called via Agent tool inherit `MEMORY_DIR` boundaries; they
cannot peek at MC's memfs by default (W6 in the local-mode plan).
Workflows that need shared context must pass it explicitly in the
subagent prompt. Same for letta-teams (each teammate gets a separate
prompt; no shared scratch).

This is the right contract — explicit handoff. If a meeting-prep flow
wants Calendar to know "meeting is with Leslie & Kiley", it includes
that in the dispatch prompt rather than expecting the subagent to read
MC's working_context.md.

## First skill to implement: meeting-prep

Replaces the legacy `meeting_prep` task_type. Triggered by:
- Direct user request: "prep me for the board meeting"
- Slash: `/mprep <meeting identifier>` (MC's slash table maps this to
  loading meeting-prep skill)

### Recipe sketch

```markdown
---
name: meeting-prep
description: |
  Multi-agent briefing for an upcoming meeting. Use when user says
  "prep me for X", "what should I know about meeting with Y",
  "/mprep X", or similar pre-meeting context-gathering requests.
---

# Meeting Prep

## 1. Identify the meeting (Calendar)

Use the Agent tool to ask calendar-agent (or shell `letta-calendar -p`):
> "Find the meeting matching '<user's description>' in the next 7 days.
> Return: date, time, attendees (with emails), agenda body if any."

If multiple matches, ask user to disambiguate.

## 2. Pull related context (parallel — letta-teams dispatch)

```bash
letta-teams dispatch \
  docs="Find recent notes / Drive docs related to {meeting title} or with attendees {emails}, last 30 days. Return titles + key bullets." \
  pulse="Find recent Slack threads mentioning {attendees} or {meeting topic}, last 14 days. Return links + summaries." \
  -w
```

## 3. Synthesize

Combine into briefing template:
- **Meeting**: <title>, <date/time>, <attendees>
- **Recent context with these people**: <docs+pulse bullets>
- **Agenda**: <verbatim from calendar>
- **What to read first**: <top 1-2 docs>
- **Open questions to clarify**: <derived from gaps>

## 4. Return verbatim to user

Don't ask "want me to do more?" — finish the briefing. User can ask
follow-ups.
```

## Other workflows worth porting

Past pa-routing-handler had `meeting_prep` as the sole concrete task_type.
Worth designing as skills:

1. **daily-brief** — already mostly handled by daily-schedule-agent's
   cron, but a user-triggered MC version that ALSO pulls task list +
   pulse signals would be useful
2. **status-recap** — "what happened today / this week" — pulls
   signals + recent agent activity + completed tasks
3. **followup-sweep** — "what's outstanding from <person>" — cross-agent
   query against email + slack + drive + tasks
4. **week-ahead** — combination of calendar + tasks + signals
   for upcoming 7 days
5. **person-context** — "give me everything you know about <person>" —
   canonical entry + recent meetings + slack threads + open tasks
   with them

Each becomes a skill. Each gets loaded only when relevant.

## When to implement

**At MC migration to local mode.** Reasons:
- These skills are MC's domain knowledge; they belong with MC's memfs/skills
- Local-mode MC has direct access to the Agent tool and CLI substrate
  (no slackbot-routing complications)
- Implementing now while MC is still Docker means writing them against
  pa-web-ui subprocess pool routing — more friction than waiting

Until MC migrates, skip coordination workflows; user can ask each
specialist directly (or use letta-calendar etc.).

## What NOT to do

- **Don't resurrect /v1/coordinate as a microservice.** The whole point
  is removing the indirection.
- **Don't put coordination logic in code.** It belongs in skill prose
  so MC can refine it based on what works.
- **Don't bake routing decisions into the service.** Let the user
  explicitly trigger (slash command or natural language). If MC
  auto-decides to coordinate when it shouldn't, the answer is sharper
  skill descriptions, not a separate routing layer.

## Open question

Whether MC's slash commands (like `/mprep`) should be:
- Hard-coded in MC's persona ("when user types /mprep, load
  meeting-prep skill")
- Or registered through letta-code's slash command system

The latter is more extensible (other slashes work the same way) but
requires writing letta-code config. The former is zero-config. Decide
at implementation time.
