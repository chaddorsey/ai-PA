"""Task queue writer - writes task entries to Letta memory block."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
import structlog

from gmail_watch.settings import settings

logger = structlog.get_logger()

# Timezone for queue timestamps
EASTERN_TZ = ZoneInfo("America/New_York")

# Forward detection patterns (shared with watch_manager.py)
FORWARD_DELIMITER = re.compile(r"-{5,}\s*Forwarded message\s*-{5,}")
FORWARDED_HEADER = re.compile(r"^(From|Date|Subject|To):\s*(.+)$", re.MULTILINE)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+")

# Task marker pattern: lines starting with [] or [ ] or [c] (explicit) or > (pointer)
MARKER_RE = re.compile(r"^\s*(?:[-*]\s*)?(\[\s?\]|\[\s*c\s*[\]\[]|>)\s+(.+)$", re.MULTILINE)


class TaskQueueWriter:
    """Writes task queue entries to Letta memory block."""

    def __init__(
        self,
        letta_base_url: Optional[str] = None,
        block_id: Optional[str] = None,
    ) -> None:
        self.letta_base_url = letta_base_url or settings.letta_base_url
        self.block_id = block_id or settings.task_queue_block_id

    def format_queue_entry(
        self,
        message_id: str,
        thread_id: str,
        subject: str,
        from_address: str,
        date: str,
        snippet: str,
        trigger: str,
        notes: Optional[str] = None,
        forwarded_message_id: Optional[str] = None,
        marker_type: Optional[str] = None,
        task_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Format a queue entry in the standard format.

        Args:
            marker_type: "explicit" for [] markers, "pointer" for > markers.
            task_hint: The marker text (without prefix).
            context: Non-marker context lines from user notes.
        """
        now = datetime.now(EASTERN_TZ)
        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        lines = [
            (
                f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] "
                f"message_id: {message_id} "
                f"| thread_id: {thread_id}"
            ),
            f"subject: {subject}",
            f"from: {from_address}",
            f"date: {date}",
            f"snippet: {snippet[:150]}",
            f"gmail_link: {gmail_link}",
            f"trigger: {trigger}",
        ]
        if marker_type:
            lines.append(f"marker_type: {marker_type}")
        if task_hint:
            lines.append(f"task_hint: {task_hint}")
        if context:
            lines.append(f"context: {context}")
        if notes and not marker_type:
            lines.append(f"notes: {notes}")
        if forwarded_message_id:
            lines.append(f"forwarded_message_id: {forwarded_message_id}")

        return "\n".join(lines)

    async def read_block(self) -> str:
        """Read the current block value.

        Returns:
            The block text content, or empty string on error.
        """
        if not self.block_id or not self.letta_base_url:
            return ""

        block_url = f"{self.letta_base_url}/v1/blocks/{self.block_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(block_url)
                resp.raise_for_status()
                return resp.json().get("value", "")
        except Exception:
            return ""

    async def write_to_block(
        self, entry_text: str, dedup_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Append a queue entry to the Letta memory block.

        Reads current block value, appends entry with separator, writes back.
        If dedup_key is provided, skips write if key already exists in block.

        Returns:
            Dict with status and details.
        """
        if not self.block_id:
            return {"status": "error", "error": "No task_queue_block_id configured"}
        if not self.letta_base_url:
            return {"status": "error", "error": "No letta_base_url configured"}

        block_url = f"{self.letta_base_url}/v1/blocks/{self.block_id}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Read current block value
                resp = await client.get(block_url)
                resp.raise_for_status()
                block_data = resp.json()
                current_value = block_data.get("value", "").rstrip()

                # Deduplicate if key provided
                if dedup_key and dedup_key in current_value:
                    logger.info(
                        "task_queue_dedup_skip",
                        dedup_key=dedup_key,
                        block_id=self.block_id,
                    )
                    return {"status": "ok", "dedup": True}

                # Append entry
                updated = f"{current_value}\n{entry_text}\n---"

                # Write back
                patch_resp = await client.patch(
                    block_url,
                    json={"value": updated},
                )
                patch_resp.raise_for_status()

            logger.info("task_queue_entry_written", block_id=self.block_id)
            return {"status": "ok"}

        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error("task_queue_write_failed", error=error)
            return {"status": "error", "error": error}
        except Exception as e:
            logger.error("task_queue_write_failed", error=str(e))
            return {"status": "error", "error": str(e)}

    def format_spark_record(
        self,
        message_id: str,
        thread_id: str,
        subject: str,
        from_address: str,
        date: str,
        snippet: str,
        trigger: str,
        source_type: str = "email",
        notes: Optional[str] = None,
        forwarded_message_id: Optional[str] = None,
        marker_type: Optional[str] = None,
        task_hint: Optional[str] = None,
        context: Optional[str] = None,
    ) -> str:
        """Format a Spark Record for the spark_queue block.

        JSON format with fetch_hint for deferred full-content retrieval.
        """
        import json
        import uuid

        now = datetime.now(EASTERN_TZ)
        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        # Build source_text: user notes + extended snippet (500 chars)
        source_text_parts = []
        if notes:
            source_text_parts.append(notes)
        if snippet:
            source_text_parts.append(snippet[:500])
        source_text = "\n---\n".join(source_text_parts) if source_text_parts else ""

        origin = "user-indicated" if trigger in ("forwarded", "TaskQueue") else "agent-identified"

        record = {
            "spark_id": uuid.uuid4().hex[:8],
            "captured_at": now.isoformat(),
            "source_type": source_type,
            "origin": origin,
            "reference_id": f"email-{message_id}",
            "source_text": source_text,
            "from_person": from_address,
            "location": subject,
            "location_id": message_id,
            "permalink": gmail_link,
            "related_urls": [],
            "marker_type": marker_type,
            "task_hint": task_hint,
            "user_notes": notes,
            "fetch_hint": f"gmail:{message_id}",
        }
        if context:
            record["surrounding_context"] = context
        if forwarded_message_id:
            record["forwarded_message_id"] = forwarded_message_id

        return json.dumps(record)

    async def write_to_spark_queue(self, spark_json: str) -> dict[str, Any]:
        """Write a Spark Record to the spark_queue block.

        Uses the spark_queue_block_id from settings.
        Deduplicates by reference_id — skips if the same reference already exists.
        """
        import json as _json

        spark_block_id = settings.spark_queue_block_id
        if not spark_block_id:
            return {"status": "error", "error": "No spark_queue_block_id configured"}
        if not self.letta_base_url:
            return {"status": "error", "error": "No letta_base_url configured"}

        block_url = f"{self.letta_base_url}/v1/blocks/{spark_block_id}"

        # Extract reference_id for dedup check
        try:
            spark_data = _json.loads(spark_json)
            ref_id = spark_data.get("reference_id", "")
        except Exception:
            ref_id = ""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(block_url)
                resp.raise_for_status()
                block_data = resp.json()
                current_value = block_data.get("value", "").rstrip()

                # Deduplicate: skip if reference_id already in block
                if ref_id and ref_id in current_value:
                    logger.info(
                        "spark_queue_dedup_skip",
                        reference_id=ref_id,
                        block_id=spark_block_id,
                    )
                    return {"status": "ok", "dedup": True}

                # Strip "(empty)" placeholder
                if "(empty)" in current_value:
                    current_value = current_value.replace("(empty)", "").strip()
                    if not current_value:
                        current_value = "# Spark Queue"

                updated = f"{current_value}\n{spark_json}\n---"

                patch_resp = await client.patch(
                    block_url,
                    json={"value": updated},
                )
                patch_resp.raise_for_status()

            logger.info("spark_queue_entry_written", block_id=spark_block_id)
            return {"status": "ok"}

        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error("spark_queue_write_failed", error=error)
            return {"status": "error", "error": error}
        except Exception as e:
            logger.error("spark_queue_write_failed", error=str(e))
            return {"status": "error", "error": str(e)}

    @staticmethod
    def parse_forward(body: str) -> dict[str, Any]:
        """Parse a forwarded email body into components.

        Returns:
            Dict with keys: is_forward, notes, from, subject, date, snippet.
        """
        if not body:
            return {"is_forward": False}

        fwd_match = FORWARD_DELIMITER.search(body)
        if not fwd_match:
            return {"is_forward": False}

        above = body[: fwd_match.start()].strip()
        below = body[fwd_match.end() :]

        # Parse forwarded headers
        fwd_headers = {}
        for match in FORWARDED_HEADER.finditer(below[:500]):
            fwd_headers[match.group(1).lower()] = match.group(2).strip()

        # Extract snippet from forwarded body (after header block)
        fwd_body_start = re.search(r"\n\s*\n", below)
        snippet = ""
        if fwd_body_start:
            fwd_body = below[fwd_body_start.end() :].strip()
            if fwd_body:
                snippet = fwd_body[:150]

        return {
            "is_forward": True,
            "notes": above if above else None,
            "from": fwd_headers.get("from", ""),
            "subject": fwd_headers.get("subject", ""),
            "date": fwd_headers.get("date", ""),
            "snippet": snippet,
        }

    @staticmethod
    def parse_markers(notes: str) -> list[dict[str, Any]]:
        """Parse task markers from user notes.

        Conventions (matching meeting system):
        - [] or [ ] at line start = explicit task description
        - > at line start = pointer/gist needing expansion from email

        Lines without markers are treated as shared context.

        Returns:
            List of dicts with marker_type, task_hint, context.
            Empty list if no markers found (caller uses notes as-is).
        """
        if not notes:
            return []

        markers = []
        context_lines = []

        for line in notes.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            m = MARKER_RE.match(line)
            if m:
                marker = m.group(1).strip()
                text = m.group(2).strip()
                marker_type = "pointer" if marker == ">" else "explicit"
                markers.append({"marker_type": marker_type, "task_hint": text})
            else:
                context_lines.append(stripped)

        if not markers:
            return []

        context = "\n".join(context_lines) if context_lines else None
        for item in markers:
            item["context"] = context

        return markers
