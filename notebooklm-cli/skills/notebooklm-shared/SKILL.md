---
name: notebooklm-shared
version: 1.0.0
description: "NotebookLM CLI: Shared patterns for installation, auth, global flags, schema discovery, and security rules."
metadata:
  openclaw:
    category: "research"
    requires:
      bins: ["notebooklm-cli"]
---

# notebooklm-cli — Shared Reference

## Installation

### Host (Letta Code on macOS)

```bash
pip install ./notebooklm-cli
```

### Docker (Standard Letta)

Volume-mounted and pip-installed via `entrypoint-wrapper.sh`. Auth cookies are mounted from `~/.notebooklm/` on the host to `/notebooklm-auth/` inside the container.

## Authentication

One-time browser login (requires a display):

```bash
pip install "notebooklm-py[browser]"
playwright install chromium
notebooklm login
```

This creates `~/.notebooklm/storage_state.json` with Google session cookies. Cookies persist for weeks to months. Re-run `notebooklm login` when `notebooklm-cli health` reports an error.

## CLI Syntax

```bash
notebooklm-cli [global-flags] <group> <action> [flags]
```

**Global flags go BEFORE the subcommand:**

| Flag | Description |
|------|-------------|
| `--body '{"key": "val"}'` | JSON input (agent-first path) |
| `--format json\|text` | Output format (default: auto-detect) |
| `--fields id,title,...` | Comma-separated output field mask |
| `--dry-run` | Validate and preview, no execution |
| `--storage PATH` | Path to storage_state.json (overrides default) |

## Schema Discovery

```bash
# List all available methods
notebooklm-cli schema --list

# Inspect a method's parameters, types, and requirements
notebooklm-cli schema notebook.create
```

Always use `schema` to discover parameters before constructing `--body` payloads.

## Input Paths

1. **Agent path (preferred):** `--body '{"title": "My Research"}'`
2. **Human path:** `--title "My Research"` (convenience flags per command)

If both `--body` and convenience flags are provided, `--body` wins.

## Exit Codes

| Code | Meaning | Output |
|------|---------|--------|
| 0 | Success | stdout = JSON |
| 1 | Execution error | stderr has details |
| 2 | Validation error | stdout = JSON with field-level errors |

## Security Rules

- **Always** use `--dry-run` before destructive operations (delete)
- **Confirm** with user before deleting notebooks or sources
- IDs are opaque — never construct, modify, or guess them
- File paths must not contain `..` (path traversal is blocked)

## Workflow Pattern

```
1. notebooklm-cli schema notebook.create          — discover params
2. notebooklm-cli --body '...' --dry-run notebook create  — validate
3. notebooklm-cli --body '...' notebook create             — execute
4. Parse stdout JSON for result
```

## Conversation Lifecycle

`chat ask` returns a `conversationId`. Pass it back for follow-up questions:

```bash
# First question
notebooklm-cli --body '{"notebookId": "nb123", "question": "What is X?"}' chat ask
# Response includes conversationId

# Follow-up
notebooklm-cli --body '{"notebookId": "nb123", "question": "Elaborate?", "conversationId": "conv456"}' chat ask
```

Omitting `conversationId` starts a fresh conversation.

## Artifact Generation Lifecycle

```
1. artifact generate  — returns taskId
2. artifact wait      — poll until complete (use timeout=300 for Letta)
3. artifact download  — save to file
```
