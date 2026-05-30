---
title: Schedule Lookahead — Stage 2 (pure-Python schedule builder + cross-tab tool)
created: 2026-04-29
status: deferred
owner: chad
---

# Schedule Lookahead — Stage 2

Stage 1 (shipped 2026-04-29) extended the `daily-schedule-agent` cron to
pre-write `signals/{date}/schedule.md` for D+2..D+13 every morning at
5 AM ET. Each pre-write goes through the agent's
`generate_daily_briefing` tool — which means an LLM run per future day.

Stage 2 replaces the LLM with a deterministic Python builder for the
routine pre-write path, and adds a cross-tabulation tool for free-time
queries.

## Why Stage 2

**Cost.** Twelve agent runs per day at ~10-30s each is a non-trivial
LLM bill and a ~3-6 min wall-clock sequential window. The schedule
synthesis itself is mostly deterministic: pull events from the calendar,
dedupe overlapping busy blocks, clamp to work_end, compute available
intervals. The LLM is doing rule-following, not reasoning.

**Latency.** When MC asks "do I have 2 free hours next Tuesday?", the
file ideally already exists (Stage 1 ✓). But for ad-hoc "show me all my
open 30-min windows in the next 14 days", we don't want a 14-LLM-call
fan-out. A pure-Python tool should answer in <1 second by reading the
already-written `schedule.md` JSON blocks.

**Reliability.** LLM runs sometimes hit `stop_reason: tool_rule` or
fail silently. The Stage-1 smoke test missed 1/12 days. A pure-Python
builder either succeeds or fails loudly, with a stack trace.

## Scope

### Stage 2.A — Extract pure-Python schedule builder
- Read the body of `generate_daily_briefing` (currently inside
  Letta's tool sandbox; the source is in `letta/tmp*.py` or similar) —
  isolate the deterministic synthesis logic from the agent-coupling
  glue.
- Lift it into `scheduler-service/scripts/build_schedule.py` (or a
  proper service module) that takes `(target_date, calendar_event_list)`
  → markdown briefing + JSON busy_blocks dict, identical format to the
  current `signals/{date}/schedule.md`.
- Add a Google Calendar fetcher (the existing `gws` CLI in the letta
  container can serve here, or a direct Calendar API call with the
  service account). Returns a flat list of events for the target_date.
- Cron: replace `daily-schedule-lookahead.py` LLM-loop with a Python
  loop that calls the builder for each offset 0..13. Now today + tomorrow
  + lookahead all flow through the same code path. The agent still runs
  intra-day (every 15 min during workdays) for the natural-language
  polish + memory block update; the canonical signal file is owned by
  the script.

### Stage 2.B — Cross-tabulation tool
- New script + CLI `query_available_time.py` (or a lightweight FastAPI
  endpoint on scheduler-service):
  - Inputs: `start_date`, `end_date`, `min_duration_minutes` (default 30),
    `working_hours_only=true`, `weekdays_only=true`
  - Reads `signals/{D}/schedule.md` for each day in range, parses the
    embedded `Schedule JSON`, computes free intervals, filters by
    `min_duration`, returns sorted list across the range
- Surface as:
  - A Python CLI for Bash-via-skill use from MC
  - Optionally a Letta tool (`query_available_time(start, end, min)`)
    for direct agent calls — though the Bash+CLI path is preferred
    given recent feedback against tool proliferation

### Stage 2.C — Dirty-day recompute
- Track per-day "calendar_etag" or "last_modified" from Google Calendar
  Activity feed. When a day's etag changes, mark it dirty and rebuild
  only that day's `signals/{date}/schedule.md`.
- Eliminates the every-15-min today-refresh churn in cases where the
  calendar didn't actually change.
- Implementation can piggyback on the existing Activity API poller
  (`drive-rag/activity_client.py`) — point a second instance at the
  Calendar service and write to a `calendar_freshness` table similar
  to `drive_freshness`.

## Format decision (2026-04-29) — must hold across Stage 2

`signals/{date}/schedule.md` MUST be hybrid: **YAML frontmatter as
machine truth, markdown body as human/LLM-rendered view**, body
**rendered from** the frontmatter, not parallel to it.

The current producer embeds a single-line `**Schedule JSON** (for
time-remaining.py): {...}` inside the body. Stage 2 deletes that line.
Structured truth moves into frontmatter:

```yaml
---
description: Daily schedule + available time for {date}
source: daily-schedule-agent
attention_level: routine
date: {YYYY-MM-DD}
day_of_week: {Monday..Sunday}
timezone: America/New_York
work_start: "08:00"
work_end:   "17:00"
last_refreshed_at: {ISO8601}
busy_blocks:
  - { name: ..., start: "HH:MM", end: "HH:MM", attendees: [...] OR attendee_count: N }
  ...
free_blocks:
  - { start: "HH:MM", end: "HH:MM", duration_min: N }
  ...
total_free_min: N
---

# {Day}'s Schedule (updated {timestamp})

## Schedule
- **{HH:MM}–{HH:MM}** — {name} *({attendees})*
...

## Available time — {Hh Mm}
- {HH:MM}–{HH:MM} ({duration})
...
```

Why this format is non-negotiable:

1. **Single source of truth.** Markdown body is rendered FROM the YAML;
   they cannot drift.
2. **Cross-tab is one parser.** `query_available_time(start, end, min)`
   reads `free_blocks` from frontmatter directly. No regex over markdown.
3. **LLM-native.** Both halves enter context together. Agents see
   facts (frontmatter) AND prose (body), don't have to parse either.
4. **Convention parity.** `pulse-monitor-pipeline-health.md`,
   `slack-watch-mentions-active.md`, `steward-daily-rollup.md` already
   use this shape. Schedule's the outlier.
5. **Reporting is free.** Print the body for humans; hand the
   frontmatter to tools.

Producer-only change. Existing markdown readers keep working; new
structured readers target frontmatter.

## Open questions

- **Where does the synthesis logic live?** Today it's inside the
  `generate_daily_briefing` Letta tool. To extract, either move that
  tool's body to a shared module (importable both as a Letta tool and
  as a script) or accept duplication. Probably easier to maintain as
  one Python module the tool also imports.

- **Focus-block + protected-time rules.** The current synthesis applies
  several Chad-specific rules (focus-block defaults, work_end clamp,
  meeting-density limits). These need to live somewhere readable by
  both the agent and the script. Probably:
  `agents-canonical/reference/user/prefs/scheduling.md` — already exists
  per `system/shared_context`.

- **What gets lost without the LLM?** The friendly-language framing of
  the briefing ("Wednesday looks busy; suggest a buffer at 2:30"). The
  signal file should be the deterministic synthesis; the LLM-rendered
  variant can still live in the daily-schedule-agent's own memory block
  (current_daily_schedule_and_available_time) for chat-style display.

- **Migration plan.** Run Stage 2.A in shadow mode first: compute the
  pure-Python output, diff it against the LLM output for a week, fix
  any divergence, then cut over. The cron flips from `script:
  daily-schedule-lookahead.py` (LLM-fanout) to `script:
  build_schedule_loop.py` (pure-Python).

## When to revisit

Pick this up after Stage 1 has run for a week and we have:
- A sample of pre-written lookahead briefings to compare against
- A clearer sense of how often `tool_rule` failures or silent gaps
  occur in practice
- A real cross-day query MC needs to answer that motivates the
  cross-tab tool

## Related

- `scheduler-service/scripts/daily-schedule-lookahead.py` (Stage 1)
- `scheduler-service/scripts/steward-daily-rollup.py` (analogous
  pure-Python pattern that already replaced an agent path)
- `letta/tmp*.py` (current location of the `generate_daily_briefing`
  tool body — inspect for synthesis logic to extract)
- `signals/{date}/schedule.md` JSON block (consumer contract for
  cross-tab tool)
