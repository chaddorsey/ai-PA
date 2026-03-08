# slack-cli

Agent-first CLI for the Slack Web API, following the [gws CLI](https://github.com/googleworkspace/cli) patterns.

## Installation

```bash
# From source
cd slack-cli && pip install .

# Development
cd slack-cli && poetry install
```

## Quick Start

```bash
# Set up authentication
export SLACK_BOT_TOKEN=xoxb-your-bot-token
export SLACK_MCP_XOXP_TOKEN=xoxp-your-user-token  # optional, for search

# Verify
slack auth status
slack auth test

# List channels
slack conversations list --body '{"types": "public_channel", "limit": 10}'

# Send a message
slack chat +send --channel general --text "Hello from slack-cli"

# Search messages (requires user token)
slack search messages --body '{"query": "on:2026-03-08 standup"}'
```

## Command Reference

| Group | Methods | Description |
|-------|---------|-------------|
| `conversations` | list, info, history, create, archive, +find | Channel management |
| `chat` | postMessage, update, delete, +send | Messaging |
| `users` | list, info, lookupByEmail, +whois | User lookup |
| `reactions` | add, remove, get, list | Emoji reactions |
| `files` | list, upload, info, delete | File management |
| `search` | messages, files | Search (user token) |
| `pins` | add, remove, list | Pinned messages |
| `bookmarks` | add, edit, remove, list | Channel bookmarks |
| `reminders` | add, complete, delete, info, list | Reminders |
| `team` | info, accessLogs, billableInfo | Team info |
| `auth` | status, test, store | Authentication |
| `schema` | (introspection) | API schema discovery |

## Usage Patterns

### Agent-first (--body)
```bash
slack chat postMessage --body '{"channel": "C0123ABCDEF", "text": "Hello"}'
```

### Human-friendly (flags)
```bash
slack chat +send --channel general --text "Hello"
```

### Schema discovery
```bash
slack schema                        # List groups
slack schema --group conversations  # List methods
slack schema chat.postMessage       # Method details
```

### Output control
```bash
slack conversations list --format table
slack users list --fields "ok,members" --body '{"limit": 5}'
slack conversations list --page-all --page-limit 3
```

## Deployment

### macOS host (Letta Code)
```bash
pip install ./slack-cli
export SLACK_BOT_TOKEN=xoxb-...
slack auth test
```

### Docker (standard Letta)
```yaml
# docker-compose.yml
letta:
  volumes:
    - ./slack-cli:/app/tools/slack-cli:ro
```
```bash
# entrypoint-wrapper.sh
pip install /app/tools/slack-cli/
```

## Testing

```bash
cd slack-cli
poetry run pytest                    # Unit tests
poetry run pytest -m integration     # Integration tests (needs tokens)
poetry run pytest --cov              # With coverage
```

## Skills

OpenClaw SKILL.md files for agent consumption are in `skills/`:
- `slack-shared` — Auth, flags, security
- `slack-channels` — Channel operations
- `slack-messages` — Messaging
- `slack-search` — Search with quirk docs
- `slack-users` — User lookup
- `slack-files` — File management
- `slack-dm` — Direct messages
- `recipe-slack-daily-summary` — Daily summary workflow
- `recipe-slack-thread-export` — Thread export workflow
