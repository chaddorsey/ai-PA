# Slack CLI — Agent Context

## Critical Rules

- **Always use `--fields`** when listing or getting resources to limit response size and token cost
- **Use `--dry-run`** before any mutating operation (delete, archive, postMessage to production channels)
- **Prefer channel IDs** (C0123ABCDEF) over names — IDs are stable, names can change
- **Timestamps** are Slack's `ts` format (e.g., `1234567890.123456`), not Unix epoch integers
- **Search requires a user token** — `search.messages` and `search.files` need SLACK_MCP_XOXP_TOKEN
- **Use `slack schema <method>`** for parameter discovery — don't guess parameter names

## Token Types

| Method Group | Token Type | Notes |
|-------------|------------|-------|
| Most methods | bot (xoxb) | Default for conversations, chat, users, etc. |
| search.* | user (xoxp) | Search requires user token |
| chat.postMessage | either | Works with bot or user token |
| reactions.get/list | either | Works with bot or user token |

## Known Slack API Quirks

- **Search date filtering:** `on:YYYY-MM-DD` works. `after:` + `before:` combined returns 0 results (Slack bug).
- **Rate limits:** Tier 1 (1/min), Tier 2 (20/min), Tier 3 (50/min), Tier 4 (100/min). The CLI surfaces rate-limit events to stderr.
- **Pagination:** Always cursor-based. Use `--page-all` or pass `cursor` in `--body`.
- **Channel names:** Don't include `#`. Use `general`, not `#general`.
- **thread_ts:** The parent message's timestamp, not the reply's.

## Common Patterns

```bash
# Pattern: --body for agents, convenience flags for humans
slack chat postMessage --body '{"channel":"C123","text":"hello"}'
slack chat +send --channel general --text "hello"

# Pattern: schema discovery before API calls
slack schema chat.postMessage  # See all params
slack chat postMessage --body '{"channel":"C0123ABCDEF","text":"hi"}'

# Pattern: dry-run before mutating
slack --dry-run chat delete --body '{"channel":"C123","ts":"1234567890.123456"}'
slack chat delete --body '{"channel":"C123","ts":"1234567890.123456"}'
```
