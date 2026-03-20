# Task Duration Estimation — Design Spec

**Date:** 2026-03-18
**Status:** Approved

## Overview

Add LLM-generated time estimates to the task extraction pipeline. Estimates appear as editable inline badges on task cards, flow through confirmation into OmniFocus as `estimatedDuration`, and seed the timer widget's time tracking system via an `Agent Estimate` note line.

## Data Flow

```
Extraction (Letta agent)
  → ESTIMATE: 15 in archival passage TASK METADATA section

Sidebar load (/api/tasks/<ref_id>)
  → parses estimate_minutes from passage → returns to frontend

Task card display
  → inline ⏱ 0:15 badge in metadata row (click to edit H:MM)

Confirm dialog
  → read-only ⏱ 0:15 display below task name textarea

OmniFocus creation
  → estimatedDuration param (minutes) from card value
  → "Agent Estimate: 15m 00s" standalone line in note
  → NO time tracking block (timer creates this at task start)

Timer start (later)
  → reads estimatedDuration → Original Estimate
  → finds standalone "Agent Estimate:" line, moves inside block
  → creates full --- Time Tracking --- block
```

## Changes by Component

### 1. Letta Agent Extraction Prompt

**File:** `task_extraction_tool_use_guidelines` memory block on tasks agent

**Change:** Add instruction to the extraction guidelines requiring the agent to include a time estimate in the archival passage. The agent already has full task context during enrichment.

**Passage format addition** (under TASK METADATA):
```
TASK METADATA
- Estimate: 15
```

Value is always an integer in minutes. The LLM should estimate based on task description, source context, URLs, and any other enrichment data available.

### 2. Backend Passage Parser

**File:** `pa-web-ui/app.py` — `parse_archival_passage()` function

**Change:** Parse `- Estimate: <N>` from the TASK METADATA section. Add `estimate_minutes` (int or null) to the returned detail object.

**API response addition** (GET `/api/tasks/<ref_id>`):
```json
{
  "estimate_minutes": 15,
  ...existing fields...
}
```

### 3. Backend PATCH Endpoint

**File:** `pa-web-ui/app.py` — PATCH `/api/tasks/<ref_id>`

**Change:** Accept optional `estimate_minutes` field. Update the archival passage:
- If `- Estimate: <N>` exists → replace the value
- If not → add `- Estimate: <N>` under TASK METADATA (create section if needed)

### 4. Frontend Task Card — Inline Estimate Badge

**File:** `pa-web-ui/static/js/sidebar.js` — `buildTaskCard()`

**Change:** Add `⏱ H:MM` badge in the card metadata row (next to ref_id and origin badge).

**Display rules:**
- Value comes from `task.estimate_minutes` (loaded via accordion detail fetch, or from a new field on the task list endpoint)
- Format: `H:MM` (e.g., `0:15`, `1:30`, `2:00`)
- Dim placeholder `⏱ —` if no estimate (shouldn't happen for new tasks)

**Edit behavior:**
- Click badge → becomes an `<input type="text">` with H:MM pattern
- Enter/blur → parse H:MM back to minutes, PATCH to backend
- Escape → cancel edit
- Same pattern as existing inline description edit

**Data flow for initial load:** The task list endpoint (`/api/tasks`) currently returns only `extracted_time`, `ref_id`, `origin`, `description` parsed from the block line. The estimate lives in the archival passage (not the block). Two options:

- **Option A:** Add estimate to the block line format: `[extracted_time: ...; ref_id: ...; origin: ...; est: 15] description`
- **Option B:** Fetch estimate lazily when accordion opens (already fetches full details)

**Decision: Option A** — add `est: <N>` to the block line format so the estimate is available immediately without an extra API call. The extraction tool writes it; the parser reads it.

**Block line format change:**
```
[extracted_time: 2026-03-18 01:57; ref_id: 67f9073d; origin: user-indicated; est: 15] Review draft reminder email
```

**Backend parser update** (`parse_task_block()`): Extract optional `est` field from the block line regex.

**Task list response addition:**
```json
{
  "extracted_time": "2026-03-18 01:57",
  "ref_id": "67f9073d",
  "origin": "user-indicated",
  "estimate_minutes": 15,
  "description": "Review draft reminder email"
}
```

### 5. Confirm Dialog — Read-Only Estimate

**File:** `pa-web-ui/static/js/sidebar.js` — `onConfirm()` / confirm dialog setup

**Change:** Below the task name textarea in the "Add to OmniFocus" dialog, show a read-only estimate display:

```
Task name: [editable textarea]
⏱ 0:15 estimated
```

This uses the current value of `task.estimate_minutes` (which may have been edited on the card). It's informational only — no editing here.

### 6. OmniFocus Task Creation

**File:** `pa-web-ui/static/js/sidebar.js` — `confirmOFDialog()`
**File:** `pa-web-ui/app.py` — `/api/tasks/omnifocus-create`

**Frontend change:** Include `estimatedDuration` (minutes) in the create request body, sourced from the task's current estimate_minutes value.

**Backend change:** Pass `estimatedMinutes` to the OmniFocus bridge `createTask` call.

**Note change:** In `buildOFNote()`, add a standalone line:
```
Agent Estimate: 15m 00s
```

This line goes near the top of the note (after `ref_id:` and `Origin:`), NOT inside a time tracking block. The timer widget will find it and move it inside the block when it creates one.

**Duration format:** Use the timer's format: `Xm 00s` for < 1 hour, `Xh YYm 00s` for >= 1 hour. Always include seconds as `00s` since this is an estimate, not a measurement.

### 7. Timer Parser Update

**File:** `omnifocus-timer/omnifocus-timer.omnifocusjs/Resources/timerLib.js` — `parseNoteBlock()`

**Change:** After parsing the time tracking block (if it exists), also scan the full note text for a standalone `Agent Estimate: <duration>` line outside the block. If found and no agent estimate was parsed from inside the block, use it.

When `writeNoteBlock()` creates the block for the first time, include the agent estimate inside the block. The standalone line in the note body is left as-is (the block version takes precedence on subsequent reads).

### 8. Extraction Tool Update

**File:** `letta/extracted_tasks_tool.py` — `add_extracted_tasks()`

**Change:** Accept optional `estimate_minutes` parameter. Include it in:
- The block line: `est: <N>` field
- The archival passage: `- Estimate: <N>` under TASK METADATA

## Format Reference

| Context | Format | Example |
|---------|--------|---------|
| Archival passage | Integer minutes | `- Estimate: 15` |
| Block line | Integer minutes | `est: 15` |
| API response | Integer minutes | `"estimate_minutes": 15` |
| Card display | H:MM | `0:15` |
| Card edit input | H:MM | `0:15` |
| OmniFocus estimatedDuration | Integer minutes | `15` |
| Note Agent Estimate line | Timer duration format | `Agent Estimate: 15m 00s` |
| Timer Original Estimate | Timer duration format | `Original Estimate: 15m 00s` |

## What This Design Does NOT Include

- **No time tracking block at creation** — timer creates this at task start
- **No Original Estimate at creation** — timer copies estimatedDuration at start
- **No re-estimation on description edit** — future enhancement
- **No reinforcement learning** — future enhancement
- **No estimate quality tracking** — future enhancement (compare agent vs actual)
