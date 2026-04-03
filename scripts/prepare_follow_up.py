#!/usr/bin/env python3
"""Prepare follow-ups and time tracking records from completion events.

Called by the host bridge on every timer.stopped / timer.auto-stopped event.
Reads the completion record from stdin (JSON), performs two actions:

1. ALWAYS: Write a time-tracking archival passage (for ALL tasks)
2. IF ref_id exists: Check archival for source context, prepare follow-up if external

Zero LLM cost — all logic is deterministic (regex parsing, API lookups, templates).

Usage:
    echo '{"taskId":"...","taskName":"...","refId":"abc123",...}' | python3 prepare_follow_up.py
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime

LETTA_URL = os.environ.get("LETTA_URL", "http://localhost:8283")
# Tasks agent owns the shared archive with ref_id passages
TASKS_AGENT_ID = "agent-dd15479e-6543-400e-8463-b2a48b13cd4a"
ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
MC_AGENT_ID = os.environ.get("MC_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef")
FOLLOWUP_QUEUE = os.environ.get(
    "FOLLOWUP_QUEUE",
    os.path.join(os.environ.get("TIMER_LOG_DIR", "/tmp"), "pending-followups.jsonl"),
)
USER_NAME = "Chad Dorsey"


def log(msg):
    print(f"[follow-up] {msg}", flush=True)


def letta_get(path):
    """GET from Letta API."""
    req = urllib.request.Request(f"{LETTA_URL}{path}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def letta_post(path, data):
    """POST to Letta API."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{LETTA_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def format_duration(ms):
    """Format milliseconds as human-readable duration."""
    if not ms:
        return "0s"
    total_sec = round(ms / 1000)
    if total_sec < 60:
        return f"{total_sec}s"
    mins = total_sec // 60
    secs = total_sec % 60
    if mins < 60:
        return f"{mins}m {secs:02d}s"
    hours = mins // 60
    m = mins % 60
    return f"{hours}h {m:02d}m {secs:02d}s"


def write_time_tracking_passage(event):
    """Write a time-tracking archival passage for any completed task."""
    task_name = event.get("taskName", "Unknown")
    task_id = event.get("taskId", "")
    ref_id = event.get("refId") or "none"
    project = event.get("projectName") or "none"
    session_ms = event.get("sessionMs") or event.get("totalMs") or 0
    total_ms = event.get("totalMs") or session_ms
    estimate_min = event.get("originalEstimateMin")
    agent_est_min = event.get("agentEstimateMin")
    completed_at = event.get("completedAt", datetime.utcnow().isoformat())

    # Calculate variance
    variance_str = "n/a"
    if estimate_min and estimate_min > 0:
        actual_min = total_ms / 60000
        diff = actual_min - estimate_min
        pct = round((diff / estimate_min) * 100)
        sign = "+" if diff >= 0 else ""
        direction = "over" if diff >= 0 else "under"
        variance_str = f"{sign}{pct}% ({direction} estimate)"

    passage = (
        f"COMPLETION: {task_name}\n"
        f"TASK_ID: {task_id}\n"
        f"REF_ID: {ref_id}\n"
        f"PROJECT: {project}\n"
        f"SESSION: {format_duration(session_ms)}\n"
        f"TOTAL: {format_duration(total_ms)}\n"
        f"ESTIMATE: {estimate_min} min\n"
        f"AGENT_ESTIMATE: {agent_est_min} min\n"
        f"VARIANCE: {variance_str}\n"
        f"COMPLETED: {completed_at}"
    )

    try:
        letta_post(f"/v1/archives/{ARCHIVE_ID}/passages", {"text": passage})
        log(f"Time tracking passage written for {task_name} ({task_id})")
    except Exception as e:
        log(f"Failed to write time tracking passage: {e}")


def find_archival_passage(ref_id):
    """Search for the task's archival passage by ref_id."""
    try:
        results = letta_get(
            f"/v1/agents/{TASKS_AGENT_ID}/archival-memory?search={ref_id}&limit=10"
        )
        for p in results:
            text = p.get("text", "")
            if f"REF_ID: {ref_id}" in text:
                return text
    except Exception as e:
        log(f"Archival search failed: {e}")
    return None


def parse_passage_fields(text):
    """Extract structured fields from an archival passage."""
    patterns = {
        "task_description": r"^TASK: (.+)$",
        "source_type": r"^- Type: (.+)$",
        "source_context": r"^- Context: (.+)$",
        "reference_id": r"^- Reference ID: (.+)$",
        "from_person": r"^- From: (.+)$",
        "location": r"^- Location: (.+)$",
        "location_id": r"^- Location ID: (.+)$",
        "omnifocus_status": r"^- Status: (.+)$",
    }
    fields = {}
    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.MULTILINE)
        fields[key] = m.group(1).strip() if m else ""

    # Extract source text
    source_match = re.search(r"SOURCE TEXT\n(.*)", text, re.DOTALL)
    fields["source_text"] = source_match.group(1).strip() if source_match else ""

    return fields


def _resolve_first_name(from_raw):
    """Extract first name from 'Name (USERID)' or resolve bare user IDs."""
    if not from_raw:
        return "there"
    # Bare user ID pattern (e.g., U02V91KU8)
    if re.match(r'^U[A-Z0-9]{6,12}$', from_raw):
        resolved = _resolve_slack_name(from_raw)
        return resolved or "there"
    # Strip parenthetical user ID: "Cynthia McIntyre (U09DXRLAH)" → "Cynthia"
    name_part = re.sub(r'\s*\([A-Z0-9]+\)\s*$', '', from_raw).strip()
    return name_part.split()[0] if name_part else "there"


def _resolve_slack_name(user_id):
    """Look up a Slack user's first name via the API."""
    try:
        token = os.environ.get("SLACK_BOT_TOKEN", "")
        if not token:
            return None
        req = urllib.request.Request(
            f"https://slack.com/api/users.info?user={user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                profile = data["user"].get("profile", {})
                return profile.get("first_name") or data["user"].get("real_name", "").split()[0]
    except Exception:
        pass
    return None


def prepare_slack_followup(ref_id, fields, event):
    """Prepare a Slack thread reply follow-up."""
    reference_id = fields["reference_id"]
    slack_match = re.match(r"slack-([A-Z0-9]+)-([\d.]+?)(?:-t([\d.]+))?$", reference_id)
    if not slack_match:
        log(f"Could not parse Slack reference_id: {reference_id}")
        return None

    channel_id = slack_match.group(1)
    message_ts = slack_match.group(2)
    thread_ts = slack_match.group(3) or message_ts

    first_name = _resolve_first_name(fields["from_person"])
    task_desc = re.sub(r"^\[(COMPLETED|DROPPED)\]\s*", "", fields["task_description"])

    return {
        "id": f"fu-{ref_id}",
        "type": "slack",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ref_id": ref_id,
        "task_description": task_desc,
        "from_person": fields["from_person"],
        "source_context": fields.get("source_context", ""),
        "location": fields.get("location", ""),
        "draft_message": f"Done — {task_desc.lower()}. Thanks, {first_name}!",
        "source_text": fields.get("source_text", ""),
        "routing": {
            "tool": "post_slack_channel_reply",
            "channel": channel_id,
            "thread_ts": thread_ts,
        },
        "editable": True,
    }


def prepare_docs_followup(ref_id, fields, event):
    """Prepare a Google Docs comment reply follow-up."""
    reference_id = fields["reference_id"]
    comment_match = re.match(r"gdocs-comment-(.+)-([A-Za-z0-9_]+)$", reference_id)
    if not comment_match:
        log(f"Could not parse Docs reference_id: {reference_id}")
        return None

    file_id = comment_match.group(1)
    comment_id = comment_match.group(2)

    first_name = _resolve_first_name(fields["from_person"])
    task_desc = re.sub(r"^\[(COMPLETED|DROPPED)\]\s*", "", fields["task_description"])
    is_self = USER_NAME in fields.get("from_person", "")

    if is_self:
        draft_msg = "Done."
    else:
        draft_msg = f"Done — {task_desc.lower()}. Thanks, {first_name}!"

    # For self-originated comments, note that in the follow-up
    is_self_comment = is_self

    return {
        "id": f"fu-{ref_id}",
        "type": "docs_comment",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ref_id": ref_id,
        "task_description": task_desc,
        "from_person": fields["from_person"],
        "source_context": fields.get("source_context", ""),
        "draft_message": draft_msg,
        "source_text": fields.get("source_text", ""),
        "self_originated": is_self_comment,
        "routing": {
            "tool": "run_gws",
            "reply_command": "drive replies create",
            "reply_params": {"fileId": file_id, "commentId": comment_id},
            "resolve_command": "drive comments update",
            "resolve_params": {"fileId": file_id, "commentId": comment_id},
        },
        "resolve_after_reply": True,
        "editable": True,
    }


def prepare_email_followup(ref_id, fields, event):
    """Prepare an email reply follow-up."""
    reference_id = fields["reference_id"]
    email_match = re.match(r"email-(.+)$", reference_id)
    if not email_match:
        log(f"Could not parse email reference_id: {reference_id}")
        return None

    first_name = _resolve_first_name(fields["from_person"])
    task_desc = re.sub(r"^\[(COMPLETED|DROPPED)\]\s*", "", fields["task_description"])

    return {
        "id": f"fu-{ref_id}",
        "type": "email",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ref_id": ref_id,
        "task_description": task_desc,
        "from_person": fields["from_person"],
        "source_context": fields.get("source_context", ""),
        "draft_message": f"Done — {task_desc.lower()}. Thanks, {first_name}!",
        "source_text": fields.get("source_text", ""),
        "routing": {
            "tool": "gmail_draft_reply",
            "message_id": email_match.group(1),
        },
        "editable": True,
    }


def write_followup(followup):
    """Append a follow-up to the pending queue."""
    line = json.dumps(followup) + "\n"
    with open(FOLLOWUP_QUEUE, "a") as f:
        f.write(line)
    log(f"Follow-up queued: {followup['type']} for {followup['from_person']} ({followup['ref_id']})")

    # Log to task-lifecycle.jsonl
    try:
        lifecycle_path = os.path.join(os.path.dirname(FOLLOWUP_QUEUE), "task-lifecycle.jsonl")
        entry = {
            "event": "followup_created",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "followup_id": followup.get("id"),
            "ref_id": followup.get("ref_id"),
            "type": followup.get("type"),
            "from_person": followup.get("from_person"),
        }
        with open(lifecycle_path, "a") as lf:
            lf.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def main():
    # Read completion event from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        log("No input")
        return

    try:
        event = json.loads(raw)
    except json.JSONDecodeError as e:
        log(f"Invalid JSON: {e}")
        return

    task_name = event.get("taskName", "?")
    ref_id = event.get("refId")

    # 1. ALWAYS: Write time-tracking archival passage
    write_time_tracking_passage(event)

    # 2. IF ref_id: Check for follow-up
    if not ref_id:
        log(f"No ref_id for '{task_name}' — time tracking only")
        return

    # Check if event data includes pre-resolved fields (from sync service)
    # These override archival lookup since the passage may already be replaced
    if event.get("fromPerson") and event.get("sourceType"):
        fields = {
            "source_type": event["sourceType"],
            "from_person": event["fromPerson"],
            "reference_id": event.get("referenceId", ""),
            "task_description": event.get("taskName", ""),
            "location": event.get("location", ""),
            "source_text": event.get("sourceText", ""),
            "source_context": event.get("sourceContext", ""),
        }
        log(f"Using pre-resolved fields from event data for {ref_id}")
    else:
        # Look up the archival passage
        passage = find_archival_passage(ref_id)
        if not passage:
            log(f"No archival passage for ref_id {ref_id}")
            return
        fields = parse_passage_fields(passage)

    source_type = fields.get("source_type", "")
    from_person = fields.get("from_person", "")

    # Check if follow-up is appropriate
    is_self = not from_person or USER_NAME in from_person
    if is_self and source_type not in ("google-docs-comment", "google-drive-comment"):
        log(f"Task from self — no follow-up needed for {ref_id}")
        return
    if is_self:
        # Self-originated Docs comment — still create follow-up to resolve the comment
        log(f"Self-originated docs comment — creating resolve follow-up for {ref_id}")

    # Route by source type
    followup = None
    if source_type == "slack":
        followup = prepare_slack_followup(ref_id, fields, event)
    elif source_type in ("google-docs-comment", "google-drive-comment"):
        followup = prepare_docs_followup(ref_id, fields, event)
    elif source_type == "email":
        followup = prepare_email_followup(ref_id, fields, event)
    else:
        log(f"Unknown source_type '{source_type}' for {ref_id} — no follow-up")
        return

    if followup:
        write_followup(followup)


if __name__ == "__main__":
    main()
