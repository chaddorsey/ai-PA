# Twitter Curator Discovery — Design

## Goal

Identify Twitter users who consistently like the same tweets you bookmark. Rank them by signal quality and auto-manage a private Twitter List of top curators for easy browsing.

## Architecture

Extends the existing Curator Radar service (port 5145) with a Twitter platform module. Reads bookmarked tweet IDs from Smaug's output files, fetches likers via Twitter's GraphQL Favoriters endpoint, scores overlap using the same IDF-weighted algorithm as GitHub, and syncs a private Twitter List with top curators daily.

No new Docker containers. No bird CLI dependency — direct GraphQL calls using Smaug's existing auth cookies.

## Data Flow

```
Smaug (launchd, every 6h)
  → fetches new bookmarks via bird CLI
  → writes to smaug-data/.state/ and bookmarks.md

Curator Radar Twitter module (scheduler-service, daily)
  → reads Smaug output for new tweet IDs
  → inserts into BookmarkedTweet table
  → fetches likers per tweet (Favoriters GraphQL endpoint)
  → stores in TweetLiker table
  → rescores Twitter curators (IDF-weighted overlap)
  → syncs top-N curators to a private Twitter List
  → weekly: generates digest section alongside GitHub curators
```

## Data Model

### New Tables

**`BookmarkedTweet`** — tweets you've bookmarked (mirrors `StarredRepo`)

| Column | Type | Notes |
|--------|------|-------|
| `tweet_id` | str, PK | Twitter status ID |
| `author_handle` | str | Tweet author's handle |
| `author_name` | str | Display name |
| `text` | str | Tweet text (truncated) |
| `tweet_url` | str | Full URL |
| `bookmarked_at` | datetime | When the tweet was created (proxy for bookmark time) |
| `likers_fetched` | bool | False until Favoriters endpoint has been called |

**`TweetLiker`** — users who liked your bookmarked tweets (mirrors `RepoStargazer`)

| Column | Type | Notes |
|--------|------|-------|
| `tweet_id` | str, compound PK | FK to BookmarkedTweet |
| `user_handle` | str, compound PK | Liker's Twitter handle |
| `user_name` | str | Display name |
| `fetched_at` | datetime | When we fetched this liker |

**`TwitterList`** — auto-managed curator list

| Column | Type | Notes |
|--------|------|-------|
| `list_id` | str, PK | Twitter list ID |
| `list_name` | str | List name (e.g., "Curator Radar") |
| `last_synced_at` | datetime | Last sync time |

**`TwitterListMember`** — current list membership

| Column | Type | Notes |
|--------|------|-------|
| `list_id` | str, compound PK | FK to TwitterList |
| `user_handle` | str, compound PK | Member handle |
| `added_at` | datetime | When added to list |
| `removed_at` | datetime, nullable | When removed (null = active) |

### Modified Tables

**`Curator`** — add platform discrimination

- Add `platform` column: `"github"` (default) or `"twitter"`
- Change unique constraint from `user_login` to `(user_login, platform)`
- Existing GitHub rows unaffected (default value covers migration)

## Twitter Client

**`twitter_client.py`** — lightweight async HTTP client for Twitter's GraphQL API.

- **Auth:** Reads `auth_token` and `ct0` from Smaug's config file at `/Volumes/main-drive/ai-PA/smaug/smaug.config.json`. No duplicate credential storage.
- **Favoriters endpoint:** POST to `https://x.com/i/api/graphql/{queryId}/Favoriters` with tweet ID as variable. Returns paginated list of users who liked the tweet.
- **List management:** `ListAddMember`, `ListRemoveMember`, `CreateList` GraphQL mutations for Twitter List sync.
- **Rate limiting:** Adaptive delays starting at 2 seconds between calls. Exponential backoff on 429 responses. No artificial per-run cap — rate limiter is the governor. First runs will establish baseline for likers-per-tweet volume and API tolerance, allowing tuning from observed data.

## Bookmark Ingestion

On each run, the service reads Smaug's state file (`smaug-data/.state/bookmarks-state.json`) to find tweet IDs not yet in the `BookmarkedTweet` table. Inserts new bookmarks with `likers_fetched = false`. No dependency on Smaug's schedule — just reads its output files.

## Likers Fetch & Backfill

1. Query `BookmarkedTweet WHERE likers_fetched = false ORDER BY bookmarked_at DESC` (newest first — higher-signal recent bookmarks get processed before older ones)
2. For each tweet, call Favoriters endpoint, paginate fully to get all likers
3. Upsert likers into `TweetLiker`
4. Mark `likers_fetched = true`
5. Resumable — if interrupted, unfetched tweets remain in queue

Initial backfill works through 993 existing bookmarks newest-first. Daily runs pick up new bookmarks from Smaug. Self-tuning based on observed rate limits and likers-per-tweet volume.

## Scoring

Reuses the existing IDF-weighted overlap algorithm, parameterized by platform:

- **IDF formula:** `LN(1 + C / (1 + likers_count))` — tweets liked by millions are low signal, niche tweets with 15 likers are high signal
- **No earlyness component** (unlike GitHub stars, Twitter likes don't have meaningful temporal ordering)
- **Minimum threshold:** ≥2 overlapping tweets to qualify as a curator
- **Output:** Ranked Twitter curators in the `Curator` table with `platform = "twitter"`

## Twitter List Sync

After rescoring:

1. Take top N curators (configurable, default 50)
2. Compare against current `TwitterListMember` rows
3. Add new members via `ListAddMember` GraphQL mutation
4. Remove dropped members via `ListRemoveMember`
5. If list doesn't exist yet, create it on first run (private, named "Curator Radar")
6. Idempotent — safe to run repeatedly

## Daily Run Sequence

1. Ingest new bookmarks from Smaug output
2. Fetch likers for all unfetched tweets (adaptive rate limiting)
3. Rescore Twitter curators
4. Sync Twitter List membership
5. Weekly: generate combined digest with both GitHub and Twitter sections

Scheduled via scheduler-service cron job, once daily.

## Digest

Extends the existing weekly digest with a "Twitter Curators" section:

- Markdown table: Rank | Handle | Overlap Count | Score
- Delivered alongside the GitHub curators section

## Credentials & Config

- Twitter auth cookies (`auth_token`, `ct0`) read from Smaug's config — single source of truth
- No new credentials needed
- Cookies expire periodically and require manual browser refresh (same as Smaug)

## Out of Scope

- **Cross-platform identity matching** — matching Twitter handles to GitHub usernames. Useful but complex; deferred.
- **Active monitoring of curator tweets** — Twitter likes are private since 2023. Curator discovery is passive (scores update as you bookmark more tweets).
- **bird CLI integration** — Favoriters endpoint not supported by bird CLI. Direct GraphQL is simpler for a single endpoint.
- **OAuth authentication** — Twitter's OAuth is heavy. Browser cookie auth matches Smaug's approach.
