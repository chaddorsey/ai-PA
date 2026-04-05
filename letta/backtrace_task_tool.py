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
    archival hits classified by type, and hop candidates for the agent to
    evaluate. Does NOT write to archival — use write_packet_info for that.

    The return value is the "hard center" that's immediately usable regardless
    of whether the agent does further hops.

    Args:
        ref_id: The 8-char hex reference ID of the task to backtrace.
        max_hops: Maximum iterative search rounds (default 3).

    Returns:
        Dictionary with source_content, anchors, archival_hits,
        three_node_candidates, hop_candidates, and node_coverage.
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

        # ── Step 1: Fetch the task's archival passage ──
        search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={ref_id}&limit=3"
        req = urllib.request.Request(search_url)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                passages = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                req2 = urllib.request.Request(e.headers.get("Location", ""))
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    passages = json.loads(resp2.read().decode("utf-8"))
            else:
                raise
        if not isinstance(passages, list):
            passages = []

        task_passage = None
        task_text = ""
        for p in passages:
            if isinstance(p, dict) and f"REF_ID: {ref_id}" in p.get("text", ""):
                task_passage = p
                task_text = p.get("text", "")
                break

        if not task_passage:
            return {"status": "error", "error_message": f"No archival passage found for ref_id {ref_id}"}

        # Parse fields from passage
        fields = {}
        for pattern, key in [
            (r"^TASK: (.+)$", "task_desc"),
            (r"- Type: (.+)$", "source_type"),
            (r"- From: (.+)$", "from_person"),
            (r"- Location: (.+)$", "location"),
            (r"- Location ID: (.+)$", "location_id"),
            (r"- Reference ID: (.+)$", "reference_id"),
        ]:
            m = re.search(pattern, task_text, re.MULTILINE)
            if m:
                fields[key] = m.group(1).strip()

        task_desc = fields.get("task_desc", "")
        source_type = fields.get("source_type", "")
        from_person = fields.get("from_person", "")
        location = fields.get("location", "")
        location_id = fields.get("location_id", "")
        reference_id = fields.get("reference_id", "")

        # Extract source text and fetch hint
        st_match = re.search(r"SOURCE TEXT\n(.+?)(?=\nFETCH HINT:|\nENRICH|\nPACKET INFO|\Z)", task_text, re.DOTALL)
        source_text_field = st_match.group(1).strip() if st_match else ""

        fetch_hint_match = re.search(r"FETCH HINT: (.+)$", task_text, re.MULTILINE)
        fetch_hint = fetch_hint_match.group(1).strip() if fetch_hint_match else ""

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
            except (FileNotFoundError, Exception):
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

        # ── Step 4: Archival search ──
        archival_hits = []
        seen_ids = {task_passage.get("id", "")}
        searched_terms = set()
        new_anchors = []

        for iteration in range(min(hops, 3)):
            terms_this_round = search_terms if iteration == 0 else new_anchors
            new_anchors = []

            for term in terms_this_round:
                if term.lower() in searched_terms:
                    continue
                searched_terms.add(term.lower())

                try:
                    s_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={urllib.request.quote(term)}&limit=5"
                    s_req = urllib.request.Request(s_url)
                    with urllib.request.urlopen(s_req, timeout=15) as s_resp:
                        results = json.loads(s_resp.read().decode("utf-8"))
                    for p in (results if isinstance(results, list) else []):
                        if not isinstance(p, dict):
                            continue
                        pid = p.get("id", "")
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        p_text = p.get("text", "")
                        if f"REF_ID: {ref_id}" in p_text:
                            continue
                        tags = p.get("tags", []) or []
                        archival_hits.append({
                            "id": pid,
                            "text_preview": p_text[:300],
                            "tags": tags,
                            "matched_anchor": term,
                        })
                        # Extract new anchors for next iteration
                        for new_pn in re.findall(r"[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+", p_text[:300]):
                            if (new_pn.lower() not in searched_terms
                                    and new_pn.split()[0].lower() not in STOP):
                                new_anchors.append(new_pn)
                except Exception:
                    continue

            if not new_anchors:
                break

        # ── Step 5: Classify hits into three-node candidates ──
        relevance_terms = [t.lower() for t in search_terms[:10]]

        artifact_candidates = []
        intent_candidates = []
        related_tasks = []
        other_hits = []

        for hit in archival_hits:
            text = hit.get("text_preview", "")
            tags = hit.get("tags", []) or []
            text_lower = text.lower()
            is_relevant = any(rt in text_lower for rt in relevance_terms)

            # Related tasks (other extracted tasks sharing search terms)
            if "TASK:" in text and "REF_ID:" in text and is_relevant:
                task_match = re.search(r"TASK: (.+)", text)
                ref_match = re.search(r"REF_ID: (\S+)", text)
                status_match = re.search(r"\[(COMPLETED|REJECTED)\]", text)
                if task_match and ref_match:
                    related_tasks.append({
                        "ref_id": ref_match.group(1),
                        "task": task_match.group(1).strip()[:100],
                        "status": status_match.group(1).lower() if status_match else "active",
                        "matched_anchor": hit.get("matched_anchor", ""),
                    })
                continue

            # Artifact candidates: Drive/Docs sources, relevant to task
            if is_relevant and (
                any(t.startswith("source:google") for t in tags)
                or "drive.google.com" in text
                or "docs.google.com" in text
            ):
                artifact_candidates.append({
                    "preview": text[:200],
                    "tags": tags,
                    "matched_anchor": hit.get("matched_anchor", ""),
                })
                continue

            # Intent candidates: meetings, decisions, strategy
            if (any(t.startswith("source:meeting") for t in tags)
                    or "Decision" in text
                    or "agreed" in text_lower
                    or "strategy" in text_lower):
                intent_candidates.append({
                    "preview": text[:200],
                    "tags": tags,
                    "matched_anchor": hit.get("matched_anchor", ""),
                })
                continue

            # Everything else
            if is_relevant:
                other_hits.append({
                    "preview": text[:200],
                    "tags": tags,
                    "matched_anchor": hit.get("matched_anchor", ""),
                })

        # ── Step 6: Build hop candidates ──
        hop_candidates = []

        # URLs from source content → potential artifact hops
        for u in anchors_urls[:5]:
            if "drive.google.com" in u or "docs.google.com" in u:
                hop_candidates.append({
                    "ref": u,
                    "type": "drive_doc",
                    "node_likelihood": "artifact_provenance",
                    "reason": "Drive/Docs link found in source content",
                })
            elif "slack.com/archives" in u:
                hop_candidates.append({
                    "ref": u,
                    "type": "slack_thread",
                    "node_likelihood": "direct_action",
                    "reason": "Slack permalink found in source content",
                })

        # Intent genesis candidates from meeting hits
        for ic in intent_candidates[:3]:
            meeting_match = re.search(r"- Context: (.+?)$", ic["preview"], re.MULTILINE)
            hop_candidates.append({
                "ref": meeting_match.group(1) if meeting_match else ic["preview"][:60],
                "type": "meeting",
                "node_likelihood": "intent_genesis",
                "reason": f"Meeting passage matched anchor '{ic['matched_anchor']}'",
            })

        # ── Step 7: Assess node coverage ──
        node_coverage = {
            "direct_action": True,  # Always filled from passage metadata
            "artifact_provenance": len(artifact_candidates) > 0,
            "intent_genesis": len(intent_candidates) > 0,
        }

        # ── Build mismatch warnings ──
        mismatch_warnings = []
        completed_related = [rt for rt in related_tasks if rt["status"] == "completed"]
        rejected_related = [rt for rt in related_tasks if rt["status"] == "rejected"]
        if completed_related:
            mismatch_warnings.append({
                "type": "overlap",
                "message": f"{len(completed_related)} related task(s) already completed",
                "examples": [f"[{rt['ref_id']}] {rt['task'][:60]}" for rt in completed_related[:3]],
            })
        if rejected_related:
            mismatch_warnings.append({
                "type": "prior_rejection",
                "message": f"{len(rejected_related)} similar task(s) previously rejected",
                "examples": [f"[{rt['ref_id']}] {rt['task'][:60]}" for rt in rejected_related[:3]],
            })

        return {
            "status": "ok",
            "ref_id": ref_id,
            "task": task_desc,
            "passage_id": task_passage.get("id", ""),

            # Hard center — source material
            "source_content": full_content[:3000],
            "source_type": source_type,
            "fetch_hint": fetch_hint,

            # Structured anchors
            "anchors": {
                "urls": anchors_urls[:10],
                "doc_ids": anchors_doc_ids,
                "proper_nouns": anchors_proper_nouns[:15],
                "distinctive_phrases": anchors_distinctive[:10],
                "acronyms": anchors_acronyms[:10],
                "participants": participants,
            },

            # Direct-action node (always filled from passage metadata)
            "direct_action": {
                "source": f"{source_type} from {from_person}",
                "location": location,
                "location_id": location_id,
                "reference_id": reference_id,
            },

            # Three-node candidates (for agent to evaluate, not pre-selected)
            "artifact_candidates": artifact_candidates[:5],
            "intent_candidates": intent_candidates[:5],

            # Related items
            "related_tasks": related_tasks[:10],
            "other_hits": other_hits[:10],

            # Hop candidates (for agent to chase or skip)
            "hop_candidates": hop_candidates[:10],

            # Coverage + warnings
            "node_coverage": node_coverage,
            "mismatch_warnings": mismatch_warnings,

            # Search metadata
            "search_terms_used": list(searched_terms),
            "total_archival_hits": len(archival_hits),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
