# Slack CLI — Agent Context

> **PREREQUISITE:** Read `skills/slack-shared/SKILL.md` for installation, authentication, and global flags.

## Critical Rules

- **Always use `--fields`** on list/get calls to limit response size and token cost
- **Always use `--dry-run`** before any mutating operation (delete, archive, kick)
- **Always confirm with user** before executing write/delete commands
- **Use `slack schema <method>`** to discover parameters — don't guess
- **Prefer channel IDs** (C0123ABCDEF) over names — IDs are stable, names change
- **Timestamps** are Slack's `ts` format (e.g., `1234567890.123456`), not Unix epoch integers
- **Search requires a user token** — `search.messages` and `search.files` need `--as-user`

## Workflow: Schema First, Then Execute

```
1. slack schema <method>           # Discover parameters
2. slack <resource> <method> --dry-run --body '...'  # Validate
3. slack <resource> <method> --body '...' --fields "..."  # Execute with field mask
```

If you don't know the exact parameters for a method, run `slack schema <method>` first.
If you don't know which method to use, run `slack schema --group <resource>` to see all methods.

## Token Types

| Method Group | Token Type | Notes |
|-------------|------------|-------|
| Most methods | bot (xoxb) | Default for conversations, chat, users, etc. |
| search.* | user (xoxp) | Search requires user token — use `--as-user` |
| chat.postMessage | either | Works with bot or user token |
| reactions.get/list | either | Works with bot or user token |

## Field Masks for Context Window Protection

Always pass `--fields` to limit response data:

```bash
# BAD: returns full channel objects with all metadata
slack conversations list --body '{"limit":100}'

# GOOD: returns only the fields you need
slack conversations list --body '{"limit":100}' --fields "id,name,topic"
```

Common field patterns:
- Channels: `"id,name,topic,purpose,num_members"`
- Messages: `"ts,text,user,thread_ts,reply_count"`
- Users: `"id,name,real_name,profile.email"`

## Known Slack API Quirks

- **Search date filtering:** `on:YYYY-MM-DD` works. `after:` + `before:` combined returns 0 results (Slack bug).
- **Rate limits:** Tier 1 (1/min), Tier 2 (20/min), Tier 3 (50/min), Tier 4 (100/min). The CLI surfaces rate-limit events to stderr.
- **Pagination:** Always cursor-based. Use `--page-all` or pass `cursor` in `--body`.
- **Channel names:** Don't include `#`. Use `general`, not `#general`.
- **thread_ts:** The parent message's timestamp, not the reply's.
- **Ephemeral messages:** Cannot be updated or deleted after sending.

## Error Format

Errors are always JSON on stdout:
```json
{"ok": false, "error": "channel_not_found", "detail": "Channel 'C999' does not exist"}
```

Exit codes: 0 (success), 1 (execution error), 2 (validation error).

## Common Patterns

```bash
# Agent-first path: --body with JSON parameters
slack chat postMessage --body '{"channel":"C123","text":"hello"}'

# Human-friendly path: helper commands with named flags
slack chat +send --channel general --text "hello"

# Schema discovery before API calls
slack schema chat.postMessage
slack schema --group conversations

# Dry-run before mutating
slack chat delete --dry-run --body '{"channel":"C123","ts":"1234567890.123456"}'

# Pagination
slack conversations list --body '{"limit":200}' --page-all --fields "id,name"
```
