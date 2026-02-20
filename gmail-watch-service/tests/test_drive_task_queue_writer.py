"""Tests for DriveTaskQueueWriter service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from gmail_watch.services.drive_task_queue_writer import DriveTaskQueueWriter

EASTERN_TZ = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# strip_trigger_address
# ---------------------------------------------------------------------------


class TestStripTriggerAddress:
    """Tests for DriveTaskQueueWriter.strip_trigger_address."""

    def test_removes_trigger_line(self):
        """Strips a line containing the +dtasks trigger address."""
        text = "Please handle this\n+cdorsey+dtasks@concord.org\nThanks"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert "+dtasks" not in result
        assert "Please handle this" in result
        assert "Thanks" in result

    def test_removes_trigger_line_case_insensitive(self):
        """Strips trigger address regardless of case."""
        text = "Note\n+CDorsey+DTASKS@concord.org\nDone"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert "+DTASKS" not in result
        assert "Note" in result
        assert "Done" in result

    def test_removes_line_with_only_trigger(self):
        """Strips a line that is only the trigger address."""
        text = "+cdorsey+dtasks@concord.org"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result.strip() == ""

    def test_preserves_other_text(self):
        """Non-trigger lines are preserved intact."""
        text = "Line one\nLine two\nLine three"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result == text

    def test_handles_empty_string(self):
        """Returns empty string for empty input."""
        assert DriveTaskQueueWriter.strip_trigger_address("") == ""

    def test_handles_none(self):
        """Returns empty string for None input."""
        assert DriveTaskQueueWriter.strip_trigger_address(None) == ""

    def test_handles_variant_plus_address(self):
        """Strips any +dtasks variant address."""
        text = "Check this\nsomeone+dtasks@example.com\nEnd"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert "+dtasks" not in result
        assert "Check this" in result
        assert "End" in result

    def test_strips_leading_trailing_whitespace(self):
        """Result is stripped of leading/trailing whitespace after removal."""
        text = "\n+cdorsey+dtasks@concord.org\nActual content\n"
        result = DriveTaskQueueWriter.strip_trigger_address(text)
        assert result.strip() == "Actual content"


# ---------------------------------------------------------------------------
# extract_doc_and_comment_ids
# ---------------------------------------------------------------------------


class TestExtractDocAndCommentIds:
    """Tests for DriveTaskQueueWriter.extract_doc_and_comment_ids."""

    def test_extracts_from_docs_url(self):
        """Extracts doc_id and comment_id from a Google Docs URL."""
        body = (
            "Someone commented on your doc:\n"
            "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit"
            "?disco=AAAA1234"
        )
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
        assert comment_id == "AAAA1234"

    def test_extracts_from_sheets_url(self):
        """Extracts doc_id and comment_id from a Google Sheets URL."""
        body = (
            "New comment:\n"
            "https://docs.google.com/spreadsheets/d/1SpReAdShEeT_id123/edit"
            "?disco=BBBB5678"
        )
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1SpReAdShEeT_id123"
        assert comment_id == "BBBB5678"

    def test_extracts_from_slides_url(self):
        """Extracts doc_id and comment_id from a Google Slides URL."""
        body = (
            "Comment on slide:\n"
            "https://docs.google.com/presentation/d/1SliDeS_iD-abc/edit"
            "?disco=CCCC9012"
        )
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1SliDeS_iD-abc"
        assert comment_id == "CCCC9012"

    def test_returns_none_when_no_link(self):
        """Returns (None, None) when no Google Docs link found."""
        body = "This is just a plain email with no links."
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id is None
        assert comment_id is None

    def test_extracts_doc_without_comment_id(self):
        """Returns doc_id with None comment_id when disco param missing."""
        body = (
            "Open the doc:\n"
            "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit"
        )
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
        assert comment_id is None

    def test_handles_empty_body(self):
        """Returns (None, None) for empty body."""
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids("")
        assert doc_id is None
        assert comment_id is None

    def test_handles_none_body(self):
        """Returns (None, None) for None body."""
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(None)
        assert doc_id is None
        assert comment_id is None

    def test_extracts_with_extra_query_params(self):
        """Extracts correctly when URL has additional query parameters."""
        body = (
            "https://docs.google.com/document/d/1DocId123/edit"
            "?disco=CommentABC&ts=12345&tab=t.0"
        )
        doc_id, comment_id = DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
        assert doc_id == "1DocId123"
        assert comment_id == "CommentABC"


# ---------------------------------------------------------------------------
# format_drive_queue_entry - basic (no markers)
# ---------------------------------------------------------------------------


class TestFormatDriveQueueEntryBasic:
    """Tests for DriveTaskQueueWriter.format_drive_queue_entry without markers."""

    def setup_method(self):
        """Create writer with mocked settings."""
        with patch(
            "gmail_watch.services.drive_task_queue_writer.settings"
        ) as mock_settings:
            mock_settings.drive_task_queue_block_id = "block-drive-test"
            mock_settings.letta_base_url = "http://letta:8283"
            self.writer = DriveTaskQueueWriter(
                letta_base_url="http://letta:8283",
                block_id="block-drive-test",
            )

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_basic_entry_format(self, mock_dt):
        """Formats a basic queue entry with all required fields."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="AAAA1234",
            doc_id="1aBcDeFgHiJkLmNoPqRsTuVwXyZ",
            doc_title="Project Proposal",
            doc_type="document",
            comment_author="Alice Smith",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="We should revisit this section.",
            gmail_message_id="msg_abc123",
        )

        assert "[queued: 2026-02-19 14:30]" in entry
        assert "comment_id: AAAA1234" in entry
        assert "doc_id: 1aBcDeFgHiJkLmNoPqRsTuVwXyZ" in entry
        assert "doc_title: Project Proposal" in entry
        assert "doc_type: document" in entry
        assert "comment_author: Alice Smith" in entry
        assert "triggered_by: cdorsey@concord.org" in entry
        assert "comment_date: 2026-02-18" in entry
        assert "comment_text: We should revisit this section." in entry
        assert "gmail_message_id: msg_abc123" in entry
        assert "trigger: docs-comment-action-item" in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_includes_doc_link_for_document(self, mock_dt):
        """Constructs correct doc_link for Google Docs."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="CommentXYZ",
            doc_id="DocId123",
            doc_title="My Doc",
            doc_type="document",
            comment_author="Bob",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Fix this.",
            gmail_message_id="msg_001",
        )

        expected_link = (
            "https://docs.google.com/document/d/DocId123/edit?disco=CommentXYZ"
        )
        assert f"doc_link: {expected_link}" in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_includes_doc_link_for_spreadsheet(self, mock_dt):
        """Constructs correct doc_link for Google Sheets."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="CommentXYZ",
            doc_id="SheetId456",
            doc_title="Budget",
            doc_type="spreadsheet",
            comment_author="Carol",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Check totals.",
            gmail_message_id="msg_002",
        )

        expected_link = (
            "https://docs.google.com/spreadsheets/d/SheetId456/edit"
            "?disco=CommentXYZ"
        )
        assert f"doc_link: {expected_link}" in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_includes_doc_link_for_presentation(self, mock_dt):
        """Constructs correct doc_link for Google Slides."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="CommentXYZ",
            doc_id="SlidesId789",
            doc_title="Keynote",
            doc_type="presentation",
            comment_author="Dave",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Add slide.",
            gmail_message_id="msg_003",
        )

        expected_link = (
            "https://docs.google.com/presentation/d/SlidesId789/edit"
            "?disco=CommentXYZ"
        )
        assert f"doc_link: {expected_link}" in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_includes_notes_when_no_markers(self, mock_dt):
        """Includes notes field when no markers are present."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C1",
            doc_id="D1",
            doc_title="Doc",
            doc_type="document",
            comment_author="Author",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Comment.",
            gmail_message_id="msg_004",
            notes="Please review by Friday",
        )

        assert "notes: Please review by Friday" in entry
        assert "marker_type:" not in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_includes_quoted_passage(self, mock_dt):
        """Includes quoted_passage field when provided."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C1",
            doc_id="D1",
            doc_title="Doc",
            doc_type="document",
            comment_author="Author",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Fix this wording.",
            gmail_message_id="msg_005",
            quoted_passage="The quarterly results show...",
        )

        assert "quoted_passage: The quarterly results show..." in entry


# ---------------------------------------------------------------------------
# format_drive_queue_entry - with markers
# ---------------------------------------------------------------------------


class TestFormatDriveQueueEntryWithMarkers:
    """Tests for DriveTaskQueueWriter.format_drive_queue_entry with markers."""

    def setup_method(self):
        """Create writer with mocked settings."""
        with patch(
            "gmail_watch.services.drive_task_queue_writer.settings"
        ) as mock_settings:
            mock_settings.drive_task_queue_block_id = "block-drive-test"
            mock_settings.letta_base_url = "http://letta:8283"
            self.writer = DriveTaskQueueWriter(
                letta_base_url="http://letta:8283",
                block_id="block-drive-test",
            )

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_with_marker_fields(self, mock_dt):
        """Includes marker_type, task_hint, context when provided."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C1",
            doc_id="D1",
            doc_title="Doc",
            doc_type="document",
            comment_author="Author",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Review this section.",
            gmail_message_id="msg_006",
            marker_type="explicit",
            task_hint="Rewrite the intro paragraph",
            context="The intro needs work",
        )

        assert "marker_type: explicit" in entry
        assert "task_hint: Rewrite the intro paragraph" in entry
        assert "context: The intro needs work" in entry
        # notes should NOT be present when markers are present
        assert "notes:" not in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_entry_with_pointer_marker(self, mock_dt):
        """Includes pointer marker_type correctly."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C2",
            doc_id="D2",
            doc_title="Doc 2",
            doc_type="spreadsheet",
            comment_author="Author2",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Check numbers.",
            gmail_message_id="msg_007",
            marker_type="pointer",
            task_hint="Verify Q4 revenue figures",
        )

        assert "marker_type: pointer" in entry
        assert "task_hint: Verify Q4 revenue figures" in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_notes_suppressed_when_markers_present(self, mock_dt):
        """Notes field is suppressed when marker_type is set."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C3",
            doc_id="D3",
            doc_title="Doc 3",
            doc_type="document",
            comment_author="Author3",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Noted.",
            gmail_message_id="msg_008",
            marker_type="explicit",
            task_hint="Fix typo",
            notes="This should not appear",
        )

        assert "notes:" not in entry
        assert "marker_type: explicit" in entry


# ---------------------------------------------------------------------------
# format_drive_queue_entry - foreign trigger annotation
# ---------------------------------------------------------------------------


class TestFormatDriveQueueEntryForeignTrigger:
    """Tests for foreign trigger annotation in format_drive_queue_entry."""

    def setup_method(self):
        """Create writer with mocked settings."""
        with patch(
            "gmail_watch.services.drive_task_queue_writer.settings"
        ) as mock_settings:
            mock_settings.drive_task_queue_block_id = "block-drive-test"
            mock_settings.letta_base_url = "http://letta:8283"
            self.writer = DriveTaskQueueWriter(
                letta_base_url="http://letta:8283",
                block_id="block-drive-test",
            )

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_no_annotation_for_own_email(self, mock_dt):
        """No [FROM: ...] annotation when triggered_by is cdorsey@concord.org."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C1",
            doc_id="D1",
            doc_title="Doc",
            doc_type="document",
            comment_author="Chad Dorsey",
            triggered_by="cdorsey@concord.org",
            comment_date="2026-02-18",
            comment_text="Action needed.",
            gmail_message_id="msg_009",
        )

        assert "[FROM:" not in entry

    @patch(
        "gmail_watch.services.drive_task_queue_writer.datetime",
    )
    def test_annotation_for_foreign_trigger(self, mock_dt):
        """Adds [FROM: email] annotation when triggered_by is not owner."""
        mock_dt.now.return_value = datetime(
            2026, 2, 19, 14, 30, tzinfo=EASTERN_TZ
        )
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        entry = self.writer.format_drive_queue_entry(
            comment_id="C1",
            doc_id="D1",
            doc_title="Doc",
            doc_type="document",
            comment_author="External User",
            triggered_by="external@other.org",
            comment_date="2026-02-18",
            comment_text="Please review.",
            gmail_message_id="msg_010",
        )

        assert "[FROM: external@other.org]" in entry


# ---------------------------------------------------------------------------
# __init__ defaults
# ---------------------------------------------------------------------------


class TestDriveTaskQueueWriterInit:
    """Tests for DriveTaskQueueWriter initialization."""

    def test_uses_settings_defaults(self):
        """Uses drive_task_queue_block_id from settings when not provided."""
        with (
            patch(
                "gmail_watch.services.drive_task_queue_writer.settings"
            ) as mock_drive_settings,
            patch(
                "gmail_watch.services.task_queue_writer.settings"
            ) as mock_parent_settings,
        ):
            mock_drive_settings.drive_task_queue_block_id = "block-from-settings"
            mock_parent_settings.letta_base_url = "http://letta-from-settings:8283"
            mock_parent_settings.task_queue_block_id = "block-from-settings"

            writer = DriveTaskQueueWriter()

            assert writer.block_id == "block-from-settings"
            assert writer.letta_base_url == "http://letta-from-settings:8283"

    def test_override_block_id(self):
        """Allows overriding block_id."""
        with patch(
            "gmail_watch.services.drive_task_queue_writer.settings"
        ) as mock_settings:
            mock_settings.drive_task_queue_block_id = "block-default"
            mock_settings.letta_base_url = "http://letta:8283"

            writer = DriveTaskQueueWriter(block_id="block-custom")

            assert writer.block_id == "block-custom"


# ---------------------------------------------------------------------------
# write_to_block (inherited) - quick smoke test
# ---------------------------------------------------------------------------


class TestDriveTaskQueueWriterWriteToBlock:
    """Smoke test that inherited write_to_block still works."""

    @pytest.mark.asyncio
    async def test_write_to_block_calls_letta_api(self):
        """write_to_block delegates to parent and calls Letta API."""
        with patch(
            "gmail_watch.services.drive_task_queue_writer.settings"
        ) as mock_settings:
            mock_settings.drive_task_queue_block_id = "block-drive-test"
            mock_settings.letta_base_url = "http://letta:8283"

            writer = DriveTaskQueueWriter(
                letta_base_url="http://letta:8283",
                block_id="block-drive-test",
            )

        with patch(
            "gmail_watch.services.task_queue_writer.httpx.AsyncClient"
        ) as mock_client_cls:
            client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = client

            # Mock GET (read current block)
            get_resp = MagicMock()
            get_resp.json.return_value = {"value": "existing content"}
            get_resp.raise_for_status = MagicMock()
            client.get.return_value = get_resp

            # Mock PATCH (write back)
            patch_resp = MagicMock()
            patch_resp.raise_for_status = MagicMock()
            client.patch.return_value = patch_resp

            result = await writer.write_to_block("new entry text")

            assert result["status"] == "ok"
            client.get.assert_called_once()
            client.patch.assert_called_once()
