"""
Draft Reply to Email Tool for Letta

Creates a Gmail draft reply threaded into the original email conversation.
Combines threading headers from reply_to_email with draft creation from
draft_email. The draft appears in Gmail's Drafts folder for user review
and manual sending.

Uses gws CLI for Gmail API access instead of direct OAuth.

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
    import html as html_mod
    import subprocess
    import traceback
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

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

        # Fetch original message to get threadId
        r = subprocess.run(
            ["gws", "gmail", "users", "messages", "get",
             "--params", json.dumps({
                 "userId": "me", "id": message_id.strip(),
                 "format": "metadata",
             }),
             "--format", "json"],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return {**EMPTY, "status": "error", "error_message": r.stderr[:500]}

        original = json.loads(r.stdout)
        thread_id = original.get("threadId", "")
        orig_hdrs = original.get("payload", {}).get("headers", [])
        orig_subject = ""
        for h in orig_hdrs:
            if h["name"].lower() == "subject":
                orig_subject = h["value"]

        # Fetch full thread to find the most recent message
        r2 = subprocess.run(
            ["gws", "gmail", "users", "threads", "get",
             "--params", json.dumps({
                 "userId": "me", "id": thread_id,
                 "format": "metadata",
             }),
             "--format", "json"],
            capture_output=True, text=True, timeout=15)
        if r2.returncode != 0:
            return {**EMPTY, "status": "error", "error_message": r2.stderr[:500]}

        thread_data = json.loads(r2.stdout)
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
        last_body_html = ""
        if last_gmail_id:
            r3 = subprocess.run(
                ["gws", "gmail", "users", "messages", "get",
                 "--params", json.dumps({"userId": "me", "id": last_gmail_id, "format": "full"}),
                 "--format", "json"],
                capture_output=True, text=True, timeout=15)
            if r3.returncode == 0:
                last_full = json.loads(r3.stdout)
                payload = last_full.get("payload", {})

                # Extract both plain text and HTML from MIME parts
                parts_to_check = [payload]
                while parts_to_check:
                    part = parts_to_check.pop(0)
                    mime = part.get("mimeType", "")
                    body_data = part.get("body", {}).get("data")
                    if body_data:
                        decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
                        if mime == "text/plain" and not last_body_text:
                            last_body_text = decoded
                        elif mime == "text/html" and not last_body_html:
                            last_body_html = decoded
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
            r_profile = subprocess.run(
                ["gws", "gmail", "users", "getProfile",
                 "--params", json.dumps({"userId": "me"}),
                 "--format", "json"],
                capture_output=True, text=True, timeout=15)
            my_email = ""
            if r_profile.returncode == 0:
                profile = json.loads(r_profile.stdout)
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
        reply_clean = reply_text.strip()
        has_plain = bool(last_body_text.strip()) if last_body_text else False
        has_html = bool(last_body_html.strip()) if last_body_html else False

        if has_plain or has_html:
            # Plain text version (for non-HTML clients)
            if has_plain:
                quoted_lines = "\n".join(f"> {line}" for line in last_body_text.strip().split("\n"))
                plain_body = f"{reply_clean}\n\nOn {last_date}, {last_from} wrote:\n{quoted_lines}"
            else:
                plain_body = reply_clean

            # HTML version — embed original HTML body in gmail_quote blockquote
            reply_html = html_mod.escape(reply_clean).replace("\n", "<br>")
            attr_html = html_mod.escape(f"On {last_date}, {last_from} wrote:")

            if has_html:
                quote_content = last_body_html.strip()
            else:
                quote_content = html_mod.escape(last_body_text.strip()).replace("\n", "<br>\n")

            html_body = (
                f'<div dir="ltr">{reply_html}</div><br>\n'
                f'<div class="gmail_quote">'
                f'<div dir="ltr" class="gmail_attr">{attr_html}<br></div>'
                f'<blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;'
                f'border-left:1px solid rgb(204,204,204);padding-left:1ex">'
                f'{quote_content}'
                f'</blockquote></div>'
            )

            message = MIMEMultipart("alternative")
            message.attach(MIMEText(plain_body, "plain"))
            message.attach(MIMEText(html_body, "html"))
        else:
            message = MIMEText(reply_clean, "plain")
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

        # Encode and create DRAFT (not send) via gws
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        r_draft = subprocess.run(
            ["gws", "gmail", "users", "drafts", "create",
             "--params", json.dumps({"userId": "me"}),
             "--json", json.dumps({"message": {"raw": raw, "threadId": thread_id}}),
             "--format", "json"],
            capture_output=True, text=True, timeout=30)
        if r_draft.returncode != 0:
            return {**EMPTY, "status": "error", "error_message": r_draft.stderr[:500]}

        draft = json.loads(r_draft.stdout) if r_draft.stdout.strip() else {}
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
            "gmail_link": f"https://mail.google.com/mail/u/0/#drafts/{draft.get('id', '')}",
            "error_message": "",
        }

    except Exception as e:
        return {
            **EMPTY, "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
