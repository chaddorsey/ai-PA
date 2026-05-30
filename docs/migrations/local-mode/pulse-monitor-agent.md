---
date_started: 2026-05-30
date_phase_h: 2026-05-30
status: migrated, soaking
agent_old_id: agent-2ed14ef4-6289-453a-ae27-290b6ed196b8
agent_old_name_now: XXX-PRE-LOCAL-pulse-monitor-agent_copy
agent_new_id: agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a
agent_new_name: pulse-monitor-agent-local
model: lmstudio/gpt-5.4-nano
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/pulse-monitor-agent_copy/
launcher: ~/bin/letta-pulse
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Pulse migration log

Fourth per-agent local-mode migration. Completed in two passes within
the same session:

1. **Shell migration**: agent record + memfs imported, no cron repoint
2. **Full migration (this turn)**: extracted 21 bespoke pulse tools
   from Letta, built `pulse-cli` wrapping them (Option-1 pattern),
   updated memfs with `pulse_cli_recipes.md`, repointed all 6 crons,
   renamed Docker pulse

## pulse-cli (built this turn)

21 bespoke pulse tools extracted from Letta to `letta/pulse-tools/`
(3,659 lines total). Wrapped in `pulse-cli/src/pulse_cli/cli.py` with
Click subcommands. Same Option-1 pattern as task-cli:

- One implementation, two interfaces (Letta tool registration retained
  on Docker pulse for rollback; local agent calls `pulse <verb>` via Bash)
- Bug fixes land in one place
- Post-soak relocation: `letta/pulse-tools/` → `pulse-cli/src/pulse_cli/lib/`

CLI subcommands:
- `pulse compose-briefing` — morning briefing
- `pulse snapshot` — daily quantitative snapshot
- `pulse slack-trigger/download/analyze` — Slack CSV pipeline
- `pulse drive-workspace/personal/mentions` — Drive analytics collectors
- `pulse drive-averages/summary/trends/mentions-read` — stored-state readers
- `pulse drive-files/info/top/my-activity/recent/doc-events/activity-search` — Drive queries
- `pulse email-analytics` — email summary
- `pulse init-drive-memory` — first-time setup
- `pulse health` — connectivity probe

Installed via pipx; `pulse` on PATH.

## Storage substrate (transitional)

The wrapped Python in `letta/pulse-tools/` currently reads/writes
Letta memory blocks (drive_analytics_*) via the Letta API. **Memory
blocks are deprecated** but functional during transition. Docker pulse
maintains the blocks; local pulse reads via the CLI.

**Substrate migration follow-up** queued in
`docs/followups/2026-05-30-pulse-cli-scoping.md`: move
drive_analytics_* state from blocks → `analytics.*` pg-schema tables.
~3-4 hrs of post-soak work. Done discretely so the agent's interface
doesn't change.

## What migrated

- Agent record (model `gpt-5.4-nano`, letta_v1, message_buffer_autoclear=false)
- 20 system/*.md memfs files (post-cleanup, see next section)
- Local-mode patched `canonical_reference_protocol.md` (ported from
  calendar-agent)
- New file: `system/pulse_local_mode_status.md` — describes the
  partial-migration shape so the agent knows what it can and can't do

## Pre-import cleanup (Item C — system/ bloat)

Docker pulse's memfs had **31 system files** including:
- 9 dated `daily_vibe_check_*.md` files (stale snapshots from
  March-April 2026)
- `temp_mpdm_list.md` (ephemeral work artifact)
- `coordination_gathered_*.md` (ad-hoc context gathering)

These were getting projected into every turn's context — a real
token-bloat hit. During import, the 11 ephemeral files were moved
from `system/` to `digest/` (out of pinned context). Local agent
import has **20 system files** instead of 31.

Original locations preserved in
`/Volumes/main-filestore/ai-PA-backups/.../memfs-extract/system/`
for rollback.

## What did NOT migrate

- **12 archival passages** preserved on Docker side (NOT imported).
  Most pulse "knowledge" lives in system/* memfs files; archival
  surface is smaller than initially expected.
- All 34 Letta tools: NOT detached from Docker pulse (Docker remains
  fully tooled for ongoing briefing production).
- Cron jobs: NOT repointed (all 6 still target Docker agent ID).

## Two-headed runtime state (rollback preservation)

**Docker `XXX-PRE-LOCAL-pulse-monitor-agent_copy`** (renamed):
- 34 tools attached — preserved untouched for rollback
- 0 crons firing — all 6 repointed to local agent
- Memory blocks maintained (drive_analytics_*) — local CLI reads them
  during the transitional substrate window
- Archival passages intact

**Local `pulse-monitor-agent-local`** (new, ACTIVE):
- 0 attached Letta tools
- Uses Bash + CLIs on host: `pulse` (this migration), `slack`,
  `slack-extract`, `atlassian`, `drive-rag-curl`, `signal`, `task`, `gws`
- All 6 daily crons now target this agent (route=local)
- `letta-pulse` wrapper at `~/bin/letta-pulse`

## Phase E smoke

| Test | Time | Result |
|---|---|---|
| Identity (shell pass) | 2.3s | ✅ Self-identifies as pulse-monitor agent |
| Identity (post-pulse-cli) | 2.4s | ✅ Names `pulse` CLI and `pulse compose-briefing` correctly |

## Rollback path

Docker pulse retains all 34 tools + memory blocks. To roll back:

1. **Repoint the 6 crons back** (loop over the backup files):
   ```bash
   PULSE_OLD=agent-2ed14ef4-6289-453a-ae27-290b6ed196b8
   for f in /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/pulse-monitor-agent_copy/cron-*-original.json; do
     JOB=$(basename "$f" | sed 's/cron-//;s/-original.json//')
     curl -X PATCH http://localhost:8087/v1/jobs/$JOB -d "@$f"
   done
   ```

2. **Rename Docker agent back**:
   ```bash
   curl -X PATCH http://localhost:8283/v1/agents/$PULSE_OLD \
     -d '{"name":"pulse-monitor-agent_copy"}'
   ```

3. Local agent + memfs can be left alone (don't delete; useful for re-engaging if Docker has issues).

## Soak validation list

- [ ] Mon 02:00 ET Slack CSV trigger fires — agent invokes `pulse slack-trigger`
- [ ] Mon 02:30 ET Quantitative snapshot — `pulse snapshot` lands in pa_web
- [ ] Mon 03:00 ET Slack vibe-check completes
- [ ] Mon 04:00 ET Snapshot re-collection (T+2) re-runs cleanly
- [ ] Mon 06:00 ET Compose morning briefing produces canonical signal
      with the same shape as Docker pulse's prior briefings
- [ ] */15 8-6 ET intra-day mentions refresh updates state
- [ ] Side-by-side compare 3-5 daily briefings (local vs prior Docker
      output retained in canonical) for format/quality regression

## Storage substrate follow-up (post-soak)

The wrapped Python in `letta/pulse-tools/` reads/writes Letta memory
blocks (drive_analytics_*). Memory blocks are deprecated and slated
for removal. Substrate migration plan in
`docs/followups/2026-05-30-pulse-cli-scoping.md`:

- New `analytics.drive_workspace_daily`, `analytics.drive_mentions`,
  `analytics.drive_personal_daily` pg-schema tables
- Backfill from existing memory block contents
- Refactor `letta/pulse-tools/*.py` to use pg in place of blocks
- Once Docker pulse is decommissioned, the blocks themselves can be
  deleted

This is internal to the CLI; the agent interface (`pulse <verb>`)
doesn't change.
