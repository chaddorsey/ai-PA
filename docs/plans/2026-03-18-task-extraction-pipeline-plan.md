# Task Extraction Pipeline — Consolidated Plan

**Date:** 2026-03-18
**Status:** Working plan
**Context:** Tasks agent consolidated as single extractor (gpt-5-mini). Need to finalize extraction pipeline design before end-to-end testing.

---

## Core Insight: Extraction is Always Multi-Phase

Every task, regardless of source or tier, benefits from a two-phase pipeline:

**Phase 1 — Formulate:** Identify and state the task clearly (verb-led, single-action)
**Phase 2 — Enrich:** Gather metadata, URLs, context, related resources, and potentially discover additional tasks

These phases apply to ALL sources. The difference between tiers is where Phase 1 starts:

| Tier | Phase 1 Input | Phase 2 Depth |
|------|--------------|---------------|
| **Intentional (user-signaled)** | Slack shortcut message, tagged email, marked meeting note | Surrounding context, document links, thread replies |
| **Semi-intentional (arrows, markers)** | Meeting note arrow items, comment tags | Meeting body, attendee context, referenced docs |
| **Ambient (agent-discovered)** | Raw email thread, channel scan, full meeting transcript | Deep multi-source correlation, goal matching |

The tasks agent should handle all three, processing in order: clear intentional tasks first, then markers, then ambient scan. This is a single agent loop, not separate pipelines.

---

## The Formulate → Enrich Loop

For any extraction trigger (Slack shortcut, email, meeting scan, MC delegation):

```
1. RECEIVE trigger with source context
2. ASSESS: How many tasks are here? How clear are they?
   - Explicit task statements → queue for immediate formulation
   - Ambiguous items → flag for enrichment before formulation
   - Bare links / sparse text → must enrich before formulating
3. FORMULATE clear tasks first (low-hanging fruit)
   - But do NOT call add_extracted_tasks yet
4. ENRICH each formulated task:
   - Fetch surrounding context (thread, nearby messages, document content)
   - Resolve document links → titles, owners, content summaries
   - Find related URLs from nearby messages (Slack: ~2 messages each side)
   - Check for additional tasks discovered during enrichment
   - Add metadata: people, dates, project associations
5. EXTRACT: Call add_extracted_tasks with the enriched task
6. LOOP: If enrichment revealed new tasks, return to step 3
```

This loop handles the meeting notes case naturally:
- Arrow-marked items → immediate formulation, then enrich from meeting body
- Action items discovered during enrichment → new formulation cycle
- Each task gets its full context regardless of how it was identified

---

## File-Based Task Staging (Replacing Queue Blocks)

### Why files instead of memory blocks

- **No cache busting:** File writes don't trigger prompt recompilation
- **No size limits:** JSONL files grow without constraint
- **Skills/subagent ready:** File-based state is the direction Letta is heading
- **Durable:** Survives agent restarts, model switches, compaction events
- **Inspectable:** Easy to tail, grep, debug from the command line

### Staging file design

**Location:** `/Volumes/main-drive/ai-PA/omnifocus-timer/logs/task-staging.jsonl`

Each entry represents a task in progress through the pipeline:

```json
{
  "id": "stg-abc123",
  "phase": "received | formulating | enriching | ready | extracted | failed",
  "source_type": "slack | email | meeting | google-docs-comment | mc-delegated",
  "trigger": "intentional | semi-intentional | ambient",
  "created_at": "2026-03-18T04:00:00Z",

  "raw_input": {
    "text": "original message text",
    "sender": "Cynthia McIntyre",
    "channel": "#mapping-time",
    "urls": ["https://docs.google.com/..."],
    "source_ref": "slack-C0A7NPWDGG3-1773772275.179449"
  },

  "formulated": {
    "task_description": "Review the reminder email draft...",
    "confidence": "high | medium | low"
  },

  "enrichment": {
    "document_titles": {"url1": "Mapping Time Reminder Draft"},
    "surrounding_context": "thread reply from Chad: 'I'll take a look'",
    "related_urls": ["url1", "url2"],
    "additional_tasks_found": [],
    "people_resolved": {"U09DXRLAH": "Cynthia McIntyre"}
  },

  "extraction_result": {
    "ref_id": "c92f8ced",
    "omnifocus_task_id": null,
    "status": "pending_review"
  }
}
```

### How the tasks agent uses the staging file

The agent doesn't read/write the file directly (that would require a file tool in the sandbox). Instead:

**Option A: Trigger message contains everything.** For intentional extractions, the trigger (Slack shortcut, email watcher) passes all raw input in the message. The agent processes it in a single conversation turn. The staging file is written by the trigger handler (slackbot, bridge) as a durable backup, not by the agent.

**Option B: A staging tool.** A lightweight Letta tool (`read_task_staging`, `update_task_staging`) that reads/writes the JSONL file. The agent calls these during multi-step enrichment to persist progress. This enables the agent to pause enrichment (e.g., waiting for a document fetch) and resume.

**Recommendation:** Start with Option A for intentional extractions (the trigger message has everything). Build Option B when we implement Tier 2 ambient scanning, which genuinely needs multi-step state persistence.

---

## MC Delegation Interface

When MC identifies a task and sends it to the tasks agent:

```
Message format:
"[TASK EXTRACTION]
Mode: extract | pre-formulated | batch
Source: slack | email | meeting | docs | cross-source
Trigger: intentional | ambient

Context:
<source text, URLs, metadata — everything the tasks agent needs>

Notes:
<MC's assessment, priority hints, related goals>"
```

- `mode: extract` — full formulate → enrich loop
- `mode: pre-formulated` — MC already stated the task, just enrich + archive
- `mode: batch` — multiple tasks, extract each sequentially

The tasks agent recognizes the `[TASK EXTRACTION]` header and switches to extraction mode. This keeps the interface structured without requiring a separate tool.

---

## What Stays in Memory Blocks vs. Files

| Data | Location | Reason |
|------|----------|--------|
| **Persona + protocols** | Core memory block | Needed every call, stable, cache-friendly |
| **extracted_tasks** (shared display) | Core memory block | Read by pa-web Tasks tab, shared across agents |
| **task_extraction_tool_use_guidelines** | Core memory block | Needed every extraction call, stable |
| **important_people** | Core memory block | Needed for name resolution, stable |
| **Task staging queue** | JSONL file | Avoids cache busting, durable, inspectable |
| **Completion records** | JSONL file (completions.jsonl) | Already file-based |
| **Follow-up queue** | JSONL file (pending-followups.jsonl) | Already file-based |
| **Archival passages** | Letta archival memory | Searchable, permanent record |

Candidates to move OUT of blocks eventually:
- `omnifocus_folder_and_project_hierarchy_sync` (4.8K) — could be fetched live via `run_omnifocus`
- `extracted_tasks_review_work` (15.4K) — if this is a working scratch pad, move to file
- `task_organization` (2.4K) — if stable reference, keep; if dynamic, move to file

---

## Source-Specific Trigger Wiring

| Source | Current Trigger | Target | Status |
|--------|----------------|--------|--------|
| **Slack shortcut** | Slackbot → tasks agent message | Tasks agent | ✓ Just wired |
| **Tagged email** | Email watcher → email agent | Tasks agent | TODO: redirect |
| **Drive comment** | Drive webhook → docs agent | Tasks agent | TODO: redirect |
| **Meeting scan** | Scheduler → docs agent | MC triggers → tasks agent | TODO: redesign |
| **MC delegation** | MC → tasks agent message | Tasks agent | TODO: define format |
| **Ambient Slack** | Pulse scan | MC identifies → tasks agent | Future |
| **Ambient email** | Email scan | MC identifies → tasks agent | Future |

---

## Implementation Order

### Phase 1: Make current Slack shortcut work end-to-end (NOW)
- [x] Tasks agent has consolidated persona + tools
- [x] Slack shortcut redirected to tasks agent
- [ ] Remove Slack queue block write from shortcut handler (pass everything in message)
- [ ] Clear stale `extracted_tasks_review_work` if needed
- [ ] Test: Slack shortcut → extraction → review → OmniFocus → timer → completion → follow-up

### Phase 2: Redirect remaining intentional triggers
- [ ] Email: redirect `process_email_task_queue` trigger to tasks agent
- [ ] Drive comments: redirect trigger to tasks agent
- [ ] Meeting intentional tasks: redirect to tasks agent

### Phase 3: Enrichment improvements
- [ ] Build staging tool for multi-step enrichment persistence
- [ ] Improve surrounding context fetching (Slack: 2 messages each side)
- [ ] Document link resolution via `run_gws`
- [ ] Multi-task splitting with per-task enrichment

### Phase 4: MC delegation and Tier 2
- [ ] Define MC → tasks agent message format
- [ ] MC ambient scanning: email threads, Slack channels
- [ ] Meeting transcript ambient extraction
- [ ] File-based staging for multi-step Tier 2 enrichment

### Phase 5: Agent consolidation
- [ ] Evaluate Pulse agent: retire or reduce to pure monitoring
- [ ] Evaluate Docs-Transcripts agent: retire or reduce
- [ ] Evaluate Email agent: retire or reduce
- [ ] Move meeting follow-up composition to tasks agent or MC

---

## Caching Profile

Tasks agent prompt prefix (estimated):
- Persona: ~6K chars (~2K tokens)
- Tool guidelines: ~5K chars (~1.5K tokens)
- Review process: ~2.5K chars (~800 tokens)
- important_people: ~8.4K chars (~2.5K tokens)
- extracted_tasks: ~1K chars (~300 tokens)
- Other stable blocks: ~10K chars (~3K tokens)
- Tool definitions (13 tools): ~4K tokens
- Total prefix: ~14K tokens

On gpt-5-mini at $0.40/M input, cached at $0.20/M:
- Cold call: ~$0.006
- Warm call (90%+ cached): ~$0.003
- At 20 extractions/day: ~$0.06-0.12/day

The prefix is stable between extractions (no block writes during extraction). Cache hit rate should be 90%+ after first call in a session.
