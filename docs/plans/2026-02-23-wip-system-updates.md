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

## 3. OmniFocus Completion Sync (COMPLETED)

**Status:** Implemented and deployed
**Plan:** [2026-02-23-omnifocus-completion-sync-design.md](2026-02-23-omnifocus-completion-sync-design.md)

**What was built:**
- `checkTaskCompletionStatus` batch method in OmniFocus plugin
- `sync_omnifocus_completions` Letta tool on `tasks-agent-sleeptime`
- Scheduler cron job for periodic execution

This is the foundation that items 1 and 2 build upon. Listed here for reference and dependency tracking.

---

## Execution Order

The recommended order for tackling these projects:

1. **Archive Embedding Migration** (item 1) — fixes infrastructure that other features depend on
2. **Completion Feedback Loop** (item 2) — builds on the sync tool and benefits from working semantic search

Both can be shelved and picked up independently. The feedback loop can proceed without the embedding migration (it uses substring search as a fallback), but semantic search would make the `prepare_completion_feedback` tool more robust.
