# Compaction-Resilient Meeting Task Extraction — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make meeting task extraction survive Letta context compaction by writing marker-extracted candidates to the `queued_tasks_from_meetings` memory block inside the `scan_meeting_notes` tool call.

**Architecture:** Add queue-writing logic to `scan_meeting_notes` (Letta tool). After marker extraction, the tool GETs the queue block, appends formatted entries for each `my_tasks`/`their_tasks` marker, PATCHes the block. Also update the agent notification message and the `meeting_processing_chain` instruction block.

**Tech Stack:** Python (Letta tool conventions — all imports inside function body, no nested defs), Letta REST API for block read/write.

**Design doc:** `docs/plans/2026-02-20-compaction-resilient-meeting-tasks-design.md`

---

### Task 1: Add Queue-Writing to `scan_meeting_notes`

**Files:**
- Modify: `letta/meeting_scan_tool.py:308-324` (before the return statement)

**Context for implementer:**
- This is a Letta tool. ALL imports must be inside the function body. NO nested `def` statements.
- The tool already has `import os, re, json, traceback, urllib.request, urllib.parse, urllib.error` at lines 34-40.
- The queue block ID is `block-809efd9b-e2ca-4d11-af89-9a1c7710716c` (label: `queued_tasks_from_meetings`).
- The block has a 20,000 char limit.
- At line 307, we're past all extraction logic. Variables available: `my_tasks`, `their_tasks`, `meeting_id`, `meeting_title`, `meeting_date`, `participants`, `granola_link`, `doc_urls`, `LETTA_BASE`, `AGENT_ID`.
- Each marker item is a dict: `{"marker": "[ ]", "text": "Send budget", "line": 12}` with optional `deadline_hint` and `deadline_source`.

**Step 1: Add queue-writing code**

Insert the following block **before** the `return` statement at line 308 (after the `# Add doc URL placeholders` section ending at line 306):

```python
        # ── Queue task candidates to durable memory block ──
        QUEUE_BLOCK_ID = "block-809efd9b-e2ca-4d11-af89-9a1c7710716c"
        QUEUE_BLOCK_LIMIT = 20000
        queue_items = my_tasks + their_tasks
        queued_count = 0

        if queue_items:
            import uuid as _uuid
            from datetime import datetime as _dt

            try:
                # GET current block value
                block_url = f"{LETTA_BASE}/v1/blocks/{QUEUE_BLOCK_ID}"
                block_req = urllib.request.Request(block_url, method="GET")
                with urllib.request.urlopen(block_req, timeout=10) as block_resp:
                    block_data = json.loads(block_resp.read().decode("utf-8"))
                current_value = block_data.get("value", "")

                # Strip "(empty)" placeholder if present
                if "(empty)" in current_value:
                    current_value = current_value.replace("(empty)", "").strip()
                    if not current_value:
                        current_value = "# Queued Tasks from Meetings"

                now_str = _dt.now().strftime("%Y-%m-%d %H:%M")
                participants_str = ", ".join(participants) if participants else "unknown"
                urls_str = ", ".join(doc_urls) if doc_urls else ""

                new_entries = []
                for item in queue_items:
                    scan_id = _uuid.uuid4().hex[:8]
                    marker_type = (
                        "my_tasks" if item["marker"] in ("[]", "[ ]") else "their_tasks"
                    )
                    entry_lines = [
                        f"[queued: {now_str}; scan_id: {scan_id}] meeting_id: {meeting_id}",
                        f"title: {meeting_title}",
                        f"date: {meeting_date}",
                        f"participants: {participants_str}",
                        f"granola_link: {granola_link}",
                        f"marker_type: {marker_type}",
                        f"task: {item['text']}",
                    ]
                    if item.get("deadline_hint"):
                        entry_lines.append(f"deadline_hint: {item['deadline_hint']}")
                        entry_lines.append(
                            f"deadline_source: {item.get('deadline_source', 'unknown')}"
                        )
                    if urls_str:
                        entry_lines.append(f"urls: {urls_str}")
                    new_entries.append("\n".join(entry_lines))

                # Build new block value — append entries separated by ---
                entries_text = "\n---\n".join(new_entries) + "\n---"
                if current_value.rstrip().endswith("---"):
                    new_value = current_value.rstrip() + "\n" + entries_text
                else:
                    new_value = current_value.rstrip() + "\n" + entries_text

                # Overflow guard
                if len(new_value) > QUEUE_BLOCK_LIMIT:
                    pass  # Skip queue write, log in return value
                else:
                    patch_data = json.dumps({"value": new_value}).encode("utf-8")
                    patch_req = urllib.request.Request(
                        block_url,
                        data=patch_data,
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    urllib.request.urlopen(patch_req, timeout=10)
                    queued_count = len(new_entries)

            except Exception as qe:
                pass  # Queue write failure is non-fatal; scan package still returns
```

**Step 2: Update the return dict**

Change the return statement (currently line 308-324) to include `queued_to_block`:

```python
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
                "decisions": decisions,
            },
            "scannable_content": scannable_content,
            "has_user_notes": bool(private_notes),
            "doc_urls_found": doc_urls,
            "queued_to_block": queued_count,
        }
```

**Step 3: Verify the tool parses correctly**

Run: `python3 -c "import ast; ast.parse(open('letta/meeting_scan_tool.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add letta/meeting_scan_tool.py
git commit -m "feat: queue meeting task candidates to durable memory block in scan_meeting_notes"
```

---

### Task 2: Update Agent Notification Message

**Files:**
- Modify: `letta/granola_mcp_to_archival.py:84-88`

**Step 1: Update the message text**

Replace lines 84-88 in `notify_agent_new_meeting`:

```python
    message_content = (
        f'New meeting archived: "{meeting_title}" (meeting_id: {meeting_id}). '
        f"Run post-meeting processing: call scan_meeting_notes with this meeting_id, "
        f"review the scan package for additional action items, expand any pointers, "
        f"then call prepare_meeting_followup with merged results. "
        f"Any task markers found have been queued to queued_tasks_from_meetings — "
        f"process them after completing the scan review and followup email."
    )
```

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('letta/granola_mcp_to_archival.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add letta/granola_mcp_to_archival.py
git commit -m "feat: update agent notification to mention queued meeting tasks"
```

---

### Task 3: Update `meeting_processing_chain` Block

**Files:**
- No file changes — this is a Letta API call to update a memory block

**Step 1: PATCH the block**

Run this Python script to update Step 4 in the block:

```python
python3 -c "
import urllib.request, json

BLOCK_ID = 'block-2c406991-db8e-4f85-b6aa-96fb7b70fc11'
LETTA_BASE = 'http://localhost:8283'

# GET current value
url = f'{LETTA_BASE}/v1/blocks/{BLOCK_ID}'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
current = data['value']

OLD_STEP4 = '''### Step 4: Extract Tasks
For any my_actions items, also call add_extracted_tasks following the
task_extraction_process_docs_transcripts block rules.
Include related_urls from user notes and private_notes only (not transcript text).
Omit URLs from AI summary or linked_doc content.'''

NEW_STEP4 = '''### Step 4: Extract Tasks from Queue
scan_meeting_notes writes task marker candidates to queued_tasks_from_meetings.
Check that block for pending entries. For each entry:
- Interpret the marker text using your knowledge of the user's projects and context.
- For my_tasks entries: call add_extracted_tasks per task_extraction_process_docs_transcripts rules.
  Pass cleanup_block_id=block-809efd9b-e2ca-4d11-af89-9a1c7710716c and cleanup_entry_identifier={scan_id}.
  Pass related_urls from the entry's urls field. Apply deadline_hint with confidence per Step 2b rules.
- For their_tasks entries: decide if a follow-up task is implied for the user (e.g. \"follow up with X on Y\").
  If so, extract it. If purely informational, remove the entry from the queue.
- If the entry is not actionable, remove it from the queue block.
- You can search archival for the full meeting transcript (?search={meeting_id}) if you need more context.
Queue entries persist through compaction — process them even if you don't remember the original scan.'''

if OLD_STEP4 in current:
    new_value = current.replace(OLD_STEP4, NEW_STEP4)
    patch_data = json.dumps({'value': new_value}).encode('utf-8')
    patch_req = urllib.request.Request(url, data=patch_data, headers={'Content-Type': 'application/json'}, method='PATCH')
    urllib.request.urlopen(patch_req, timeout=10)
    print('Block updated successfully')
else:
    print('ERROR: Could not find old Step 4 text in block')
    print('Current value:')
    print(current)
"
```

Expected: `Block updated successfully`

**Step 2: Verify the update**

```python
python3 -c "
import urllib.request, json
url = 'http://localhost:8283/v1/blocks/block-2c406991-db8e-4f85-b6aa-96fb7b70fc11'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
print(data['value'])
" | grep -A5 "Step 4"
```

Expected: Shows the new Step 4 text with `queued_tasks_from_meetings` reference.

---

### Task 4: Re-register Tool and Verify

**Files:**
- Run: `letta/register_meeting_processing_tools.py` (no modifications needed)

**Step 1: Re-register the updated scan tool**

```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python3 letta/register_meeting_processing_tools.py
```

Expected: Output showing `scan_meeting_notes` tool updated/registered.

**Step 2: Verify tool source was updated in Letta**

```python
python3 -c "
import urllib.request, json
# Get tool list and find scan_meeting_notes
url = 'http://localhost:8283/v1/tools?name=scan_meeting_notes'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    tools = json.loads(resp.read().decode('utf-8'))
if tools:
    source = tools[0].get('source_code', '')
    print('Has QUEUE_BLOCK_ID:', 'QUEUE_BLOCK_ID' in source)
    print('Has queued_to_block:', 'queued_to_block' in source)
else:
    print('ERROR: scan_meeting_notes tool not found')
"
```

Expected:
```
Has QUEUE_BLOCK_ID: True
Has queued_to_block: True
```

---

### Task 5: End-to-End Test

**Step 1: Find a meeting from today with markers**

Check today's meetings for one with private notes markers:

```python
python3 -c "
import urllib.request, json

LETTA_BASE = 'http://localhost:8283'
AGENT_ID = 'agent-398b4f6c-6afa-493f-8063-897c6b171a0d'

# Search for today's meetings
url = f'{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory?search=2026-02-20&limit=50'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=30) as resp:
    passages = json.loads(resp.read().decode('utf-8'))

# Find unique meeting IDs from today
meetings = set()
for p in passages:
    tags = p.get('tags', [])
    for t in tags:
        if t.startswith('id:'):
            mid = t[3:]
            text = p.get('text', '')
            if '### My Notes' in text and ('[ ]' in text or '[;]' in text):
                title_match = __import__('re').search(r'## Meeting:\s*(.+)', text)
                title = title_match.group(1).strip() if title_match else 'unknown'
                meetings.add((mid, title))
for mid, title in meetings:
    print(f'{mid}: {title}')
"
```

If no meeting from today has markers, use a known meeting with markers (e.g. from the design doc test data). If none available, create a test by manually adding a marker-containing meeting to archival.

**Step 2: Verify queue block is empty**

```python
python3 -c "
import urllib.request, json
url = 'http://localhost:8283/v1/blocks/block-809efd9b-e2ca-4d11-af89-9a1c7710716c'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
print(repr(data['value']))
"
```

Expected: `'# Queued Tasks from Meetings\n(empty)\n'` or similar empty state.

**Step 3: Trigger scan via agent message**

Send a test message to the agent to scan a meeting:

```python
python3 -c "
import urllib.request, json

LETTA_BASE = 'http://localhost:8283'
AGENT_ID = 'agent-398b4f6c-6afa-493f-8063-897c6b171a0d'
MEETING_ID = '<meeting_id_from_step_1>'  # REPLACE THIS

url = f'{LETTA_BASE}/v1/agents/{AGENT_ID}/messages'
payload = json.dumps({
    'messages': [{'role': 'user', 'content': f'Please call scan_meeting_notes with meeting_id={MEETING_ID} and then check your queued_tasks_from_meetings block for any new entries.'}]
}).encode('utf-8')
req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=120) as resp:
    result = json.loads(resp.read().decode('utf-8'))
for msg in result:
    if msg.get('message_type') == 'tool_call_message':
        print(f\"Tool call: {msg.get('tool_call', {}).get('name', 'unknown')}\")
    elif msg.get('message_type') == 'tool_return_message':
        tr = msg.get('tool_return', '')
        if 'queued_to_block' in tr:
            print(f'Tool return (truncated): ...queued_to_block: {tr.split(\"queued_to_block\")[1][:30]}')
    elif msg.get('message_type') == 'assistant_message':
        print(f\"Assistant: {msg.get('content', '')[:200]}\")
"
```

**Step 4: Verify queue entries appeared**

```python
python3 -c "
import urllib.request, json
url = 'http://localhost:8283/v1/blocks/block-809efd9b-e2ca-4d11-af89-9a1c7710716c'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
print(data['value'])
"
```

Expected: Block now contains formatted entries with `scan_id`, `marker_type`, `task`, etc.

**Step 5: Verify agent can extract from queue**

If the agent didn't already process the queue entries in Step 3, send a follow-up:

```python
python3 -c "
import urllib.request, json

LETTA_BASE = 'http://localhost:8283'
AGENT_ID = 'agent-398b4f6c-6afa-493f-8063-897c6b171a0d'

url = f'{LETTA_BASE}/v1/agents/{AGENT_ID}/messages'
payload = json.dumps({
    'messages': [{'role': 'user', 'content': 'You have entries in queued_tasks_from_meetings. Please process each one — extract real tasks with add_extracted_tasks and remove non-actionable ones.'}]
}).encode('utf-8')
req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=120) as resp:
    result = json.loads(resp.read().decode('utf-8'))
for msg in result:
    if msg.get('message_type') == 'tool_call_message':
        name = msg.get('tool_call', {}).get('name', 'unknown')
        print(f'Tool call: {name}')
    elif msg.get('message_type') == 'assistant_message':
        print(f\"Assistant: {msg.get('content', '')[:200]}\")
"
```

Expected: Agent calls `add_extracted_tasks` with `cleanup_block_id` and `cleanup_entry_identifier`.

**Step 6: Verify queue cleanup**

After agent processes entries, check the block is clean:

```python
python3 -c "
import urllib.request, json
url = 'http://localhost:8283/v1/blocks/block-809efd9b-e2ca-4d11-af89-9a1c7710716c'
req = urllib.request.Request(url, method='GET')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
print(repr(data['value']))
"
```

Expected: Queue block is empty or has only unprocessed entries remaining.

**Step 7: Final commit if any test fixes were needed**

```bash
git add -A && git status
# Only commit if there are changes from test fixes
```
