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

    Reads the queued_tasks_from_drive memory block. For each entry:
    1. Calls Drive API to get comment metadata (author, text, quoted passage)
    2. Calls Drive API to get file metadata (type, title)
    3. Retrieves surrounding context based on document type
    4. Calls add_extracted_tasks with full metadata
    5. Removes the processed entry from the block

    Call this tool when notified of new drive comment task queue entries.

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
    import traceback
    import pytz
    import urllib.request
    import urllib.error
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        QUEUE_BLOCK_LABEL = "queued_tasks_from_drive"
        OWNER_EMAIL = "cdorsey@concord.org"

        if max_entries is None or max_entries < 1:
            max_entries = 10
        if max_entries > 20:
            max_entries = 20

        # ── Google Auth ──
        CREDS_DIR = "/root/.gmail-mcp"
        with open(f"{CREDS_DIR}/gcp-oauth.keys.json") as f:
            keys = json.load(f)
            client_config = keys.get("installed") or keys.get("web")
        with open(f"{CREDS_DIR}/credentials.json") as f:
            tokens = json.load(f)
        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=client_config["token_uri"],
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/documents.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/presentations.readonly",
            ],
        )
        if not creds.valid:
            creds.refresh(Request())
            tokens["access_token"] = creds.token
            with open(f"{CREDS_DIR}/credentials.json", "w") as f:
                json.dump(tokens, f, indent=2)

        drive_service = build("drive", "v3", credentials=creds)

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
                    file_meta = drive_service.files().get(
                        fileId=doc_id,
                        fields="id,name,mimeType,webViewLink",
                    ).execute()
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
                        comment_data = drive_service.comments().get(
                            fileId=doc_id,
                            commentId=comment_id,
                            fields="content,author,quotedFileContent,createdTime,resolved",
                        ).execute()
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
                        docs_service = build("docs", "v1", credentials=creds)
                        doc_data = docs_service.documents().get(
                            documentId=doc_id,
                        ).execute()
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
                        sheets_service = build("sheets", "v4", credentials=creds)
                        sheet_data = sheets_service.spreadsheets().get(
                            spreadsheetId=doc_id,
                            fields="sheets.data.rowData.values.formattedValue",
                        ).execute()
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
                        slides_service = build("slides", "v1", credentials=creds)
                        pres_data = slides_service.presentations().get(
                            presentationId=doc_id,
                            fields="slides.pageElements.shape.text.textElements.textRun.content",
                        ).execute()
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

                # ── Build source text ──
                source_parts = []
                if comment_text:
                    source_parts.append(f"Comment: {comment_text}")
                if quoted_passage:
                    source_parts.append(f"Quoted passage: {quoted_passage}")
                if surrounding_context:
                    source_parts.append(f"Surrounding context:\n{surrounding_context}")
                if notes:
                    source_parts.append(f"User notes: {notes}")
                if context:
                    source_parts.append(f"User context: {context}")
                source_text = "\n\n".join(source_parts) if source_parts else "(no content)"

                # ── Build doc link ──
                type_slug = {
                    "document": "document",
                    "spreadsheet": "spreadsheets",
                    "presentation": "presentation",
                }.get(doc_type, "document")
                doc_link = f"https://docs.google.com/{type_slug}/d/{doc_id}/edit"
                if comment_id:
                    doc_link += f"?disco={comment_id}"

                # ── Compose task description ──
                if marker_type == "explicit" and task_hint:
                    task_description = task_hint
                elif marker_type == "pointer" and task_hint:
                    task_description = f"{task_hint} (from comment on {doc_title})"
                elif comment_text:
                    task_description = f"Review comment: {comment_text[:100]}"
                else:
                    task_description = f"Review comment on {doc_title}"

                # Foreign trigger annotation
                if triggered_by and triggered_by.lower() != OWNER_EMAIL.lower():
                    task_description = f"[FROM: {triggered_by}] {task_description}"

                # ── Determine from_person ──
                from_person = comment_author
                if comment_author_email:
                    from_person = f"{comment_author} ({comment_author_email})"
                if not from_person:
                    from_person = triggered_by

                # ── Build reference_id ──
                reference_id = f"gdrive-comment-{doc_id}"
                if comment_id:
                    reference_id += f"-{comment_id}"

                # ── Build extraction message ──
                extract_msg = (
                    f"Extract this task using add_extracted_tasks:\n"
                    f"- task_description: {task_description}\n"
                    f"- source_type: google-drive-comment\n"
                    f"- source_context: Comment on {doc_title} ({doc_type})\n"
                    f"- reference_id: {reference_id}\n"
                    f"- source_text: {source_text[:2000]}\n"
                    f"- from_person: {from_person}\n"
                    f"- location: {doc_title} — {doc_link}\n"
                    f"- location_id: {doc_id}\n"
                    f"- source_timestamp: {comment_date}\n"
                )

                processed.append({
                    "doc_id": doc_id,
                    "comment_id": comment_id,
                    "doc_title": doc_title,
                    "task_description": task_description,
                    "marker_type": marker_type,
                    "extract_message": extract_msg,
                })

            except Exception as entry_err:
                errors.append({
                    "entry": entry_text[:80],
                    "error": str(entry_err),
                })

        # ── Remove processed entries from block ──
        if processed:
            block_url = f"{LETTA_BASE}/v1/blocks/{queue_block_id}"
            block_req = urllib.request.Request(block_url, method="GET")
            with urllib.request.urlopen(block_req, timeout=10) as resp:
                block_data = json.loads(resp.read().decode("utf-8"))
            current_value = block_data.get("value", "")

            remaining_parts = []
            for part in current_value.split("---"):
                part_stripped = part.strip()
                if not part_stripped:
                    continue
                was_processed = False
                for p in processed:
                    if (
                        p["doc_id"] in part_stripped
                        and (not p["comment_id"] or p["comment_id"] in part_stripped)
                    ):
                        was_processed = True
                        break
                if not was_processed:
                    remaining_parts.append(part_stripped)

            if remaining_parts:
                new_value = "\n---\n".join(remaining_parts) + "\n---"
            else:
                new_value = (
                    "# Queued Tasks from Drive Comments\n\n"
                    "Drive comment tasks queued by gmail-watch-service for extraction.\n"
                    "Process each entry using process_drive_task_queue tool, "
                    "then remove it.\n\n(empty)\n"
                )

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
            "message": f"Processed {len(processed)} drive comment task(s).",
            "processed": len(processed),
            "details": [
                {
                    "doc_title": p["doc_title"],
                    "task_description": p["task_description"],
                    "marker_type": p["marker_type"],
                }
                for p in processed
            ],
        }
        if errors:
            result["errors"] = errors

        # Return extraction messages for the agent to act on
        if processed:
            result["extraction_messages"] = [
                p["extract_message"] for p in processed
            ]

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
