# WIP System Updates Tracker

**Last updated:** 2026-02-23

This document tracks in-flight system improvement projects that have been designed but not yet fully implemented. Each entry links to its detailed plan document.

---

## 1. Archive Embedding Configuration Migration (COMPLETED)

**Status:** Implemented and deployed — 7-day soak period until 2026-03-02
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

## 2. Completion Feedback Loop (Source Notification on Task Completion) (COMPLETED)

**Status:** Implemented and deployed (Phase 1: all source types routed)
**Plan:** [2026-02-23-completion-feedback-loop-design.md](2026-02-23-completion-feedback-loop-design.md)

**What was built:**
- `prepare_completion_feedback` tool — looks up completed passage, parses source type, returns routing info + draft message. Supports google-docs-comment (reply + resolve), slack (threaded reply), email (manual followup flag).
- `sync_omnifocus_completions` updated — return details now include `source_type`, `from_person`, `has_external_origin` for each completed task.
- `reply_to_document_comment` and `resolve_document_comment` tools attached to `tasks-agent-sleeptime` (Option A — direct attachment).
- Agent persona block updated with Completion Feedback Loop instructions (human-in-loop approval required).
- Tool IDs: `prepare_completion_feedback: tool-a462ba54-d411-454e-bc16-325943e6a6d3`, `sync_omnifocus_completions: tool-9ac0d26a-fa94-4ab2-9105-ab45cc9a3efb`.

**Verification:** Tested reference_id parsing for all 3 source types (google-docs-comment, slack, email). Confirmed 4 active `confirmed` passages with external origins correctly detected. Agent will suggest feedback on next OmniFocus completion sync cycle.

---

## 3. Meeting Follow-up Email Pipeline (Compaction Fix)

**Status:** Fix deployed (Option B) — awaiting production verification on next real meeting
**Plan:** [2026-02-17-meeting-notes-processing-design.md](2026-02-17-meeting-notes-processing-design.md) / [2026-02-17-meeting-notes-processing-tasks.md](2026-02-17-meeting-notes-processing-tasks.md)
**Risk:** Low
**Estimated effort:** Done (verification remaining)

**What's deployed and working:**
- `scan_meeting_notes` tool — registered on Granola agent, called on every new meeting (13+ calls observed)
- `prepare_meeting_followup` tool — registered, creates HTML D/NA Gmail draft
- Post-ingestion trigger in `granola_mcp_to_archival.py` — fires on every new meeting
- Agent system prompt + `meeting_processing_chain` memory block with full instructions
- Granola import cron jobs (3 jobs covering business hours, off-hours, weekends)
- Marker convention updated to `[c]` for Chad tasks (2026-02-23; Granola was swallowing `[ ]`)

**The problem (now fixed):** After `scan_meeting_notes` returned, Letta's context compaction fired (the scan result + meeting content is large), and the agent lost the instruction to call `prepare_meeting_followup`. It produced a text summary instead of creating the Gmail draft. Result: 16 scans, only 1 followup call (and that one had empty args).

**Fix applied (2026-02-23):** Option B — `scan_meeting_notes` now returns a `next_action` block with pre-computed `prepare_meeting_followup` args embedded in the tool return. Tool returns survive compaction. Tested with zero-marker meetings and marker-rich meetings (Rebecca meeting with 4 `[;]` items — all correctly populated in pipe-separated format). The instruction tells the agent to call the tool with the pre-computed args, allowing semantic augmentation before calling.

**Also fixed (2026-02-23):** Marker regex bug — `\[\s?\]` only matched `[ ]`/`[]`, missing `[  ]`/`[   ]` variants users actually typed. Now uses `[c]` convention which avoids the Granola checkbox problem entirely.

**Verification:** Monitor the next real meeting archived via Granola cron. Check Gmail drafts and agent message history for `prepare_meeting_followup` calls.

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

## 5. Slack Task Extraction Pipeline (Event-Driven Trigger) (COMPLETED)

**Status:** Implemented and deployed
**Risk:** Low

**What was built:**
- **Event-driven trigger** in `send_to_tasks.py`: both shortcut callbacks (`send_to_tasks_callback` and `send_to_tasks_view_callback`) use `_queue_and_trigger` — writes to queue, then sends agent message (sequenced to prevent race condition)
- **Context Enrichment Protocol** in guidelines block: agent fetches linked documents and surrounding Slack context
- **Queue format**: `---` separators (consistent with other queues, required for atomic cleanup)
- **Separator pile-up fix** in `add_extracted_tasks` cleanup logic: drops whitespace-only segments after removing matched entries

**Deployed (2026-02-23):** Slackbot rebuilt. All 6 backlogged queue items drained and extracted successfully (ref_ids: a9c30072, e380b050, f2bbf4c8, d900127f, 7d1e75b2, 508e121a). Queue block cleaned to empty. `add_extracted_tasks` tool scoped to 8 relevant agents (was incorrectly on all 25).

---

## 6. Agent Outbound Notifications (Slack Notify)

**Status:** Implemented and deployed (Combined Stage 1+3: interactive Slack blocks)
**Plan:** [2026-02-23-agent-outbound-notifications-design.md](2026-02-23-agent-outbound-notifications-design.md)

**What was built:**
- Slackbot `POST /api/notify` endpoint — receives notification from agent, renders Block Kit with Send Reply/Modify/Skip buttons, posts Slack DM, stores pending reply record in Supabase
- Supabase `pending_agent_replies` table — maps thread_ts → originating agent for reply routing
- Notification action handlers — `@app.action("notification_approve/modify/skip")` handlers route user responses back to originating agent
- Modify modal — pre-filled with suggested reply text, user edits and submits
- Thread-aware routing in DM handler — replies in notification threads route to originating agent (not default routing)
- Letta `send_slack_dm` tool (`tool-ea101b75-64b5-408d-9bb0-efd00933c9db`) — attached to `tasks-agent-sleeptime`
- Agent persona block updated with `send_slack_dm` instructions for completion feedback loop

**Key files:**
- `slackbot/health_check.py` — `/api/notify` POST handler
- `slackbot/services/pending_replies.py` — Supabase CRUD for pending replies
- `slackbot/adapters/notification_blocks.py` — Block Kit renderer
- `slackbot/listeners/actions/notification_actions.py` — button action handlers
- `slackbot/listeners/views/notification_modify.py` — modify modal handler
- `slackbot/listeners/messages/message_im_hybrid.py` — thread-aware routing addition
- `letta/send_slack_dm_tool.py` — Letta tool source

**Verification:** Test notification posted to Slack DM with interactive buttons. Pending reply record created in Supabase and resolved correctly. Slackbot rebuilt and healthy.

**Evolution path:** Stage 2 (multi-channel delivery via web-ui), Stage 4 (full outbound routing service).

**Depends on:** Item 2 (Completion Feedback Loop) — already deployed.

---

## Execution Order

Items 1-6 complete.

Remaining monitoring:

- **Item 1 (Archive Embedding Migration):** 7-day soak period for DEPRECATED archives (delete after 2026-03-02)
- **Item 3 (Meeting Follow-up Pipeline):** Awaiting production verification on next real meeting via Granola cron
- **Item 6 (Outbound Notifications):** Awaiting production verification on next OmniFocus completion sync with external-origin task

**Completed:** Items 1-6 — archive embedding migration, completion feedback loop, meeting follow-up fix, OmniFocus sync, Slack pipeline, agent outbound notifications.
