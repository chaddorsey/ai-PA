# Drive Comment Task Queueing — Design Document

## Problem

There is no way to flag individual Google Docs/Sheets/Slides comments as tasks for the AI PA system. The user needs a lightweight gesture that works on any existing comment across all Google Workspace document types, captures rich context (comment text, surrounding passage, document metadata), and feeds into the existing task extraction pipeline.

## Trigger Mechanism

**Reply with action item `+cdorsey+dtasks@concord.org`** on any Google Workspace comment.

This generates a notification email to `cdorsey@concord.org` that Gmail automatically labels with `DTaskQueue` (via the existing `+dtasks` suffix routing). The Gmail Watch service already polls for labeled messages — extending it to detect `DTaskQueue` alongside the existing `TaskQueue` label is a small configuration change.

### Why this approach

- Works on **existing comments** (no need to create new ones)
- Works across **all Google Workspace doc types** (Docs, Sheets, Slides)
- Leverages **existing Gmail Watch infrastructure** (Pub/Sub push, label detection, agent notification)
- Provides a **visible audit trail** — the action item reply appears in the comment thread
- **Author verification** — the notification email includes who triggered the action item, enabling foreign-trigger detection

### What the notification email contains

When `+cdorsey+dtasks@concord.org` is added as an action item reply, Gmail receives a notification with:
- Document title and link
- Comment text and author
- The quoted passage the comment is anchored to
- Who triggered the action item

This is enough to bootstrap enrichment via the Drive API.

## Architecture

```
User adds +cdorsey+dtasks@concord.org reply on comment
         │
         ▼
Gmail receives notification email
  └─ Auto-labeled "DTaskQueue" via +dtasks suffix
         │
         ▼
Gmail Watch Service (existing)
  └─ process_task_queue() detects DTaskQueue label
  └─ Parses notification email for doc_id + comment_id
  └─ Writes queue entry to queued_tasks_from_drive block
  └─ Removes DTaskQueue label
  └─ Notifies Docs & Transcripts Agent
         │
         ▼
Docs & Transcripts Agent receives notification
  └─ Calls process_drive_task_queue tool
         │
         ▼
process_drive_task_queue (new Letta tool)
  └─ Reads queued_tasks_from_drive block
  └─ For each entry:
      ├─ Calls Drive API: comments.get(fileId, commentId)
      ├─ Calls Drive API: files.get(fileId) for mime type + title
      ├─ Branches by doc type for surrounding context:
      │   ├─ Docs → documents.get → locate passage → ~3 paragraphs
      │   ├─ Sheets → spreadsheets.get → cell range context
      │   └─ Slides → presentations.get → slide text content
      ├─ Detects foreign triggers → [FROM: email] annotation
      └─ Calls add_extracted_tasks with full metadata
  └─ Removes processed entry from block
```

## Components

### 1. Gmail Watch Config (small change)

**File:** `gmail-watch-service/src/gmail_watch/settings.py`

Add new settings alongside existing `task_queue_*`:

```python
# Drive comment task queue settings
drive_task_queue_enabled: bool = Field(
    default=False,
    alias="DRIVE_TASK_QUEUE_ENABLED",
)
drive_task_queue_label_name: str = Field(
    default="DTaskQueue",
    alias="DRIVE_TASK_QUEUE_LABEL_NAME",
)
drive_task_queue_block_id: Optional[str] = Field(
    default=None,
    alias="DRIVE_TASK_QUEUE_BLOCK_ID",
    description="Letta memory block ID for queued_tasks_from_drive",
)
drive_task_queue_agent_id: Optional[str] = Field(
    default=None,
    alias="DRIVE_TASK_QUEUE_AGENT_ID",
    description="Docs & Transcripts agent ID for notifications",
)
```

**File:** `docker-compose.yml` — Add env vars to gmail-watch-service:

```yaml
DRIVE_TASK_QUEUE_ENABLED: "true"
DRIVE_TASK_QUEUE_LABEL_NAME: "DTaskQueue"
DRIVE_TASK_QUEUE_BLOCK_ID: "<block-id>"  # queued_tasks_from_drive
DRIVE_TASK_QUEUE_AGENT_ID: "agent-398b4f6c-6afa-493f-8063-897c6b171a0d"
```

### 2. Gmail Watch — DTaskQueue Processing (medium change)

**File:** `gmail-watch-service/src/gmail_watch/services/watch_manager.py`

Add `process_drive_task_queue()` method modeled on existing `process_task_queue()`. Key differences:

- Searches for `DTaskQueue` label (not `TaskQueue`)
- Parses notification email to extract `doc_id` and `comment_id` from the Google Docs link in the email body (pattern: `https://docs.google.com/document/d/{doc_id}/...`)
- Extracts `triggered_by` from the email headers (who added the action item)
- Writes to `queued_tasks_from_drive` block (not `queued_tasks_from_email`)
- Uses dedicated `DriveTaskQueueWriter` (or extends `TaskQueueWriter`) for the drive-specific queue entry format

**Queue entry format (text block):**

```
[queued: 2026-02-19 15:30] comment_id: AAAABx123 | doc_id: 1abc2def
doc_title: Q3 Strategy Planning
doc_type: document
doc_link: https://docs.google.com/document/d/1abc2def/edit?disco=AAAABx123
comment_author: Jane Smith <jsmith@concord.org>
triggered_by: cdorsey@concord.org
comment_date: Wed, Feb 19, 2026 at 3:15 PM
comment_text: We should revisit the timeline on this section
quoted_passage: Phase 2 will begin in March
surrounding_context: |
  ...the board approved the revised scope on February 3.
  >> Phase 2 will begin in March and extend through June, <<
  with quarterly milestones reported to the steering committee...
gmail_message_id: 19c64abc12345678
trigger: docs-comment-action-item
---
```

For foreign-triggered tasks (someone other than the user adding the action item):

```
triggered_by: jsmith@concord.org
[FROM: jsmith@concord.org]
```

### 3. Agent Notifier Update (small change)

**File:** `gmail-watch-service/src/gmail_watch/services/agent_notifier.py`

Add `notify_drive_task_queued()` method. This follows the same pattern as existing `notify_task_queued()` but:

- Targets the **Docs & Transcripts Agent** (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`) instead of the Email Agent
- Message format references `queued_tasks_from_drive` block and `process_drive_task_queue` tool

**Design note:** Meetings don't use a separate notifier — the Granola ingestion script (`granola_mcp_to_archival.py`) messages the agent directly. Drive comments use the Gmail Watch notification path because the trigger comes through Gmail, making it natural to extend the existing `AgentNotifier` rather than building a new notification mechanism.

### 4. `process_drive_task_queue` Tool (main work — new Letta tool)

**File:** `letta/drive_task_queue_tool.py`

A new Letta tool registered on the Docs & Transcripts Agent. This is the primary new code. It:

1. Reads the `queued_tasks_from_drive` memory block
2. Parses each `---`-delimited entry
3. For each entry:
   - Calls `Drive API comments.get(fileId, commentId)` for full comment metadata (author, text, quotedFileContent, resolved status, replies)
   - Calls `Drive API files.get(fileId, fields="mimeType,name,webViewLink")` for document metadata
   - Retrieves surrounding context based on document type:
     - **Docs:** `documents.get(documentId)` → search `body.content[]` paragraphs for quoted passage → extract ~3 paragraphs before/after
     - **Sheets:** `spreadsheets.get(spreadsheetId)` → locate cell range from comment anchor → extract surrounding cell values
     - **Slides:** `presentations.get(presentationId)` → find slide containing comment → extract slide text
   - Detects foreign triggers: if `triggered_by != cdorsey@concord.org`, annotates with `[FROM: {email}]`
   - Calls `add_extracted_tasks()` with:
     - `source_type`: `"google-drive-comment"`
     - `reference_id`: `"gdrive-comment-{doc_id}-{comment_id}"`
     - `location`: document title + deep link
     - `location_id`: `doc_id`
     - `source_text`: full comment text + quoted passage + surrounding context
     - `from_person`: comment author name + email
     - `source_context`: e.g., "Comment on Q3 Strategy Planning (Google Doc)"
4. Removes processed entries from block

**Follows Letta tool patterns:** All imports inside function body, no nested defs, try-except wrapper, `Dict[str, Any]` return type.

**OAuth scopes needed:** The tool runs in Letta sandbox and needs Google API access. It should use the same OAuth credentials pattern as other Google-integrated tools. Required scopes:
- `drive.readonly` (comments + file metadata)
- `documents.readonly` (Docs surrounding context)
- `spreadsheets.readonly` (Sheets surrounding context)
- `presentations.readonly` (Slides surrounding context)

### 5. `add_extracted_tasks` Source Type Update (small change)

**File:** `letta/extracted_tasks_tool.py`

Add `"google-drive-comment"` to `valid_source_types` set (line 113):

```python
valid_source_types = {"slack", "google-docs", "google-docs-comment", "meeting", "email", "google-drive-comment"}
```

### 6. Block Verification / Creation

Verify or create the `queued_tasks_from_drive` memory block on the Docs & Transcripts Agent (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`).

Initial block value:

```
# queued_tasks_from_drive
# Entries are separated by --- and processed by process_drive_task_queue tool.
# Format: [queued: timestamp] comment_id: X | doc_id: Y
```

### 7. Agent Extraction Guidelines Update

Update the Docs & Transcripts Agent's system prompt or instruction block to include `google-drive-comment` processing rules:

- When notified of new drive task queue entries, call `process_drive_task_queue()`
- After processing, call `add_extracted_tasks()` for each valid task
- For entries with `[FROM: {email}]`, note the external trigger in the task description
- Use `source_type: "google-drive-comment"` for all doc types

### 8. Registration Script

**File:** `letta/register_drive_task_queue_tool.py`

Boilerplate script to register the tool and attach it to the Docs & Transcripts Agent. Follows the pattern in existing `register_*.py` scripts.

## Queue Entry Field Reference

| Field | Source | Description |
|-------|--------|-------------|
| `comment_id` | Email body parsing | Google comment ID (e.g., `AAAABx123`) |
| `doc_id` | Email body parsing | Google document ID |
| `doc_title` | Email subject / Drive API | Document name |
| `doc_type` | Drive API `files.get` | `document`, `spreadsheet`, or `presentation` |
| `doc_link` | Constructed | Deep link: `https://docs.google.com/document/d/{id}/edit?disco={commentId}` |
| `comment_author` | Email body / Drive API | Who wrote the original comment |
| `triggered_by` | Email headers | Who added the `+dtasks` action item |
| `comment_date` | Drive API `comments.get` | When the comment was created |
| `comment_text` | Drive API `comments.get` | Full comment text |
| `quoted_passage` | Drive API `quotedFileContent.value` | Text the comment is anchored to |
| `surrounding_context` | Docs/Sheets/Slides API | ~3 paragraphs around the quoted passage |
| `gmail_message_id` | Gmail API | For audit trail / label removal |
| `trigger` | Constant | `docs-comment-action-item` |

## `add_extracted_tasks` Field Mapping

| `add_extracted_tasks` param | Value |
|-----------------------------|-------|
| `task_description` | Agent-composed from comment_text |
| `source_type` | `"google-drive-comment"` |
| `source_context` | `"Comment on {doc_title} ({doc_type})"` |
| `reference_id` | `"gdrive-comment-{doc_id}-{comment_id}"` |
| `source_text` | Comment text + quoted passage + surrounding context |
| `from_person` | Comment author name + email |
| `location` | `"{doc_title} — {doc_link}"` |
| `location_id` | `doc_id` |
| `source_timestamp` | Comment creation timestamp (ISO 8601) |

## Key Agents & Blocks

| Entity | ID |
|--------|----|
| Docs & Transcripts Agent | `agent-398b4f6c-6afa-493f-8063-897c6b171a0d` |
| Email Agent | `agent-b4928949-8012-4436-a3c7-a9e510785147` |
| `extracted_tasks_archive` | `archive-3f0530eb-82db-463a-a28b-f4752a95d7d5` |
| `queued_tasks_from_email` | `block-e64dcb37-aae3-416f-8565-5f2a23f53325` |
| `queued_tasks_from_slack` | `block-033a720d-1f13-44a2-a5cb-b5edde418ea1` |
| `queued_tasks_from_drive` | TBD (create during implementation) |

## Implementation Order

1. **Block creation** — Create `queued_tasks_from_drive` block, attach to Docs & Transcripts Agent
2. **`add_extracted_tasks` update** — Add `"google-drive-comment"` to valid source types
3. **Gmail Watch settings** — Add `DRIVE_TASK_QUEUE_*` config fields
4. **Gmail Watch processing** — Add `process_drive_task_queue()` to `WatchManager`
5. **Agent notifier** — Add `notify_drive_task_queued()` targeting Docs & Transcripts Agent
6. **`process_drive_task_queue` tool** — Main Letta tool (Drive API enrichment + context retrieval)
7. **Registration** — Register tool, attach to agent, update agent guidelines
8. **Docker config** — Add env vars, rebuild gmail-watch-service
9. **End-to-end test** — Add action item on a real comment, verify full pipeline

## Open Questions for Implementation

1. **Google API credentials in Letta sandbox** — The `process_drive_task_queue` tool needs Drive/Docs/Sheets/Slides API access from within the Letta sandbox. Need to verify how credentials are passed (service account JSON mounted? OAuth token from env var?).
2. **DTaskQueue Gmail label** — Verify the label exists or create it. The `+dtasks` suffix should auto-create it on first use, but the label ID needs to be discoverable by Gmail Watch.
3. **Notification email format** — The exact format of Google Docs action item notification emails needs to be confirmed by triggering one manually. The doc_id and comment_id extraction regex depends on the email body structure.
