"""
Google Workspace CLI Tools for Letta Agents

Two tools that provide full access to all Google Workspace APIs:

1. run_gws — General-purpose tool for ANY gws CLI command (read, write, schema discovery)
2. compose_gmail — Email composition with MIME construction (the one thing a CLI can't do)

The gws CLI was designed for native LLM use: structured JSON output, self-documenting
schema commands, and consistent `gws <service> <resource> <method>` syntax.

Authentication:
- gws CLI reads credentials from GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE env var
- Credential file: /root/.gws/credentials.json (OAuth client + refresh token)
- Auto-refreshes tokens internally
"""

from typing import Dict, Any, Optional


def run_gws(command: str, params: Optional[str] = None, body: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any Google Workspace CLI command. Provides access to ALL Google APIs
    including Gmail, Calendar, Drive, Docs, Sheets, and Admin.

    Commands follow the pattern: <service> <resource> <method>
    Use "schema <dotted.path>" to discover API parameters and response shapes.

    Gmail examples:
      command="gmail users messages list", params='{"userId":"me","q":"is:unread","maxResults":5}'
      command="gmail users messages get", params='{"userId":"me","id":"MSG_ID","format":"full"}'
      command="gmail users threads get", params='{"userId":"me","id":"THREAD_ID","format":"metadata"}'
      command="gmail users labels list", params='{"userId":"me"}'
      command="gmail users labels get", params='{"userId":"me","id":"LABEL_ID"}'
      command="gmail users messages modify", params='{"userId":"me","id":"MSG_ID"}', body='{"addLabelIds":["STARRED"],"removeLabelIds":["UNREAD"]}'
      command="gmail users drafts list", params='{"userId":"me"}'
      command="gmail users drafts get", params='{"userId":"me","id":"DRAFT_ID","format":"full"}'
      command="gmail users drafts delete", params='{"userId":"me","id":"DRAFT_ID"}'
      command="gmail users messages attachments get", params='{"userId":"me","messageId":"MSG_ID","id":"ATTACHMENT_ID"}'
      command="gmail users getProfile", params='{"userId":"me"}'

    Calendar examples:
      command="calendar events list", params='{"calendarId":"primary","timeMin":"2026-03-06T00:00:00Z","maxResults":10}'
      command="calendar events get", params='{"calendarId":"primary","eventId":"EVENT_ID"}'

    Drive examples:
      command="drive files list", params='{"q":"name contains 'report'","pageSize":10}'
      command="drive files get", params='{"fileId":"FILE_ID"}'

    Schema discovery (learn any API's parameters):
      command="schema gmail.users.messages.list"
      command="schema gmail.users.drafts.create"
      command="schema calendar.events.list"

    Args:
        command: The gws subcommand path (e.g. "gmail users messages list" or "schema gmail.users.messages.list")
        params: JSON string of query/path parameters (optional). Passed as --params to gws.
        body: JSON string of request body (optional). Passed as --json to gws. Used for modify, create, update operations.
        timeout: Command timeout in seconds (default 30, increase for large operations)

    Returns:
        Dictionary with status and the parsed JSON response, or raw output for non-JSON responses.
    """
    import json
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        # Build the gws command
        cmd_parts = ["gws"] + command.strip().split()

        if params:
            cmd_parts.extend(["--params", params])
        if body:
            cmd_parts.extend(["--json", body])

        # Add --format json unless this is a schema or auth command
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word not in ("schema", "auth"):
            cmd_parts.extend(["--format", "json"])

        r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            return {"status": "error", "error_message": r.stderr[:1000] if r.stderr else f"Exit code {r.returncode}"}

        # Try to parse as JSON; fall back to raw text (schema output is plain text)
        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def compose_gmail(
    action: str,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
    reply_all: bool = False,
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compose and send or draft an email. Handles MIME message construction,
    base64 encoding, and threading — the parts that require code, not just CLI calls.

    For reading, searching, listing, modifying labels, or any other Gmail operation,
    use run_gws instead.

    Args:
        action: Either "send" to send immediately, or "draft" to create a draft
        to: Recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Plain text body of the email
        cc: CC recipient(s), comma-separated (optional)
        bcc: BCC recipient(s), comma-separated (optional)
        html_body: HTML version of the body for rich formatting (optional)
        reply_to_message_id: Gmail message ID to reply to (optional). When set,
            fetches the original message for proper threading headers (In-Reply-To,
            References) and prepends "Re:" to the subject if needed.
        reply_all: If True and reply_to_message_id is set, include all original
            recipients in CC (default False)
        thread_id: Gmail thread ID to associate with (optional). Auto-detected
            when reply_to_message_id is set.

    Returns:
        Dictionary with status, id (message or draft), threadId, and labelIds.
    """
    import json
    import base64
    import subprocess
    import traceback
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        if action not in ("send", "draft"):
            return {"status": "error", "error_message": "action must be 'send' or 'draft'"}

        reply_subject = subject
        in_reply_to = ""
        references = ""

        # If replying, fetch original message for threading
        if reply_to_message_id:
            r = subprocess.run(
                ["gws", "gmail", "users", "messages", "get",
                 "--params", json.dumps({
                     "userId": "me", "id": reply_to_message_id.strip(),
                     "format": "metadata",
                 }),
                 "--format", "json"],
                capture_output=True, text=True, timeout=15)

            if r.returncode == 0:
                original = json.loads(r.stdout)
                orig_headers = original.get("payload", {}).get("headers", [])
                orig_header_map = {}
                for h in orig_headers:
                    orig_header_map[h["name"].lower()] = h["value"]

                # Auto-detect thread_id from original message
                if not thread_id:
                    thread_id = original.get("threadId", "")

                # Build reply subject
                orig_subject = orig_header_map.get("subject", subject)
                if not orig_subject.lower().startswith("re:"):
                    reply_subject = f"Re: {orig_subject}"
                else:
                    reply_subject = orig_subject

                # Threading headers
                orig_message_id = orig_header_map.get("message-id", "")
                orig_references = orig_header_map.get("references", "")
                if orig_message_id:
                    in_reply_to = orig_message_id
                    references = f"{orig_references} {orig_message_id}".strip() if orig_references else orig_message_id

                # Reply-all: set To to original sender, CC to other recipients
                if reply_all:
                    orig_from = orig_header_map.get("from", "")
                    orig_to_val = orig_header_map.get("to", "")
                    orig_cc_val = orig_header_map.get("cc", "")

                    # Override To with original sender
                    to = orig_from

                    # Get our email to exclude from CC
                    r_profile = subprocess.run(
                        ["gws", "gmail", "users", "getProfile",
                         "--params", json.dumps({"userId": "me"}),
                         "--format", "json"],
                        capture_output=True, text=True, timeout=15)
                    my_email = ""
                    if r_profile.returncode == 0:
                        profile = json.loads(r_profile.stdout)
                        my_email = profile.get("emailAddress", "").lower()

                    all_recipients = []
                    for addr in (orig_to_val + "," + orig_cc_val).split(","):
                        addr = addr.strip()
                        if addr and my_email not in addr.lower() and orig_from.lower() not in addr.lower():
                            all_recipients.append(addr)

                    if all_recipients:
                        cc = ", ".join(all_recipients)
                elif not to:
                    # Simple reply: set To to original sender
                    to = orig_header_map.get("from", to)

        # Build MIME message
        if html_body:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain"))
            message.attach(MIMEText(html_body, "html"))
        else:
            message = MIMEText(body, "plain")

        message["To"] = to
        message["Subject"] = reply_subject

        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references

        # Base64url-encode the MIME message
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        # Build the gws command
        if action == "send":
            gws_body = {"raw": raw}
            if thread_id:
                gws_body["threadId"] = thread_id
            r_send = subprocess.run(
                ["gws", "gmail", "users", "messages", "send",
                 "--params", json.dumps({"userId": "me"}),
                 "--json", json.dumps(gws_body),
                 "--format", "json"],
                capture_output=True, text=True, timeout=30)
        else:  # draft
            draft_msg = {"raw": raw}
            if thread_id:
                draft_msg["threadId"] = thread_id
            r_send = subprocess.run(
                ["gws", "gmail", "users", "drafts", "create",
                 "--params", json.dumps({"userId": "me"}),
                 "--json", json.dumps({"message": draft_msg}),
                 "--format", "json"],
                capture_output=True, text=True, timeout=30)

        if r_send.returncode != 0:
            return {"status": "error", "error_message": r_send.stderr[:500]}

        result = json.loads(r_send.stdout) if r_send.stdout.strip() else {}

        # Normalize response shape for send vs draft
        if action == "draft":
            draft_message = result.get("message", {})
            return {
                "status": "ok",
                "action": "draft",
                "draft_id": result.get("id", ""),
                "message_id": draft_message.get("id", ""),
                "threadId": draft_message.get("threadId", ""),
                "gmail_link": f"https://mail.google.com/mail/u/0/#drafts/{result.get('id', '')}",
            }
        else:
            return {
                "status": "ok",
                "action": "sent",
                "id": result.get("id", ""),
                "threadId": result.get("threadId", ""),
                "labelIds": result.get("labelIds", []),
            }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
