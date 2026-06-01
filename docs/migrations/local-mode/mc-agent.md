---
date_started: 2026-06-01
date_phase_h: 2026-06-01
status: migrated, soaking
agent_old_id: agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
agent_old_name_now: XXX-PRE-LOCAL-Mission-Control
agent_new_id: agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d
agent_new_name: Mission Control (local)
model: lmstudio/gpt-5.4-nano
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-snapshots/snapshot_20260601_005756
launcher: ~/bin/letta-mc
launch_cwd: /Volumes/main-drive/letta-launchpad
plan: docs/plans/2026-05-31-mc-migration-plan.md
---

# Mission Control migration log

Sixth and final per-agent local-mode migration. Largest of the set:
26 attached Letta tools (vs 5 for email, 13 for others), 12 system/
memfs files, and an upstream gateway (LettaBot) that had to be
decommissioned in a separate Block C before the migration could land.

## What migrated

- Agent record (`Mission Control (local)`, model
  `lmstudio/gpt-5.4-nano`)
- 12 system/*.md memfs files imported from the Docker MC Gitea memfs
  repo via `curl + raw content` walk
- Local-mode-patched `canonical_reference_protocol.md` (replaced with
  email-agent's already-patched version — adds env-checking pattern,
  people lookup recipe, and "do the lookup yourself" anti-delegation
  guidance)
- New: `system/mc_cli_recipes.md` — maps each retired Letta tool to a
  host CLI invocation; explicit "deleted, delegate to Tasks agent"
  callouts for the 6 tasks-substrate tools per Block A decision

## mc-cli (built this turn)

4 bespoke MC-only tools extracted from Letta to `letta/mc-tools/`:

| Tool | LOC | Wrapped as |
|---|---|---|
| `execute_on_laptop` | ~50 | `mc laptop "<cmd>" [--applescript]` |
| `manage_widget_queue` | ~75 | `mc widget <action> [--task-ids X] [--position N]` |
| `stage_resource` | ~300 | `mc stage --url X --label Y [--priority P] [--ref-id R]` |
| `search_github_stars` | ~210 | `mc github [--query Q] [--repo R] [--readme] [--limit N] [--cursor C]` |

Wrapped in `mc-cli/src/mc_cli/cli.py` (Click), installed via pipx as
`mc` binary. `mc health` probes import + env health.

## Tools NOT extracted (per Block A decisions)

- `run_slack`, `run_omnifocus`, `run_gws`, `run_twitter` — replaced by
  direct calls to canonical CLIs already on PATH (`slack`, `omnifocus`,
  `gws`, `twitter-cli`)
- `emit_canonical_signal`, `read_recent_signals` — `signal` CLI
- `granola_*` (5 tools) — existing `granola` CLI binary on PATH +
  MCP supergateway both stay available
- `refresh_plate`, `write_packet_info`, `backtrace_task`,
  `fetch_source_content`, `search_agent_archival`,
  `trigger_task_extraction` — REMOVED entirely. MC delegates to Tasks
  agent via harness Task/Agent (per `send_message_to_agent_*`
  deprecation 2026-04-28)

## Switchover scope (Block B + E)

Direct callers of Docker MC were rewired in Block B before Block D
landed:

| Caller | Before | After |
|---|---|---|
| **LettaBot** (Telegram + others) | Sole upstream | RETIRED 2026-06-01 (see `lettabot-retired-2026-06-01.md`) |
| **scheduler-service Pipeline-health daily cron** | `LETTABOT_AGENTS` registry → LettaBot URL | PAUSED + replaced by host-side Bash watchdog `scripts/check-mc-pipeline-health.sh` |
| **task-completion-service** | Direct `POST /v1/agents/{MC}/messages` | `pa_web.task_queue` write with `source='mc-completion'`; MC claims via `task queue-claim --source mc-completion` |
| **pa-web-ui** | Subprocess pool against Docker MC agent_id | UNCHANGED — pa-web-ui continues to spawn `letta-code` subprocesses against the Docker agent_id, which still resolves (Docker MC is renamed but the agent_id is preserved). Two-headed pattern, same as other 5 agents. |

## What did NOT migrate

- **26 attached Letta tools on Docker side** — NOT detached; preserved
  for rollback. The local MC has zero attached Letta tools (uses Bash
  + CLI exclusively).
- **MC's archival memory** — preserved on Docker side. Not used in
  routine local-mode ops; recipe documents fallback to canonical for
  signals-style memory.
- **MC's Docker-side identity** — preserved at agent-90b2e860; renamed
  to `XXX-PRE-LOCAL-Mission-Control`.

## Two-headed runtime state

**Docker `XXX-PRE-LOCAL-Mission-Control`** (renamed):
- 26 tools attached — preserved for rollback
- Still receives traffic from pa-web-ui (subprocess pool spawns
  against this agent_id via `LETTA_BASE_URL`)
- Archival intact; memfs Gitea repo still active (Schedule agent
  continues pushing to it)
- Reachable via `pa-web-ui` UI or direct Letta API

**Local `Mission Control (local)`** (new, primary for TUI use):
- 0 attached Letta tools
- Uses Bash + `mc` + `granola` + `slack` + `gws` + `omnifocus` +
  `signal` + `task` + `drive-rag-curl` + `atlassian` CLIs
- Reachable via `~/bin/letta-mc`
- Receives task-completion events via `pa_web.task_queue` (claims via
  `task queue-claim --source mc-completion`)
- Receives no LettaBot traffic (channel retired)

## Phase H+I smoke

| Test | Time | Result |
|---|---|---|
| Identity + date awareness | ~3s | ✅ "I'm Letta Code's Mission Control (local-mode) agent, and today is Monday, June 1, 2026." |
| Canonical signal emission via Bash + signal CLI | ~4s | ✅ Signal landed at `signals/2026-06-01/mc-local-mode-smoke.md` (mc-* prefix correct) |
| `mc laptop "hostname"` via Bash | ~5s | ✅ Returned `CC-TN2WDG94P2-2051.local` (SSH-over-Tailscale working) |

## Rollback path

1. Rename Docker MC back:
   ```bash
   curl -X PATCH http://localhost:8283/v1/agents/agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef \
     -H 'Content-Type: application/json' \
     -d '{"name":"Mission Control"}'
   ```
2. Revert Block C (LettaBot retirement) per
   `docs/migrations/local-mode/lettabot-retired-2026-06-01.md`'s rollback recipe.
3. Revert Block B `task-completion-service` rewire — git revert
   `e53f4f33`; restart task-completion-service.
4. Re-enable scheduler-service Pipeline-health cron:
   ```bash
   curl -X PATCH "http://localhost:8087/v1/jobs/3cbdccfd-045d-4362-abc3-71bd5f2858d2" \
     -H 'Content-Type: application/json' \
     -d '{"status":"scheduled"}'
   ```
5. Unload MC pipeline-health watchdog plist if no longer wanted.

## Soak validation

- [ ] `letta-mc` TUI launches cleanly, agent self-identifies as Mission
      Control (local) and reads today's date correctly
- [ ] `mc health` reports all 4 tools importable; `GITHUB_TOKEN`
      warning is OK (only needed for `mc github`)
- [ ] Daily 06:30 ET `check-mc-pipeline-health.sh` continues to fire
      via launchd; canonical signal lands at expected path
- [ ] task-completion-service writes successfully to pa_web.task_queue
      on a real task completion (verify via `psql` after completing
      an OmniFocus task with a timer)
- [ ] MC claims task-completion events via `task queue-claim
      --source mc-completion` and acts on them (e.g., archives,
      annotates, or surfaces)
- [ ] pa-web-ui MC conversation still works (subprocess pool against
      Docker agent_id continues to function)
- [ ] No new LettaBot-related errors anywhere
- [ ] Slack delegation pattern: MC delegates tasks-substrate work to
      Tasks agent via harness Task/Agent (no errors about missing
      `refresh_plate` etc.)

Soak window: 1-2 weeks (longer than other agents because MC's blast
radius is bigger — fleet orchestration, scheduler health, completion
notifications).

Post-soak cleanup:
- Detach the 26 Letta tools from Docker MC (cleanup, not required)
- Delete Docker MC agent entirely (after rollback window expires)
- Remove dead LettaBot fallback path in pa-web-ui/app.py:2393-2416
