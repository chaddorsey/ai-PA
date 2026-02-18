# Gmail Watch Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add follow-up reminders, flexible intervals, and BCC-based auto-watching to the gmail-watch-service.

**Architecture:** Enhance the existing gmail-watch-service (Approach A: all-in-one). New interval parser utility, schema migration from `followup_days` to `followup_seconds`, follow-up scanner in the existing scheduler loop, BCC auto-watch with forward detection in the watch manager. Reuse forwarded-message parsing patterns from `email_task_queue_tool.py`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL, Google Gmail API, Google Pub/Sub, pytest + pytest-asyncio

**Design Doc:** `docs/plans/2026-02-17-gmail-watch-enhancements-design.md`

---

### Task 1: Interval Parser Utility

**Files:**
- Create: `gmail-watch-service/src/gmail_watch/utils/__init__.py`
- Create: `gmail-watch-service/src/gmail_watch/utils/interval_parser.py`
- Create: `gmail-watch-service/tests/test_interval_parser.py`

**Context:** All interval logic (BCC parsing, MCP tool input, display formatting) uses this module. It converts between human-readable strings (`"3d"`, `"12h"`, `"1w"`) and integer seconds. Also extracts interval from BCC plus-addresses like `cdorsey+watch3d@concord.org`.

**Step 1: Write tests**

```python
# gmail-watch-service/tests/test_interval_parser.py
"""Tests for interval parser utility."""

import pytest

from gmail_watch.utils.interval_parser import (
    parse_interval,
    format_interval,
    extract_interval_from_address,
)

DEFAULT_SECONDS = 259200  # 3 days


class TestParseInterval:
    """Tests for parse_interval()."""

    def test_parse_hours(self):
        assert parse_interval("12h") == 43200

    def test_parse_days(self):
        assert parse_interval("3d") == 259200

    def test_parse_weeks(self):
        assert parse_interval("1w") == 604800

    def test_parse_two_weeks(self):
        assert parse_interval("2w") == 1209600

    def test_parse_one_day(self):
        assert parse_interval("1d") == 86400

    def test_parse_with_whitespace(self):
        assert parse_interval("  3d  ") == 259200

    def test_parse_uppercase(self):
        assert parse_interval("3D") == 259200

    def test_parse_empty_returns_default(self):
        assert parse_interval("") == DEFAULT_SECONDS

    def test_parse_none_returns_default(self):
        assert parse_interval(None) == DEFAULT_SECONDS

    def test_parse_invalid_returns_default(self):
        assert parse_interval("abc") == DEFAULT_SECONDS

    def test_parse_no_unit_returns_default(self):
        assert parse_interval("3") == DEFAULT_SECONDS


class TestFormatInterval:
    """Tests for format_interval()."""

    def test_format_weeks(self):
        assert format_interval(604800) == "1w"

    def test_format_days(self):
        assert format_interval(259200) == "3d"

    def test_format_hours(self):
        assert format_interval(43200) == "12h"

    def test_format_two_weeks(self):
        assert format_interval(1209600) == "2w"

    def test_format_one_day(self):
        assert format_interval(86400) == "1d"

    def test_format_non_round_hours(self):
        # 90000 seconds = 25 hours, not evenly divisible by days
        assert format_interval(90000) == "25h"


class TestExtractIntervalFromAddress:
    """Tests for extract_interval_from_address()."""

    def test_extract_3d(self):
        assert extract_interval_from_address(
            "cdorsey+watch3d@concord.org", "cdorsey+watch"
        ) == 259200

    def test_extract_12h(self):
        assert extract_interval_from_address(
            "cdorsey+watch12h@concord.org", "cdorsey+watch"
        ) == 43200

    def test_extract_1w(self):
        assert extract_interval_from_address(
            "cdorsey+watch1w@concord.org", "cdorsey+watch"
        ) == 604800

    def test_extract_no_interval_returns_default(self):
        assert extract_interval_from_address(
            "cdorsey+watch@concord.org", "cdorsey+watch"
        ) == DEFAULT_SECONDS

    def test_extract_case_insensitive(self):
        assert extract_interval_from_address(
            "CDorsey+Watch3D@concord.org", "cdorsey+watch"
        ) == 259200

    def test_extract_no_match_returns_none(self):
        assert extract_interval_from_address(
            "someone@example.com", "cdorsey+watch"
        ) is None
```

**Step 2: Run tests to verify they fail**

Run: `cd gmail-watch-service && python -m pytest tests/test_interval_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gmail_watch.utils'`

**Step 3: Implement interval parser**

```python
# gmail-watch-service/src/gmail_watch/utils/__init__.py
```

```python
# gmail-watch-service/src/gmail_watch/utils/interval_parser.py
"""Interval parsing and formatting for follow-up durations.

Converts between human-readable interval strings ('3d', '12h', '1w')
and integer seconds. Also extracts intervals from BCC plus-addresses.
"""

from __future__ import annotations

import re
from typing import Optional

# Default follow-up interval: 3 days in seconds
DEFAULT_FOLLOWUP_SECONDS = 259200

# Multipliers for interval units
_UNIT_MULTIPLIERS = {"h": 3600, "d": 86400, "w": 604800}

# Pattern: digits followed by h/d/w
_INTERVAL_PATTERN = re.compile(r"^(\d+)(h|d|w)$")


def parse_interval(s: Optional[str]) -> int:
    """Parse a human-readable interval string to seconds.

    Args:
        s: Interval string like '3d', '12h', '1w'.
           Returns DEFAULT_FOLLOWUP_SECONDS for None, empty, or invalid input.

    Returns:
        Interval in seconds.
    """
    if not s:
        return DEFAULT_FOLLOWUP_SECONDS

    match = _INTERVAL_PATTERN.match(s.strip().lower())
    if not match:
        return DEFAULT_FOLLOWUP_SECONDS

    num, unit = int(match.group(1)), match.group(2)
    return num * _UNIT_MULTIPLIERS[unit]


def format_interval(seconds: int) -> str:
    """Format seconds as a human-readable interval string.

    Args:
        seconds: Interval in seconds.

    Returns:
        Human-readable string like '3d', '12h', '1w'.
    """
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    return f"{seconds // 3600}h"


def extract_interval_from_address(
    address: str, bcc_prefix: str
) -> Optional[int]:
    """Extract follow-up interval from a BCC plus-address.

    Parses addresses like 'user+watch3d@domain.com' to extract the interval.
    The prefix (e.g., 'user+watch') is matched case-insensitively.

    Args:
        address: Full email address to parse.
        bcc_prefix: The plus-address prefix to match (e.g., 'cdorsey+watch').

    Returns:
        Interval in seconds, DEFAULT_FOLLOWUP_SECONDS if prefix matches but
        no interval specified, or None if prefix doesn't match.
    """
    # Extract local part (before @)
    local_part = address.split("@")[0] if "@" in address else address

    if not local_part.lower().startswith(bcc_prefix.lower()):
        return None

    # Extract the suffix after the prefix
    suffix = local_part[len(bcc_prefix):]

    if not suffix:
        # Matched prefix but no interval — use default
        return DEFAULT_FOLLOWUP_SECONDS

    return parse_interval(suffix)
```

**Step 4: Run tests to verify they pass**

Run: `cd gmail-watch-service && python -m pytest tests/test_interval_parser.py -v`
Expected: All 17 tests PASS

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/utils/__init__.py \
       gmail-watch-service/src/gmail_watch/utils/interval_parser.py \
       gmail-watch-service/tests/test_interval_parser.py
git commit -m "feat: add interval parser utility for gmail-watch-service"
```

---

### Task 2: Schema Migration

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/models.py:56-60`
- Modify: `gmail-watch-service/scripts/init_schema.sql`
- Create: `gmail-watch-service/scripts/migrate_001_followup_seconds.sql`

**Context:** Replace `followup_days` (INTEGER) with `followup_seconds` (INTEGER). Add `source` and `bcc_address` columns. The service doesn't use Alembic — schema is managed via raw SQL scripts. We create a migration script for the live database and update `init_schema.sql` for fresh installs.

**Step 1: Write migration SQL**

```sql
-- gmail-watch-service/scripts/migrate_001_followup_seconds.sql
-- Migration: Replace followup_days with followup_seconds, add source and bcc_address
-- Run: docker cp this.sql supabase-db:/tmp/ && docker exec supabase-db psql -U postgres -f /tmp/migrate_001_followup_seconds.sql

BEGIN;

-- Add new columns
ALTER TABLE gmail_watch.watched_threads
    ADD COLUMN IF NOT EXISTS followup_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS bcc_address VARCHAR(255);

-- Migrate existing data: followup_days -> followup_seconds
UPDATE gmail_watch.watched_threads
SET followup_seconds = followup_days * 86400
WHERE followup_days IS NOT NULL AND followup_seconds IS NULL;

-- Drop old column
ALTER TABLE gmail_watch.watched_threads
    DROP COLUMN IF EXISTS followup_days;

-- Update followup index to use new column name
DROP INDEX IF EXISTS gmail_watch.idx_watched_threads_followup;
CREATE INDEX IF NOT EXISTS idx_watched_threads_followup
    ON gmail_watch.watched_threads(followup_due_at)
    WHERE is_active = TRUE AND followup_seconds IS NOT NULL AND NOT followup_notified;

COMMIT;
```

**Step 2: Update init_schema.sql**

Replace in `gmail-watch-service/scripts/init_schema.sql` the `followup_days` line and add new columns:

In the `watched_threads` CREATE TABLE, replace:
```sql
    -- Follow-up timing (Phase 2)
    followup_days INTEGER,
```
with:
```sql
    -- Follow-up timing
    followup_seconds INTEGER,
    source VARCHAR(50) DEFAULT 'manual',
    bcc_address VARCHAR(255),
```

Update the followup index from:
```sql
    WHERE is_active = TRUE AND followup_days IS NOT NULL AND NOT followup_notified;
```
to:
```sql
    WHERE is_active = TRUE AND followup_seconds IS NOT NULL AND NOT followup_notified;
```

**Step 3: Update SQLAlchemy model**

In `gmail-watch-service/src/gmail_watch/models.py`, replace lines 56-60:
```python
    followup_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
```
with:
```python
    followup_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    source: Mapped[str] = mapped_column(String(50), default="manual")
    bcc_address: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
```

**Step 4: Run migration on live database**

```bash
docker cp gmail-watch-service/scripts/migrate_001_followup_seconds.sql ai-pa-supabase-db-1:/tmp/
docker exec ai-pa-supabase-db-1 psql -U postgres -f /tmp/migrate_001_followup_seconds.sql
```

Expected: `BEGIN`, `ALTER TABLE`, `UPDATE 0` (no existing watches with followup_days), `ALTER TABLE`, `DROP INDEX`, `CREATE INDEX`, `COMMIT`

**Step 5: Verify migration**

```bash
docker exec ai-pa-supabase-db-1 psql -U postgres -c "\d gmail_watch.watched_threads"
```

Expected: `followup_seconds` column present, `followup_days` absent, `source` and `bcc_address` present

**Step 6: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/models.py \
       gmail-watch-service/scripts/init_schema.sql \
       gmail-watch-service/scripts/migrate_001_followup_seconds.sql
git commit -m "feat: migrate schema from followup_days to followup_seconds"
```

---

### Task 3: Update Registry (followup_seconds)

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/services/registry.py:20-85,142-198`
- Modify: `gmail-watch-service/tests/test_registry.py`

**Context:** Update `ThreadRegistry` to use `followup_seconds` instead of `followup_days`. Add `source` and `bcc_address` to watch creation. Update `list_watched` and `get_watch_status` responses to include new fields and human-readable interval.

**Step 1: Update tests**

Add/modify in `gmail-watch-service/tests/test_registry.py`:

Replace the `test_watch_thread_creates_record` test to accept `followup_interval`:

```python
@pytest.mark.asyncio
async def test_watch_thread_with_interval(mock_session):
    """watch_thread stores followup_seconds from interval string."""
    registry = ThreadRegistry(mock_session)

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.watch_thread(
        thread_id="thread_abc123",
        subject="Test Subject",
        recipients=["user@example.com"],
        followup_interval="3d",
    )

    assert result["status"] == "ok"
    assert result["followup_interval"] == "3d"
    assert result["followup_due_at"] is not None
    mock_session.add.assert_called_once()
    # Verify the WatchedThread object was created with correct seconds
    added_thread = mock_session.add.call_args[0][0]
    assert added_thread.followup_seconds == 259200


@pytest.mark.asyncio
async def test_watch_thread_with_source_bcc(mock_session):
    """watch_thread stores source and bcc_address."""
    registry = ThreadRegistry(mock_session)

    mock_result = mock_session.execute.return_value
    mock_result.scalar_one_or_none.return_value = None

    result = await registry.watch_thread(
        thread_id="thread_abc123",
        subject="Test Subject",
        followup_interval="12h",
        source="bcc",
        bcc_address="cdorsey+watch12h@concord.org",
    )

    assert result["status"] == "ok"
    added_thread = mock_session.add.call_args[0][0]
    assert added_thread.source == "bcc"
    assert added_thread.bcc_address == "cdorsey+watch12h@concord.org"
    assert added_thread.followup_seconds == 43200
```

Update `test_list_watched_returns_active_threads` to check new fields:
- Change `mock_thread.followup_days = None` to `mock_thread.followup_seconds = None`
- Add `mock_thread.source = "manual"`

Update `test_get_watch_status_returns_details` to check new fields:
- Change `mock_thread.followup_days = 3` to `mock_thread.followup_seconds = 259200`
- Add `mock_thread.source = "manual"`, `mock_thread.bcc_address = None`
- Change assertion `assert result["followup_days"] == 3` to `assert result["followup_interval"] == "3d"`
- Add assertion `assert result["source"] == "manual"`

**Step 2: Run tests to verify they fail**

Run: `cd gmail-watch-service && python -m pytest tests/test_registry.py -v`
Expected: FAIL — `watch_thread() got unexpected keyword argument 'followup_interval'`

**Step 3: Update registry implementation**

In `gmail-watch-service/src/gmail_watch/services/registry.py`:

Add import at top:
```python
from gmail_watch.utils.interval_parser import parse_interval, format_interval
```

Update `watch_thread` signature (line 20-27) — replace `followup_days` param:
```python
    async def watch_thread(
        self,
        thread_id: str,
        subject: Optional[str] = None,
        recipients: Optional[list[str]] = None,
        followup_interval: Optional[str] = None,
        context: Optional[str] = None,
        source: str = "manual",
        bcc_address: Optional[str] = None,
        followup_due_at_override: Optional[datetime] = None,
    ) -> dict[str, Any]:
```

Update the body — replace followup calculation (lines 63-76):
```python
        # Calculate followup timing
        followup_seconds = None
        followup_due_at = None
        if followup_interval:
            followup_seconds = parse_interval(followup_interval)
            if followup_due_at_override:
                followup_due_at = followup_due_at_override
            else:
                followup_due_at = datetime.now(timezone.utc) + timedelta(
                    seconds=followup_seconds
                )

        # Create new watch
        thread = WatchedThread(
            thread_id=thread_id,
            subject=subject,
            original_recipients=recipients,
            followup_seconds=followup_seconds,
            followup_due_at=followup_due_at,
            source=source,
            bcc_address=bcc_address,
            extra_data={"context": context} if context else None,
        )
```

Update return value (lines 80-85):
```python
        return {
            "status": "ok",
            "thread_id": thread_id,
            "message": "Thread is now being watched",
            "followup_interval": format_interval(followup_seconds) if followup_seconds else None,
            "followup_due_at": followup_due_at.isoformat() if followup_due_at else None,
        }
```

Update `list_watched` response (lines 145-158) — replace `followup_days` key:
```python
                    "followup_interval": (
                        format_interval(t.followup_seconds)
                        if t.followup_seconds
                        else None
                    ),
                    "followup_due_at": (
                        t.followup_due_at.isoformat() if t.followup_due_at else None
                    ),
                    "source": t.source,
```

Update `get_watch_status` response (lines 177-198) — replace `followup_days` key:
```python
            "followup_interval": (
                format_interval(thread.followup_seconds)
                if thread.followup_seconds
                else None
            ),
            "followup_due_at": (
                thread.followup_due_at.isoformat() if thread.followup_due_at else None
            ),
            "followup_notified": thread.followup_notified,
            "source": thread.source,
            "bcc_address": thread.bcc_address,
            "message_count": thread.message_count,
            "extra_data": thread.extra_data,
```

**Step 4: Run tests**

Run: `cd gmail-watch-service && python -m pytest tests/test_registry.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/registry.py \
       gmail-watch-service/tests/test_registry.py
git commit -m "feat: update registry to use followup_seconds and source"
```

---

### Task 4: Update MCP Server and Letta Tools

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/mcp_server.py:18-31,58-91,163-178`
- Modify: `letta/gmail_watch_tools.py:10-16`
- Modify: `letta/register_gmail_watch_tools.py` (re-register)

**Context:** Update the MCP tool schema and Letta wrapper tools to use `followup_interval` (string) instead of `followup_days` (int).

**Step 1: Update MCP server**

In `gmail-watch-service/src/gmail_watch/mcp_server.py`:

Replace `WatchThreadRequest` field (lines 26-28):
```python
    followup_interval: str | None = Field(
        None, description="Follow-up interval like '3d', '12h', '1w'"
    )
```

Replace `followup_days` in TOOLS schema (lines 80-83):
```python
                "followup_interval": {
                    "type": "string",
                    "description": "Follow-up interval like '3d' (3 days), '12h' (12 hours), '1w' (1 week)",
                },
```

Replace `followup_days` usage in `call_tool` (line 176):
```python
                result = await registry.watch_thread(
                    thread_id=thread_id,
                    subject=arguments.get("subject"),
                    recipients=recipients,
                    followup_interval=arguments.get("followup_interval"),
                    context=arguments.get("context"),
                )
```

**Step 2: Update Letta tools**

In `letta/gmail_watch_tools.py`, update `watch_gmail_thread` signature:

Replace `followup_days: Optional[int] = None` with:
```python
    followup_interval: Optional[str] = None,
```

Update the docstring Args:
```python
        followup_interval: Follow-up reminder interval like '3d' (3 days),
            '12h' (12 hours), '1w' (1 week). Default: 3 days if omitted.
```

Update the arguments dict inside the function:
```python
        if followup_interval is not None:
            arguments["followup_interval"] = followup_interval
```

(Remove the old `if followup_days is not None:` block.)

**Step 3: Re-register Letta tools**

Run: `cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python letta/register_gmail_watch_tools.py`
Expected: "Updating existing tool: watch_gmail_thread" (and others), "Registered 4 Gmail Watch tools."

**Step 4: Rebuild and restart gmail-watch-service**

```bash
cd /Volumes/main-drive/ai-PA
find gmail-watch-service -name "._*" -type f -delete  # Clean macOS metadata
docker-compose up -d --build gmail-watch-service
```

Wait 30 seconds, then verify:
```bash
curl -s http://localhost:8000/health | python -m json.tool
curl -s http://localhost:8000/mcp | python -m json.tool
```

Expected: Health OK, MCP tools list shows `followup_interval` instead of `followup_days`

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/mcp_server.py \
       letta/gmail_watch_tools.py
git commit -m "feat: update MCP and Letta tools to use followup_interval"
```

---

### Task 5: Settings for New Features

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/settings.py:65-71`
- Modify: `docker-compose.yml` (gmail-watch-service environment)

**Context:** Add `FOLLOWUP_CHECK_INTERVAL`, `BCC_WATCH_ADDRESS`, and `DEFAULT_FOLLOWUP_SECONDS` env vars.

**Step 1: Update settings.py**

Add after `pull_interval_seconds` (line 70) in `gmail-watch-service/src/gmail_watch/settings.py`:

```python
    # Follow-up scanner settings
    followup_check_interval: int = Field(
        default=300,
        alias="FOLLOWUP_CHECK_INTERVAL",
        description="Interval in seconds between follow-up deadline checks",
    )

    # BCC auto-watch settings
    bcc_watch_address: str = Field(
        default="cdorsey+watch",
        alias="BCC_WATCH_ADDRESS",
        description="Plus-address prefix for BCC-triggered watches (without domain)",
    )
    default_followup_seconds: int = Field(
        default=259200,
        alias="DEFAULT_FOLLOWUP_SECONDS",
        description="Default follow-up interval in seconds (3 days = 259200)",
    )
```

**Step 2: Update docker-compose.yml**

Add to the gmail-watch-service environment block:
```yaml
        - FOLLOWUP_CHECK_INTERVAL=300
        - BCC_WATCH_ADDRESS=cdorsey+watch
        - DEFAULT_FOLLOWUP_SECONDS=259200
```

**Step 3: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/settings.py docker-compose.yml
git commit -m "feat: add followup scanner and BCC watch settings"
```

---

### Task 6: Follow-Up Scanner

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/services/agent_notifier.py:66-88`
- Modify: `gmail-watch-service/src/gmail_watch/services/watch_manager.py`
- Modify: `gmail-watch-service/src/gmail_watch/scheduler.py:52-91`
- Create: `gmail-watch-service/tests/test_followup_scanner.py`

**Context:** Add `notify_followup_needed()` to AgentNotifier. Add `check_followups()` to WatchManager. Add periodic follow-up check to the scheduler loop on a slower cadence than Pub/Sub polling.

**Step 1: Write tests**

```python
# gmail-watch-service/tests/test_followup_scanner.py
"""Tests for follow-up scanner functionality."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gmail_watch.services.agent_notifier import AgentNotifier
from gmail_watch.services.watch_manager import WatchManager


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


class TestNotifyFollowupNeeded:
    """Tests for AgentNotifier.notify_followup_needed()."""

    @pytest.mark.asyncio
    async def test_formats_followup_message(self):
        notifier = AgentNotifier(
            letta_base_url="http://letta:8283",
            agent_id="agent-test",
        )

        mock_thread = MagicMock()
        mock_thread.subject = "Project Proposal"
        mock_thread.thread_id = "thread_123"
        mock_thread.original_recipients = ["jane@example.com"]
        mock_thread.followup_seconds = 259200
        mock_thread.followup_due_at = datetime.now(timezone.utc) - timedelta(hours=6)
        mock_thread.created_at = datetime.now(timezone.utc) - timedelta(days=4)
        mock_thread.message_count = 1

        message = notifier._format_followup_message(mock_thread)

        assert "[Gmail Watch] Follow-up needed" in message
        assert "Project Proposal" in message
        assert "jane@example.com" in message
        assert "3d" in message or "3 day" in message.lower()

    @pytest.mark.asyncio
    async def test_sends_followup_to_agent(self):
        notifier = AgentNotifier(
            letta_base_url="http://letta:8283",
            agent_id="agent-test",
        )

        mock_thread = MagicMock()
        mock_thread.subject = "Test"
        mock_thread.thread_id = "thread_123"
        mock_thread.original_recipients = ["user@example.com"]
        mock_thread.followup_seconds = 86400
        mock_thread.followup_due_at = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_thread.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        mock_thread.message_count = 1

        with patch.object(notifier, "_send_to_agent", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"status": "ok"}
            result = await notifier.notify_followup_needed(mock_thread)
            assert result["status"] == "ok"
            mock_send.assert_called_once()


class TestCheckFollowups:
    """Tests for WatchManager.check_followups()."""

    @pytest.mark.asyncio
    async def test_finds_overdue_threads(self, mock_session):
        overdue_thread = MagicMock()
        overdue_thread.thread_id = "thread_overdue"
        overdue_thread.subject = "Overdue Thread"
        overdue_thread.followup_seconds = 259200
        overdue_thread.followup_due_at = datetime.now(timezone.utc) - timedelta(hours=6)
        overdue_thread.original_recipients = ["user@example.com"]
        overdue_thread.created_at = datetime.now(timezone.utc) - timedelta(days=4)
        overdue_thread.message_count = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [overdue_thread]
        mock_session.execute = AsyncMock(return_value=mock_result)

        manager = WatchManager(
            gmail_client=MagicMock(),
            pubsub_puller=MagicMock(),
            session=mock_session,
        )

        with patch.object(manager, "notifier") as mock_notifier:
            mock_notifier.notify_followup_needed = AsyncMock(
                return_value={"status": "ok"}
            )
            mock_notifier.agent_id = "agent-test"

            result = await manager.check_followups()

        assert result["overdue_count"] == 1
        assert result["notified_count"] == 1
        assert overdue_thread.followup_notified is True

    @pytest.mark.asyncio
    async def test_no_overdue_threads(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        manager = WatchManager(
            gmail_client=MagicMock(),
            pubsub_puller=MagicMock(),
            session=mock_session,
        )

        result = await manager.check_followups()

        assert result["overdue_count"] == 0
        assert result["notified_count"] == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd gmail-watch-service && python -m pytest tests/test_followup_scanner.py -v`
Expected: FAIL — `AttributeError: 'AgentNotifier' object has no attribute '_format_followup_message'`

**Step 3: Add `notify_followup_needed` to AgentNotifier**

In `gmail-watch-service/src/gmail_watch/services/agent_notifier.py`, add import:
```python
from gmail_watch.utils.interval_parser import format_interval
```

Add after `_format_watch_started_message` method (after line 88):

```python
    def _format_followup_message(
        self,
        thread: WatchedThread,
    ) -> str:
        """Format the notification message for an overdue follow-up."""
        recipients_str = ", ".join(thread.original_recipients or ["unknown"])
        interval_str = (
            format_interval(thread.followup_seconds)
            if thread.followup_seconds
            else "unknown"
        )

        # Calculate how overdue
        now = datetime.now(timezone.utc)
        overdue_delta = now - thread.followup_due_at if thread.followup_due_at else None
        if overdue_delta:
            overdue_hours = int(overdue_delta.total_seconds() / 3600)
            if overdue_hours < 24:
                overdue_str = f"{overdue_hours} hours ago"
            else:
                overdue_days = overdue_hours // 24
                overdue_str = f"{overdue_days} day(s) ago"
        else:
            overdue_str = "unknown"

        message = f"""[Gmail Watch] Follow-up needed — no reply received

**Subject:** {thread.subject or "(no subject)"}
**Recipients:** {recipients_str}
**Watch interval:** {interval_str}
**Follow-up was due:** {overdue_str}
**Messages in thread:** {thread.message_count}

No reply has been received on this thread. Consider following up or closing the watch.
Use `read_email(thread_id="{thread.thread_id}")` to review the thread, or `reply_to_email()` to send a follow-up."""

        return message

    async def notify_followup_needed(
        self,
        thread: WatchedThread,
    ) -> dict[str, Any]:
        """Send follow-up needed notification to Email Agent."""
        message = self._format_followup_message(thread)
        return await self._send_to_agent(message)
```

**Step 4: Add `check_followups` to WatchManager**

In `gmail-watch-service/src/gmail_watch/services/watch_manager.py`, add import at top:
```python
from gmail_watch.models import Notification, SyncState, WatchedThread
```

Add method after `process_notifications` (after line 422):

```python
    async def check_followups(self) -> dict[str, Any]:
        """Check for threads with overdue follow-up deadlines.

        Queries for active, non-replied threads whose followup_due_at
        has passed and sends a one-time notification to the agent.

        Returns:
            Dictionary with overdue_count and notified_count.
        """
        try:
            now = datetime.now(timezone.utc)

            stmt = select(WatchedThread).where(
                WatchedThread.is_active == True,  # noqa: E712
                WatchedThread.followup_seconds.isnot(None),
                WatchedThread.followup_due_at < now,
                WatchedThread.followup_notified == False,  # noqa: E712
                WatchedThread.reply_received == False,  # noqa: E712
            )

            result = await self._session.execute(stmt)
            overdue_threads = result.scalars().all()

            notified_count = 0

            for thread in overdue_threads:
                # Notify agent
                notify_result = await self.notifier.notify_followup_needed(thread)

                # Mark as notified regardless of send success
                thread.followup_notified = True

                # Log notification
                await self._log_notification(
                    thread_id=thread.thread_id,
                    notification_type="followup_needed",
                    agent_id=self.notifier.agent_id,
                    extra_data={
                        "notify_status": notify_result.get("status"),
                        "followup_seconds": thread.followup_seconds,
                    },
                )

                if notify_result.get("status") == "ok":
                    notified_count += 1

            await self._session.commit()

            return {
                "status": "ok",
                "overdue_count": len(overdue_threads),
                "notified_count": notified_count,
            }

        except Exception as e:
            error_msg = f"check_followups error: {str(e)}"
            try:
                await self._record_error(error_msg)
            except Exception:
                pass
            return {
                "status": "error",
                "error": str(e),
                "overdue_count": 0,
                "notified_count": 0,
            }
```

**Step 5: Add follow-up check to scheduler loop**

In `gmail-watch-service/src/gmail_watch/scheduler.py`, update `_run_loop` to add a cycle counter:

Replace the `while self._running:` block (lines 68-91):

```python
        followup_check_cycles = max(
            1,
            settings.followup_check_interval // settings.pull_interval_seconds,
        )
        cycle_count = 0

        while self._running:
            try:
                async with session_maker() as session:
                    manager = WatchManager(session=session)

                    # Check if watch needs renewal
                    check_result = await manager.check_watch_expiration()
                    if check_result.get("needs_renewal", False):
                        logger.info("Renewing Gmail watch subscription")
                        await manager.initialize_watch()

                    # Process Pub/Sub notifications (every cycle)
                    result = await manager.process_notifications()

                    if result.get("replies_found", 0) > 0:
                        logger.info(
                            "Processed notifications",
                            replies_found=result["replies_found"],
                        )

                    # Check follow-up deadlines (every N cycles)
                    cycle_count += 1
                    if cycle_count >= followup_check_cycles:
                        cycle_count = 0
                        followup_result = await manager.check_followups()
                        if followup_result.get("overdue_count", 0) > 0:
                            logger.info(
                                "Follow-up check",
                                overdue=followup_result["overdue_count"],
                                notified=followup_result["notified_count"],
                            )

            except Exception as e:
                logger.error("Error in polling loop", error=str(e))

            await asyncio.sleep(settings.pull_interval_seconds)
```

**Step 6: Run tests**

Run: `cd gmail-watch-service && python -m pytest tests/test_followup_scanner.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/agent_notifier.py \
       gmail-watch-service/src/gmail_watch/services/watch_manager.py \
       gmail-watch-service/src/gmail_watch/scheduler.py \
       gmail-watch-service/tests/test_followup_scanner.py
git commit -m "feat: add follow-up scanner for overdue watch deadlines"
```

---

### Task 7: BCC Auto-Watch Detection

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/services/watch_manager.py`
- Modify: `gmail-watch-service/src/gmail_watch/services/gmail_client.py`
- Create: `gmail-watch-service/tests/test_bcc_auto_watch.py`

**Context:** When the service sees a Pub/Sub notification for a thread NOT in the registry, check if the message was BCC'd to the watch address. If so, auto-register the watch. For forwards, resolve the original thread and use the original send date as the follow-up baseline.

Reference: `letta/email_task_queue_tool.py` lines 63-66 and 199-262 for forward detection patterns.

**Step 1: Write tests**

```python
# gmail-watch-service/tests/test_bcc_auto_watch.py
"""Tests for BCC auto-watch detection."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gmail_watch.services.watch_manager import WatchManager


SAMPLE_MESSAGE_BCC = {
    "id": "msg_001",
    "threadId": "thread_new",
    "snippet": "Hey, just following up on...",
    "internalDate": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
    "payload": {
        "headers": [
            {"name": "From", "value": "cdorsey@concord.org"},
            {"name": "To", "value": "jane@example.com"},
            {"name": "Bcc", "value": "cdorsey+watch3d@concord.org"},
            {"name": "Subject", "value": "Project Proposal"},
            {"name": "Date", "value": "Mon, 17 Feb 2026 10:00:00 -0500"},
        ],
        "mimeType": "text/plain",
        "body": {"data": "SGV5LCBqdXN0IGZvbGxvd2luZyB1cC4uLg=="},
    },
}

SAMPLE_MESSAGE_FWD = {
    "id": "msg_fwd",
    "threadId": "thread_fwd",
    "snippet": "---------- Forwarded message...",
    "internalDate": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
    "payload": {
        "headers": [
            {"name": "From", "value": "cdorsey@concord.org"},
            {"name": "To", "value": "cdorsey+watch1w@concord.org"},
            {"name": "Subject", "value": "Fwd: Budget Review"},
            {"name": "Date", "value": "Mon, 17 Feb 2026 14:00:00 -0500"},
        ],
        "mimeType": "text/plain",
        "body": {
            "data": "LS0tLS0tLS0tLSBGb3J3YXJkZWQgbWVzc2FnZSAtLS0tLS0tLS0tCkZyb206IEJvYiBTbWl0aCA8Ym9iQGV4YW1wbGUuY29tPgpEYXRlOiBNb24sIEZlYiAxMCwgMjAyNiBhdCAyOjMwIFBNClN1YmplY3Q6IEJ1ZGdldCBSZXZpZXcKVG86IGNkb3JzZXlAY29uY29yZC5vcmcKClBsZWFzZSByZXZpZXcgdGhlIGF0dGFjaGVkIGJ1ZGdldC4="
        },
    },
}


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


class TestBccAutoWatch:
    """Tests for BCC auto-watch detection."""

    @pytest.mark.asyncio
    async def test_detects_bcc_watch_address(self, mock_session):
        """Auto-registers watch when BCC address matches."""
        mock_gmail = MagicMock()
        mock_gmail.get_message.return_value = SAMPLE_MESSAGE_BCC

        manager = WatchManager(
            gmail_client=mock_gmail,
            pubsub_puller=MagicMock(),
            session=mock_session,
        )

        # Mock registry.watch_thread
        with patch.object(
            manager.registry, "watch_thread", new_callable=AsyncMock
        ) as mock_watch:
            mock_watch.return_value = {"status": "ok", "thread_id": "thread_new"}

            result = await manager.try_auto_register(
                message_id="msg_001", thread_id="thread_new"
            )

        assert result is not None
        assert result["status"] == "ok"
        mock_watch.assert_called_once()
        call_kwargs = mock_watch.call_args[1]
        assert call_kwargs["thread_id"] == "thread_new"
        assert call_kwargs["source"] == "bcc"
        assert call_kwargs["followup_interval"] == "3d"
        assert call_kwargs["subject"] == "Project Proposal"

    @pytest.mark.asyncio
    async def test_detects_forward_and_resolves_original(self, mock_session):
        """Detects forward, resolves original thread, uses original date."""
        mock_gmail = MagicMock()
        mock_gmail.get_message.return_value = SAMPLE_MESSAGE_FWD

        # Mock Gmail search for original thread
        mock_gmail.search_messages.return_value = [
            {"id": "msg_original", "threadId": "thread_original"}
        ]

        manager = WatchManager(
            gmail_client=mock_gmail,
            pubsub_puller=MagicMock(),
            session=mock_session,
        )

        with patch.object(
            manager.registry, "watch_thread", new_callable=AsyncMock
        ) as mock_watch:
            mock_watch.return_value = {"status": "ok", "thread_id": "thread_original"}

            result = await manager.try_auto_register(
                message_id="msg_fwd", thread_id="thread_fwd"
            )

        assert result is not None
        call_kwargs = mock_watch.call_args[1]
        # Should watch the ORIGINAL thread, not the forward
        assert call_kwargs["thread_id"] == "thread_original"
        assert call_kwargs["subject"] == "Budget Review"
        assert call_kwargs["followup_interval"] == "1w"
        # Should have a followup_due_at_override based on original date
        assert call_kwargs["followup_due_at_override"] is not None

    @pytest.mark.asyncio
    async def test_no_bcc_match_returns_none(self, mock_session):
        """Returns None when no BCC watch address found."""
        msg_no_bcc = {
            "id": "msg_002",
            "threadId": "thread_other",
            "payload": {
                "headers": [
                    {"name": "From", "value": "someone@example.com"},
                    {"name": "To", "value": "cdorsey@concord.org"},
                    {"name": "Subject", "value": "Hello"},
                ],
                "mimeType": "text/plain",
                "body": {"data": ""},
            },
        }
        mock_gmail = MagicMock()
        mock_gmail.get_message.return_value = msg_no_bcc

        manager = WatchManager(
            gmail_client=mock_gmail,
            pubsub_puller=MagicMock(),
            session=mock_session,
        )

        result = await manager.try_auto_register(
            message_id="msg_002", thread_id="thread_other"
        )

        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd gmail-watch-service && python -m pytest tests/test_bcc_auto_watch.py -v`
Expected: FAIL — `AttributeError: 'WatchManager' object has no attribute 'try_auto_register'`

**Step 3: Add `search_messages` to GmailClient**

In `gmail-watch-service/src/gmail_watch/services/gmail_client.py`, add after `get_message` (after line 120):

```python
    def search_messages(
        self, query: str, max_results: int = 5
    ) -> list[dict[str, Any]]:
        """Search Gmail messages by query.

        Args:
            query: Gmail search query string.
            max_results: Maximum results to return.

        Returns:
            List of message dicts with 'id' and 'threadId'.
        """
        response = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return response.get("messages", [])

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove a label from a message."""
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": [label_id]},
        ).execute()
```

**Step 4: Add `try_auto_register` to WatchManager**

In `gmail-watch-service/src/gmail_watch/services/watch_manager.py`, add imports:

```python
import base64
import re

from gmail_watch.settings import settings
from gmail_watch.utils.interval_parser import extract_interval_from_address, format_interval
```

Add method after `check_followups`:

```python
    # Patterns for forward detection (same as email_task_queue_tool.py)
    _FORWARD_DELIMITER = re.compile(r"-{5,}\s*Forwarded message\s*-{5,}")
    _FORWARDED_HEADER = re.compile(
        r"^(From|Date|Subject|To):\s*(.+)$", re.MULTILINE
    )
    _EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+")

    async def try_auto_register(
        self,
        message_id: str,
        thread_id: str,
    ) -> Optional[dict[str, Any]]:
        """Try to auto-register a watch from BCC address detection.

        Called when a Pub/Sub notification arrives for a thread NOT in the
        registry. Fetches the message, checks for BCC watch address, and
        registers the watch if found.

        For forwards (subject starts with 'Fwd:'), resolves the original
        thread and uses the original send date as the follow-up baseline.

        Args:
            message_id: Gmail message ID from the notification.
            thread_id: Gmail thread ID from the notification.

        Returns:
            Watch registration result dict, or None if no BCC match.
        """
        try:
            # Fetch full message to get headers and body
            message = self._gmail_client.get_message(message_id, format="full")

            # Extract all headers
            headers = {}
            for h in message.get("payload", {}).get("headers", []):
                headers[h["name"].lower()] = h["value"]

            # Check To, CC, BCC for watch address
            bcc_prefix = settings.bcc_watch_address
            matched_address = None
            interval_seconds = None

            for header_name in ("to", "cc", "bcc"):
                value = headers.get(header_name, "")
                for addr in self._EMAIL_PATTERN.findall(value):
                    result = extract_interval_from_address(addr, bcc_prefix)
                    if result is not None:
                        matched_address = addr
                        interval_seconds = result
                        break
                if matched_address:
                    break

            if not matched_address:
                return None

            subject = headers.get("subject", "")
            interval_str = format_interval(interval_seconds)

            # Check for forward
            is_forward = subject.lower().startswith("fwd:")
            watch_thread_id = thread_id
            followup_due_override = None
            recipients = []

            # Extract recipients from To header
            to_header = headers.get("to", "")
            for addr in self._EMAIL_PATTERN.findall(to_header):
                if not addr.lower().startswith(bcc_prefix.lower()):
                    recipients.append(addr)

            if is_forward:
                # Parse forwarded message body for original headers
                body = self._extract_body(message)
                fwd_match = self._FORWARD_DELIMITER.search(body) if body else None

                if fwd_match:
                    below = body[fwd_match.end():]
                    fwd_headers = {}
                    for match in self._FORWARDED_HEADER.finditer(below[:500]):
                        fwd_headers[match.group(1).lower()] = match.group(2).strip()

                    # Use original subject (strip Fwd: prefix)
                    original_subject = fwd_headers.get("subject", "")
                    if not original_subject:
                        original_subject = re.sub(
                            r"^(Fwd:\s*)+", "", subject, flags=re.IGNORECASE
                        ).strip()
                    subject = original_subject

                    # Parse original date for follow-up baseline
                    original_date_str = fwd_headers.get("date", "")
                    original_date = self._parse_date(original_date_str)

                    if original_date and interval_seconds:
                        followup_due_override = original_date + timedelta(
                            seconds=interval_seconds
                        )

                    # Extract original sender for recipients
                    original_from = fwd_headers.get("from", "")
                    from_match = self._EMAIL_PATTERN.search(original_from)
                    if from_match:
                        recipients = [from_match.group(0)]

                    # Try to resolve original thread
                    if from_match and original_subject:
                        clean_subject = original_subject.replace('"', '\\"')
                        query = f'from:{from_match.group(0)} subject:"{clean_subject}"'
                        try:
                            search_results = self._gmail_client.search_messages(query)
                            for result in search_results:
                                if result["id"] != message_id:
                                    watch_thread_id = result.get(
                                        "threadId", watch_thread_id
                                    )
                                    break
                        except Exception:
                            pass  # Fall back to forward's thread

                    # Remove Watching label from forward thread if we resolved original
                    if watch_thread_id != thread_id:
                        try:
                            label_id = self._gmail_client.get_watching_label_id()
                            self._gmail_client.remove_label(message_id, label_id)
                        except Exception:
                            pass  # Non-critical cleanup

            # Register the watch
            result = await self.registry.watch_thread(
                thread_id=watch_thread_id,
                subject=subject,
                recipients=recipients if recipients else None,
                followup_interval=interval_str,
                source="bcc",
                bcc_address=matched_address,
                followup_due_at_override=followup_due_override,
            )

            # Log auto-registration
            await self._log_notification(
                thread_id=watch_thread_id,
                notification_type="watch_auto_created",
                message_id=message_id,
                agent_id=self.notifier.agent_id,
                extra_data={
                    "bcc_address": matched_address,
                    "interval": interval_str,
                    "is_forward": is_forward,
                    "original_thread": thread_id if watch_thread_id != thread_id else None,
                },
            )

            # Notify agent about auto-watch
            thread_obj = MagicMock()
            thread_obj.subject = subject
            thread_obj.original_recipients = recipients
            thread_obj.followup_seconds = interval_seconds
            thread_obj.followup_due_at = followup_due_override or (
                datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            )
            await self.notifier.notify_watch_started(thread_obj)

            return result

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _extract_body(self, message: dict[str, Any]) -> str:
        """Extract text body from Gmail message using MIME walk."""
        plain_body = ""
        html_body = ""
        stack = [message.get("payload", {})]

        while stack:
            part = stack.pop()
            mime_type = part.get("mimeType", "")
            parts = part.get("parts", [])
            if parts:
                stack.extend(parts)
                continue
            body_data = part.get("body", {}).get("data", "")
            if not body_data:
                continue
            decoded = base64.urlsafe_b64decode(body_data).decode(
                "utf-8", errors="replace"
            )
            if mime_type == "text/plain" and not plain_body:
                plain_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded

        return plain_body if plain_body else html_body

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse various date formats from email headers."""
        if not date_str:
            return None

        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return None
```

**Step 5: Wire into process_notifications**

In `watch_manager.py`, update `process_notifications` — replace the block at lines 379-381:

```python
                        if thread_id not in watched_thread_ids:
                            # Not a watched thread — try BCC auto-register
                            auto_result = await self.try_auto_register(
                                message_id=msg_id,
                                thread_id=thread_id,
                            )
                            if auto_result and auto_result.get("status") == "ok":
                                # Successfully auto-registered — add to watched set
                                # so future messages in this cycle are treated as replies
                                watched_thread_ids.add(
                                    auto_result.get("thread_id", thread_id)
                                )
                            continue
```

**Step 6: Run tests**

Run: `cd gmail-watch-service && python -m pytest tests/test_bcc_auto_watch.py -v`
Expected: All tests PASS

Also run full test suite:
Run: `cd gmail-watch-service && python -m pytest tests/ -v`
Expected: All tests PASS (some may need minor mock updates for the new import)

**Step 7: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/watch_manager.py \
       gmail-watch-service/src/gmail_watch/services/gmail_client.py \
       gmail-watch-service/tests/test_bcc_auto_watch.py
git commit -m "feat: add BCC auto-watch with forward detection"
```

---

### Task 8: Update Existing Tests and Agent Notifier

**Files:**
- Modify: `gmail-watch-service/tests/test_agent_notifier.py`
- Modify: `gmail-watch-service/tests/test_mcp_server.py`
- Modify: `gmail-watch-service/tests/test_watch_manager.py`
- Modify: `gmail-watch-service/src/gmail_watch/services/agent_notifier.py:66-88`

**Context:** Update existing tests that reference `followup_days` to use `followup_seconds`. Update the `_format_watch_started_message` in agent_notifier to use `followup_seconds` instead of `followup_days`.

**Step 1: Update agent_notifier `_format_watch_started_message`**

In `agent_notifier.py`, replace lines 73-79:
```python
        followup_str = ""
        if thread.followup_seconds and thread.followup_due_at:
            interval_str = format_interval(thread.followup_seconds)
            due_date_str = thread.followup_due_at.strftime("%b %d")
            followup_str = (
                f"\n**Follow-up deadline:** {interval_str} "
                f"(due {due_date_str})"
            )
```

**Step 2: Update test files**

Search all test files for `followup_days` and replace with `followup_seconds`. Key changes:

- `test_agent_notifier.py`: Update mock threads to use `followup_seconds` instead of `followup_days`
- `test_mcp_server.py`: Update `followup_days` in request bodies to `followup_interval`
- `test_watch_manager.py`: Update any `followup_days` references
- `test_registry.py`: Already updated in Task 3

**Step 3: Run full test suite**

Run: `cd gmail-watch-service && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add gmail-watch-service/tests/ \
       gmail-watch-service/src/gmail_watch/services/agent_notifier.py
git commit -m "fix: update all tests and notifier for followup_seconds migration"
```

---

### Task 9: Integration Test and Deploy

**Files:**
- No new files

**Context:** Rebuild the service, verify it works end-to-end, and test the BCC flow manually.

**Step 1: Rebuild and deploy**

```bash
cd /Volumes/main-drive/ai-PA
find gmail-watch-service -name "._*" -type f -delete
docker-compose up -d --build gmail-watch-service
```

**Step 2: Verify health**

```bash
# Wait 30 seconds for startup
sleep 30
curl -s http://localhost:8000/health | python -m json.tool
```

Expected: `"status": "healthy"`, scheduler running

**Step 3: Test MCP tool with new interval parameter**

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"name": "watch_thread", "arguments": {"thread_id": "test_thread_001", "subject": "Test Watch", "followup_interval": "1d"}}' | python -m json.tool
```

Expected: `"status": "ok"`, `"followup_interval": "1d"`, `"followup_due_at": "<~24h from now>"`

**Step 4: Verify list includes new fields**

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"name": "list_watched_threads", "arguments": {}}' | python -m json.tool
```

Expected: Thread shows `"followup_interval": "1d"`, `"source": "manual"`

**Step 5: Clean up test watch**

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"name": "unwatch_thread", "arguments": {"thread_id": "test_thread_001"}}' | python -m json.tool
```

**Step 6: Set up Gmail filter (manual step)**

In Gmail Settings > Filters and Blocked Addresses > Create new filter:
- To: `cdorsey+watch@concord.org`
- Actions: Apply label "Watching", Skip Inbox

**Step 7: End-to-end BCC test**

Send a test email from Gmail, BCC'ing `cdorsey+watch1d@concord.org`. Wait 60 seconds for Pub/Sub to propagate and the service to poll.

Check logs:
```bash
docker logs gmail-watch-service --tail 50
```

Expected: Log entry showing auto-registration of the new watch.

Verify:
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"name": "list_watched_threads", "arguments": {}}' | python -m json.tool
```

Expected: New thread with `"source": "bcc"`, `"followup_interval": "1d"`

**Step 8: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: integration test fixes for gmail-watch enhancements"
```
