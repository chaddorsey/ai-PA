# Compaction-Resilient Meeting Task Extraction — Design Document

**Date:** 2026-02-20
**Status:** Approved
**Amends:** `2026-02-17-meeting-notes-processing-design.md` (Section 2 pipeline, Section 5 trigger)
**Agent:** docs-and-transcripts-agent (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`)

## Problem

The meeting processing pipeline (designed 2026-02-17) requires multiple consecutive agent tool calls: `scan_meeting_notes` -> agent interprets -> `add_extracted_tasks`. Letta's context compaction fires between agent turns and destroys the scan results before the agent can act on them. Result: 10 successful scans on 2026-02-20, zero meeting tasks extracted.

Drive comment extraction works because it uses a queue block (durable core memory) rather than ephemeral conversation. Meeting task extraction needs the same pattern.

## Goal

Make meeting task extraction survive context compaction by persisting marker-extracted candidates to the `queued_tasks_from_meetings` memory block inside the `scan_meeting_notes` tool call — a single atomic operation. The agent then processes durable queue entries at its own pace using its full context and memory.

## Design

### Core Change: Queue-at-Scan

`scan_meeting_notes` gains one new responsibility. After extracting markers from private notes, it writes task candidate entries directly to the `queued_tasks_from_meetings` block via Letta API PATCH.

**Gate condition:** Only writes to queue when `my_tasks` or `their_tasks` markers are found. No markers = no queue entries. `pointers` and `decisions` are not queued (they feed the followup email).

**The tool still returns the full scan package** (marker_extractions, scannable_content, doc_urls_found) unchanged. The queue write is a side-effect, not a replacement. If compaction doesn't hit, the agent can still use the ephemeral results for the email flow.

### Queue Entry Format

Each `my_tasks` or `their_tasks` marker produces one entry using the existing block format with additions:

```
[queued: 2026-02-20 14:30; scan_id: a7f3b2c1] meeting_id: 427cb2b1
title: Chad/Hee-Sun
date: 2026-02-20
participants: Chad Dorsey, Hee-Sun Kim
granola_link: https://notes.granola.ai/d/427cb2b1
marker_type: my_tasks
task: Follow up on the budget review before March board meeting
deadline_hint: before March board meeting
deadline_source: notes
urls: https://docs.google.com/spreadsheets/d/abc123
---
```

**Fields:**
- `scan_id` — short hash (first 8 chars of uuid4) for cleanup targeting via `add_extracted_tasks`
- `marker_type` — `my_tasks` or `their_tasks`. Agent uses this to frame ownership.
- `deadline_hint` / `deadline_source` — from scan's deadline extraction (omitted if none found)
- `urls` — from `doc_urls_found` (private_notes URLs only, per existing rules). Omitted if none.
- `meeting_id`, `title`, `date`, `participants`, `granola_link` — from meeting metadata already available in the tool

**Size:** ~300-500 chars per entry. Block limit is 20,000 chars (~40-60 entries). If appending would exceed the limit, the tool logs a warning and skips the queue write. The scan package still returns normally — degraded but not broken.

### Agent Processing Flow

The agent processes queue entries the same way it processes `queued_tasks_from_drive`:

1. Agent sees entries in `queued_tasks_from_meetings` (core memory, always visible)
2. For each entry, agent interprets using its full context — projects, relationships, patterns
3. If the entry is a real task: call `add_extracted_tasks` with:
   - `cleanup_block_id=block-809efd9b-e2ca-4d11-af89-9a1c7710716c`
   - `cleanup_entry_identifier={scan_id}`
   - `related_urls` from the entry's `urls` field
   - `due_date` from `deadline_hint` (agent applies confidence judgment)
   - Other fields per `task_extraction_process_docs_transcripts` rules
4. If not actionable: agent removes entry from queue (core_memory_replace or similar)
5. For `their_tasks` entries: agent decides if a follow-up task is implied for the user

**Archival lookup for deeper context:** The agent can search archival via `?search={meeting_id}` to read the full transcript if the queue entry alone isn't sufficient for interpretation.

### Instruction Updates

**`meeting_processing_chain` block — Step 4 update:**

Current: "For my_actions items, also call add_extracted_tasks following the task_extraction_process_docs_transcripts block rules."

Updated: "Check queued_tasks_from_meetings for pending entries written by scan_meeting_notes. For each entry, interpret the marker text using your knowledge of the user's projects and context. If it's a real task, call add_extracted_tasks with cleanup_block_id=block-809efd9b-e2ca-4d11-af89-9a1c7710716c and cleanup_entry_identifier={scan_id}. If not actionable, remove from queue. For their_tasks entries, decide if a follow-up task is implied. You can search archival for the full meeting transcript if needed."

**`notify_agent_new_meeting` message update:**

Current: "Run post-meeting processing: call scan_meeting_notes with this meeting_id, review the scan package..."

Updated: Adds "Any task markers found have been queued to queued_tasks_from_meetings — process them after completing the scan review and followup email."

## Files Changed

| File | Change |
|------|--------|
| `letta/meeting_scan_tool.py` | Add queue-writing after marker extraction: GET block, append entries, PATCH. Overflow guard at 20K chars. |
| `letta/granola_mcp_to_archival.py` | Update `notify_agent_new_meeting` message text |
| `meeting_processing_chain` block | Update Step 4 to reference queue processing with cleanup IDs |

## Files NOT Changed

- `letta/extracted_tasks_tool.py` — already supports `cleanup_block_id` / `cleanup_entry_identifier`
- `letta/meeting_followup_tool.py` — email draft flow is independent
- `letta/register_meeting_processing_tools.py` — re-run to push updated tool source (no script changes)
- `task_extraction_process_docs_transcripts` block — formatting rules unchanged
- `task_extraction_tool_use_guidelines` block — unchanged

## Why This Works

| Property | Drive comments (working) | Meeting tasks (broken) | Meeting tasks (fixed) |
|----------|------------------------|----------------------|---------------------|
| Data lands in | Queue block (core memory) | Tool return (conversation) | Queue block (core memory) |
| Survives compaction? | Yes | No | Yes |
| Agent interprets with context? | Yes | Yes (if it gets there) | Yes |
| Atomic cleanup? | Yes (cleanup_block_id) | N/A | Yes (scan_id) |

## Testing

1. Call `scan_meeting_notes` on a meeting with known markers
2. Verify entries appear in `queued_tasks_from_meetings` block
3. Send agent a message to process the queue
4. Verify `add_extracted_tasks` is called with correct fields
5. Verify queue entry is removed after extraction
6. Test with a meeting with no markers — verify no queue entries written
7. Test overflow guard — verify warning logged and scan still returns normally
