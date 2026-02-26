"""
Meeting Follow-up Tool for Letta

Creates a D/NA (Decisions / Next Actions) Gmail draft from meeting notes.
Task extraction is handled by scan_meeting_notes (upstream).

Tool: prepare_meeting_followup
"""

from typing import Dict, Any, Optional


def prepare_meeting_followup(
    meeting_id: str,
    meeting_title: str,
    meeting_date: str,
    participants: str,
    decisions: Optional[str] = None,
    my_actions: Optional[str] = None,
    their_actions: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a follow-up email draft with Decisions and Next Actions from a meeting.

    Formats all action items into a structured D/NA email and creates a Gmail draft.
    The email is created as a DRAFT — the user reviews and sends manually.

    Task extraction is handled upstream by scan_meeting_notes, which calls
    add_extracted_tasks directly for each [c] marker.

    Args:
        meeting_id: Granola meeting UUID for reference linking.
        meeting_title: Display title of the meeting (used in email subject).
        meeting_date: Meeting date as YYYY-MM-DD string.
        participants: Comma-separated participant entries, each as "Name <email>"
            (e.g. "Rebecca Ellis <rellis@concord.org>, Amy Pallant <apallant@concord.org>").
        decisions: Pipe-separated list of key decisions made. Decisions are rare
            and must be high-confidence: explicitly marked with "D:" or "Decision:" in
            user notes, or clearly stated as a decision in meeting context. Progress
            updates and status items are NOT decisions. Omit if none identified.
        my_actions: Pipe-separated list of personal action items
            (e.g. "Send budget to finance|Review one-pager by Friday").
            Omit if no personal actions identified.
        their_actions: Pipe-separated list of others' action items as complete sentences
            (e.g. "AJ to send budget|Rebecca to contact Rose"). Each item already contains
            the assignee name. Omit if no actions for others identified.

    Returns:
        Dictionary with status, draft_id, and email details.
    """
    import re
    import json
    import base64
    import traceback
    from datetime import datetime
    from email.mime.text import MIMEText
    import pytz
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)

        # ── Parse participants ──
        SENDER_EMAIL = "cdorsey@concord.org"
        participant_list = []
        emails_list = []
        EMAIL_RE = re.compile(r"<([^>]+@[^>]+)>")
        NAME_RE = re.compile(r"^([^<]+)")
        for entry in (participants or "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            email_match = EMAIL_RE.search(entry)
            name_match = NAME_RE.match(entry)
            email = email_match.group(1) if email_match else ""
            name = name_match.group(1).strip() if name_match else entry
            participant_list.append({"name": name, "email": email})
            # Exclude sender from recipients
            if email and email.lower() != SENDER_EMAIL:
                emails_list.append(email)

        # ── Parse action items (pipe-separated) ──
        decision_list = [d.strip() for d in (decisions or "").split("|") if d.strip()]
        my_action_list = [a.strip() for a in (my_actions or "").split("|") if a.strip()]

        # Parse their_actions: entries are already complete sentences
        # like "AJ to send..." — use as-is, no name prefix needed
        their_action_list = [a.strip() for a in (their_actions or "").split("|") if a.strip()]

        # ── Format email body as HTML ──
        # Time-aware opening: "this morning" / "this afternoon" / "today"
        try:
            meeting_hour = int(meeting_date.split(" ")[1].split(":")[0]) if " " in meeting_date else -1
        except (ValueError, IndexError):
            meeting_hour = -1
        if 0 <= meeting_hour < 12:
            time_phrase = "this morning"
        elif 12 <= meeting_hour < 17:
            time_phrase = "this afternoon"
        else:
            time_phrase = "today"

        html_parts = []
        html_parts.append("<p>Folks,</p>")
        html_parts.append(
            f"<p>Thanks for a great meeting {time_phrase}. I&#39;ve summarized "
            "below the decisions and next actions I captured. Please let me know "
            "if your notes differ from mine.</p>"
        )
        html_parts.append("<p>--Chad</p>")
        html_parts.append("<p>=====</p>")
        html_parts.append("<p><b>Decisions / Next Actions</b></p>")

        # Build decision bullet items (italic "Decision" prefix)
        decision_items = []
        for d in decision_list:
            cap_d = d[0].upper() + d[1:] if d else d
            decision_items.append(f"<li><i>Decision</i> &#8211; {cap_d}</li>")

        # Build action bullet items ("Name to verb..." format)
        action_items = []
        for a in my_action_list:
            if not a:
                continue
            a_lower = a.lower()
            if a_lower.startswith("chad to ") or a_lower.startswith("chad: "):
                action_items.append(f"<li>{a}</li>")
            else:
                action_items.append(f"<li>Chad to {a[0].lower()}{a[1:]}</li>")

        for a in their_action_list:
            if a:
                action_items.append(f"<li>{a}</li>")

        # Assemble bullet lists with blank line between decisions and actions
        if decision_items and action_items:
            html_parts.append("<ul>" + "".join(decision_items) + "</ul>")
            html_parts.append("<br>")
            html_parts.append("<ul>" + "".join(action_items) + "</ul>")
        elif decision_items:
            html_parts.append("<ul>" + "".join(decision_items) + "</ul>")
        elif action_items:
            html_parts.append("<ul>" + "".join(action_items) + "</ul>")

        body_html = "".join(html_parts)

        # ── Create Gmail draft ──
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

        message = MIMEText(body_html, "html")
        message["To"] = ", ".join(emails_list)
        subject = f"{meeting_title} - meeting summary"
        message["Subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft = gmail.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()

        draft_id = draft.get("id", "")
        draft_message = draft.get("message", {})

        return {
            "status": "ok",
            "draft_id": draft_id,
            "message_id": draft_message.get("id", ""),
            "thread_id": draft_message.get("threadId", ""),
            "email_to": ", ".join(emails_list),
            "email_subject": subject,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
