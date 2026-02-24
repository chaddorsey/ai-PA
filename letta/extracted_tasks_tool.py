"""
Extracted Tasks Tool for Letta

Provides a concurrent-safe way for multiple agents to contribute to a shared
extracted_tasks memory block and automatically archive source references.

Tool: add_extracted_tasks
"""

from typing import Dict, Any, Optional


def add_extracted_tasks(
    task_description: str,
    source_type: str,
    source_context: str,
    reference_id: str,
    source_text: str,
    from_person: str,
    location: str,
    location_id: str,
    source_timestamp: str,
    project: Optional[str] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
    priority: Optional[str] = None,
    related_urls: Optional[str] = None,
    cleanup_block_id: Optional[str] = None,
    cleanup_entry_identifier: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract a task and archive its source reference in one atomic operation.

    This tool does three things:
    1. Adds the task to the shared extracted_tasks memory block (concurrent-safe).
    2. Inserts a structured source reference passage into the shared
       extracted_tasks_archive (visible to all agents with the archive attached).
    3. Optionally removes the source queue entry from a block (atomic cleanup).

    The ref_id (8-char hex) links the two together.

    Only capture metadata that is explicitly stated or clearly evident in the
    source material. Do NOT infer or fabricate dates, priorities, or project
    associations that are not present in the source.

    Args:
        task_description: Concise verb-led task title
            (e.g., "Review agenda items highlighted in yellow on worksheet").
        source_type: Source type shorthand. One of: "slack", "google-docs",
            "meeting", "email", "google-docs-comment".
        source_context: Human-readable origin description
            (e.g., "Direct message from Danielle Kehoe").
        reference_id: Deterministic canonical unique identifier for the source.
            Format depends on source_type:
            slack = "slack-{channel_id}-{ts}",
            google-docs = "gdocs-{document_id}",
            meeting = "meeting-{meeting_id}",
            email = "email-{message_id}",
            google-docs-comment = "gdocs-comment-{document_id}-{comment_id}".
        source_text: Verbatim relevant text from the source. Do NOT summarize.
        from_person: Person name or ID who originated the task
            (e.g., "Danielle Kehoe (U09B5JUK2TY)").
        location: Human-readable location: channel name, document URL,
            meeting title, or email subject line.
        location_id: Machine-readable location identifier: channel ID,
            document ID, meeting ID, or message ID.
        source_timestamp: When the source message or document was created,
            in ISO 8601 format (e.g., "2026-02-11T06:37:00Z").
        project: Optional project name for tagging. Only provide if clearly
            relevant (e.g., "grants", "codap"). Adds a 4th tag.
        due_date: Optional due date in ISO 8601 format. Only provide when
            explicitly stated in source (e.g., "by Friday", "due March 1").
            Do NOT infer deadlines that are not clearly indicated.
        defer_date: Optional defer/start date in ISO 8601 format. Only provide
            when explicitly stated (e.g., "start Monday", "after the meeting").
        priority: Optional priority level. One of: "high", "normal", "low".
            Only provide when urgency is clearly indicated in the source
            (e.g., "ASAP", "urgent", "when you get a chance"). Do NOT default
            to any value — omit if not evident.
        related_urls: Optional comma-separated list of URLs relevant to the
            task. Only include URLs that appear in the immediate source
            context — not every URL in a document. Examples: links in a
            quoted passage, URLs in a forwarded email, links in a Slack
            message. Persisted as a RELATED URLS section in the archival
            passage for future reference.
        cleanup_block_id: Optional block ID of the source queue to clean up
            after successful extraction. When provided with
            cleanup_entry_identifier, the matching entry is removed from
            the block atomically. Use this to prevent compaction from
            swallowing queue cleanup. Pass the block ID of
            queued_tasks_from_drive, queued_tasks_from_email, etc.
        cleanup_entry_identifier: Optional unique string that identifies the
            source entry to remove from the cleanup block. The tool splits
            the block by "---" separators and removes the section containing
            this string. For drive queue entries, use the comment_id. For
            email queue entries, use the gmail_message_id.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - message: Confirmation message or error description
        - agent_name: Name of the agent that added the task
        - timestamp: ISO timestamp when task was extracted
        - ref_id: 8-character hex reference ID linking task to archival passage
        - archival_passage_id: ID of the created archival memory passage
        - cleanup_result: "removed", "not_found", "skipped", or error detail
        - error_message: Detailed error message if status is "error"
    """
    import os
    import traceback
    import uuid
    import re
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    import json

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")

        if not AGENT_ID:
            return {
                "status": "error",
                "message": "",
                "agent_name": "",
                "timestamp": "",
                "ref_id": "",
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": "LETTA_AGENT_ID environment variable not set"
            }

        # Validate source_type
        valid_source_types = {"slack", "google-docs", "google-docs-comment", "meeting", "email", "google-drive-comment"}
        if source_type not in valid_source_types:
            return {
                "status": "error",
                "message": "",
                "agent_name": "",
                "timestamp": "",
                "ref_id": "",
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": f"Invalid source_type '{source_type}'. Must be one of: {', '.join(sorted(valid_source_types))}"
            }

        # Validate priority if provided
        valid_priorities = {"high", "normal", "low"}
        if priority and priority not in valid_priorities:
            return {
                "status": "error",
                "message": "",
                "agent_name": "",
                "timestamp": "",
                "ref_id": "",
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": f"Invalid priority '{priority}'. Must be one of: {', '.join(sorted(valid_priorities))}"
            }

        # Get agent name
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method='GET')

        try:
            with urllib.request.urlopen(agent_req, timeout=10) as response:
                agent_data = json.loads(response.read().decode('utf-8'))
                agent_name = agent_data.get('name', 'Unknown Agent')
        except Exception:
            agent_name = 'Unknown Agent'

        # Generate ref_id and timestamp
        ref_id = uuid.uuid4().hex[:8]
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")
        iso_timestamp = now.isoformat()
        year_month = now.strftime("%Y-%m")

        # ── Step 1: Update extracted_tasks block ──

        # Get agent memory blocks
        try:
            with urllib.request.urlopen(agent_req, timeout=10) as response:
                agent_data_full = json.loads(response.read().decode('utf-8'))
                blocks_data = agent_data_full.get('memory', {}).get('blocks', [])
        except Exception as e:
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "ref_id": ref_id,
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": f"Failed to retrieve memory blocks: {str(e)}"
            }

        # Find extracted_tasks block
        extracted_tasks_block = None
        for block in blocks_data:
            if block.get('label') == 'extracted_tasks':
                extracted_tasks_block = block
                break

        if not extracted_tasks_block:
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "ref_id": ref_id,
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": "extracted_tasks block not found. Ensure block is attached to this agent."
            }

        extracted_tasks_block_id = extracted_tasks_block.get('id')
        current_value = extracted_tasks_block.get('value', '')

        # Find this agent's section in the block
        section_header = f"=== {agent_name} ({AGENT_ID}) ==="
        section_pattern = re.compile(
            rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9-]+\)\s+===)|$)',
            re.DOTALL
        )

        section_match = section_pattern.search(current_value)
        task_line = f"[extracted_time: {timestamp_str}; ref_id: {ref_id}] {task_description}\n\n"

        if section_match:
            insert_pos = section_match.end()
            before = current_value[:insert_pos]
            after = current_value[insert_pos:]
            if before and not before.endswith('\n'):
                before += '\n'
            new_value = before + task_line + after
        else:
            new_value = current_value + f"\n{section_header}\n{task_line}"

        # Update the block
        update_url = f"{LETTA_BASE}/v1/blocks/{extracted_tasks_block_id}"
        update_data = {"value": new_value}
        update_payload = json.dumps(update_data).encode('utf-8')
        update_req = urllib.request.Request(
            update_url,
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method='PATCH'
        )

        try:
            with urllib.request.urlopen(update_req, timeout=10) as response:
                json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as http_err:
            error_body = http_err.read().decode('utf-8')
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "ref_id": ref_id,
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": f"HTTP {http_err.code}: Failed to update extracted_tasks block. {error_body[:200]}"
            }

        # ── Step 2: Insert archival source reference passage ──

        # Build TASK METADATA section (only include fields that were provided)
        metadata_lines = []
        if due_date:
            metadata_lines.append(f"- Due: {due_date}")
        if defer_date:
            metadata_lines.append(f"- Defer: {defer_date}")
        if priority:
            metadata_lines.append(f"- Priority: {priority}")

        metadata_section = ""
        if metadata_lines:
            metadata_section = (
                "\nTASK METADATA\n"
                + "\n".join(metadata_lines)
                + "\n"
            )

        # Build RELATED URLS section (only if URLs provided)
        urls_section = ""
        if related_urls and related_urls.strip():
            url_list = [u.strip() for u in related_urls.split(",") if u.strip()]
            if url_list:
                urls_section = (
                    "\nRELATED URLS\n"
                    + "\n".join(f"- {u}" for u in url_list)
                    + "\n"
                )

        passage_text = (
            f"TASK: {task_description}\n"
            f"REF_ID: {ref_id}\n"
            f"{metadata_section}\n"
            f"SOURCE REFERENCE\n"
            f"- Type: {source_type}\n"
            f"- Context: {source_context}\n"
            f"- Reference ID: {reference_id}\n"
            f"\n"
            f"SOURCE METADATA\n"
            f"- Timestamp: {source_timestamp}\n"
            f"- From: {from_person}\n"
            f"- Location: {location}\n"
            f"- Location ID: {location_id}\n"
            f"{urls_section}\n"
            f"TIMESTAMPS\n"
            f"- Source: {source_timestamp}\n"
            f"- Extracted: {iso_timestamp}\n"
            f"- OmniFocus: pending\n"
            f"\n"
            f"OMNIFOCUS\n"
            f"- Task ID: pending\n"
            f"- Status: extracted\n"
            f"\n"
            f"SOURCE TEXT\n"
            f"{source_text}"
        )

        # Build tags (exactly 3-4)
        tags = [
            f"source:{source_type}",
            year_month,
            "status:extracted",
        ]
        if project:
            tags.append(f"project:{project}")

        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
        archival_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
        tags.append(f"agent:{AGENT_ID}")
        archival_data = {"text": passage_text, "tags": tags}
        archival_payload = json.dumps(archival_data).encode('utf-8')
        archival_req = urllib.request.Request(
            archival_url,
            data=archival_payload,
            headers={"Content-Type": "application/json"},
            method='POST'
        )

        archival_passage_id = ""
        try:
            with urllib.request.urlopen(archival_req, timeout=30) as response:
                archival_resp = json.loads(response.read().decode('utf-8'))
                archival_passage_id = archival_resp.get('id', '')
        except urllib.error.HTTPError as http_err:
            error_body = http_err.read().decode('utf-8')
            return {
                "status": "error",
                "message": "Task added to extracted_tasks block, but archival insert failed.",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "ref_id": ref_id,
                "archival_passage_id": "",
                "cleanup_result": "skipped",
                "error_message": f"HTTP {http_err.code}: Archival insert failed. {error_body[:200]}"
            }

        # ── Step 3: Optional queue cleanup ──
        cleanup_result = "skipped"
        if cleanup_block_id and cleanup_entry_identifier:
            try:
                cleanup_url = f"{LETTA_BASE}/v1/blocks/{cleanup_block_id}"
                cleanup_get_req = urllib.request.Request(cleanup_url, method="GET")
                with urllib.request.urlopen(cleanup_get_req, timeout=10) as resp:
                    cleanup_block_data = json.loads(resp.read().decode("utf-8"))
                cleanup_value = cleanup_block_data.get("value", "")

                parts = cleanup_value.split("---")
                original_count = len(parts)
                filtered = [p for p in parts if cleanup_entry_identifier not in p]

                if len(filtered) < original_count:
                    # Drop whitespace-only segments to prevent separator pile-up
                    filtered = [p for p in filtered if p.strip()]
                    new_cleanup_value = "---".join(filtered).strip()
                    if new_cleanup_value:
                        new_cleanup_value += "\n---"
                    cleanup_patch = json.dumps({"value": new_cleanup_value}).encode("utf-8")
                    cleanup_patch_req = urllib.request.Request(
                        cleanup_url,
                        data=cleanup_patch,
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    urllib.request.urlopen(cleanup_patch_req, timeout=10)
                    cleanup_result = "removed"
                else:
                    cleanup_result = "not_found"
            except Exception as ce:
                cleanup_result = f"cleanup_error: {str(ce)}"

        return {
            "status": "ok",
            "message": "Task extracted and source reference archived.",
            "agent_name": agent_name,
            "timestamp": iso_timestamp,
            "ref_id": ref_id,
            "archival_passage_id": archival_passage_id,
            "cleanup_result": cleanup_result,
        }

    except Exception as e:
        try:
            error_timestamp = datetime.now(pytz.timezone("America/New_York")).isoformat()
        except Exception:
            from datetime import datetime as dt
            error_timestamp = dt.now().isoformat()

        return {
            "status": "error",
            "message": "",
            "agent_name": "",
            "timestamp": error_timestamp,
            "ref_id": "",
            "archival_passage_id": "",
            "cleanup_result": "skipped",
            "error_message": f"Error adding task: {str(e)}\n{traceback.format_exc()}"
        }
