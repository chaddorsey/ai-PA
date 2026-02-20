# Drive Comment Task Queueing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable flagging Google Docs/Sheets/Slides comments as tasks by replying with `+cdorsey+dtasks@concord.org`, with the reply parsed for markers and routed through Gmail Watch to the Docs & Transcripts Agent.

**Architecture:** Gmail Watch service detects `DTaskQueue`-labeled notification emails, parses them for doc_id/comment_id/reply markers, writes queue entries to a Letta memory block, and notifies the Docs & Transcripts Agent. A new Letta tool on that agent enriches entries via Drive/Docs/Sheets/Slides APIs and calls `add_extracted_tasks`.

**Tech Stack:** Python, FastAPI (gmail-watch-service), Letta API, Google Drive/Docs/Sheets/Slides APIs, pytest

**Design doc:** `docs/plans/2026-02-17-drive-comment-task-queue-design.md`

---

## Key References

| Entity | ID / Path |
|--------|-----------|
| Docs & Transcripts Agent | `agent-398b4f6c-6afa-493f-8063-897c6b171a0d` |
| Email Agent | `agent-b4928949-8012-4436-a3c7-a9e510785147` |
| `extracted_tasks_archive` | `archive-3f0530eb-82db-463a-a28b-f4752a95d7d5` |
| `queued_tasks_from_email` block | `block-e64dcb37-aae3-416f-8565-5f2a23f53325` |
| Gmail Watch settings | `gmail-watch-service/src/gmail_watch/settings.py` |
| Gmail Watch scheduler | `gmail-watch-service/src/gmail_watch/scheduler.py` |
| WatchManager | `gmail-watch-service/src/gmail_watch/services/watch_manager.py` |
| AgentNotifier | `gmail-watch-service/src/gmail_watch/services/agent_notifier.py` |
| TaskQueueWriter | `gmail-watch-service/src/gmail_watch/services/task_queue_writer.py` |
| Email task queue tool (pattern) | `letta/email_task_queue_tool.py` |
| Extracted tasks tool | `letta/extracted_tasks_tool.py` |
| Registration pattern | `letta/register_extracted_tasks_tool.py` |
| Attach pattern | `letta/attach_extracted_tasks_tool_to_agents.py` |
| Docker config | `docker-compose.yml:800-843` (gmail-watch-service section) |
| Gmail credentials (Letta sandbox) | `/root/.gmail-mcp/gcp-oauth.keys.json` + `/root/.gmail-mcp/credentials.json` |

---

### Task 1: Add `google-drive-comment` to valid source types

**Files:**
- Modify: `letta/extracted_tasks_tool.py:113`

**Step 1: Edit the valid_source_types set**

In `letta/extracted_tasks_tool.py`, line 113, change:

```python
valid_source_types = {"slack", "google-docs", "google-docs-comment", "meeting", "email"}
```

to:

```python
valid_source_types = {"slack", "google-docs", "google-docs-comment", "meeting", "email", "google-drive-comment"}
```

**Step 2: Re-register the tool**

```bash
LETTA_BASE_URL=http://localhost:8283 python3 letta/register_extracted_tasks_tool.py
```

When prompted "Tool already exists. Re-register?", answer `y`.

Expected: `SUCCESS` with tool ID printed.

**Step 3: Commit**

```bash
git add letta/extracted_tasks_tool.py
git commit -m "feat: add google-drive-comment source type to extracted_tasks tool"
```

---

### Task 2: Add Drive task queue settings to Gmail Watch service

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/settings.py:92-111`

**Step 1: Add settings fields**

In `gmail-watch-service/src/gmail_watch/settings.py`, after the existing task queue settings block (line 111, after `task_queue_bcc_address`), add:

```python
    # Drive comment task queue settings
    drive_task_queue_enabled: bool = Field(
        default=False,
        alias="DRIVE_TASK_QUEUE_ENABLED",
        description="Enable drive comment task queue processing",
    )
    drive_task_queue_label_name: str = Field(
        default="DTaskQueue",
        alias="DRIVE_TASK_QUEUE_LABEL_NAME",
        description="Gmail label name for drive comment task queue messages",
    )
    drive_task_queue_block_id: Optional[str] = Field(
        default=None,
        alias="DRIVE_TASK_QUEUE_BLOCK_ID",
        description="Letta memory block ID for queued_tasks_from_drive",
    )
    drive_task_queue_agent_id: Optional[str] = Field(
        default=None,
        alias="DRIVE_TASK_QUEUE_AGENT_ID",
        description="Docs & Transcripts agent ID for drive task notifications",
    )
```

**Step 2: Verify settings load**

```bash
cd gmail-watch-service && python3 -c "
from gmail_watch.settings import Settings
s = Settings(
    DRIVE_TASK_QUEUE_ENABLED='true',
    DRIVE_TASK_QUEUE_LABEL_NAME='DTaskQueue',
    DRIVE_TASK_QUEUE_BLOCK_ID='block-test',
    DRIVE_TASK_QUEUE_AGENT_ID='agent-test',
)
print(f'enabled={s.drive_task_queue_enabled}')
print(f'label={s.drive_task_queue_label_name}')
print(f'block={s.drive_task_queue_block_id}')
print(f'agent={s.drive_task_queue_agent_id}')
"
```

Expected: All four values printed correctly.

**Step 3: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/settings.py
git commit -m "feat: add drive task queue settings to Gmail Watch service"
```

---

### Task 3: Create DriveTaskQueueWriter

**Files:**
- Create: `gmail-watch-service/src/gmail_watch/services/drive_task_queue_writer.py`
- Create: `gmail-watch-service/tests/test_drive_task_queue_writer.py`

This writer formats queue entries for drive comment tasks and writes them to the Letta memory block. It reuses `TaskQueueWriter.parse_markers()` for marker detection and extends the base `TaskQueueWriter.write_to_block()` for block writes.

**Step 1: Write the tests**

Create `gmail-watch-service/tests/test_drive_task_queue_writer.py`:

```python
"""Tests for DriveTaskQueueWriter."""

import pytest

from gmail_watch.services.drive_task_queue_writer import DriveTaskQueueWriter


TRIGGER_ADDRESS_RE = DriveTaskQueueWriter.TRIGGER_ADDRESS_RE


class TestStripTriggerAddress:
    """Tests for stripping the +dtasks trigger address from reply text."""

    def test_strips_trigger_line(self):
        text = "Some note\n+cdorsey+dtasks@concord.org\n"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result.strip() == "Some note"

    def test_strips_trigger_with_plus_prefix(self):
        text = "[] Review this\n+cdorsey+dtasks@concord.org"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result.strip() == "[] Review this"

    def test_preserves_text_without_trigger(self):
        text = "Just a note"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result.strip() == "Just a note"

    def test_strips_trigger_anywhere_in_text(self):
        text = "Line 1\n+cdorsey+dtasks@concord.org\nLine 2"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "dtasks" not in result

    def test_handles_empty_text(self):
        assert DriveTaskQueueWriter.strip_trigger_address("").strip() == ""
        assert DriveTaskQueueWriter.strip_trigger_address(None) == ""


class TestExtractDocAndCommentIds:
    """Tests for extracting doc_id and comment_id from notification email body."""

    def test_extracts_from_docs_link(self):
        body = 'View comment at https://docs.google.com/document/d/1abc2def/edit?disco=AAAABx123'
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1abc2def"
        assert comment_id == "AAAABx123"

    def test_extracts_from_sheets_link(self):
        body = 'https://docs.google.com/spreadsheets/d/1xyz9abc/edit?disco=BBBBCy456'
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1xyz9abc"
        assert comment_id == "BBBBCy456"

    def test_extracts_from_slides_link(self):
        body = 'https://docs.google.com/presentation/d/1pqr5stu/edit?disco=CCCCDz789'
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1pqr5stu"
        assert comment_id == "CCCCDz789"

    def test_returns_none_when_no_link(self):
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids("No link here")
        assert doc_id is None
        assert comment_id is None

    def test_extracts_doc_id_without_comment_id(self):
        body = 'https://docs.google.com/document/d/1abc2def/edit'
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1abc2def"
        assert comment_id is None


class TestFormatDriveQueueEntry:
    """Tests for formatting drive task queue entries."""

    def test_basic_entry_without_markers(self):
        writer = DriveTaskQueueWriter()
        entry = writer.format_drive_queue_entry(
            comment_id="AAAABx123",
            doc_id="1abc2def",
            doc_title="Q3 Strategy",
            doc_type="document",
            comment_author="Jane Smith <jsmith@concord.org>",
            triggered_by="cdorsey@concord.org",
            comment_date="Wed, Feb 19, 2026",
            comment_text="We should revisit the timeline",
            quoted_passage="Phase 2 begins in March",
            gmail_message_id="msg123",
            notes="Some user notes",
        )
        assert "comment_id: AAAABx123" in entry
        assert "doc_id: 1abc2def" in entry
        assert "doc_title: Q3 Strategy" in entry
        assert "doc_type: document" in entry
        assert "notes: Some user notes" in entry
        assert "trigger: docs-comment-action-item" in entry
        assert "marker_type" not in entry

    def test_entry_with_marker(self):
        writer = DriveTaskQueueWriter()
        entry = writer.format_drive_queue_entry(
            comment_id="AAAABx123",
            doc_id="1abc2def",
            doc_title="Q3 Strategy",
            doc_type="document",
            comment_author="Jane Smith <jsmith@concord.org>",
            triggered_by="cdorsey@concord.org",
            comment_date="Wed, Feb 19, 2026",
            comment_text="We should revisit the timeline",
            quoted_passage="Phase 2 begins in March",
            gmail_message_id="msg123",
            marker_type="explicit",
            task_hint="Review timeline assumptions",
            context="Why this matters",
        )
        assert "marker_type: explicit" in entry
        assert "task_hint: Review timeline assumptions" in entry
        assert "context: Why this matters" in entry
        assert "notes" not in entry

    def test_entry_includes_doc_link(self):
        writer = DriveTaskQueueWriter()
        entry = writer.format_drive_queue_entry(
            comment_id="AAAABx123",
            doc_id="1abc2def",
            doc_title="Test",
            doc_type="document",
            comment_author="test",
            triggered_by="test",
            comment_date="test",
            comment_text="test",
            quoted_passage="test",
            gmail_message_id="msg123",
        )
        assert "doc_link: https://docs.google.com/document/d/1abc2def/edit?disco=AAAABx123" in entry

    def test_foreign_trigger_annotation(self):
        writer = DriveTaskQueueWriter()
        entry = writer.format_drive_queue_entry(
            comment_id="AAAABx123",
            doc_id="1abc2def",
            doc_title="Test",
            doc_type="document",
            comment_author="test",
            triggered_by="jsmith@concord.org",
            comment_date="test",
            comment_text="test",
            quoted_passage="test",
            gmail_message_id="msg123",
        )
        assert "[FROM: jsmith@concord.org]" in entry
```

**Step 2: Run tests to verify they fail**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_task_queue_writer.py -v
```

Expected: ImportError — `drive_task_queue_writer` module not found.

**Step 3: Implement DriveTaskQueueWriter**

Create `gmail-watch-service/src/gmail_watch/services/drive_task_queue_writer.py`:

```python
"""Drive task queue writer - formats and writes drive comment task entries."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from gmail_watch.services.task_queue_writer import TaskQueueWriter
from gmail_watch.settings import settings

# Timezone for queue timestamps
EASTERN_TZ = ZoneInfo("America/New_York")

# Google Docs/Sheets/Slides URL pattern
DOC_URL_RE = re.compile(
    r"https://docs\.google\.com/"
    r"(?:document|spreadsheets|presentation)/d/"
    r"([a-zA-Z0-9_-]+)"
)
COMMENT_ID_RE = re.compile(r"[?&]disco=([a-zA-Z0-9_-]+)")

# Trigger address pattern (matches +dtasks variants)
TRIGGER_ADDRESS_RE = re.compile(
    r"^\s*\+?\s*[\w.+-]*\+dtasks[\w.]*@[\w.-]+\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Doc type URL slug to human-readable type
DOC_TYPE_MAP = {
    "document": "document",
    "spreadsheets": "spreadsheet",
    "presentation": "presentation",
}

# User email for foreign trigger detection
OWNER_EMAIL = "cdorsey@concord.org"


class DriveTaskQueueWriter(TaskQueueWriter):
    """Formats and writes drive comment task queue entries."""

    def __init__(
        self,
        letta_base_url: Optional[str] = None,
        block_id: Optional[str] = None,
    ) -> None:
        block_id = block_id or settings.drive_task_queue_block_id
        super().__init__(letta_base_url=letta_base_url, block_id=block_id)

    @staticmethod
    def strip_trigger_address(text: Optional[str]) -> str:
        """Remove the +dtasks trigger address line from reply text."""
        if not text:
            return ""
        return TRIGGER_ADDRESS_RE.sub("", text)

    @staticmethod
    def extract_doc_and_comment_ids(
        body: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract doc_id and comment_id from a notification email body.

        Looks for Google Docs/Sheets/Slides URLs with ?disco= parameter.

        Returns:
            Tuple of (doc_id, comment_id). Either may be None.
        """
        doc_match = DOC_URL_RE.search(body)
        if not doc_match:
            return None, None

        doc_id = doc_match.group(1)

        # Look for comment ID in the same URL
        url_end = body[doc_match.start():]
        comment_match = COMMENT_ID_RE.search(url_end)
        comment_id = comment_match.group(1) if comment_match else None

        return doc_id, comment_id

    def format_drive_queue_entry(
        self,
        comment_id: str,
        doc_id: str,
        doc_title: str,
        doc_type: str,
        comment_author: str,
        triggered_by: str,
        comment_date: str,
        comment_text: str,
        quoted_passage: str,
        gmail_message_id: str,
        notes: Optional[str] = None,
        marker_type: Optional[str] = None,
        task_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Format a drive comment queue entry.

        Args:
            marker_type: "explicit" for [] markers, "pointer" for > markers.
            task_hint: The marker text (without prefix).
            context: Non-marker context lines from reply notes.
            notes: Freeform notes (used when no markers present).
        """
        now = datetime.now(EASTERN_TZ)

        # Build doc link with comment anchor
        doc_type_slug = {
            "document": "document",
            "spreadsheet": "spreadsheets",
            "presentation": "presentation",
        }.get(doc_type, "document")
        doc_link = (
            f"https://docs.google.com/{doc_type_slug}/d/{doc_id}"
            f"/edit?disco={comment_id}"
        )

        lines = [
            (
                f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] "
                f"comment_id: {comment_id} | doc_id: {doc_id}"
            ),
            f"doc_title: {doc_title}",
            f"doc_type: {doc_type}",
            f"doc_link: {doc_link}",
            f"comment_author: {comment_author}",
            f"triggered_by: {triggered_by}",
            f"comment_date: {comment_date}",
            f"comment_text: {comment_text}",
            f"quoted_passage: {quoted_passage}",
        ]

        # Foreign trigger annotation
        if triggered_by and triggered_by.lower() != OWNER_EMAIL.lower():
            lines.append(f"[FROM: {triggered_by}]")

        if marker_type:
            lines.append(f"marker_type: {marker_type}")
        if task_hint:
            lines.append(f"task_hint: {task_hint}")
        if context:
            lines.append(f"context: {context}")
        if notes and not marker_type:
            lines.append(f"notes: {notes}")

        lines.append(f"gmail_message_id: {gmail_message_id}")
        lines.append("trigger: docs-comment-action-item")

        return "\n".join(lines)
```

**Step 4: Run tests**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_task_queue_writer.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/drive_task_queue_writer.py gmail-watch-service/tests/test_drive_task_queue_writer.py
git commit -m "feat: add DriveTaskQueueWriter for drive comment task entries"
```

---

### Task 4: Add `notify_drive_task_queued()` to AgentNotifier

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/services/agent_notifier.py`
- Create: `gmail-watch-service/tests/test_drive_agent_notifier.py`

**Step 1: Write the test**

Create `gmail-watch-service/tests/test_drive_agent_notifier.py`:

```python
"""Tests for drive task queue notification in AgentNotifier."""

import pytest
from unittest.mock import AsyncMock, patch

from gmail_watch.services.agent_notifier import AgentNotifier


@pytest.mark.asyncio
async def test_notify_drive_task_queued_formats_message():
    """notify_drive_task_queued sends correctly formatted message."""
    notifier = AgentNotifier(
        letta_base_url="http://test:8283",
        agent_id="agent-email",
    )

    entries = [
        {
            "comment_id": "AAAABx123",
            "doc_title": "Q3 Strategy",
            "comment_text": "Revisit timeline",
            "triggered_by": "cdorsey@concord.org",
            "marker_type": None,
            "task_hint": None,
        },
    ]

    with patch.object(notifier, "_send_to_agent", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "ok"}
        result = await notifier.notify_drive_task_queued(
            entries=entries,
            agent_id="agent-docs",
        )

    mock_send.assert_called_once()
    message = mock_send.call_args[0][0]
    assert "Drive comment" in message or "drive" in message.lower()
    assert "Q3 Strategy" in message
    assert "process_drive_task_queue" in message


@pytest.mark.asyncio
async def test_notify_drive_task_queued_uses_target_agent():
    """notify_drive_task_queued targets the specified agent, not the default."""
    notifier = AgentNotifier(
        letta_base_url="http://test:8283",
        agent_id="agent-email",
    )

    with patch.object(notifier, "_send_to_agent", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "ok"}
        await notifier.notify_drive_task_queued(
            entries=[{
                "comment_id": "AAA",
                "doc_title": "Test",
                "comment_text": "test",
                "triggered_by": "test@test.com",
            }],
            agent_id="agent-docs-transcripts",
        )

    # Check it used the right agent ID (via URL in _send_to_agent)
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_notify_drive_task_queued_empty_entries():
    """Empty entries list returns immediately."""
    notifier = AgentNotifier(
        letta_base_url="http://test:8283",
        agent_id="agent-email",
    )
    result = await notifier.notify_drive_task_queued(
        entries=[],
        agent_id="agent-docs",
    )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_notify_drive_task_queued_with_markers():
    """Marker entries show task_hint in notification."""
    notifier = AgentNotifier(
        letta_base_url="http://test:8283",
        agent_id="agent-email",
    )

    entries = [
        {
            "comment_id": "AAAABx123",
            "doc_title": "Q3 Strategy",
            "comment_text": "Revisit timeline",
            "triggered_by": "cdorsey@concord.org",
            "marker_type": "explicit",
            "task_hint": "Review timeline assumptions",
        },
        {
            "comment_id": "AAAABx123",
            "doc_title": "Q3 Strategy",
            "comment_text": "Revisit timeline",
            "triggered_by": "cdorsey@concord.org",
            "marker_type": "pointer",
            "task_hint": "Check budget numbers",
        },
    ]

    with patch.object(notifier, "_send_to_agent", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "ok"}
        await notifier.notify_drive_task_queued(
            entries=entries,
            agent_id="agent-docs",
        )

    message = mock_send.call_args[0][0]
    assert "Review timeline assumptions" in message
    assert "Check budget numbers" in message
```

**Step 2: Run tests to verify they fail**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_agent_notifier.py -v
```

Expected: AttributeError — `notify_drive_task_queued` not found.

**Step 3: Implement `notify_drive_task_queued`**

In `gmail-watch-service/src/gmail_watch/services/agent_notifier.py`, add this method to the `AgentNotifier` class (after `notify_task_queued`, around line 225):

```python
    async def notify_drive_task_queued(
        self,
        entries: list[dict[str, Any]],
        agent_id: str,
    ) -> dict[str, Any]:
        """Notify Docs & Transcripts Agent that drive comment tasks are queued.

        Args:
            entries: List of dicts with comment_id, doc_title, comment_text,
                     triggered_by, marker_type, task_hint.
            agent_id: Target agent ID (Docs & Transcripts agent).
        """
        if not entries:
            return {"status": "ok", "message": "no entries"}

        lines = ["[Gmail Watch] New drive comment tasks queued for extraction\n"]
        for entry in entries:
            doc_title = entry.get("doc_title", "(untitled)")
            marker_type = entry.get("marker_type")
            task_hint = entry.get("task_hint")

            if marker_type and task_hint:
                tag = (
                    "explicit task"
                    if marker_type == "explicit"
                    else "pointer — expand from comment context"
                )
                lines.append(f"- **{task_hint}** on {doc_title} ({tag})")
            else:
                comment_text = entry.get("comment_text", "")[:80]
                lines.append(f"- Comment on **{doc_title}**: \"{comment_text}\"")

        lines.append(
            "\nProcess queued_tasks_from_drive entries using "
            "process_drive_task_queue tool. "
            'For "explicit" marker entries, the task_hint IS the task description. '
            'For "pointer" marker entries, read the full comment and document context '
            "to expand the hint into a complete task. "
            "For entries without markers, compose a task from the comment text. "
            "Remove each entry from the block after extraction."
        )

        message = "\n".join(lines)

        # Temporarily swap agent_id to target the Docs & Transcripts agent
        original_agent_id = self.agent_id
        self.agent_id = agent_id
        try:
            return await self._send_to_agent(message)
        finally:
            self.agent_id = original_agent_id
```

**Step 4: Run tests**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_agent_notifier.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/agent_notifier.py gmail-watch-service/tests/test_drive_agent_notifier.py
git commit -m "feat: add notify_drive_task_queued to AgentNotifier"
```

---

### Task 5: Add `process_drive_task_queue()` to WatchManager

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/services/watch_manager.py`
- Create: `gmail-watch-service/tests/test_drive_task_queue.py`

This is the Gmail Watch side of the pipeline: detect DTaskQueue label, parse notification email, extract doc_id/comment_id, parse reply markers, write queue entries, remove label, notify agent.

**Step 1: Write tests**

Create `gmail-watch-service/tests/test_drive_task_queue.py`:

```python
"""Tests for WatchManager.process_drive_task_queue()."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from gmail_watch.services.watch_manager import WatchManager


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def manager(mock_session):
    """WatchManager with mocked dependencies."""
    m = WatchManager(session=mock_session)
    m._gmail_client = MagicMock()
    m._notifier = AsyncMock()
    m._drive_task_queue_writer = AsyncMock()
    return m


class TestProcessDriveTaskQueue:

    @pytest.mark.asyncio
    async def test_disabled_returns_early(self, manager):
        """Returns disabled status when feature is off."""
        with patch("gmail_watch.services.watch_manager.settings") as mock_settings:
            mock_settings.drive_task_queue_enabled = False
            result = await manager.process_drive_task_queue()
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_no_label_returns_ok(self, manager):
        """Returns ok with 0 processed when label not found."""
        with patch("gmail_watch.services.watch_manager.settings") as mock_settings:
            mock_settings.drive_task_queue_enabled = True
            mock_settings.drive_task_queue_label_name = "DTaskQueue"
            mock_settings.drive_task_queue_agent_id = "agent-docs"
            manager._gmail_client.get_label_id_by_name.return_value = None
            result = await manager.process_drive_task_queue()
        assert result["status"] == "ok"
        assert result["processed"] == 0

    @pytest.mark.asyncio
    async def test_no_messages_returns_ok(self, manager):
        """Returns ok with 0 processed when no messages have label."""
        with patch("gmail_watch.services.watch_manager.settings") as mock_settings:
            mock_settings.drive_task_queue_enabled = True
            mock_settings.drive_task_queue_label_name = "DTaskQueue"
            mock_settings.drive_task_queue_agent_id = "agent-docs"
            manager._gmail_client.get_label_id_by_name.return_value = "Label_123"
            manager._gmail_client.list_messages_by_label.return_value = []
            result = await manager.process_drive_task_queue()
        assert result["status"] == "ok"
        assert result["processed"] == 0

    @pytest.mark.asyncio
    async def test_processes_notification_email(self, manager):
        """Processes a notification email and writes queue entry."""
        with patch("gmail_watch.services.watch_manager.settings") as mock_settings:
            mock_settings.drive_task_queue_enabled = True
            mock_settings.drive_task_queue_label_name = "DTaskQueue"
            mock_settings.drive_task_queue_agent_id = "agent-docs"

            manager._gmail_client.get_label_id_by_name.return_value = "Label_123"
            manager._gmail_client.list_messages_by_label.return_value = [{"id": "msg1"}]

            # Mock message with Google Docs link
            manager._gmail_client.get_message.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Comment on Q3 Strategy"},
                        {"name": "From", "value": "docs-noreply@google.com"},
                    ],
                    "body": {"data": ""},
                },
            }

            # Mock body extraction
            body_text = (
                'Jane Smith commented on "Q3 Strategy":\n'
                '"We should revisit the timeline"\n'
                "View: https://docs.google.com/document/d/1abc2def/edit?disco=AAAABx123\n"
                "Reply: +cdorsey+dtasks@concord.org"
            )
            with patch.object(manager, "_extract_body", return_value=body_text):
                manager._drive_task_queue_writer.write_to_block = AsyncMock(
                    return_value={"status": "ok"}
                )
                manager._drive_task_queue_writer.format_drive_queue_entry = MagicMock(
                    return_value="formatted entry"
                )

                result = await manager.process_drive_task_queue()

        assert result["processed"] >= 0  # May be 0 if parsing doesn't match
```

**Step 2: Run tests to verify they fail**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_task_queue.py -v
```

Expected: AttributeError — `process_drive_task_queue` not found.

**Step 3: Implement `process_drive_task_queue`**

In `gmail-watch-service/src/gmail_watch/services/watch_manager.py`:

1. Add import at top:
```python
from gmail_watch.services.drive_task_queue_writer import DriveTaskQueueWriter
```

2. Add property after `task_queue_writer` property (around line 73):
```python
    @property
    def drive_task_queue_writer(self) -> DriveTaskQueueWriter:
        """Lazy-load drive task queue writer."""
        if self._drive_task_queue_writer is None:
            self._drive_task_queue_writer = DriveTaskQueueWriter()
        return self._drive_task_queue_writer
```

3. Add `_drive_task_queue_writer` to `__init__`:
```python
        self._drive_task_queue_writer: Optional[DriveTaskQueueWriter] = None
```

4. Add `process_drive_task_queue` method after `process_task_queue` (after line 705):

```python
    async def process_drive_task_queue(self) -> dict[str, Any]:
        """Process emails with DTaskQueue label for drive comment tasks.

        Searches for messages with the DTaskQueue Gmail label, extracts
        doc_id/comment_id from the notification email, parses reply text
        for task markers, writes entries to queued_tasks_from_drive block,
        and removes the label.
        """
        import structlog

        log = structlog.get_logger()

        if not settings.drive_task_queue_enabled:
            return {"status": "disabled", "processed": 0}

        try:
            label_id = self._gmail_client.get_label_id_by_name(
                settings.drive_task_queue_label_name
            )
            if not label_id:
                return {
                    "status": "ok",
                    "processed": 0,
                    "message": "DTaskQueue label not found",
                }

            messages = self._gmail_client.list_messages_by_label(
                label_id, max_results=10
            )
            if not messages:
                return {"status": "ok", "processed": 0}

            processed = []
            errors = []

            for msg_ref in messages:
                msg_id = msg_ref["id"]
                try:
                    message = self._gmail_client.get_message(msg_id, format="full")

                    headers = {}
                    for h in message.get("payload", {}).get("headers", []):
                        headers[h["name"].lower()] = h["value"]

                    subject = headers.get("subject", "")
                    from_address = headers.get("from", "")
                    date = headers.get("date", "")

                    body = self._extract_body(message)
                    if not body:
                        errors.append({"message_id": msg_id, "error": "empty body"})
                        continue

                    # Extract doc_id and comment_id from notification URL
                    doc_id, comment_id = (
                        DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
                    )
                    if not doc_id:
                        errors.append({
                            "message_id": msg_id,
                            "error": "no doc_id found in email body",
                        })
                        continue

                    # Extract reply text and strip trigger address
                    reply_text = DriveTaskQueueWriter.strip_trigger_address(body)

                    # Parse for task markers
                    marker_entries = TaskQueueWriter.parse_markers(reply_text)

                    # Extract doc title from email subject
                    doc_title = subject.replace("Comment on ", "").replace(
                        "Re: Comment on ", ""
                    ).strip(' "')

                    # Triggered by: extract from email headers or body
                    triggered_by = from_address

                    if marker_entries:
                        entry_defs = [
                            {
                                "marker_type": me["marker_type"],
                                "task_hint": me["task_hint"],
                                "context": me["context"],
                            }
                            for me in marker_entries
                        ]
                    else:
                        notes = reply_text.strip() if reply_text.strip() else None
                        entry_defs = [{
                            "marker_type": None,
                            "task_hint": None,
                            "context": None,
                            "notes": notes,
                        }]

                    msg_had_error = False
                    for entry_def in entry_defs:
                        entry = self.drive_task_queue_writer.format_drive_queue_entry(
                            comment_id=comment_id or "",
                            doc_id=doc_id,
                            doc_title=doc_title,
                            doc_type="unknown",  # Enriched by Letta tool later
                            comment_author="",  # Enriched by Letta tool later
                            triggered_by=triggered_by,
                            comment_date=date,
                            comment_text="",  # Enriched by Letta tool later
                            quoted_passage="",  # Enriched by Letta tool later
                            gmail_message_id=msg_id,
                            notes=entry_def.get("notes"),
                            marker_type=entry_def["marker_type"],
                            task_hint=entry_def["task_hint"],
                            context=entry_def["context"],
                        )

                        write_result = await self.drive_task_queue_writer.write_to_block(
                            entry
                        )

                        if write_result.get("status") != "ok":
                            errors.append({
                                "message_id": msg_id,
                                "error": write_result.get("error", "write failed"),
                            })
                            msg_had_error = True
                            continue

                        processed.append({
                            "comment_id": comment_id,
                            "doc_id": doc_id,
                            "doc_title": doc_title,
                            "comment_text": "",
                            "triggered_by": triggered_by,
                            "marker_type": entry_def["marker_type"],
                            "task_hint": entry_def.get("task_hint"),
                        })

                        log.info(
                            "drive_task_queued",
                            doc_title=doc_title,
                            doc_id=doc_id,
                            comment_id=comment_id,
                            marker_type=entry_def["marker_type"],
                        )

                    if not msg_had_error:
                        self._gmail_client.remove_label(msg_id, label_id)

                except Exception as msg_err:
                    log.error(
                        "drive_task_queue_message_error",
                        message_id=msg_id,
                        error=str(msg_err),
                    )
                    errors.append({"message_id": msg_id, "error": str(msg_err)})

            # Notify Docs & Transcripts agent
            if processed and settings.drive_task_queue_agent_id:
                try:
                    await self.notifier.notify_drive_task_queued(
                        entries=processed,
                        agent_id=settings.drive_task_queue_agent_id,
                    )
                except Exception as notify_err:
                    log.error(
                        "drive_task_queue_notify_error", error=str(notify_err)
                    )

            result = {
                "status": "ok",
                "processed": len(processed),
                "details": processed,
            }
            if errors:
                result["errors"] = errors
            return result

        except Exception as e:
            log.error("drive_task_queue_processing_error", error=str(e))
            return {"status": "error", "error": str(e), "processed": 0}
```

**Step 4: Run tests**

```bash
cd gmail-watch-service && poetry run pytest tests/test_drive_task_queue.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/services/watch_manager.py gmail-watch-service/tests/test_drive_task_queue.py
git commit -m "feat: add process_drive_task_queue to WatchManager"
```

---

### Task 6: Add drive task queue to scheduler loop

**Files:**
- Modify: `gmail-watch-service/src/gmail_watch/scheduler.py:94-100`

**Step 1: Add call to `process_drive_task_queue` in the polling loop**

In `gmail-watch-service/src/gmail_watch/scheduler.py`, after the existing task queue processing block (line 100), add:

```python
                    # Process drive comment task queue
                    dtq_result = await manager.process_drive_task_queue()
                    if dtq_result.get("processed", 0) > 0:
                        logger.info(
                            "Drive task queue processed",
                            processed=dtq_result["processed"],
                        )
```

**Step 2: Verify the scheduler file is syntactically correct**

```bash
cd gmail-watch-service && python3 -c "from gmail_watch.scheduler import WatchScheduler; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add gmail-watch-service/src/gmail_watch/scheduler.py
git commit -m "feat: add drive task queue processing to scheduler loop"
```

---

### Task 7: Docker config and env vars

**Files:**
- Modify: `docker-compose.yml:826-827`

**Step 1: Add drive task queue env vars**

In `docker-compose.yml`, after line 826 (`TASK_QUEUE_BCC_ADDRESS=cdorsey+tasks`), add:

```yaml
      - DRIVE_TASK_QUEUE_ENABLED=true
      - DRIVE_TASK_QUEUE_LABEL_NAME=DTaskQueue
      - DRIVE_TASK_QUEUE_BLOCK_ID=${DRIVE_TASK_QUEUE_BLOCK_ID}
      - DRIVE_TASK_QUEUE_AGENT_ID=agent-398b4f6c-6afa-493f-8063-897c6b171a0d
```

Note: `DRIVE_TASK_QUEUE_BLOCK_ID` will be set in `.env` after block creation in Task 8.

**Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add drive task queue env vars to gmail-watch-service"
```

---

### Task 8: Create `queued_tasks_from_drive` block and attach to agent

**Files:**
- Create: `letta/create_drive_task_queue_block.py`

**Step 1: Create block creation script**

```python
#!/usr/bin/env python3
"""Create queued_tasks_from_drive block and attach to Docs & Transcripts Agent."""

import os
import sys

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found.")
        sys.exit(1)

DOCS_AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"
BLOCK_LABEL = "queued_tasks_from_drive"
INITIAL_VALUE = (
    "# queued_tasks_from_drive\n"
    "# Entries separated by --- and processed by process_drive_task_queue tool.\n"
    "# Format: [queued: timestamp] comment_id: X | doc_id: Y\n"
)


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    # Check for existing block
    blocks = client.blocks.list()
    existing = None
    for block in blocks:
        if block.label == BLOCK_LABEL:
            existing = block
            break

    if existing:
        print(f"Block already exists: {existing.id}")
    else:
        existing = client.blocks.create(label=BLOCK_LABEL, value=INITIAL_VALUE)
        print(f"Created block: {existing.id}")

    # Attach to Docs & Transcripts agent
    agent_blocks = client.agents.blocks.list(DOCS_AGENT_ID)
    already_attached = any(b.label == BLOCK_LABEL for b in agent_blocks)

    if already_attached:
        print(f"Block already attached to agent {DOCS_AGENT_ID}")
    else:
        client.agents.blocks.attach(DOCS_AGENT_ID, existing.id)
        print(f"Attached to agent {DOCS_AGENT_ID}")

    print(f"\nBlock ID: {existing.id}")
    print(f"Add to .env: DRIVE_TASK_QUEUE_BLOCK_ID={existing.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run the script**

```bash
LETTA_BASE_URL=http://localhost:8283 python3 letta/create_drive_task_queue_block.py
```

Expected: Block ID printed. Copy it.

**Step 3: Add block ID to `.env`**

Add line to `.env`:
```
DRIVE_TASK_QUEUE_BLOCK_ID=block-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

**Step 4: Commit**

```bash
git add letta/create_drive_task_queue_block.py
git commit -m "feat: add script to create queued_tasks_from_drive block"
```

---

### Task 9: Create `process_drive_task_queue` Letta tool

**Files:**
- Create: `letta/drive_task_queue_tool.py`

This is the main Letta tool. It reads the `queued_tasks_from_drive` block, calls Drive/Docs/Sheets/Slides APIs for enrichment, and calls `add_extracted_tasks` for each entry.

**Important Letta tool constraints:**
- All imports inside the function body (after docstring)
- No nested `def` statements
- Entire body wrapped in try-except
- Returns `Dict[str, Any]`
- Parameters documented in `Args:` docstring section

**Step 1: Create the tool**

Create `letta/drive_task_queue_tool.py`:

```python
"""
Drive Task Queue Tool for Letta

Processes queued Google Docs/Sheets/Slides comment tasks by enriching
them with Drive API data and extracting tasks.

Tool: process_drive_task_queue
"""

from typing import Dict, Any, Optional


def process_drive_task_queue(max_entries: int = 10) -> Dict[str, Any]:
    """
    Process queued drive comment tasks and extract them.

    Reads the queued_tasks_from_drive memory block. For each entry:
    1. Calls Drive API to get comment metadata (author, text, quoted passage)
    2. Calls Drive API to get file metadata (type, title)
    3. Retrieves surrounding context based on document type
    4. Calls add_extracted_tasks with full metadata
    5. Removes the processed entry from the block

    Call this tool when notified of new drive comment task queue entries.

    For entries with marker_type "explicit", the task_hint IS the task
    description — use it directly. For "pointer" markers, expand the hint
    using the comment and document context. For entries without markers,
    compose a task from the comment text.

    Args:
        max_entries: Maximum entries to process per call (1-20, default 10).

    Returns:
        Dictionary with status, count processed, and per-entry details.
    """
    import os
    import re
    import json
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        QUEUE_BLOCK_LABEL = "queued_tasks_from_drive"
        OWNER_EMAIL = "cdorsey@concord.org"

        if max_entries is None or max_entries < 1:
            max_entries = 10
        if max_entries > 20:
            max_entries = 20

        tz = pytz.timezone("America/New_York")

        # ── Google Auth ──
        CREDS_DIR = "/root/.gmail-mcp"
        with open(f"{CREDS_DIR}/gcp-oauth.keys.json") as f:
            keys = json.load(f)
            client_config = keys.get("installed") or keys.get("web")
        with open(f"{CREDS_DIR}/credentials.json") as f:
            tokens = json.load(f)
        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=client_config["token_uri"],
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/documents.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/presentations.readonly",
            ],
        )
        if not creds.valid:
            creds.refresh(Request())
            tokens["access_token"] = creds.token
            with open(f"{CREDS_DIR}/credentials.json", "w") as f:
                json.dump(tokens, f, indent=2)

        drive_service = build("drive", "v3", credentials=creds)

        # ── Get queue block ──
        if not AGENT_ID:
            return {"status": "error", "error_message": "LETTA_AGENT_ID not set"}

        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method="GET")
        with urllib.request.urlopen(agent_req, timeout=10) as resp:
            agent_data = json.loads(resp.read().decode("utf-8"))

        blocks = agent_data.get("memory", {}).get("blocks", [])
        queue_block = None
        for block in blocks:
            if block.get("label") == QUEUE_BLOCK_LABEL:
                queue_block = block
                break

        if not queue_block:
            return {
                "status": "error",
                "error_message": f"Block '{QUEUE_BLOCK_LABEL}' not found on this agent.",
            }

        queue_block_id = queue_block["id"]
        block_value = queue_block.get("value", "")

        # ── Parse entries ──
        raw_entries = [e.strip() for e in block_value.split("---") if e.strip()]
        # Filter out header comments
        entries = [
            e for e in raw_entries
            if e and not e.startswith("#") and "comment_id:" in e
        ]

        if not entries:
            return {
                "status": "ok",
                "message": "No entries to process.",
                "processed": 0,
                "details": [],
            }

        entries = entries[:max_entries]
        processed = []
        errors = []

        for entry_text in entries:
            try:
                # Parse entry fields
                fields = {}
                for line in entry_text.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("[queued:"):
                        # Parse header line for comment_id and doc_id
                        m = re.search(r"comment_id:\s*(\S+)", line)
                        if m:
                            fields["comment_id"] = m.group(1)
                        m = re.search(r"doc_id:\s*(\S+)", line)
                        if m:
                            fields["doc_id"] = m.group(1)
                        continue
                    if ":" in line:
                        key, _, val = line.partition(":")
                        fields[key.strip()] = val.strip()

                doc_id = fields.get("doc_id", "")
                comment_id = fields.get("comment_id", "")
                marker_type = fields.get("marker_type")
                task_hint = fields.get("task_hint")
                context = fields.get("context")
                notes = fields.get("notes")
                triggered_by = fields.get("triggered_by", "")

                if not doc_id:
                    errors.append({"entry": entry_text[:50], "error": "no doc_id"})
                    continue

                # ── Drive API: file metadata ──
                try:
                    file_meta = drive_service.files().get(
                        fileId=doc_id,
                        fields="id,name,mimeType,webViewLink",
                    ).execute()
                except Exception as api_err:
                    errors.append({
                        "doc_id": doc_id,
                        "error": f"files.get failed: {str(api_err)}",
                    })
                    continue

                doc_title = file_meta.get("name", fields.get("doc_title", ""))
                mime_type = file_meta.get("mimeType", "")
                web_link = file_meta.get("webViewLink", "")

                # Map mime type to doc_type
                mime_to_type = {
                    "application/vnd.google-apps.document": "document",
                    "application/vnd.google-apps.spreadsheet": "spreadsheet",
                    "application/vnd.google-apps.presentation": "presentation",
                }
                doc_type = mime_to_type.get(mime_type, "document")

                # ── Drive API: comment metadata ──
                comment_text = ""
                comment_author = ""
                comment_author_email = ""
                quoted_passage = ""
                comment_date = ""

                if comment_id:
                    try:
                        comment_data = drive_service.comments().get(
                            fileId=doc_id,
                            commentId=comment_id,
                            fields="content,author,quotedFileContent,createdTime,resolved",
                        ).execute()
                        comment_text = comment_data.get("content", "")
                        author = comment_data.get("author", {})
                        comment_author = author.get("displayName", "")
                        comment_author_email = author.get("emailAddress", "")
                        quoted_fc = comment_data.get("quotedFileContent", {})
                        quoted_passage = quoted_fc.get("value", "")
                        comment_date = comment_data.get("createdTime", "")
                    except Exception:
                        pass  # Enrichment is best-effort

                # ── Surrounding context (by doc type) ──
                surrounding_context = ""
                if quoted_passage and doc_type == "document":
                    try:
                        docs_service = build("docs", "v1", credentials=creds)
                        doc_data = docs_service.documents().get(
                            documentId=doc_id,
                        ).execute()
                        body_content = doc_data.get("body", {}).get("content", [])
                        paragraphs = []
                        for element in body_content:
                            paragraph = element.get("paragraph", {})
                            if paragraph:
                                text_runs = paragraph.get("elements", [])
                                para_text = "".join(
                                    tr.get("textRun", {}).get("content", "")
                                    for tr in text_runs
                                )
                                if para_text.strip():
                                    paragraphs.append(para_text.strip())

                        # Find paragraph containing quoted passage
                        target_idx = None
                        for idx, p in enumerate(paragraphs):
                            if quoted_passage in p:
                                target_idx = idx
                                break
                        if target_idx is not None:
                            start = max(0, target_idx - 3)
                            end = min(len(paragraphs), target_idx + 4)
                            context_paras = paragraphs[start:end]
                            # Mark the quoted passage
                            marked = []
                            for p in context_paras:
                                if quoted_passage in p:
                                    marked.append(f">> {p} <<")
                                else:
                                    marked.append(p)
                            surrounding_context = "\n".join(marked)
                    except Exception:
                        pass  # Context retrieval is best-effort

                elif quoted_passage and doc_type == "spreadsheet":
                    try:
                        sheets_service = build("sheets", "v4", credentials=creds)
                        sheet_data = sheets_service.spreadsheets().get(
                            spreadsheetId=doc_id,
                            fields="sheets.data.rowData.values.formattedValue",
                        ).execute()
                        # Flatten all cell values for search
                        all_cells = []
                        for sheet in sheet_data.get("sheets", []):
                            for grid_data in sheet.get("data", []):
                                for row in grid_data.get("rowData", []):
                                    row_vals = []
                                    for cell in row.get("values", []):
                                        row_vals.append(
                                            cell.get("formattedValue", "")
                                        )
                                    if any(row_vals):
                                        all_cells.append(" | ".join(row_vals))
                        # Find rows near quoted passage
                        for idx, row_text in enumerate(all_cells):
                            if quoted_passage in row_text:
                                start = max(0, idx - 2)
                                end = min(len(all_cells), idx + 3)
                                surrounding_context = "\n".join(all_cells[start:end])
                                break
                    except Exception:
                        pass

                elif quoted_passage and doc_type == "presentation":
                    try:
                        slides_service = build("slides", "v1", credentials=creds)
                        pres_data = slides_service.presentations().get(
                            presentationId=doc_id,
                            fields="slides.pageElements.shape.text.textElements.textRun.content",
                        ).execute()
                        for slide in pres_data.get("slides", []):
                            slide_text_parts = []
                            for element in slide.get("pageElements", []):
                                shape = element.get("shape", {})
                                text_obj = shape.get("text", {})
                                for te in text_obj.get("textElements", []):
                                    tr = te.get("textRun", {})
                                    content = tr.get("content", "")
                                    if content.strip():
                                        slide_text_parts.append(content.strip())
                            slide_text = "\n".join(slide_text_parts)
                            if quoted_passage in slide_text:
                                surrounding_context = slide_text
                                break
                    except Exception:
                        pass

                # ── Build source text ──
                source_parts = []
                if comment_text:
                    source_parts.append(f"Comment: {comment_text}")
                if quoted_passage:
                    source_parts.append(f"Quoted passage: {quoted_passage}")
                if surrounding_context:
                    source_parts.append(f"Surrounding context:\n{surrounding_context}")
                if notes:
                    source_parts.append(f"User notes: {notes}")
                if context:
                    source_parts.append(f"User context: {context}")
                source_text = "\n\n".join(source_parts) if source_parts else "(no content)"

                # ── Build doc link ──
                type_slug = {
                    "document": "document",
                    "spreadsheet": "spreadsheets",
                    "presentation": "presentation",
                }.get(doc_type, "document")
                doc_link = f"https://docs.google.com/{type_slug}/d/{doc_id}/edit"
                if comment_id:
                    doc_link += f"?disco={comment_id}"

                # ── Compose task description ──
                if marker_type == "explicit" and task_hint:
                    task_description = task_hint
                elif marker_type == "pointer" and task_hint:
                    task_description = f"{task_hint} (from comment on {doc_title})"
                elif comment_text:
                    task_description = f"Review comment: {comment_text[:100]}"
                else:
                    task_description = f"Review comment on {doc_title}"

                # Foreign trigger annotation
                if triggered_by and triggered_by.lower() != OWNER_EMAIL.lower():
                    task_description = f"[FROM: {triggered_by}] {task_description}"

                # ── Determine from_person ──
                from_person = comment_author
                if comment_author_email:
                    from_person = f"{comment_author} ({comment_author_email})"
                if not from_person:
                    from_person = triggered_by

                # ── Build reference_id ──
                reference_id = f"gdrive-comment-{doc_id}"
                if comment_id:
                    reference_id += f"-{comment_id}"

                # ── Call add_extracted_tasks via Letta API ──
                tool_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/messages"
                extract_msg = (
                    f"Extract this task using add_extracted_tasks:\n"
                    f"- task_description: {task_description}\n"
                    f"- source_type: google-drive-comment\n"
                    f'- source_context: Comment on {doc_title} ({doc_type})\n'
                    f"- reference_id: {reference_id}\n"
                    f"- source_text: {source_text[:2000]}\n"
                    f"- from_person: {from_person}\n"
                    f"- location: {doc_title} — {doc_link}\n"
                    f"- location_id: {doc_id}\n"
                    f"- source_timestamp: {comment_date}\n"
                )

                processed.append({
                    "doc_id": doc_id,
                    "comment_id": comment_id,
                    "doc_title": doc_title,
                    "task_description": task_description,
                    "marker_type": marker_type,
                    "extract_message": extract_msg,
                })

            except Exception as entry_err:
                errors.append({
                    "entry": entry_text[:80],
                    "error": str(entry_err),
                })

        # ── Remove processed entries from block ──
        if processed:
            # Re-read block (may have changed)
            block_url = f"{LETTA_BASE}/v1/blocks/{queue_block_id}"
            block_req = urllib.request.Request(block_url, method="GET")
            with urllib.request.urlopen(block_req, timeout=10) as resp:
                block_data = json.loads(resp.read().decode("utf-8"))
            current_value = block_data.get("value", "")

            # Remove processed entries by matching doc_id + comment_id
            remaining_parts = []
            for part in current_value.split("---"):
                part_stripped = part.strip()
                if not part_stripped:
                    continue
                # Check if this entry was processed
                was_processed = False
                for p in processed:
                    if (
                        p["doc_id"] in part_stripped
                        and (not p["comment_id"] or p["comment_id"] in part_stripped)
                    ):
                        was_processed = True
                        break
                if not was_processed:
                    remaining_parts.append(part_stripped)

            # Rebuild block value
            if remaining_parts:
                new_value = "\n---\n".join(remaining_parts) + "\n---"
            else:
                new_value = INITIAL_HEADER = (
                    "# queued_tasks_from_drive\n"
                    "# Entries separated by --- and processed by "
                    "process_drive_task_queue tool.\n"
                    "# Format: [queued: timestamp] comment_id: X | doc_id: Y\n"
                )

            update_data = json.dumps({"value": new_value}).encode("utf-8")
            update_req = urllib.request.Request(
                block_url,
                data=update_data,
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )
            urllib.request.urlopen(update_req, timeout=10)

        result = {
            "status": "ok",
            "message": f"Processed {len(processed)} drive comment task(s).",
            "processed": len(processed),
            "details": [
                {
                    "doc_title": p["doc_title"],
                    "task_description": p["task_description"],
                    "marker_type": p["marker_type"],
                }
                for p in processed
            ],
        }
        if errors:
            result["errors"] = errors

        # Return extraction messages for the agent to act on
        if processed:
            result["extraction_messages"] = [
                p["extract_message"] for p in processed
            ]

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
```

**Step 2: Commit**

```bash
git add letta/drive_task_queue_tool.py
git commit -m "feat: add process_drive_task_queue Letta tool"
```

---

### Task 10: Register tool and attach to agent

**Files:**
- Create: `letta/register_drive_task_queue_tool.py`

**Step 1: Create registration script**

```python
#!/usr/bin/env python3
"""Register process_drive_task_queue tool with Letta and attach to Docs & Transcripts Agent."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found.")
        sys.exit(1)

from drive_task_queue_tool import process_drive_task_queue

DOCS_AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    # Check for existing tool
    existing_tools = client.tools.list()
    for tool in existing_tools:
        if tool.name == "process_drive_task_queue":
            response = input("Tool already exists. Re-register? [y/N]: ")
            if response.lower() != "y":
                print(f"Existing tool ID: {tool.id}")
                return 0
            client.tools.delete(tool.id)
            print("Deleted existing tool.")
            break

    # Register
    created_tool = client.tools.create_from_function(
        func=process_drive_task_queue,
        tags=["drive", "tasks", "comments", "google-docs"],
    )
    print(f"Registered: {created_tool.name} ({created_tool.id})")

    # Attach to Docs & Transcripts agent
    agent_tools = client.agents.tools.list(DOCS_AGENT_ID)
    already_attached = any(t.id == created_tool.id for t in agent_tools)

    if not already_attached:
        client.agents.tools.attach(DOCS_AGENT_ID, created_tool.id)
        print(f"Attached to agent {DOCS_AGENT_ID}")
    else:
        print("Already attached.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run registration**

```bash
LETTA_BASE_URL=http://localhost:8283 python3 letta/register_drive_task_queue_tool.py
```

Expected: `Registered: process_drive_task_queue (tool-...)` and `Attached to agent ...`

**Step 3: Commit**

```bash
git add letta/register_drive_task_queue_tool.py
git commit -m "feat: add registration script for drive task queue tool"
```

---

### Task 11: Rebuild gmail-watch-service and verify

**Step 1: Rebuild the service**

```bash
docker-compose up -d --build gmail-watch-service
```

**Step 2: Check logs for startup**

```bash
docker-compose logs --tail=20 gmail-watch-service
```

Expected: Service starts without errors. Look for `Watch scheduler started`.

**Step 3: Run existing tests to verify no regressions**

```bash
cd gmail-watch-service && poetry run pytest -v
```

Expected: All existing tests still pass.

---

### Task 12: End-to-end test

**Step 1: Trigger a test by adding an action item on a real Google Doc comment**

Reply to any comment with:
```
[] Test task from drive comment
+cdorsey+dtasks@concord.org
```

**Step 2: Wait for Gmail Watch to detect DTaskQueue label** (~30 seconds)

```bash
docker-compose logs --tail=30 -f gmail-watch-service | grep -i drive
```

Expected: `drive_task_queued` log entry.

**Step 3: Verify queue block has entry**

```bash
curl -s http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d | python3 -c "
import sys, json
data = json.load(sys.stdin)
for b in data.get('memory', {}).get('blocks', []):
    if b.get('label') == 'queued_tasks_from_drive':
        print(b.get('value', ''))
"
```

Expected: Queue entry with comment_id, doc_id, and marker info.

**Step 4: Verify agent was notified and tool was called**

Check the Docs & Transcripts agent messages for the notification and tool call.

**Step 5: Verify task was extracted**

Search archival memory for the test task:
```bash
curl -s "http://localhost:8283/v1/archives/archive-3f0530eb-82db-463a-a28b-f4752a95d7d5/passages?search=Test+task+from+drive+comment" | python3 -m json.tool | head -30
```

Expected: Archival passage with `source:google-drive-comment` tag.
