# Gmail Watch Service Enhancements Design

## Goal

Add follow-up reminders, flexible intervals, and BCC-based auto-watching to the gmail-watch-service so users can monitor email threads for replies with configurable deadlines triggered by simply BCC'ing or forwarding messages.

## Context

The gmail-watch-service (deployed Feb 2026) monitors Gmail threads labeled "Watching" for replies via Google Cloud Pub/Sub. It successfully detects replies and notifies the Letta Email Agent. However, it lacks:

- **Follow-up reminders**: The schema stores `followup_days` and `followup_due_at` but no code ever checks for overdue threads.
- **Sub-day interval precision**: Only integer days are supported.
- **BCC-based auto-watching**: Users must manually call `watch_thread` via the agent. No way to trigger a watch by BCC'ing an address when composing or forwarding an email.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | All-in-one (enhance existing service) | Service already has a scheduler loop; no new services or cron jobs needed |
| BCC address | `cdorsey+watch@concord.org` with plus-addressing | Native Gmail support, single filter covers all interval variants |
| Reply notifications | Always notify on reply (existing behavior) | Already working; new feature is follow-up reminders only |
| Default interval | 3 days (259200 seconds) | Reasonable for business email; explicit intervals override |
| After reminder fires | One-and-done | `followup_notified=true` prevents repeats; agent or user can re-watch if needed |
| Follow-up notification style | Inform the agent | Agent decides action (draft follow-up, remind user, etc.) |
| Forward handling | Detect forwards, resolve original thread, use original send date as baseline | Enables retroactive watching of old threads |

---

## Schema Changes

### `watched_threads` table modifications

| Column | Current | Proposed |
|--------|---------|----------|
| `followup_days` | `INTEGER` | **Remove** |
| `followup_seconds` | -- | **Add** `INTEGER` — follow-up interval in seconds |
| `source` | -- | **Add** `VARCHAR(50) DEFAULT 'manual'` — `'manual'` or `'bcc'` |
| `bcc_address` | -- | **Add** `VARCHAR(255)` — the parsed BCC address for audit |

`followup_due_at` (timestamp) and `followup_notified` (boolean) stay unchanged. The calculation changes from `created_at + followup_days * 86400` to `created_at + followup_seconds`.

Existing `followup_days` values are migrated: `followup_seconds = followup_days * 86400`.

### Interval encoding convention

| BCC suffix | Seconds |
|-----------|---------|
| `+watch` (no number) | 259200 (3 days) |
| `+watch12h` | 43200 |
| `+watch1d` | 86400 |
| `+watch3d` | 259200 |
| `+watch1w` | 604800 |
| `+watch2w` | 1209600 |

Pattern: `(\d+)(h|d|w)` — hours, days, weeks.

---

## BCC Auto-Watch Flow

### Two triggers, same Gmail filter

| Trigger | Thread to watch | Follow-up baseline |
|---------|----------------|-------------------|
| BCC on new outgoing email | The thread the BCC is on | `now()` |
| Forward existing email to watch address | The **original** thread | Original message's send date |

### Gmail filter (one-time manual setup)

- Matches: `to:(cdorsey+watch@concord.org)`
- Actions: Apply label "Watching", Skip Inbox
- Covers all plus-tag variants (`+watch`, `+watch3d`, `+watch12h`, etc.)

### Detection flow

```
Service sees new "Watching"-labeled thread (unknown thread_id via Pub/Sub)
    |
    v
Fetch message via Gmail API (format=full)
    |
    v
Is subject prefixed with "Fwd:" ?
    |-- NO --> BCC flow:
    |           Parse To/CC/BCC headers for cdorsey+watch*@concord.org
    |           Extract interval from plus-address
    |           Register watch on this thread
    |           followup_due_at = now() + followup_seconds
    |
    |-- YES --> Forward flow:
                Parse forwarded message block for original Date, Subject, From
                (reuse patterns from email_task_queue_tool.py)
                Search Gmail for original thread: from:email subject:"subject"
                    |-- Found --> Watch ORIGINAL thread
                    |             followup_due_at = original_date + followup_seconds
                    |             Remove "Watching" label from forward thread
                    |-- Not found --> Fallback: watch forward thread
                                      followup_due_at = forward_date + followup_seconds
                                      Log warning
```

### Reused patterns from email_task_queue_tool.py

- `FORWARD_DELIMITER = re.compile(r'-{5,}\s*Forwarded message\s*-{5,}')`
- `FORWARDED_HEADER = re.compile(r'^(From|Date|Subject|To):\s*(.+)$', re.MULTILINE)`
- Stack-based MIME walk for body extraction (prefer text/plain)
- Original thread resolution via `from:email subject:"subject"` Gmail search

### Edge cases

- **BCC not visible in headers**: Gmail includes BCC in the sender's copy of the message. The service fetches the sender's message, so BCC is accessible.
- **Already-watched thread via BCC**: If thread_id already exists in registry, skip auto-registration (existing watch takes precedence).
- **Forward of forward**: Only parse first-level forwarded headers. If resolution fails, fall back to watching the forward thread.
- **Retroactive overdue**: If forwarding a 5-day-old message with `+watch3d`, the follow-up is already 2 days overdue. The next scanner cycle immediately notifies the agent.

---

## Follow-Up Scanner

### Where it runs

Inside the existing `WatchScheduler.run()` loop (30-second cadence). A counter triggers the follow-up check every `FOLLOWUP_CHECK_INTERVAL` seconds (default: 300 = 5 minutes).

### Query

```sql
SELECT * FROM gmail_watch.watched_threads
WHERE is_active = TRUE
  AND followup_seconds IS NOT NULL
  AND followup_due_at < NOW()
  AND NOT followup_notified
  AND NOT reply_received
```

The existing index `idx_watched_threads_followup` already optimizes this query (with minor adjustment for the column rename).

### Per overdue thread

1. Notify agent: "No reply on thread [subject] -- follow-up was due [time ago]. Recipients: [recipients]. Use `read_email()` or `reply_to_email()` to follow up."
2. Set `followup_notified = TRUE`
3. Log to `notifications` table (type: `"followup_needed"`)

---

## MCP Tool & Letta Tool Changes

### MCP tool: `watch_thread`

- **Remove**: `followup_days` (int)
- **Add**: `followup_interval` (str, optional) -- human-readable like `"3d"`, `"12h"`, `"1w"`. Parsed to seconds internally.
- Other params unchanged: `thread_id`, `subject`, `recipients`, `context`

### MCP tool responses

- `list_watched_threads`: Add `followup_interval` (human-readable), `source` field
- `get_watch_status`: Add `followup_interval`, `source`, `bcc_address`

### Letta tools (`gmail_watch_tools.py`)

- `watch_gmail_thread`: Replace `followup_days: Optional[int]` with `followup_interval: Optional[str]`
- Docstring: "Interval string like '3d' (3 days), '12h' (12 hours), '1w' (1 week)."

### Shared interval parser

```python
def parse_interval(s: str) -> int:
    """Parse '3d', '12h', '1w' -> seconds. Returns default 259200 (3d) for empty/None."""
    match = re.match(r'^(\d+)(h|d|w)$', s.strip().lower())
    if not match:
        return 259200  # 3-day default
    num, unit = int(match.group(1)), match.group(2)
    multipliers = {'h': 3600, 'd': 86400, 'w': 604800}
    return num * multipliers[unit]

def format_interval(seconds: int) -> str:
    """Format seconds -> human-readable. E.g., 259200 -> '3d', 43200 -> '12h'."""
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    return f"{seconds // 3600}h"
```

---

## Configuration

### New environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FOLLOWUP_CHECK_INTERVAL` | `300` | Seconds between follow-up scans |
| `BCC_WATCH_ADDRESS` | `cdorsey+watch` | Plus-address prefix to match (without domain) |
| `DEFAULT_FOLLOWUP_SECONDS` | `259200` | Default when no duration specified (3 days) |

### docker-compose.yml additions

Add to existing gmail-watch-service environment block:
```yaml
- FOLLOWUP_CHECK_INTERVAL=300
- BCC_WATCH_ADDRESS=cdorsey+watch
- DEFAULT_FOLLOWUP_SECONDS=259200
```

---

## Files Changed

| File | Change |
|------|--------|
| `gmail-watch-service/src/gmail_watch/models.py` | Add `followup_seconds`, `source`, `bcc_address`; remove `followup_days` |
| `gmail-watch-service/scripts/init_schema.sql` | Migration DDL |
| `gmail-watch-service/src/gmail_watch/mcp_server.py` | `followup_interval` param; updated responses |
| `gmail-watch-service/src/gmail_watch/services/watch_manager.py` | Add `auto_register_from_bcc()` with forward detection |
| `gmail-watch-service/src/gmail_watch/scheduler.py` | Add follow-up scanner cadence |
| `gmail-watch-service/src/gmail_watch/services/agent_notifier.py` | Add `notify_followup_needed()` |
| `gmail-watch-service/src/gmail_watch/services/gmail_client.py` | Add `get_message()` for full message fetch |
| `gmail-watch-service/src/gmail_watch/settings.py` | New env vars |
| `gmail-watch-service/src/gmail_watch/utils/interval_parser.py` | New: shared parse/format functions |
| `letta/gmail_watch_tools.py` | `followup_interval` replaces `followup_days` |
| `letta/register_gmail_watch_tools.py` | Re-register updated tools |
| `docker-compose.yml` | New env vars |

**Unchanged**: Pub/Sub infrastructure, reply detection, notification delivery, health checks, admin endpoints.
