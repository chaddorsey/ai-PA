---
date: 2026-06-07
purpose: revert the schedule-briefing cron jobs from the local extension path back to the Docker daily-schedule-agent + server tool
risk: low (full pre-flip job snapshot saved; server tool + Docker agent left intact)
related:
  - docs/runbooks/2026-06-07-pulse-cron-extension-flip-rollback.md  # analytics twin
  - docs/plans/2026-06-07-server-tools-definitive-disposition.md
snapshot: docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json
---

# Rollback: schedule-briefing cron flip (Docker server tool → local extension)

On 2026-06-07 the three "Gold-Standard Briefing Update" cron jobs were flipped
off the Docker `daily-schedule-agent-sleeptime`
(`agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2`) onto the local-mode deterministic
extension path: they now target the local agent **calendar-agent_copy-local**
(`agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c`), route `local`, and call
`generate_daily_briefing_ext()` (pinned `~/.letta/pa-tools-venv`) instead of the
server tool `generate_daily_briefing`.

| Job ID | Title | Cron |
|---|---|---|
| `933b620f-9cb1-47f8-b519-7ccedf1603ab` | Weekend - Monday Preview | `0 18 * * 5,6` |
| `f732d44c-50d1-4fd2-88b4-6102cece4fa3` | Off-Hours - Next Day | `0 18,22,2,6 * * 0-5` |
| `a683f7ef-bf03-4a4b-a607-fb52399f43a4` | Gold-Standard (workday) | `*/15 8-17 * * mon-fri` |

## What changed per job
1. `actions[].config.agent_id` → `agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c`
2. `actions[].config.route` → `"local"` (was unset → defaulted to `letta`/Docker)
3. `actions[].config.message`: `generate_daily_briefing` → `generate_daily_briefing_ext`
   and the parameter token `target_date` → `date` (the extension exposes `date`,
   which it maps to the Python `target_date` kwarg). All date-calculation prose
   was preserved.

## Revert (restore the exact pre-flip jobs)

The full pre-flip job records (all fields) are snapshotted. Restore each job's
`actions` array verbatim:

```python
import json, urllib.request
snap = json.load(open("docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json"))
for jid, j in snap.items():
    body = json.dumps({"actions": j["actions"]}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"http://localhost:8087/v1/jobs/{jid}",
        data=body, method="PATCH", headers={"Content-Type": "application/json"}))
    print("reverted", jid)
```

Reverting points the jobs back at the Docker `daily-schedule-agent-sleeptime`
and the server tool `generate_daily_briefing` (both left in place — no
re-registration needed). The Docker Letta server must be running for the
reverted path to work.

## When to revert
- The local extension path regresses (pa-tools venv, `~/.letta/extensions/pa-tools.ts`,
  the local runner on :8920, or gws calendar auth via
  `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`).
- Note: reverting reintroduces the LET-9147 interpreter non-determinism.
  Prefer fixing the extension first (`letta --no-extensions` recovers the TUI;
  check `~/.letta/extensions/diagnostics/latest.json`).

## Dependencies the local path needs (don't break these)
- Local runner on `http://host.docker.internal:8920` (letta-local-runner).
- `~/.letta/pa-tools.env` keys: `GITEA_MEMFS_TOKEN`, `GITEA_BASE_URL` (host),
  `MC_AGENT_ID`, `LETTA_BASE_URL`, **`GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`**
  (= `/Volumes/main-drive/ai-PA/gws-bridge/credentials.json` — gws calendar auth;
  the launchd runner subprocess has no keychain access, so the creds file is
  required).
- Extension `runPinned` prepends host CLI dirs to PATH (`~/bin:/opt/homebrew/bin:/usr/local/bin`)
  so the tool's `gws` subprocess resolves.
