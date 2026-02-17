"""
Meeting Scan Tool for Letta

Scans a meeting's archival passages for task markers, extracts URLs,
retrieves transcript excerpts for pointers, and returns a structured
scan package for the agent to perform semantic analysis on.

Tool: scan_meeting_notes
"""

from typing import Dict, Any


def scan_meeting_notes(meeting_id: str) -> Dict[str, Any]:
    """
    Scan a meeting's archival passages for task markers and prepare a scan package.

    Fetches the meeting's archived content (private notes, AI summary, transcript),
    parses user-authored markers ([ ] for my tasks, [;] for others' tasks, > for
    pointers), extracts document URLs, and retrieves transcript excerpts matching
    pointer topics.

    Returns a structured scan package for the agent to perform semantic analysis on.
    The agent should review all scannable_content items for additional action items
    beyond what markers captured, then call prepare_meeting_followup with merged results.

    Args:
        meeting_id: The Granola meeting UUID (e.g. "9b86c082-3840-4b84-98e9-b8096b4ef5e9")

    Returns:
        Dictionary with meeting metadata, marker_extractions, scannable_content,
        doc_urls_found, and has_user_notes flag.
    """
    import os
    import re
    import json
    import traceback
    import urllib.request
    import urllib.parse
    import urllib.error

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        if not AGENT_ID:
            return {"status": "error", "error_message": "LETTA_AGENT_ID not set"}

        # ── Fetch archival passages for this meeting ──
        # Use text substring search on the list endpoint — the passage text
        # contains **ID:** {meeting_id} so this reliably finds all chunks.
        encoded_id = urllib.parse.quote(meeting_id, safe="")
        search_url = (
            f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory"
            f"?search={encoded_id}&limit=30"
        )
        req = urllib.request.Request(search_url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            all_passages = json.loads(resp.read().decode("utf-8"))

        # Filter to passages tagged with this meeting's id (belt + suspenders)
        meeting_passages = []
        for p in all_passages:
            tags = p.get("tags", [])
            if f"id:{meeting_id}" in tags:
                meeting_passages.append(p)

        if not meeting_passages:
            return {
                "status": "error",
                "error_message": f"No archival passages found for meeting {meeting_id}",
            }

        # ── Reconstruct meeting content from passages ──
        # Sort by chunk tag: summary first, then transcript-1, transcript-2, etc.
        # Inline sort-key logic (no nested def allowed in Letta tools)
        meeting_passages.sort(
            key=lambda p: (
                lambda tags_list: (
                    0 if any(t == "chunk:summary" for t in tags_list)
                    else 1 if any(t == "chunk:metadata" for t in tags_list)
                    else (10 + int(next(
                        (t.split("-", 1)[1] for t in tags_list
                         if t.startswith("chunk:transcript-")),
                        "99"
                    )))
                    if any(t.startswith("chunk:transcript-") for t in tags_list)
                    else (10 + int(next(
                        (t.split(":", 1)[1] for t in tags_list
                         if t.startswith("chunk:") and t.split(":", 1)[1].isdigit()),
                        "99"
                    )))
                    if any(t.startswith("chunk:") for t in tags_list)
                    else 50
                )
            )(p.get("tags", []))
        )

        full_text = "\n\n".join(p.get("text", "") for p in meeting_passages)

        # ── Parse meeting header ──
        title_match = re.search(r"## Meeting:\s*(.+)", full_text)
        meeting_title = title_match.group(1).strip() if title_match else "Untitled"

        date_match = re.search(r"\*\*Date:\*\*\s*(.+)", full_text)
        meeting_date = date_match.group(1).strip() if date_match else ""

        participants_match = re.search(r"\*\*Participants:\*\*\s*(.+)", full_text)
        participants_raw = participants_match.group(1).strip() if participants_match else ""
        participants = [p.strip() for p in participants_raw.split(",") if p.strip()]

        granola_link = f"https://notes.granola.ai/d/{meeting_id}"

        # ── Extract sections ──
        private_notes = ""
        ai_summary = ""
        transcript_text = ""

        notes_match = re.search(
            r"### My Notes\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if notes_match:
            private_notes = notes_match.group(1).strip()

        summary_match = re.search(
            r"### Summary\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if summary_match:
            ai_summary = summary_match.group(1).strip()

        transcript_match = re.search(
            r"### Transcript\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if transcript_match:
            transcript_text = transcript_match.group(1).strip()

        # ── Parse markers from private_notes ──
        MARKER_RE = re.compile(
            r"^\s*(?:[-*]\s*)?(\[;\]|\[\s?\]|>)\s+(.+)$", re.MULTILINE
        )
        my_tasks = []
        their_tasks = []
        pointers = []

        if private_notes:
            for line_num, line in enumerate(private_notes.split("\n"), 1):
                m = MARKER_RE.match(line)
                if not m:
                    continue
                marker = m.group(1).strip()
                text = m.group(2).strip()
                item = {"marker": marker, "text": text, "line": line_num}

                if marker in ("[]", "[ ]"):
                    my_tasks.append(item)
                elif marker == "[;]":
                    their_tasks.append(item)
                elif marker == ">":
                    pointers.append(item)

        # ── Extract URLs from private_notes ──
        URL_RE = re.compile(r"https?://[^\s<>\"]+")
        doc_urls = []
        if private_notes:
            doc_urls = URL_RE.findall(private_notes)

        # ── Context lines (unmarked, non-empty lines from notes) ──
        context_lines = []
        if private_notes:
            for line in private_notes.split("\n"):
                stripped = line.strip()
                if stripped and not MARKER_RE.match(line) and not stripped.startswith("D/NA"):
                    context_lines.append(stripped)

        # ── Transcript excerpts for pointers ──
        WINDOW_SIZE = 500
        STEP_SIZE = 100
        MIN_KEYWORD_LENGTH = 4
        transcript_excerpts = []
        if transcript_text and pointers:
            for ptr in pointers:
                keywords = set(
                    w.lower()
                    for w in re.findall(r"\w{" + str(MIN_KEYWORD_LENGTH) + r",}", ptr["text"])
                )
                if not keywords:
                    continue
                # Slide a window looking for best keyword overlap
                best_start = 0
                best_score = 0
                for start in range(0, max(1, len(transcript_text) - WINDOW_SIZE), STEP_SIZE):
                    window = transcript_text[start : start + WINDOW_SIZE].lower()
                    score = sum(1 for kw in keywords if kw in window)
                    if score > best_score:
                        best_score = score
                        best_start = start
                if best_score > 0:
                    excerpt = transcript_text[
                        best_start : best_start + WINDOW_SIZE
                    ].strip()
                    transcript_excerpts.append(
                        {
                            "source": "transcript_excerpt",
                            "label": f"Transcript near: {ptr['text'][:60]}",
                            "text": excerpt,
                        }
                    )

        # ── Build scannable_content ──
        scannable_content = []

        if private_notes:
            scannable_content.append(
                {
                    "source": "private_notes",
                    "label": "User's meeting notes",
                    "text": private_notes,
                    "context_lines": context_lines,
                }
            )

        if ai_summary:
            scannable_content.append(
                {
                    "source": "ai_summary",
                    "label": "Granola AI summary",
                    "text": ai_summary,
                }
            )

        scannable_content.extend(transcript_excerpts)

        # Add doc URL placeholders (agent fetches content via existing tools)
        for url in doc_urls:
            scannable_content.append(
                {
                    "source": "linked_doc",
                    "label": f"Linked document: {url[:80]}",
                    "url": url,
                    "text": None,
                    "fetch_note": (
                        "Use fetch_document_from_drive or get_drive_file_info "
                        "to retrieve this document's content for scanning."
                    ),
                }
            )

        return {
            "status": "ok",
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "meeting_date": meeting_date,
            "participants": participants,
            "granola_link": granola_link,
            "marker_extractions": {
                "my_tasks": my_tasks,
                "their_tasks": their_tasks,
                "pointers": pointers,
            },
            "scannable_content": scannable_content,
            "has_user_notes": bool(private_notes),
            "doc_urls_found": doc_urls,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
