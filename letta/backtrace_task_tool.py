"""
Backtrace Task Tool for Letta

Phase B materials preparation: fetches full source content, extracts structured
anchors, searches archival for related passages, and returns raw materials for
agent synthesis. Does NOT write PACKET INFO — that's write_packet_info's job.

The agent (MC, tasks-agent, or sleeptime) drives the backtrace loop:
  1. backtrace_task(ref_id) → returns hard center (source content, anchors, hits, hop candidates)
  2. Agent reviews, decides whether to chase hop candidates
  3. Agent calls fetch_source_content for selected hops
  4. Agent synthesizes and calls write_packet_info when satisfied

Tool: backtrace_task
"""

from typing import Dict, Any, Optional


def backtrace_task(ref_id: str, max_hops: Optional[int] = None) -> Dict[str, Any]:
    """
    Fetch and search materials for cross-source backtracing of a task.

    Returns structured raw materials: full source content, extracted anchors,
    search_terms, and hop candidates for the agent to evaluate. Does NOT write
    to archival — use write_packet_info for that.

    The return value is the "hard center" that's immediately usable regardless
    of whether the agent does further hops.

    Args:
        ref_id: The 8-char hex reference ID of the task to backtrace.
        max_hops: Maximum iterative search rounds (default 3).

    Returns:
        Dictionary with source_content, anchors, search_terms, hop_candidates,
        and node_coverage.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.environ.get("TASKS_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
        hops = max_hops or 3

        if not ref_id:
            return {"status": "error", "error_message": "ref_id is required"}

        # ── Step 1: Fetch task context from pa_web.tasks (cycle-1 canonical) ──
        # The earlier extracted_tasks_archive path was retired 2026-05-30.
        # All current and historical tasks live in pa_web.tasks; everything
        # the legacy passage carried (task_desc, source_type, from_person,
        # location, reference_id, source_text, fetch_hint) is derivable
        # from the row + source_metadata JSONB.
        task_desc = ""
        source_type = ""
        from_person = ""
        location = ""
        location_id = ""
        reference_id = ""
        source_text_field = ""
        fetch_hint = ""

        # Inline pa_web.tasks query (Letta tool extraction requires
        # imports + logic in the function body).
        if True:
            try:
                import psycopg as _pg
                pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
                if not pg_url:
                    pw = os.environ.get("POSTGRES_PASSWORD", "")
                    pg_url = f"postgresql://postgres:{pw}@supabase-db:5432/postgres"
                with _pg.connect(pg_url, autocommit=True, connect_timeout=10) as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            """SELECT raw_description, suggested_title, source, source_ref,
                                      source_metadata, task_body, origin
                                 FROM pa_web.tasks WHERE ref_id = %s""",
                            (ref_id,),
                        )
                        _row = _cur.fetchone()
                if _row is None:
                    return {"status": "error", "error_message": f"No row in pa_web.tasks (or archival) for ref_id {ref_id}"}
                _raw, _sug, _src, _sref, _smeta, _body, _origin = _row
                task_desc = _sug or _raw or ""
                source_type = _src or "unknown"
                reference_id = _sref or ""
                location_id = _sref or ""
                source_text_field = _body or _raw or ""
                smeta = _smeta or {}
                if _origin:
                    from_person = _origin
                elif source_type == "email":
                    from_person = smeta.get("from") or smeta.get("sender") or ""
                elif source_type == "slack":
                    from_person = smeta.get("user_name") or smeta.get("user") or ""
                # Source-specific fetch_hint derivation (mirrors fetch_source_content)
                if source_type == "email":
                    mid = smeta.get("message_id") or smeta.get("location_id")
                    if mid:
                        fetch_hint = f"gmail:{mid}"
                    elif _sref and _sref.startswith("email-"):
                        fetch_hint = f"gmail:{_sref[6:]}"
                elif source_type in ("meeting", "meeting_marker"):
                    mid = smeta.get("meeting_id") or smeta.get("location_id")
                    if mid:
                        fetch_hint = f"granola:{mid}"
                else:
                    # slack, google-docs-comment, drive, generic
                    fetch_hint = _sref or ""
            except Exception as _e:
                return {"status": "error", "error_message": f"pa_web.tasks fallback failed for {ref_id}: {_e}"}

        # Extract participants from passage
        participants = []
        if from_person:
            email_match = re.search(r"<([^>]+)>", from_person)
            if email_match:
                participants.append(email_match.group(1))

        # ── Step 2: Fetch full source content ──
        full_content = ""
        if fetch_hint:
            try:
                import subprocess
                if fetch_hint.startswith("gmail:"):
                    msg_id = fetch_hint.split(":", 1)[1]
                    result = subprocess.run(
                        ["gws", "gmail", "users", "messages", "get",
                         "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"}),
                         "--format", "json"],
                        capture_output=True, text=True, timeout=15,
                    )
                    if result.returncode == 0:
                        import base64
                        raw = "\n".join(l for l in result.stdout.split("\n") if not l.startswith("Using keyring"))
                        msg = json.loads(raw)
                        payload = msg.get("payload", {})
                        parts_to_check = [payload]
                        while parts_to_check:
                            part = parts_to_check.pop(0)
                            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                                full_content = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
                                break
                            parts_to_check.extend(part.get("parts", []))
                elif fetch_hint.startswith("granola:"):
                    mid = fetch_hint.split(":", 1)[1]
                    api_key = os.environ.get("GRANOLA_API_KEY", "")
                    if mid and api_key:
                        g_req = urllib.request.Request(
                            f"https://public-api.granola.ai/v1/notes/{mid}?include=transcript",
                            headers={"Authorization": f"Bearer {api_key}",
                                     "Accept": "application/json"},
                        )
                        with urllib.request.urlopen(g_req, timeout=15) as g_resp:
                            note = json.loads(g_resp.read().decode("utf-8"))
                        bits = []
                        if note.get("web_url"):
                            bits.append(note["web_url"])  # harvestable URL
                        if note.get("summary_text") or note.get("summary_markdown"):
                            bits.append(note.get("summary_text") or note.get("summary_markdown"))
                        t = note.get("transcript")
                        if isinstance(t, list):
                            bits.extend(f"{e.get('speaker','')}: {e.get('text','')}"
                                        for e in t[:200] if e.get("text"))
                        elif isinstance(t, str):
                            bits.append(t)
                        full_content = "\n".join(bits)
            except (FileNotFoundError, Exception):
                pass

        # slack + docs-comment: reuse fetch_source_content's proximity window
        # (thread replies, ±N surrounding messages, comment quoted-passage) so the
        # anchor extraction below runs over the FULL local context, not just the
        # thin row excerpt. This is what turns surrounding-thread links/people/
        # proper-nouns into search_terms for the cross-channel fan-out.
        if not full_content and source_type in ("slack", "google-docs-comment"):
            try:
                from letta.fetch_source_content_tool import fetch_source_content
                _fsc = fetch_source_content(ref_id=ref_id)
                if isinstance(_fsc, dict) and _fsc.get("status") == "ok":
                    full_content = _fsc.get("content", "") or ""
            except Exception:
                pass

        if not full_content:
            full_content = source_text_field

        # ── Step 3: Extract structured anchors ──
        all_text = f"{task_desc} {full_content}".replace("\r\n", "\n").replace("\r", "\n")

        # Minimal stopwords — only function words and ever-present scaffolding
        STOP = {
            "a", "an", "the", "and", "or", "but", "for", "of", "in", "on",
            "to", "at", "by", "is", "it", "be", "as", "do", "if", "so",
            "no", "not", "we", "us", "my", "me", "he", "hi",
            "this", "that", "with", "from", "have", "has", "had", "are",
            "was", "will", "can", "our", "all", "also", "just", "been",
            "about", "some", "into", "your", "you", "its",
            "chad", "dorsey", "chad dorsey",
            "re", "cc", "am", "pm", "ok", "id",
            "sent", "subject", "external", "use", "caution",
            "best", "thanks", "regards", "sincerely", "dear",
        }

        # --- Anchor extraction ---
        anchors_urls = []
        anchors_doc_ids = []
        anchors_proper_nouns = []
        anchors_distinctive = []
        anchors_acronyms = []

        # Seed artifact URLs from source_metadata (permalink / web_url / source_url)
        # so a clean task body without inline links still surfaces the source as a
        # hop candidate.
        for _k in ("permalink", "web_url", "source_url"):
            _v = (smeta or {}).get(_k)
            if _v and _v not in anchors_urls:
                anchors_urls.append(_v)

        # URLs + domains + doc IDs
        urls_found = re.findall(r"https?://[^\s<>\"]+", all_text)
        for u in urls_found:
            anchors_urls.append(u)
            # Extract Drive doc IDs
            drive_match = re.search(r"docs\.google\.com/[^/]+/d/([a-zA-Z0-9_-]+)", u)
            if drive_match:
                anchors_doc_ids.append(drive_match.group(1))

        # Multi-word proper nouns (single line only)
        seen_nouns = set()
        for pn in re.findall(r"[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+", all_text):
            first_word = pn.split()[0].lower()
            if first_word in STOP or pn.lower() in STOP:
                continue
            if pn.lower() not in seen_nouns and len(pn) > 4:
                seen_nouns.add(pn.lower())
                anchors_proper_nouns.append(pn)

        # CamelCase project names (PhET, TechNexus)
        for cc in re.findall(r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b", all_text):
            if cc.lower() not in STOP and cc not in anchors_proper_nouns:
                anchors_proper_nouns.append(cc)

        # Single capitalized words >3 chars
        for sc in re.findall(r"\b([A-Z][a-z]{3,})\b", all_text):
            if sc.lower() not in STOP and sc.lower() not in seen_nouns:
                seen_nouns.add(sc.lower())
                anchors_proper_nouns.append(sc)

        # Person name from source
        person_name = ""
        if from_person:
            person_name = re.sub(r"\s*[\(<].*", "", from_person).strip()
            if person_name and person_name.lower() not in STOP:
                anchors_proper_nouns.append(person_name)

        # Acronyms (2+ uppercase)
        for a in re.findall(r"\b([A-Z]{2,})\b", all_text):
            if a.lower() not in STOP and a not in anchors_acronyms:
                anchors_acronyms.append(a)

        # Compound acronym phrases (CC BY, CC BY-NC)
        for ca in re.findall(r"\b([A-Z]{2,}\s+[A-Z]{2,}(?:[-][A-Z]{2,})?)\b", all_text):
            if ca not in anchors_acronyms:
                anchors_acronyms.append(ca)

        # Distinctive phrases from task description (multi-word, lowercase included)
        desc_words = task_desc.split()
        for i in range(len(desc_words)):
            w = desc_words[i]
            w_clean = w.lower().rstrip(".,;:!?'s")
            if len(w_clean) > 5 and w_clean not in STOP:
                if w_clean not in anchors_distinctive:
                    anchors_distinctive.append(w_clean)
            if w[0:1].isupper() and len(w) > 3 and w.lower() not in STOP:
                if w not in anchors_proper_nouns and w not in anchors_distinctive:
                    anchors_distinctive.append(w)

        # Build search term list (flattened, deduplicated, priority-ordered)
        search_terms = []
        seen = set()
        for term_list in [anchors_distinctive, anchors_proper_nouns, anchors_acronyms]:
            for t in term_list:
                t_clean = t.strip()
                if t_clean and t_clean.lower() not in seen and len(t_clean) > 1:
                    seen.add(t_clean.lower())
                    search_terms.append(t_clean)
        # Add domains from URLs
        for u in anchors_urls[:5]:
            domain_match = re.search(r"https?://([^/\s]+)", u)
            if domain_match:
                d = domain_match.group(1)
                if d not in ("mail.google.com", "docs.google.com", "slack.com",
                             "www.google.com", "www.linkedin.com") and d.lower() not in seen:
                    seen.add(d.lower())
                    search_terms.append(d)

        search_terms = search_terms[:20]

        # Hop candidates = URLs already present in the source content / metadata.
        # Cross-channel discovery now happens in `task xsearch` (agent-driven),
        # not here — this tool's job is anchors + search_terms + inline URLs.
        hop_candidates = []
        for u in anchors_urls[:8]:
            if "drive.google.com" in u or "docs.google.com" in u:
                hop_candidates.append({"ref": u, "type": "drive_doc",
                                       "node_likelihood": "artifact_provenance",
                                       "reason": "Drive/Docs link in source content"})
            elif "slack.com/archives" in u:
                hop_candidates.append({"ref": u, "type": "slack_thread",
                                       "node_likelihood": "direct_action",
                                       "reason": "Slack permalink in source content"})

        node_coverage = {"direct_action": True,
                         "artifact_provenance": bool(anchors_doc_ids or hop_candidates),
                         "intent_genesis": False}

        return {
            "status": "ok",
            "ref_id": ref_id,
            "task": task_desc,
            "source_content": full_content[:3000],
            "source_type": source_type,
            "fetch_hint": fetch_hint,
            "anchors": {
                "urls": anchors_urls[:10],
                "doc_ids": anchors_doc_ids,
                "proper_nouns": anchors_proper_nouns[:15],
                "distinctive_phrases": anchors_distinctive[:10],
                "acronyms": anchors_acronyms[:10],
                "participants": participants,
            },
            "search_terms": search_terms,
            "hop_candidates": hop_candidates[:10],
            "node_coverage": node_coverage,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
