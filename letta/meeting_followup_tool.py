"""
Meeting Follow-up Tool for Letta

Creates a D/NA (Decisions / Next Actions) Gmail draft from meeting notes
and queues personal action items to the queued_tasks_from_meetings block
for downstream task extraction.

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
    Also queues personal tasks (my_actions) to the queued_tasks_from_meetings block
    for extraction into the task pipeline.

    The email is created as a DRAFT — the user reviews and sends manually.

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
        their_actions: Pipe-separated list of others' action items, each prefixed with
            assignee name and colon (e.g. "Rebecca: Create task list|Rebecca: Contact Rose").
            Omit if no actions for others identified.

    Returns:
        Dictionary with status, draft_id, tasks_queued count, and email details.
    """
    import os
    import re
    import json
    import base64
    import traceback
    from datetime import datetime
    from email.mime.text import MIMEText
    import pytz
    import urllib.request
    import urllib.error
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        QUEUE_BLOCK_LABEL = "queued_tasks_from_meetings"

        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)

        # ── Parse participants ──
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
            if email:
                emails_list.append(email)

        # ── Parse action items (pipe-separated) ──
        decision_list = [d.strip() for d in (decisions or "").split("|") if d.strip()]
        my_action_list = [a.strip() for a in (my_actions or "").split("|") if a.strip()]

        # Parse their_actions: "Name: action" format
        their_action_map = {}
        for entry in (their_actions or "").split("|"):
            entry = entry.strip()
            if not entry:
                continue
            colon_idx = entry.find(":")
            if colon_idx > 0:
                who = entry[:colon_idx].strip()
                action = entry[colon_idx + 1 :].strip()
            else:
                who = "TBD"
                action = entry
            if who not in their_action_map:
                their_action_map[who] = []
            their_action_map[who].append(action)

        # ── Format email body as HTML ──
        # Build participant first-name greeting
        first_names = [p["name"].split()[0] for p in participant_list if p["name"]]
        if len(first_names) == 1:
            greeting_names = first_names[0]
        elif len(first_names) == 2:
            greeting_names = f"{first_names[0]} and {first_names[1]}"
        elif first_names:
            greeting_names = ", ".join(first_names[:-1]) + f", and {first_names[-1]}"
        else:
            greeting_names = "all"

        html_parts = []
        html_parts.append(f"<p>{greeting_names},</p>")
        html_parts.append(
            "<p>I&#39;ve summarized below the decisions and next actions "
            "I captured. Please let me know if your notes differ from mine.</p>"
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

        for who, actions in sorted(their_action_map.items()):
            for a in actions:
                if not a:
                    continue
                a_lower = a.lower()
                if a_lower.startswith(f"{who.lower()} to "):
                    action_items.append(f"<li>{a}</li>")
                else:
                    action_items.append(f"<li>{who} to {a[0].lower()}{a[1:]}</li>")

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

        # ── Queue my_actions to queued_tasks_from_meetings block ──
        tasks_queued = 0
        if my_action_list and AGENT_ID:
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

            if queue_block:
                block_id = queue_block["id"]
                block_url = f"{LETTA_BASE}/v1/blocks/{block_id}"
                block_req = urllib.request.Request(block_url, method="GET")
                with urllib.request.urlopen(block_req, timeout=10) as resp:
                    block_data = json.loads(resp.read().decode("utf-8"))
                current_value = block_data.get("value", "").rstrip()

                entry_lines = [
                    f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] meeting_id: {meeting_id}",
                    f"title: {meeting_title}",
                    f"date: {meeting_date}",
                    f"participants: {', '.join(p['name'] for p in participant_list)}",
                    f"granola_link: https://notes.granola.ai/d/{meeting_id}",
                ]
                for action in my_action_list:
                    entry_lines.append(f"task: {action}")
                entry_text = "\n".join(entry_lines)

                updated = f"{current_value}\n{entry_text}\n---"
                update_data = json.dumps({"value": updated}).encode("utf-8")
                update_req = urllib.request.Request(
                    block_url,
                    data=update_data,
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                urllib.request.urlopen(update_req, timeout=10)
                tasks_queued = len(my_action_list)

        return {
            "status": "ok",
            "draft_id": draft_id,
            "message_id": draft_message.get("id", ""),
            "thread_id": draft_message.get("threadId", ""),
            "tasks_queued": tasks_queued,
            "email_to": ", ".join(emails_list),
            "email_subject": subject,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
