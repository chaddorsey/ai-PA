---
date_started: 2026-05-30
date_phase_h: 2026-05-30
status: migrated, soaking
agent_old_id: agent-dd15479e-6543-400e-8463-b2a48b13cd4a
agent_old_name_now: XXX-PRE-LOCAL-tasks-agent
agent_new_id: agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4
agent_new_name: tasks-agent-local
model: lmstudio/gpt-5.2
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/tasks-agent/
launcher: ~/bin/letta-tasks
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Tasks migration log

Third per-agent local-mode migration. Same recipe as Docs + Calendar,
plus a pre-migration cycle-1 finishing pass that landed earlier in the
session (see commit 87e6fc1a).

## Cycle-1 prework (committed before migration)

Work Item 1 of the Tasks migration finished the cycle-1 (April 2026)
pg-canonical migration that left the agent with dead-tool and
archival-using residue:

- DELETED: process_spark_queue, update_tasks_section, report_refs
- REWRITTEN: retrieve_task_info, backtrace_task (pg-canonical;
  archival reach stripped)
- Persona patched to reflect cycle-1 flow

After that pass: tool count 18 → 15. All remaining tools are
pg-canonical (no archival/block dependence).

## What migrated

- Agent record (model `gpt-5.2`, letta_v1, message_buffer_autoclear=false)
- 10 system/*.md memfs files (all valid frontmatter; no read_only violations)
- 1 cron repointed: `Pipeline-health: tasks-agent daily self-check`
  (06:30 ET, route=local)
- New file: `system/task_cli_recipes.md` — the local-mode operation
  guide. Maps every retired Letta tool to a `task <verb>` CLI invocation.

## What did NOT migrate

- **767 archival passages** preserved on Docker side (NOT imported).
  Local agent's substrate is pa_web.tasks + canonical, not archival.
- Custom Letta tools: NOT imported. Local agent uses Bash + `task` CLI
  for every pa_web.tasks op.
- Sibling tools that are CLI-replaceable (run_gws, run_slack,
  run_omnifocus): NOT imported. Local agent shells out directly to
  gws, slack, omnifocus on PATH.

## Two-headed runtime state

Docker tasks-agent (renamed XXX-PRE-LOCAL-tasks-agent) retains all
15 attached tools + 767 archival passages. Slackbot's
`SPARK_QUEUE_AGENT_ID` env in docker-compose still points at the
preserved agent_id (which works since rename preserved ID). Currently:

- Slackbot Phase-0 notification → renamed Docker agent gets the
  notification (and may not act on it, since the agent is now
  effectively detached from cron + pa-web-ui sidebar attention)
- Local agent picks up via cron (06:30 ET pipeline-health) + direct
  TUI invocations

This means the slackbot's notification flow currently goes to the
OLD agent (which has its tools but no cron/user attention). The local
agent only sees queue work when explicitly told. **Followup**: update
slackbot's `SPARK_QUEUE_AGENT_ID` to the local agent ID after soak
proves stable — or rewire slackbot to write to a per-source channel
the local agent polls.

For now: any time-sensitive task ingestion still relies on the local
agent being asked to `task queue-claim`. Worth monitoring during soak.

## Sidebar impact

pa-web-ui `/api/tasks` is independent (psycopg2 → pa_web.tasks; no
agent involvement). Verified serving 45+ rows after migration.

Sidebar's `_find_archival_passage` (line ~3230) still queries the
Docker agent's archival memory for "reassemble work packet" feature.
This works because XXX-PRE-LOCAL-tasks-agent retains archival.
**Followup**: post-soak, rewrite that helper to read from pa_web.tasks
instead so the Docker agent can be decommissioned.

## Phase E smoke results

| Test | Time | Result |
|---|---|---|
| E1 identity | 2.7s | ✅ "Tasks Agent, primary substrate pa_web.tasks (accessed via task CLI)" |
| E3 task search via Bash | 4.4s | ✅ Ran `task search --status active --limit 3 --fields ref_id,suggested_title` correctly, reported count=3 with refs |

System prompt size: 73,702 chars (vs 10,837 default — full memfs imported + recompiled).

## Rollback path (within 7-day soak)

1. Revert cron:
   ```bash
   curl -X PATCH http://localhost:8087/v1/jobs/6afa76c3-ba0e-44f8-b960-b5b41316502f \
     -d "@/Volumes/main-filestore/ai-PA-backups/local-mode-migrations/tasks-agent/cron-6afa76c3-*-original.json"
   ```

2. Rename Docker agent back:
   ```bash
   curl -X PATCH http://localhost:8283/v1/agents/agent-dd15479e-6543-400e-8463-b2a48b13cd4a \
     -d '{"name":"tasks-agent"}'
   ```

3. Slackbot notification path is unchanged throughout. Sidebar reads
   pa_web.tasks throughout. Both are independent of the migration.

## Soak validation list

- [ ] Tomorrow's 06:30 ET pipeline-health cron fires + signals
- [ ] Slackbot notification routes correctly (and the local agent
      claims queue rows when prompted)
- [ ] `task queue-claim` against real new sparks lands rows in
      pa_web.tasks with all expected columns populated
- [ ] Sidebar continues serving + reassemble-work-packet works
- [ ] Verify the agent doesn't reach for retired tool names —
      should always invoke `task <verb>` instead
- [ ] Confirm backtrace + packet-write workflow on a user-indicated task
