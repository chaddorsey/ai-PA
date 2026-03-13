# Twitter CLI Integration Design

**Date:** 2026-03-12
**Status:** Approved
**Approach:** Fork-and-Adapt (Approach A)

## Summary

Vendor `jackwener/twitter-cli` into `twitter-cli/` as a Poetry package, replacing curator-radar's hand-rolled `TwitterClient` with twitter-cli's robust auth/TLS fingerprinting layer. Simultaneously expose a `run_twitter` Letta tool following the progressive disclosure pattern for agent access to Twitter.

## Goals

1. **Reliability** — Replace fragile hand-rolled GraphQL client with `curl_cffi` TLS fingerprinting (Chrome impersonation), eliminating bot detection failures
2. **Agent access** — Give Letta agents read + curated write access to Twitter via `run_twitter` tool
3. **List curation** — Support reading user timelines and managing lists, the primary agent use cases
4. **Conversation parsing** — Enable reading tweet replies as flat lists or threaded trees for summarization

## Non-Goals

- Posting tweets, retweeting, or replying (agent cannot tweet as user)
- Browser cookie extraction (`browser_cookie3`) — Smaug cookies are sufficient
- Skills/recipes layer — deferred until foundation is solid

## Architecture

### Package Structure

```
twitter-cli/
├── pyproject.toml              # Poetry, deps: curl_cffi, click
├── src/
│   └── twitter_cli/
│       ├── __init__.py
│       ├── client.py           # Core session: curl_cffi, TLS fingerprint, cookie mgmt
│       ├── auth.py             # Cookie loading from Smaug path + refresh logic
│       ├── graphql.py          # GraphQL query definitions
│       ├── models.py           # Tweet, User, Thread data classes
│       ├── cli.py              # Click CLI entry point
│       └── formatters.py       # JSON/human output formatting
└── skills/                     # Future skill recipes
```

### Auth Flow

- `auth.py` reads cookies from Smaug config at `settings.smaug_config_path` (container path: `/app/smaug-config/smaug.config.json`)
- Expected JSON structure: `{"twitter": {"authToken": "...", "ct0": "..."}}`
- `client.py` creates a `curl_cffi` session with Chrome TLS fingerprint, injects cookies plus the public web-client bearer token
- Single cookie source serves both curator-radar batch calls and agent CLI calls

### CLI Surface

```
twitter-cli read feed [--count N] [--json]
twitter-cli read user <handle> [--count N] [--json]
twitter-cli read bookmarks [--count N] [--json]
twitter-cli read search <query> [--count N] [--json]
twitter-cli read list <list-id> [--json]
twitter-cli read tweet <tweet-id> [--json]           # Focal tweet + flat replies
twitter-cli read thread <tweet-id> [--depth N] [--json]  # Replies as tree

twitter-cli write bookmark <tweet-id>
twitter-cli write list-add <list-id> <handle>
twitter-cli write list-remove <list-id> <handle>

twitter-cli schema                    # List all commands
twitter-cli schema <command>          # Details for a specific command
```

### Letta Tool — `run_twitter`

Progressive disclosure pattern matching `run_slack`/`run_gws`/`query_curator_radar`:

```python
COMMANDS = {
    "read feed":               "Your home timeline",
    "read user <handle>":      "A user's recent tweets and retweets",
    "read bookmarks":          "Your bookmarked tweets",
    "read search <query>":     "Search tweets",
    "read list <list-id>":     "Members and recent tweets from a list",
    "read tweet <tweet-id>":   "A tweet and its replies (flat)",
    "read thread <tweet-id>":  "A tweet and reply tree (nested)",
    "write bookmark <id>":     "Bookmark a tweet",
    "write list-add <list-id> <handle>":    "Add user to a list",
    "write list-remove <list-id> <handle>": "Remove user from a list",
    "schema":                  "List all available commands",
}
```

Agent calls `run_twitter(command="schema")` to discover, then `run_twitter(command="read user elonmusk", params='{"count": 10}')`. Tool calls curator-radar's HTTP API and returns parsed JSON.

### Thread/Reply Support

twitter-cli's existing `TweetDetail` GraphQL endpoint fetches a tweet plus replies via `threaded_conversation_with_injections_v2`. Current gap: replies come back flat.

**Additions needed:**
- Extend `Tweet` model with `in_reply_to_id`, `conversation_id`, `depth` fields
- Update parser to reconstruct parent-child links from Twitter's response format
- `read tweet` returns flat list (fast, good for agent summarization)
- `read thread` reconstructs tree with configurable depth (good for conversation structure)

## Curator-Radar Migration

### Method Mapping

| Current `TwitterClient` method | New source | Status |
|---|---|---|
| `get_retweeters(tweet_id)` | `twitter_cli.client` | Port existing — gets TLS fingerprinting |
| `get_user_rest_id(screen_name)` | `twitter_cli.client` | Port existing |
| `add_list_member(list_id, user_id)` | `twitter_cli.client` | Port existing |
| `remove_list_member(list_id, user_id)` | `twitter_cli.client` | Port existing |
| `create_list(name, description)` | `twitter_cli.client` | Port existing |

**New implementations** (not in current TwitterClient):

| Method | Purpose |
|---|---|
| `get_list_members(list_id)` | Read list membership — needed for `read list` CLI command |
| `get_bookmarks()` | Fetch bookmarks via API — needed for `read bookmarks` CLI command (note: Smaug ingest still uses file-based `bookmarks.md`, this is for agent access) |
| `get_user_tweets(handle)` | User timeline — needed for `read user` CLI command |
| `search_tweets(query)` | Search — needed for `read search` CLI command |
| `get_home_timeline()` | Home feed — needed for `read feed` CLI command |
| `get_tweet_detail(tweet_id)` | Tweet + replies — exists in upstream twitter-cli, port over |
| `add_bookmark(tweet_id)` | Bookmark a tweet — needed for `write bookmark` CLI command |

### What Changes

- `curator_radar/twitter_client.py` — deleted, replaced by `twitter_cli.client.TwitterClient`
- `twitter_backfill.py`, `twitter_list_sync.py`, `routes.py` — update imports to `from twitter_cli.client import TwitterClient`
- **Async-to-sync transition**: The new `twitter_cli` client uses `curl_cffi` which is synchronous. Curator-radar callers (`twitter_backfill.py`, `twitter_list_sync.py`) currently `await` async methods — these calls change to sync. Use `asyncio.to_thread()` in the async route handlers if blocking is a concern, or accept the simplification since these are background tasks that don't need concurrency within a single request.
- `Dockerfile` — adds `COPY twitter-cli/ /app/twitter-cli/` and `pip install /app/twitter-cli`
- Cookie path — unchanged, `twitter_cli.auth` reads from Smaug config at `settings.smaug_config_path`

### What Doesn't Change

- `twitter_ingest.py` — still reads from Smaug's `bookmarks.md` file
- Scoring algorithm (`scoring.py`) — untouched
- DB models — untouched
- Existing routes — untouched (new agent-access routes are added separately)
- Scheduler jobs — untouched (same HTTP endpoints)

## Container & Deployment

### Curator-Radar Container
- `twitter-cli/` copied into curator-radar container
- `curator-radar/Dockerfile`: `COPY twitter-cli/ /app/twitter-cli/` + `pip install /app/twitter-cli`
- Smaug cookie volume mount stays as-is
- No new scheduler jobs — existing `twitter/run` pipeline uses the same HTTP routes

### Letta Tool Execution
The `run_twitter` Letta tool calls curator-radar's HTTP API (adding new pass-through routes) rather than shelling out to the CLI directly. Rationale:
- `curl_cffi` has native C dependencies that won't compile in the Letta sandbox venv
- The CLI needs access to Smaug cookies which are only mounted in the curator-radar container
- This matches the existing `query_curator_radar` tool pattern (HTTP to `http://curator-radar:5145/v1/...`)

New curator-radar routes for agent access:
- `GET /v1/twitter/feed` — home timeline
- `GET /v1/twitter/user/{handle}` — user tweets
- `GET /v1/twitter/search` — search tweets
- `GET /v1/twitter/tweet/{id}` — tweet + flat replies
- `GET /v1/twitter/thread/{id}` — tweet + threaded replies
- `POST /v1/twitter/bookmark/{id}` — bookmark a tweet

The `run_twitter` tool uses `urllib.request` to call these routes, same as `query_curator_radar`.

### Dependencies

| Package | Purpose |
|---|---|
| `curl_cffi` | TLS fingerprinting — the key value-add |
| `click` | CLI framework (matches slack-cli, omnifocus-cli) |

## Future Extensions (Not In Scope)

- **Skills/recipes** — SKILL.md-based agent recipes (like Slack CLI's pulse report)
- **Posting/replying** — Agent tweeting requires human-in-the-loop gate
- **Browser cookie extraction** — `browser_cookie3` if Smaug cookies become unreliable
