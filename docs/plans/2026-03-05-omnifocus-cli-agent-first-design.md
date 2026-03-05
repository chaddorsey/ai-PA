# OmniFocus CLI v1 — Agent-First Redesign

**Date:** 2026-03-05
**Status:** Design approved — redesign of v0 based on gws CLI agent-first principles
**Prior art:** [gws CLI](https://github.com/googleworkspace/cli), blog post by Justin Poehnelt (2026-03-04)
**Supersedes:** `2026-03-04-omnifocus-cli-design.md` (v0 flag-based design)

## Goal

Redesign the OmniFocus CLI so the **primary interface is agent-first**: raw JSON payloads, schema introspection, input hardening, dry-run, and field masks. Human convenience flags are secondary sugar. The CLI is the lowest-friction, most predictable interface for Letta agents to reach OmniFocus.

## Design Principles (from gws CLI)

1. **Raw JSON payloads > bespoke flags** — `--body '{...}'` maps directly to plugin method params
2. **Schema introspection replaces documentation** — `omnifocus-cli schema task.create` returns machine-readable parameter definitions
3. **Input hardening against hallucinations** — validate all inputs before osascript execution
4. **Context window discipline** — `--fields` limits output to save agent tokens
5. **Dry-run for mutations** — `--dry-run` validates + previews without executing
6. **Ship agent context** — `CONTEXT.md` encodes invariants agents can't intuit

## Architecture

```
Letta Tool (Python, subprocess.run)
  → omnifocus-cli (Python/Click, host-installed)
    → validate (schema check, input hardening)
      → osascript (only if validation passes)
        → OmniFocus plugin (omnifocus-mcp.omnijs)
          → OmniFocus database
```

Validation is a gate before osascript — hallucinated inputs never reach OmniFocus.

## Core Interface

### Agent Path (primary)

```bash
# Raw JSON body maps directly to plugin method params
omnifocus-cli task create --body '{"name": "Buy milk", "projectId": "abc-123", "flagged": true}'

# Dry-run: validate + preview, no execution
omnifocus-cli task create --body '{"name": "Buy milk"}' --dry-run

# Field masks: limit output tokens
omnifocus-cli task list --body '{"projectId": "abc"}' --fields id,name,flagged,dueDate

# Schema discovery
omnifocus-cli schema task.create
omnifocus-cli schema --list
```

### Human Path (sugar)

```bash
# Convenience flags produce the same plugin call
omnifocus-cli task create --name "Buy milk" --project abc-123 --flag
```

When both `--body` and convenience flags are provided, `--body` wins (flags are ignored with a warning).

## Global Flags

| Flag | Purpose | Default |
|------|---------|---------|
| `--body '{...}'` | Raw JSON input — the agent-first path | — |
| `--dry-run` | Validate against schema + preview payload, no execution | off |
| `--fields f1,f2,...` | Limit output fields (context window discipline) | all fields |
| `--format json\|text` | Output format | `json` if stdout is not a TTY, `text` if TTY |

## Command Groups (unchanged from v0)

| Command Group | Actions |
|---------------|---------|
| `task` | create, get, update, complete, list |
| `search` | (single command with filters) |
| `project` | list, get, create, update, folders |
| `inbox` | list, process |
| `tags` | list, create, rename, delete |

## Schema Introspection

Static registry in `schema.py` — a Python dict mapping `<group>.<action>` to method metadata.

### `omnifocus-cli schema <method>`

```bash
$ omnifocus-cli schema task.create
{
  "method": "createTask",
  "description": "Create a new task in OmniFocus",
  "params": {
    "name":             {"type": "string",        "required": true,  "description": "Task name"},
    "projectId":        {"type": "string",        "required": false, "description": "Project UUID to assign task to"},
    "note":             {"type": "string",        "required": false, "description": "Task notes/description"},
    "flagged":          {"type": "boolean",       "required": false, "description": "Whether task is flagged"},
    "dueDate":          {"type": "string",        "required": false, "description": "Due date in ISO 8601 format"},
    "deferDate":        {"type": "string",        "required": false, "description": "Defer/start date in ISO 8601 format"},
    "plannedDate":      {"type": "string",        "required": false, "description": "Planned date (Forecast view)"},
    "estimatedMinutes": {"type": "integer",       "required": false, "description": "Estimated duration in minutes"},
    "tagIds":           {"type": "array[string]", "required": false, "description": "Tag UUIDs to assign"}
  }
}
```

### `omnifocus-cli schema --list`

```
task.create    task.get    task.update    task.complete    task.list
search
project.list   project.get   project.create   project.update   project.folders
inbox.list     inbox.process
tags.list      tags.create   tags.rename   tags.delete
```

## Input Hardening

All validation runs before osascript. Validation errors return structured JSON to stderr with exit code 2.

### Validation Rules

| Input Type | Rules |
|------------|-------|
| **JSON body** | Parse JSON, validate against schema: reject unknown fields, type mismatches, missing required fields |
| **UUIDs** (taskId, projectId, tagId, folderId) | Reject `?`, `#`, `%`, `..`, control chars (< 0x20, 0x7F), whitespace |
| **Dates** | Validate ISO 8601 format before passing to plugin |
| **Names/titles** | Reject only control characters (< 0x20, 0x7F). Slashes, hyphens, dashes, unicode all allowed |
| **`--fields`** | Validate against known output fields for the method |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Execution error (osascript/plugin failure) |
| 2 | Validation error (bad input, schema mismatch) |

### Example Validation Error

```bash
$ omnifocus-cli task create --body '{"name": "Test", "flagged": "yes", "bogusField": 1}'
# stderr:
{
  "error": "validation_failed",
  "errors": [
    {"field": "flagged", "error": "expected boolean, got string"},
    {"field": "bogusField", "error": "unknown field"}
  ]
}
# exit code: 2
```

## Dry Run

`--dry-run` = schema validation + payload preview. No osascript call.

```bash
$ omnifocus-cli task create --body '{"name": "Test"}' --dry-run
{
  "dry_run": true,
  "method": "createTask",
  "params": {"name": "Test"},
  "validation": "passed"
}
# exit code: 0

$ omnifocus-cli task create --body '{"flagged": "yes"}' --dry-run
{
  "dry_run": true,
  "method": "createTask",
  "params": {"flagged": "yes"},
  "validation_errors": [
    {"field": "name", "error": "required field missing"},
    {"field": "flagged", "error": "expected boolean, got string"}
  ]
}
# exit code: 2
```

## Field Masks

`--fields` filters output JSON keys. Applied after plugin response, before output.

```bash
$ omnifocus-cli task list --body '{"projectId": "abc"}' --fields id,name,flagged
[
  {"id": "t-1", "name": "Buy milk", "flagged": true},
  {"id": "t-2", "name": "Write report", "flagged": false}
]
```

Unknown field names produce a warning to stderr but don't fail (the plugin may return fields not in our known list).

## CONTEXT.md (Agent Guidance)

Shipped in the CLI repo root. Intended for injection into agent system prompts.

Key invariants:
- Use `omnifocus-cli schema <method>` to discover parameters before constructing payloads
- Always pass `--fields` on list/search operations to limit token usage
- Use `--dry-run` before any create/update/complete operation
- UUIDs are opaque strings — never construct, modify, or guess them
- Dates must be ISO 8601 format (e.g., `2026-03-10`, `2026-03-10T17:00:00Z`)
- `--body` accepts the full parameter set for any command as JSON
- Prefer `--body` over convenience flags for predictable behavior

## Letta Tool Simplification

Each tool reduces to ~15 lines — just action + `--body` JSON:

```python
def omnifocus_task(action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage OmniFocus tasks. Run omnifocus-cli schema task.<action> to discover params.

    Args:
        action: One of: create, get, update, complete, list (REQUIRED)
        params: JSON string with parameters. Use schema to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json, subprocess, traceback
    try:
        cli_args = ["omnifocus-cli", "task", action]
        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])
        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}
        return {"status": "ok", "result": json.loads(result.stdout)}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

## Project Layout

```
omnifocus-cli/
├── pyproject.toml
├── CONTEXT.md                # Agent guidance (system prompt injection)
├── src/
│   └── omnifocus_cli/
│       ├── __init__.py
│       ├── cli.py            # Click commands (--body + convenience flags)
│       ├── bridge.py         # osascript execution + base64 encoding
│       ├── schema.py         # Static schema registry + introspection command
│       ├── validate.py       # Input hardening (UUIDs, dates, names, JSON body)
│       ├── fields.py         # Field mask filtering
│       └── formatters.py     # Output formatting (auto-detect TTY)
├── tests/
│   └── ...
└── letta_tools/
    ├── omnifocus_task.py
    ├── omnifocus_search.py
    ├── omnifocus_project.py
    ├── omnifocus_inbox.py
    └── omnifocus_tags.py
```

## What Changes from v0

| Component | v0 | v1 (agent-first) |
|-----------|----|----|
| Primary input | Convenience flags | `--body` JSON |
| Schema discovery | None | `omnifocus-cli schema` command |
| Input validation | None (plugin errors) | Pre-osascript validation |
| Dry run | None | `--dry-run` flag |
| Field masks | None (full output) | `--fields` flag |
| Output default | Text (human) | JSON when not TTY |
| Agent context | Letta docstrings only | CONTEXT.md + docstrings |
| Letta tools | ~60 lines each (flag building) | ~15 lines each (JSON passthrough) |

## What's NOT Changing

- Bridge module (osascript + base64)
- Plugin (`omnifocus-mcp.omnijs`)
- Command groups (task, search, project, inbox, tags)
- 5 Letta tools (same count, simplified internals)
- Excluded MCP tools and OmniFocus feature gaps (see v0 design doc)

## Relationship to v0

The v0 implementation in the `feature/omnifocus-cli` branch has working bridge, formatters, and command structure. The v1 redesign:
- **Keeps**: bridge.py, project scaffold, test structure, integration tests
- **Rewrites**: cli.py (add `--body`, `--dry-run`, `--fields`), formatters.py (auto-detect TTY)
- **Adds**: schema.py, validate.py, fields.py, CONTEXT.md
- **Simplifies**: all 5 letta_tools files
