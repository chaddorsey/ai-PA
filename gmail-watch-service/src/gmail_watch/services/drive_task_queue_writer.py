"""Drive task queue writer - formats and writes drive comment task entries."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Optional
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

# Pattern to extract author name and email from notification opening line
# e.g. "Chad Dorsey (cdorsey@concord.org) mentioned you in a comment"
AUTHOR_RE = re.compile(
    r"^(.+?)\s+\(([^)]+@[^)]+)\)\s+(?:mentioned you|replied to a comment)",
)

# Google Docs notification boilerplate markers
COMMENT_SECTION_START_RE = re.compile(r"^\.\s*$", re.MULTILINE)
COMMENT_SECTION_END_RE = re.compile(r"^Open\s*$", re.MULTILINE)

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
    def parse_notification_body(
        body: Optional[str],
    ) -> dict[str, str]:
        """Parse a Google Docs comment notification email body.

        Returns the FIRST comment for backward compat.
        Use parse_all_comments() for multi-comment notifications.

        Returns:
            Dict with keys: author_name, author_email, comment_text.
        """
        comments = DriveTaskQueueWriter.parse_all_comments(body)
        if comments:
            return comments[0]
        return {"author_name": "", "author_email": "", "comment_text": ""}

    @staticmethod
    def parse_all_comments(
        body: Optional[str],
    ) -> list[dict[str, str]]:
        """Parse ALL comments from a Google Docs notification email.

        Google batches multiple comments into a single notification.
        Each comment section follows this pattern:

            .
            {Author Name}
            {comment content lines...}

            Open
            ({URL with disco=COMMENT_ID})

        Returns:
            List of dicts, each with: author_name, author_email,
            comment_text, comment_id, doc_url.
        """
        if not body:
            return []

        # Extract author/email from the opening line (if present)
        default_author = ""
        default_email = ""
        author_match = AUTHOR_RE.match(body.strip())
        if author_match:
            default_author = author_match.group(1).strip()
            default_email = author_match.group(2).strip()

        # Split into comment sections using "." as section start
        # and "Open" as section end
        comments = []
        dot_positions = [m.start() for m in COMMENT_SECTION_START_RE.finditer(body)]
        open_positions = [m.start() for m in COMMENT_SECTION_END_RE.finditer(body)]

        for dot_pos in dot_positions:
            # Find the next "Open" after this dot
            next_open = None
            for op in open_positions:
                if op > dot_pos:
                    next_open = op
                    break
            if next_open is None:
                continue

            raw_section = body[dot_pos:next_open + 4]  # include "Open"
            raw_comment = body[dot_pos + 1:next_open].strip()  # after the "."

            # Extract comment_id from the URL after "Open"
            url_start = body.find("(", next_open)
            url_end = body.find(")", url_start) if url_start > 0 else -1
            comment_id = None
            doc_url = ""
            if url_start > 0 and url_end > url_start:
                doc_url = body[url_start + 1:url_end].strip()
                disco_match = DISCO_PARAM_RE.search(doc_url)
                if disco_match:
                    comment_id = disco_match.group(1)

            # Parse the comment section
            lines = raw_comment.split("\n")
            author_name = ""
            comment_lines = []
            found_author = False

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if re.match(r"^\[.*comment.*hidden\]$", stripped, re.IGNORECASE):
                    continue
                if stripped == "_Assigned to you_":
                    continue
                if not found_author:
                    # First non-empty line is the author name
                    author_name = stripped
                    found_author = True
                    continue
                comment_lines.append(stripped)

            comments.append({
                "author_name": author_name or default_author,
                "author_email": default_email,
                "comment_text": "\n".join(comment_lines),
                "comment_id": comment_id,
                "doc_url": doc_url,
            })

        return comments

    # Pattern to match the @user+dtasks@domain.com mention (inline, not whole line)
    TRIGGER_MENTION_RE = re.compile(
        r"@?\S*\+dtasks@\S+", re.IGNORECASE
    )

    @staticmethod
    def strip_trigger_address(text: Optional[str]) -> str:
        """Remove +dtasks trigger address mentions from text.

        Strips the @user+dtasks@domain.com mention inline, preserving
        any other content on the same line (like [c] markers).

        Args:
            text: The reply text to clean.

        Returns:
            Text with trigger address mentions removed.
        """
        if not text:
            return ""

        cleaned = DriveTaskQueueWriter.TRIGGER_MENTION_RE.sub("", text)
        # Clean up extra whitespace
        lines = [line.strip() for line in cleaned.split("\n")]
        return "\n".join(line for line in lines if line).strip()

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

        # Find all doc URLs and prefer the one with a disco (comment_id) param
        doc_id = None
        comment_id = None

        for doc_match in DOC_URL_RE.finditer(body):
            matched_id = doc_match.group(1)
            full_match = doc_match.group(0)
            disco_match = DISCO_PARAM_RE.search(full_match)

            if disco_match:
                # Found a URL with disco param — use this one
                return (matched_id, disco_match.group(1))

            # Track first doc_id as fallback
            if doc_id is None:
                doc_id = matched_id

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
        surrounding_context: Optional[str] = None,
        urls: Optional[list[str]] = None,
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
            surrounding_context: Document context around the quoted passage.
            urls: Hyperlink URLs found in the document context.
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
            lines.append(f"quoted_passage: {quoted_passage[:200]}")
        if surrounding_context:
            lines.append(f"surrounding_context: {surrounding_context[:500]}")
        if urls:
            lines.append("urls: " + " , ".join(urls))

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

    def format_spark_record_drive(
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
        surrounding_context: Optional[str] = None,
        urls: Optional[list[str]] = None,
        marker_type: Optional[str] = None,
        task_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Format a Spark Record for a Google Docs comment.

        Docs comments are already enriched by DriveEnricher (comment text,
        quoted passage, surrounding context) so no fetch_hint is needed.
        """
        now = datetime.now(EASTERN_TZ)
        path_segment = DOC_TYPE_TO_PATH.get(doc_type, "document")
        doc_link = (
            f"https://docs.google.com/{path_segment}/d/{doc_id}/edit"
            f"?disco={comment_id}"
        )

        # Build source_text from enriched content
        source_parts = []
        if comment_text:
            source_parts.append(f"Comment: {comment_text}")
        if quoted_passage:
            source_parts.append(f"Quoted passage: {quoted_passage[:300]}")
        if surrounding_context:
            source_parts.append(f"Surrounding context: {surrounding_context[:500]}")
        source_text = "\n".join(source_parts)

        record: dict[str, Any] = {
            "spark_id": uuid.uuid4().hex[:8],
            "captured_at": now.isoformat(),
            "source_type": "google-docs-comment",
            "origin": "user-indicated",
            "reference_id": f"gdocs-comment-{doc_id}-{comment_id}",
            "source_text": source_text,
            "from_person": f"{comment_author} ({triggered_by})" if triggered_by else comment_author,
            "location": doc_title,
            "location_id": doc_id,
            "permalink": doc_link,
            "related_urls": urls or [],
            "marker_type": marker_type,
            "task_hint": task_hint,
            "user_notes": context,
            "surrounding_context": surrounding_context,
            "fetch_hint": None,
            "document_metadata": {
                "title": doc_title,
                "type": doc_type,
                "link": doc_link,
            },
        }

        return json.dumps(record)
