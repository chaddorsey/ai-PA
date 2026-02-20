"""Drive task queue writer - formats and writes drive comment task entries."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import structlog

from gmail_watch.services.task_queue_writer import TaskQueueWriter
from gmail_watch.settings import settings

logger = structlog.get_logger()

# Timezone for queue timestamps
EASTERN_TZ = ZoneInfo("America/New_York")

# Owner email address (no foreign trigger annotation for this address)
OWNER_EMAIL = "cdorsey@concord.org"

# Pattern matching any +dtasks trigger address (case insensitive)
TRIGGER_ADDRESS_RE = re.compile(r"^.*\+dtasks@.*$", re.IGNORECASE)

# Pattern to extract doc_id and optional comment_id from Google Docs/Sheets/Slides URLs
DOC_URL_RE = re.compile(
    r"https://docs\.google\.com/"
    r"(?:document|spreadsheets|presentation)/d/"
    r"([A-Za-z0-9_-]+)"
    r"/edit"
    r"(?:\?[^#\s]*)?"
)

DISCO_PARAM_RE = re.compile(r"[?&]disco=([A-Za-z0-9_-]+)")

# Map doc_type to URL path segment
DOC_TYPE_TO_PATH = {
    "document": "document",
    "spreadsheet": "spreadsheets",
    "presentation": "presentation",
}


class DriveTaskQueueWriter(TaskQueueWriter):
    """Writes drive comment task queue entries to Letta memory block.

    Extends TaskQueueWriter, reusing write_to_block() and parse_markers()
    while providing drive-specific entry formatting.
    """

    def __init__(
        self,
        letta_base_url: Optional[str] = None,
        block_id: Optional[str] = None,
    ) -> None:
        resolved_block_id = block_id or settings.drive_task_queue_block_id
        super().__init__(
            letta_base_url=letta_base_url,
            block_id=resolved_block_id,
        )

    @staticmethod
    def strip_trigger_address(text: Optional[str]) -> str:
        """Remove lines matching the +dtasks trigger address pattern.

        Handles:
        - +cdorsey+dtasks@concord.org
        - Any +dtasks variant (case insensitive)
        - Lines with just the trigger address

        Args:
            text: The reply text to clean.

        Returns:
            Text with trigger address lines removed.
        """
        if not text:
            return ""

        lines = text.split("\n")
        filtered = [line for line in lines if not TRIGGER_ADDRESS_RE.match(line)]
        return "\n".join(filtered).strip()

    @staticmethod
    def extract_doc_and_comment_ids(
        body: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract doc_id and comment_id from a Google Docs notification email body.

        Looks for URLs like:
        - https://docs.google.com/document/d/{doc_id}/edit?disco={comment_id}
        - https://docs.google.com/spreadsheets/d/{doc_id}/edit?disco={comment_id}
        - https://docs.google.com/presentation/d/{doc_id}/edit?disco={comment_id}

        Args:
            body: The email body text.

        Returns:
            (doc_id, comment_id) tuple where either may be None.
        """
        if not body:
            return (None, None)

        doc_match = DOC_URL_RE.search(body)
        if not doc_match:
            return (None, None)

        doc_id = doc_match.group(1)

        # Extract disco (comment_id) from the query string portion
        full_match = doc_match.group(0)
        disco_match = DISCO_PARAM_RE.search(full_match)
        comment_id = disco_match.group(1) if disco_match else None

        return (doc_id, comment_id)

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
        gmail_message_id: str,
        quoted_passage: Optional[str] = None,
        notes: Optional[str] = None,
        marker_type: Optional[str] = None,
        task_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Format a drive comment queue entry.

        Args:
            comment_id: Google Docs comment identifier.
            doc_id: Google Docs document identifier.
            doc_title: Title of the document.
            doc_type: One of "document", "spreadsheet", "presentation".
            comment_author: Name of the person who wrote the comment.
            triggered_by: Email of the person who triggered the +dtasks action.
            comment_date: Date the comment was made.
            comment_text: The comment text content.
            gmail_message_id: Gmail message ID of the notification email.
            quoted_passage: Text passage the comment is anchored to, if any.
            notes: Free-form notes (shown only when no markers).
            marker_type: "explicit" for [] markers, "pointer" for > markers.
            task_hint: The marker text (without prefix).
            context: Non-marker context lines from user notes.

        Returns:
            Formatted queue entry string.
        """
        now = datetime.now(EASTERN_TZ)

        # Construct doc_link
        path_segment = DOC_TYPE_TO_PATH.get(doc_type, "document")
        doc_link = (
            f"https://docs.google.com/{path_segment}/d/{doc_id}/edit"
            f"?disco={comment_id}"
        )

        lines = [
            (
                f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] "
                f"comment_id: {comment_id} "
                f"| doc_id: {doc_id}"
            ),
            f"doc_title: {doc_title}",
            f"doc_type: {doc_type}",
            f"doc_link: {doc_link}",
            f"comment_author: {comment_author}",
            f"triggered_by: {triggered_by}",
        ]

        # Foreign trigger annotation
        if triggered_by and triggered_by.lower() != OWNER_EMAIL.lower():
            lines.append(f"[FROM: {triggered_by}]")

        lines.extend(
            [
                f"comment_date: {comment_date}",
                f"comment_text: {comment_text}",
            ]
        )

        if quoted_passage:
            lines.append(f"quoted_passage: {quoted_passage}")

        # Marker fields vs notes (same pattern as TaskQueueWriter)
        if marker_type:
            lines.append(f"marker_type: {marker_type}")
        if task_hint:
            lines.append(f"task_hint: {task_hint}")
        if context:
            lines.append(f"context: {context}")
        if notes and not marker_type:
            lines.append(f"notes: {notes}")

        lines.extend(
            [
                f"gmail_message_id: {gmail_message_id}",
                "trigger: docs-comment-action-item",
            ]
        )

        return "\n".join(lines)
