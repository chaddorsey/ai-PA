"""
Retrieve Task Info Tool for Letta

Allows any agent to look up extracted task source references in the shared
extracted_tasks_archive, regardless of which archive is attached to the agent.

Tool: retrieve_task_info
"""

from typing import Dict, Any, Optional


def retrieve_task_info(
    ref_id: str,
    search_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Look up an extracted task's source reference from the shared archive.

    Searches the extracted_tasks_archive by ref_id (preferred) or free-text
    query. This tool uses direct API calls to the shared archive, so it works
    from any agent regardless of which archive is attached.

    Handles both regular tasks and merged tasks. For merged tasks (those with
    MERGED_IDS), automatically retrieves source details from each original
    child passage and returns them in the merged_sources list.

    Use this when you need to review the full source context, metadata, or
    status of an extracted task that appears in the extracted_tasks block.

    Args:
        ref_id: The 8-character hex reference ID to look up. This is the
            primary lookup key and matches the ref_id in extracted_tasks
            block entries (e.g., "9257de13").
        search_text: Optional additional search text to help find the passage
            if ref_id semantic search doesn't return it. The passage text
            is matched exactly after semantic retrieval, so providing the
            task description here can improve recall.

    Returns:
        Dictionary with keys:
        - status: "ok", "not_found", or "error"
        - ref_id: The ref_id that was searched
        - passage_id: ID of the found passage (empty if not found)
        - task_description: The task title from the passage
        - is_merged: Whether this is a merged task
        - merged_ids: List of child ref_ids if merged (empty list otherwise)
        - source_type: Source type (empty for merged tasks, see merged_sources)
        - source_context: Human-readable origin (empty for merged, see merged_sources)
        - reference_id: Canonical source identifier
        - from_person: Who originated the task
        - location: Where the task came from
        - source_timestamp: When the source was created
        - due_date: Due date if set (empty if none)
        - priority: Priority if set (empty if none)
        - omnifocus_status: Current OmniFocus sync status
        - related_urls: List of related URLs from the passage (empty list if none)
        - full_text: The complete passage text
        - tags: List of tags on the passage
        - merged_sources: List of dicts with source details from child tasks
            (only populated for merged tasks). Each dict has: ref_id,
            task_description, source_type, source_context, from_person,
            location, source_timestamp, full_text.
        - error_message: Error details if status is "error"
    """
    import os
    import re
    import traceback
    import urllib.request
    import urllib.error
    import json

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-3f0530eb-82db-463a-a28b-f4752a95d7d5"
        SEARCH_URL = f"{LETTA_BASE}/v1/passages/search"

        # Field extraction patterns (used for both primary and child passages)
        FIELD_PATTERNS = [
            ("task_description", r"^TASK: (.+)$"),
            ("source_type", r"^- Type: (.+)$"),
            ("source_context", r"^- Context: (.+)$"),
            ("reference_id", r"^- Reference ID: (.+)$"),
            ("from_person", r"^- From: (.+)$"),
            ("location", r"^- Location: (.+)$"),
            ("source_timestamp", r"^- Source: (.+)$"),
            ("due_date", r"^- Due: (.+)$"),
            ("priority", r"^- Priority: (.+)$"),
            ("omnifocus_status", r"^- Status: (.+)$"),
        ]

        if not ref_id or len(ref_id.strip()) == 0:
            return {
                "status": "error", "ref_id": "", "passage_id": "",
                "task_description": "", "is_merged": False, "merged_ids": [],
                "source_type": "", "source_context": "", "reference_id": "",
                "from_person": "", "location": "", "source_timestamp": "",
                "due_date": "", "priority": "", "omnifocus_status": "",
                "related_urls": [],
                "full_text": "", "tags": [], "merged_sources": [],
                "error_message": "ref_id is required",
            }

        ref_id = ref_id.strip()

        # ── Search for primary passage ──
        query = f"REF_ID: {ref_id}"
        if search_text:
            query = f"TASK: {search_text} REF_ID: {ref_id}"

        payload = json.dumps({
            "query": query,
            "archive_ids": [ARCHIVE_ID],
            "limit": 20,
        }).encode("utf-8")
        req = urllib.request.Request(
            SEARCH_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            search_results = json.loads(resp.read().decode("utf-8"))

        target = None
        for item in search_results:
            p = item.get("passage", item)
            if f"REF_ID: {ref_id}" in p.get("text", "") and p.get("archive_id", "") == ARCHIVE_ID:
                target = p
                break

        if not target:
            return {
                "status": "not_found", "ref_id": ref_id, "passage_id": "",
                "task_description": "", "is_merged": False, "merged_ids": [],
                "source_type": "", "source_context": "", "reference_id": "",
                "from_person": "", "location": "", "source_timestamp": "",
                "due_date": "", "priority": "", "omnifocus_status": "",
                "related_urls": [],
                "full_text": "", "tags": [], "merged_sources": [],
                "error_message": f"No passage found with REF_ID: {ref_id} in extracted_tasks_archive",
            }

        # ── Parse fields from primary passage ──
        text = target.get("text", "")
        fields = {}
        for key, pattern in FIELD_PATTERNS:
            m = re.search(pattern, text, re.MULTILINE)
            fields[key] = m.group(1) if m else ""

        # ── Parse RELATED URLS section ──
        related_urls = []
        urls_match = re.search(r"^RELATED URLS\n((?:- .+\n?)+)", text, re.MULTILINE)
        if urls_match:
            for url_line in urls_match.group(1).strip().split("\n"):
                url = url_line.lstrip("- ").strip()
                if url:
                    related_urls.append(url)

        # ── Check for merged task ──
        merged_match = re.search(r"^MERGED_IDS: (.+)$", text, re.MULTILINE)
        is_merged = merged_match is not None
        merged_ids = []
        merged_sources = []

        if is_merged:
            merged_ids = [rid.strip() for rid in merged_match.group(1).split(",") if rid.strip()]

            # Fetch source details from each child passage
            for child_rid in merged_ids:
                child_payload = json.dumps({
                    "query": f"REF_ID: {child_rid}",
                    "archive_ids": [ARCHIVE_ID],
                    "limit": 10,
                }).encode("utf-8")
                child_req = urllib.request.Request(
                    SEARCH_URL, data=child_payload,
                    headers={"Content-Type": "application/json"}, method="POST",
                )

                child_passage = None
                try:
                    with urllib.request.urlopen(child_req, timeout=30) as child_resp:
                        child_results = json.loads(child_resp.read().decode("utf-8"))
                    for ci in child_results:
                        cp = ci.get("passage", ci)
                        if f"REF_ID: {child_rid}" in cp.get("text", "") and cp.get("archive_id", "") == ARCHIVE_ID:
                            child_passage = cp
                            break
                except Exception:
                    pass

                if child_passage:
                    child_text = child_passage.get("text", "")
                    child_fields = {}
                    for key, pattern in FIELD_PATTERNS:
                        m = re.search(pattern, child_text, re.MULTILINE)
                        child_fields[key] = m.group(1) if m else ""
                    merged_sources.append({
                        "ref_id": child_rid,
                        "task_description": child_fields.get("task_description", ""),
                        "source_type": child_fields.get("source_type", ""),
                        "source_context": child_fields.get("source_context", ""),
                        "from_person": child_fields.get("from_person", ""),
                        "location": child_fields.get("location", ""),
                        "source_timestamp": child_fields.get("source_timestamp", ""),
                        "full_text": child_text,
                    })
                else:
                    merged_sources.append({
                        "ref_id": child_rid,
                        "task_description": "",
                        "source_type": "",
                        "source_context": "",
                        "from_person": "",
                        "location": "",
                        "source_timestamp": "",
                        "full_text": f"[not found: {child_rid}]",
                    })

        return {
            "status": "ok",
            "ref_id": ref_id,
            "passage_id": target.get("id", ""),
            "task_description": fields.get("task_description", ""),
            "is_merged": is_merged,
            "merged_ids": merged_ids,
            "source_type": fields.get("source_type", ""),
            "source_context": fields.get("source_context", ""),
            "reference_id": fields.get("reference_id", ""),
            "from_person": fields.get("from_person", ""),
            "location": fields.get("location", ""),
            "source_timestamp": fields.get("source_timestamp", ""),
            "due_date": fields.get("due_date", ""),
            "priority": fields.get("priority", ""),
            "omnifocus_status": fields.get("omnifocus_status", ""),
            "related_urls": related_urls,
            "full_text": text,
            "tags": target.get("tags", []),
            "merged_sources": merged_sources,
            "error_message": "",
        }

    except Exception as e:
        return {
            "status": "error", "ref_id": ref_id if ref_id else "",
            "passage_id": "", "task_description": "",
            "is_merged": False, "merged_ids": [],
            "source_type": "", "source_context": "", "reference_id": "",
            "from_person": "", "location": "", "source_timestamp": "",
            "due_date": "", "priority": "", "omnifocus_status": "",
            "related_urls": [],
            "full_text": "", "tags": [], "merged_sources": [],
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
