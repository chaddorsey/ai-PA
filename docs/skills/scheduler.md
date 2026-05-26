---
description: scheduler-service job-management skill. Replaces the 7 scheduler-mcp tools with Bash + the `scheduler` CLI.
applies-to: any local-mode agent that needs to inspect or modify scheduled jobs
replaces:
  - scheduler_list_jobs
  - scheduler_search_jobs
  - scheduler_get_job
  - scheduler_update_job
  - scheduler_delete_job
  - scheduler_archive_job
  - scheduler_list_executions
cli: scripts/scheduler
---

# Scheduler Skill

## When to use

- **Inspect** what's scheduled (list/search/get/executions)
- **Modify** an existing job (pause, resume, retitle, archive, delete)
- **Trigger** a job to run right now (e.g., for testing)

This skill does NOT include `scheduler create` — agents can manage
existing jobs but not spawn new ones. Same safety boundary as the
legacy scheduler-mcp surface.

## Prerequisites

`SCHEDULER_BASE_URL` defaults to `http://localhost:8087` on the host
(or `http://scheduler-service:8087` from the Docker network). No API
key is required by default; if `SCHEDULER_API_KEY` is set in env, it's
sent as `Authorization: Bearer <key>`.

## List jobs

```bash
scheduler list \
  [--status <scheduled|paused|cancelled|completed|active>] \
  [--category <cat>] \
  [--created-by <user>] \
  [--include-archived] \
  [--limit <n>] \
  [--format <json|table>]
```

Examples:

```bash
# All currently scheduled jobs (table format)
scheduler list --status scheduled --format table | head

# Jobs created by a specific agent
scheduler list --created-by tasks-agent --format table

# Including archived
scheduler list --status active --include-archived
```

## Search jobs

```bash
scheduler search "<query>" [--limit <n>]
```

Semantic search over title + description. Returns matched jobs with
similarity scores.

```bash
scheduler search "morning briefing"
scheduler search "drive rag" --limit 5
```

## Get one job's full record

```bash
scheduler get <job-id>
```

Returns the full job JSON: schedule type/expression, next_run_at,
actions, metadata, status, etc.

## Update a job

```bash
scheduler update <job-id> \
  [--title <text>] \
  [--description <text>] \
  [--status <scheduled|paused|cancelled>]
```

At least one of `--title`/`--description`/`--status` is required.
Common uses:

```bash
# Pause a job
scheduler update <job-id> --status paused

# Resume
scheduler update <job-id> --status scheduled

# Retitle
scheduler update <job-id> --title "Drive RAG Sync (every 10 min)"
```

## Delete (cancel) a job

```bash
scheduler delete <job-id>
```

Marks the job `cancelled` and removes it from the active scheduler.
Job record is retained (with status=cancelled) for audit.

## Archive jobs

```bash
scheduler archive <job-id> [<job-id>...]
```

Bulk archive. Archived jobs are hidden from default listings;
include with `scheduler list --include-archived`.

## List executions for a job

```bash
scheduler executions <job-id> [--limit <n>] [--format <json|table>]
```

```bash
scheduler executions 72368a59-fbb0-49f7-98c6-3ae94ab07682 --limit 5 --format table
# 2026-05-26T02:50:00Z  succeeded  2026-05-26T02:50:01Z
# 2026-05-26T02:40:00Z  succeeded  2026-05-26T02:40:02Z
# ...
```

Useful for diagnosing flaky crons: a quick `scheduler executions <id>
--format table | head -20` shows the last N runs and their outcomes.

## Trigger a job immediately

```bash
scheduler trigger <job-id>
```

Creates an immediate execution outside the normal schedule. The job's
normal next_run_at is unaffected. Useful for testing or manual
re-runs.

## Migration notes

When migrating an agent that uses the legacy `scheduler_*` tools:

1. **Detach** the 7 legacy scheduler-mcp tools from the local-mode
   agent (they don't exist in local mode anyway).
2. **Confirm** `scripts/scheduler` is on the agent's `$PATH` (symlinked
   to `/opt/homebrew/bin/scheduler` for the runner).
3. **Update protocols** — anywhere the agent's system protocols
   reference `scheduler_list_jobs(...)` etc., replace with `scheduler
   list ...` recipes. Mapping is 1:1:

| Legacy MCP tool | Skill equivalent |
|---|---|
| `scheduler_list_jobs(...)` | `scheduler list [opts]` |
| `scheduler_search_jobs(query)` | `scheduler search "<query>"` |
| `scheduler_get_job(job_id)` | `scheduler get <job-id>` |
| `scheduler_update_job(job_id, ...)` | `scheduler update <job-id> [opts]` |
| `scheduler_delete_job(job_id)` | `scheduler delete <job-id>` |
| `scheduler_archive_job(job_id, ...)` | `scheduler archive <id> [<id>...]` |
| `scheduler_list_executions(job_id)` | `scheduler executions <job-id>` |

## Failure modes

- **`ERROR (404): ...`** — job not found. Verify the job_id.
- **`ERROR (422): ...`** — request validation failure. Check that
  your `--status` value is in the allowed set, or that an `update`
  call has at least one field.
- **scheduler-service unreachable** — check `docker ps | grep
  scheduler-service`; `SCHEDULER_BASE_URL` env var must match.
- **Search returns empty** — no jobs match the query above the default
  min_score threshold. Try simpler / broader query terms.

## Validation history

- **2026-05-25** — CLI shipped + smoke-tested against live
  scheduler-service. All 7 operations verified:
  - `list --status scheduled --limit 3 --format table` → 39 jobs
  - `search "drive rag"` → matched "Drive RAG Changes API Sync"
  - `get <id>` → full record JSON
  - `executions <id> --format table` → table of last N runs
  - update/delete/archive paths constructed (not exercised against
    production jobs for safety)
