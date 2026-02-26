# Meeting Task Extraction Pipeline + Origin Metadata

**Date:** 2026-02-25
**Status:** Design approved, implementation pending
**Related:** [WIP System Updates](2026-02-23-wip-system-updates.md) (items 3, 5), [Meeting Processing Design](2026-02-17-meeting-notes-processing-design.md)
**Future phase:** [Intelligent Task Review](2026-02-25-intelligent-task-review-proto-design.md)

---

## Problem

The meeting task extraction pipeline has a gap: `scan_meeting_notes` writes `[c]` markers to the `queued_tasks_from_meetings` block, but nothing ever processes those entries. No trigger exists to call `add_extracted_tasks`, so tasks accumulate without being extracted. The block reached 19,972/20,000 chars and overflowed. Meanwhile, the Slack pipeline works correctly because `send_to_tasks.py` includes a `_trigger_extraction` step that messages the Pulse agent.

Additionally, `prepare_meeting_followup` duplicates the queue write (same tasks, same block), contributing to overflow.

Finally, `add_extracted_tasks` has no way to distinguish user-indicated tasks (from `[c]` markers or Slack shortcuts) from agent-identified tasks (future capability). This distinction is critical for the user's review workflow at the OmniFocus confirmation step.

## Design

### 1. Add `origin` field to `add_extracted_tasks`

New optional parameter:

```
origin: Optional[str] — How this task was identified. One of:
  "user-indicated" — User explicitly marked this as a task ([c] marker, Slack shortcut, etc.)
  "agent-identified" — Agent inferred this is a task from context analysis
  Default: None (omit if not determinable)
```

Carried through to:
- The `extracted_tasks` block entry: `[extracted_time: ...; ref_id: ...; origin: user-indicated] Task description`
- The archival passage: new `ORIGIN` line in the passage text
- Tags: `origin:user-indicated` or `origin:agent-identified`

### 2. Add extraction trigger to `scan_meeting_notes`

After the scan tool writes `[c]` markers to the queue block (existing behavior), it also calls `add_extracted_tasks` via HTTP for each `[c]` task — directly, within the same tool execution. This is a lightweight mechanical extraction, not a deep consideration step.

Each call includes:
- `task_description`: The `[c]` marker text (already "Chad to ..." prefixed)
- `source_type`: `"meeting"`
- `source_context`: `"Meeting notes marker [c] from {meeting_title}"`
- `reference_id`: `"meeting-{meeting_id}"`
- `source_text`: The marker's line from private notes
- `from_person`: `"Chad Dorsey (note creator)"`
- `location`: Meeting title
- `location_id`: Meeting ID
- `source_timestamp`: Meeting date in ISO 8601
- `origin`: `"user-indicated"`
- `related_urls`: Any doc URLs found in private notes
- `due_date`/`defer_date`: From `deadline_hint` if present
- `cleanup_block_id`: `block-809efd9b-e2ca-4d11-af89-9a1c7710716c`
- `cleanup_entry_identifier`: The `scan_id` for this entry

This closes the gap: tasks flow from queue → extracted_tasks → archival atomically. The queue entry is cleaned up in the same operation.

**Why tool-level extraction rather than agent-triggered:** The scan → followup chain already suffered from context compaction losing the agent's instruction. Adding a third agent step (extraction) would compound this fragility. Direct HTTP calls from within the tool are reliable and atomic. The agent's consideration opportunity is preserved for the future intelligent review phase (see proto-design).

### 3. Remove duplicate queue write from `prepare_meeting_followup`

The entire "Queue my_actions to queued_tasks_from_meetings block" section (lines 213-265) is removed. The scan tool already handles queue writes and extraction. The followup tool's job is email drafting only.

### 4. Update Slack pipeline with `origin` field

`send_to_tasks.py`'s `_trigger_extraction` message updated to include:
- `origin: user-indicated` instruction for the agent when calling `add_extracted_tasks`

### 5. Clean stale queue block

Clear the `queued_tasks_from_meetings` block (19,972 chars of unprocessed entries). These tasks are from past meetings and were never extracted — they're stale. Future entries will be cleaned up atomically by the extraction step.

---

## Changes by file

| File | Change |
|------|--------|
| `letta/extracted_tasks_tool.py` | Add `origin` parameter, carry to block entry + passage + tags |
| `letta/meeting_scan_tool.py` | Add HTTP calls to `add_extracted_tasks` for each `[c]` marker after queue write |
| `letta/meeting_followup_tool.py` | Remove queue write section (lines 213-265) |
| `slackbot/listeners/shortcuts/send_to_tasks.py` | Add `origin: user-indicated` to trigger message |
| `letta/register_meeting_processing_tools.py` | Re-register scan tool |
| Letta API | Re-register `add_extracted_tasks` on relevant agents |

## Risks

- **Scan tool becomes heavier:** Each `[c]` marker adds an HTTP round-trip. With 2-3 markers per meeting this is fine. A meeting with 10+ markers would add noticeable latency. Non-fatal: extraction failures don't block the scan return.
- **Tool-level extraction bypasses agent consideration:** This is intentional for now. The intelligent review phase (proto-design) addresses this by adding a post-extraction consideration step. The queue still exists as the durable record; extraction is additive.
- **Re-registration required:** Both `scan_meeting_notes` and `add_extracted_tasks` need re-registration after code changes. Multiple agents have `add_extracted_tasks` attached.

## What this enables

- Meeting `[c]` tasks reach `extracted_tasks` automatically (currently broken)
- User-indicated vs agent-identified tasks are distinguished in the archive
- Queue block stops overflowing (atomic cleanup on extraction)
- Foundation for the intelligent review phase (origin metadata, extraction infrastructure)
