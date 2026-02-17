# Meeting Notes Processing Pipeline — Design Document

**Date:** 2026-02-17
**Status:** Approved
**Agent:** Granola agent (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`)

## Goal

Automatically extract tasks and generate follow-up emails from meeting notes. Every archived meeting triggers a scan that identifies action items (from explicit user markers AND semantic analysis of content), routes personal tasks to the extraction pipeline, and drafts a Decisions / Next Actions follow-up email.

## Architecture: Hybrid Extraction (Approach C)

Deterministic regex extraction in tools for high-confidence marker parsing. LLM reasoning in the agent for semantic scanning, pointer expansion, and D/NA synthesis.

---

## Section 1: Marker Convention

Users type markers in Granola's private notes during meetings. Markers survive in the `private_notes` field (verified — Granola's AI cleanup only affects the generated summary, not user-authored notes).

### Marker Types

| Marker | Meaning | Pipeline Destination |
|--------|---------|---------------------|
| `[ ]` or `[]` | My task | Task queue + D/NA email |
| `[;]` | Someone else's task | D/NA email only |
| `>` | Pointer needing expansion | Agent expands from transcript, feeds D/NA |
| (unmarked) | Contextual note | Preserved, available for semantic scan |

### Parsing Rules

Regex: `^\s*(?:[-*]\s*)?(\[;\]|\[\s?\]|>)\s+(.+)$`

Handles:
- `[;] Rebecca to create a list of tasks` — line start
- `- [ ] Send budget to finance` — after bullet prefix
- `* [;] task` — after asterisk bullet
- `> discuss pricing model` — pointer at line start

### D/NA Section Header

`D/NA` on its own line is an informational section header (confirms user intent) but not required for routing — `[;]` items route to the D/NA email regardless of whether a header is present.

### Verified Against Real Data

Rebecca meeting (2026-02-17) `private_notes`:
```
D/NA

[;] Rebecca to create a list of tasks  – needs section
[;] Rebecca to start working on description of intervention
[;] Rebecca to contact Rose to get description of her research and approach
[;] Rebecca to ask Lisa to find budget numbers for Rose and graduate student from last year of M2Studio
```

---

## Section 2: Pipeline Architecture

Every new meeting triggers processing regardless of whether user notes exist.

```
Archive (existing — every 15 min via Granola MCP)
    |
    v
Enrich Metadata
  |-- Calendar event (attendees, description, linked docs)
  |-- Google Docs content (if URL in notes or calendar)
  '-- Store enriched metadata passage
    |
    v
Scan (always both layers)
  |-- Layer 1: Deterministic marker extraction from private_notes
  |     [ ], [;], > markers parsed by regex
  |
  |-- Layer 2: Agent semantic scan of:
  |     |-- AI summary
  |     |-- Transcript
  |     '-- Linked document content
  |
  '-- Agent merges both layers:
       - Markers = high-confidence anchors
       - Semantic hits = augmentation + new discoveries
       - Deduplication (semantic hit covered by marker -> enrich, don't duplicate)
    |
    v
Outputs (parallel)
  |-- [ ] items -> queued_tasks_from_meetings block
  |     -> existing extracted_tasks pipeline
  |
  '-- ALL items -> prepare_meeting_followup()
      |-- My Next Actions ([ ] items + semantic discoveries for me)
      |-- Others' Next Actions ([;] items + semantic discoveries for others)
      |-- Decisions (from summary)
      '-- -> Gmail Draft
```

### Phase Details

**Phase 1: Archive** (existing, no changes needed)
- Granola MCP ingestion runs every 15 min
- `### My Notes` now preserved in archival passages (fix applied 2026-02-16)

**Phase 2: Enrich** — `enrich_meeting_metadata` tool
- Runs on every new meeting regardless of notes
- Calendar event lookup for attendees, description, linked docs
- Google Doc content fetch if URL found in notes or calendar description
- Updates meeting's metadata passage with enriched data

**Phase 3: Scan** — `scan_meeting_notes` tool + agent reasoning
- Layer 1 (tool): deterministic regex extraction of markers + URL extraction + transcript excerpt retrieval for pointers
- Layer 2 (agent): semantic scan of all scannable content for additional action items and context augmentation
- Always runs both layers — markers are anchors, semantic scan catches what wasn't explicitly noted

**Phase 4: Follow-up** — `prepare_meeting_followup` tool
- Takes agent's merged action items and creates Gmail draft
- ALL action items appear in the email (both `[ ]` and `[;]` items)
- `[ ]` items additionally route to the task extraction queue

---

## Section 3: Scan Package (Tool -> Agent Data Contract)

`scan_meeting_notes` returns a structured object with all scannable content clearly labeled by source. The agent never receives "go find content" — it receives "here is the content, scan it."

### Return Structure

```json
{
  "meeting_id": "9b86c082-...",
  "meeting_title": "Proposal Check in Rebecca",
  "participants": ["Rebecca Ellis", "Amy Pallant"],
  "meeting_date": "2026-02-17T18:00",

  "marker_extractions": {
    "my_tasks": [
      {"marker": "[ ]", "text": "Send budget to finance", "line": 12}
    ],
    "their_tasks": [
      {"marker": "[;]", "text": "Rebecca to create a list of tasks", "line": 18}
    ],
    "pointers": [
      {"marker": ">", "text": "discuss pricing model", "line": 8}
    ]
  },

  "scannable_content": [
    {
      "source": "private_notes",
      "label": "User's meeting notes",
      "text": "...",
      "context_lines": ["unmarked lines not matching any marker"]
    },
    {
      "source": "ai_summary",
      "label": "Granola AI summary",
      "text": "..."
    },
    {
      "source": "linked_doc",
      "label": "Google Doc: 'Proposal One-Pager'",
      "url": "https://docs.google.com/...",
      "text": "[fetched doc content, plaintext]",
      "extraction_note": "Full document content (revision filtering v2)"
    },
    {
      "source": "transcript_excerpt",
      "label": "Transcript sections matching pointer '> discuss pricing model'",
      "text": "[relevant transcript window]"
    }
  ],

  "has_user_notes": true,
  "doc_urls_found": ["https://docs.google.com/..."]
}
```

### Design Principles

- Each `scannable_content` item labeled with `source` for provenance tracking
- Agent weights by confidence: markers > user notes context > AI summary > linked docs > transcript inference
- If a doc fetch fails, the tool returns an error note in that slot (never silently omits)
- Linked doc content fetched and returned by the tool — agent never navigates to URLs
- v1: full doc content returned. v2: could filter to meeting-window edits via Google Docs revision API

### Known Risk: Long Documents

Long-running meeting notes documents may produce large `scannable_content` items. v1 accepts this trade-off; if it becomes a problem, the tool can truncate with a note or extract only sections with task-like indicators.

---

## Section 4: Follow-up Email (D/NA Draft)

`prepare_meeting_followup` formats action items into a Gmail draft.

### Input (from agent)

```json
{
  "meeting_id": "...",
  "meeting_title": "Proposal Check in Rebecca",
  "meeting_date": "2026-02-17",
  "participants": ["Rebecca Ellis <rellis@concord.org>", "Amy Pallant <apallant@concord.org>"],
  "decisions": ["Rose Zbiek confirmed as partner", "Two-year project structure"],
  "my_actions": ["Send budget to finance", "Review one-pager draft by Friday"],
  "their_actions": [
    {"who": "Rebecca", "action": "Create a list of tasks"},
    {"who": "Rebecca", "action": "Start working on description of intervention"}
  ]
}
```

### Email Format

```
Subject: Re: Proposal Check in Rebecca -- D/NA

Hi all,

Here's a summary of our Proposal Check-in (Feb 17):

## Decisions
- Rose Zbiek confirmed as partner
- Two-year project structure: pre-service Y1, in-service Y2

## Next Actions
**Chad:**
- Send budget to finance
- Review one-pager draft by Friday

**Rebecca:**
- Create a list of tasks -- needs section
- Start working on description of intervention
- Contact Rose for description of research
- Ask Lisa for budget numbers from M2Studio

Let me know if I missed anything.

Best,
Chad
```

### Behavior

- Creates Gmail **draft** (never auto-sends) — user reviews and edits before sending
- Uses existing `create_draft` tool from `gmail_tools.py`
- Participant emails extracted from Granola's `known_participants` field
- Actions grouped by person for readability
- Returns draft ID so user can find and review it
- Email template will be refined after initial testing

---

## Section 5: Trigger & Agent Ownership

### Agent

Granola agent (`agent-398b4f6c-6afa-493f-8063-897c6b171a0d`) owns the full pipeline: ingestion, enrichment, scan, and follow-up.

### Trigger Flow

1. `granola_mcp_to_archival.py` ingests a new meeting (existing, every 15 min)
2. After successful archival, script sends a message to the Granola agent: "New meeting archived: {title} ({meeting_id}). Run post-meeting processing."
3. Agent's system prompt instructs:
   - Call `scan_meeting_notes(meeting_id)` to get the scan package
   - Review all `scannable_content` items for action items beyond markers
   - Expand `>` pointers using provided transcript excerpts
   - Call `prepare_meeting_followup(...)` with merged results
   - Route `[ ]` items to `queued_tasks_from_meetings` block

### New Memory Block

`queued_tasks_from_meetings` — parallels `queued_tasks_from_email`. Entries follow the same format and get picked up by the existing extracted_tasks pipeline.

### System Prompt Additions

- Marker convention reference (Section 1)
- Post-meeting processing protocol (scan -> merge -> follow-up -> queue tasks)
- Confidence weighting: markers > user notes context > AI summary > linked docs > transcript inference

---

## New Tools Summary

| Tool | Type | Purpose |
|------|------|---------|
| `scan_meeting_notes` | Letta tool | Marker extraction, doc fetch, transcript excerpt, scan package assembly |
| `enrich_meeting_metadata` | Letta tool | Calendar lookup, Google Doc content fetch, metadata passage update |
| `prepare_meeting_followup` | Letta tool | Format D/NA email, create Gmail draft |

---

## Dependencies & Prerequisites

- Granola `private_notes` preservation (done — 2026-02-16 fix)
- Gmail `create_draft` tool (exists on Granola agent via `gmail_tools.py`)
- Google Docs API access (for linked doc content fetch)
- Calendar API access (for event metadata enrichment)
- `queued_tasks_from_meetings` memory block (to create)
- `extracted_tasks` pipeline (exists)

## v2 Considerations (Not in v1)

- Google Docs revision API filtering (meeting-window edits only)
- Long document truncation/section extraction
- Zoom chat / Slack thread enrichment sources
- Email template customization per meeting type
- Backfill processing of historical meetings with notes
