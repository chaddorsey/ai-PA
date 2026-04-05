"""
Write Packet Info Tool for Letta

Writes the PACKET INFO section to a task's archival passage after the agent
has synthesized backtrace materials. Separates "search" (backtrace_task)
from "write" (this tool).

Called by MC, tasks agent, or sleeptime after reviewing backtrace_task output
and performing any additional hops / synthesis.

Tool: write_packet_info
"""

from typing import Dict, Any, Optional


def write_packet_info(
    ref_id: str,
    direct_action: str,
    artifact_provenance: Optional[str] = None,
    intent_genesis: Optional[str] = None,
    context_brief: Optional[str] = None,
    resources: Optional[str] = None,
    related_tasks: Optional[str] = None,
    knowns: Optional[str] = None,
    unknowns: Optional[str] = None,
    mismatch_warnings: Optional[str] = None,
    additional_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write PACKET INFO to a task's archival passage after backtrace synthesis.

    The agent calls this after reviewing backtrace_task output, performing
    any additional hops, and synthesizing the results. This is the "write"
    step — backtrace_task is the "search" step.

    All string parameters accept free-form text. The agent composes the
    content based on its synthesis of backtrace materials + its own memory.

    Args:
        ref_id: The 8-char hex reference ID of the task.
        direct_action: Direct-action node summary (who asked, where, what's done).
        artifact_provenance: Primary artifact location and provenance chain. Null if not identified.
        intent_genesis: Why/strategy/constraints — prior decisions, meetings, context. Null if not found.
        context_brief: 3-5 bullet synthesis of what the agent knows about this task's context.
        resources: Key resources for execution. One per line, format: "[priority] label — url_or_path (role)". Priority: primary, secondary, background. Role: read, reference, download, open. Example: "[primary] PhET Substack post — https://... (read)"
        related_tasks: One per line. ref_ids and short descriptions of related tasks found.
        knowns: What is established and verified. One per line.
        unknowns: What is missing or unresolved. One per line.
        mismatch_warnings: Any overlap/conflict warnings to flag prominently. Null if none.
        additional_notes: Any other synthesis the agent wants to preserve.

    Returns:
        Dictionary with status and the updated passage text.
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
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"

        if not ref_id:
            return {"status": "error", "error_message": "ref_id is required"}

        # ── Fetch the task's archival passage ──
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

        # ── Retrieve stored backtrace materials (from refine_task_description) ──
        stored_materials = None
        try:
            mat_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search=backtrace-materials:{ref_id}&limit=3"
            mat_req = urllib.request.Request(mat_url)
            with urllib.request.urlopen(mat_req, timeout=10) as mat_resp:
                mat_passages = json.loads(mat_resp.read().decode("utf-8"))
            for mp in (mat_passages if isinstance(mat_passages, list) else []):
                if isinstance(mp, dict) and f"BACKTRACE_MATERIALS ref_id:{ref_id}" in mp.get("text", ""):
                    mat_text = mp.get("text", "")
                    json_start = mat_text.find("\n")
                    if json_start >= 0:
                        stored_materials = json.loads(mat_text[json_start + 1:])
                    # Clean up the transient passage
                    mat_pid = mp.get("id", "")
                    if mat_pid:
                        try:
                            urllib.request.urlopen(urllib.request.Request(
                                f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{mat_pid}",
                                method="DELETE",
                            ), timeout=10)
                        except Exception:
                            pass
                    break
        except Exception:
            pass  # Retrieval is best-effort

        # Auto-populate fields from stored materials when agent didn't provide them
        if stored_materials:
            if not resources:
                urls = stored_materials.get("anchors", {}).get("urls", [])
                if urls:
                    resource_lines = []
                    for u in urls[:5]:
                        resource_lines.append(f"[primary] {u}")
                    resources = "\n".join(resource_lines)
            if not related_tasks:
                rt_list = stored_materials.get("related_tasks", [])
                if rt_list:
                    rt_lines = [f"[{rt['ref_id']}] {rt['task'][:60]}" for rt in rt_list[:5]]
                    related_tasks = "\n".join(rt_lines)
            if not mismatch_warnings:
                mw_list = stored_materials.get("mismatch_warnings", [])
                if mw_list:
                    mismatch_warnings = "; ".join(w["message"] for w in mw_list)

        # ── Build PACKET INFO section ──
        lines = ["\nPACKET INFO"]

        if mismatch_warnings:
            lines.append("")
            lines.append(f">>> ⚠ {mismatch_warnings} <<<")
            lines.append("")

        lines.append(f"- Direct-action: {direct_action}")
        lines.append(f"- Artifact provenance: {artifact_provenance or '(not identified)'}")
        lines.append(f"- Intent genesis: {intent_genesis or '(not identified)'}")

        if context_brief:
            lines.append("")
            lines.append("Context brief:")
            for item in context_brief.split("\n"):
                item = item.strip().lstrip("- ")
                if item:
                    lines.append(f"  - {item}")

        if resources:
            lines.append("")
            lines.append("Resources:")
            for item in resources.split("\n"):
                item = item.strip().lstrip("- ")
                if item:
                    lines.append(f"  - {item}")

        if related_tasks:
            lines.append("")
            lines.append("Related tasks:")
            for item in related_tasks.split("\n"):
                item = item.strip().lstrip("- ")
                if item:
                    lines.append(f"  - {item}")

        if knowns or unknowns:
            lines.append("")
            lines.append("Knowns / Unknowns:")
            if knowns:
                for k in knowns.split("\n"):
                    k = k.strip().lstrip("- ")
                    if k:
                        lines.append(f"  Known: {k}")
            if unknowns:
                for u in unknowns.split("\n"):
                    u = u.strip().lstrip("- ")
                    if u:
                        lines.append(f"  Unknown: {u}")

        if additional_notes:
            lines.append("")
            lines.append("Agent notes:")
            for n in additional_notes.split("\n"):
                n = n.strip()
                if n:
                    lines.append(f"  {n}")

        packet_info_text = "\n".join(lines)

        # ── Update archival passage ──
        new_text = task_text

        # Remove existing PACKET INFO and stale sections
        new_text = re.sub(
            r"\n*Context brief:\n.*?(?=\nSOURCE TEXT\n|\nFETCH HINT:|\nPACKET INFO|\Z)",
            "", new_text, flags=re.DOTALL,
        )
        new_text = re.sub(
            r"\n*Knowns / (?:Assumptions / )?Unknowns:\n.*?(?=\nSOURCE TEXT\n|\nFETCH HINT:|\nPACKET INFO|\Z)",
            "", new_text, flags=re.DOTALL,
        )
        new_text = re.sub(
            r"\nPACKET INFO.*?(?=\nSOURCE TEXT\n|\nFETCH HINT:|\Z)",
            "", new_text, flags=re.DOTALL,
        )

        # Update enrichment status
        new_text = re.sub(
            r"- Status: (?:none|phase-a-complete|phase0-complete|packet-info)",
            "- Status: packet-info", new_text,
        )

        # Insert PACKET INFO before SOURCE TEXT
        source_text_idx = new_text.find("\nSOURCE TEXT\n")
        if source_text_idx > 0:
            new_text = new_text[:source_text_idx] + "\n" + packet_info_text + new_text[source_text_idx:]
        else:
            new_text += "\n" + packet_info_text

        # Update tags
        tags = task_passage.get("tags", []) or []
        tags = [t for t in tags if not t.startswith("enrichment:")]
        tags.append("enrichment:packet-info")

        # Delete old passage, insert new
        passage_id = task_passage.get("id", "")
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

        # Trigger OmniFocus note re-assembly if task is confirmed.
        # Baked in so worker agents don't need an HTTP tool.
        reassemble_status = "skipped"
        reassemble_detail = ""
        if "- Status: confirmed" in new_text and "- Task ID:" in new_text:
            pa_web_url = os.environ.get("PA_WEB_UI_URL", "http://pa-web-ui:5200")
            reassemble_url = f"{pa_web_url}/api/tasks/{ref_id}/reassemble-work-packet"
            try:
                r_req = urllib.request.Request(reassemble_url, method="POST")
                with urllib.request.urlopen(r_req, timeout=30) as r_resp:
                    reassemble_status = "ok"
                    reassemble_detail = f"HTTP {r_resp.status}"
            except urllib.error.HTTPError as he:
                reassemble_status = "failed"
                reassemble_detail = f"HTTP {he.code}"
            except Exception as re_err:
                reassemble_status = "failed"
                reassemble_detail = str(re_err)[:100]

        return {
            "status": "ok",
            "ref_id": ref_id,
            "enrichment_status": "packet-info",
            "packet_info_preview": packet_info_text[:500],
            "reassemble": reassemble_status,
            "reassemble_detail": reassemble_detail,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
