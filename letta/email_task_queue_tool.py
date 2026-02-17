"""
Email Task Queue Tool for Letta

Processes emails labeled TaskQueue in Gmail and queues them for task
extraction by the email-agent. Supports two workflows:

1. Forward-to-self: User forwards email to cdorsey+tasks@concord.org,
   optionally typing notes above the forwarded content. Gmail filter
   applies TaskQueue label.

2. Direct label: User manually applies TaskQueue label to any email.

Tool: process_email_task_queue
"""

from typing import Dict, Any


def process_email_task_queue(max_messages: int = 10) -> Dict[str, Any]:
    """
    Process emails labeled TaskQueue and queue them for task extraction.

    Searches Gmail for messages with the TaskQueue label. For each message:
    1. Detects if it's a forwarded message (parses user notes + original content)
    2. Resolves the original message to get its canonical Gmail message ID
    3. Writes a structured entry to the queued_tasks_from_email memory block
    4. Removes the TaskQueue label from the processed message

    Two workflows are supported:
    - Forward to +tasks address: User notes typed above the forward delimiter
      are captured. The original message is resolved via sender/subject search.
    - Manual label: The message itself is the task source (no notes).

    Call this tool when triggered by Gmail Watch or to manually check for
    queued items.

    Args:
        max_messages: Maximum TaskQueue messages to process per call (1-20,
            default 10). Higher values process more items but take longer.

    Returns:
        Dictionary with status, count of messages processed, and per-message
        details including subject, sender, and whether notes were captured.
    """
    import os
    import re
    import json
    import base64
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.error
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        QUEUE_BLOCK_LABEL = "queued_tasks_from_email"
        TASKQUEUE_LABEL_NAME = "TaskQueue"
        FORWARD_DELIMITER = re.compile(r'-{5,}\s*Forwarded message\s*-{5,}')
        FORWARDED_HEADER = re.compile(
            r'^(From|Date|Subject|To):\s*(.+)$', re.MULTILINE
        )
        EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w.-]+')

        # Clamp max_messages
        if max_messages is None or max_messages < 1:
            max_messages = 10
        if max_messages > 20:
            max_messages = 20

        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)

        # ── Gmail Auth ──
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
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.settings.basic",
            ],
        )
        if not creds.valid:
            creds.refresh(Request())
            tokens["access_token"] = creds.token
            with open(f"{CREDS_DIR}/credentials.json", "w") as f:
                json.dump(tokens, f, indent=2)
        gmail = build("gmail", "v1", credentials=creds)

        # ── Find TaskQueue label ID ──
        labels_resp = gmail.users().labels().list(userId="me").execute()
        taskqueue_label_id = None
        for lbl in labels_resp.get("labels", []):
            if lbl["name"] == TASKQUEUE_LABEL_NAME:
                taskqueue_label_id = lbl["id"]
                break
        if not taskqueue_label_id:
            return {
                "status": "ok",
                "message": "TaskQueue label not found in Gmail. Create it first.",
                "processed": 0,
                "details": [],
            }

        # ── Search for TaskQueue messages ──
        search_resp = gmail.users().messages().list(
            userId="me",
            labelIds=[taskqueue_label_id],
            maxResults=max_messages,
        ).execute()
        messages = search_resp.get("messages", [])
        if not messages:
            return {
                "status": "ok",
                "message": "No messages in TaskQueue.",
                "processed": 0,
                "details": [],
            }

        # ── Get queue block ──
        if not AGENT_ID:
            return {
                "status": "error",
                "error_message": "LETTA_AGENT_ID not set",
            }
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
                "error_message": (
                    f"Block '{QUEUE_BLOCK_LABEL}' not found on this agent."
                ),
            }
        queue_block_id = queue_block["id"]

        # ── Process each message ──
        processed = []
        errors = []

        for msg_ref in messages:
            msg_id = msg_ref["id"]
            try:
                # Read full message
                msg = gmail.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()

                # Extract headers
                headers = msg.get("payload", {}).get("headers", [])
                header_map = {}
                for h in headers:
                    header_map[h["name"].lower()] = h["value"]

                # Extract body (stack-based MIME walk, prefer text/plain)
                plain_body = ""
                html_body = ""
                stack = [msg.get("payload", {})]
                while stack:
                    part = stack.pop()
                    mime_type = part.get("mimeType", "")
                    parts = part.get("parts", [])
                    if parts:
                        stack.extend(parts)
                        continue
                    body_data = part.get("body", {}).get("data", "")
                    if not body_data:
                        continue
                    decoded = base64.urlsafe_b64decode(
                        body_data
                    ).decode("utf-8", errors="replace")
                    if mime_type == "text/plain" and not plain_body:
                        plain_body = decoded
                    elif mime_type == "text/html" and not html_body:
                        html_body = decoded
                body = plain_body if plain_body else html_body

                # ── Detect forward vs direct label ──
                forward_match = FORWARD_DELIMITER.search(body) if body else None
                notes = ""
                original_from = header_map.get("from", "")
                original_subject = header_map.get("subject", "")
                original_date = header_map.get("date", "")
                original_message_id = msg_id
                original_thread_id = msg.get("threadId", "")
                trigger = "TaskQueue"
                snippet = msg.get("snippet", "")

                if forward_match:
                    trigger = "forwarded"
                    above = body[:forward_match.start()].strip()
                    below = body[forward_match.end():]

                    # Notes are above the delimiter
                    if above:
                        notes = above

                    # Parse forwarded headers (From, Date, Subject, To)
                    fwd_headers = {}
                    for match in FORWARDED_HEADER.finditer(below[:500]):
                        fwd_headers[match.group(1).lower()] = (
                            match.group(2).strip()
                        )

                    if fwd_headers.get("from"):
                        original_from = fwd_headers["from"]
                    if fwd_headers.get("subject"):
                        original_subject = fwd_headers["subject"]
                    if fwd_headers.get("date"):
                        original_date = fwd_headers["date"]

                    # Extract snippet from forwarded body (after header block)
                    fwd_body_start = re.search(r'\n\s*\n', below)
                    if fwd_body_start:
                        fwd_body = below[fwd_body_start.end():].strip()
                        if fwd_body:
                            snippet = fwd_body[:150]

                    # ── Resolve original message ──
                    from_match = EMAIL_PATTERN.search(original_from)
                    from_email = from_match.group(0) if from_match else ""

                    if from_email and original_subject:
                        clean_subject = original_subject.replace('"', '\\"')
                        search_q = (
                            f'from:{from_email} subject:"{clean_subject}"'
                        )
                        try:
                            orig_search = gmail.users().messages().list(
                                userId="me", q=search_q, maxResults=5
                            ).execute()
                            orig_messages = orig_search.get("messages", [])
                            for orig_ref in orig_messages:
                                if orig_ref["id"] != msg_id:
                                    original_message_id = orig_ref["id"]
                                    original_thread_id = orig_ref.get(
                                        "threadId", original_thread_id
                                    )
                                    break
                        except Exception:
                            pass  # Keep forwarded message ID as fallback

                # ── Build queue entry ──
                gmail_link = (
                    "https://mail.google.com/mail/u/0/#inbox/"
                    + original_thread_id
                )
                lines = [
                    (
                        f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] "
                        f"message_id: {original_message_id} "
                        f"| thread_id: {original_thread_id}"
                    ),
                    f"subject: {original_subject}",
                    f"from: {original_from}",
                    f"date: {original_date}",
                    f"snippet: {snippet[:150]}",
                    f"gmail_link: {gmail_link}",
                    f"trigger: {trigger}",
                ]
                if notes:
                    lines.append(f"notes: {notes}")
                if trigger == "forwarded":
                    lines.append(f"forwarded_message_id: {msg_id}")
                entry_text = "\n".join(lines)

                # ── Append to queue block ──
                block_url = f"{LETTA_BASE}/v1/blocks/{queue_block_id}"
                block_req = urllib.request.Request(block_url, method="GET")
                with urllib.request.urlopen(block_req, timeout=10) as resp:
                    block_data = json.loads(resp.read().decode("utf-8"))
                current_value = block_data.get("value", "").rstrip()

                updated = f"{current_value}\n{entry_text}\n---"

                update_data = json.dumps(
                    {"value": updated}
                ).encode("utf-8")
                update_req = urllib.request.Request(
                    block_url,
                    data=update_data,
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                urllib.request.urlopen(update_req, timeout=10)

                # ── Remove TaskQueue label ──
                gmail.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"removeLabelIds": [taskqueue_label_id]},
                ).execute()

                processed.append({
                    "message_id": original_message_id,
                    "subject": original_subject,
                    "from": original_from,
                    "has_notes": bool(notes),
                    "is_forward": bool(forward_match),
                })

            except Exception as msg_err:
                errors.append({
                    "message_id": msg_id,
                    "error": str(msg_err),
                })

        result = {
            "status": "ok",
            "message": f"Processed {len(processed)} message(s) from TaskQueue.",
            "processed": len(processed),
            "details": processed,
        }
        if errors:
            result["errors"] = errors
        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
