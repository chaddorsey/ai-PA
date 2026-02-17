# Email Task Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable forwarding Gmail messages to `cdorsey+tasks@concord.org` (or manually labeling) to queue them for task extraction by the email-agent, with near-real-time triggering via Gmail Watch.

**Architecture:** A Letta tool (`process_email_task_queue`) processes TaskQueue-labeled Gmail messages — parsing forwarded content, resolving original messages, and writing structured entries to the `queued_tasks_from_email` block. A lightweight Gmail Watch service detects new TaskQueue labels in near-real-time and triggers the email-agent via the existing `agent_message` pattern.

**Tech Stack:** Python, Gmail API (`google-api-python-client`), Google Cloud Pub/Sub, FastAPI, Letta API

**Key IDs:**
- Email-agent: `agent-b4928949-8012-4436-a3c7-a9e510785147`
- `queued_tasks_from_email` block: `block-e64dcb37-aae3-416f-8565-5f2a23f53325`
- Gmail credentials: `/root/.gmail-mcp/` (inside Letta container), `~/.gmail-mcp/` (host)

---

## Phase 1: Processing Pipeline

### Task 1: Create TaskQueue Gmail Label

**Files:**
- Create: `scripts/create_gmail_taskqueue_label.py`

This one-time script creates a `TaskQueue` label in Gmail and prints its label ID (needed for the Watch registration in Phase 2).

**Step 1: Write the setup script**

```python
#!/usr/bin/env python3
"""Create the TaskQueue Gmail label (one-time setup)."""
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDS_DIR = os.path.expanduser("~/.gmail-mcp")

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

# Check if label already exists
labels = gmail.users().labels().list(userId="me").execute().get("labels", [])
for lbl in labels:
    if lbl["name"] == "TaskQueue":
        print(f"TaskQueue label already exists: {lbl['id']}")
        sys.exit(0)

# Create label
result = gmail.users().labels().create(
    userId="me",
    body={
        "name": "TaskQueue",
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    },
).execute()

print(f"Created TaskQueue label: {result['id']}")
print(f"\nSave this label ID for Phase 2 Gmail Watch registration.")
```

**Step 2: Run the script**

```bash
python scripts/create_gmail_taskqueue_label.py
```

Expected: Prints the label ID (e.g., `Label_123456`). Save this ID — it's needed for the Watch registration.

**Step 3: Create Gmail filter (manual)**

In Gmail Settings → Filters → Create new filter:
- **To:** `cdorsey+tasks@concord.org`
- **Do this:** Apply label "TaskQueue", Skip Inbox
- **Also apply to matching conversations:** No (only new messages)

**Step 4: Verify plus-addressing works**

Send a test email to `cdorsey+tasks@concord.org` from another account. Confirm:
- Message arrives and gets the `TaskQueue` label
- Message skips the inbox (if Skip Inbox was set)

**Step 5: Commit**

```bash
git add scripts/create_gmail_taskqueue_label.py
git commit -m "feat: add TaskQueue Gmail label creation script"
```

---

### Task 2: Build `process_email_task_queue` Letta Tool

**Files:**
- Create: `letta/email_task_queue_tool.py`

This is the core processing pipeline. It searches for `label:TaskQueue` messages, parses forwarded content, resolves original messages, writes structured entries to the queue block, and removes the label.

**Step 1: Write the tool**

The tool follows all Letta tool patterns (see `context/coding_custom_letta_tools.md`):
- All imports inside function body
- No nested `def` statements
- Returns `Dict[str, Any]`
- Try-except wrapper
- Basic JSON parameter types

```python
from typing import Dict, Any, Optional

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
            scopes=["https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.settings.basic"],
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
            return {"status": "error", "error_message": "LETTA_AGENT_ID not set"}
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method='GET')
        with urllib.request.urlopen(agent_req, timeout=10) as resp:
            agent_data = json.loads(resp.read().decode('utf-8'))
        blocks = agent_data.get('memory', {}).get('blocks', [])
        queue_block = None
        for block in blocks:
            if block.get('label') == QUEUE_BLOCK_LABEL:
                queue_block = block
                break
        if not queue_block:
            return {
                "status": "error",
                "error_message": (
                    f"Block '{QUEUE_BLOCK_LABEL}' not found on this agent."
                ),
            }
        queue_block_id = queue_block['id']

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
                forward_match = FORWARD_DELIMITER.search(body)
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
                    f"[queued: {now.strftime('%Y-%m-%d %H:%M')}] "
                    f"message_id: {original_message_id} "
                    f"| thread_id: {original_thread_id}",
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
                block_req = urllib.request.Request(block_url, method='GET')
                with urllib.request.urlopen(block_req, timeout=10) as resp:
                    block_data = json.loads(resp.read().decode('utf-8'))
                current_value = block_data.get('value', '').rstrip()

                if current_value.endswith("Queue:"):
                    updated = f"{current_value}\n{entry_text}\n---"
                elif current_value:
                    updated = f"{current_value}\n{entry_text}\n---"
                else:
                    updated = entry_text + "\n---"

                update_data = json.dumps(
                    {"value": updated}
                ).encode('utf-8')
                update_req = urllib.request.Request(
                    block_url,
                    data=update_data,
                    headers={"Content-Type": "application/json"},
                    method='PATCH',
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
```

**Queue entry format** (written to `queued_tasks_from_email` block):

```
[queued: 2026-02-16 14:30] message_id: 19c63786ec4294ae | thread_id: 19c63786ec4294ae
subject: Budget review
from: Danielle Kehoe <dkehoe@concord.org>
date: Fri, Feb 14, 2026 at 3:22 PM
snippet: Hi Chad, could you review the budget line items...
gmail_link: https://mail.google.com/mail/u/0/#inbox/19c63786ec4294ae
trigger: forwarded
notes: Check the CODAP grant line items specifically
forwarded_message_id: 19c63abc12345678
---
```

**Step 2: Run quick syntax check**

```bash
python -c "from letta.email_task_queue_tool import process_email_task_queue; print('OK')"
```

**Step 3: Commit**

```bash
git add letta/email_task_queue_tool.py
git commit -m "feat: add process_email_task_queue Letta tool"
```

---

### Task 3: Register Tool and Attach to Email-Agent

**Files:**
- Create: `letta/register_email_task_queue_tool.py`

**Step 1: Write the registration script**

Pattern matches `letta/register_extracted_tasks_tool.py` and `letta/register_gmail_tools.py`.

```python
#!/usr/bin/env python3
"""Register process_email_task_queue tool with Letta."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

from email_task_queue_tool import process_email_task_queue

EMAIL_AGENT_ID = "agent-b4928949-8012-4436-a3c7-a9e510785147"

def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    # Check for existing tool
    for tool in client.tools.list():
        if tool.name == "process_email_task_queue":
            resp = input(f"Tool exists ({tool.id}). Re-register? [y/N]: ")
            if resp.lower() != 'y':
                return
            client.tools.delete(tool.id)
            print(f"Deleted {tool.id}")
            break

    # Register
    created = client.tools.create_from_function(
        func=process_email_task_queue,
        tags=["email", "task-queue", "gmail"],
    )
    print(f"Registered: {created.name} ({created.id})")

    # Attach to email-agent
    try:
        client.agents.tools.attach(agent_id=EMAIL_AGENT_ID, tool_id=created.id)
        print(f"Attached to email-agent ({EMAIL_AGENT_ID})")
    except Exception as e:
        print(f"Attach failed (may already be attached): {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
```

**Step 2: Run registration from host**

```bash
LETTA_BASE_URL=http://localhost:8283 python letta/register_email_task_queue_tool.py
```

Expected: Tool registered and attached to email-agent.

**Step 3: Verify tool appears on agent**

```bash
curl -s http://localhost:8283/v1/agents/agent-b4928949-8012-4436-a3c7-a9e510785147 | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print([t['name'] for t in d.get('tools',[])])"
```

Expected: `process_email_task_queue` appears in the tool list.

**Step 4: Commit**

```bash
git add letta/register_email_task_queue_tool.py
git commit -m "feat: add registration script for email task queue tool"
```

---

### Task 4: Update `queued_tasks_from_email` Block Header

**Target:** `block-e64dcb37-aae3-416f-8565-5f2a23f53325`

The block header already defines the entry format. Add a `notes:` field and `forwarded_message_id:` field to the format description, and mention the `process_email_task_queue` trigger.

**Step 1: Update block via Letta API**

```bash
curl -s http://localhost:8283/v1/blocks/block-e64dcb37-aae3-416f-8565-5f2a23f53325 | \
  python3 -c "import sys,json; print(json.loads(sys.stdin.read(), strict=False)['value'])"
```

Review the current value, then PATCH with the updated header that adds:
- `notes:` field (optional, from forwarded messages with user annotations)
- `forwarded_message_id:` field (optional, the forward's own message ID)
- `trigger:` values: `"TaskQueue"` (direct label) or `"forwarded"` (forward-to-self)
- Note that `process_email_task_queue` tool populates this block

**Step 2: Verify**

Re-read the block to confirm the header update took effect.

---

### Task 5: Manual E2E Test

**Prerequisite:** TaskQueue label exists (Task 1), tool registered (Task 3).

**Step 1: Create a test email with TaskQueue label**

Option A (forward test): Forward any email to `cdorsey+tasks@concord.org` with a note typed above the forwarded content.

Option B (direct label test): In Gmail, manually apply the `TaskQueue` label to any email.

**Step 2: Trigger the tool via Letta API**

```bash
curl -s -X POST http://localhost:8283/v1/agents/agent-b4928949-8012-4436-a3c7-a9e510785147/messages \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"system","content":"Call process_email_task_queue to check for new TaskQueue items."}]}'
```

**Step 3: Verify queue entry**

```bash
curl -s http://localhost:8283/v1/blocks/block-e64dcb37-aae3-416f-8565-5f2a23f53325 | \
  python3 -c "import sys,json; print(json.loads(sys.stdin.read(), strict=False)['value'])"
```

Expected: A new queue entry with the correct format, including `notes:` if forwarded.

**Step 4: Verify label removed**

In Gmail, confirm the test message no longer has the `TaskQueue` label.

**Step 5: Verify agent can process the queue**

Send another message to the email-agent asking it to process the queued items:

```bash
curl -s -X POST http://localhost:8283/v1/agents/agent-b4928949-8012-4436-a3c7-a9e510785147/messages \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Process any queued email tasks in queued_tasks_from_email."}]}'
```

Expected: Agent reads queue, calls `read_email` for full context, calls `add_extracted_tasks`, removes processed entries from block.

---

## Phase 2: Gmail Watch Trigger Service

### Overview

Gmail Watch sends push notifications via Google Cloud Pub/Sub when the TaskQueue label is added to a message. A lightweight FastAPI service receives these notifications and triggers the email-agent.

**Architecture:**

```
User forwards email
  → Gmail filter applies TaskQueue label
  → Gmail Watch detects label change
  → Google Pub/Sub pushes notification to gmail-watch-service
  → gmail-watch-service sends agent_message to email-agent
  → Email-agent calls process_email_task_queue
  → Tool processes messages, writes queue entries, removes labels
  → Email-agent extracts tasks from queue
```

**Prerequisites:**
- GCP project with Pub/Sub API enabled (same project as Gmail OAuth)
- Cloudflare tunnel route for the webhook endpoint
- TaskQueue label ID from Task 1

---

### Task 6: GCP Pub/Sub Infrastructure Setup

**This is a manual/CLI task** — not code to commit.

**Step 1: Enable Pub/Sub API**

In GCP Console → APIs & Services → Enable `Cloud Pub/Sub API` for the project.

**Step 2: Create Pub/Sub topic**

```bash
gcloud pubsub topics create gmail-task-notifications \
  --project=YOUR_GCP_PROJECT_ID
```

**Step 3: Grant Gmail API publish permission**

```bash
gcloud pubsub topics add-iam-policy-binding gmail-task-notifications \
  --project=YOUR_GCP_PROJECT_ID \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

**Step 4: Create push subscription**

The push endpoint URL will be the gmail-watch-service's webhook, exposed via Cloudflare tunnel. Determine the URL first (e.g., `https://gmail-watch.cd-ai-pa.work/webhook`), then:

```bash
gcloud pubsub subscriptions create gmail-watch-sub \
  --project=YOUR_GCP_PROJECT_ID \
  --topic=gmail-task-notifications \
  --push-endpoint=https://gmail-watch.cd-ai-pa.work/webhook \
  --ack-deadline=30
```

**Step 5: Note the full topic name**

Format: `projects/YOUR_GCP_PROJECT_ID/topics/gmail-task-notifications`

This goes into the Watch service's environment configuration.

---

### Task 7: Build `gmail-watch-service`

**Files:**
- Create: `gmail-watch-service/main.py`
- Create: `gmail-watch-service/Dockerfile`
- Create: `gmail-watch-service/requirements.txt`

**Step 1: Write `requirements.txt`**

```
fastapi>=0.104.0
uvicorn>=0.24.0
httpx>=0.25.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-httplib2>=0.1.0
```

**Step 2: Write `main.py`**

```python
"""Gmail Watch Service — triggers email-agent on TaskQueue label changes."""
import base64
import json
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as AuthRequest
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gmail-watch")

app = FastAPI(title="Gmail Watch Service")

# Configuration via environment
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
EMAIL_AGENT_ID = os.getenv(
    "EMAIL_AGENT_ID",
    "agent-b4928949-8012-4436-a3c7-a9e510785147",
)
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC")  # Full topic path
TASKQUEUE_LABEL_ID = os.getenv("TASKQUEUE_LABEL_ID")  # From Task 1
CREDS_DIR = os.getenv("GMAIL_CREDS_DIR", "/root/.gmail-mcp")


def get_gmail_service():
    """Build authenticated Gmail API service."""
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
        creds.refresh(AuthRequest())
        tokens["access_token"] = creds.token
        with open(f"{CREDS_DIR}/credentials.json", "w") as f:
            json.dump(tokens, f, indent=2)
    return build("gmail", "v1", credentials=creds)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gmail-watch"}


@app.post("/webhook")
async def pubsub_webhook(request: Request):
    """Receive Pub/Sub push notification from Gmail Watch."""
    try:
        envelope = await request.json()
        message = envelope.get("message", {})
        data_b64 = message.get("data", "")

        if data_b64:
            data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
            email_address = data.get("emailAddress", "")
            history_id = data.get("historyId", "")
            logger.info(
                "Gmail notification: email=%s historyId=%s",
                email_address,
                history_id,
            )

        # Trigger email-agent to process TaskQueue
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{LETTA_BASE_URL}/v1/agents/{EMAIL_AGENT_ID}/messages",
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Gmail Watch: new activity on TaskQueue label. "
                                "Call process_email_task_queue to check for "
                                "and process any new items."
                            ),
                        }
                    ]
                },
            )
            logger.info("Agent triggered: status=%d", resp.status_code)

    except Exception:
        logger.exception("Error processing webhook")

    # Always return 200 to acknowledge the Pub/Sub message
    # (prevents retries for transient processing errors)
    return Response(status_code=200)


@app.post("/watch/register")
async def register_watch():
    """Register or renew Gmail Watch on TaskQueue label."""
    if not PUBSUB_TOPIC:
        return {"status": "error", "message": "PUBSUB_TOPIC not configured"}
    if not TASKQUEUE_LABEL_ID:
        return {"status": "error", "message": "TASKQUEUE_LABEL_ID not configured"}

    try:
        gmail = get_gmail_service()
        result = gmail.users().watch(
            userId="me",
            body={
                "topicName": PUBSUB_TOPIC,
                "labelIds": [TASKQUEUE_LABEL_ID],
                "labelFilterBehavior": "include",
            },
        ).execute()

        logger.info(
            "Watch registered: historyId=%s expiration=%s",
            result.get("historyId"),
            result.get("expiration"),
        )
        return {
            "status": "ok",
            "historyId": result.get("historyId"),
            "expiration": result.get("expiration"),
        }

    except Exception as e:
        logger.exception("Watch registration failed")
        return {"status": "error", "message": str(e)}
```

**Step 3: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
```

**Step 4: Commit**

```bash
git add gmail-watch-service/
git commit -m "feat: add gmail-watch-service for TaskQueue notifications"
```

---

### Task 8: Docker Compose Integration

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Add gmail-watch-service to docker-compose.yml**

Add after the other MCP/utility services:

```yaml
gmail-watch-service:
  build:
    context: ./gmail-watch-service
    dockerfile: Dockerfile
  container_name: ai-pa-gmail-watch-1
  restart: unless-stopped
  ports:
    - "8090:8090"
  environment:
    LETTA_BASE_URL: http://letta:8283
    EMAIL_AGENT_ID: agent-b4928949-8012-4436-a3c7-a9e510785147
    PUBSUB_TOPIC: ${GMAIL_PUBSUB_TOPIC}
    TASKQUEUE_LABEL_ID: ${GMAIL_TASKQUEUE_LABEL_ID}
    GMAIL_CREDS_DIR: /root/.gmail-mcp
  volumes:
    - ${HOME}/.gmail-mcp:/root/.gmail-mcp:ro
  networks:
    - pa-internal
  depends_on:
    - letta
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
    interval: 30s
    timeout: 5s
    retries: 3
```

**Step 2: Add environment variables to `.env`**

```bash
# Gmail Watch Service
GMAIL_PUBSUB_TOPIC=projects/YOUR_PROJECT/topics/gmail-task-notifications
GMAIL_TASKQUEUE_LABEL_ID=Label_XXXXXX
```

**Step 3: Add Cloudflare tunnel route**

Add to the tunnel configuration (in Cloudflare dashboard or `config.yml`):

```yaml
- hostname: gmail-watch.cd-ai-pa.work
  service: http://gmail-watch-service:8090
```

**Step 4: Build and start**

```bash
docker-compose up -d --build gmail-watch-service
```

**Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add gmail-watch-service to docker-compose"
```

---

### Task 9: Watch Renewal via Scheduler

Gmail Watch expires after 7 days. Create a scheduler job that renews it every 6 days.

**Step 1: Register the watch initially**

```bash
curl -X POST http://localhost:8090/watch/register
```

Expected: Returns `historyId` and `expiration` (Unix ms, ~7 days from now).

**Step 2: Create scheduler renewal job**

```bash
curl -X POST http://localhost:8001/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SCHEDULER_API_KEY}" \
  -d '{
    "title": "Renew Gmail Watch",
    "description": "Renew Gmail Watch registration before 7-day expiry",
    "schedule_type": "CRON",
    "schedule_expression": {"cron": "0 3 */6 * *"},
    "category": "infrastructure",
    "created_by": "system",
    "actions": [
      {
        "action_type": "http",
        "config": {
          "url": "http://gmail-watch-service:8090/watch/register",
          "method": "POST",
          "timeout": 30
        }
      }
    ]
  }'
```

This runs at 3am every 6 days.

---

### Task 10: Full E2E Test with Watch

**Step 1: Forward a test email**

Forward any email to `cdorsey+tasks@concord.org` with notes typed above the forwarded content.

**Step 2: Wait for Watch notification** (~10-60 seconds)

Monitor the gmail-watch-service logs:

```bash
docker-compose logs -f gmail-watch-service
```

Expected: Log entry showing "Gmail notification" followed by "Agent triggered".

**Step 3: Verify queue entry appeared**

```bash
curl -s http://localhost:8283/v1/blocks/block-e64dcb37-aae3-416f-8565-5f2a23f53325 | \
  python3 -c "import sys,json; print(json.loads(sys.stdin.read(), strict=False)['value'])"
```

Expected: New entry in the queue with `trigger: forwarded` and captured notes.

**Step 4: Verify TaskQueue label was removed**

Check Gmail — the forwarded message should no longer have the TaskQueue label.

**Step 5: Verify task extraction**

The email-agent should have processed the queue entry and created an extracted task. Check the `extracted_tasks` block or search the shared archive:

```bash
curl -s -X POST http://localhost:8283/v1/passages/search \
  -H "Content-Type: application/json" \
  -d '{"query": "TASK:", "archive_id": "archive-3f0530eb-82db-463a-a28b-f4752a95d7d5", "limit": 5}'
```

---

## Edge Cases & Notes

**Forward detection:** The delimiter regex (`-{5,}\s*Forwarded message\s*-{5,}`) handles standard Gmail forwards. Non-Gmail forwards may use different delimiters — handle gracefully by falling back to direct-label behavior.

**Original message not found:** If the Gmail search for the original message returns no results (deleted, external sender, etc.), the tool uses the forwarded message's own ID. The agent can still extract a task — it just won't have the canonical message_id.

**Block size limits:** The `queued_tasks_from_email` block has a character limit (default 5000). Each entry is ~300-500 chars. The tool processes up to 10 messages per call. If the block fills up, the PATCH will fail — the agent should process (clear) the queue regularly.

**Concurrent access:** The `queued_tasks_from_email` block is only written by the email-agent (via the tool). No concurrent-access concern like the shared `extracted_tasks` block.

**Watch notification deduplication:** Pub/Sub may deliver duplicate notifications. The `process_email_task_queue` tool is idempotent — if a message has already been processed (label removed), it won't appear in the search results.
