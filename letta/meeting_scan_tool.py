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
    import base64
    import subprocess
    import traceback
    import urllib.request
    import urllib.parse
    import urllib.error
    from email.mime.text import MIMEText

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
        # [c] or variants ([ c ], [c ], [ c]) = Chad's tasks
        # [;] = someone else's task
        # > = pointer needing expansion
        # D: or Decision: = explicit decision
        # Note: Granola auto-converts [ ] into its own checkboxes,
        # so we use [c] for "Chad" tasks instead.
        MARKER_RE = re.compile(
            r"^\s*(?:[-*]\s*)?(\[;\]|\[\s*c\s*\]|>|D:|Decision:)\s+(.+)$",
            re.MULTILINE | re.IGNORECASE,
        )
        my_tasks = []
        their_tasks = []
        pointers = []
        decisions = []

        if private_notes:
            for line_num, line in enumerate(private_notes.split("\n"), 1):
                m = MARKER_RE.match(line)
                if not m:
                    continue
                marker = m.group(1).strip()
                text = m.group(2).strip()

                # Split on inline [;] markers within the captured text.
                # Users often write: [c] task1[;] task2[;] task3
                # Handle typos like [;[ and [;} as well
                INLINE_SPLIT = re.compile(r'\[;\]|\[;\[|\[;\}')
                segments = INLINE_SPLIT.split(text)

                first_marker = marker
                for idx, seg in enumerate(segments):
                    seg = seg.strip()
                    if not seg:
                        continue
                    if idx == 0:
                        cur_marker = first_marker
                    else:
                        cur_marker = "[;]"
                    item = {"marker": cur_marker, "text": seg, "line": line_num}

                    if cur_marker.lower().startswith("[") and "c" in cur_marker.lower():
                        my_tasks.append(item)
                    elif cur_marker == "[;]":
                        their_tasks.append(item)
                    elif cur_marker == ">":
                        pointers.append(item)
                    elif cur_marker in ("D:", "Decision:"):
                        decisions.append(item)

        # ── Scan for deadline hints on each action item ──
        # Patterns: "by Friday", "by EOD Tuesday", "by March 15", "by 3/18",
        # "this week", "next week", "tomorrow", "end of week", etc.
        DEADLINE_INLINE_RE = re.compile(
            r"\b(?:by|before|until|due|no later than)\s+"
            r"(?:EOD\s+|end of day\s+|COB\s+)?"
            r"("
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
            r"(?:\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?)?"
            r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*"
            r"\s+\d{1,2}(?:,?\s+\d{4})?"
            r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
            r"|tomorrow|end of (?:week|day|month)"
            r"|next (?:Monday|Tuesday|Wednesday|Thursday|Friday|week)"
            r")",
            re.IGNORECASE,
        )
        DEADLINE_WINDOW = 800
        DEADLINE_STEP = 200

        all_action_items = my_tasks + their_tasks
        for item in all_action_items:
            # First check the item text itself
            inline_match = DEADLINE_INLINE_RE.search(item["text"])
            if inline_match:
                item["deadline_hint"] = inline_match.group(0).strip()
                item["deadline_source"] = "notes"
                continue

            # Then search transcript near this action item's keywords
            if not transcript_text:
                continue
            keywords = set(
                w.lower()
                for w in re.findall(r"\w{4,}", item["text"])
            )
            if not keywords:
                continue
            best_start = 0
            best_score = 0
            for start in range(
                0, max(1, len(transcript_text) - DEADLINE_WINDOW), DEADLINE_STEP
            ):
                window = transcript_text[start : start + DEADLINE_WINDOW].lower()
                score = sum(1 for kw in keywords if kw in window)
                if score > best_score:
                    best_score = score
                    best_start = start
            if best_score >= 2:
                nearby = transcript_text[
                    best_start : best_start + DEADLINE_WINDOW
                ]
                deadline_match = DEADLINE_INLINE_RE.search(nearby)
                if deadline_match:
                    item["deadline_hint"] = deadline_match.group(0).strip()
                    item["deadline_source"] = "transcript"

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

        # ── Keyword-based proposed action extraction from AI summary ──
        # When there are no user markers, scan the AI summary for phrases
        # that suggest actions or decisions. These become "proposed" items
        # the agent can promote into a draft (labeled as Proposed).
        #
        # Granola AI summaries use markdown bullet points like:
        #   - Agreed to cancel the conference
        #   - Will email conferences@nctm.org to cancel
        #   - Chad to follow up with Hee-Sun
        #   - Scott may still attend to take notes
        #
        # We extract lines containing action verbs or decision language.

        # Pattern 1: Lines with explicit action/decision keywords
        ACTION_LINE_RE = re.compile(
            r"^\s*[-*]\s+(.+)$",  # any bullet line
            re.MULTILINE,
        )
        # Phrases within bullet lines that signal actions
        ACTION_SIGNALS = re.compile(
            r"(?:"
            r"(?:will|agreed to|need(?:s)? to|should|must|plan(?:s|ning)? to|going to)\s+\w+"
            r"|(?:next\s+(?:action|step)s?|action\s+items?)\s*[:\-;]"
            r"|(?:\w+)\s+(?:to\s+(?:follow\s*up|send|draft|review|schedule|prepare|check"
            r"|reach\s+out|connect|share|update|submit|complete|cancel|confirm|email"
            r"|contact|present|attend|coordinate|discuss|explore|investigate|finalize"
            r"|organize|arrange|set\s+up|write|create|build|implement|look\s+into"
            r"|talk\s+(?:to|with)|meet\s+with|circle\s+back|loop\s+in|flag|notify"
            r"|address|resolve|handle|process|forward|distribute|announce|propose"
            r"|convene|brief|debrief|report|document|outline|identify|assess|evaluate"
            r"|prioritize|allocate|commit|deliver|publish|register|sign\s+up|book"
            r"|reserve|order|request|apply|file|approve|sign|endorse|ratify))"
            r")",
            re.IGNORECASE,
        )
        DECISION_SIGNALS = re.compile(
            r"(?:"
            r"(?:agreed|decided|decision)\s+(?:to\s+|[:\-;])"
            r"|(?:will\s+(?:not|no\s+longer)\s+)"
            r"|(?:cancell?(?:ed|ing))"
            r"|(?:confirmed|approved|endorsed|committed\s+to)"
            r")",
            re.IGNORECASE,
        )

        proposed_actions = []
        proposed_decisions = []
        has_user_markers = bool(my_tasks or their_tasks or pointers or decisions)

        if ai_summary and not has_user_markers:
            seen_texts = set()
            for line_match in ACTION_LINE_RE.finditer(ai_summary):
                line_text = line_match.group(1).strip()
                # Skip sub-bullets (indented further) that are just context
                if line_text.startswith("-"):
                    continue
                # Skip very short or header-like lines
                if len(line_text) < 20:
                    continue

                # Check for decision signals first (decisions are a subset of actions)
                if DECISION_SIGNALS.search(line_text):
                    normalized = line_text.lower()
                    if normalized not in seen_texts:
                        seen_texts.add(normalized)
                        proposed_decisions.append({"text": line_text, "source": "ai_summary"})
                    continue

                # Check for action signals
                if ACTION_SIGNALS.search(line_text):
                    normalized = line_text.lower()
                    if normalized not in seen_texts:
                        seen_texts.add(normalized)
                        proposed_actions.append({"text": line_text, "source": "ai_summary"})

            # Also scan transcript for "next action" / "action item" phrases
            if transcript_text:
                ACTION_PHRASE_RE = re.compile(
                    r"(?:next\s+action|action\s+item)s?\s*(?:is|are|would\s+be)?\s*[:;]?\s*(.{15,120})",
                    re.IGNORECASE,
                )
                for m in ACTION_PHRASE_RE.finditer(transcript_text):
                    text = m.group(1).strip().rstrip(".")
                    normalized = text.lower()
                    if normalized not in seen_texts:
                        seen_texts.add(normalized)
                        proposed_actions.append({"text": text, "source": "transcript"})

        # ── Queue task candidates to durable memory block ──
        QUEUE_BLOCK_ID = "block-809efd9b-e2ca-4d11-af89-9a1c7710716c"
        QUEUE_BLOCK_LIMIT = 20000
        # Deduplicate by task text (multi-chunk meetings can duplicate markers)
        seen_texts = set()
        queue_items = []
        for item in my_tasks + their_tasks:
            if item["text"] not in seen_texts:
                seen_texts.add(item["text"])
                queue_items.append(item)
        queued_count = 0

        if queue_items:
            import uuid as _uuid
            from datetime import datetime as _dt

            try:
                # GET current block value
                block_url = f"{LETTA_BASE}/v1/blocks/{QUEUE_BLOCK_ID}"
                block_req = urllib.request.Request(block_url, method="GET")
                with urllib.request.urlopen(block_req, timeout=10) as block_resp:
                    block_data = json.loads(block_resp.read().decode("utf-8"))
                current_value = block_data.get("value", "")

                # Strip "(empty)" placeholder if present
                if "(empty)" in current_value:
                    current_value = current_value.replace("(empty)", "").strip()
                    if not current_value:
                        current_value = "# Queued Tasks from Meetings"

                now_str = _dt.now().strftime("%Y-%m-%d %H:%M")
                participants_str = ", ".join(participants) if participants else "unknown"
                urls_str = ", ".join(doc_urls) if doc_urls else ""

                new_entries = []
                for item in queue_items:
                    scan_id = _uuid.uuid4().hex[:8]
                    marker_type = (
                        "my_tasks" if "c" in item["marker"].lower() else "their_tasks"
                    )
                    entry_lines = [
                        f"[queued: {now_str}; scan_id: {scan_id}] meeting_id: {meeting_id}",
                        f"title: {meeting_title}",
                        f"date: {meeting_date}",
                        f"participants: {participants_str}",
                        f"granola_link: {granola_link}",
                        f"marker_type: {marker_type}",
                        f"task: {item['text']}",
                    ]
                    if item.get("deadline_hint"):
                        entry_lines.append(f"deadline_hint: {item['deadline_hint']}")
                        entry_lines.append(
                            f"deadline_source: {item.get('deadline_source', 'unknown')}"
                        )
                    if urls_str:
                        entry_lines.append(f"urls: {urls_str}")
                    new_entries.append("\n".join(entry_lines))

                # Build new block value — append entries separated by ---
                entries_text = "\n---\n".join(new_entries) + "\n---"
                if current_value.rstrip().endswith("---"):
                    new_value = current_value.rstrip() + "\n" + entries_text
                else:
                    new_value = current_value.rstrip() + "\n" + entries_text

                # Overflow guard
                if len(new_value) > QUEUE_BLOCK_LIMIT:
                    pass  # Skip queue write, log in return value
                else:
                    patch_data = json.dumps({"value": new_value}).encode("utf-8")
                    patch_req = urllib.request.Request(
                        block_url,
                        data=patch_data,
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    urllib.request.urlopen(patch_req, timeout=10)
                    queued_count = len(new_entries)

            except Exception as qe:
                pass  # Queue write failure is non-fatal; scan package still returns

        # ── Extract [c] tasks via add_extracted_tasks HTTP calls ──
        # Direct HTTP calls from within the tool are reliable and atomic.
        # Only [c] markers (my_tasks) are extracted — [;] markers are for
        # others' tasks and don't enter Chad's extracted_tasks pipeline.
        extraction_results = []
        if my_tasks:
            from datetime import datetime as _dt2

            participants_str = ", ".join(participants) if participants else "unknown"
            urls_str = ", ".join(doc_urls) if doc_urls else ""

            for item in my_tasks:
                task_text = item["text"]
                # Strip "Chad to" prefix — tasks should begin with an action verb
                # e.g. "Chad to send a follow-up" → "Send a follow-up"
                _stripped = re.sub(r'^(?:Chad\s+to\s+)', '', task_text, flags=re.IGNORECASE).strip()
                if _stripped:
                    task_text = _stripped[0].upper() + _stripped[1:]
                else:
                    task_text = task_text

                extract_payload = {
                    "task_description": task_text,
                    "source_type": "meeting",
                    "source_context": f"Meeting notes marker [c] from {meeting_title}",
                    "reference_id": f"meeting-{meeting_id}",
                    "source_text": item["text"],
                    "from_person": "Chad Dorsey (note creator)",
                    "location": meeting_title,
                    "location_id": meeting_id,
                    "source_timestamp": meeting_date if "T" in str(meeting_date) else f"{meeting_date}T00:00:00Z",
                    "origin": "user-indicated",
                }
                if item.get("deadline_hint"):
                    extract_payload["due_date"] = item["deadline_hint"]
                if urls_str:
                    extract_payload["related_urls"] = urls_str
                # Cleanup: use scan_id if we queued, otherwise skip cleanup
                # The scan_id was generated in the queue section above
                if queued_count > 0:
                    extract_payload["cleanup_block_id"] = QUEUE_BLOCK_ID
                    # Find the scan_id for this item from queue_items
                    for qi in queue_items:
                        if qi["text"] == item["text"]:
                            # Reconstruct scan_id — look for it in new_entries
                            for entry_str in new_entries:
                                if item["text"] in entry_str:
                                    import re as _re2
                                    sid_match = _re2.search(r"scan_id: ([a-f0-9]{8})", entry_str)
                                    if sid_match:
                                        extract_payload["cleanup_entry_identifier"] = sid_match.group(1)
                                    break
                            break

                try:
                    extract_url = f"{LETTA_BASE}/v1/tools/call"
                    # Call add_extracted_tasks via direct Letta tool invocation
                    # Since this tool runs in the agent sandbox, we call the
                    # extraction tool's HTTP endpoint pattern instead.
                    # Use the Letta blocks/archives API directly (same as the
                    # extracted_tasks_tool does internally).
                    #
                    # Actually, the simplest approach: POST to the agent's
                    # messages endpoint with a structured extraction request.
                    # But that would be agent-triggered, not tool-level.
                    #
                    # Best approach: call the extraction function's logic via
                    # a direct HTTP POST to a helper endpoint. Since no such
                    # endpoint exists, we replicate the core logic inline.
                    #
                    # Replicate the core add_extracted_tasks logic:
                    import uuid as _uuid2
                    ref_id = _uuid2.uuid4().hex[:8]
                    now_et = _dt2.now()
                    try:
                        import pytz as _pytz
                        tz_et = _pytz.timezone("America/New_York")
                        now_et = _dt2.now(tz_et)
                    except Exception:
                        pass
                    timestamp_str = now_et.strftime("%Y-%m-%d %H:%M")
                    iso_timestamp = now_et.isoformat()
                    year_month = now_et.strftime("%Y-%m")

                    # Get agent name (already known from AGENT_ID)
                    try:
                        agent_info_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
                        agent_info_req = urllib.request.Request(agent_info_url, method="GET")
                        with urllib.request.urlopen(agent_info_req, timeout=10) as aresp:
                            agent_info = json.loads(aresp.read().decode("utf-8"))
                            agent_name = agent_info.get("name", "Unknown Agent")
                    except Exception:
                        agent_name = "Unknown Agent"

                    # Step A: Update extracted_tasks block
                    try:
                        with urllib.request.urlopen(
                            urllib.request.Request(f"{LETTA_BASE}/v1/agents/{AGENT_ID}", method="GET"),
                            timeout=10,
                        ) as a_resp:
                            a_data = json.loads(a_resp.read().decode("utf-8"))
                            blocks = a_data.get("memory", {}).get("blocks", [])
                        et_block = None
                        for blk in blocks:
                            if blk.get("label") == "extracted_tasks":
                                et_block = blk
                                break

                        if et_block:
                            et_block_id = et_block["id"]
                            et_value = et_block.get("value", "")
                            section_header = f"=== {agent_name} ({AGENT_ID}) ==="
                            origin_part = "; origin: user-indicated"
                            task_line = f"[extracted_time: {timestamp_str}; ref_id: {ref_id}{origin_part}] {task_text}\n\n"

                            section_pat = re.compile(
                                rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9-]+\)\s+===)|$)',
                                re.DOTALL,
                            )
                            sec_match = section_pat.search(et_value)
                            if sec_match:
                                insert_pos = sec_match.end()
                                before = et_value[:insert_pos]
                                after = et_value[insert_pos:]
                                if before and not before.endswith("\n"):
                                    before += "\n"
                                new_et_value = before + task_line + after
                            else:
                                new_et_value = et_value + f"\n{section_header}\n{task_line}"

                            et_patch = json.dumps({"value": new_et_value}).encode("utf-8")
                            et_req = urllib.request.Request(
                                f"{LETTA_BASE}/v1/blocks/{et_block_id}",
                                data=et_patch,
                                headers={"Content-Type": "application/json"},
                                method="PATCH",
                            )
                            urllib.request.urlopen(et_req, timeout=10)
                    except Exception:
                        pass  # Block update failure non-fatal for scan

                    # Step B: Insert archival passage
                    passage_id = ""
                    try:
                        source_ts = extract_payload["source_timestamp"]
                        origin_line = "ORIGIN: user-indicated\n"
                        metadata_section = ""
                        if item.get("deadline_hint"):
                            metadata_section = f"\nTASK METADATA\n- Due: {item['deadline_hint']}\n"

                        urls_section = ""
                        if urls_str:
                            url_list = [u.strip() for u in urls_str.split(",") if u.strip()]
                            if url_list:
                                urls_section = "\nRELATED URLS\n" + "\n".join(f"- {u}" for u in url_list) + "\n"

                        passage_text = (
                            f"TASK: {task_text}\n"
                            f"REF_ID: {ref_id}\n"
                            f"{origin_line}"
                            f"{metadata_section}\n"
                            f"SOURCE REFERENCE\n"
                            f"- Type: meeting\n"
                            f"- Context: Meeting notes marker [c] from {meeting_title}\n"
                            f"- Reference ID: meeting-{meeting_id}\n"
                            f"\n"
                            f"SOURCE METADATA\n"
                            f"- Timestamp: {source_ts}\n"
                            f"- From: Chad Dorsey (note creator)\n"
                            f"- Location: {meeting_title}\n"
                            f"- Location ID: {meeting_id}\n"
                            f"{urls_section}\n"
                            f"TIMESTAMPS\n"
                            f"- Source: {source_ts}\n"
                            f"- Extracted: {iso_timestamp}\n"
                            f"- OmniFocus: pending\n"
                            f"\n"
                            f"OMNIFOCUS\n"
                            f"- Task ID: pending\n"
                            f"- Status: extracted\n"
                            f"\n"
                            f"SOURCE TEXT\n"
                            f"{item['text']}"
                        )

                        tags = [
                            "source:meeting",
                            year_month,
                            "status:extracted",
                            "origin:user-indicated",
                            f"agent:{AGENT_ID}",
                        ]

                        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
                        arch_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages"
                        arch_data = json.dumps({"text": passage_text, "tags": tags}).encode("utf-8")
                        arch_req = urllib.request.Request(
                            arch_url,
                            data=arch_data,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with urllib.request.urlopen(arch_req, timeout=30) as arch_resp:
                            arch_result = json.loads(arch_resp.read().decode("utf-8"))
                            passage_id = arch_result.get("id", "")
                    except Exception:
                        pass  # Archival failure non-fatal for scan

                    # Step C: Queue cleanup (remove entry from queue block)
                    cleanup_id = extract_payload.get("cleanup_entry_identifier")
                    if cleanup_id and queued_count > 0:
                        try:
                            cb_url = f"{LETTA_BASE}/v1/blocks/{QUEUE_BLOCK_ID}"
                            cb_req = urllib.request.Request(cb_url, method="GET")
                            with urllib.request.urlopen(cb_req, timeout=10) as cb_resp:
                                cb_data = json.loads(cb_resp.read().decode("utf-8"))
                            cb_value = cb_data.get("value", "")
                            parts = cb_value.split("---")
                            orig_count = len(parts)
                            filtered = [p for p in parts if cleanup_id not in p]
                            if len(filtered) < orig_count:
                                filtered = [p for p in filtered if p.strip()]
                                new_cb_value = "---".join(filtered).strip()
                                if new_cb_value:
                                    new_cb_value += "\n---"
                                cb_patch = json.dumps({"value": new_cb_value}).encode("utf-8")
                                cb_patch_req = urllib.request.Request(
                                    cb_url,
                                    data=cb_patch,
                                    headers={"Content-Type": "application/json"},
                                    method="PATCH",
                                )
                                urllib.request.urlopen(cb_patch_req, timeout=10)
                        except Exception:
                            pass

                    extraction_results.append({
                        "task": task_text,
                        "ref_id": ref_id,
                        "passage_id": passage_id,
                        "status": "extracted",
                    })

                except Exception as ext_err:
                    extraction_results.append({
                        "task": task_text,
                        "ref_id": "",
                        "passage_id": "",
                        "status": f"error: {str(ext_err)[:100]}",
                    })

        # ── Pre-compute prepare_meeting_followup args ──
        # Embedding these in the return ensures the agent sees them even
        # after context compaction (tool returns survive compaction).
        followup_my = []
        for item in my_tasks:
            action = item["text"]
            # [c] markers are Chad's tasks — ensure they start with "Chad to"
            if not action.lower().startswith("chad to"):
                action = "Chad to " + action[0].lower() + action[1:]
            # Append deadline only if not already present in the task text
            if item.get("deadline_hint"):
                hint_text = item["deadline_hint"]
                if hint_text.lower() not in action.lower():
                    action += f" {hint_text}"
            followup_my.append(action)

        followup_their = []
        for item in their_tasks:
            # [;] markers already contain the assignee in the bullet text
            # (e.g., "Susan to review the budget") — leave as-is
            action = item["text"]
            # Append deadline only if not already present in the task text
            if item.get("deadline_hint"):
                hint_text = item["deadline_hint"]
                if hint_text.lower() not in action.lower():
                    action += f" {hint_text}"
            followup_their.append(action)

        followup_decisions = [item["text"] for item in decisions]

        # Merge proposed items into followup args when no user markers
        is_proposed = False
        if not has_user_markers and (proposed_actions or proposed_decisions):
            is_proposed = True
            # Use proposed items as the followup content
            for pa in proposed_actions:
                followup_my.append(pa["text"])
            for pd in proposed_decisions:
                followup_decisions.append(pd["text"])

        next_action = {
            "tool": "prepare_meeting_followup",
            "pre_computed_args": {
                "meeting_id": meeting_id,
                "meeting_title": meeting_title,
                "meeting_date": meeting_date,
                "participants": ", ".join(participants),
                "decisions": " | ".join(followup_decisions),
                "my_actions": " | ".join(followup_my),
                "their_actions": " | ".join(followup_their),
                "proposed": is_proposed,
            },
            "instruction": (
                "The followup email draft has ALREADY been created (see draft_result). "
                "Do NOT call prepare_meeting_followup — it was created inline. "
                "Report the draft_result to the user. If draft_result is null and there "
                "are actions/decisions in pre_computed_args, you may call "
                "prepare_meeting_followup as a fallback with the pre_computed_args above. "
                "CRITICAL: Pass the 'proposed' field exactly as shown in pre_computed_args. "
                "IMPORTANT: Pass participants EXACTLY as provided — including the "
                "'Name <email>' format. Do not strip email addresses."
            ),
        }

        # ── Create followup email draft directly ──
        # Previously the agent was instructed to relay pre_computed_args to
        # prepare_meeting_followup, but the agent often mangled them (squishing
        # multiple markers into one bullet). Creating the draft inline is reliable.
        draft_result = None
        all_followup_items = followup_decisions + followup_my + followup_their
        if all_followup_items:
            try:
                import pytz as _pytz_fu
                _tz_fu = _pytz_fu.timezone("America/New_York")
                from datetime import datetime as _dt_fu
                _now_fu = _dt_fu.now(_tz_fu)
            except Exception:
                from datetime import datetime as _dt_fu
                _now_fu = _dt_fu.now()

            GWS_TIMEOUT = 15
            SENDER_EMAIL = "cdorsey@concord.org"
            EMAIL_RE_FU = re.compile(r"<([^>]+@[^>]+)>")

            # Extract recipient emails from participants
            emails_list_fu = []
            for entry in participants:
                email_match = EMAIL_RE_FU.search(entry)
                if email_match:
                    email = email_match.group(1)
                    if email.lower() != SENDER_EMAIL:
                        emails_list_fu.append(email)

            # Time-aware opening
            try:
                meeting_hour = int(meeting_date.split(" ")[1].split(":")[0]) if " " in str(meeting_date) else -1
            except (ValueError, IndexError):
                meeting_hour = -1
            if 0 <= meeting_hour < 12:
                time_phrase = "this morning"
            elif 12 <= meeting_hour < 17:
                time_phrase = "this afternoon"
            else:
                time_phrase = "today"

            # Build HTML email body
            html_parts_fu = []
            html_parts_fu.append("<p>Folks,</p>")
            html_parts_fu.append(
                f"<p>Thanks for a great meeting {time_phrase}. I&#39;ve summarized "
                "below the decisions and next actions I captured. Please let me know "
                "if your notes differ from mine.</p>"
            )
            html_parts_fu.append("<p>--Chad</p>")
            html_parts_fu.append("<p>=====</p>")
            html_parts_fu.append("<p><b>Decisions / Next Actions</b></p>")

            # Strip leading auxiliary verbs
            LEADING_VERB_RE_FU = re.compile(
                r"^(?:will|shall|should|must|needs?\s+to|has\s+to|have\s+to"
                r"|agreed\s+to|plans?\s+to|planning\s+to|going\s+to"
                r"|is\s+going\s+to|was\s+going\s+to)\s+",
                re.IGNORECASE,
            )

            li_items = []
            # Decisions
            for d in followup_decisions:
                cap_d = d[0].upper() + d[1:] if d else d
                li_items.append(f"<li><i>Decision</i> &#8211; {cap_d}</li>")

            # My actions
            for a in followup_my:
                if not a:
                    continue
                a_lower = a.lower()
                if a_lower.startswith("chad to ") or a_lower.startswith("chad: "):
                    prefix_len = 8 if a_lower.startswith("chad to ") else 6
                    rest = a[prefix_len:]
                    rest = LEADING_VERB_RE_FU.sub("", rest)
                    li_items.append(f"<li>{a[:prefix_len]}{rest}</li>")
                else:
                    stripped = LEADING_VERB_RE_FU.sub("", a)
                    li_items.append(f"<li>Chad to {stripped[0].lower()}{stripped[1:]}</li>")

            # Their actions
            for a in followup_their:
                if not a:
                    continue
                name_to_match = re.match(r"^(\w+(?:\s+\w+)?\s+to\s+)", a, re.IGNORECASE)
                if name_to_match:
                    prefix = name_to_match.group(1)
                    rest = a[len(prefix):]
                    rest = LEADING_VERB_RE_FU.sub("", rest)
                    li_items.append(f"<li>{prefix}{rest}</li>")
                else:
                    li_items.append(f"<li>{a}</li>")

            if li_items:
                html_parts_fu.append("<ul>" + "".join(li_items) + "</ul>")

            body_html_fu = "".join(html_parts_fu)

            # Create MIME message and Gmail draft
            mime_msg = MIMEText(body_html_fu, "html")
            mime_msg["To"] = ", ".join(emails_list_fu)
            subject_fu = f"{meeting_title} - meeting summary"
            mime_msg["Subject"] = subject_fu
            raw_fu = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

            _cmd_fu = ["gws", "gmail", "users", "drafts", "create",
                       "--params", json.dumps({"userId": "me"}),
                       "--json", json.dumps({"message": {"raw": raw_fu}}),
                       "--format", "json"]
            _r_fu = subprocess.run(_cmd_fu, capture_output=True, text=True, timeout=GWS_TIMEOUT)

            if _r_fu.returncode == 0 and _r_fu.stdout.strip():
                draft_data = json.loads(_r_fu.stdout)
                draft_id_fu = draft_data.get("id", "")
                draft_msg_fu = draft_data.get("message", {})
                message_id_fu = draft_msg_fu.get("id", "")

                # Apply "Followup" label (and "Proposed" if applicable)
                label_ids_to_add = []
                if message_id_fu:
                    _cmd_labels = ["gws", "gmail", "users", "labels", "list",
                                   "--params", json.dumps({"userId": "me"}),
                                   "--format", "json"]
                    _r_labels = subprocess.run(_cmd_labels, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                    if _r_labels.returncode == 0 and _r_labels.stdout.strip():
                        all_labels = json.loads(_r_labels.stdout).get("labels", [])
                        # Find Followup label
                        followup_label_id = None
                        for lbl in all_labels:
                            if lbl["name"] == "Followup":
                                followup_label_id = lbl["id"]
                                break
                        if followup_label_id:
                            label_ids_to_add.append(followup_label_id)

                        # Apply Proposed label if no user markers
                        if is_proposed:
                            proposed_label_id = None
                            for lbl in all_labels:
                                if lbl["name"] == "Proposed":
                                    proposed_label_id = lbl["id"]
                                    break
                            if proposed_label_id:
                                label_ids_to_add.append(proposed_label_id)

                        if label_ids_to_add:
                            _cmd_modify = ["gws", "gmail", "users", "messages", "modify",
                                           "--params", json.dumps({"userId": "me", "id": message_id_fu}),
                                           "--json", json.dumps({"addLabelIds": label_ids_to_add}),
                                           "--format", "json"]
                            subprocess.run(_cmd_modify, capture_output=True, text=True, timeout=GWS_TIMEOUT)

                draft_result = {
                    "status": "ok",
                    "draft_id": draft_id_fu,
                    "message_id": message_id_fu,
                    "email_to": ", ".join(emails_list_fu),
                    "email_subject": subject_fu,
                    "proposed": is_proposed,
                    "items_count": len(li_items),
                }
            else:
                draft_result = {
                    "status": "error",
                    "error_message": _r_fu.stderr[:300] if _r_fu.stderr else f"gws exit {_r_fu.returncode}",
                }

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
                "decisions": decisions,
            },
            "proposed_items": {
                "actions": proposed_actions,
                "decisions": proposed_decisions,
            },
            "has_user_markers": has_user_markers,
            "scannable_content": scannable_content,
            "has_user_notes": bool(private_notes),
            "doc_urls_found": doc_urls,
            "queued_to_block": queued_count,
            "extraction_results": extraction_results,
            "draft_result": draft_result,
            "next_action": next_action,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
