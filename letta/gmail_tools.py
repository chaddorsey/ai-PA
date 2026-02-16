"""
Gmail API Tools for Letta Agents

Provides direct Gmail API access via custom Letta tools for searching, reading,
sending, replying, drafting, labeling, and downloading attachments.

All functions follow the Letta tool pattern:
- Imports inside function body (after docstring)
- No nested def statements - all logic inlined
- Returns Dict[str, Any] with {"status": "ok", ...} or {"status": "error", "error_message": ...}
- Entire function body wrapped in try/except
- All parameters documented in Args: docstring section
- Only basic JSON types for parameters

Authentication:
- OAuth client keys: /root/.gmail-mcp/gcp-oauth.keys.json
- Token file: /root/.gmail-mcp/credentials.json (Node.js format)
- Scopes: gmail.modify, gmail.settings.basic
- Auto-refreshes expired tokens and persists new access_token
"""

from typing import Dict, Any, Optional


def search_emails(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Search Gmail messages using Gmail search syntax.

    Supports all Gmail search operators (from:, to:, subject:, has:attachment,
    after:, before:, label:, is:unread, etc.).

    Args:
        query: Gmail search query string (e.g. "from:alice@example.com subject:meeting is:unread")
        max_results: Maximum number of results to return (1-50, default 10)

    Returns:
        Dictionary with status, emails list, and count.
    """
    import json
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # Clamp max_results to valid range
        if max_results is None or max_results < 1:
            max_results = 10
        if max_results > 50:
            max_results = 50

        # --- Auth boilerplate ---
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

        # Search for messages
        results = gmail.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = results.get("messages", [])

        if not messages:
            return {"status": "ok", "emails": [], "count": 0, "query": query}

        # Fetch metadata for each message
        emails = []
        for msg in messages:
            msg_data = gmail.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "To", "Date"],
            ).execute()

            headers = msg_data.get("payload", {}).get("headers", [])
            header_map = {}
            for h in headers:
                header_map[h["name"].lower()] = h["value"]

            emails.append({
                "id": msg_data["id"],
                "threadId": msg_data.get("threadId", ""),
                "subject": header_map.get("subject", ""),
                "from": header_map.get("from", ""),
                "to": header_map.get("to", ""),
                "date": header_map.get("date", ""),
                "snippet": msg_data.get("snippet", ""),
                "labelIds": msg_data.get("labelIds", []),
            })

        return {"status": "ok", "emails": emails, "count": len(emails), "query": query}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def read_email(message_id: str) -> Dict[str, Any]:
    """
    Read a single email message with full body content.

    Retrieves the complete email including decoded body text, headers,
    and attachment metadata. Prefers text/plain body; falls back to text/html.

    Args:
        message_id: Gmail message ID (from search_emails or other tools)

    Returns:
        Dictionary with status, email details including decoded body and attachment list.
    """
    import json
    import base64
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        msg = gmail.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        # Extract headers
        headers = msg.get("payload", {}).get("headers", [])
        header_map = {}
        for h in headers:
            header_map[h["name"].lower()] = h["value"]

        # Extract body by walking MIME parts using a stack (no nested def)
        plain_body = ""
        html_body = ""
        attachments = []

        stack = [msg.get("payload", {})]
        while stack:
            part = stack.pop()
            mime_type = part.get("mimeType", "")
            filename = part.get("filename", "")
            body_data = part.get("body", {})
            parts = part.get("parts", [])

            # If this part has sub-parts, push them onto the stack
            if parts:
                stack.extend(parts)
                continue

            # Check for attachment (has filename and attachmentId)
            attachment_id = body_data.get("attachmentId", "")
            if filename and attachment_id:
                attachments.append({
                    "attachmentId": attachment_id,
                    "filename": filename,
                    "mimeType": mime_type,
                    "size": body_data.get("size", 0),
                })
                continue

            # Extract body text
            data = body_data.get("data", "")
            if not data:
                continue

            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

            if mime_type == "text/plain" and not plain_body:
                plain_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded

        body = plain_body if plain_body else html_body

        return {
            "status": "ok",
            "id": msg["id"],
            "threadId": msg.get("threadId", ""),
            "subject": header_map.get("subject", ""),
            "from": header_map.get("from", ""),
            "to": header_map.get("to", ""),
            "cc": header_map.get("cc", ""),
            "date": header_map.get("date", ""),
            "body": body,
            "attachments": attachments,
            "labelIds": msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def get_email_thread(thread_id: str) -> Dict[str, Any]:
    """
    Retrieve all messages in an email thread.

    Returns the thread with metadata for each message, useful for understanding
    conversation context without fetching full bodies.

    Args:
        thread_id: Gmail thread ID (from search_emails or read_email)

    Returns:
        Dictionary with status, thread metadata, and list of message summaries.
    """
    import json
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        thread = gmail.users().threads().get(
            userId="me",
            id=thread_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date"],
        ).execute()

        thread_messages = thread.get("messages", [])

        # Extract subject from first message
        thread_subject = ""
        messages = []
        for msg in thread_messages:
            headers = msg.get("payload", {}).get("headers", [])
            header_map = {}
            for h in headers:
                header_map[h["name"].lower()] = h["value"]

            if not thread_subject:
                thread_subject = header_map.get("subject", "")

            messages.append({
                "id": msg["id"],
                "from": header_map.get("from", ""),
                "to": header_map.get("to", ""),
                "date": header_map.get("date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return {
            "status": "ok",
            "threadId": thread_id,
            "subject": thread_subject,
            "message_count": len(messages),
            "messages": messages,
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an email message.

    Composes and sends an email. Supports plain text and optional HTML body.
    Multiple recipients can be specified as comma-separated email addresses.

    Args:
        to: Recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Plain text body of the email
        cc: CC recipient(s), comma-separated (optional)
        bcc: BCC recipient(s), comma-separated (optional)
        html_body: HTML version of the body for rich formatting (optional)

    Returns:
        Dictionary with status and sent message details (id, threadId, labelIds).
    """
    import json
    import base64
    import traceback
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        # Build MIME message
        if html_body:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain"))
            message.attach(MIMEText(html_body, "html"))
        else:
            message = MIMEText(body, "plain")

        message["To"] = to
        message["Subject"] = subject

        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc

        # Encode and send
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = gmail.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return {
            "status": "ok",
            "id": sent.get("id", ""),
            "threadId": sent.get("threadId", ""),
            "labelIds": sent.get("labelIds", []),
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def reply_to_email(
    message_id: str,
    body: str,
    reply_all: bool = False,
    html_body: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reply to an existing email message.

    Fetches the original message to construct a proper reply with correct
    threading headers (In-Reply-To, References). Supports reply and reply-all.

    Args:
        message_id: Gmail message ID of the email to reply to
        body: Plain text body of the reply
        reply_all: If True, reply to all original recipients (default False)
        html_body: HTML version of the reply body (optional)

    Returns:
        Dictionary with status and sent reply details (id, threadId, labelIds).
    """
    import json
    import base64
    import traceback
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        # Fetch original message for threading headers
        original = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Cc", "Message-ID", "References"],
        ).execute()

        orig_headers = original.get("payload", {}).get("headers", [])
        orig_header_map = {}
        for h in orig_headers:
            orig_header_map[h["name"].lower()] = h["value"]

        orig_subject = orig_header_map.get("subject", "")
        orig_from = orig_header_map.get("from", "")
        orig_to = orig_header_map.get("to", "")
        orig_cc = orig_header_map.get("cc", "")
        orig_message_id = orig_header_map.get("message-id", "")
        orig_references = orig_header_map.get("references", "")
        thread_id = original.get("threadId", "")

        # Build reply subject
        reply_subject = orig_subject
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        # Determine recipients
        reply_to = orig_from
        reply_cc = ""

        if reply_all:
            # Get our own email to exclude from recipients
            profile = gmail.users().getProfile(userId="me").execute()
            my_email = profile.get("emailAddress", "").lower()

            # Combine original To and Cc, excluding ourselves
            all_recipients = []
            for addr in (orig_to + "," + orig_cc).split(","):
                addr = addr.strip()
                if addr and my_email not in addr.lower():
                    all_recipients.append(addr)

            # Original sender is the To, remaining go to Cc
            if all_recipients:
                reply_cc = ", ".join(all_recipients)

        # Build MIME message
        if html_body:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain"))
            message.attach(MIMEText(html_body, "html"))
        else:
            message = MIMEText(body, "plain")

        message["To"] = reply_to
        message["Subject"] = reply_subject

        if reply_cc:
            message["Cc"] = reply_cc

        # Threading headers
        if orig_message_id:
            message["In-Reply-To"] = orig_message_id
            if orig_references:
                message["References"] = f"{orig_references} {orig_message_id}"
            else:
                message["References"] = orig_message_id

        # Encode and send with threadId
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = gmail.users().messages().send(
            userId="me", body={"raw": raw, "threadId": thread_id}
        ).execute()

        return {
            "status": "ok",
            "id": sent.get("id", ""),
            "threadId": sent.get("threadId", ""),
            "labelIds": sent.get("labelIds", []),
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def draft_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a draft email without sending it.

    Composes a draft that appears in the Gmail Drafts folder. The user can
    review and send it manually later. Supports plain text and HTML bodies.

    Args:
        to: Recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Plain text body of the email
        cc: CC recipient(s), comma-separated (optional)
        bcc: BCC recipient(s), comma-separated (optional)
        html_body: HTML version of the body for rich formatting (optional)

    Returns:
        Dictionary with status, draft_id, message_id, and threadId.
    """
    import json
    import base64
    import traceback
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        # Build MIME message
        if html_body:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain"))
            message.attach(MIMEText(html_body, "html"))
        else:
            message = MIMEText(body, "plain")

        message["To"] = to
        message["Subject"] = subject

        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc

        # Encode and create draft
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft = gmail.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()

        draft_message = draft.get("message", {})

        return {
            "status": "ok",
            "draft_id": draft.get("id", ""),
            "message_id": draft_message.get("id", ""),
            "threadId": draft_message.get("threadId", ""),
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def modify_email(
    message_id: str,
    add_labels: Optional[str] = None,
    remove_labels: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Modify labels on an email message.

    Adds and/or removes labels from a message. Supports convenient shortcuts
    for common operations like marking read/unread, archiving, starring, etc.

    Shortcuts (case-insensitive):
      "read"        -> removes UNREAD
      "unread"      -> adds UNREAD
      "archive"     -> removes INBOX
      "unarchive"   -> adds INBOX
      "star"        -> adds STARRED
      "unstar"      -> removes STARRED
      "trash"       -> adds TRASH
      "untrash"     -> removes TRASH
      "important"   -> adds IMPORTANT
      "unimportant" -> removes IMPORTANT
      "spam"        -> adds SPAM
      "not_spam"    -> removes SPAM

    Any value not matching a shortcut is passed as a literal label ID.

    Args:
        message_id: Gmail message ID to modify
        add_labels: Comma-separated label IDs or shortcut names to add (optional)
        remove_labels: Comma-separated label IDs or shortcut names to remove (optional)

    Returns:
        Dictionary with status, message id, and updated labelIds.
    """
    import json
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        # Shortcut mappings: shortcut -> (add_label_id, remove_label_id)
        # Each shortcut resolves to either an add or remove of a system label
        SHORTCUTS_ADD = {
            "unread": "UNREAD",
            "unarchive": "INBOX",
            "star": "STARRED",
            "trash": "TRASH",
            "important": "IMPORTANT",
            "spam": "SPAM",
        }
        SHORTCUTS_REMOVE = {
            "read": "UNREAD",
            "archive": "INBOX",
            "unstar": "STARRED",
            "untrash": "TRASH",
            "unimportant": "IMPORTANT",
            "not_spam": "SPAM",
        }

        final_add = []
        final_remove = []

        # Process add_labels
        if add_labels:
            for label in add_labels.split(","):
                label = label.strip()
                if not label:
                    continue
                label_lower = label.lower()
                if label_lower in SHORTCUTS_ADD:
                    final_add.append(SHORTCUTS_ADD[label_lower])
                elif label_lower in SHORTCUTS_REMOVE:
                    # Shortcut that implies a remove, even though it was in add_labels
                    final_remove.append(SHORTCUTS_REMOVE[label_lower])
                else:
                    final_add.append(label)

        # Process remove_labels
        if remove_labels:
            for label in remove_labels.split(","):
                label = label.strip()
                if not label:
                    continue
                label_lower = label.lower()
                if label_lower in SHORTCUTS_REMOVE:
                    final_remove.append(SHORTCUTS_REMOVE[label_lower])
                elif label_lower in SHORTCUTS_ADD:
                    # Shortcut that implies an add, even though it was in remove_labels
                    final_add.append(SHORTCUTS_ADD[label_lower])
                else:
                    final_remove.append(label)

        if not final_add and not final_remove:
            return {
                "status": "error",
                "error_message": "At least one of add_labels or remove_labels must be specified with valid values.",
            }

        modify_body = {}
        if final_add:
            modify_body["addLabelIds"] = list(set(final_add))
        if final_remove:
            modify_body["removeLabelIds"] = list(set(final_remove))

        result = gmail.users().messages().modify(
            userId="me", id=message_id, body=modify_body
        ).execute()

        return {
            "status": "ok",
            "id": result.get("id", ""),
            "labelIds": result.get("labelIds", []),
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def list_labels() -> Dict[str, Any]:
    """
    List all Gmail labels for the authenticated account.

    Returns system labels (INBOX, SENT, TRASH, etc.) and user-created labels
    with message counts. Sorted alphabetically by name.

    Returns:
        Dictionary with status, labels list (id, name, type, messagesTotal, messagesUnread), and count.
    """
    import json
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        results = gmail.users().labels().list(userId="me").execute()
        raw_labels = results.get("labels", [])

        # Fetch detailed info for each label (list only returns id, name, type)
        labels = []
        for lbl in raw_labels:
            label_detail = gmail.users().labels().get(
                userId="me", id=lbl["id"]
            ).execute()
            labels.append({
                "id": label_detail.get("id", ""),
                "name": label_detail.get("name", ""),
                "type": label_detail.get("type", ""),
                "messagesTotal": label_detail.get("messagesTotal", 0),
                "messagesUnread": label_detail.get("messagesUnread", 0),
            })

        # Sort by name
        labels.sort(key=lambda x: x["name"].lower())

        return {"status": "ok", "labels": labels, "count": len(labels)}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


def download_attachment(message_id: str, attachment_id: str) -> Dict[str, Any]:
    """
    Download an email attachment by its attachment ID.

    Retrieves the raw attachment data as a base64 string along with filename
    and MIME type metadata. Use read_email first to discover attachment IDs.

    Args:
        message_id: Gmail message ID that contains the attachment
        attachment_id: Attachment ID from the read_email attachments list

    Returns:
        Dictionary with status, attachment_id, filename, mime_type, size, and data_base64.
    """
    import json
    import base64
    import traceback
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        # --- Auth boilerplate ---
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

        # Fetch the attachment data
        att = gmail.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()

        att_data = att.get("data", "")
        att_size = att.get("size", 0)

        # Fetch the message to find the filename and mimeType for this attachment
        msg = gmail.users().messages().get(
            userId="me", id=message_id, format="metadata"
        ).execute()

        # Walk parts to find the matching attachment metadata
        filename = ""
        mime_type = ""

        # Re-fetch with full format to get parts structure
        msg_full = gmail.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        stack = [msg_full.get("payload", {})]
        while stack:
            part = stack.pop()
            parts = part.get("parts", [])
            if parts:
                stack.extend(parts)
                continue

            body = part.get("body", {})
            if body.get("attachmentId") == attachment_id:
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                break

        # The data from the API is already base64url-encoded; convert to standard base64
        # for easier consumption by downstream tools
        if att_data:
            raw_bytes = base64.urlsafe_b64decode(att_data)
            data_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        else:
            data_b64 = ""

        return {
            "status": "ok",
            "attachment_id": attachment_id,
            "filename": filename,
            "mime_type": mime_type,
            "size": att_size,
            "data_base64": data_b64,
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
