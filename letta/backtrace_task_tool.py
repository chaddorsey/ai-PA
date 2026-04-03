"""
Backtrace Task Tool for Letta

Phase B: Cross-source backtracing to build PACKET INFO for a task.
Searches archival, Slack, email, and meetings for related context
beyond the immediate source. Produces the three-node model + context brief.

Can be called by any agent (tasks agent, MC, sleeptime).

Tool: backtrace_task
"""

from typing import Dict, Any, Optional


def backtrace_task(ref_id: str, max_hops: Optional[int] = None) -> Dict[str, Any]:
    """
    Perform cross-source backtracing for a task to build PACKET INFO.

    Searches archival memory for related passages, identifies the three-node
    model (direct-action, artifact provenance, intent genesis), and produces
    a context brief. Writes results to the archival passage's PACKET INFO section.

    This is Phase B enrichment — runs after Phase A has produced a good task
    statement. The backtrace crosses source boundaries to understand WHY the
    task exists and WHAT is needed to execute it.

    Args:
        ref_id: The 8-char hex reference ID of the task to backtrace.
        max_hops: Maximum search hops (default 3). Higher = more thorough but slower.

    Returns:
        Dictionary with status, three-node model, context brief, and related items found.
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

        # Parse fields from passage (inline, no nested functions)
        task_desc = ""
        source_type = ""
        from_person = ""
        location = ""
        location_id = ""
        reference_id = ""
        source_text_field = ""
        for pattern, field_name in [
            (r"^TASK: (.+)$", "task_desc"),
            (r"- Type: (.+)$", "source_type"),
            (r"- From: (.+)$", "from_person"),
            (r"- Location: (.+)$", "location"),
            (r"- Location ID: (.+)$", "location_id"),
            (r"- Reference ID: (.+)$", "reference_id"),
        ]:
            m = re.search(pattern, task_text, re.MULTILINE)
            if m:
                if field_name == "task_desc": task_desc = m.group(1).strip()
                elif field_name == "source_type": source_type = m.group(1).strip()
                elif field_name == "from_person": from_person = m.group(1).strip()
                elif field_name == "location": location = m.group(1).strip()
                elif field_name == "location_id": location_id = m.group(1).strip()
                elif field_name == "reference_id": reference_id = m.group(1).strip()
        st_match = re.search(r"SOURCE TEXT\n(.+?)(?=\n\nFETCH|\n\nENRICH|\Z)", task_text, re.DOTALL)
        if st_match:
            source_text_field = st_match.group(1).strip()

        # ── Step 2: Build search queries from task context ──
        # Extract key terms for searching
        search_terms = []

        # Person name (without email/ID)
        if from_person:
            name_only = re.sub(r"\s*[\(<].*", "", from_person).strip()
            if name_only and name_only != "Chad Dorsey":
                search_terms.append(name_only)

        # Key nouns from task description (crude but effective)
        if task_desc:
            # Remove common verbs and articles
            stop_words = {"review", "check", "send", "draft", "complete", "update",
                          "the", "a", "an", "for", "to", "in", "on", "with", "and",
                          "of", "from", "by", "at", "is", "are", "was", "this", "that"}
            words = [w for w in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,}", task_desc)
                     if w.lower() not in stop_words and len(w) > 2]
            search_terms.extend(words[:3])

        # Location/channel
        if location and not location.startswith("#"):
            search_terms.append(location[:40])

        # ── Step 3: Search archival for related passages ──
        related_passages = []
        seen_ids = {task_passage.get("id", "")}

        for term in search_terms[:hops]:
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
                    # Skip if it's just the same task
                    if f"REF_ID: {ref_id}" in p_text:
                        continue
                    related_passages.append({
                        "id": pid,
                        "text_preview": p_text[:200],
                        "tags": p.get("tags", []),
                        "search_term": term,
                    })
            except Exception:
                continue

        # ── Step 4: Build three-node model ──
        direct_action = {
            "source": f"{source_type} from {from_person}",
            "location": location,
            "reference_id": reference_id,
        }

        # Classify related passages into three-node model
        artifact_provenance = None
        intent_genesis = []
        related_tasks = []
        related_slack = []

        for rp in related_passages:
            text = rp.get("text_preview", "")
            tags = rp.get("tags", []) or []

            # Artifact provenance: Drive docs, files, links
            if (any(t.startswith("source:google") for t in tags)
                    or "drive.google.com" in text
                    or "docs.google.com" in text):
                if not artifact_provenance:
                    artifact_provenance = {"text": text[:150], "tags": tags}

            # Intent genesis: meetings, decisions, strategy discussions
            if (any(t.startswith("source:meeting") for t in tags)
                    or "Decision" in text
                    or "agreed" in text.lower()
                    or "strategy" in text.lower()):
                intent_genesis.append({"text": text[:150], "tags": tags})

            # Related tasks: other extracted tasks
            if "TASK:" in text and "REF_ID:" in text:
                task_match = re.search(r"TASK: (.+)", text)
                ref_match = re.search(r"REF_ID: (\S+)", text)
                if task_match and ref_match:
                    related_tasks.append({
                        "ref_id": ref_match.group(1),
                        "task": task_match.group(1)[:80],
                    })

            # Slack context: related channel discussions
            if any(t.startswith("source:slack") for t in tags):
                related_slack.append({"text": text[:150], "tags": tags})

        # ── Step 5: Build context brief ──
        context_brief = []
        if task_desc:
            context_brief.append(f"Task: {task_desc}")
        if from_person:
            context_brief.append(f"Requested by: {from_person}")
        if location:
            context_brief.append(f"Source: {location}")
        if artifact_provenance:
            context_brief.append(f"Primary artifact: {artifact_provenance['text'][:80]}")
        if intent_genesis:
            context_brief.append(f"Prior context: {len(intent_genesis)} related meeting/decision passage(s)")
        context_brief.append(f"Related passages found: {len(related_passages)}")

        # ── Step 6: Write PACKET INFO to archival passage ──
        packet_info_lines = [
            "\nPACKET INFO",
            f"- Direct-action node: {source_type} — {from_person} in {location}",
        ]
        if artifact_provenance:
            packet_info_lines.append(f"- Artifact provenance: {artifact_provenance['text'][:100]}")
        else:
            packet_info_lines.append("- Artifact provenance: (not identified)")

        if intent_genesis:
            for ig in intent_genesis[:3]:
                packet_info_lines.append(f"- Intent genesis: {ig['text'][:100]}")
        else:
            packet_info_lines.append("- Intent genesis: (not identified)")

        packet_info_lines.append("")
        packet_info_lines.append("Context brief:")
        for cb in context_brief:
            packet_info_lines.append(f"  - {cb}")

        if related_tasks:
            packet_info_lines.append("")
            packet_info_lines.append("Related tasks:")
            for rt in related_tasks[:5]:
                packet_info_lines.append(f"  - [{rt['ref_id']}] {rt['task']}")

        if related_slack:
            packet_info_lines.append("")
            packet_info_lines.append("Related Slack context:")
            for rs in related_slack[:3]:
                packet_info_lines.append(f"  - {rs['text'][:80]}")

        # Knowns / Assumptions / Unknowns
        knowns = []
        assumptions = []
        unknowns = []

        if from_person:
            knowns.append(f"Requested by {from_person}")
        if artifact_provenance:
            knowns.append("Primary artifact identified")
        else:
            unknowns.append("Primary artifact/deliverable location not identified")
        if intent_genesis:
            knowns.append(f"{len(intent_genesis)} prior decision/meeting passage(s) found")
        else:
            unknowns.append("No prior meetings or decisions found — intent/strategy context missing")
        if related_tasks:
            knowns.append(f"{len(related_tasks)} related task(s) in system")
        if not related_passages:
            unknowns.append("No related archival passages found — task may be novel or poorly indexed")

        packet_info_lines.append("")
        packet_info_lines.append("Knowns / Assumptions / Unknowns:")
        for k in knowns:
            packet_info_lines.append(f"  Known: {k}")
        for a in assumptions:
            packet_info_lines.append(f"  Assumption: {a}")
        for u in unknowns:
            packet_info_lines.append(f"  Unknown: {u}")

        # ── Formulation mismatch check ──
        # If backtrace reveals context that contradicts the task formulation,
        # flag prominently. Check if related tasks suggest a different action.
        mismatch_flag = None
        if related_tasks:
            completed_related = [rt for rt in related_tasks
                                 if "[COMPLETED]" in rt.get("task", "")]
            if completed_related:
                mismatch_flag = (
                    f"⚠ POSSIBLE OVERLAP: {len(completed_related)} related task(s) already "
                    f"completed. The current task may be a duplicate or the scope may have "
                    f"shifted. Review: {completed_related[0]['task'][:60]}"
                )
            rejected_related = [rt for rt in related_tasks
                                if "[REJECTED]" in rt.get("task", "")]
            if rejected_related and not mismatch_flag:
                mismatch_flag = (
                    f"⚠ NOTE: A similar task was previously rejected: "
                    f"{rejected_related[0]['task'][:60]}. "
                    f"Verify this is a distinct action."
                )

        if mismatch_flag:
            packet_info_lines.insert(1, "")
            packet_info_lines.insert(2, f">>> {mismatch_flag} <<<")
            packet_info_lines.insert(3, "")

        packet_info_text = "\n".join(packet_info_lines)

        # Update the archival passage
        new_text = task_text
        # Remove existing PACKET INFO if present
        new_text = re.sub(r"\nPACKET INFO\n.*?(?=\n\n[A-Z]|\Z)", "", new_text, flags=re.DOTALL)
        # Update enrichment status
        new_text = re.sub(r"- Status: (?:none|phase-a-complete|phase0-complete)",
                          "- Status: packet-info", new_text)
        # Append packet info before SOURCE TEXT
        source_text_idx = new_text.find("\nSOURCE TEXT\n")
        if source_text_idx > 0:
            new_text = new_text[:source_text_idx] + packet_info_text + new_text[source_text_idx:]
        else:
            new_text += packet_info_text

        # Update tags
        tags = task_passage.get("tags", []) or []
        tags = [t for t in tags if not t.startswith("enrichment:")]
        tags.append("enrichment:packet-info")

        # Delete old passage, insert new
        passage_id = task_passage.get("id", "")
        try:
            del_req = urllib.request.Request(
                f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}",
                method="DELETE",
            )
            urllib.request.urlopen(del_req, timeout=10)

            ins_data = json.dumps({"text": new_text, "tags": tags}).encode("utf-8")
            ins_req = urllib.request.Request(
                f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
                data=ins_data, headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(ins_req, timeout=15)
        except Exception:
            pass  # Archival update is best-effort

        return {
            "status": "ok",
            "ref_id": ref_id,
            "task": task_desc,
            "three_node_model": {
                "direct_action": direct_action,
                "artifact_provenance": artifact_provenance,
                "intent_genesis": intent_genesis[:3],
            },
            "context_brief": context_brief,
            "knowns_unknowns": {"knowns": knowns, "assumptions": assumptions, "unknowns": unknowns},
            "mismatch_flag": mismatch_flag,
            "related_tasks": related_tasks[:5],
            "related_slack": len(related_slack),
            "related_passages_found": len(related_passages),
            "search_terms_used": search_terms[:hops],
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
