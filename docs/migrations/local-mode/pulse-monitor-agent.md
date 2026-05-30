---
date_started: 2026-05-30
date_phase_h: deferred (see "Why partial" below)
status: shell-migrated (partial); Docker continues producing briefings
agent_old_id: agent-2ed14ef4-6289-453a-ae27-290b6ed196b8
agent_old_name_now: pulse-monitor-agent_copy (UNCHANGED — Docker is primary)
agent_new_id: agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a
agent_new_name: pulse-monitor-agent-local
model: lmstudio/gpt-5.4-nano
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/pulse-monitor-agent_copy/
launcher: ~/bin/letta-pulse
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Pulse migration log — shell-only (partial)

Fourth per-agent local-mode migration. **Intentionally partial** —
the agent shell exists and is fully usable for ad-hoc queries, but
the 6 daily-analytics crons still point at Docker pending the
`pulse-cli` build (see followup
`docs/followups/2026-05-30-pulse-cli-scoping.md`).

## Why partial

Pulse has 20+ bespoke analytics tools (`compose_daily_briefing`,
`collect_daily_workspace_activity`, `calculate_running_averages`,
`analyze_slack_analytics`, etc.) that:

1. Have NO existing CLI counterpart (unlike `task-cli` which wraps
   already-pg-canonical Python).
2. Store running state in **memory blocks** (drive_analytics_*),
   which are deprecated — moving them to local mode requires
   deciding new storage substrate (pa_web tables vs memfs vs
   recompute-on-demand).
3. Drive the 6 daily crons that produce user-visible morning
   briefings. Repointing crons to a local agent that can't actually
   execute the workflows would break daily briefings — a noisy,
   user-visible regression.

The goal language was "fully retaining existing Docker functionality
to ensure ability to roll back". Following that intent: Docker pulse
stays fully active producing briefings; local shell agent is ready
for cron repointing once pulse-cli ships and provides the missing
CLI subcommands.

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

## Two-headed runtime state (deliberate)

**Docker `pulse-monitor-agent_copy`** (unchanged name):
- 34 tools attached
- 6 crons firing M-F (02:00, 02:30, 03:00, 04:00, 06:00, */15 8-6)
- Producing daily analytics briefings
- Memory blocks (drive_analytics_*) maintained
- Archival passages intact

**Local `pulse-monitor-agent-local`** (new):
- 0 attached Letta tools
- Uses Bash + CLIs on host (slack, atlassian, drive-rag-curl,
  slack-extract, signal, task, gws)
- Available for ad-hoc TUI queries (`letta-pulse`)
- Won't take over crons until pulse-cli ships

## Phase E smoke

| Test | Time | Result |
|---|---|---|
| Identity | 2.3s | ✅ Self-identifies as pulse-monitor agent, correctly states partial-migration status |

System prompt size: 65,133 chars (vs the bloated full-import which
would have been ~120K+ with the 9 dated files included).

## Rollback path

Trivially clean — nothing on the Docker side changed:
1. Stop using `letta-pulse`
2. (Optionally) delete the local agent + memfs from
   `~/.letta/lc-local-backend/`

The Docker pulse keeps running through the rollback.

## Soak validation (light — local agent has limited surface)

- [ ] `letta-pulse` opens cleanly, agent recognizes itself
- [ ] Agent correctly REFUSES to attempt briefing composition (per
      its `pulse_local_mode_status.md` guidance) — should surface
      "Docker is still producing official briefings"
- [ ] Ad-hoc queries through CLIs work (slack/atlassian/drive-rag-curl)

## Full migration prerequisites (when pulse-cli ships)

1. Build pulse-cli (~8-12 hrs scope per
   `docs/followups/2026-05-30-pulse-cli-scoping.md`)
2. Decide drive_analytics_* storage substrate (pa_web tables likely)
3. Migrate Docker pulse's memory blocks → new substrate
4. Test pulse-cli end-to-end against a real day's data
5. Repoint the 6 crons (route=local, agent_id=local)
6. Rename Docker pulse → XXX-PRE-LOCAL-pulse-monitor-agent_copy
7. Standard 7-14 day soak watching briefing quality
