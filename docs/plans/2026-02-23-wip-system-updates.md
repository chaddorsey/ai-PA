# WIP System Updates Tracker

**Last updated:** 2026-02-23

This document tracks in-flight system improvement projects that have been designed but not yet fully implemented. Each entry links to its detailed plan document.

---

## 1. Archive Embedding Configuration Migration

**Status:** Planned — not started
**Plan:** [2026-02-23-archive-embedding-migration.md](2026-02-23-archive-embedding-migration.md)
**Risk:** Medium (data involved, but phased approach with rollback)
**Estimated effort:** 1-2 hours hands-on + 24-hour verification soak

**Problem:** 5 Letta archives have mismatched or missing embedding configurations. All 25 agents use `openai/text-embedding-3-small` (1536-dim), but these archives either have `embedding_config: null` or use `letta/letta-free` (4096-dim padded vectors). Semantic search via `/v1/passages/search` fails for affected archives. The Letta API does not support patching `embedding_config` on existing archives.

**Solution:** Create new archives with correct config, migrate passages (which auto-embeds them), swap archive attachments on agents, update hardcoded archive IDs in tool source files, re-register tools. Four phases ordered by ascending risk:
1. Delete orphaned archive (zero risk)
2. Replace empty archive (low risk)
3. Migrate small letta-free archives (11 + 4 passages)
4. Migrate `extracted_tasks_archive` (~10 passages, 4 tool files, 6 tool re-registrations) — highest risk, most dependencies

**Prerequisite for:** Completion Feedback Loop (item 2) — the `prepare_completion_feedback` tool would benefit from semantic search on the task archive.

---

## 2. Completion Feedback Loop (Source Notification on Task Completion)

**Status:** Designed — not started
**Plan:** [2026-02-23-completion-feedback-loop-design.md](2026-02-23-completion-feedback-loop-design.md)
**Risk:** Low (additive feature, human-in-loop approval)
**Estimated effort:** 2-3 hours for Phase 1 (Google Docs only)

**Problem:** When extracted tasks are completed in OmniFocus, `sync_omnifocus_completions` updates the Letta archive — but the original requester (e.g., a colleague who left a Google Doc comment or sent a Slack message) has no visibility that the task was done.

**Solution:** New `prepare_completion_feedback` tool that parses completed passage metadata, determines the feedback channel (Google Docs reply, Slack thread, email flag), drafts a message, and routes it for user approval before sending. Phased rollout:
1. **Phase 1:** Google Doc comments only (reply + resolve)
2. **Phase 2:** Slack messages (threaded reply)
3. **Phase 3:** Email (flagging only, no auto-reply)

**Key decisions:**
- Human-in-loop for all feedback initially (agent presents draft via Slack DM, user approves/modifies/skips)
- `sync_omnifocus_completions` gets minor modification to include `source_type`, `from_person`, `has_external_origin` in return details
- `reply_to_document_comment` and `resolve_document_comment` tools attached to `tasks-agent-sleeptime` (or cross-agent delegation as fallback)

**Depends on:** Archive embedding migration (optional but beneficial for semantic passage lookup)

---

## 3. Meeting Follow-up Email Pipeline (Compaction Fix)

**Status:** Partially built — tools deployed, but agent drops the email draft step due to context compaction
**Plan:** [2026-02-17-meeting-notes-processing-design.md](2026-02-17-meeting-notes-processing-design.md) / [2026-02-17-meeting-notes-processing-tasks.md](2026-02-17-meeting-notes-processing-tasks.md)
**Risk:** Low (existing infrastructure, needs reliability fix)
**Estimated effort:** 1-2 hours depending on approach

**What's deployed and working:**
- `scan_meeting_notes` tool — registered on Granola agent, called on every new meeting (13+ calls observed)
- `prepare_meeting_followup` tool — registered, creates HTML D/NA Gmail draft
- Post-ingestion trigger in `granola_mcp_to_archival.py` — fires on every new meeting
- Agent system prompt + `meeting_processing_chain` memory block with full instructions
- Granola import cron jobs (3 jobs covering business hours, off-hours, weekends)
- Marker convention updated to `[c]` for Chad tasks (2026-02-23; Granola was swallowing `[ ]`)

**The problem:** After `scan_meeting_notes` returns, Letta's context compaction fires (the scan result + meeting content is large), and the agent loses the instruction to call `prepare_meeting_followup`. It produces a text summary instead of creating the Gmail draft. Result: 16 scans, only 1 followup call (and that one had empty args).

**Options under consideration:**
- **Option B (cheapest):** Embed pre-computed followup call arguments directly in the scan tool's return value, so the agent sees "call prepare_meeting_followup with these exact args" in the data it's processing — tool returns survive compaction
- **Option D (most robust):** Move the deterministic scan-to-draft pipeline outside the agent entirely (scheduler/script calls tools directly via API, no LLM needed); agent only involved for optional semantic augmentation

**Also fixed (2026-02-23):** Marker regex bug — `\[\s?\]` only matched `[ ]`/`[]`, missing `[  ]`/`[   ]` variants users actually typed. Now uses `[c]` convention which avoids the Granola checkbox problem entirely.

---

## 4. OmniFocus Completion Sync (COMPLETED)

**Status:** Implemented and deployed
**Plan:** [2026-02-23-omnifocus-completion-sync-design.md](2026-02-23-omnifocus-completion-sync-design.md)

**What was built:**
- `checkTaskCompletionStatus` batch method in OmniFocus plugin
- `sync_omnifocus_completions` Letta tool on `tasks-agent-sleeptime`
- Scheduler cron job for periodic execution

This is the foundation that items 1 and 2 build upon. Listed here for reference and dependency tracking.

---

## 5. Slack Task Extraction Pipeline (Event-Driven Trigger)

**Status:** Partially implemented — shortcut trigger code written, guidelines updated, needs deploy + remaining queue drain
**Risk:** Low (additive change to existing infrastructure)
**Estimated effort:** 30 min remaining (deploy slackbot, drain 6 backlogged items)

**What was already built:**
- "Send to Tasks" Slack shortcuts (silent + modal with notes)
- `queued_tasks_from_slack` memory block on Pulse Monitor agent
- `task_extraction_process_slack` guidelines block with detailed extraction rules
- `add_extracted_tasks` tool with atomic queue cleanup
- Pulse agent has full Slack toolkit + Drive tools for context enrichment

**The gap:** No automated trigger between queue write and agent processing. 11 items accumulated without extraction (0 Slack-sourced tasks in the archive).

**What was built (2026-02-23):**
- **Event-driven trigger** in `send_to_tasks.py`: after writing to queue, sends a message to the Pulse agent with item context, triggering immediate extraction
- **Context Enrichment Protocol** added to guidelines: agent fetches linked documents (`get_drive_file_info`) and searches Slack for surrounding context when message text is sparse or ambiguous
- **Queue format fix**: changed from newline-separated JSON to `---` separators (consistent with other queues, required for atomic cleanup)
- **Tested:** We News item (straightforward) and TechNexus item (bare URL requiring enrichment) both extracted successfully

**Remaining:**
- Deploy slackbot rebuild (`docker-compose up -d --build slackbot`)
- Drain 6 remaining backlogged queue items via individual agent messages

---

## Execution Order

The recommended order for tackling these projects:

1. **Meeting Follow-up Pipeline fix** (item 3) — smallest scope, highest daily impact (every meeting triggers it)
2. **Archive Embedding Migration** (item 1) — fixes infrastructure that other features depend on
3. **Completion Feedback Loop** (item 2) — builds on the sync tool and benefits from working semantic search

Items 1-3 can be shelved and picked up independently. The feedback loop can proceed without the embedding migration (it uses substring search as a fallback), but semantic search would make the `prepare_completion_feedback` tool more robust.
