---
description: Standalone daily-briefing generator. Replaces the daily-schedule-agent + generate_daily_briefing tool with a direct host-side script.
applies-to: cron triggers (replaces 4 scheduler-service agent_message jobs that target daily-schedule-agent)
replaces:
  - daily-schedule-agent (the entire agent — it was an overglorified cron job)
  - generate_daily_briefing Letta tool (now run as a host script)
cli: scripts/daily-briefing.py
---

# Daily Briefing Script

## Why this exists

The legacy flow was:

```
cron tick → scheduler-service → letta server
  → daily-schedule-agent (LLM prompt: "use the generate_daily_briefing tool")
  → LLM emits one tool_call
  → tool body runs (fetch calendar via gws, format, write to Gitea)
  → response → scheduler-service execution log
```

The LLM step adds 30-90s and dollars per tick but contributes zero
reasoning. The agent has no agency — it just dispatches one tool.

Replacement flow:

```
cron tick → scheduler-service (script action) → daily-briefing.py
  → fetch calendar via gws, format, write to Gitea
```

One fewer process, no LLM call, ~3s end-to-end.

## Usage

```bash
daily-briefing.py [--target-date YYYY-MM-DD] [--calendar-id <email>]
                  [--timezone <tz>] [--mc-agent-id <id>] [--json]
```

Examples:

```bash
# Today's briefing (writes to Gitea on success)
daily-briefing.py

# Specific date
daily-briefing.py --target-date 2026-05-26

# JSON output (for scheduler-service / programmatic use)
daily-briefing.py --json | jq .

# Different MC agent (for testing against canary)
daily-briefing.py --mc-agent-id agent-local-d06e9bf7-...
```

## Prerequisites

- `gws` CLI on `$PATH` with `cdorsey@concord.org` credentials configured
- `GITEA_MEMFS_TOKEN` in env
- `GITEA_BASE_URL` — defaults to `http://localhost:3030` (host) or
  `http://gitea:3000` (Docker network)

## What it writes

Two files per invocation:

1. **Canonical signal** at `agents-canonical/signals/<date>/schedule.md`
   — for cross-agent consumption via `signal read --source schedule`
2. **MC's memfs** at `agent-<MC-id>/contents/schedule/today.md`
   — for MC's own awareness (the file MC consults during chat)

Both are committed to Gitea. The contents are byte-equivalent to what
the legacy `generate_daily_briefing` Letta tool produced.

## Migration path (per-cron, when ready)

The 4 scheduler-service cron jobs that currently target
daily-schedule-agent need to flip from `agent_message` action to a
host-side script invocation. Options:

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| **A. scheduler-service `script` action type** | Bind-mount `/Volumes/main-drive/ai-PA/scripts` into `/app/scripts` of scheduler-service; flip `action_type` from `agent_message` to `script` | Keeps scheduler-service as the orchestrator; uniform job management | Requires Docker compose change |
| **B. launchd cron on host** | Write a plist that calls `daily-briefing.py` at the same times | Removes scheduler-service from the loop for this one job | Two cron systems |
| **C. scheduler-service POSTs to a tiny host HTTP shim** | Like letta-local-runner but for arbitrary host scripts | Composable, ready for other Tier-3 scripts | Yet another service |

**Recommended: A.** Scheduler-service is the source of truth for what
runs when; flipping the action type keeps that property. The Docker
compose change is small.

To wire (when ready):

1. Add a volume mount in `docker-compose.yml` under `scheduler-service`:
   ```yaml
   volumes:
     - ./scripts:/app/scripts:ro
   ```
2. For each of the 4 daily-briefing cron jobs (find via
   `scheduler search "briefing"`), PATCH the action to:
   ```json
   {
     "action_type": "script",
     "config": {
       "script": "daily-briefing.py",
       "args": ["--target-date", "{{date}}", "--json"],
       "env": {
         "GITEA_MEMFS_TOKEN": "...",
         "GITEA_BASE_URL": "http://gitea:3000"
       },
       "timeout": 120
     }
   }
   ```
3. Verify the next execution succeeds; once soak-clean, retire the
   `daily-schedule-agent` agent record (after exporting any
   accumulated archival memory you want to preserve).

## Validation history

- **2026-05-25** — Standalone smoke against live calendar + Gitea.
  Generated briefing for 2026-05-26, wrote canonical signal
  (signals/2026-05-26/schedule.md, 1204 bytes) and MC memfs
  schedule/today.md (642 bytes), 3 seconds wall time.

## Open items

- `--no-write` dry-run flag is accepted but not yet honored by the
  underlying function. Add support in the function itself if dev-mode
  briefing generation becomes useful.
- `BRIEFING_CALENDAR_ID` and `BRIEFING_TIMEZONE` env defaults could
  move to a config file if we ever migrate the calendar identity to
  per-environment values.
