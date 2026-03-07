# OmniFocus CLI — Agent Context

## Quick Start

```bash
# Discover available methods and their parameters
omnifocus-cli schema --list
omnifocus-cli schema task.create

# Create a task (agent path)
omnifocus-cli task create --body '{"name": "Buy milk", "flagged": true}'

# Dry-run before mutating
omnifocus-cli task create --body '{"name": "Buy milk"}' --dry-run

# Limit output tokens
omnifocus-cli task list --fields id,name,flagged
```

## Invariants

- Use `omnifocus-cli schema <method>` to discover parameters before constructing payloads
- Always pass `--fields` on list/search operations to limit token usage
- Use `--dry-run` before any create/update/complete operation
- UUIDs are opaque strings — never construct, modify, or guess them
- Dates must be ISO 8601 format (e.g., `2026-03-10`, `2026-03-10T17:00:00Z`)
- `--body` accepts the full parameter set for any command as JSON
- Prefer `--body` over convenience flags for predictable behavior
- Global flags (`--body`, `--dry-run`, `--fields`, `--format`) go BEFORE the subcommand

## Error Handling

- Exit 0: Success — parse stdout as JSON
- Exit 1: Execution error — osascript/OmniFocus failure, stderr has details
- Exit 2: Validation error — stdout has structured JSON with field-level errors

## Command Groups

| Group | Actions |
|-------|---------|
| task | create, get, update, complete, delete, move, list, subtasks, add-subtask, hierarchy, flatten |
| search | (single command with filters) |
| project | list, get, create, update, complete, move, convert |
| folder | list, get, create, delete, tree |
| inbox | list, process, context, bulk |
| tags | list, get, create, rename, delete |
| schema | (introspection: `schema <method>` or `schema --list`) |

## Workflow Pattern

1. `omnifocus-cli schema task.create` — discover params
2. `omnifocus-cli --body '{"name":"..."}' --dry-run task create` — validate
3. `omnifocus-cli --body '{"name":"..."}' task create` — execute
4. Parse stdout JSON for result
