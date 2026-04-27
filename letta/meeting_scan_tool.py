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
            # Granola exports escape markdown brackets as `\[c\]` / `\[;\]`.
            # Normalize so the marker regex (which expects plain `[c]` /
            # `[;]`) matches both forms. Affects only the pre-bracket and
            # post-bracket backslash characters; doesn't touch other escapes.
            private_notes = re.sub(r'\\([\[\]])', r'\1', private_notes)

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
            r"^\s*(?:[-*]\s*)?(\[;\]|\[\s*c\s*[\]\[]|>|D:|Decision:)\s+(.+)$",
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

        # ── Queue task candidates to pa_web.task_queue (Cycle-1 Pattern 2) ──
        # Cutover 2026-04-26: replaces block-PATCH on
        # block-809efd9b-... with Postgres INSERT into pa_web.task_queue
        # source='meeting'. Each candidate gets a unique source_ref so the
        # UNIQUE (source, source_ref) constraint can dedup re-scans.
        # Deduplicate by task text (multi-chunk meetings can duplicate markers)
        seen_texts = set()
        queue_items = []
        for item in my_tasks + their_tasks:
            if item["text"] not in seen_texts:
                seen_texts.add(item["text"])
                queue_items.append(item)
        queued_count = 0

        if queue_items:
            import os as _os
            import hashlib as _hashlib
            from datetime import datetime as _dt
            try:
                import psycopg as _psycopg
                from psycopg.types.json import Jsonb as _Jsonb
            except Exception:
                _psycopg = None
                _Jsonb = None

            if _psycopg is not None:
                try:
                    pg_password = _os.environ.get("POSTGRES_PASSWORD", "")
                    pg_url = _os.environ.get(
                        "PA_WEB_POSTGRES_URL",
                        f"postgresql://postgres:{pg_password}@supabase-db:5432/postgres",
                    )
                    participants_str = ", ".join(participants) if participants else "unknown"
                    urls_list = list(doc_urls) if doc_urls else []
                    now_iso = _dt.now().isoformat()

                    rows_to_insert = []
                    for item in queue_items:
                        # Stable source_ref: meeting_id + sha8 of task text
                        text_hash = _hashlib.sha256(item["text"].encode()).hexdigest()[:8]
                        source_ref = f"meeting-{meeting_id}-{text_hash}"
                        marker_type = (
                            "my_tasks" if "c" in item["marker"].lower() else "their_tasks"
                        )
                        payload = {
                            "queued_at": now_iso,
                            "meeting_id": meeting_id,
                            "title": meeting_title,
                            "date": meeting_date,
                            "participants": participants,
                            "granola_link": granola_link,
                            "marker_type": marker_type,
                            "task": item["text"],
                            "related_urls": urls_list,
                        }
                        if item.get("deadline_hint"):
                            payload["deadline_hint"] = item["deadline_hint"]
                            payload["deadline_source"] = item.get("deadline_source", "unknown")
                        rows_to_insert.append((source_ref, _Jsonb(payload)))

                    with _psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as _conn:
                        with _conn.cursor() as _cur:
                            for sref, payload in rows_to_insert:
                                _cur.execute(
                                    """
                                    INSERT INTO pa_web.task_queue (source, source_ref, payload)
                                    VALUES ('meeting', %s, %s)
                                    ON CONFLICT (source, source_ref) DO NOTHING
                                    RETURNING id
                                    """,
                                    (sref, payload),
                                )
                                if _cur.fetchone():
                                    queued_count += 1
                except Exception as qe:
                    pass  # Queue write failure is non-fatal; scan package still returns

        # ── Extract [c] tasks via spark queue ──
        # Write sparks for each [c] marker task. process_spark_queue handles
        # the extraction deterministically. Falls back to inline extraction
        # if spark write fails.
        extraction_results = []
        if my_tasks:
            import uuid as _uuid2

            participants_str = ", ".join(participants) if participants else "unknown"
            urls_str = ", ".join(doc_urls) if doc_urls else ""
            source_ts = meeting_date if "T" in str(meeting_date) else f"{meeting_date}T00:00:00Z"

            # Cycle-1 Pattern 2 cutover (2026-04-26): write to
            # pa_web.task_queue with source='meeting_marker' instead of
            # PATCHing block-534bb56d-... The unique source_ref is the
            # spark_id, which is generated per-marker.
            import os as _os_sp
            try:
                import psycopg as _psycopg_sp
                from psycopg.types.json import Jsonb as _Jsonb_sp
            except Exception:
                _psycopg_sp = None
                _Jsonb_sp = None

            pg_password_sp = _os_sp.environ.get("POSTGRES_PASSWORD", "")
            pg_url_sp = _os_sp.environ.get(
                "PA_WEB_POSTGRES_URL",
                f"postgresql://postgres:{pg_password_sp}@supabase-db:5432/postgres",
            )

            for item in my_tasks:
                task_text = item["text"]
                # Strip "Chad to" prefix
                _stripped = re.sub(r'^(?:Chad\s+to\s+)', '', task_text, flags=re.IGNORECASE).strip()
                if _stripped:
                    task_text = _stripped[0].upper() + _stripped[1:]

                spark_id = _uuid2.uuid4().hex[:8]
                # Build spark record
                spark = {
                    "spark_id": spark_id,
                    "captured_at": source_ts,
                    "source_type": "meeting",
                    "origin": "user-indicated",
                    "reference_id": f"meeting-{meeting_id}-{spark_id}",
                    "source_text": item["text"],
                    "from_person": "Chad Dorsey (note creator)",
                    "location": meeting_title,
                    "location_id": meeting_id,
                    "permalink": granola_link or "",
                    "related_urls": doc_urls,
                    "marker_type": "explicit",
                    "task_hint": task_text,
                    "user_notes": None,
                    "surrounding_context": participants_str,
                    "fetch_hint": f"granola:{meeting_id}",
                }
                if item.get("deadline_hint"):
                    spark["deadline_hint"] = item["deadline_hint"]

                if _psycopg_sp is None:
                    extraction_results.append({
                        "task": task_text,
                        "ref_id": "",
                        "status": "spark_failed: psycopg unavailable",
                    })
                    continue

                try:
                    with _psycopg_sp.connect(pg_url_sp, autocommit=True, connect_timeout=10) as _conn_sp:
                        with _conn_sp.cursor() as _cur_sp:
                            _cur_sp.execute(
                                """
                                INSERT INTO pa_web.task_queue (source, source_ref, payload)
                                VALUES ('meeting_marker', %s, %s)
                                ON CONFLICT (source, source_ref) DO NOTHING
                                RETURNING id
                                """,
                                (spark["reference_id"], _Jsonb_sp(spark)),
                            )
                            row_sp = _cur_sp.fetchone()
                    extraction_results.append({
                        "task": task_text,
                        "ref_id": spark_id,
                        "status": "spark_queued" if row_sp else "spark_dedup",
                    })
                except Exception as spark_err:
                    extraction_results.append({
                        "task": task_text,
                        "ref_id": "",
                        "status": f"spark_failed: {str(spark_err)[:80]}",
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
