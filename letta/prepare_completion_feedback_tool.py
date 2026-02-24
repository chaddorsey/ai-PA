"""
Prepare Completion Feedback Tool for Letta

Parses a completed task's archival passage and prepares structured routing
info + draft message for notifying the original requester.

Phase 1: Google Doc comments only (reply + optionally resolve).
Phase 2+: Slack threaded replies, email flagging.

Tool: prepare_completion_feedback
"""

from typing import Dict, Any


def prepare_completion_feedback(
    ref_id: str,
) -> Dict[str, Any]:
    """
    Prepare a feedback message for the original requester of a completed task.

    Looks up the completed task's archival passage, determines the appropriate
    feedback channel based on source_type, and returns a structured routing
    plan with a draft message. The agent should present this to the user for
    approval before dispatching.

    Currently supports:
    - google-docs-comment: Reply to the original comment + optionally resolve
    - slack: Threaded reply to the original message (returns routing info)
    - email: Flags for manual follow-up (no auto-reply)

    Args:
        ref_id: The 8-character hex reference ID of the completed task
            (e.g., "8a3b5089"). Must be a task with status:completed
            or status:dropped in the archive.

    Returns:
        Dictionary with keys:
        - status: "ok", "not_found", "not_applicable", or "error"
        - ref_id: The ref_id that was looked up
        - source_type: The source type of the original task
        - from_person: Who originated the task
        - task_description: The task title
        - should_send_feedback: Whether feedback is appropriate
        - reason: Why feedback should or should not be sent
        - suggested_action: Action type (e.g., "reply_and_resolve", "threaded_reply", "manual_followup")
        - routing: Dict with tool name and pre-parsed args for dispatching
        - draft_message: Suggested feedback message text (fallback template)
        - resolve_after_reply: Whether to resolve the comment after replying
        - source_comment_text: The original comment/message text that triggered the task
        - document_title: The title of the source document (if applicable)
        - comment_thread: List of existing replies on the comment thread
        - error_message: Error details if status is "error"
    """
    import os
    import re
    import json
    import traceback
    import urllib.request
    import urllib.error

    EMPTY_RESULT = {
        "status": "", "ref_id": "", "source_type": "", "from_person": "",
        "task_description": "", "should_send_feedback": False, "reason": "",
        "suggested_action": "", "routing": {}, "draft_message": "",
        "resolve_after_reply": False, "source_comment_text": "",
        "document_title": "", "comment_thread": [], "error_message": "",
    }

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
        SEARCH_URL = f"{LETTA_BASE}/v1/passages/search"
        USER_NAME = "Chad Dorsey"

        if not ref_id or not ref_id.strip():
            return {**EMPTY_RESULT, "status": "error", "error_message": "ref_id is required"}

        ref_id = ref_id.strip()

        # ── Look up the passage ──
        payload = json.dumps({
            "query": f"REF_ID: {ref_id}",
            "archive_id": ARCHIVE_ID,
            "limit": 20,
        }).encode("utf-8")
        req = urllib.request.Request(
            SEARCH_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            results = json.loads(resp.read().decode("utf-8"))

        target = None
        for item in results:
            p = item.get("passage", item)
            if f"REF_ID: {ref_id}" in p.get("text", "") and p.get("archive_id", "") == ARCHIVE_ID:
                target = p
                break

        if not target:
            return {**EMPTY_RESULT, "status": "not_found", "ref_id": ref_id,
                    "error_message": f"No passage found with REF_ID: {ref_id}"}

        text = target.get("text", "")

        # ── Parse passage fields ──
        field_patterns = [
            ("task_description", r"^TASK: (.+)$"),
            ("source_type", r"^- Type: (.+)$"),
            ("source_context", r"^- Context: (.+)$"),
            ("reference_id", r"^- Reference ID: (.+)$"),
            ("from_person", r"^- From: (.+)$"),
            ("location", r"^- Location: (.+)$"),
            ("omnifocus_status", r"^- Status: (.+)$"),
        ]
        fields = {}
        for key, pattern in field_patterns:
            m = re.search(pattern, text, re.MULTILINE)
            fields[key] = m.group(1).strip() if m else ""

        task_description = fields["task_description"]
        # Strip [COMPLETED]/[DROPPED] prefix from task description for cleaner display
        task_description = re.sub(r"^\[(COMPLETED|DROPPED)\]\s*", "", task_description)

        source_type = fields["source_type"]
        from_person = fields["from_person"]
        reference_id = fields["reference_id"]
        omnifocus_status = fields["omnifocus_status"]

        # ── Check if feedback is appropriate ──

        # Must be completed or dropped
        if omnifocus_status not in ("completed", "dropped"):
            return {
                **EMPTY_RESULT, "status": "not_applicable", "ref_id": ref_id,
                "source_type": source_type, "from_person": from_person,
                "task_description": task_description,
                "reason": f"Task status is '{omnifocus_status}', not completed/dropped",
            }

        # Must have external origin
        is_external = bool(from_person and USER_NAME not in from_person)
        if not is_external:
            return {
                **EMPTY_RESULT, "status": "not_applicable", "ref_id": ref_id,
                "source_type": source_type, "from_person": from_person,
                "task_description": task_description,
                "reason": "Task originated from the user, not an external request",
            }

        # ── Route by source type ──

        if source_type == "google-docs-comment" or source_type == "google-drive-comment":
            # Parse reference_id: gdocs-comment-{fileId}-{commentId}
            # The commentId is always the last segment after the last hyphen
            # that starts with "AAAB" or similar Google comment ID pattern.
            # However, fileId can contain hyphens, so we use the known prefix.
            comment_match = re.match(r"gdocs-comment-(.+)-([A-Za-z0-9_]+)$", reference_id)
            if not comment_match:
                return {
                    **EMPTY_RESULT, "status": "error", "ref_id": ref_id,
                    "source_type": source_type, "from_person": from_person,
                    "task_description": task_description,
                    "error_message": f"Could not parse file_id and comment_id from reference_id: {reference_id}",
                }

            file_id = comment_match.group(1)
            comment_id = comment_match.group(2)

            # Extract person's first name for a natural message
            first_name = from_person.split()[0] if from_person else "there"

            # ── Fetch the original comment from Google Drive API ──
            # Best-effort: if this fails, we proceed with empty context
            source_comment_text = ""
            document_title = ""
            comment_thread = []
            try:
                from pathlib import Path
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                TOKEN_PATH = os.getenv(
                    "GMAIL_CREDENTIALS_PATH",
                    str(Path.home() / ".gmail-mcp" / "admin-reports.credentials.json")
                )
                SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

                creds = None
                if os.path.exists(TOKEN_PATH):
                    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, "w") as token:
                        token.write(creds.to_json())

                if creds and creds.valid:
                    service = build("drive", "v3", credentials=creds)

                    # Get document title
                    file_info = service.files().get(
                        fileId=file_id,
                        fields="name",
                        supportsAllDrives=True,
                    ).execute()
                    document_title = file_info.get("name", "")

                    # Get the specific comment with replies
                    comment_data = service.comments().get(
                        fileId=file_id,
                        commentId=comment_id,
                        fields="content,author(displayName),createdTime,resolved,replies(content,author(displayName),createdTime)",
                        includeDeleted=False,
                    ).execute()

                    source_comment_text = comment_data.get("content", "")
                    for reply in comment_data.get("replies", []):
                        comment_thread.append({
                            "author": reply.get("author", {}).get("displayName", ""),
                            "text": reply.get("content", ""),
                            "created_time": reply.get("createdTime", ""),
                        })
            except Exception:
                # Non-fatal: proceed without source context
                pass

            is_dropped = omnifocus_status == "dropped"
            if is_dropped:
                draft = f"This has been reviewed and won't be pursued at this time. Thanks for flagging it, {first_name}."
                suggested_action = "reply_and_resolve"
            else:
                draft = f"Done — {task_description.lower()}. Thanks, {first_name}!"
                suggested_action = "reply_and_resolve"

            return {
                "status": "ok",
                "ref_id": ref_id,
                "source_type": source_type,
                "from_person": from_person,
                "task_description": task_description,
                "should_send_feedback": True,
                "reason": f"External request from {from_person} via Google Doc comment",
                "suggested_action": suggested_action,
                "routing": {
                    "tool": "reply_to_document_comment",
                    "args": {
                        "file_id": file_id,
                        "comment_id": comment_id,
                    },
                    "resolve_tool": "resolve_document_comment",
                    "resolve_args": {
                        "file_id": file_id,
                        "comment_id": comment_id,
                    },
                },
                "draft_message": draft,
                "resolve_after_reply": True,
                "source_comment_text": source_comment_text,
                "document_title": document_title,
                "comment_thread": comment_thread,
                "error_message": "",
            }

        elif source_type == "slack":
            # Parse reference_id: slack-{channel_id}-{ts} or slack-{channel_id}-{ts}-t{thread_ts}
            slack_match = re.match(r"slack-([A-Z0-9]+)-([\d.]+?)(?:-t([\d.]+))?$", reference_id)
            if not slack_match:
                return {
                    **EMPTY_RESULT, "status": "error", "ref_id": ref_id,
                    "source_type": source_type, "from_person": from_person,
                    "task_description": task_description,
                    "error_message": f"Could not parse channel_id and ts from reference_id: {reference_id}",
                }

            channel_id = slack_match.group(1)
            message_ts = slack_match.group(2)
            original_thread_ts = slack_match.group(3)  # None if standalone
            # If message was in a thread, reply in that thread;
            # otherwise reply to the message itself (creates new thread)
            reply_thread_ts = original_thread_ts if original_thread_ts else message_ts
            first_name = from_person.split()[0] if from_person else "there"

            # Extract source text from passage's SOURCE TEXT section
            source_comment_text = ""
            source_text_match = re.search(r"SOURCE TEXT\n(.*)", text, re.DOTALL)
            if source_text_match:
                source_comment_text = source_text_match.group(1).strip()

            # Extract channel name from passage's Location field
            document_title = ""
            location_match = re.search(r"^- Location: (.+)$", text, re.MULTILINE)
            if location_match:
                document_title = location_match.group(1).strip()

            is_dropped = omnifocus_status == "dropped"
            if is_dropped:
                draft = f"Reviewed this — won't be pursuing it at this time. Thanks for flagging, {first_name}."
            else:
                draft = f"Done — {task_description.lower()}. Thanks, {first_name}!"

            return {
                "status": "ok",
                "ref_id": ref_id,
                "source_type": source_type,
                "from_person": from_person,
                "task_description": task_description,
                "should_send_feedback": True,
                "reason": f"External request from {from_person} via Slack message",
                "suggested_action": "threaded_reply",
                "routing": {
                    "tool": "post_slack_channel_reply",
                    "args": {
                        "channel": channel_id,
                        "thread_ts": reply_thread_ts,
                    },
                },
                "draft_message": draft,
                "resolve_after_reply": False,
                "source_comment_text": source_comment_text,
                "document_title": document_title,
                "comment_thread": [],
                "error_message": "",
            }

        elif source_type == "email":
            # Only create draft replies for completed tasks, not dropped
            if omnifocus_status == "dropped":
                return {
                    **EMPTY_RESULT, "status": "not_applicable", "ref_id": ref_id,
                    "source_type": source_type, "from_person": from_person,
                    "task_description": task_description,
                    "reason": "Dropped tasks don't get email draft replies",
                }

            # Parse reference_id: email-{message_id}
            email_match = re.match(r"email-(.+)$", reference_id)
            if not email_match:
                return {
                    **EMPTY_RESULT, "status": "error", "ref_id": ref_id,
                    "source_type": source_type, "from_person": from_person,
                    "task_description": task_description,
                    "error_message": f"Could not parse message_id from reference_id: {reference_id}",
                }

            email_message_id = email_match.group(1)
            first_name = from_person.split()[0] if from_person else "there"

            # ── Fetch email thread context from Gmail API ──
            source_comment_text = ""
            email_subject = ""
            thread_messages = []
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build as gmail_build

                GMAIL_CREDS_DIR = "/root/.gmail-mcp"

                with open(f"{GMAIL_CREDS_DIR}/gcp-oauth.keys.json") as gf:
                    gkeys = json.load(gf)
                    gmail_client_config = gkeys.get("installed") or gkeys.get("web")

                with open(f"{GMAIL_CREDS_DIR}/credentials.json") as gf:
                    gmail_tokens = json.load(gf)

                gmail_creds = Credentials(
                    token=gmail_tokens.get("access_token"),
                    refresh_token=gmail_tokens.get("refresh_token"),
                    token_uri=gmail_client_config["token_uri"],
                    client_id=gmail_client_config["client_id"],
                    client_secret=gmail_client_config["client_secret"],
                    scopes=["https://www.googleapis.com/auth/gmail.modify",
                            "https://www.googleapis.com/auth/gmail.settings.basic"],
                )

                if not gmail_creds.valid:
                    gmail_creds.refresh(Request())
                    gmail_tokens["access_token"] = gmail_creds.token
                    with open(f"{GMAIL_CREDS_DIR}/credentials.json", "w") as gf:
                        json.dump(gmail_tokens, gf, indent=2)

                gmail_svc = gmail_build("gmail", "v1", credentials=gmail_creds)

                # Get original message for threadId and subject
                original_msg = gmail_svc.users().messages().get(
                    userId="me", id=email_message_id, format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Cc", "Date"],
                ).execute()

                orig_hdrs = original_msg.get("payload", {}).get("headers", [])
                orig_hdr_map = {}
                for h in orig_hdrs:
                    orig_hdr_map[h["name"].lower()] = h["value"]

                email_subject = orig_hdr_map.get("subject", "")
                email_thread_id = original_msg.get("threadId", "")

                # Get full thread for conversation context
                if email_thread_id:
                    thread_data = gmail_svc.users().threads().get(
                        userId="me", id=email_thread_id, format="metadata",
                        metadataHeaders=["Subject", "From", "To", "Date"],
                    ).execute()

                    for tmsg in thread_data.get("messages", []):
                        tmsg_hdrs = tmsg.get("payload", {}).get("headers", [])
                        tmsg_hdr_map = {}
                        for h in tmsg_hdrs:
                            tmsg_hdr_map[h["name"].lower()] = h["value"]
                        thread_messages.append({
                            "author": tmsg_hdr_map.get("from", ""),
                            "text": tmsg.get("snippet", ""),
                            "created_time": tmsg_hdr_map.get("date", ""),
                        })
            except Exception:
                # Non-fatal: proceed without thread context
                pass

            # Extract source text from passage's SOURCE TEXT section
            source_text_match = re.search(r"SOURCE TEXT\n(.*)", text, re.DOTALL)
            if source_text_match:
                source_comment_text = source_text_match.group(1).strip()

            # Fall back to passage Location field for subject if Gmail API failed
            if not email_subject:
                location_match = re.search(r"^- Location: (.+)$", text, re.MULTILINE)
                if location_match:
                    email_subject = location_match.group(1).strip()

            draft = f"Thanks, {first_name} \u2014 {task_description.lower()}. Done!"

            return {
                "status": "ok",
                "ref_id": ref_id,
                "source_type": source_type,
                "from_person": from_person,
                "task_description": task_description,
                "should_send_feedback": True,
                "reason": f"External request from {from_person} via email",
                "suggested_action": "draft_reply",
                "routing": {
                    "tool": "draft_reply_to_email",
                    "args": {
                        "message_id": email_message_id,
                        "reply_all": True,
                    },
                },
                "draft_message": draft,
                "resolve_after_reply": False,
                "source_comment_text": source_comment_text,
                "document_title": email_subject,
                "comment_thread": thread_messages,
                "error_message": "",
            }

        else:
            return {
                **EMPTY_RESULT, "status": "not_applicable", "ref_id": ref_id,
                "source_type": source_type, "from_person": from_person,
                "task_description": task_description,
                "reason": f"No feedback routing defined for source_type '{source_type}'",
            }

    except Exception as e:
        return {
            **EMPTY_RESULT, "status": "error",
            "ref_id": ref_id if ref_id else "",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
