# OmniFocus CLI — Design Document

**Date:** 2026-03-04
**Status:** WIP — Experimental replacement for OmniFocus MCP server

## Goal

Replace the OmniFocus MCP server with a lightweight Python CLI that Letta agents call via subprocess. Eliminates MCP protocol overhead, Express server, Docker container, and host-bridge HTTP service.

## Architecture

```
Letta Tool (Python, subprocess.run)
  → omnifocus-cli (Python/Click, host-installed)
    → osascript
      → OmniFocus plugin (omnifocus-mcp.omnijs)
        → OmniFocus database
```

**Eliminated layers:** MCP SDK, Express server (port 8888), Docker container, host-bridge HTTP service (port 8889), Docker networking hops.

## CLI Scope (v0 Experiment)

### Included — 5 Letta Tools

| Letta Tool | CLI Command Group | Operations |
|------------|-------------------|------------|
| `omnifocus_task` | `omnifocus-cli task` | create, get, update (flag/defer/duration/due/tags/notes/planned-date), complete, list |
| `omnifocus_search` | `omnifocus-cli search` | text search, filter by due range, defer range, flagged, tag, project, status, available |
| `omnifocus_project` | `omnifocus-cli project` | list, get, list-folders, projects-in-folder |
| `omnifocus_inbox` | `omnifocus-cli inbox` | list, process (move to project, assign tags) |
| `omnifocus_tags` | `omnifocus-cli tags` | list, create, rename, delete |

### Output

- Human-readable by default
- `--json` flag for structured JSON output (always used by Letta tools)
- Errors to stderr, exit code 1 with JSON error body

## Excluded MCP Tools — Recovery Tracking

These MCP tools are intentionally excluded from v0. This section tracks them for selective recovery later.

### Priority 2 — Likely Needed Eventually

| MCP Tool | What It Does | Recovery Notes |
|----------|-------------|----------------|
| `taskHierarchy` | Create subtasks, flatten groups, move branches | Add as `omnifocus-cli task subtask`, `task flatten`, `task move-branch` |
| `projectOperations` (create/update/move) | Full project CRUD | v0 has read-only projects. Add create/update as `project create`, `project update` |
| `projectSettings` | Sequential/parallel, completion behavior | Add as `project settings` subcommand |
| `folderOperations` (create/delete) | Folder CRUD | v0 has read-only folders via project tool. Add `folder create`, `folder delete` |
| `folderNavigation` | Full tree view, validate moves | Add as `project tree` or `folder tree` |
| `taskGroupOperations` | Sequential/parallel task groups | Add as `task group-type` subcommand |

### Priority 3 — Nice to Have

| MCP Tool | What It Does | Recovery Notes |
|----------|-------------|----------------|
| `bulkInboxProcessing` | Batch inbox operations | Add as `inbox process-bulk` with JSON input |
| `reviewOperations` | List projects needing review, mark reviewed | Add as `review list`, `review mark` |
| `perspectiveOperations` | List/switch perspectives | Add as `perspective list`, `perspective switch` |
| `analyticsInsights` | Project health, workload, trends | Add as `analytics` command group |
| `automationSupport` | Suggestions, diagnostics, cleanup | Add as `system diagnose`, `system cleanup` |

### Priority 4 — Likely Not Needed for CLI

| MCP Tool | What It Does | Why Excluded |
|----------|-------------|--------------|
| `validationOperations` | Pre-validate moves/creates | CLI can validate inline; no need for separate tool |
| `transactionOperations` | Begin/execute/accept/rollback batches | Complex stateful pattern; handle errors per-call instead |
| `systemOperations` | Health check | Only useful for MCP server monitoring |
| `tasksHelp` | Help text for LLM | CLI has `--help`; Letta tools have docstrings |

### Quick-Access Tools (Absorbed)

| MCP Tool | Where It Went |
|----------|---------------|
| `markCompleted` | `omnifocus-cli task complete <id>` |
| `listUncompletedTasks` | `omnifocus-cli task list` + `omnifocus-cli search --available` |
| `listProjects` | `omnifocus-cli project list` |
| `moveTaskToProject` | `omnifocus-cli task update <id> --project <id>` |

## OmniFocus Features — Intentional Gaps

Beyond MCP tool coverage, these OmniFocus capabilities are not addressed in v0:

| Feature | Description | Recovery Path |
|---------|-------------|---------------|
| **Repetition rules** | Recurring task configuration (daily/weekly/monthly, from-completion) | Add `--repeat` flag to `task create`/`task update` with structured syntax |
| **Project creation** | Creating new projects (only listing/reading in v0) | Add `project create` command |
| **Project status changes** | Setting active/on-hold/completed/dropped | Add `project update --status` |
| **Nested tags** | Parent-child tag hierarchies | Add `--parent` flag to `tags create` |
| **Planned dates** | "When do you plan to work on this" (Forecast view) | Add `--planned-date` to task update (**Note: already in scope above — verify plugin support**) |
| **Drop/delete tasks** | Dropping or deleting tasks (only complete in v0) | Add `task drop`, `task delete` |
| **Attachment handling** | File attachments on tasks | Not practical via CLI; skip |
| **Notification rules** | Custom notification settings per task | OmniFocus handles natively; skip |
| **Detail levels** | minimal/standard/full output verbosity | Add `--detail` flag if output is too verbose |
| **Sort orders** | freshness/default sorting | Add `--sort` flag |
| **Completion state filters** | Include completed/dropped in lists | Add `--include-completed`, `--include-dropped` flags |

## Technical Decisions

- **Python + Click** — matches Letta ecosystem, clean CLI framework
- **Reuses existing omnifocus-mcp.omnijs plugin** — no OmniFocus-side changes needed
- **Host-installed** (not Docker) — needs direct osascript access
- **Base64 JSON payloads** — same encoding as current bridge to avoid AppleScript escaping issues
- **No caching in CLI** — plugin handles its own 3-level caching

## Project Layout

```
omnifocus-cli/
├── pyproject.toml
├── src/
│   └── omnifocus_cli/
│       ├── __init__.py
│       ├── cli.py          # Click command definitions
│       ├── bridge.py       # osascript execution + JSON encoding
│       └── formatters.py   # Human-readable output formatting
├── tests/
│   └── ...
└── letta_tools/
    ├── omnifocus_task.py
    ├── omnifocus_search.py
    ├── omnifocus_project.py
    ├── omnifocus_inbox.py
    └── omnifocus_tags.py
```
