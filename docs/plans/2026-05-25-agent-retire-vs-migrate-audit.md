---
title: Agent retire-vs-migrate audit
date: 2026-05-25
status: draft — seeking second opinion from Letta support agent
context: docs/plans/2026-05-25-letta-code-local-mode-investigation.md (W12 / W15)
---

# Agent Retire-vs-Migrate Audit

## Purpose

Before migrating each agent from the Docker Letta server to local mode,
classify whether the agent should actually be **migrated** as an agent, or
**retired** because its work can be done by a cron + CLI/skill without the
agent abstraction.

## Audit framework

For each agent, apply these tests:

1. **Multi-turn reasoning** — does the agent's job require accumulating
   context across turns, OR is each invocation a one-shot transformation?
2. **Persona meaningfulness** — does the agent have a role-specific persona
   + protocols that encode behavior, OR is it the generic "helpful self-
   improving agent" boilerplate?
3. **Tool surface** — is the agent calling 5+ distinct tools that benefit
   from being orchestrated by an LLM, OR is it a thin wrapper around 1-3
   tool calls that could be a shell script + cron?
4. **State accumulation** — does memfs/archival memory drive future
   behavior, OR is each invocation stateless?
5. **User-facing** — does a human interact with this agent directly, OR is
   it purely a backend automation step?

A "yes" on **any one** of multi-turn / persona / 5+ tools / state-driven
+ user-facing → **keep**. A "no" on all of them → **retire**.

## Agents in scope

Eighteen non-clutter agents (44 total minus 26 XXX-* / rogue / archive).

### Quick reference table

| Agent | Type | Tools | Crons | Blocks | Custom-Python | MCP | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| **Mission Control** | letta_v1 | 27 | 1 | 10 | 10 | 5 granola | **KEEP** — primary chat |
| **tasks-agent** | letta_v1 | 18 | 1 | 8 | 11 | — | **KEEP** — extraction reasoning |
| **pulse-monitor-agent_copy** | letta_v1 | 36 | 6 | 32 | 26 | 4 | **KEEP** — analytics consolidation |
| **daily-schedule-agent-sleeptime** | sleeptime | 19 | 4 | 26 | 5 | 7 scheduler | **KEEP + RENAME** (drop sleeptime) |
| **docs-and-transcripts-agent** | letta_v1 | 31 | 0 | 6 | 20 | 6 granola | **KEEP** — granola pipeline |
| **email-agent** | letta_v1 | 15 | 0 | 4 | 10 | — | **KEEP** — email patterns substantial |
| **main-assistant-agent-kinara** | letta_v1 | 32 | 0 | 22 | 12 | 7 | **KEEP IF SLACK USED** — Slack assistant |
| **sports_and_media_maven** | letta_v1 | 34 | 0 | 6 | 26 | — | **KEEP IF DOMAIN USED** — unique IR/Roku/TV tools |
| **calendar-agent_copy** | letta_v1 | 4 | 1 | 12 | 2 | — | **BORDERLINE** — see below |
| **work-packet-assembler** | memgpt | 11 | 0 | 2 | 4 | — | **RETIRE** — thin orchestration shell |
| **steward** | letta_v1 | 3 | 0 | 4 | 0 | — | **RETIRE** — could be a cron + script |
| **auto_madden_agent** | letta_v1 | 1 | 0 | 3 | 0 | — | **RETIRE** — actual work is in non-agent services |
| **6× *-sleeptime variants** | sleeptime | 4-28 | 0 | 4-43 | 1-23 | 0-2 | **RETIRE ALL** — per Ezra's deprecation note |

## Per-agent reasoning

### KEEP — substantive work that benefits from agent abstraction

#### Mission Control (`agent-90b2e860`)
- Primary user-facing chat agent (pa-web-ui, TUI, Slackbot)
- 10 memory blocks of role-specific protocols (`system/scheduling_protocol`,
  `system/canonical_reference_protocol`, etc.)
- Multi-turn reasoning is the entire point
- **Keep.** Last to migrate.

#### tasks-agent (`agent-dd15479e`)
- 18 tools, 8 blocks, 1 cron (daily self-check)
- LLM-based task extraction from email/Slack/Drive — genuine reasoning work
- Substantial role-specific blocks (task-extraction patterns)
- **Keep.** Good early-migration candidate (well-bounded scope).

#### pulse-monitor-agent_copy (`agent-2ed14ef4`)
- 6 daily crons producing Slack analytics briefings
- 32 memory blocks of channel-by-channel intel
- 26 custom Python tools (consolidation, scoring, signal emission)
- Genuinely multi-step daily workflow
- **Keep.**

#### daily-schedule-agent-sleeptime (`agent-a3f3940f`)
- 4 crons producing gold-standard briefings
- 26 memory blocks of schedule/preference state
- Uses 7 scheduler-mcp tools heavily — those convert to skill (W9)
- **Keep but rename** (drop sleeptime suffix per memory note about sleeptime deprecation)

#### docs-and-transcripts-agent (`agent-398b4f6c`)
- 31 tools, 20 custom Python (Drive + Granola pipeline)
- 6 granola-MCP tools — convert to `run_granola` CLI (W10)
- Maintains state about ingested transcripts, Drive doc summaries
- **Keep.**

#### email-agent (`agent-b4928949`)
- 15 tools, 4 blocks with substantial role-specific content:
  - `system/email_patterns` (2618 chars)
  - `system/task_extraction_process_email` (3990 chars)
  - `system/email_tool_use_guidelines` (2148 chars)
- Persona: "the Email Agent, managing Gmail for Chad Dorsey"
- 10 custom Python tools wrapping gmail-watch-service + task extraction
- **Keep.** The email-specific reasoning is substantive.

#### main-assistant-agent-kinara (`agent-b1574f99`) — conditional
- 32 tools, 22 memory blocks
- Slack-facing assistant (the Kinara persona)
- 12 custom Python + 7 scheduler-mcp + 5 CLI wrappers
- **Keep IF Slack interaction is desired post-migration.** Has substantive
  blocks and tool surface. If user moves to TUI exclusively, this agent
  could be reconsidered.

#### sports_and_media_maven (`agent-2515f29d`) — conditional
- 34 tools, 26 custom Python — UNIQUE tool surface for FiOS IR commands,
  Roku ECP control, TV guide queries, streaming content lookup,
  watch-history tracking, series tracking
- 5670-char `fios_and_roku_channel_info` block (specialized knowledge)
- Generic Letta persona BUT highly specialized tool inventory
- **Keep IF "watch the game" / TV control workflows are desired.** No
  substitute for this tool surface — the work isn't reasoning-heavy but
  the tool inventory is unique.

### RETIRE — thin shells around mechanical work

#### work-packet-assembler (`agent-06a5b4a8`)
**Strong retire candidate.**
- Only 11 tools, 4 of which are custom Python (write_packet_info,
  backtrace_task, fetch_source_content, stage_resource)
- The rest are Letta-built-ins (conversation_search, core_memory_*, memory_*)
- **Only 2 memory blocks** (persona + human, both ~1KB) — no role-specific
  protocols
- Persona is generic: *"You are Letta, the latest version of Limnal
  Corporation's digital companion..."*
- Trigger: invoked when tasks-agent confirms a task → calls back to
  pa-web-ui pipeline
- **Replacement**: pa-web-ui's `/api/tasks/<id>/confirm` endpoint runs the
  work-packet assembly directly (fetch source → write packet → emit
  signal). No agent needed; the work is mechanical.
- **Cost to retire**: low. ~2h to move the pipeline logic into pa-web-ui
  and delete the agent record after a soak window.

#### steward (`agent-6349140d`)
**Strong retire candidate.**
- 3 tools, ALL Letta built-ins (`conversation_search`, `memory_insert`,
  `memory_replace`)
- Generic Letta persona (no specialization)
- Role per `system/duties` (5315 chars): boot-time config-drift detector,
  required-tools auditor
- This is a cron job + Python script, not an agent
- **Replacement**: a `scripts/steward-check.sh` run by launchd or
  scheduler-service that:
  - Queries each agent's tool inventory
  - Compares against expected (declared in `system/required_tools.md` per
    agent-memfs-conventions)
  - Emits a signal or sends a Slack alert if drift detected
- **Cost to retire**: ~3h to write the check script.

#### auto_madden_agent (`agent-30ff1be2`)
**Strong retire candidate.**
- 1 tool (`conversation_search`)
- 13977-char `extracted_tasks` block (looks like stale data leaked from
  another agent)
- Generic Letta persona
- Real Auto-Madden work happens in non-agent services:
  `auto-madden-game-state` (5132), `auto-madden-insight-engine` (5131),
  `auto-madden-companion-ui` (5130)
- **Replacement**: none — the agent isn't doing any work. Already
  effectively retired.
- **Cost to retire**: trivial. Just delete the agent record.

### RETIRE — sleeptime variants (Ezra deprecation 2026-04-26)

Per `feedback_multi_agent_messaging_deprecation` and the Cycle-1
notes, `agent_type='sleeptime_agent'` is being deprecated. Replacement
path: reflection subagents (ephemeral, client-side) for genuine background-
of-a-parent use cases, OR plain `letta_v1_agent` for everything else.

Under local mode specifically, the parent/sleeptime split makes even less
sense — local-mode agents are themselves lightweight processes; running
two of them for one "logical agent" doubles infrastructure cost for
unclear benefit.

| Sleeptime agent | Status | Action |
|---|---|---|
| `pulse-monitor-agent-sleeptime` | retired predecessor, idle since Dec 2025 | Delete |
| `companion-sleeptime_copy` | unclear purpose | Audit then delete or merge |
| `email-agent-sleeptime` | paired with email-agent (which is keep) | Delete; email-agent absorbs the function |
| `tasks-agent-sleeptime` | paired with tasks-agent (which is keep) | Delete; tasks-agent absorbs |
| `sports_and_media_maven_sleeptime` | paired with maven | Delete; maven absorbs |
| `auto_madden_sleeptime` | paired with auto_madden_agent (also retiring) | Delete with parent |

### BORDERLINE — calendar-agent_copy

Worth a closer look before deciding.

#### calendar-agent_copy (`agent-892a2d58`)
- Only 4 tools (`orchestrate_scheduling`, `emit_canonical_signal`,
  `web_search`, `fetch_webpage`)
- BUT **12 memory blocks** with substantial role-specific content:
  - `system/orchestrate_scheduling_tool_use_guidelines` (6716 chars)
  - `system/persona` (3246 chars; "calendar management specialist")
  - `system/scheduling_context`, `system/calendar_preferences`,
    `system/user_calendar_context`, `system/user_preferences`, etc.
- 1 cron job (calendar refresh / sync)
- Persona is meaningful (calendar specialist) and the protocols encode
  scheduling intelligence (preferences, calendly handling, conflict
  resolution heuristics)

**The case for KEEP:** the calendar specialist persona + the 6.7KB
scheduling-tool-use guidelines encode real domain knowledge that an
arbitrary one-shot CLI wouldn't reproduce. The agent's accumulated state
(canonical signals it emits, scheduling patterns it learns) has value.

**The case for RETIRE:** the only actual *tool* is `orchestrate_scheduling`.
If that becomes a `run_calendar orchestrate ...` CLI, MC could call it
directly with the right protocol skill, and the calendar persona could
absorb into MC's `system/calendar_use_protocol.md`.

**Open question for Letta support:** is there a way to package the
calendar-specialist behavior as a skill on MC without losing the
accumulated scheduling-pattern state? Or is the "specialist sub-agent"
pattern still the right shape for this kind of domain expertise under
local mode?

## Proposed action set

If audit is accepted:

### Definitely retire (no agent migration needed, ~5 deletions)
- `work-packet-assembler`
- `steward`
- `auto_madden_agent`
- 6× sleeptime variants

### Revised after 2026-05-25 conversation review

After iterating on the original audit with the user, additional
retirements identified:

- **email-agent** retires. Its 15 tools are wrappable (run_gws covers
  the main Gmail surface; gmail-watch tools become a skill); its
  3 substantive memory blocks (email_patterns, task_extraction_process_email,
  email_tool_use_guidelines) move to tasks-agent. tasks-agent absorbs the
  email-extraction function.
- **work-packet-assembler** retires INTO tasks-agent (not into pa-web-ui
  as originally proposed). One agent owns the whole task lifecycle:
  extract → confirm → assemble → dispatch.
- **daily-schedule-agent** retires. The agent is an overglorified cron
  job — its sole function is calling `generate_daily_briefing` (a Python
  tool) on a timer. The 26 memory blocks are read BY THE TOOL, not by the
  LLM. Reducing to a cron-driven script is strictly better: one fewer
  LLM call per briefing, faster, cheaper, same output. Memory blocks
  migrate to MC's memfs (priorities, schedule_preferences, monitoring
  recipes — MC reads them for chat anyway).
- **tasks-agent-sleeptime** action tools (`post_slack_channel_reply`,
  `send_slack_dm`, `draft_reply_to_email`, `sync_omnifocus_completions`)
  become explicit skills, not absorbed into tasks-agent. Preserves the
  safety boundary (action-side is dangerous-on-impulse).

### Definitely migrate (5 agents)
- **Mission Control** — primary chat surface
- **tasks-agent** — extraction + work-packet assembly + email function
- **pulse-monitor-agent_copy** — daily Slack analytics consolidation
- **docs-and-transcripts-agent** — Granola + Drive pipeline
- **calendar-agent_copy** — Slackbot scheduler dependency (confirmed); multi-tenant future

### Conditional (1-2 agents — keep but reconsider)
- **main-assistant-agent-kinara** — Slack-facing executive assistant.
  KEEP for now; flag as a follow-up workstream (see "Slack strategy"
  section below). Long-term: probably absorb into MC with Slackbot
  routing directly.
- **sports_and_media_maven** — keep IF TV-control workflows still desired

### Docker purgatory (defer)
- **auto_madden_agent** — defer (NFL-season; non-agent services do the work)
- **sports_and_media_maven** — defer (alternative to migrating)

### Retire (10 agents)
- email-agent (functions → tasks-agent + gmail-watch skill)
- work-packet-assembler (functions → tasks-agent skill)
- daily-schedule-agent (functions → cron-driven script + memfs files on MC)
- steward (functions → cron-driven script + alerting)
- auto_madden_agent (no actual work being done)
- 6× sleeptime variants (deprecated; action tools → skills where needed)

### Final fleet shape

- **5 definite agents** post-migration
- Plus 1 conditional (Kinara, pending Slack strategy)
- Plus 1-2 in purgatory (auto_madden, maven)
- **Down from 18** active-or-load-bearing today
- Down from 44 total agent records currently

## Slack strategy planning (Workstream candidate, post-migration)

The Slackbot today routes ALL Slack DMs to `main-assistant-agent-kinara`
(agent-b1574f99) as the primary handler, and routes scheduling-intent
requests to calendar-agent_copy. Kinara has ~32 tools and ~22 memory
blocks that substantially OVERLAP with MC's tools and blocks — the two
agents are effectively split-brain "executive assistants" with separate
memories for the two interfaces (Slack vs. pa-web-ui chat).

### Three options for the Slack strategy

| Option | What | Tradeoff |
|---|---|---|
| **A. Keep Kinara separate** | Status quo — Slackbot to Kinara, pa-web-ui to MC | Two agents to maintain; split brain on memory blocks; "did you tell MC or Kinara that thing?" confusion |
| **B. Slackbot routes to MC directly** | One agent (MC) handles all chat surfaces; Kinara retired | Unified memory; MC gets all Slack noise; simpler architecture; requires Kinara's distinct blocks merged into MC's memfs |
| **C. Thin Slack-routing dispatcher** | Slackbot picks agent per intent (scheduling → calendar-agent, otherwise → MC) | Smarter routing; dispatcher logic lives somewhere (slackbot itself? a tiny new service?); preserves specialist agents |

### Public-facing direction (per user)

If calendar-agent eventually serves OTHER Concord employees via Slack
(not just Chad), the architecture has different constraints:

- Identity-aware behavior per Slack user
- Per-user preferences (calendar-agent already has `preferences_U02V91KU8`
  and `preferences_U0AB18G54ET` blocks — Slack user IDs)
- Privacy boundary across users
- Calendly URL per user (run_calendly needs per-user identity)
- Persona shifts from "Chad's assistant" to "scheduling assistant for
  the requesting Concord user"

The multi-tenant constraint argues for **keeping specialists** (Option C)
rather than absorbing everything into MC (which has Chad-specific
persona). Calendar-agent's per-user preferences pattern already
half-supports this; build on that rather than refactoring.

### Recommended sequencing

This is a follow-up workstream, NOT on the local-mode migration
critical path. Suggested order:

1. **During migration**: keep Kinara as-is. Migrate it like any other
   agent (it has substantial memory blocks).
2. **Post-migration**: revisit. By then we'll have local-mode operational
   experience and the multi-tenant calendar question will be sharper.
3. **Decision points**:
   - If TUI replaces Slack as the daily interface: retire Kinara (Option B)
   - If Slack stays critical but multi-tenant matters: invest in Option C
     (a dispatcher) + keep calendar-agent as specialist
   - If Slack stays single-tenant (just Chad): Option B is cleanest

## What we actually want from Letta support

After two rounds of iteration, most of our original five questions have
been answered by our own investigation. The one that hasn't is the
underlying architectural question:

### **When should an agent stay narrow vs. broaden its scope?**

Concrete instances of this question in our migration:

| Decision point | Narrow option | Broad option | Our current lean |
|---|---|---|---|
| tasks-agent absorbing email-agent + work-packet-assembler | Three specialist agents | One task-lifecycle agent | Broad (absorb) |
| calendar-agent_copy as specialist | Keep narrow scheduling agent | Absorb into MC + skill files | Narrow (Slackbot dep + multi-tenant) |
| Kinara as Slack twin of MC | Two interface-specific agents | One MC + Slack router | Narrow now, broad later |
| daily-schedule-agent | Specialist briefing agent | Cron + script reading from MC's memfs | Broad (retire agent; script-ify) |
| Sleeptime action twins | Twin agents with action tools | Action skills any agent can invoke | Broad (skills) |

### The pattern we're using (heuristic)

- **Broaden when:** natural workflow continuity (task lifecycle), heavy
  memory-block overlap (Kinara/MC), the "agent" is just calling one
  tool (daily-schedule), or the safety boundary can move to explicit
  skill invocation (sleeptime action twins)
- **Stay narrow when:** different audiences (multi-tenant calendar),
  meaningfully different persona (calendar specialist vs. generalist),
  memfs context would explode in a generalist (Granola voluminous
  knowledge stays with docs-and-transcripts), or external routing
  depends on the specialist's identity (Slackbot routes to calendar-agent)

### The actual question for Letta support

> **Does Letta's design philosophy under local mode favor fewer broader
> agents or many narrower specialists? And what anti-patterns should we
> avoid?**

Concretely:
- Is our heuristic above sound? Are there cases where we're broadening
  too aggressively or keeping too narrow?
- Is the "specialist agent for a domain that the primary agent could
  also do" pattern (calendar-agent_copy) something Letta still
  recommends, or is the direction moving toward "one rich agent with
  skill files for domain knowledge"?
- For agents whose only function is calling one tool on a cron
  (daily-schedule-agent), is the "retire and replace with script"
  pattern always the right call, or are there cases where keeping the
  agent abstraction adds value we're missing?
- Any other anti-patterns to flag?

The other questions we had earlier (calendar specialist vs. MC absorb,
sleeptime replacement, work-packet-assembler retirement, domain agents
under local mode, steward as script) all collapse into this central
question. Their answers fall out from whatever Letta's general
philosophy on agent scope under local mode is.
