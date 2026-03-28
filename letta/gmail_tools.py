"""
Google Workspace CLI Tools for Letta Agents

Three tools that provide full access to all Google Workspace APIs:

1. run_gws — General-purpose tool for ANY gws CLI command (read, write, schema discovery)
2. fetch_gmail_messages — Batch-fetch Gmail messages with configurable fields in a single call
3. compose_gmail — Email composition with MIME construction (the one thing a CLI can't do)

The gws CLI was designed for native LLM use: structured JSON output, self-documenting
schema commands, and consistent `gws <service> <resource> <method>` syntax.

Authentication:
- gws CLI reads credentials from GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE env var
- Credential file: /root/.gws/credentials.json (OAuth client + refresh token)
- Auto-refreshes tokens internally
"""

from typing import Dict, Any, Optional


def run_gws(command: str, params: Optional[str] = None, body: Optional[str] = None,
            output_file: Optional[str] = None, format: Optional[str] = None,
            page_all: bool = False, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any Google Workspace CLI command. Provides access to ALL Google APIs.

    The gws CLI follows a consistent pattern: gws <service> <resource> <method>
    Use "schema <dotted.path>" to discover any API's parameters and response shapes.

    IMPORTANT: All params values must be strings or numbers, NOT arrays. For multi-value
    fields like labelIds, use a comma-separated string: "INBOX,UNREAD" not ["INBOX","UNREAD"].

    Available services: gmail, calendar, drive, docs, sheets, slides, tasks, people,
      chat, classroom, forms, keep, meet, events, admin-reports, workflow

    === SCHEMA DISCOVERY ===
    Always start here when unsure of parameters for any API:
      command="schema docs.documents.get"
      command="schema drive.files.export"
      command="schema gmail.users.messages.list"
      command="schema calendar.events.list"
      command="schema sheets.spreadsheets.get"

    === DOCS ===
    Read a document (first tab only):
      command="docs documents get", params='{"documentId":"DOC_ID"}'
    Read a document (ALL tabs — use this for multi-tab docs):
      command="docs documents get", params='{"documentId":"DOC_ID","includeTabsContent":true}'
      With tabs: content is in result.tabs[].documentTab.body (not result.body)
    Create a document:
      command="docs documents create", body='{"title":"My Doc"}'
    Append text to a document:
      command="docs +write --document DOC_ID --text 'Text to append'"
    Update a document (batch operations):
      command="docs documents batchUpdate", params='{"documentId":"DOC_ID"}', body='{"requests":[...]}'

    === DRIVE ===
    Export a Google Doc/Sheet/Slide as plain text, markdown, PDF, etc.:
      command="drive files export", params='{"fileId":"DOC_ID","mimeType":"text/plain"}', output_file="/dev/stdout"
      command="drive files export", params='{"fileId":"DOC_ID","mimeType":"text/markdown"}', output_file="/dev/stdout"
      Supported mimeTypes: text/plain, text/markdown, application/pdf,
        application/vnd.openxmlformats-officedocument.wordprocessingml.document
      IMPORTANT: Use output_file="/dev/stdout" to get the exported content returned directly.
      Without output_file, export saves to a local file and returns metadata only.
    List files:
      command="drive files list", params='{"q":"name contains \\'report\\'","pageSize":10}'
    Search for recent files:
      command="drive files list", params='{"q":"modifiedTime > \\'2026-03-01T00:00:00\\'","orderBy":"modifiedTime desc","pageSize":10}'
    Get file metadata:
      command="drive files get", params='{"fileId":"FILE_ID","fields":"id,name,modifiedTime,mimeType"}'

    === GMAIL ===
    Helpers (recommended — handle MIME, threading, attachments automatically):
      command="gmail +send --to alice@example.com --subject 'Hello' --body 'Hi!'"
      command="gmail +send --to alice@example.com --subject 'Hello' --body 'Hi!' --draft"
      command="gmail +send --to a@x.com --subject 'Report' --body 'See attached' -a report.pdf"
      command="gmail +reply --message-id MSG_ID --body 'Thanks!'"
      command="gmail +reply --message-id MSG_ID --body 'Draft reply' --draft"
      command="gmail +reply-all --message-id MSG_ID --body 'Noted, thanks all'"
      command="gmail +forward --message-id MSG_ID --to bob@example.com --body 'FYI'"
      command="gmail +forward --message-id MSG_ID --to bob@example.com --draft"
      command="gmail +read --message-id MSG_ID"
      command="gmail +triage"
      command="gmail +watch"
      Use --html flag for HTML body content. Use --draft to save instead of sending.
    Raw API (for operations not covered by helpers):
      command="gmail users messages list", params='{"userId":"me","q":"is:unread","maxResults":5}'
      command="gmail users messages get", params='{"userId":"me","id":"MSG_ID","format":"full"}'
    Get inbox counts (use labels get, NOT messages list):
      command="gmail users labels get", params='{"userId":"me","id":"INBOX"}'
      Returns messagesTotal and messagesUnread — these are exact counts.
      WARNING: Gmail's "resultSizeEstimate" from messages.list is inaccurate. Use labels.get.
    Modify labels:
      command="gmail users messages modify", params='{"userId":"me","id":"MSG_ID"}', body='{"addLabelIds":["STARRED"]}'
    List/get drafts:
      command="gmail users drafts list", params='{"userId":"me"}'
      command="gmail users drafts get", params='{"userId":"me","id":"DRAFT_ID","format":"full"}'

    === CALENDAR ===
    Helpers:
      command="calendar +agenda"
      command="calendar +insert --title 'Meeting' --start '2026-04-01T10:00' --end '2026-04-01T11:00'"
    Raw API:
      command="calendar events list", params='{"calendarId":"primary","timeMin":"2026-03-06T00:00:00Z","maxResults":10}'
      command="calendar events get", params='{"calendarId":"primary","eventId":"EVENT_ID"}'

    === SHEETS ===
    Get spreadsheet metadata:
      command="sheets spreadsheets get", params='{"spreadsheetId":"SHEET_ID"}'
    Read cell values:
      command="sheets spreadsheets.values get", params='{"spreadsheetId":"SHEET_ID","range":"Sheet1!A1:D10"}'
    Read values (helper):
      command="sheets +read --spreadsheet SHEET_ID --range Sheet1!A1:D10"
    Append a row (helper):
      command="sheets +append --spreadsheet SHEET_ID --range Sheet1 --values 'val1,val2,val3'"

    === SLIDES ===
    Get presentation:
      command="slides presentations get", params='{"presentationId":"PRES_ID"}'

    === TASKS ===
    List task lists:
      command="tasks tasklists list"
    List tasks:
      command="tasks tasks list", params='{"tasklist":"TASKLIST_ID"}'

    === WORKFLOW HELPERS ===
    Cross-service productivity helpers:
      command="workflow +standup-report"
      command="workflow +meeting-prep"
      command="workflow +weekly-digest"

    === FLAGS ===
    format: Override output format — "json" (default), "table", "yaml", "csv"
    output_file: Write binary/text output to this path (use "/dev/stdout" to capture export content)
    page_all: Auto-paginate through all results (for list operations with many pages)
    timeout: Command timeout in seconds (default 30, increase for large docs/exports)

    Args:
        command: The gws subcommand (e.g. "docs documents get" or "schema docs.documents.get")
        params: JSON string of query/path parameters (optional)
        body: JSON string of request body (optional). Used for create, update, modify operations.
        output_file: File path for binary/export output (optional). Use "/dev/stdout" to return
            content directly (essential for drive files export).
        format: Output format override (optional). One of: json, table, yaml, csv.
            Default is json. Use "table" or "yaml" for more readable output on complex responses.
        page_all: Auto-paginate through all results (default False). Useful for list operations.
        timeout: Command timeout in seconds (default 30, increase for large operations)

    Returns:
        Dictionary with status and the parsed JSON response, or result_text for non-JSON output.
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
        if output_file:
            cmd_parts.extend(["-o", output_file])
        if page_all:
            cmd_parts.append("--page-all")

        # Determine output format
        first_word = command.strip().split()[0] if command.strip() else ""
        if format:
            cmd_parts.extend(["--format", format])
        elif first_word not in ("schema", "auth"):
            cmd_parts.extend(["--format", "json"])

        # For export to /dev/stdout, capture stdout as binary-safe text
        r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            error_detail = r.stderr.strip() or r.stdout.strip() or f"Exit code {r.returncode}"
            return {"status": "error", "error_message": error_detail[:2000]}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        # If output_file was /dev/stdout, return the raw content as text
        if output_file == "/dev/stdout":
            return {"status": "ok", "result_text": output}

        # Try to parse as JSON; fall back to raw text (schema, table, yaml, csv output)
        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s. Try increasing the timeout parameter."}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def fetch_gmail_messages(
    message_ids: Optional[str] = None,
    q: Optional[str] = None,
    label: Optional[str] = None,
    headers: str = "Subject,From,Date",
    max_results: int = 20,
    include_snippet: bool = True,
    include_labels: bool = False,
) -> Dict[str, Any]:
    """
    Batch-fetch Gmail messages with configurable fields. Returns structured data
    for multiple messages in a single tool call.

    Simplest usage — just call with defaults to get your latest Primary inbox:
      fetch_gmail_messages()

    Filter by category or search:
      fetch_gmail_messages(q="category:primary is:unread")
      fetch_gmail_messages(q="from:boss@example.com after:2026/03/01")
      fetch_gmail_messages(q="category:updates", max_results=5)

    Filter by label:
      fetch_gmail_messages(label="INBOX")
      fetch_gmail_messages(label="STARRED")
      fetch_gmail_messages(label="IMPORTANT", q="is:unread")

    Fetch specific messages by ID:
      fetch_gmail_messages(message_ids="19ccab91bedfde8a,19cca54abd44ccb0")

    Customize returned fields — headers is a comma-separated list of email headers:
      fetch_gmail_messages(headers="Subject,From,To,Cc,Date,Reply-To")
      fetch_gmail_messages(headers="Subject,From", include_snippet=False)
      fetch_gmail_messages(headers="Subject,From,List-Unsubscribe", include_labels=True)

    Common header names: Subject, From, To, Cc, Bcc, Date, Reply-To, Message-ID,
      In-Reply-To, References, Content-Type, List-Unsubscribe, Delivered-To, X-Mailer

    Non-header fields controlled by flags:
      include_snippet (default True) — short preview text of the message body
      include_labels (default False) — Gmail label IDs like INBOX, UNREAD, CATEGORY_SOCIAL

    Args:
        message_ids: Comma-separated Gmail message IDs to fetch directly (skips listing)
        q: Gmail search query (e.g. "category:primary", "is:unread", "from:x@y.com")
        label: Gmail label to filter by (e.g. "INBOX", "STARRED", "IMPORTANT")
        headers: Comma-separated email header names to extract (default "Subject,From,Date")
        max_results: Maximum messages to list when using q/label (default 20, max 100)
        include_snippet: Include message snippet/preview text (default True)
        include_labels: Include Gmail label IDs on each message (default False)

    Returns:
        Dictionary with status, count, and messages list. Each message has id, threadId,
        and the requested headers as key-value pairs.
    """
    import json
    import subprocess
    import traceback

    try:
        ids_to_fetch = []

        if message_ids:
            ids_to_fetch = [mid.strip() for mid in message_ids.split(",") if mid.strip()]
        else:
            # Build list query
            list_params = {"userId": "me", "maxResults": min(max_results, 100)}
            if label:
                list_params["labelIds"] = label
            if q:
                list_params["q"] = q
            elif not label:
                list_params["q"] = "category:primary"

            r = subprocess.run(
                ["gws", "gmail", "users", "messages", "list",
                 "--params", json.dumps(list_params),
                 "--format", "json"],
                capture_output=True, text=True, timeout=30)

            if r.returncode != 0:
                error_detail = r.stderr.strip() or r.stdout.strip() or f"Exit code {r.returncode}"
                return {"status": "error", "error_message": error_detail[:1000]}

            list_result = json.loads(r.stdout) if r.stdout.strip() else {}
            ids_to_fetch = [m["id"] for m in list_result.get("messages", [])]

        if not ids_to_fetch:
            return {"status": "ok", "count": 0, "messages": []}

        header_names = [h.strip() for h in headers.split(",") if h.strip()]

        messages = []
        for mid in ids_to_fetch:
            get_params = {
                "userId": "me",
                "id": mid,
                "format": "metadata",
            }
            r = subprocess.run(
                ["gws", "gmail", "users", "messages", "get",
                 "--params", json.dumps(get_params),
                 "--format", "json"],
                capture_output=True, text=True, timeout=15)

            if r.returncode != 0:
                messages.append({"id": mid, "_error": "fetch failed"})
                continue

            msg_data = json.loads(r.stdout) if r.stdout.strip() else {}

            entry = {"id": mid, "threadId": msg_data.get("threadId", "")}

            # Extract requested headers
            msg_headers = msg_data.get("payload", {}).get("headers", [])
            header_map = {}
            for h in msg_headers:
                header_map[h["name"].lower()] = h["value"]
            for name in header_names:
                entry[name.lower()] = header_map.get(name.lower(), "")

            if include_snippet:
                entry["snippet"] = msg_data.get("snippet", "")
            if include_labels:
                entry["labelIds"] = msg_data.get("labelIds", [])

            messages.append(entry)

        return {"status": "ok", "count": len(messages), "messages": messages}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": "Operation timed out"}
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
