# NotebookLM CLI — Agent Context

## Quick Start

```bash
# Discover available methods and their parameters
notebooklm-cli schema --list
notebooklm-cli schema notebook.create

# Create a notebook (agent path)
notebooklm-cli --body '{"title": "Research Project"}' notebook create

# Dry-run before mutating
notebooklm-cli --body '{"title": "Test"}' --dry-run notebook create

# Limit output tokens
notebooklm-cli --fields id,title notebook list
```

## Invariants

- Use `notebooklm-cli schema <method>` to discover parameters before constructing payloads
- Always pass `--fields` on list operations to limit token usage
- Use `--dry-run` before any create/update/delete operation
- IDs are opaque strings — never construct, modify, or guess them
- `--body` accepts the full parameter set for any command as JSON
- Prefer `--body` over convenience flags for predictable behavior
- Global flags (`--body`, `--dry-run`, `--fields`, `--format`, `--storage`) go BEFORE the subcommand

## Error Handling

- Exit 0: Success — parse stdout as JSON
- Exit 1: Execution error — API/auth failure, stderr has details
- Exit 2: Validation error — stdout has structured JSON with field-level errors

## Command Groups

| Group | Actions |
|-------|---------|
| notebook | create, list, get, delete, rename, describe, topics |
| source | add-url, add-text, add-file, add-youtube, add-drive, list, get, delete, rename, refresh, guide, fulltext |
| artifact | generate, list, get, delete, rename, download, status, wait |
| chat | ask, history, clear, save |
| research | start, poll, import |
| note | create, list, update, delete |
| health | (top-level command) |
| schema | (introspection: `schema <method>` or `schema --list`) |

## Workflow Pattern

1. `notebooklm-cli schema notebook.create` — discover params
2. `notebooklm-cli --body '{"title":"..."}' --dry-run notebook create` — validate
3. `notebooklm-cli --body '{"title":"..."}' notebook create` — execute
4. Parse stdout JSON for result

## Conversation Lifecycle

`chat ask` returns a `conversationId` in its response. Pass it back for follow-ups:

```bash
# First question — returns conversationId
notebooklm-cli --body '{"notebookId": "nb123", "question": "What is X?"}' chat ask

# Follow-up — pass conversationId for context continuity
notebooklm-cli --body '{"notebookId": "nb123", "question": "Elaborate?", "conversationId": "conv456"}' chat ask
```

Omitting `conversationId` starts a fresh conversation.

## Artifact Generation Pattern

```bash
# 1. Generate (returns taskId)
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio"}' artifact generate

# 2. Wait for completion (use timeout=300 for Letta)
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "task789"}' artifact wait

# 3. Download
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio", "outputPath": "./out.mp3"}' artifact download
```

## Research Pattern

```bash
# 1. Start research
notebooklm-cli --body '{"notebookId": "nb123", "query": "topic", "source": "web"}' research start

# 2. Poll for results
notebooklm-cli --body '{"notebookId": "nb123"}' research poll

# 3. Import discovered sources
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "rtask321", "sources": [...]}' research import
```
