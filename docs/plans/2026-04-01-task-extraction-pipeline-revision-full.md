# Standardized Task Pipeline: Initiation → Enrichment Architecture

## Context

Task extraction currently flows through four separate pipelines (Slack shortcuts, email forwards, meeting notes, Google Docs comments), each with different architectures, different levels of context capture, and different agent routing. The email pipeline is broken (drops full body, emails stuck in queue). The Google Docs comment pipeline is partially built but not fully connected. There is no standardized enrichment layer or "work packet" concept.

Chad has articulated a clear vision: separate **initiation** (capture the spark + immediate context, highly automatable) from **enrichment** (backtracing, work packet creation, reasoning-heavy). Gate enrichment depth by confidence (user-indicated = invest more pre-confirmation; agent-identified = defer heavy enrichment). Architect toward progressive agent autonomy.

## The Four Pipeline Stages

```
CAPTURE → FORMULATE → ENRICH → CONFIRM/ACT
```

| Stage | Nature | Who | Output |
|-------|--------|-----|--------|
| **CAPTURE** | Automated, no LLM | Service code (slackbot, gmail-watch, granola-ingest) | Spark Record in `spark_queue` block |
| **FORMULATE** | LLM reasoning | Tasks agent (agent-dd15479e) | Extracted task in `extracted_tasks` block + archival passage |
| **ENRICH** | Reasoning-heavy | MC (deep/immediate) or sleeptime (background) | Updated archival passage with work packet |
| **CONFIRM/ACT** | Human review | User via sidebar + tasks agent for transitions | OmniFocus task created |

## Spark Record: Standardized Intermediate Format

All four sources produce the same structure, written to a single `spark_queue` block on the tasks agent. Replaces `queued_tasks_from_email` and `queued_tasks_from_drive` blocks, and the Slack direct-send pattern.

### Schema

```json
{
  "spark_id": "a1b2c3d4",
  "captured_at": "2026-04-01T12:00:00-04:00",
  "source_type": "email|slack|meeting|google-docs-comment",
  "origin": "user-indicated|agent-identified",

  "reference_id": "email-19d435a26f2df099",
  "source_text": "<inline content OR fetch instruction>",
  "from_person": "Name <email>",
  "location": "#channel-name | email subject | meeting title | doc title",
  "location_id": "channel_id | message_id | meeting_id | doc_id",
  "permalink": "https://...",
  "related_urls": ["url1", "url2"],

  "marker_type": "explicit|pointer|null",
  "task_hint": "marker text if present",
  "user_notes": "free-form context",

  "surrounding_context": "thread/nearby content",
  "participants": ["Name <email>"],
  "document_metadata": {"title": "...", "type": "...", "link": "..."},

  "fetch_hint": "gmail:MESSAGE_ID | null"
}
```

### Handling Large Source Content (Emails, Meeting Transcripts)

The `spark_queue` block has a size limit and must stay compact. For sources where the full content is large (email bodies, meeting transcripts), the spark uses a **reference-and-fetch** pattern rather than inlining the full text:

- **`source_text`**: Contains enough inline context for initial evaluation — user notes above the forward delimiter, the email snippet (first 500 chars), or the AI summary for meetings. NOT the full body.
- **`fetch_hint`**: A retrieval instruction the tasks agent uses during formulation to get the full content. Format: `"gmail:MESSAGE_ID"` for email, `"granola:MEETING_ID"` for meetings. Null for Slack (message is already inline and short) and Docs comments (already enriched by DriveEnricher).

During **formulation-time enrichment** (Phase A), the tasks agent reads the spark, sees the `fetch_hint`, and calls the appropriate tool (`run_gws("gmail get MESSAGE_ID")` or archival search for the meeting) to load full content before formulating. This keeps sparks compact (~500-800 chars each) while ensuring the formulation step has access to everything.

For **Slack messages**: typically short enough to inline fully in `source_text`. No `fetch_hint` needed.
For **Docs comments**: DriveEnricher already captures comment text + quoted passage + surrounding paragraphs at capture time. Inline in `source_text`. No `fetch_hint` needed.
For **Emails**: `source_text` = user notes + first 500 chars of body. `fetch_hint` = `"gmail:MESSAGE_ID"`.
For **Meetings**: `source_text` = marker text + AI summary excerpt. `fetch_hint` = `"granola:MEETING_ID"` (tasks agent searches archival for full meeting passage).

## Enrichment: Two Distinct Phases

Enrichment is not a single step — it separates into **formulation-time enrichment** (lightweight, needed to produce a good task statement) and **work packet assembly** (heavyweight, needed to make a task immediately actionable).

### Phase A: Formulation-Time Enrichment (during FORMULATE stage)

Even with user-indicated tasks, the spark often needs contextual scanning to produce a cogent task statement. A `[c] Kate proposal` marker in meeting notes is user-indicated but not self-explanatory — the tasks agent needs to look at surrounding context to formulate "Review Kate's STEMK12 proposal and provide feedback on budget section."

**Codified first-layer enrichment protocol** (tasks agent, during formulation):

1. **Is the task statement self-contained?** If `task_hint` is already a complete verb-led sentence with a clear done-state, skip to extraction. If it's a fragment, pointer, or absent, proceed.
2. **Resolve the source text**: Read the full spark content. For pointers (`>`), the task_hint is a gist — expand from `source_text` + `surrounding_context`.
3. **Resolve linked resources**: If `related_urls` contains Drive/Docs links, fetch enough metadata (title, owner, type) via `run_gws` to disambiguate what the artifact is.
4. **Fetch immediate conversation context** (only if still ambiguous):
   - Slack: fetch thread replies and/or nearby messages via `run_slack`
   - Email: fetch the full message + thread context via `run_gws` (message + thread APIs)
   - Docs comment: surrounding paragraphs already in spark (via DriveEnricher)
5. **Micro-backtrace (bounded, 1 additional hop; only if still ambiguous):** Find the *defining node* for the deliverable/done-state.
   - Slack: search within the same channel/DM for earlier mentions of the key artifact (file ID/name) or phrase; or load ~10–20 messages before/after.
   - Meetings: find the prior meeting in the same series / same participants within the last N days and scan for the artifact definition.
   - Email: scan earlier messages in the same thread or same sender/subject family.

   **Stop condition:** stop micro-backtracing as soon as you can answer (a) what is the deliverable, (b) who is it for, (c) what does “done” mean.
6. **Formulate**: Using all gathered context, produce a specific, actionable task description (verb-led, clear done-state). This is the extraction output — it goes into `extracted_tasks` + archival.

This protocol already exists in the tasks agent's persona as the "Context Enrichment Protocol." The change is to **codify it as mandatory for non-self-contained sparks** rather than optional, and to ensure email/meeting sparks carry enough raw material for it to work.

### Phase B: Work Packet Assembly (after FORMULATE, before or after CONFIRM)

The work packet is the full "execution-ready" bundle. It involves reasoning-heavy backtracing that goes beyond the immediate source.

In practice, Phase B backtracing tends to identify three distinct context nodes (useful both for execution and for building a durable context web):
- **Direct-action context**: where the task was assigned/created (meeting/email/Slack)
- **Artifact provenance**: where the primary artifact actually lives (Slack file, Drive doc, etc.)
- **Intent genesis**: earlier moments (often prior meetings) where the purpose/strategy and success criteria were established

Common Phase B questions:
- What prior commitments, conversations, or decisions relate to this task?
- What documents need to be open when working on it?
- What related tasks exist (extracted or in OmniFocus)?
- What's the synthesis — what does Chad actually need to do, step by step?

**The work packet's primary interface is the OmniFocus task note.** This means the full packet (with openfile:// links, related context, execution notes) is assembled at or after confirmation, not before. Pre-confirmation, we build **packet-info**: the backtracing data and resource inventory that feeds into the final packet.

**Two-part enrichment model:**

| Field | Phase A (formulation) | Phase B (packet assembly) |
|-------|----------------------|--------------------------|
| **When** | During FORMULATE | Background/sleeptime (pre-confirm) or at confirmation |
| **Who** | Tasks agent | MC (has organizational context + LettaBot tools) |
| **Output** | Good task statement + archival passage with source context | Updated archival with PACKET INFO section; at confirmation, OmniFocus note with full work packet |
| **Triggers next** | Appears in sidebar for review | Task is actionable in OmniFocus |

## Enrichment Status in Task Lifecycle

Add to archival passage format (additive, backward-compatible):

```
ENRICHMENT
- Status: formulated | packet-info | packet-ready
- Enriched: <ISO timestamp>
- Enriched By: <agent name>

PACKET INFO  (added during background enrichment, before confirmation)
- Direct-action node: <meeting/email/slack ref_id + link>
- Artifact provenance node: <where the primary artifact lives: Slack file ID, Drive fileId, etc.>
- Intent genesis nodes: <1–3 refs: prior meetings/emails that establish purpose/strategy>

- Context brief (action-oriented; 3–7 bullets):
  - <why this exists / what it is testing>
  - <key constraints / stakeholders / dynamics>
  - <what “good” looks like>

- Related Passages: <ref_ids of connected archival passages>
- Related Tasks: <ref_ids or OmniFocus IDs of connected tasks>
- Key Documents: <titles + URLs/doc IDs>
- Prior Decisions: <relevant D: items from meetings>

- Suggested task refinement (only if discoveries materially change the task):
  - current: <current task statement>
  - proposed: <revised task statement>
  - reason: <1–2 bullets>

- Backtracing notes: <MC’s analysis of context and connections>

Knowns / Assumptions / Unknowns
- Knowns: ...
- Assumptions: ...
- Unknowns: ...
```

The full WORK PACKET (with openfile:// links, execution steps, opened resources) is written to the **OmniFocus task note** at confirmation time, not to the archival passage.

New tag: `enrichment:{status}` alongside existing `status:extracted`, `origin:user-indicated`.

Tagging guidance (to avoid orphaned context briefs)
- Every enrichment passage should include 3–4 gardenable tags, e.g.:
  - 1 domain tag: `savvas`, `earth-science`, `mapping-time`, `ai-rubrics`, etc.
  - 1 activity tag: `bd-proposal`, `proposal-admin`, `scheduling`, `compliance`, etc.
  - 1 dynamics tag (when relevant): `pricing-scope`, `partner-dynamics`, `delegation`, etc.
  - 1 workflow tag: `backtracing` or `work-packets`

## Confidence-Gated Enrichment

| Origin | Pre-confirmation | Post-confirmation |
|--------|-----------------|-------------------|
| **user-indicated** | Tasks agent does formulation-time enrichment (Phase A). MC queued for background packet-info assembly. Goal: `packet-info` before review when possible. | At confirmation: MC assembles full work packet → OmniFocus note |
| **agent-identified** | Tasks agent does Phase A (enough for evaluation). No background packet-info — defer until confirmed. | If confirmed: MC performs backtracing + full work packet |

Sidebar shows enrichment status badge (`formulated` / `packet-info` / `packet-ready`).

### Rush / Immediate Action

"Rush" is a sidebar action (to be specified in detail during implementation) that combines:
1. Confirm the task → create OmniFocus entry
2. Request immediate MC work packet assembly (synchronous or near-synchronous)
3. MC assembles packet, writes to OmniFocus note, opens relevant documents

This bypasses the background enrichment queue. Exact UX, timeout handling, and fallback behavior TBD in Phase 4 implementation.

## User Feedback Signals at Confirmation/Rejection

The CONFIRM/ACT stage is a key feedback collection point. Three types of user signal should be captured and stored for downstream evaluation and training:

### 1. Rejection Reason (optional, on reject)

**UX**: The reject button ("x") works as-is for quick low-friction rejection. An adjacent arrow/expansion affordance reveals an optional text field for the reason. Submitting the reason is a single click (submit arrow) — it does not replace or gate the regular reject action.

**Storage**: Added to the archival passage alongside the existing rejection timestamp:
```
TIMESTAMPS
- Rejected: 2026-04-02T01:15:00-04:00
- Rejection reason: Status update, not actionable — agent misidentified FYI as task
```

### 2. User Task Modifications (on confirm or edit)

When the user edits a task description or estimate before confirming, the original agent-generated values should be preserved alongside the user's revision:

```
TASK METADATA
- Estimate: 30              ← user's revision
- Agent Estimate: 15        ← original agent estimate
- User Modified: true

SOURCE TEXT
<original verbatim>

USER REVISION HISTORY
- [2026-04-02 01:15] description: "Review Kate's proposal" → "Review and annotate Kate's STEMK12 budget section"
- [2026-04-02 01:15] estimate: 15 → 30
```

This is partially in place (Agent Estimate is already stored). The revision history and user-modified flag are new.

### 3. Evaluation and Training Cycles (TBD)

Aggregation and pattern analysis across rejection reasons, estimate accuracy (agent vs user vs actual), and task modification patterns are deferred to a future evaluation framework. Candidate evaluation cycles include:

- **Rejection pattern analysis**: Scan rejected passages for recurring themes (e.g., "agent keeps extracting status updates as tasks"). Feed patterns back into tasks agent extraction guidelines.
- **Estimate calibration**: Compare agent estimates vs user-revised estimates vs actual time (from OmniFocus timer). Identify systematic over/under-estimation by source type, domain, or complexity.
- **Modification delta analysis**: When users consistently rewrite task descriptions in similar ways, extract the rewrite pattern as a formulation guideline.
- **Confirmation rate by origin**: Track what percentage of user-indicated vs agent-identified tasks survive review. Adjust confidence thresholds accordingly.

These cycles are best run as periodic sleeptime or scheduled analysis tasks — exact implementation TBD.

## Pipeline Migrations

### Slack Shortcut
- **Current**: `send_to_tasks.py` → direct `[TASK EXTRACTION]` message to tasks agent
- **New**: `send_to_tasks.py` → write Spark Record to `spark_queue` → notify tasks agent
- **Files**: `slackbot/listeners/shortcuts/send_to_tasks.py`

### Email
- **Current** (broken): gmail-watch → 150-char snippet in `queued_tasks_from_email` → email agent → tasks agent
- **New**: gmail-watch → Spark Record with user notes + 500-char snippet + `fetch_hint: "gmail:MSG_ID"` in `spark_queue` → tasks agent fetches full email during formulation
- **Files**: `gmail-watch-service/src/gmail_watch/services/task_queue_writer.py`, `agent_notifier.py`, `watch_manager.py`
- Email agent removed from extraction pipeline (keeps reply watching, compose, thread monitoring)

### Meeting Notes
- **Current**: `scan_meeting_notes()` → inline `add_extracted_tasks()` HTTP calls
- **New**: `scan_meeting_notes()` → write Spark Records for `[c]` markers → tasks agent processes
- **Files**: `letta/meeting_scan_tool.py`, `granola-ingest/ingest.py`
- Draft email creation remains inline (separate concern from task extraction)

### Google Docs Comments
- **Current**: gmail-watch → DriveEnricher → `queued_tasks_from_drive` → docs-and-transcripts agent
- **New**: gmail-watch → DriveEnricher → Spark Record in `spark_queue` → tasks agent
- **Files**: `gmail-watch-service/src/gmail_watch/services/drive_task_queue_writer.py`, `agent_notifier.py`
- Docs-and-transcripts agent freed from extraction duties

## Agent Roles (Post-Migration)

| Agent | Role |
|-------|------|
| **Tasks agent** | FORMULATE: sole extractor. Reads `spark_queue`, produces `extracted_tasks`. Basic enrichment (Context Enrichment Protocol). Owns both blocks. |
| **MC** | ENRICH: deep backtracing, organizational context, work packet assembly. Triggered by tasks agent or sleeptime. Has broadest context + LettaBot tools. |
| **Tasks-agent-sleeptime** | ENRICH (background): batch scans for `enrichment:none` passages, performs basic→backtraced enrichment during off-hours. |
| **Email agent** | Thread watching, reply composition, follow-up monitoring. No extraction role. |
| **Docs-and-transcripts agent** | Document management, transcript archival. No extraction role. |

## Phased Implementation

### Phase 0: Deterministic Spark Processing (COMPLETED 2026-04-02/03)

Fully deterministic pre-processing — no LLM reasoning. Guarantees every spark produces a task in the sidebar quickly and reliably.

**Tool**: `process_spark_queue` — reads block, parses JSON, extracts tasks via API, clears queue.

**Task formulation priority** (deterministic, applied in order):
1. `user_notes` — user's explicit intent (Slack shortcut notes, email forward notes)
2. `task_hint` — from marker parsing (`[c]`, `[]`, `>`, or implicit comment text)
3. Comment text — extracted from Docs comment source_text (strips boilerplate)
4. Source text first line — for bare Slack messages
5. Location fallback — last resort

**Short fragment enrichment**: Task descriptions <40 chars get the quoted passage and document location appended (e.g. "Add citation" → "Add citation — 'Systems conveners...' in Proposal Draft").

**Marker types** (set at capture time, inform Phase A enrichment depth):
- `explicit` — user used `[c]` or `[]` convention. Self-contained task statement. Phase A: skip.
- `pointer` — user used `>` convention. Fragment needing expansion from document context. Phase A: mandatory enrichment.
- `implicit` — user wrote free-form text (Docs comment without marker, Slack notes, email notes). Usually passable. Phase A: light review.
- `None` — no notes provided (bare Slack message, email forward without notes). Phase A: full formulation needed.

**Infrastructure**:
- All notifications instruct agent to "Call process_spark_queue() now"
- Cron drain script (`~/bin/spark-queue-drain.sh`) fires every 2 minutes as fallback
- JSON parsing uses line-by-line detection (avoids `---` in source_text breaking splits)

**Files**: `letta/process_spark_queue_tool.py`, `scripts/spark-queue-drain.sh`

### Phase 1: Fix Email Pipeline (COMPLETED 2026-04-02)
- Increase snippet from 150 to 500 chars; add `fetch_hint` field with Gmail message ID for full retrieval during formulation
- Route notification to tasks agent instead of email agent
- Add `[c]` marker support (already done in gmail-watch-service)
- Ensure tasks agent persona/protocol includes: "When `fetch_hint` is present, fetch full content before formulating"
- **Files**: `task_queue_writer.py`, `agent_notifier.py`, `watch_manager.py`, tasks agent persona block

### Phase 1.5: Task Formulation Quality (COMPLETED 2026-04-03)

Deterministic task naming improvements — folded into Phase 0. All fixes applied to `process_spark_queue_tool.py` and upstream capture code.

**Fixed**: user_notes priority, marker parsing in all pipelines, trigger address inline stripping, short fragment context enrichment, multi-comment notification parsing, implicit marker type for unstructured comments.

**Remaining (Phase A)**: LLM-based refinement for `pointer` and `None` marker types where the deterministic formulation produces a passable but rough task name.

### Phases 2-3: Spark Record Format + Pipeline Migration (COMPLETED 2026-04-02)
- Define JSON schema, create block on tasks agent
- Migrate email pipeline to Spark Records (proves format)
- Add `process_spark_queue()` tool or update tasks agent persona
- **Files**: New letta tool, `task_queue_writer.py`

### Phase 3: Migrate Slack + Docs Pipelines
- `send_to_tasks.py` writes Spark Records
- `drive_task_queue_writer.py` writes Spark Records
- Retire old queue blocks
- **Files**: `send_to_tasks.py`, `drive_task_queue_writer.py`, `agent_notifier.py`

### Phase 4: Enrichment Status + Work Packet
- Add ENRICHMENT section to archival passage template
- Create `update_enrichment_status()` tool
- Update sidebar to show enrichment status + "Rush" button
- **Files**: `extracted_tasks_tool.py`, `pa-web-ui/app.py`, `sidebar.js`

### Phase 5: Background Enrichment
- Wire tasks-agent-sleeptime for enrichment scanning
- Create `build_work_packet` tool/prompt for MC
- Implement backtracing logic (archival search by person, project, domain)
- **Files**: New letta tool, sleeptime agent persona update

### Phase 6: Migrate Meeting Pipeline
- `scan_meeting_notes` writes Spark Records for `[c]` markers
- Keep draft email creation inline (separate concern)
- **Files**: `meeting_scan_tool.py`, `granola-ingest/ingest.py`

## Key Design Decisions

1. **Single queue block** (`spark_queue`): Consistent with Letta memory block patterns. Sparks are transient — consumed and removed during formulation.
2. **Reference-and-fetch for large content**: Sparks stay compact (~500-800 chars). `fetch_hint` tells the tasks agent how to retrieve full content during formulation. Keeps the queue clean while ensuring full information is accessible.
3. **Tasks agent as sole formulator**: One agent, one set of extraction standards, one persona to tune. Formulation-time enrichment (Phase A) is codified as mandatory for non-self-contained sparks.
4. **MC for deep enrichment, not formulation**: Avoids bottleneck; MC's organizational context is best used for backtracing and packet assembly, not parsing.
5. **Work packet lives in OmniFocus note**: The full packet (links, execution steps, resources) is assembled at confirmation time and written to the OmniFocus task note — its primary interface. Pre-confirmation, archival holds `PACKET INFO` (backtracing data, resource inventory) that feeds the final packet.
6. **Backward-compatible archival format**: ENRICHMENT and PACKET INFO sections are additive. Existing passages treated as `enrichment: formulated`.
7. **No Big Bang**: Each pipeline migrates independently. Tasks agent handles both old `[TASK EXTRACTION]` messages and new spark queue reads during transition.
8. **Immediate action bypass**: "Rush" bypasses background enrichment. Exact UX specified during Phase 4 implementation.

## Verification

After each phase:
- Forward a test email to cdorsey+tasks@concord.org → verify it appears in sidebar within 2 minutes
- Use Slack "Send to Tasks" shortcut → verify extraction
- Create a meeting with `[c]` markers → verify extraction
- Add a Google Docs comment → verify extraction
- Check enrichment status badge in sidebar
- Test "Rush" button triggers MC work packet assembly
