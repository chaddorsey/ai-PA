# Scheduler CLI — Design Options

**Date:** 2026-03-07
**Status:** Decision pending

## Problem

The scheduler service currently requires a dedicated MCP server (`scheduler-mcp`, port 8088) to expose 10 tools to Letta agents. This adds a Docker container, an async HTTP client, Pydantic model translation, and MCP protocol overhead — all to proxy a REST API that's already on the Docker network.

**Current tool inventory (scheduler-mcp):**
1. `scheduler_list_jobs` — list with status/category/creator filters
2. `scheduler_search_jobs` — semantic search on embeddings
3. `scheduler_get_job` — fetch single job by ID
4. `scheduler_create_job` — create (cron, interval, one_off, natural)
5. `scheduler_update_job` — update title/description/status
6. `scheduler_delete_job` — cancel a job
7. `scheduler_archive_job` — archive one or more jobs
8. `scheduler_batch_archive_jobs` — batch archive
9. `scheduler_list_executions` — execution history for a job
10. `scheduler_get_execution` — single execution record

**Scheduler service endpoints (12 total):**

| Method | Path | Purpose |
|--------|------|---------|
| GET | /v1/jobs | List jobs (query params: status_filter, category_filter, created_by_filter, include_archived) |
| GET | /v1/jobs/{job_id} | Get single job |
| POST | /v1/jobs | Create job |
| PATCH | /v1/jobs/{job_id} | Update job |
| DELETE | /v1/jobs/{job_id} | Cancel job |
| GET | /v1/jobs/search | Semantic search (query_text, limit, min_score, status_filter, category_filter) |
| POST | /v1/jobs/batch/archive | Batch archive |
| POST | /v1/jobs/batch/cancel | Batch cancel |
| POST | /v1/jobs/{job_id}/executions | Trigger job immediately |
| GET | /v1/jobs/{job_id}/executions | List executions for job |
| GET | /v1/jobs/executions/{execution_id} | Get single execution |
| GET | /healthz | Health check |

---

## Option A: Full CLI (omnifocus-cli pattern)

Create `scheduler-cli/` with Click CLI, static schema registry, HTTP bridge, validation, field masking. Install via pip in Letta container. Single `run_scheduler` Letta tool.

**Architecture:**
```
scheduler-cli/
  pyproject.toml
  CONTEXT.md
  src/scheduler_cli/
    cli.py          # Click CLI: job, execution, health groups
    bridge.py       # HTTP client to scheduler-service
    schema.py       # 12 schema entries
    fields.py       # Output field masking
    validate.py     # UUID validation
    formatters.py   # JSON/text output
  tests/
```

**Pros:**
- Pattern consistency with omnifocus-cli and (future) gws CLI replacement
- Schema discovery via `scheduler-cli schema --list` / `schema job.create`
- `--dry-run` for safe previewing
- `--fields` for token economy on large job lists
- Human-usable CLI (useful for debugging scheduler issues from terminal)
- Input validation before hitting the service

**Cons:**
- Three layers of indirection: Letta subprocess -> CLI -> HTTP -> scheduler-service
- The bridge is trivially `urllib.request.urlopen()` — no transport detection needed (no local binary equivalent)
- 12 endpoints don't justify the schema registry complexity that omnifocus-cli's 72 methods did
- Adds pip install + volume mount to Letta container
- Subprocess spawn overhead per invocation

**Effort:** 4-6 hours

---

## Option B: Direct Letta Tool (no CLI, no MCP)

Single `run_scheduler` Letta tool that calls the scheduler REST API directly via `urllib.request` from within the Letta sandbox. No CLI binary, no subprocess, no volume mount. Schema lives in the tool docstring.

**Architecture:**
```
letta/
  scheduler_tools.py        # run_scheduler() — direct HTTP calls
  register_scheduler_tools.py
```

**Pros:**
- Simplest approach — fewest moving parts
- No pip install, no volume mount, no subprocess overhead
- Direct HTTP call is faster than subprocess -> CLI -> HTTP
- 12 endpoints fit comfortably in a tool docstring with examples
- Scheduler service already validates input (Pydantic models server-side)
- No new Docker dependencies

**Cons:**
- No standalone CLI for human debugging (would need curl)
- No `--dry-run` (though the service itself validates on write)
- No programmatic schema discovery (agents read the docstring instead)
- No `--fields` output filtering (though scheduler responses are already compact)
- Pattern diverges from omnifocus-cli/gws conventions

**Effort:** 1-2 hours

---

## Option C: Lightweight CLI (thin wrapper, no schema registry)

Minimal CLI that wraps HTTP calls with Click. `scheduler-cli job list`, `scheduler-cli job create --body '{...}'`. No static schema registry (API is small enough). Bridge is just HTTP.

**Architecture:**
```
scheduler-cli/
  pyproject.toml
  src/scheduler_cli/
    cli.py       # Click CLI with --body, --format, --fields
    bridge.py    # HTTP client
  tests/
```

**Pros:**
- Human-usable CLI for debugging
- Consistent subprocess pattern with other tools
- Simpler than Option A (no schema.py, validate.py)

**Cons:**
- Loses the main features that made omnifocus-cli valuable (schema discovery, validation)
- Still has subprocess overhead for no functional gain over Option B
- Inconsistent — neither fully following the pattern nor fully simple

**Effort:** 2-3 hours

---

## Recommendation

**Option B (Direct Letta Tool)** is recommended for this specific case because:

1. **The bridge adds no value.** omnifocus-cli's bridge solves a real problem (macOS AppleScript can't be called from Docker). The scheduler service is already an HTTP API on the Docker network. A CLI wrapping HTTP with HTTP adds latency and complexity.

2. **The API is small.** 12 endpoints vs omnifocus-cli's 72 methods. A docstring with examples is sufficient for agent discovery. Schema discovery is valuable when the API surface is too large to memorize — it's not here.

3. **Server-side validation is sufficient.** The scheduler service has Pydantic models that validate all input. Client-side schema validation would duplicate this.

4. **Field masking is unnecessary.** Scheduler job responses are already compact (~15 fields). Unlike OmniFocus task lists (which can return 20+ fields per item), there's no token savings from filtering.

The `create-cli` skill pattern is the right tool when:
- The underlying service isn't directly callable from Docker (AppleScript, desktop apps)
- The API surface is large enough to justify schema discovery (>30 methods)
- There's a genuine dual-transport need (local vs Docker)

For internal REST APIs with small surfaces, a direct Letta tool is cleaner.

---

## Decision

_Pending user decision._

---

## Regardless of Option Chosen

The scheduler-mcp service (Docker container + separate Python project) would be decommissioned:
- Remove `scheduler-mcp` from docker-compose.yml
- Remove `scheduler-tools` from letta_mcp_config.json
- Detach MCP tools from agents
- Attach new `run_scheduler` tool to relevant agents
- Write rollback document (same pattern as omnifocus-cli-rollback.md)
