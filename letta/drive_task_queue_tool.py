"""
Drive Task Queue Tool for Letta

Processes queued Google Docs/Sheets/Slides comment tasks by enriching
them with Drive API data and extracting tasks.

Tool: process_drive_task_queue
"""

from typing import Dict, Any, Optional


def process_drive_task_queue(max_entries: int = 10) -> Dict[str, Any]:
    """
    Process queued drive comment tasks and extract them.

    Reads the queued_tasks_from_drive memory block. For each raw entry:
    1. Calls Drive API to get file metadata (type, title)
    2. Calls Drive API to get comment metadata (author, text, quoted passage)
    3. Retrieves surrounding context based on document type
    4. Replaces the raw entry in the block with an enriched version

    After this tool returns, review the [enriched] entries in the
    queued_tasks_from_drive block and extract tasks using
    add_extracted_tasks. Then remove the processed entries from the block.

    For entries with marker_type "explicit", the task_hint IS the task
    description - use it directly. For "pointer" markers, expand the hint
    using the comment and document context. For entries without markers,
    compose a task from the comment text.

    Args:
        max_entries: Maximum entries to process per call (1-20, default 10).

    Returns:
        Dictionary with status, count processed, and per-entry details.
    """
    import os
    import re
    import json
    import subprocess
    import traceback
    import pytz
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        QUEUE_BLOCK_LABEL = "queued_tasks_from_drive"
        OWNER_EMAIL = "cdorsey@concord.org"
        GWS_TIMEOUT = 15

        if max_entries is None or max_entries < 1:
            max_entries = 10
        if max_entries > 20:
            max_entries = 20

        # ── Get queue block ──
        if not AGENT_ID:
            return {"status": "error", "error_message": "LETTA_AGENT_ID not set"}

        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method="GET")
        with urllib.request.urlopen(agent_req, timeout=10) as resp:
            agent_data = json.loads(resp.read().decode("utf-8"))

        blocks = agent_data.get("memory", {}).get("blocks", [])
        queue_block = None
        for block in blocks:
            if block.get("label") == QUEUE_BLOCK_LABEL:
                queue_block = block
                break

        if not queue_block:
            return {
                "status": "error",
                "error_message": f"Block '{QUEUE_BLOCK_LABEL}' not found on this agent.",
            }

        queue_block_id = queue_block["id"]
        block_value = queue_block.get("value", "")

        # ── Parse entries ──
        raw_entries = [e.strip() for e in block_value.split("---") if e.strip()]
        entries = [
            e for e in raw_entries
            if e and not e.startswith("#") and "comment_id:" in e
        ]

        if not entries:
            return {
                "status": "ok",
                "message": "No entries to process.",
                "processed": 0,
                "details": [],
            }

        entries = entries[:max_entries]
        processed = []
        errors = []

        for entry_text in entries:
            try:
                # Parse entry fields
                fields = {}
                for line in entry_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("[queued:"):
                        # Parse header line for comment_id and doc_id
                        m = re.search(r"comment_id:\s*(\S+)", line)
                        if m:
                            fields["comment_id"] = m.group(1)
                        m = re.search(r"doc_id:\s*(\S+)", line)
                        if m:
                            fields["doc_id"] = m.group(1)
                        continue
                    if line.startswith("[FROM:"):
                        continue  # Skip foreign trigger annotation line
                    if ":" in line:
                        key, _, val = line.partition(":")
                        fields[key.strip()] = val.strip()

                doc_id = fields.get("doc_id", "")
                comment_id = fields.get("comment_id", "")
                marker_type = fields.get("marker_type")
                task_hint = fields.get("task_hint")
                context = fields.get("context")
                notes = fields.get("notes")
                triggered_by = fields.get("triggered_by", "")

                if not doc_id:
                    errors.append({"entry": entry_text[:50], "error": "no doc_id"})
                    continue

                # ── Drive API: file metadata ──
                try:
                    _cmd = ["gws"] + "drive files get".split()
                    _cmd.extend(["--params", json.dumps({
                        "fileId": doc_id,
                        "fields": "id,name,mimeType,webViewLink",
                    })])
                    _cmd.extend(["--format", "json"])
                    _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                    if _r.returncode != 0:
                        raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
                    file_meta = json.loads(_r.stdout) if _r.stdout.strip() else {}
                except Exception as api_err:
                    errors.append({
                        "doc_id": doc_id,
                        "error": f"files.get failed: {str(api_err)}",
                    })
                    continue

                doc_title = file_meta.get("name", fields.get("doc_title", ""))
                mime_type = file_meta.get("mimeType", "")

                # Map mime type to doc_type
                mime_to_type = {
                    "application/vnd.google-apps.document": "document",
                    "application/vnd.google-apps.spreadsheet": "spreadsheet",
                    "application/vnd.google-apps.presentation": "presentation",
                }
                doc_type = mime_to_type.get(mime_type, "document")

                # ── Drive API: comment metadata ──
                comment_text = ""
                comment_author = ""
                comment_author_email = ""
                quoted_passage = ""
                comment_date = ""

                if comment_id:
                    try:
                        _cmd = ["gws"] + "drive comments get".split()
                        _cmd.extend(["--params", json.dumps({
                            "fileId": doc_id,
                            "commentId": comment_id,
                            "fields": "content,author,quotedFileContent,createdTime,resolved",
                        })])
                        _cmd.extend(["--format", "json"])
                        _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                        if _r.returncode != 0:
                            raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
                        comment_data = json.loads(_r.stdout) if _r.stdout.strip() else {}
                        comment_text = comment_data.get("content", "")
                        author = comment_data.get("author", {})
                        comment_author = author.get("displayName", "")
                        comment_author_email = author.get("emailAddress", "")
                        quoted_fc = comment_data.get("quotedFileContent", {})
                        quoted_passage = quoted_fc.get("value", "")
                        comment_date = comment_data.get("createdTime", "")
                    except Exception:
                        pass  # Enrichment is best-effort

                # ── Surrounding context (by doc type) ──
                surrounding_context = ""
                if quoted_passage and doc_type == "document":
                    try:
                        _cmd = ["gws"] + "docs documents get".split()
                        _cmd.extend(["--params", json.dumps({
                            "documentId": doc_id,
                        })])
                        _cmd.extend(["--format", "json"])
                        _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                        if _r.returncode != 0:
                            raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
                        doc_data = json.loads(_r.stdout) if _r.stdout.strip() else {}
                        body_content = doc_data.get("body", {}).get("content", [])
                        paragraphs = []
                        for element in body_content:
                            paragraph = element.get("paragraph", {})
                            if paragraph:
                                text_runs = paragraph.get("elements", [])
                                para_text = "".join(
                                    tr.get("textRun", {}).get("content", "")
                                    for tr in text_runs
                                )
                                if para_text.strip():
                                    paragraphs.append(para_text.strip())

                        # Find paragraph containing quoted passage
                        target_idx = None
                        for idx, p in enumerate(paragraphs):
                            if quoted_passage in p:
                                target_idx = idx
                                break
                        if target_idx is not None:
                            start = max(0, target_idx - 3)
                            end = min(len(paragraphs), target_idx + 4)
                            context_paras = paragraphs[start:end]
                            marked = []
                            for p in context_paras:
                                if quoted_passage in p:
                                    marked.append(f">> {p} <<")
                                else:
                                    marked.append(p)
                            surrounding_context = "\n".join(marked)
                    except Exception:
                        pass  # Context retrieval is best-effort

                elif quoted_passage and doc_type == "spreadsheet":
                    try:
                        _cmd = ["gws"] + "sheets spreadsheets get".split()
                        _cmd.extend(["--params", json.dumps({
                            "spreadsheetId": doc_id,
                            "fields": "sheets.data.rowData.values.formattedValue",
                        })])
                        _cmd.extend(["--format", "json"])
                        _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                        if _r.returncode != 0:
                            raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
                        sheet_data = json.loads(_r.stdout) if _r.stdout.strip() else {}
                        all_cells = []
                        for sheet in sheet_data.get("sheets", []):
                            for grid_data in sheet.get("data", []):
                                for row in grid_data.get("rowData", []):
                                    row_vals = []
                                    for cell in row.get("values", []):
                                        row_vals.append(
                                            cell.get("formattedValue", "")
                                        )
                                    if any(row_vals):
                                        all_cells.append(" | ".join(row_vals))
                        for idx, row_text in enumerate(all_cells):
                            if quoted_passage in row_text:
                                start = max(0, idx - 2)
                                end = min(len(all_cells), idx + 3)
                                surrounding_context = "\n".join(all_cells[start:end])
                                break
                    except Exception:
                        pass

                elif quoted_passage and doc_type == "presentation":
                    try:
                        _cmd = ["gws"] + "slides presentations get".split()
                        _cmd.extend(["--params", json.dumps({
                            "presentationId": doc_id,
                            "fields": "slides.pageElements.shape.text.textElements.textRun.content",
                        })])
                        _cmd.extend(["--format", "json"])
                        _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                        if _r.returncode != 0:
                            raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
                        pres_data = json.loads(_r.stdout) if _r.stdout.strip() else {}
                        for slide in pres_data.get("slides", []):
                            slide_text_parts = []
                            for element in slide.get("pageElements", []):
                                shape = element.get("shape", {})
                                text_obj = shape.get("text", {})
                                for te in text_obj.get("textElements", []):
                                    tr = te.get("textRun", {})
                                    content = tr.get("content", "")
                                    if content.strip():
                                        slide_text_parts.append(content.strip())
                            slide_text = "\n".join(slide_text_parts)
                            if quoted_passage in slide_text:
                                surrounding_context = slide_text
                                break
                    except Exception:
                        pass

                # ── Build doc link ──
                type_slug = {
                    "document": "document",
                    "spreadsheet": "spreadsheets",
                    "presentation": "presentation",
                }.get(doc_type, "document")
                doc_link = f"https://docs.google.com/{type_slug}/d/{doc_id}/edit"
                if comment_id:
                    doc_link += f"?disco={comment_id}"

                # ── Determine from_person ──
                from_person = comment_author
                if comment_author_email:
                    from_person = f"{comment_author} ({comment_author_email})"
                if not from_person:
                    from_person = triggered_by

                # ── Build enriched entry for block ──
                tz = pytz.timezone("America/New_York")
                from datetime import datetime
                enrich_ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
                enriched_lines = [
                    (
                        f"[enriched: {enrich_ts}] "
                        f"comment_id: {comment_id} "
                        f"| doc_id: {doc_id}"
                    ),
                    f"doc_title: {doc_title}",
                    f"doc_type: {doc_type}",
                    f"doc_link: {doc_link}",
                    f"comment_author: {from_person}",
                ]
                if triggered_by:
                    enriched_lines.append(f"triggered_by: {triggered_by}")
                if triggered_by and triggered_by.lower() != OWNER_EMAIL.lower():
                    enriched_lines.append(f"[FROM: {triggered_by}]")
                if comment_date:
                    enriched_lines.append(f"comment_date: {comment_date}")
                if comment_text:
                    enriched_lines.append(f"comment_text: {comment_text[:300]}")
                if quoted_passage:
                    enriched_lines.append(f"quoted_passage: {quoted_passage[:200]}")
                if surrounding_context:
                    enriched_lines.append(
                        f"surrounding_context: {surrounding_context[:500]}"
                    )
                if marker_type:
                    enriched_lines.append(f"marker_type: {marker_type}")
                if task_hint:
                    enriched_lines.append(f"task_hint: {task_hint}")
                if context:
                    enriched_lines.append(f"context: {context}")
                if notes and not marker_type:
                    enriched_lines.append(f"notes: {notes}")
                raw_urls = fields.get("urls", "")
                if raw_urls:
                    enriched_lines.append(f"urls: {raw_urls}")
                enriched_lines.append("trigger: docs-comment-action-item")

                processed.append({
                    "doc_id": doc_id,
                    "comment_id": comment_id,
                    "doc_title": doc_title,
                    "marker_type": marker_type,
                    "enriched_entry": "\n".join(enriched_lines),
                })

            except Exception as entry_err:
                errors.append({
                    "entry": entry_text[:80],
                    "error": str(entry_err),
                })

        # ── Replace raw entries with enriched versions in block ──
        if processed:
            block_url = f"{LETTA_BASE}/v1/blocks/{queue_block_id}"
            block_req = urllib.request.Request(block_url, method="GET")
            with urllib.request.urlopen(block_req, timeout=10) as resp:
                block_data = json.loads(resp.read().decode("utf-8"))
            current_value = block_data.get("value", "")

            # Build lookup of enriched replacements
            enriched_lookup = {}
            for p in processed:
                key = (p["doc_id"], p["comment_id"])
                enriched_lookup[key] = p["enriched_entry"]

            new_parts = []
            for part in current_value.split("---"):
                part_stripped = part.strip()
                if not part_stripped:
                    continue
                replaced = False
                for (did, cid), enriched in enriched_lookup.items():
                    if (
                        did in part_stripped
                        and (not cid or cid in part_stripped)
                        and "[enriched:" not in part_stripped
                    ):
                        new_parts.append(enriched)
                        replaced = True
                        break
                if not replaced:
                    new_parts.append(part_stripped)

            if new_parts:
                new_value = "\n---\n".join(new_parts) + "\n---"
            else:
                new_value = ""

            update_data = json.dumps({"value": new_value}).encode("utf-8")
            update_req = urllib.request.Request(
                block_url,
                data=update_data,
                headers={"Content-Type": "application/json"},
                method="PATCH",
            )
            urllib.request.urlopen(update_req, timeout=10)

        result = {
            "status": "ok",
            "message": f"Enriched {len(processed)} entry(s). Review enriched entries in queued_tasks_from_drive and extract tasks using add_extracted_tasks, then remove processed entries from the block.",
            "processed": len(processed),
            "details": [
                {
                    "doc_title": p["doc_title"],
                    "marker_type": p["marker_type"],
                }
                for p in processed
            ],
        }
        if errors:
            result["errors"] = errors

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
