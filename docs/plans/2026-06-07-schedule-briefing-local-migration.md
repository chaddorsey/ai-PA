---
date: 2026-06-07
status: DONE — verified in production
goal: Move the daily SCHEDULE briefing onto the local deterministic extension
  path (the analytics-briefing twin), retire the Docker daily-schedule-agent,
  and fix the stale today.md / canonical schedule signal.
related:
  - docs/plans/2026-06-07-server-tools-definitive-disposition.md
  - docs/runbooks/2026-06-07-schedule-briefing-cron-flip-rollback.md
  - docs/runbooks/2026-06-07-pulse-cron-extension-flip-rollback.md  # analytics twin
  - docs/superpowers/specs/2026-06-07-pulse-analytics-extension-pilot-design.md
---

# Schedule-briefing local migration (record)

## What moved
The schedule briefing (`generate_daily_briefing`) — calendar events +
available-time 8AM–5PM Eastern, written to MC memfs `schedule/today.md`, the
canonical signal `signals/{date}/schedule.md`, a JSON sidecar, and (legacy) a
memory block — was the **last fleet capability still running on the Docker
Letta server** (agent `daily-schedule-agent-sleeptime`,
`agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2`).

It now runs as the extension tool **`generate_daily_briefing_ext`** in the
pinned `~/.letta/pa-tools-venv` (deterministic interpreter, sidesteps LET-9147),
invoked by the local agent **calendar-agent_copy-local**
(`agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c`) via the local runner.

## How (same template as the analytics pilot)
- Source module: `letta/daily_briefing/generate_daily_briefing.py`, imported as
  `daily_briefing.generate_daily_briefing` (PYTHONPATH already includes `letta`).
- Registered in `letta/extensions/pa-tools.ts` via the `dateTool` factory,
  generalized with a `dateParam` argument (this tool's date kwarg is
  `target_date`, not the analytics tools' `date`). Deployed to
  `~/.letta/extensions/pa-tools.ts`.
- Two extension fixes were required because this is the first migrated tool that
  shells out to a host CLI (`gws calendar`):
  1. **PATH**: `runPinned` now prepends `~/bin:/opt/homebrew/bin:/usr/local/bin`
     — the launchd-spawned runner subprocess does not inherit the user shell PATH,
     so `gws` was not found.
  2. **gws creds**: added `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`
     (= `gws-bridge/credentials.json`) to `~/.letta/pa-tools.env` — the runner
     subprocess has no Keychain access, so gws needs an explicit creds file.
  Also added `MC_AGENT_ID` to the env file (the tool already defaulted correctly).

## Crons flipped (scheduler :8087)
| Job ID | Title | Cron |
|---|---|---|
| `933b620f-…` | Weekend - Monday Preview | `0 18 * * 5,6` |
| `f732d44c-…` | Off-Hours - Next Day | `0 18,22,2,6 * * 0-5` |
| `a683f7ef-…` | Gold-Standard (workday) | `*/15 8-17 * * mon-fri` |

Each: `agent_id` → calendar-local, `route` → `local`, message
`generate_daily_briefing`→`_ext` and param token `target_date`→`date`.
Pre-flip snapshot: `docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json`.

## Verification (2026-06-07)
- Phase-1 direct venv run: `status:ok`, real calendar data.
- Phase-2 agent runs: 3/3 green (8 events, memfs written).
- All 3 crons triggered → fresh `succeeded` execution records.
- **today.md** fresh (Sunday 5:26 PM) — was stale; **canonical signal**
  `signals/2026-06-07/schedule.md` fresh (21:26Z).
- Dated-file branch verified (`schedule/2026-06-05.md`, a past date).
- Daily-schedule skill `letta-code/.scripts/schedule` produces live output.
- Extension diagnostics: 0 errors.

Write-path note (by design): the tool writes `today.md` when `target_date` is
today **or tomorrow** (evening pre-staging); only past/distant dates go to a
dated `schedule/{date}.md`. The skill reads the **canonical signal**
`signals/{today}/schedule.md` (migrated 2026-04-29), not today.md.

## Remaining (non-blocking)
- The tool still PATCHes the **deprecated** memory block
  `block-28c6e49e-…` via `LETTA_BASE_URL` (Docker Letta). The write is wrapped
  in try/except and non-fatal, so it will **not** block Docker decommission
  (it will simply set `memory_error` and continue). Drop it in a follow-up.
- Docker `daily-schedule-agent-sleeptime` is now unused for the briefing and can
  be retired with the rest of the server-tool decommission.
