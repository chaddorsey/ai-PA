# Unit 15 — Daily-Schedule Falsification Audit

Date: 2026-04-26
Per cycle-1 plan R52: before migrating daily-schedule-agent under the
"minimal persona = execute briefing skill only" assumption, scan all
its cron jobs and flag any that reference rich agent context. If any do,
revert to a richer persona.

## Naming correction

The brainstorm/plan calls this agent `daily-schedule-agent`. Letta's
actual name for the same agent is `daily-schedule-agent-sleeptime`
(`agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2`, agent_type
`sleeptime_agent`). Despite the type name, it's used as a cron-invoked
briefing producer, NOT as a background memory manager.

There is no separate "non-sleeptime" daily-schedule-agent.

## Audit findings (live scheduler-service, 2026-04-26)

3 active recurring `agent_message` cron jobs target this agent
(brainstorm's "11" was wrong; matches earlier research finding):

| job_id | cron | invocation | rich context? |
|---|---|---|---|
| 933b620f | `0 18 * * 5,6` | Generate MONDAY briefing via `generate_daily_briefing` | NO |
| f732d44c | `0 18,22,2,6 * * 0-5` | Generate next-day briefing via `generate_daily_briefing` (with target_date param) | NO |
| a683f7ef | `*/15 8-17 * * mon-fri` | Generate TODAY briefing via `generate_daily_briefing` | NO |

All 3 messages share the same template: "Generate a daily briefing
[for X] using the generate_daily_briefing tool. [date-handling guidance]."

## R52 falsification result: PASS

- No cron job requires multi-block reads.
- No cron job requires conditional reasoning over rich context.
- No cron job invokes a tool chain beyond the briefing skill.
- The agent's job is: receive cron-triggered prompt → call
  `generate_daily_briefing` → reply.

The minimal-persona migration target is viable. Phase E migration of
daily-schedule-agent will:

1. Replace the existing `sleeptime_agent` system prompt with a thin
   `system/persona.md`: "Execute generate_daily_briefing(target_date=…)
   on each scheduler invocation."
2. Detach the 4 v1 memory tools (`memory_replace`, `memory_insert`,
   `memory_rethink`, `archival_memory_search` — flagged in the canary
   pre-migration audit).
3. Detach all 26 attached blocks except `persona`/`memory_persona` and
   any block the `generate_daily_briefing` tool actually reads.
4. Verify the 3 cron jobs continue firing post-migration (Phase G smoke
   test: trigger one manually, confirm briefing produced).

## Inputs verified

- Tool source: `letta/daily_briefing/generate_daily_briefing.py`
  (per project memory)
- Cron action_type: `agent_message` (no script/http hybrid; cleanly
  agent-driven)
- Falsification has been verified once; if cron set changes
  pre-migration, re-audit.
