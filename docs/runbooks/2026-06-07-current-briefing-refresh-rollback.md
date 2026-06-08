---
date: 2026-06-07
status: active
system: current-briefing-materialized-view
related:
  - docs/plans/2026-06-07-current-briefing-materialized-view-plan.md
  - docs/plans/2026-06-07-schedule-briefing-local-migration.md
---

# Rollback runbook: current-briefing-refresh materialized-view system

## Overview

The materialized-view system replaces three Docker-scheduler agent_message cron
jobs with a host-native pipeline:

1. **Refresher** (`com.ai-pa.current-briefing-refresh`, every 15 min, 06:00–23:00
   ET) — runs `letta/daily_briefing/refresh_current.py` in the pinned venv
   (`~/.letta/pa-tools-venv`), calls `generate_daily_briefing`, and writes the
   date-less cell `signals/current/schedule.md` in the agents-canonical Gitea repo.
2. **Reader** (`letta-code/.scripts/schedule`) — reads `signals/current/schedule.md`
   via the Gitea API (no Letta agent involved).
3. **Bash watchdog** (`com.ai-pa.current-briefing-monitor`, every 30 min, 06:00–23:00
   ET) — runs `scripts/check-current-briefing-fresh.sh`; writes a canonical signal
   `signals/<date>/schedule-refresh-health.md` with `attention_level: elevated` if
   the cell is stale (age > 40 min during daytime).
4. **Three Docker crons paused** — the old agent_message crons in the scheduler
   service (`http://localhost:8087`) have status `paused` and are not executing.

---

## Steps to roll back

### 1. Stop the host launchd jobs

```bash
launchctl unload ~/Library/LaunchAgents/com.ai-pa.current-briefing-refresh.plist
launchctl unload ~/Library/LaunchAgents/com.ai-pa.current-briefing-monitor.plist
```

Verify they are gone:
```bash
launchctl list | grep current-briefing   # expect no output
```

### 2. Re-enable the three Docker scheduler crons

The three paused jobs send `agent_message` requests to the local calendar agent
(`calendar-agent_copy-local`) asking it to call `generate_daily_briefing_ext`.

```python
import json, urllib.request

JOB_IDS = [
    "933b620f-9cb1-47f8-b519-7ccedf1603ab",  # Weekend - Monday Preview
    "f732d44c-50d1-4fd2-88b4-6102cece4fa3",  # Off-Hours - Next Day
    "a683f7ef-bf03-4a4b-a607-fb52399f43a4",  # Gold-Standard (workday)
]

for jid in JOB_IDS:
    req = urllib.request.Request(
        f"http://localhost:8087/v1/jobs/{jid}",
        data=json.dumps({"status": "scheduled"}).encode(),
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    print(jid[:8], resp.status)
```

If you also need to restore the full action configs (agent_id, route, message body,
etc.), the pre-flip snapshot is at:
`docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json`

### 3. Revert the reader

The `letta-code/.scripts/schedule` script was repointed from the dated canonical
signal (`signals/<date>/schedule.md`) to the current cell
(`signals/current/schedule.md`) in commit `abdbe0c` of the letta-code repo.

The letta-code repo is a separate git repo at `/Volumes/main-drive/ai-PA/letta-code`.
To revert:

```bash
cd /Volumes/main-drive/ai-PA/letta-code
git revert abdbe0c
# or if you want a hard reset:
git checkout abdbe0c^ -- .scripts/schedule
git commit -m "revert: restore schedule reader to dated-signal path"
```

---

## Dependencies the refresh path needs

If the refresher breaks and you're debugging rather than rolling back, check these:

| Dependency | Where it lives | What it does |
|---|---|---|
| `~/.letta/pa-tools.env` | Host file | Provides env vars to launchd jobs. Must contain: `GITEA_MEMFS_TOKEN`, `GITEA_BASE_URL`, `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`, `MC_AGENT_ID` |
| `~/.letta/pa-tools-venv` | Host venv | Pinned Python interpreter used for all refresh scripts. Must have `pytz`, `requests` (or urllib-only), and `letta/daily_briefing` importable via PYTHONPATH |
| `gws` calendar CLI | `~/bin/gws` or `/opt/homebrew/bin/gws` | Called by `generate_daily_briefing` to fetch calendar events. Requires `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` set (launchd doesn't inherit Keychain). |
| agents-canonical Gitea repo | `GITEA_BASE_URL/agents/agents-canonical` | Where `signals/current/schedule.md` lives. Must be reachable from the host. |
| `letta/daily_briefing/generate_daily_briefing.py` | `/Volumes/main-drive/ai-PA/letta/daily_briefing/` | The pure renderer (no Letta agent). Imported as `daily_briefing.generate_daily_briefing` with `PYTHONPATH` including `/Volumes/main-drive/ai-PA/letta`. |
| `letta/daily_briefing/refresh-current-briefing.sh` | `/Volumes/main-drive/ai-PA/letta/daily_briefing/` | Shell wrapper that sources `pa-tools.env`, sets PYTHONPATH, and runs `refresh_current.py`. Contains its own hour-guard (no separate Python guard). |

To test the refresh path manually:

```bash
set -a && . ~/.letta/pa-tools.env && set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONPATH="/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta"
~/.letta/pa-tools-venv/bin/python -m daily_briefing.refresh_current
```

---

## Watchdog details

**Script**: `scripts/check-current-briefing-fresh.sh`
**State file**: `logs/health/check-current-briefing-fresh.state` (tracks last alert)
**Signal written on staleness**: `signals/<date>/schedule-refresh-health.md`
  with `attention_level: elevated` and message describing the stale age.

The watchdog exits 0 on fresh, 1 on stale (and writes the signal). The launchd
job (`com.ai-pa.current-briefing-monitor`) runs every 30 min and is suppressed
outside 06:00–23:00 ET by the script's own daytime guard.

---

## Implementation note (deviation from original plan)

The original plan (Task 7 of the materialized-view plan) proposed a Python-based
Docker scheduler monitor job. The deployed implementation uses a pure-bash host
launchd watchdog (`scripts/check-current-briefing-fresh.sh` +
`com.ai-pa.current-briefing-monitor.plist`) to match the existing convention
established by `check-mc-pipeline-health.sh`. This keeps monitoring fully
host-native and avoids a Docker scheduler dependency for the health path.
