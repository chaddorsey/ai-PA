# Unified Follow-Ups Tab — Design Spec

**Date:** 2026-03-18
**Status:** Draft
**Goal:** Centralize all post-task and post-meeting follow-up approvals in a single pa-web tab (renamed from "Drafts" to "Follow-Ups"), with type-labeled cards and a zero-LLM-cost completion→follow-up pipeline for task-sourced follow-ups.

---

## Problem Statement

Follow-up actions after task completion (Slack replies, Docs comment replies, email responses) and meeting follow-ups (Gmail drafts from meeting notes) are currently handled through different channels:
- Meeting follow-ups appear as Gmail drafts in the pa-web Drafts tab
- Task completion follow-ups are presented in chat conversation for approval
- No unified view exists for reviewing and dispatching all pending follow-ups

The OmniFocus timer system now sends completion events to the server bridge. These can trigger follow-up preparation automatically without LLM calls, since the preparation logic (`prepare_completion_feedback`) is deterministic.

## Success Criteria

1. All follow-up types appear in a single "Follow-Ups" tab in pa-web
2. Each card is visually labeled by type (Slack, Email, Meeting, Comment, Draft)
3. Task completion follow-ups are generated automatically from timer events (zero LLM cost)
4. Meeting follow-ups continue to use docs agent for LLM-composed drafts
5. Users can review, edit, approve, or reject each follow-up from the tab
6. Approved follow-ups are dispatched via the appropriate channel (Slack API, Gmail send, Docs reply)

---

## Follow-Up Types

| Type | Label | Icon | Source | Preparation | Dispatch |
|------|-------|------|--------|-------------|----------|
| **Slack Reply** | "Slack" | Slack icon | Task completed, source_type=slack | Deterministic (template + context fetch) | `post_slack_channel_reply` → Slack API |
| **Docs Comment** | "Comment" | Google Docs icon | Task completed, source_type=google-docs-comment | Deterministic (template + comment thread fetch) | `gws drive replies create` + optional resolve |
| **Meeting Follow-up** | "Meeting" | Granola/calendar icon | Meeting scan by docs agent | LLM-composed (4.1-mini) | Gmail draft → send |
| **Email Reply** | "Email" | Gmail icon | Task completed, source_type=email | Deterministic (template) | Gmail draft → send |
| **Generic Draft** | "Draft" (italic) | Gmail icon | Manual Gmail drafts with Followup label | User-created | Gmail send |

---

## Architecture

### Completion → Follow-Up Pipeline (Zero LLM Cost)

```
Timer completion event
  → Host bridge receives POST /timer-event (event=timer.stopped)
  → Bridge logs to completions.jsonl
  → Bridge calls prepare_follow_up() server-side (NO LLM)
    → Reads task's archival passage via Letta API
    → Checks: external origin? source_type?
    → If follow-up appropriate: fetches context (Slack thread, Docs comment, etc.)
    → Generates template draft
    → Writes to follow-up queue
  → Bridge relays completion summary to MC (existing behavior)
```

The key change: `prepare_completion_feedback` logic moves from an LLM tool to a **server-side function** called directly by the bridge on completion events. Same logic, zero LLM cost.

### Meeting Follow-Up Pipeline (LLM, existing)

```
Scheduled meeting scan
  → docs-and-transcripts-agent runs scan_meeting_notes
  → Agent composes follow-up drafts (LLM, 4.1-mini)
  → Creates Gmail draft with Followup label
  → Draft appears in Follow-Ups tab via existing Gmail drafts API
```

No change to this pipeline — it works and the LLM composition is valuable.

### Follow-Up Queue

A new JSONL file on the server stores pending non-Gmail follow-ups:

**File:** `/Volumes/main-drive/ai-PA/omnifocus-timer/logs/pending-followups.jsonl`

**Entry format:**
```json
{
  "id": "fu-abc123",
  "type": "slack",
  "status": "pending",
  "created_at": "2026-03-18T12:00:00Z",
  "ref_id": "c92f8ced",
  "task_description": "Review the reminder email draft",
  "from_person": "Cynthia McIntyre",
  "source_context": "Message in #mapping-time",
  "draft_message": "Done — reviewed the reminder email draft. Thanks, Cynthia!",
  "routing": {
    "tool": "post_slack_channel_reply",
    "channel": "C0A7NPWDGG3",
    "thread_ts": "1773772275.179449"
  },
  "source_comment_text": "I'd like to get a reminder email out...",
  "editable": true
}
```

### pa-web Follow-Ups Tab

The tab reads from two sources:
1. **Gmail drafts API** (existing) — meeting follow-ups and generic drafts
2. **Follow-up queue API** (new) — Slack replies, Docs comments, email replies from task completions

Both are merged and displayed as cards with type badges.

---

## UI Design

### Tab Label
Rename "Drafts" to "Follow-Ups" in the sidebar tabs.

### Card Layout

```
┌─────────────────────────────────────────────────┐
│ [Slack icon] Slack                              │
│                                                 │
│ Re: Review the reminder email draft             │
│ → Cynthia McIntyre in #mapping-time             │
│                                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ Done — reviewed the reminder email draft.   │ │
│ │ Thanks, Cynthia!                            │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│                        [Edit] [Send] [Dismiss]  │
└─────────────────────────────────────────────────┘
```

### Type Badges

Each card has a badge in the upper-left corner:

| Type | Icon | Text | Style |
|------|------|------|-------|
| Slack reply | `#` or Slack hash icon | "Slack" | Regular weight |
| Docs comment | Google Docs icon | "Comment" | Regular weight |
| Meeting follow-up | Calendar/Granola icon | "Meeting" | Regular weight |
| Email reply | Gmail envelope icon | "Email" | Regular weight |
| Generic draft | Gmail envelope icon | "Draft" | Italic |

Icons should be small (14px) SVG or emoji, with the text label in 0.75rem next to it. Badge area is a subtle pill-shaped background.

For meeting follow-ups: the existing Gmail drafts with the "Followup" label are identified by that label. The badge can be determined by checking if the draft has the "Followup" label AND was created by the meeting scan flow (metadata or label combination).

### Card Actions

| Action | Behavior |
|--------|----------|
| **Edit** | Opens inline editor for the draft message text |
| **Send** | Dispatches via the appropriate channel (Slack API, Gmail send, Docs reply) |
| **Dismiss** | Removes from queue without sending. Marks as dismissed. |

For Gmail-based follow-ups (Meeting, Email, Generic Draft), Send uses the existing Gmail send flow. For Slack and Docs, Send calls the appropriate API directly from pa-web's backend.

---

## API Endpoints

### Existing (modified)
- `GET /api/drafts` → renamed to `GET /api/followups` — returns merged list from Gmail drafts + follow-up queue
- `GET /api/drafts/<id>` → `GET /api/followups/<id>` — returns single follow-up detail
- `PUT /api/drafts/<id>` → `PUT /api/followups/<id>` — update draft text
- `POST /api/drafts/<id>/send` → `POST /api/followups/<id>/send` — dispatch follow-up
- `DELETE /api/drafts/<id>` → `DELETE /api/followups/<id>` — dismiss follow-up

### New
- `GET /api/followups/queue` — returns only the file-based follow-up queue entries
- `POST /api/followups/<id>/dismiss` — mark as dismissed without sending

### Bridge Endpoint (existing, extended)
The `/timer-event` handler in the host bridge gains follow-up preparation logic:
- On `timer.stopped` or `timer.auto-stopped`: after logging, call `prepare_follow_up()`
- `prepare_follow_up()` reuses `prepare_completion_feedback` logic server-side
- Writes pending follow-ups to `pending-followups.jsonl`

---

## Implementation Notes

### Bridge Integration

The follow-up preparation logic from `prepare_completion_feedback` needs to be extracted into a standalone function callable from the bridge (Node.js). Two options:

**Option A:** Port the logic to Node.js in the bridge. More work but keeps it in-process.

**Option B:** The bridge calls a Python script via subprocess. Simpler — reuses existing code.

**Option C:** The bridge makes a Letta API call to run the tool on a lightweight agent. Costs one 4.1-mini call but reuses existing tool code unchanged.

Recommended: **Option B** — extract `prepare_completion_feedback` into a standalone Python script that reads from archival memory and writes to the follow-up queue. The bridge calls it via subprocess on completion events.

### Gmail Draft Type Detection

To distinguish meeting follow-ups from generic drafts in the Gmail list:
- Meeting follow-ups have the "Followup" label AND were created programmatically
- Check for metadata markers in the draft body or a specific label combination
- The docs agent could add a header like `X-PA-Type: meeting-followup` or a specific label like "PA/Meeting-Followup"

### Backward Compatibility

- Existing `/api/drafts` endpoints continue to work (aliased)
- Gmail drafts flow is unchanged
- The follow-up queue is additive — it doesn't replace Gmail drafts, it supplements them

---

## Phased Implementation

### Phase 1: Rename tab + type badges on existing drafts
- Rename "Drafts" to "Follow-Ups" in sidebar
- Add type badge detection for Gmail drafts (Meeting vs. Draft based on labels)
- No new follow-up types yet

### Phase 2: Follow-up queue + Slack/Docs cards
- Create `pending-followups.jsonl` queue
- Add follow-up queue API endpoints
- Merge queue entries with Gmail drafts in the tab
- Add Send/Dismiss for Slack and Docs types

### Phase 3: Auto-trigger from completions
- Bridge calls `prepare_follow_up()` on timer.stopped events
- Writes to the follow-up queue automatically
- Zero LLM cost for the preparation step

### Phase 4: Enhanced editing and threading
- Inline editing for all follow-up types
- Thread preview (show original message + existing replies)
- Batch operations (send all, dismiss all read)
