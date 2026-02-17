# Meeting Notes Processing Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically extract tasks and generate D/NA follow-up email drafts from every archived Granola meeting.

**Architecture:** Two new Letta tools (`scan_meeting_notes`, `prepare_meeting_followup`) handle deterministic marker extraction and email drafting. The Granola agent (`docs-and-transcripts-agent`) performs semantic scanning and merges results. A post-ingestion trigger in the MCP import script kicks off processing. See `docs/plans/2026-02-17-meeting-notes-processing-design.md` for full design.

**Tech Stack:** Python (Letta tool pattern), Letta API (urllib.request), Gmail API (google-api-python-client), Granola MCP

---

### Task 1: Create `queued_tasks_from_meetings` Memory Block

Create a new shared memory block on the Granola agent to queue meeting-sourced tasks, paralleling `queued_tasks_from_email`.

**Files:**
- Create: `letta/create_meeting_tasks_block.py`

**Step 1: Write the block creation script**

```python
#!/usr/bin/env python3
"""Create queued_tasks_from_meetings memory block on the Granola agent."""
import os
import sys

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    client = Letta(base_url=LETTA_BASE)

    # Check if block already exists
    agent = client.agents.retrieve(agent_id=AGENT_ID)
    for block in agent.memory.blocks:
        if block.label == "queued_tasks_from_meetings":
            print(f"Block already exists: {block.id}")
            return 0

    # Create block
    block = client.blocks.create(
        label="queued_tasks_from_meetings",
        value="# Queued Tasks from Meetings\n(empty)\n",
    )
    print(f"Created block: {block.id}")

    # Attach to agent
    client.agents.blocks.attach(agent_id=AGENT_ID, block_id=block.id)
    print(f"Attached to agent {AGENT_ID}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
```

**Step 2: Run the script**

Run: `LETTA_BASE_URL=http://localhost:8283 python letta/create_meeting_tasks_block.py`
Expected: Block created and attached. Note the block ID in output.

**Step 3: Verify**

Run: `curl -s http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d | python3 -c "import sys,json; blocks=json.load(sys.stdin)['memory']['blocks']; [print(f'{b[\"label\"]}: {b[\"id\"]}') for b in blocks]"`
Expected: `queued_tasks_from_meetings` appears in the list.

**Step 4: Commit**

```bash
git add letta/create_meeting_tasks_block.py
git commit -m "feat: create queued_tasks_from_meetings memory block"
```

---

### Task 2: Write `scan_meeting_notes` Tool

The core extraction tool. Fetches a meeting's archival passages, parses markers from private_notes, extracts URLs, retrieves transcript excerpts for pointers, and returns the scan package.

**Files:**
- Create: `letta/meeting_scan_tool.py`

**Reference files to read first:**
- `letta/extracted_tasks_tool.py` — Letta tool pattern (urllib.request, try/except, docstring)
- `letta/email_task_queue_tool.py` — block read/write pattern
- `docs/plans/2026-02-17-meeting-notes-processing-design.md` — Section 3: Scan Package

**Step 1: Write the tool**

Create `letta/meeting_scan_tool.py` with a single function `scan_meeting_notes(meeting_id: str) -> Dict[str, Any]`.

The function must:
1. **Imports inside function body** (after docstring): `os`, `re`, `json`, `traceback`, `urllib.request`, `pytz`, `datetime`
2. **Fetch meeting passages** from archival by searching for tag `id:{meeting_id}`
   - API: `GET /v1/agents/{AGENT_ID}/archival-memory?query={meeting_id}&limit=20`
   - Filter results to passages whose tags include `id:{meeting_id}`
3. **Extract sections from passage text:**
   - Find `### My Notes` section → `private_notes`
   - Find `### Summary` section → `ai_summary`
   - Find `### Transcript` section → `transcript_text`
   - Parse meeting header for title, date, participants, Granola link
4. **Parse markers from private_notes** using regex `^\s*(?:[-*]\s*)?(\[;\]|\[\s?\]|>)\s+(.+)$` (multiline):
   - `[ ]` or `[]` matches → `my_tasks` list
   - `[;]` matches → `their_tasks` list
   - `>` matches → `pointers` list
5. **Extract URLs** from private_notes: regex `https?://[^\s<>"]+`
6. **For each pointer**, search transcript for keyword overlap (simple word-intersection search within a 500-char window)
7. **Return the scan package** dict with:
   - `meeting_id`, `meeting_title`, `participants`, `meeting_date`
   - `marker_extractions`: `{my_tasks, their_tasks, pointers}` (each item has `marker`, `text`, `line`)
   - `scannable_content`: list of `{source, label, text}` dicts for private_notes, ai_summary, and transcript excerpts
   - `has_user_notes`: bool
   - `doc_urls_found`: list of URLs

Key implementation notes:
- Use `LETTA_BASE_URL` and `LETTA_AGENT_ID` env vars (standard Letta sandbox pattern)
- Archival search: `GET {LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory` with params
- All logic inlined (no nested `def` statements)
- Return `{"status": "error", "error_message": ...}` on failure
- Transcript may be split across multiple `chunk:transcript-*` passages — concatenate them

```python
from typing import Dict, Any

def scan_meeting_notes(meeting_id: str) -> Dict[str, Any]:
    """
    Scan a meeting's archival passages for task markers and prepare a scan package.

    Fetches the meeting's archived content (private notes, AI summary, transcript),
    parses user-authored markers ([ ] for my tasks, [;] for others' tasks, > for
    pointers), extracts document URLs, and retrieves transcript excerpts matching
    pointer topics.

    Returns a structured scan package for the agent to perform semantic analysis on.
    The agent should review all scannable_content items for additional action items
    beyond what markers captured, then call prepare_meeting_followup with merged results.

    Args:
        meeting_id: The Granola meeting UUID (e.g. "9b86c082-3840-4b84-98e9-b8096b4ef5e9")

    Returns:
        Dictionary with meeting metadata, marker_extractions, scannable_content,
        doc_urls_found, and has_user_notes flag.
    """
    import os
    import re
    import json
    import traceback
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")
        if not AGENT_ID:
            return {"status": "error", "error_message": "LETTA_AGENT_ID not set"}

        # ── Fetch archival passages for this meeting ──
        search_url = (
            f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory"
            f"?query={meeting_id}&limit=30"
        )
        req = urllib.request.Request(search_url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            all_passages = json.loads(resp.read().decode("utf-8"))

        # Filter to passages tagged with this meeting's id
        meeting_passages = []
        for p in all_passages:
            tags = p.get("tags", [])
            if f"id:{meeting_id}" in tags:
                meeting_passages.append(p)

        if not meeting_passages:
            return {
                "status": "error",
                "error_message": f"No archival passages found for meeting {meeting_id}",
            }

        # ── Reconstruct meeting content from passages ──
        # Sort by chunk tag (summary first, then transcript-1, transcript-2, etc.)
        chunk_order = {"summary": 0, "metadata": 1}
        meeting_passages.sort(
            key=lambda p: chunk_order.get(
                next((t.split(":")[1] for t in p.get("tags", []) if t.startswith("chunk:")), "z"),
                10 + int(next((t.split("-")[1] for t in p.get("tags", []) if t.startswith("chunk:transcript-")), "99"))
                if any(t.startswith("chunk:transcript-") for t in p.get("tags", []))
                else 50
            )
        )

        full_text = "\n\n".join(p.get("text", "") for p in meeting_passages)

        # ── Parse meeting header ──
        title_match = re.search(r"## Meeting:\s*(.+)", full_text)
        meeting_title = title_match.group(1).strip() if title_match else "Untitled"

        date_match = re.search(r"\*\*Date:\*\*\s*(.+)", full_text)
        meeting_date = date_match.group(1).strip() if date_match else ""

        participants_match = re.search(r"\*\*Participants:\*\*\s*(.+)", full_text)
        participants_raw = participants_match.group(1).strip() if participants_match else ""
        participants = [p.strip() for p in participants_raw.split(",") if p.strip()]

        link_match = re.search(r"\*\*Granola Link:\*\*\s*(https://\S+)", full_text)
        granola_link = link_match.group(1).strip() if link_match else ""

        # ── Extract sections ──
        private_notes = ""
        ai_summary = ""
        transcript_text = ""

        notes_match = re.search(
            r"### My Notes\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if notes_match:
            private_notes = notes_match.group(1).strip()

        summary_match = re.search(
            r"### Summary\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if summary_match:
            ai_summary = summary_match.group(1).strip()

        transcript_match = re.search(
            r"### Transcript\s*\n(.*?)(?=\n### |\Z)", full_text, re.DOTALL
        )
        if transcript_match:
            transcript_text = transcript_match.group(1).strip()

        # ── Parse markers from private_notes ──
        MARKER_RE = re.compile(
            r"^\s*(?:[-*]\s*)?(\[;\]|\[\s?\]|>)\s+(.+)$", re.MULTILINE
        )
        my_tasks = []
        their_tasks = []
        pointers = []

        if private_notes:
            for line_num, line in enumerate(private_notes.split("\n"), 1):
                m = MARKER_RE.match(line)
                if not m:
                    continue
                marker = m.group(1).strip()
                text = m.group(2).strip()
                item = {"marker": marker, "text": text, "line": line_num}

                if marker in ("[]", "[ ]"):
                    my_tasks.append(item)
                elif marker == "[;]":
                    their_tasks.append(item)
                elif marker == ">":
                    pointers.append(item)

        # ── Extract URLs from private_notes ──
        URL_RE = re.compile(r"https?://[^\s<>\"]+")
        doc_urls = []
        if private_notes:
            doc_urls = URL_RE.findall(private_notes)

        # ── Context lines (unmarked, non-empty lines from notes) ──
        context_lines = []
        if private_notes:
            for line in private_notes.split("\n"):
                stripped = line.strip()
                if stripped and not MARKER_RE.match(line) and not stripped.startswith("D/NA"):
                    context_lines.append(stripped)

        # ── Transcript excerpts for pointers ──
        transcript_excerpts = []
        if transcript_text and pointers:
            for ptr in pointers:
                keywords = set(
                    w.lower()
                    for w in re.findall(r"\w{4,}", ptr["text"])
                )
                if not keywords:
                    continue
                # Slide a 500-char window looking for best keyword overlap
                best_start = 0
                best_score = 0
                window_size = 500
                for start in range(0, max(1, len(transcript_text) - window_size), 100):
                    window = transcript_text[start : start + window_size].lower()
                    score = sum(1 for kw in keywords if kw in window)
                    if score > best_score:
                        best_score = score
                        best_start = start
                if best_score > 0:
                    excerpt = transcript_text[
                        best_start : best_start + window_size
                    ].strip()
                    transcript_excerpts.append(
                        {
                            "source": "transcript_excerpt",
                            "label": f"Transcript near: {ptr['text'][:60]}",
                            "text": excerpt,
                        }
                    )

        # ── Build scannable_content ──
        scannable_content = []

        if private_notes:
            scannable_content.append(
                {
                    "source": "private_notes",
                    "label": "User's meeting notes",
                    "text": private_notes,
                    "context_lines": context_lines,
                }
            )

        if ai_summary:
            scannable_content.append(
                {
                    "source": "ai_summary",
                    "label": "Granola AI summary",
                    "text": ai_summary,
                }
            )

        scannable_content.extend(transcript_excerpts)

        # Add doc URL placeholders (agent fetches content via existing tools)
        for url in doc_urls:
            scannable_content.append(
                {
                    "source": "linked_doc",
                    "label": f"Linked document: {url[:80]}",
                    "url": url,
                    "text": None,
                    "fetch_note": (
                        "Use fetch_document_from_drive or get_drive_file_info "
                        "to retrieve this document's content for scanning."
                    ),
                }
            )

        return {
            "status": "ok",
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "meeting_date": meeting_date,
            "participants": participants,
            "granola_link": granola_link,
            "marker_extractions": {
                "my_tasks": my_tasks,
                "their_tasks": their_tasks,
                "pointers": pointers,
            },
            "scannable_content": scannable_content,
            "has_user_notes": bool(private_notes),
            "doc_urls_found": doc_urls,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
```

**Step 2: Test locally against a real meeting**

Run: `LETTA_BASE_URL=http://localhost:8283 python3 -c "
import os; os.environ['LETTA_BASE_URL']='http://localhost:8283'; os.environ['LETTA_AGENT_ID']='agent-398b4f6c-6afa-493f-8063-897c6b171a0d'
from meeting_scan_tool import scan_meeting_notes
import json
# Use the Rebecca meeting once it's imported
result = scan_meeting_notes('9b86c082-3840-4b84-98e9-b8096b4ef5e9')
print(json.dumps(result, indent=2))
"`
Expected: Returns scan package with `their_tasks` containing 4 `[;]` items from Rebecca's meeting.

**Step 3: Commit**

```bash
git add letta/meeting_scan_tool.py
git commit -m "feat: add scan_meeting_notes Letta tool"
```

---

### Task 3: Write `prepare_meeting_followup` Tool

Formats the agent's merged action items into a Gmail draft.

**Files:**
- Create: `letta/meeting_followup_tool.py`

**Reference files:**
- `letta/gmail_tools.py:577-675` — `draft_email` function for Gmail auth pattern
- `letta/email_task_queue_tool.py` — block write pattern

**Step 1: Write the tool**

Create `letta/meeting_followup_tool.py` with function `prepare_meeting_followup(meeting_id, meeting_title, meeting_date, participants, decisions, my_actions, their_actions)`.

The function must:
1. All imports inside function body
2. Parse `participants` (comma-separated string of `"Name <email>"` entries)
3. Parse `decisions` (comma-separated string)
4. Parse `my_actions` (comma-separated string)
5. Parse `their_actions` (comma-separated string of `"Who: action"` entries)
6. Format email body with Decisions + Next Actions sections grouped by person
7. Create Gmail draft via Gmail API (inline auth, same pattern as `draft_email`)
8. Also write `[ ]` items to `queued_tasks_from_meetings` block
9. Return `{status, draft_id, tasks_queued}`

**Important Letta constraint:** All parameters must be basic JSON types (`str`, `int`, `bool`). Multi-value parameters use comma-separated strings, parsed inside the function.

```python
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
        decisions: Comma-separated list of key decisions made. Use pipe | as separator
            if decisions contain commas (e.g. "Decision one|Decision two, with detail").
            Omit if no decisions identified.
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

        # ── Format email body ──
        lines = [f"Hi all,", "", f"Here's a summary of our {meeting_title} ({meeting_date}):"]

        if decision_list:
            lines.append("")
            lines.append("DECISIONS")
            for d in decision_list:
                lines.append(f"- {d}")

        lines.append("")
        lines.append("NEXT ACTIONS")

        if my_action_list:
            lines.append("")
            lines.append("Chad:")
            for a in my_action_list:
                lines.append(f"- {a}")

        for who, actions in sorted(their_action_map.items()):
            lines.append("")
            lines.append(f"{who}:")
            for a in actions:
                lines.append(f"- {a}")

        lines.append("")
        lines.append("Let me know if I missed anything.")
        lines.append("")
        lines.append("Best,")
        lines.append("Chad")

        body_text = "\n".join(lines)

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

        message = MIMEText(body_text, "plain")
        message["To"] = ", ".join(emails_list)
        message["Subject"] = f"Re: {meeting_title} -- D/NA"

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
            "email_subject": f"Re: {meeting_title} -- D/NA",
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
```

**Step 2: Commit**

```bash
git add letta/meeting_followup_tool.py
git commit -m "feat: add prepare_meeting_followup Letta tool"
```

---

### Task 4: Register Tools and Attach to Granola Agent

**Files:**
- Create: `letta/register_meeting_processing_tools.py`

**Reference:** `letta/register_email_task_queue_tool.py`

**Step 1: Write the registration script**

```python
#!/usr/bin/env python3
"""Register meeting processing tools and attach to the Granola agent."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    from letta import Letta

from meeting_scan_tool import scan_meeting_notes
from meeting_followup_tool import prepare_meeting_followup

AGENT_ID = "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"

TOOLS = [
    (scan_meeting_notes, ["meeting", "scan", "task-extraction"]),
    (prepare_meeting_followup, ["meeting", "followup", "email", "draft"]),
]


def main():
    LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {AGENT_ID}")
    print()

    client = Letta(base_url=LETTA_BASE)

    for func, tags in TOOLS:
        name = func.__name__
        print(f"--- {name} ---")

        # Check for existing
        for tool in client.tools.list():
            if tool.name == name:
                print(f"  Existing tool found: {tool.id}")
                response = input("  Re-register? [y/N]: ")
                if response.lower() != "y":
                    print("  Skipped.")
                    # Still try to attach
                    try:
                        client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool.id)
                        print(f"  Attached {tool.id} to agent.")
                    except Exception as e:
                        print(f"  Attach: {e}")
                    continue
                client.tools.delete(tool.id)
                print("  Deleted old version.")
                break

        # Register
        created = client.tools.create_from_function(func=func, tags=tags)
        print(f"  Registered: {created.id}")

        # Attach
        try:
            client.agents.tools.attach(agent_id=AGENT_ID, tool_id=created.id)
            print(f"  Attached to agent.")
        except Exception as e:
            print(f"  Attach: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
```

**Step 2: Run registration**

Run: `cd /Volumes/main-drive/ai-PA/letta && LETTA_BASE_URL=http://localhost:8283 python register_meeting_processing_tools.py`
Expected: Both tools registered and attached. Answer "y" if prompted to re-register.

**Step 3: Verify tools are on the agent**

Run: `curl -s http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d | python3 -c "import sys,json; tools=json.load(sys.stdin).get('tools',[]); [print(t['name']) for t in tools]" | grep -E "scan_meeting|prepare_meeting"`
Expected: Both `scan_meeting_notes` and `prepare_meeting_followup` appear.

**Step 4: Commit**

```bash
git add letta/register_meeting_processing_tools.py
git commit -m "feat: add meeting processing tools registration script"
```

---

### Task 5: Add Post-Ingestion Trigger

Modify the Granola MCP ingestion script to send a message to the agent after each new meeting is archived, triggering the scan + followup pipeline.

**Files:**
- Modify: `letta/granola_mcp_to_archival.py:524-534` (after successful insertion in `ingest_meetings`)
- Modify: `letta/granola_mcp_to_archival.py:~410` (after successful insertion in `ingest_meeting_by_id`)

**Step 1: Add the trigger function**

Add a `notify_agent(meeting_id, meeting_title)` function near the top of the file (after imports, before the existing functions). This function sends a message to the Granola agent via the Letta API.

```python
def notify_agent_new_meeting(meeting_id: str, meeting_title: str):
    """Send a message to the Granola agent to trigger post-meeting processing."""
    import urllib.request
    import json as _json

    letta_base = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    url = f"{letta_base}/v1/agents/{AGENT_ID}/messages"
    payload = _json.dumps({
        "role": "user",
        "content": (
            f"New meeting archived: \"{meeting_title}\" (meeting_id: {meeting_id}). "
            f"Run post-meeting processing: call scan_meeting_notes with this meeting_id, "
            f"review the scan package for additional action items, expand any pointers, "
            f"then call prepare_meeting_followup with merged results."
        ),
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=60)
        logger.info(f"  Notified agent for post-meeting processing")
    except Exception as e:
        logger.warning(f"  Agent notification failed (non-fatal): {e}")
```

**Step 2: Add trigger call after successful ingestion in `ingest_meetings`**

In the `ingest_meetings` function, after the `logger.info(f"  Inserted ...")` line (~line 533), add:

```python
            # Trigger post-meeting processing
            notify_agent_new_meeting(mid, title)
```

**Step 3: Add trigger call after successful ingestion in `ingest_meeting_by_id`**

In the `ingest_meeting_by_id` function, after the success log line, add the same call.

**Step 4: Test with a dry run of a known meeting**

Run: `cd /Volumes/main-drive/ai-PA/letta && python granola_mcp_to_archival.py --meeting-id 9b86c082-3840-4b84-98e9-b8096b4ef5e9 --force`
Expected: Meeting re-imported and "Notified agent for post-meeting processing" appears in logs. The agent processes the meeting asynchronously.

**Step 5: Commit**

```bash
git add letta/granola_mcp_to_archival.py
git commit -m "feat: add post-ingestion agent trigger for meeting processing"
```

---

### Task 6: Update Granola Agent System Prompt

Add the marker convention, post-meeting processing protocol, and confidence weighting instructions to the agent's system prompt.

**Files:**
- Create: `letta/update_granola_agent_prompt.py`

**Step 1: Write the prompt update script**

This script reads the agent's current system prompt, appends the new meeting processing instructions, and updates it via the API.

The new prompt section to append:

```
<meeting_processing_protocol>
When you receive a "New meeting archived" notification:

1. Call scan_meeting_notes(meeting_id) to get the scan package.

2. Review the scan package:
   a. marker_extractions contains high-confidence items parsed from user notes.
   b. scannable_content contains labeled text for you to scan semantically.
   c. For linked_doc items with text=null, call fetch_document_from_drive to get content.

3. Semantic scan — review each scannable_content item for:
   - Action items not captured by markers (especially from AI summary and transcript)
   - Additional context for marker items (deadlines, specifics from discussion)
   - Tasks from linked document content

4. Merge results:
   - Markers are authoritative anchors
   - Semantic discoveries augment markers or add new items
   - Deduplicate: if a semantic hit overlaps a marker, enrich the marker item
   - Confidence weighting: markers > user notes > AI summary > linked docs > transcript

5. Expand pointers (> items): use the provided transcript excerpts to identify what
   was discussed and formulate the action item or talking point.

6. Call prepare_meeting_followup with ALL merged items:
   - meeting_id, meeting_title, meeting_date from scan package
   - participants as comma-separated "Name <email>" entries
   - decisions: pipe-separated key decisions from AI summary
   - my_actions: pipe-separated personal action items (from [ ] markers + semantic)
   - their_actions: pipe-separated "Name: action" entries (from [;] markers + semantic)

Marker convention:
- [ ] or [] = my task (queued for extraction + included in D/NA email)
- [;] = someone else's task (D/NA email only, not queued)
- > = pointer needing expansion from transcript context
- D/NA = section header (informational, not required for routing)
</meeting_processing_protocol>
```

**Step 2: Run the update**

Run: `cd /Volumes/main-drive/ai-PA/letta && LETTA_BASE_URL=http://localhost:8283 python update_granola_agent_prompt.py`

**Step 3: Verify the prompt was updated**

Run: `curl -s http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('system','')[-500:])"`
Expected: The `<meeting_processing_protocol>` section appears at the end.

**Step 4: Commit**

```bash
git add letta/update_granola_agent_prompt.py
git commit -m "feat: update Granola agent prompt with meeting processing protocol"
```

---

### Task 7: End-to-End Test with Rebecca Meeting

Manual E2E test using the real Rebecca meeting data.

**Step 1: Ensure the Rebecca meeting is in archival**

Run: `cd /Volumes/main-drive/ai-PA/letta && python granola_mcp_to_archival.py --meeting-id 9b86c082-3840-4b84-98e9-b8096b4ef5e9 --force`

**Step 2: Trigger the pipeline manually**

Send a message to the agent to process the meeting:

Run: `curl -s -X POST http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d/messages -H "Content-Type: application/json" -d '{"role":"user","content":"New meeting archived: \"Proposal Check in Rebecca\" (meeting_id: 9b86c082-3840-4b84-98e9-b8096b4ef5e9). Run post-meeting processing: call scan_meeting_notes with this meeting_id, review the scan package, then call prepare_meeting_followup with merged results."}' | python3 -m json.tool | head -80`

**Step 3: Verify outputs**

Check for:
1. Gmail draft created (check Gmail Drafts folder for "Re: Proposal Check in Rebecca -- D/NA")
2. Tasks queued in `queued_tasks_from_meetings` block:
   Run: `curl -s http://localhost:8283/v1/agents/agent-398b4f6c-6afa-493f-8063-897c6b171a0d | python3 -c "import sys,json; blocks=json.load(sys.stdin)['memory']['blocks']; [print(b['value'][:500]) for b in blocks if b['label']=='queued_tasks_from_meetings']"`

**Step 4: Review and iterate**

- Check the email draft content — does it accurately reflect the meeting?
- Are the `[;]` items listed under Rebecca's name?
- Did the semantic scan find any additional items from the AI summary?
- Adjust email template or agent prompt as needed.

---

## Execution Order Summary

| Task | What | Dependencies |
|------|------|-------------|
| 1 | Create memory block | None |
| 2 | Write scan_meeting_notes tool | None |
| 3 | Write prepare_meeting_followup tool | Task 1 (block must exist) |
| 4 | Register tools + attach to agent | Tasks 2, 3 |
| 5 | Add post-ingestion trigger | Tasks 2, 3, 4 |
| 6 | Update agent system prompt | None (can run in parallel) |
| 7 | E2E test | All above |

Tasks 1, 2, 3, 6 can be done in parallel. Task 4 depends on 2+3. Task 5 depends on 4. Task 7 depends on all.
