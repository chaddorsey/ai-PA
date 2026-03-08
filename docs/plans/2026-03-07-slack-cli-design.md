# Slack CLI Design

**Date:** 2026-03-07
**Branch:** slack-cli
**Pattern:** Follows [gws CLI](https://github.com/googleworkspace/cli) architecture and [Rewrite Your CLI for AI Agents](https://justin.poehnelt.com/posts/rewrite-your-cli-for-ai-agents/) principles.

## Overview

A Python CLI wrapping the Slack Web API via `slack_sdk`, designed for AI agent consumption. Consolidates fragmented Slack tooling (MCP server, 4+ Letta tools, analytics scripts) into a single predictable interface.

**Invocation:** `slack <resource> <method> [flags]` for raw API access, `slack <resource> +<helper>` for multi-step convenience commands.

## Architecture

```
slack-cli/
├── pyproject.toml              # Poetry, entry point: slack
├── src/slack_cli/
│   ├── __init__.py
│   ├── main.py                 # Entry point, top-level arg parsing (click)
│   ├── client.py               # Slack SDK wrapper, token resolution, retry
│   ├── auth.py                 # Credential chain (env → config → .env)
│   ├── commands/               # One module per API group
│   │   ├── __init__.py
│   │   ├── conversations.py    # list, info, history, create, archive, ...
│   │   ├── chat.py             # postMessage, update, delete, ...
│   │   ├── users.py            # list, info, lookupByEmail, ...
│   │   ├── reactions.py        # add, remove, get, list
│   │   ├── files.py            # list, upload, info, delete
│   │   ├── search.py           # messages, files
│   │   ├── pins.py             # add, remove, list
│   │   ├── bookmarks.py        # add, edit, remove, list
│   │   ├── reminders.py        # add, complete, delete, info, list
│   │   └── team.py             # info, accessLogs, billableInfo
│   ├── helpers/                # +helper convenience commands
│   │   ├── __init__.py
│   │   ├── chat.py             # +send (resolve channel + post + confirm)
│   │   ├── conversations.py    # +summarize, +find
│   │   └── users.py            # +whois (lookup by name/email)
│   ├── formatter.py            # JSON/table/CSV/YAML output
│   ├── validate.py             # Input sanitization, ID format checks
│   ├── schema.py               # `slack schema <method>` introspection
│   └── error.py                # Structured JSON errors to stdout
├── skills/                     # Auto-generated SKILL.md files
├── tests/
└── README.md
```

**CLI framework:** `click` — mature, explicit control over help text, supports groups/subcommands/nested help.

## Command Pattern

### Raw API Commands
```bash
slack conversations list --params '{"limit": 10, "types": "public_channel"}'
slack chat postMessage --params '{"channel": "C123", "text": "Hello"}'
slack users info --params '{"user": "U123"}' --fields "user(name,real_name,tz)"
```

### +Helper Commands
```bash
slack chat +send --channel general --text "Hello world"
slack users +whois --name "John"
slack conversations +find --name "project-updates"
```

### Utility Commands
```bash
slack schema chat.postMessage
slack auth status
slack auth test
slack generate-skills
```

## Flag Design

### Global Flags (all API commands)

| Flag | Purpose |
|------|---------|
| `--params '{"key":"val"}'` | API parameters as JSON (maps 1:1 to SDK kwargs) |
| `--format json\|table\|csv\|yaml` | Output format (default: `json`) |
| `--fields "id,name,topic"` | Filter response fields |
| `--dry-run` | Show what would be sent without executing |
| `--as-user` / `--as-bot` | Override auto token selection |
| `--page-all` | Auto-paginate through all results |
| `--page-limit N` | Max pages (default: 10) |

### Per-Method Flags
Each command also accepts explicit flags for common parameters:
```bash
# Equivalent:
slack conversations list --limit 10 --types public_channel
slack conversations list --params '{"limit": 10, "types": "public_channel"}'
```
Explicit flags merge into `--params`; explicit wins on conflict.

## Output & Errors

### Output
- JSON to stdout by default, pretty-printed
- Compact JSON (no indentation) when stdout isn't a TTY
- `--format table` renders key fields in aligned columns
- `--fields` filters response before output (reduces agent token cost)
- `--page-all` streams NDJSON (one JSON object per page)

### Errors
```json
// stdout (machine-parseable)
{"ok": false, "error": "channel_not_found", "detail": "Channel 'C999' does not exist"}
```
```
// stderr (human hint)
Hint: Use `slack conversations list` to find valid channel IDs
```

## Authentication

### Credential Chain (first match wins)

| Priority | Source | Token Type |
|----------|--------|------------|
| 1 | `SLACK_CLI_TOKEN` env var | bot (xoxb) |
| 2 | `SLACK_CLI_USER_TOKEN` env var | user (xoxp) |
| 3 | `~/.config/slack-cli/credentials.json` | both |
| 4 | `SLACK_BOT_TOKEN` env var | bot (xoxb) |
| 5 | `SLACK_MCP_XOXP_TOKEN` env var | user (xoxp) |

### Auto Token Selection
Each method is tagged with its required token type (`bot`, `user`, or `either`). The client picks the right token automatically. `--as-user` / `--as-bot` override.

### Auth Subcommands
```bash
slack auth status    # Show configured tokens, scopes, workspace
slack auth test      # Verify tokens via auth.test API
slack auth store     # Save tokens to ~/.config/slack-cli/credentials.json
```

Plain JSON file with `0600` permissions. No encryption needed for home server.

## Input Validation

| Check | Rule | Example Rejection |
|-------|------|-------------------|
| Slack IDs | `^[A-Z][A-Z0-9]{8,12}$` with valid prefixes (C, U, D, G, W, T) | `C123?foo=bar` |
| Control chars | Reject ASCII < 0x20 (except newlines in message text) | `\x00` |
| Embedded query params | Reject `?` and `#` in ID fields | `U123#fragment` |
| Pre-encoded strings | Reject `%` in IDs | `C%20123` |
| Timestamps | Must match `^\d{10}\.\d{6}$` | `not-a-timestamp` |

### --dry-run Output
```json
{
  "method": "chat.postMessage",
  "token_type": "bot",
  "params": {"channel": "C0123ABCD", "text": "Hello world"},
  "url": "https://slack.com/api/chat.postMessage",
  "validation": "passed"
}
```

## Schema Introspection

```bash
$ slack schema chat.postMessage
{
  "method": "chat.postMessage",
  "description": "Sends a message to a channel",
  "token_type": "bot",
  "required": ["channel", "text|blocks|attachments"],
  "parameters": {
    "channel": {"type": "string", "description": "Channel, DM, or group ID"},
    "text": {"type": "string", "description": "Message text (markdown)"},
    "blocks": {"type": "array", "description": "Block Kit blocks"},
    "thread_ts": {"type": "string", "description": "Thread timestamp for replies"},
    ...
  },
  "scopes": ["chat:write"]
}
```

Schema data maintained in a declarative registry alongside each command module.

## Deployment Environments

The CLI runs in **two environments** with identical behavior:

| Environment | Install Method | Token Source | Use Case |
|-------------|---------------|--------------|----------|
| **macOS host** | `pip install ./slack-cli` | `SLACK_BOT_TOKEN` env var | Letta Code agents (bash skills) |
| **Letta Docker** | `pip install /app/tools/slack-cli/` in `entrypoint-wrapper.sh` | `SLACK_BOT_TOKEN` env var | Standard Letta agent tools via `subprocess.run()` |

**Design constraint:** No Docker-specific assumptions. No hardcoded service names or Docker-internal URLs. The CLI only needs a Slack token env var and HTTP access to `https://slack.com/api/`.

## Skill Files (OpenClaw Format)

Skills ship as hand-written SKILL.md files in `skills/` directory, following the [OpenClaw format](https://github.com/googleworkspace/cli/tree/main/skills) used by the gws CLI. These are consumed by Letta Code agents as bash skills.

### Required Skills

| Skill | Directory | Purpose |
|-------|-----------|---------|
| `slack-shared` | `skills/slack-shared/` | CLI syntax, installation, auth, global flags, security rules |
| `slack-channels` | `skills/slack-channels/` | List channels, get info, channel history |
| `slack-messages` | `skills/slack-messages/` | Send messages, reply in threads, read messages, react |
| `slack-search` | `skills/slack-search/` | Search messages with Slack query syntax |
| `slack-users` | `skills/slack-users/` | List users, get user info, lookup by email |
| `slack-files` | `skills/slack-files/` | List/download files |
| `slack-dm` | `skills/slack-dm/` | Send direct messages, list DM conversations |
| `recipe-slack-daily-summary` | `skills/recipe-slack-daily-summary/` | Multi-step: search today's messages, summarize |
| `recipe-slack-thread-export` | `skills/recipe-slack-thread-export/` | Export a thread with all replies |

### Skill Format

Each SKILL.md uses YAML frontmatter + markdown body:

```markdown
---
name: slack-channels
version: 1.0.0
description: "Slack: List channels, get channel info, read channel history."
metadata:
  openclaw:
    category: "productivity"
    requires:
      bins: ["slack"]
    cliHelp: "slack conversations --help"
---

# Slack Channels

> **PREREQUISITE:** Read `../slack-shared/SKILL.md` for auth, global flags, and security rules.

## Common Commands
...

## Discovering Commands
Before calling any API method, inspect it:
```bash
slack conversations --help
slack schema conversations.<method>
```
```

### Design Principles for Skills

1. **Teach patterns, not exhaustive params** — skills show common examples; `slack schema <method>` provides full reference
2. **Document known quirks** — Slack API bugs and gotchas belong in skills, not just code comments
3. **Link to discovery** — every skill points to `slack schema` and `--help` for self-service
4. **Prerequisite chain** — all skills reference `slack-shared` for auth and global flags
5. **Recipes are multi-step** — recipe skills combine multiple CLI calls into a workflow

### Known Slack API Quirks (documented in skills)

- **Search date filtering:** `on:YYYY-MM-DD` works reliably; combining `after:` + `before:` returns 0 results (known Slack bug)
- **Rate limits:** Tier 2/3 methods have different rate limits; CLI surfaces rate-limit events to stderr
- **Pagination:** Always use cursor-based pagination, not offset

## Scope: Core API Groups

Initial coverage (~60-80 methods across these groups):
- `conversations` — list, info, history, create, archive, unarchive, invite, kick, join, leave, open, close, members, rename, setPurpose, setTopic
- `chat` — postMessage, update, delete, postEphemeral, scheduleMessage, unfurl
- `users` — list, info, lookupByEmail, getPresence, setPresence
- `reactions` — add, remove, get, list
- `files` — list, upload, info, delete, completeUploadExternal
- `search` — messages, files
- `pins` — add, remove, list
- `bookmarks` — add, edit, remove, list
- `reminders` — add, complete, delete, info, list
- `team` — info, accessLogs, billableInfo

## Out of Scope

- **Admin analytics** — stays in `slack-analytics-mcp-server` (Playwright-based, Slack plan doesn't support analytics API)
- **Socket Mode / real-time events** — that's the slackbot's domain
- **OAuth flows** — tokens are long-lived, obtained from Slack admin
- **MCP transport** — future enhancement, not part of initial build
- **Encryption at rest** — overkill for home server credential storage

## Letta Integration Path

Once built, the 4 custom Letta tools (`get_slack_channels`, `get_slack_messages`, `search_slack_messages`, `get_slack_users`) plus `send_slack_dm` and `post_slack_channel_reply` can be replaced with a single Letta tool that shells out to `slack <command>`. Future option: expose the CLI as an MCP server (same binary, different transport).
