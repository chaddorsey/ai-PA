# WIP System Updates Tracker

**Last updated:** 2026-02-25

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

## 7. Cross-Agent Awareness — Phase 1 (COMPLETED)

**Status:** Implemented and deployed
**Plan:** [Cross-Agent Awareness plan](../../.claude/plans/enchanted-pondering-thacker.md)

**What was built:**
- **Slackbot archival event writes** — fire-and-forget `threading.Thread` writes a summary of each Slack DM exchange to the main agent's archival memory. Tags: `memory:session`, `session:YYYY-MM-DD`, `agent:calendar-agent`, `source:slack`, `user:{id}`, `identity:{id}`.
- **Core memory blocks** — `daily_awareness` (5000 chars, shared: main + sleeptime), `relationship_context` (5000 chars, shared), `consolidation_instructions` (3000 chars, sleeptime only). Sleeptime companion uses `memory_rethink` to consolidate archival passages into these blocks.
- **`recall_activity` tool** — registered on main agent (`tool-50cc1a7f`). Searches archival memory for cross-interface activity by keyword, date range, and source filter. Uses text substring search (`?search=`) for reliability.
- **Identity mapping** — `slackbot/ai/identity.py` resolves Slack user IDs to Letta identity IDs via the Identities API. `letta_conversation.py` rewritten: resolution order is cache → Supabase `user_conversations` → Letta labels (legacy) → create new. Stores identity_id in Supabase for cross-interface lookup. Archival writes include `identity:{id}` tag.

**Key files:**
- `slackbot/ai/identity.py` — Slack-to-Letta identity resolution
- `slackbot/ai/letta_conversation.py` — identity-aware conversation management with Supabase tracking
- `slackbot/listeners/messages/message_im_hybrid.py` — archival write + identity tag additions
- `letta/awareness_tools/recall_activity.py` — Letta tool source
- `letta/register_recall_activity_tool.py` — tool registration script
- `scripts/create_awareness_blocks.py` — block creation + attachment script

**Verification:** Slackbot rebuilt and healthy. Blocks attached to both agents. Tool registered and attached. Existing archival passages confirmed to have 4096-dim embeddings (auto-created by Letta on write). Both text and semantic search work.

**Depends on:** Nothing. Foundation for items 8-10 below.

---

## 8. Cross-Interface Continuity — Layer 2: Shared Routing (NOT STARTED)

**Status:** Outline only — not yet implemented
**Depends on:** Item 7 (identity mapping, completed)
**Risk:** Medium (changes message flow for Slack DMs)
**Estimated effort:** 4-6 hours

**Problem:** Slack DMs are hardcoded to the calendar agent (`agent-892a2d58`). pa-web uses a 6-tier dynamic routing system via `pa-routing-handler`. Slack users can't reach specialist agents (tasks, research, etc.) without this layer.

**Approach:**
1. Create a lightweight routing client in the slackbot that calls `pa-routing-handler`'s `/v1/route` endpoint (or a simplified version of it) to determine the target agent based on message content.
2. Alternatively, extract the routing logic from `pa-routing-handler` into a shared library or expose it as an internal API that both pa-web and slackbot can call.
3. The routing decision uses the resolved identity_id (from Layer 1) so the agent sees a consistent user across interfaces.
4. Fallback: if routing service is unavailable, default to calendar agent (current behavior).

**Key considerations:**
- Routing handler currently runs as part of pa-web's backend. Would need to be accessible from slackbot's Docker network (already on `pa-internal`).
- Slack's streaming response pattern differs from pa-web's SSE — may need adapter in slackbot.
- Agent-specific conversation isolation must be maintained (one conversation per user per agent).

---

## 9. Cross-Interface Continuity — Layer 3: Conversation Continuity (NOT STARTED)

**Status:** Outline only — not yet implemented
**Depends on:** Items 7 + 8 (identity mapping + shared routing)
**Risk:** Medium-High (affects conversation state across interfaces)
**Estimated effort:** 3-4 hours

**Problem:** Even with shared routing and identity mapping, a user starting a conversation on pa-web and continuing on Slack would get a fresh conversation context. The agent loses prior context from the other interface.

**Approach:**
1. Use `identity_id` as the primary key for conversation lookup instead of `(user_id, user_source)`. The `user_conversations` table already has `identity_id` column.
2. When a Slack user sends a message, resolve their identity_id, then look up their most recent conversation for the target agent by identity_id (regardless of source interface).
3. The conversation lookup becomes: cache → Supabase by identity_id + agent_id → create new.
4. Both pa-web and slackbot write to the same `user_conversations` row for the same identity + agent.

**Key considerations:**
- Need to handle the case where a conversation was created by pa-web (different user_id format). The identity_id bridges this gap.
- `user_conversations` table may need a schema change: add an index on `(identity_id, agent_id)` and allow the `UNIQUE` constraint to evolve.
- Context window management: if conversations are shared, the combined message history may be longer than expected. May need a "last N messages" window.
- Privacy: ensure that cross-interface sharing is opt-in or at least transparent to the user.

---

## 10. Cross-Agent Awareness — Phase 2: Weekly Rollups (NOT STARTED)

**Status:** Outline only — not yet implemented
**Depends on:** Item 7 (Phase 1 archival writes + sleeptime consolidation)
**Risk:** Low (additive, no existing behavior changes)
**Estimated effort:** 2-3 hours

**Problem:** `daily_awareness` block gets overwritten each day by the sleeptime companion. After a few days, the agent has no memory of earlier activity patterns. Weekly rollups would provide a longer-term view.

**Approach:**
1. Add a `weekly_rollup` core memory block (shared: main + sleeptime, ~5000 chars).
2. Update `consolidation_instructions` to include a weekly consolidation step: on Sundays (or every 7th wake-up), sleeptime reviews the past week's `daily_awareness` snapshots from archival and writes a weekly summary to the `weekly_rollup` block.
3. Optionally write each daily awareness snapshot to archival (tagged `memory:daily-digest`, `digest:YYYY-MM-DD`) before overwriting, so the weekly rollup has material to work from.
4. The weekly rollup focuses on: recurring themes, action item completion rates, communication patterns, relationship evolution.

**Key considerations:**
- Sleeptime wake frequency affects consolidation timing. May need a scheduler-driven trigger instead of relying on step-based waking.
- Block size limits (5000 chars) constrain how much history can be preserved. May need to archive older weekly rollups too.
- Consider a `monthly_rollup` block in the future if weekly proves valuable.

---

## Execution Order

Items 1-7 complete.

Remaining monitoring:

- **Item 1 (Archive Embedding Migration):** 7-day soak period for DEPRECATED archives (delete after 2026-03-02)
- **Item 3 (Meeting Follow-up Pipeline):** Awaiting production verification on next real meeting via Granola cron
- **Item 6 (Outbound Notifications):** Awaiting production verification on next OmniFocus completion sync with external-origin task
- **Item 7 (Cross-Agent Awareness Phase 1):** Deployed. Monitor sleeptime consolidation of daily_awareness block and verify archival writes from Slack DMs.

Future work (not yet started):

- **Item 8 (Shared Routing):** Layer 2 of cross-interface continuity. Give Slack access to dynamic agent routing.
- **Item 9 (Conversation Continuity):** Layer 3. Allow conversations to span interfaces via identity_id lookup.
- **Item 10 (Weekly Rollups):** Phase 2 of cross-agent awareness. Longer-term activity memory.

Suggested order: 8 → 9 → 10 (each builds on the previous).

**Completed:** Items 1-7 — archive embedding migration, completion feedback loop, meeting follow-up fix, OmniFocus sync, Slack pipeline, agent outbound notifications, cross-agent awareness Phase 1 + identity mapping.
