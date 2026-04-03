"""
Refine Task Description Tool for Letta

Updates a task's description in the extracted_tasks block by ref_id.
If the task doesn't exist in the block yet (deferred from Phase 0),
creates the entry. Also updates enrichment status in archival.

Used by Phase A enrichment after the agent formulates a better task name.

Tool: refine_task_description
"""

from typing import Dict, Any


def refine_task_description(ref_id: str, new_description: str) -> Dict[str, Any]:
    """
    Update or create the description of an extracted task in the extracted_tasks block.

    If the task line exists (by ref_id), updates the description only.
    If not found, creates a new line using archival passage metadata.
    Also updates enrichment status from in-progress to phase-a-complete.

    Args:
        ref_id: The 8-char hex reference ID of the task to refine.
        new_description: The new verb-led task description (max ~120 chars).

    Returns:
        Dictionary with status, old/new descriptions, and whether line was created.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.environ.get("LETTA_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"

        if not ref_id or not new_description:
            return {"status": "error", "error_message": "ref_id and new_description are required"}

        # ── Helper: HTTP request with redirect handling ──
        # (inlined since Letta tools can't use nested def)

        # ── Step 1: Fetch archival passage for metadata ──
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
        passage_text = ""
        for p in passages:
            if isinstance(p, dict) and f"REF_ID: {ref_id}" in p.get("text", ""):
                task_passage = p
                passage_text = p.get("text", "")
                break

        if not task_passage:
            return {"status": "error", "error_message": f"No archival passage found for ref_id {ref_id}"}

        # Extract metadata from passage for potential line creation
        origin = ""
        estimate = "15"
        timestamp_str = ""
        origin_match = re.search(r"^ORIGIN: (.+)$", passage_text, re.MULTILINE)
        if origin_match:
            origin = origin_match.group(1).strip()
        est_match = re.search(r"- (?:Agent )?Estimate: (\d+)", passage_text)
        if est_match:
            estimate = est_match.group(1)
        ts_match = re.search(r"- Extracted: (.+)$", passage_text, re.MULTILINE)
        if ts_match:
            raw_ts = ts_match.group(1).strip()
            # Parse to YYYY-MM-DD HH:MM format
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(raw_ts)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                timestamp_str = raw_ts[:16]
        if not timestamp_str:
            from datetime import datetime, timezone
            timestamp_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

        # ── Step 2: Get the extracted_tasks block ──
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/"
        areq = urllib.request.Request(agent_url)
        try:
            with urllib.request.urlopen(areq, timeout=10) as aresp:
                agent_data = json.loads(aresp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                redirect = e.headers.get("Location", "")
                areq2 = urllib.request.Request(redirect)
                with urllib.request.urlopen(areq2, timeout=10) as aresp2:
                    agent_data = json.loads(aresp2.read().decode("utf-8"))
            else:
                raise

        et_block = None
        agent_name = agent_data.get("name", "tasks-agent")
        for blk in agent_data.get("memory", {}).get("blocks", []):
            if blk.get("label") == "extracted_tasks":
                et_block = blk
                break

        if not et_block:
            return {"status": "error", "error_message": "extracted_tasks block not found"}

        block_id = et_block["id"]
        value = et_block["value"]

        # ── Step 3: Find-or-create task line in block ──
        lines = value.split("\n")
        found = False
        old_desc = ""
        new_lines = []
        created = False

        for line in lines:
            if f"ref_id: {ref_id}" in line and line.strip().startswith("[extracted_time:"):
                # Found existing line — update description only
                bracket_end = line.find("] ")
                if bracket_end > 0:
                    old_desc = line[bracket_end + 2:]
                    new_line = line[:bracket_end + 2] + new_description.strip()
                    new_lines.append(new_line)
                    found = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if not found:
            # Create new task line using archival passage metadata
            origin_part = f"; origin: {origin}" if origin else ""
            task_line = f"[extracted_time: {timestamp_str}; ref_id: {ref_id}{origin_part}; est: {estimate}] {new_description.strip()}"

            # Find the tasks-agent section and insert
            section_header = f"=== {agent_name} ({AGENT_ID}) ==="
            section_pattern = re.compile(
                rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9-]+\)\s+===)|$)',
                re.DOTALL,
            )
            current_val = "\n".join(new_lines)
            section_match = section_pattern.search(current_val)

            if section_match:
                insert_pos = section_match.end()
                before = current_val[:insert_pos]
                after = current_val[insert_pos:]
                if before and not before.endswith("\n"):
                    before += "\n"
                current_val = before + task_line + "\n" + after
            else:
                current_val = current_val + f"\n{section_header}\n{task_line}\n"

            new_lines = current_val.split("\n")
            created = True
            old_desc = ""

        # Write back to block
        new_value = "\n".join(new_lines)
        update_data = json.dumps({"value": new_value}).encode("utf-8")
        update_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/blocks/{block_id}",
            data=update_data,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            urllib.request.urlopen(update_req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                redirect = e.headers.get("Location", "")
                req2 = urllib.request.Request(
                    redirect, data=update_data,
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                urllib.request.urlopen(req2, timeout=10)
            else:
                raise

        # ── Step 4: Update archival passage — TASK line + enrichment status ──
        try:
            pid = task_passage.get("id", "")
            if pid:
                # Update TASK line
                new_text = re.sub(
                    r"^TASK: .+$", f"TASK: {new_description.strip()}",
                    passage_text, count=1, flags=re.MULTILINE,
                )
                # Update ENRICHMENT status (from none or in-progress to phase-a-complete)
                new_text = re.sub(
                    r"- Status: (?:none|in-progress|phase0-complete)",
                    "- Status: phase-a-complete",
                    new_text,
                )

                tags = task_passage.get("tags", []) or []
                tags = [t for t in tags if not t.startswith("enrichment:")]
                tags.append("enrichment:phase-a-complete")

                # Delete old, insert new (passage mutation pattern)
                del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{pid}"
                urllib.request.urlopen(urllib.request.Request(del_url, method="DELETE"), timeout=10)

                ins_data = json.dumps({"text": new_text, "tags": tags}).encode("utf-8")
                ins_req = urllib.request.Request(
                    f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
                    data=ins_data, headers={"Content-Type": "application/json"}, method="POST",
                )
                urllib.request.urlopen(ins_req, timeout=15)
        except Exception:
            pass  # Archival update is best-effort

        # ── Step 5: Conditional backtrace for user-indicated tasks ──
        backtrace_result = None
        if origin == "user-indicated":
            try:
                # Extract fields from passage for backtrace
                source_type = ""
                from_person = ""
                location = ""
                location_id = ""
                reference_id_field = ""
                for pat, key in [
                    (r"- Type: (.+)$", "source_type"),
                    (r"- From: (.+)$", "from_person"),
                    (r"- Location: (.+)$", "location"),
                    (r"- Location ID: (.+)$", "location_id"),
                    (r"- Reference ID: (.+)$", "reference_id"),
                ]:
                    m = re.search(pat, passage_text, re.MULTILINE)
                    if m:
                        val = m.group(1).strip()
                        if key == "source_type": source_type = val
                        elif key == "from_person": from_person = val
                        elif key == "location": location = val
                        elif key == "location_id": location_id = val
                        elif key == "reference_id": reference_id_field = val

                st_match = re.search(r"SOURCE TEXT\n(.+?)(?=\nFETCH HINT:|\nENRICH|\nPACKET INFO|\Z)", passage_text, re.DOTALL)
                source_text_field = st_match.group(1).strip() if st_match else ""
                fh_match = re.search(r"FETCH HINT: (.+)$", passage_text, re.MULTILINE)
                fetch_hint = fh_match.group(1).strip() if fh_match else ""

                # Fetch full content via fetch_hint
                full_content = ""
                if fetch_hint and fetch_hint.startswith("gmail:"):
                    try:
                        import subprocess as _sp
                        import base64 as _b64
                        msg_id = fetch_hint.split(":", 1)[1]
                        gws_result = _sp.run(
                            ["gws", "gmail", "users", "messages", "get",
                             "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"}),
                             "--format", "json"],
                            capture_output=True, text=True, timeout=15,
                        )
                        if gws_result.returncode == 0:
                            raw = "\n".join(l for l in gws_result.stdout.split("\n") if not l.startswith("Using keyring"))
                            msg = json.loads(raw)
                            payload = msg.get("payload", {})
                            parts = [payload]
                            while parts:
                                part = parts.pop(0)
                                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                                    full_content = _b64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
                                    break
                                parts.extend(part.get("parts", []))
                    except Exception:
                        pass
                if not full_content:
                    full_content = source_text_field

                # Extract search terms (compact version of backtrace_task logic)
                all_text = f"{new_description} {full_content}".replace("\r\n", "\n")
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
                search_terms = []
                seen_terms = set()

                # Proper nouns from content
                for pn in re.findall(r"[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+", all_text):
                    if pn.split()[0].lower() not in STOP and pn.lower() not in seen_terms:
                        seen_terms.add(pn.lower())
                        search_terms.append(pn)
                    if len(search_terms) > 6:
                        break

                # CamelCase + single proper nouns
                for cc in re.findall(r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b", all_text):
                    if cc.lower() not in STOP and cc.lower() not in seen_terms:
                        seen_terms.add(cc.lower())
                        search_terms.append(cc)

                # Task description distinctive words
                for w in new_description.split():
                    w_clean = w.lower().rstrip(".,;:!?'s")
                    if len(w_clean) > 5 and w_clean not in STOP and w_clean not in seen_terms:
                        seen_terms.add(w_clean)
                        search_terms.append(w_clean)

                # Person name
                if from_person:
                    name_only = re.sub(r"\s*[\(<].*", "", from_person).strip()
                    if name_only and name_only.lower() not in STOP and name_only.lower() not in seen_terms:
                        search_terms.append(name_only)

                search_terms = search_terms[:12]

                # Search archival
                archival_hits = []
                seen_ids = {task_passage.get("id", "")}
                for term in search_terms:
                    try:
                        s_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={urllib.request.quote(term)}&limit=5"
                        s_req = urllib.request.Request(s_url)
                        with urllib.request.urlopen(s_req, timeout=15) as s_resp:
                            results = json.loads(s_resp.read().decode("utf-8"))
                        for p2 in (results if isinstance(results, list) else []):
                            if not isinstance(p2, dict):
                                continue
                            pid2 = p2.get("id", "")
                            if pid2 in seen_ids:
                                continue
                            seen_ids.add(pid2)
                            p2_text = p2.get("text", "")
                            if f"REF_ID: {ref_id}" in p2_text:
                                continue
                            archival_hits.append({
                                "id": pid2,
                                "text_preview": p2_text[:300],
                                "tags": p2.get("tags", []) or [],
                                "matched_anchor": term,
                            })
                    except Exception:
                        continue

                # Classify hits
                relevance_terms = [t.lower() for t in search_terms[:8]]
                artifact_candidates = []
                intent_candidates = []
                related_tasks = []

                for hit in archival_hits:
                    text = hit.get("text_preview", "")
                    tags = hit.get("tags", []) or []
                    text_lower = text.lower()
                    is_relevant = any(rt in text_lower for rt in relevance_terms)

                    if "TASK:" in text and "REF_ID:" in text and is_relevant:
                        task_m = re.search(r"TASK: (.+)", text)
                        ref_m = re.search(r"REF_ID: (\S+)", text)
                        status_m = re.search(r"\[(COMPLETED|REJECTED)\]", text)
                        if task_m and ref_m:
                            related_tasks.append({
                                "ref_id": ref_m.group(1),
                                "task": task_m.group(1).strip()[:100],
                                "status": status_m.group(1).lower() if status_m else "active",
                                "matched_anchor": hit.get("matched_anchor", ""),
                            })
                        continue

                    if is_relevant and any(t.startswith("source:google") for t in tags):
                        artifact_candidates.append({
                            "preview": text[:200],
                            "tags": tags,
                            "matched_anchor": hit.get("matched_anchor", ""),
                        })
                        continue

                    if (any(t.startswith("source:meeting") for t in tags)
                            or "Decision" in text or "agreed" in text_lower):
                        intent_candidates.append({
                            "preview": text[:200],
                            "tags": tags,
                            "matched_anchor": hit.get("matched_anchor", ""),
                        })

                # Build mismatch warnings
                mismatch_warnings = []
                completed = [rt for rt in related_tasks if rt["status"] == "completed"]
                rejected = [rt for rt in related_tasks if rt["status"] == "rejected"]
                if completed:
                    mismatch_warnings.append({
                        "type": "overlap",
                        "message": f"{len(completed)} related task(s) already completed",
                        "examples": [f"[{rt['ref_id']}] {rt['task'][:60]}" for rt in completed[:3]],
                    })
                if rejected:
                    mismatch_warnings.append({
                        "type": "prior_rejection",
                        "message": f"{len(rejected)} similar task(s) previously rejected",
                        "examples": [f"[{rt['ref_id']}] {rt['task'][:60]}" for rt in rejected[:3]],
                    })

                # Build URLs list from content
                urls_found = re.findall(r"https?://[^\s<>\"]+", all_text)
                urls_filtered = []
                for u in urls_found[:10]:
                    domain_m = re.search(r"https?://([^/\s]+)", u)
                    if domain_m and domain_m.group(1) not in ("mail.google.com", "slack.com", "www.google.com"):
                        urls_filtered.append(u)

                backtrace_result = {
                    "source_content": full_content[:3000],
                    "source_type": source_type,
                    "direct_action": {
                        "source": f"{source_type} from {from_person}",
                        "location": location,
                        "location_id": location_id,
                        "reference_id": reference_id_field,
                    },
                    "anchors": {
                        "urls": urls_filtered[:10],
                        "proper_nouns": [t for t in search_terms if t[0:1].isupper()][:10],
                    },
                    "artifact_candidates": artifact_candidates[:5],
                    "intent_candidates": intent_candidates[:5],
                    "related_tasks": related_tasks[:10],
                    "mismatch_warnings": mismatch_warnings,
                    "node_coverage": {
                        "direct_action": True,
                        "artifact_provenance": len(artifact_candidates) > 0,
                        "intent_genesis": len(intent_candidates) > 0,
                    },
                    "search_terms_used": search_terms,
                    "total_archival_hits": len(archival_hits),
                }
            except Exception:
                pass  # Backtrace is best-effort; refinement still succeeds

        result = {
            "status": "ok",
            "ref_id": ref_id,
            "old_description": old_desc.strip(),
            "new_description": new_description.strip(),
            "created": created,
        }
        if backtrace_result:
            result["backtrace"] = backtrace_result
        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
