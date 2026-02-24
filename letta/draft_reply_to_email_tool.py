"""
Draft Reply to Email Tool for Letta

Creates a Gmail draft reply threaded into the original email conversation.
Combines threading headers from reply_to_email with draft creation from
draft_email. The draft appears in Gmail's Drafts folder for user review
and manual sending.

Tool: draft_reply_to_email
"""

from typing import Dict, Any


def draft_reply_to_email(
    message_id: str,
    reply_text: str,
    reply_all: bool = True,
) -> Dict[str, Any]:
    """
    Create a draft reply to an existing email, threaded into the original conversation.

    Fetches the original message for threading headers (In-Reply-To, References,
    threadId), builds a proper MIME reply, and creates it as a Gmail draft instead
    of sending. The user can review and send the draft manually from Gmail.

    This is the email equivalent of reply_to_document_comment for Google Docs
    and post_slack_channel_reply for Slack — used by the completion feedback
    loop to close the loop on email-sourced tasks.

    Args:
        message_id: Gmail message ID of the email to reply to. This is the
            hex message ID from the archival passage (e.g., "19c73591f21f54c8"),
            NOT the RFC Message-ID header.
        reply_text: The text body of the reply draft. This is the completion
            feedback message approved by the user.
        reply_all: If True (default), reply to all original recipients.
            If False, reply only to the original sender.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - draft_id: Gmail draft ID (for future reference/deletion)
        - message_id: Gmail message ID of the draft
        - threadId: Gmail thread ID the draft belongs to
        - subject: The reply subject line
        - to: Primary recipient
        - cc: CC recipients (if reply_all)
        - gmail_link: Direct link to the draft in Gmail web UI
        - error_message: Error details if status is "error"
    """
    import json
    import base64
    import traceback
    from email.mime.text import MIMEText
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    EMPTY = {
        "status": "", "draft_id": "", "message_id": "", "threadId": "",
        "subject": "", "to": "", "cc": "", "gmail_link": "",
        "error_message": "",
    }

    try:
        if not message_id or not message_id.strip():
            return {**EMPTY, "status": "error", "error_message": "message_id is required"}

        if not reply_text or not reply_text.strip():
            return {**EMPTY, "status": "error", "error_message": "reply_text is required"}

        # --- Auth boilerplate (same as gmail_tools.py) ---
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
            scopes=["https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.settings.basic"],
        )

        if not creds.valid:
            creds.refresh(Request())
            tokens["access_token"] = creds.token
            with open(f"{CREDS_DIR}/credentials.json", "w") as f:
                json.dump(tokens, f, indent=2)

        gmail = build("gmail", "v1", credentials=creds)
        # --- End auth boilerplate ---

        # Fetch original message to get threadId
        original = gmail.users().messages().get(
            userId="me",
            id=message_id.strip(),
            format="metadata",
            metadataHeaders=["Subject"],
        ).execute()

        thread_id = original.get("threadId", "")
        orig_hdrs = original.get("payload", {}).get("headers", [])
        orig_subject = ""
        for h in orig_hdrs:
            if h["name"].lower() == "subject":
                orig_subject = h["value"]

        # Fetch full thread to find the most recent message
        thread_data = gmail.users().threads().get(
            userId="me",
            id=thread_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Cc", "Message-ID", "References", "Date"],
        ).execute()

        thread_msgs = thread_data.get("messages", [])
        # Use the last message in the thread for reply context
        last_msg = thread_msgs[-1] if thread_msgs else {}
        last_headers = last_msg.get("payload", {}).get("headers", [])
        last_header_map = {}
        for h in last_headers:
            last_header_map[h["name"].lower()] = h["value"]

        last_from = last_header_map.get("from", "")
        last_to = last_header_map.get("to", "")
        last_cc = last_header_map.get("cc", "")
        last_message_id = last_header_map.get("message-id", "")
        last_references = last_header_map.get("references", "")
        last_date = last_header_map.get("date", "")
        last_gmail_id = last_msg.get("id", "")

        # Fetch full body of the last message (snippet is truncated to ~200 chars)
        last_body_text = ""
        if last_gmail_id:
            last_full = gmail.users().messages().get(
                userId="me", id=last_gmail_id, format="full",
            ).execute()
            payload = last_full.get("payload", {})

            # Extract plain text from MIME parts
            parts_to_check = [payload]
            while parts_to_check:
                part = parts_to_check.pop(0)
                mime = part.get("mimeType", "")
                if mime == "text/plain" and part.get("body", {}).get("data"):
                    last_body_text = base64.urlsafe_b64decode(
                        part["body"]["data"]
                    ).decode("utf-8", errors="replace")
                    break
                if part.get("parts"):
                    parts_to_check.extend(part["parts"])

        # Build reply subject
        reply_subject = orig_subject
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        # Determine recipients from the last message in the thread
        reply_to = last_from
        reply_cc = ""

        if reply_all:
            # Get our own email to exclude from recipients
            profile = gmail.users().getProfile(userId="me").execute()
            my_email = profile.get("emailAddress", "").lower()

            # Combine last message's To and Cc, excluding ourselves
            all_recipients = []
            for addr in (last_to + "," + last_cc).split(","):
                addr = addr.strip()
                if addr and my_email not in addr.lower():
                    all_recipients.append(addr)

            # Last sender is the To, remaining go to Cc
            if all_recipients:
                reply_cc = ", ".join(all_recipients)

        # Build body with quoted text from the last message
        quote_source = last_body_text.strip() if last_body_text else ""
        if quote_source:
            quoted_lines = "\n".join(f"> {line}" for line in quote_source.split("\n"))
            full_body = f"{reply_text.strip()}\n\nOn {last_date}, {last_from} wrote:\n{quoted_lines}"
        else:
            full_body = reply_text.strip()

        # Build MIME message (plain text only)
        message = MIMEText(full_body, "plain")
        message["To"] = reply_to
        message["Subject"] = reply_subject

        if reply_cc:
            message["Cc"] = reply_cc

        # Threading headers — reply to the last message in the thread
        if last_message_id:
            message["In-Reply-To"] = last_message_id
            if last_references:
                message["References"] = f"{last_references} {last_message_id}"
            else:
                message["References"] = last_message_id

        # Encode and create DRAFT (not send)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft = gmail.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw, "threadId": thread_id}},
        ).execute()

        draft_message = draft.get("message", {})
        draft_msg_id = draft_message.get("id", "")

        return {
            "status": "ok",
            "draft_id": draft.get("id", ""),
            "message_id": draft_msg_id,
            "threadId": draft_message.get("threadId", ""),
            "subject": reply_subject,
            "to": reply_to,
            "cc": reply_cc,
            "gmail_link": f"https://mail.google.com/mail/u/0/#drafts/{draft_msg_id}",
            "error_message": "",
        }

    except Exception as e:
        return {
            **EMPTY, "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
