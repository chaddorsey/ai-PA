# WIP System Updates Tracker

**Last updated:** 2026-03-08

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

## 3. Meeting Follow-up Email Pipeline (VERIFIED)

**Status:** Deployed, verified in production, and enhanced with proposed items
**Plan:** [2026-02-17-meeting-notes-processing-design.md](2026-02-17-meeting-notes-processing-design.md) / [2026-02-17-meeting-notes-processing-tasks.md](2026-02-17-meeting-notes-processing-tasks.md)
**Risk:** Low
**Estimated effort:** Done

**What's deployed and working:**
- `scan_meeting_notes` tool — registered on Granola agent, called on every new meeting
- `prepare_meeting_followup` tool — registered, creates HTML D/NA Gmail draft
- Post-ingestion trigger in `granola_mcp_to_archival.py` — fires on every new meeting
- Agent system prompt with full `meeting_processing_protocol`
- Granola import cron jobs (3 jobs covering business hours, off-hours, weekends)
- Marker convention: `[c]` for Chad tasks, `[;]` for others' tasks

**Compaction fix (2026-02-23):** `scan_meeting_notes` returns `next_action` block with pre-computed args that survive Letta context compaction.

**Fixes applied (2026-03-03):**
1. **Draft gating** — agent prompt updated to only create drafts when user markers exist or proposed items found (was creating drafts for every meeting)
2. **Deadline doubling** — `scan_meeting_notes` now checks if deadline hint already appears in task text before appending (was producing "by EOD Wednesday (by EOD Wednesday)")
3. **Email passthrough** — prompt and `next_action` instruction reinforce passing participants with `Name <email>` format (agent was stripping emails)
4. **marker_type bug** — queue writes now correctly classify `[c]` as `my_tasks` (was checking for empty `[]` which never matched)
5. **Proposed items extraction** — see Item 15 below

**Mass re-import root cause (2026-03-02):** ExFAT permission error prevented `.granola_watcher_state.json` writes → state never saved → every import cycle saw ~90 meetings as "new" → 836+ agent notifications on March 1-2 → ~2500 junk Gmail drafts. Resolved by APFS migration (Item 12).

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

---

## 11. Coordination V2 — Follow-up Fixes

**Status:** Deployed — follow-up issues identified during smoke testing
**Plan:** [2026-02-27-coordination-v2-design.md](2026-02-27-coordination-v2-design.md) / [2026-02-27-coordination-v2-impl.md](2026-02-27-coordination-v2-impl.md)

**What's deployed and working:**
- 5-phase coordination flow: Resolve (calendar-first) → Gather (parallel) → Evaluate (main agent) → Refine (follow-ups) → Synthesize
- Calendar resolution populates `{resolved_title}`, `{resolved_participants}`, `{resolved_emails}`, `{resolved_time}` for downstream agents
- Evaluation phase correctly identifies which agents need follow-up prompts
- Synthesis output is clean (no template variable leaks)

**Known issues to address:**
1. **Document agent gather timeout** — times out in Phase 1 (90s) but contributes successfully during Phase 3 refinement. May need longer Phase 1 timeout or prompt tuning.
2. **Pulse agent never contributes** — returns empty findings across all test runs. May lack Slack search tools or not understand the memory-write instruction.
3. **`coordination_logs` table missing** — all log POSTs return 404. Need to create the table in Supabase for observability.

---

## 12. Infrastructure — ExFAT to APFS Migration (COMPLETED)

**Status:** Completed (2026-03-03)

**What was done:**
- Backed up main-drive (256GB ExFAT SSD) to main-filestore via `ditto`
- Verified backup with SHA-256 checksums across 34+ files
- Reformatted main-drive from ExFAT to APFS via Disk Utility
- Restored files via `ditto`, verified checksums match
- Docker Desktop restarted — 24 containers healthy
- Confirmed no `._*` metadata sidecar files on APFS

**Benefit:** Eliminates ExFAT metadata file issues that poisoned Docker builds and Letta restarts. Proper Unix permissions, symlinks, and extended attributes now supported.

---

## 13. Infrastructure — Time Machine Backup

**Status:** In progress (2026-03-03)
**Risk:** Low

**What was done:**
- Time Machine configured to back up to main-filestore (14TB APFS HDD, 11TB free)

**Still to do:**
- Exclude `/Volumes/main-drive/Docker` from Time Machine (228GB VM image changes constantly, bloats backups)
- Include main-drive in Time Machine for versioned ai-PA/ollama snapshots
- Verify first backup completes successfully

---

## 14. Infrastructure — Evaluate OrbStack Migration (NOT STARTED)

**Status:** Not started — planned
**Risk:** Low (drop-in Docker Desktop replacement, can run side-by-side)
**Estimated effort:** 1-2 hours

**Problem:** Docker Desktop uses a fixed VM allocation (7.9GB of 24GB RAM). With 34 containers, memory pressure caused a kernel panic (61 swapfiles, 97% memory compression, WindowServer watchdog timeout).

**Approach:**
1. Install OrbStack (uses dynamic memory sharing — no fixed VM)
2. Import Docker Desktop data
3. Test all services start and run correctly
4. Prove stability over 24-48 hours
5. Uninstall Docker Desktop if satisfied

**Benefit:** Dynamic memory sharing means containers only consume what they actually use, dramatically reducing memory pressure on the 24GB Mac Mini.

---

## 15. Meeting Follow-up — Proposed Items Extraction (COMPLETED)

**Status:** Implemented, deployed, and verified in production (2026-03-03)
**Extends:** Item 3 (Meeting Follow-up Pipeline)
**Risk:** Low (additive feature, no existing behavior changes)

**What was built:**
- **Semantic extraction** in `scan_meeting_notes` — scans AI summary bullet lines for action verbs (`ACTION_SIGNALS`) and decision language (`DECISION_SIGNALS`). Returns `proposed_items: {actions: [...], decisions: [...]}` and `has_user_markers: bool`.
- **Proposed draft workflow** — agent prompt updated: if `has_user_markers=false` but `proposed_items` contains items, creates draft with `proposed=true` (adds `[Proposed]` to subject line). If no markers AND no proposed items, skips followup entirely.
- **`proposed` parameter** on `prepare_meeting_followup` tool — boolean flag that prepends `[Proposed]` to email subject when true.
- **Pre-computed args integration** — when no user markers, `next_action.pre_computed_args` merges proposed items into followup args and sets `proposed: true`.

**Verification (live end-to-end through agent):**
- "Check in re proposal development" (no markers) → scan found 1 action + 2 decisions → agent created `[Proposed]` draft ✓
- "Chad and Kate" (no markers, personal chat) → scan found 0 items → agent correctly skipped followup ✓

**Key extraction patterns:**
- `ACTION_SIGNALS`: will/agreed to/need to/should + verb, "next action/step" headers, Name + action verb patterns
- `DECISION_SIGNALS`: agreed/decided/decision + to, will not/no longer, cancelled/confirmed/approved

**Tool IDs:**
- `scan_meeting_notes`: `tool-6079e940-f49f-4cd2-925a-ebf33c4ba3d7`
- `prepare_meeting_followup`: `tool-301ba80c-c4e8-4087-90a9-f1cdba295f85`
- Agent: `agent-398b4f6c-6afa-493f-8063-897c6b171a0d` (docs-and-transcripts-agent)

---

## Execution Order

Items 1-7, 12, 15 complete.

Remaining monitoring:

- **Item 1 (Archive Embedding Migration):** 7-day soak period for DEPRECATED archives (delete after 2026-03-02)
- **Item 6 (Outbound Notifications):** Awaiting production verification on next OmniFocus completion sync with external-origin task
- **Item 7 (Cross-Agent Awareness Phase 1):** Deployed. Monitor sleeptime consolidation of daily_awareness block and verify archival writes from Slack DMs.
- **Item 13 (Time Machine Backup):** Configure exclusions, verify first backup.

Future work (not yet started):

- **Item 8 (Shared Routing):** Layer 2 of cross-interface continuity. Give Slack access to dynamic agent routing.
- **Item 9 (Conversation Continuity):** Layer 3. Allow conversations to span interfaces via identity_id lookup.
- **Item 10 (Weekly Rollups):** Phase 2 of cross-agent awareness. Longer-term activity memory.
- **Item 11 (Coordination V2 Follow-ups):** Fix document timeout, pulse agent, coordination_logs table.
- **Item 14 (OrbStack Migration):** Evaluate as Docker Desktop replacement for memory pressure relief.
- **Item 16 (gws CLI Experiment):** Active — powering Gmail drafts sidebar via x86_64 sidecar. Full tool replacement still awaits linux/arm64.
- **Item 17 (Credential Consolidation):** Merge 5+ Google OAuth tokens into one unified credential. Enables gws CLI for Calendar/Drive.

Suggested order for cross-interface: 8 → 9 → 10 (each builds on the previous).
Suggested order for Google/gws: 17 (unblocks gws Calendar endpoints in Item 16).
- **Item 19 (Slack CLI):** Agent-first CLI wrapping Slack Web API. Implemented on `slack-cli` branch, merged.
Independent: 20 (Letta Code migration — Phase 0 validation can start anytime).
Related: [CLI Recipe Suggestions](2026-03-08-cli-recipe-suggestions.md) — proposed recipes for omnifocus-cli, slack-cli, and cross-service workflows (feeds into Item 20).

---

## 16. Google Workspace CLI (`gws`) — Experiment Active

**Status:** Experiment deployed — powering Gmail drafts sidebar in pa-web-ui via x86_64 sidecar
**Plan:** [2026-03-04-gws-cli-gmail-experiment-design.md](2026-03-04-gws-cli-gmail-experiment-design.md)
**Design:** [2026-03-04-gmail-drafts-sidebar-design.md](2026-03-04-gmail-drafts-sidebar-design.md)
**Risk:** Low (isolated sidecar, no disruption to existing Gmail tools)
**Estimated effort:** Completed initial deployment

**Experiment:** Rather than replacing existing Gmail tools (blocked by linux/arm64), the gws CLI is used via an x86_64 Docker sidecar (`gws-bridge` on port 8098, Rosetta emulation) to power a new feature: a Gmail Drafts sidebar tab in pa-web-ui. Users can list, edit, send, and discard agent-generated meeting follow-up drafts directly from the web UI.

**Components deployed:**
- `gws-bridge` — Node.js/Express sidecar wrapping `gws` CLI as HTTP (6 endpoints)
- `pa-web-ui` — `/api/drafts/*` proxy routes, tabbed sidebar (Tasks/Drafts), DraftsSidebar JS class with edit modal
- `meeting_followup_tool.py` — Now applies `Followup` label to all meeting drafts (previously only `Proposed` label on AI-proposed drafts)

**Full tool replacement still on hold:** Direct in-container `gws` use awaits linux/arm64 binary support. When it ships, migration is a one-line-per-tool change (swap HTTP call for subprocess call).

**Broader opportunity:** The sidecar validates `gws` for production use. If stable, extends to Calendar, Drive, Sheets — one auth mechanism for all Google Workspace APIs.

---

## 17. Google OAuth Credential Consolidation (NOT STARTED)

**Status:** Not started — design documented
**Plan:** [2026-03-05-google-credential-consolidation-design.md](2026-03-05-google-credential-consolidation-design.md)
**Depends on:** Item 16 (gws CLI experiment)
**Risk:** Low (OAuth re-auth is non-destructive; old tokens keep working)
**Estimated effort:** 1-2 hours

**Problem:** 2 GCP projects, 4 OAuth clients, and 5+ separate token files with narrow, overlapping scopes. The gws CLI only has Gmail scopes, so it can't be used for Calendar or Drive. Each service manages its own credential refresh independently.

**Approach:** Consolidate onto the `letta-calendar-tools` OAuth client (`389544848122`), which already has tokens for calendar, drive, and admin scopes. Run one incremental OAuth flow (with `include_granted_scopes=true`) to add Gmail scopes, producing a single unified token. Export in gws format for gws-bridge. Then point all services at the unified token.

**Three phases:**
1. Create unified auth script (modify `authenticate_calendar.py` or new `scripts/google-unified-auth.py`)
2. Migrate services to unified token (docker-compose env vars, gws-bridge credentials, drive-rag-service)
3. Cleanup deprecated individual token files after 7-day soak

**Context:** The n8n calendar dependency was removed (2026-03-05) by adding direct Google Calendar API calls to the scheduling orchestrator. The orchestrator currently uses `calendar.credentials.json` directly — consolidation would simplify this further but isn't blocking.

---

## 18. Scheduling Pipeline — Direct Calendar API (COMPLETED)

**Status:** Deployed and verified (2026-03-05)
**Risk:** Low (n8n MCP fallback available via `USE_DIRECT_CALENDAR=false`)

**What was built:**
- `google_calendar_client.py` — Direct Google Calendar API client using `google-api-python-client`. Same interface as `MCPCalendarClient` (initialize, get_core_event_data, fetch_event_by_id).
- `calendar_client_factory.py` — Selects direct API vs n8n MCP based on `USE_DIRECT_CALENDAR` env var.
- Event classification logic (`_classify_event`) replicating n8n's `locked`/`protected`/`flexible`/`transparent` computation from raw Google Calendar API fields.
- OAuth credentials (`~/.gmail-mcp`) mounted read-only into `scheduling-orchestrator-api` container.
- All 4 `MCPCalendarClient` import sites in `orchestrate_scheduling.py` updated to use the factory.

**Performance:** 5.7s end-to-end (down from 6-8s with n8n MCP hop). Combined with the Letta bypass (item not tracked here, commit 113b465), total DM-to-proposal time dropped from ~25s to ~6s.

**Key files:**
- `letta/scheduling_orchestrator/google_calendar_client.py`
- `letta/scheduling_orchestrator/calendar_client_factory.py`
- `letta/scheduling_orchestrator/orchestrate_scheduling.py` (4 import sites changed)
- `docker-compose.yml` (orchestrator env vars + volume mount)

---

## 19. Slack CLI — Agent-First Slack Web API Wrapper (MERGED)

**Status:** Implementation complete, merged to main
**Branch:** `slack-cli` (merged)
**Design:** [2026-03-07-slack-cli-design.md](2026-03-07-slack-cli-design.md)
**Plan:** [2026-03-07-slack-cli-impl.md](2026-03-07-slack-cli-impl.md)
**Risk:** Low (new standalone tool, no existing services modified)

**Problem:** Slack interactions are fragmented across 5+ places: third-party MCP server (port 3001), 4 custom Letta tools, DM notification tool, channel reply tool, analytics browser automation. Agents have limited, inconsistent access to the Slack API.

**Approach:** Python CLI (`click` + `slack_sdk`) following `gws` and `omnifocus-cli` patterns:
- `slack <resource> <method>` for raw API access (conversations, chat, users, reactions, files, search, pins, bookmarks, reminders, team)
- `slack <resource> +<helper>` for multi-step convenience commands (+send, +find, +whois)
- `--body '{JSON}'` agent-first path, convenience flags as sugar
- Schema introspection (`slack schema <method>`), `--dry-run`, `--fields`, structured JSON errors
- Credential chain: env vars → config file → fallback to existing tokens
- Auto token selection (bot vs user) per method
- Input validation (Slack IDs, timestamps, control chars)
- Letta tool wrappers via subprocess pattern (same as omnifocus-cli)

**Key files:**
- `slack-cli/src/slack_cli/cli.py` — Click entry point + `_run()` helper
- `slack-cli/src/slack_cli/schema.py` — Schema registry (52 methods)
- `slack-cli/src/slack_cli/client.py` — Slack SDK wrapper
- `slack-cli/src/slack_cli/auth.py` — Credential chain
- `slack-cli/src/slack_cli/validate.py` — Input hardening
- `slack-cli/letta_tools/` — Subprocess wrappers for Letta agents

**Out of scope:** Admin analytics (stays in `slack-analytics-mcp-server`), Socket Mode, OAuth flows, MCP transport.

---

## 20. Scheduler Tool Consolidation (DECISION PENDING)

**Status:** Design options documented — awaiting decision
**Plan:** [2026-03-07-scheduler-cli-design.md](2026-03-07-scheduler-cli-design.md)
**Risk:** Low (additive replacement, rollback documented)
**Estimated effort:** 1-6 hours depending on option chosen

**Problem:** The scheduler service requires a dedicated MCP server (`scheduler-mcp`, port 8088, separate Docker container) to expose 10 tools to Letta agents. This is a lot of infrastructure to proxy a 12-endpoint REST API that's already on the Docker network.

**Options:**
- **A: Full CLI** (omnifocus-cli pattern) — schema discovery, `--dry-run`, `--fields`, pip install in container. 4-6 hours.
- **B: Direct Letta tool** (recommended) — single `run_scheduler` tool calling REST API via `urllib.request`. No CLI, no subprocess. 1-2 hours.
- **C: Lightweight CLI** — thin Click wrapper without schema registry. 2-3 hours.

**Recommendation:** Option B. The scheduler is an internal REST API with a small surface (12 endpoints). The `create-cli` pattern is best justified when the underlying service isn't directly callable from Docker or has a large API surface (>30 methods). See design doc for full analysis.

**Decommissions:** `scheduler-mcp` Docker service, `scheduler-tools` MCP config entry, 10 individual MCP tools.

---

## 21. Letta Code Migration Assessment (NOT STARTED)

**Status:** Assessment complete — hybrid architecture recommended, no code changes yet
**Plan:** [2026-03-07-letta-code-migration-assessment.md](2026-03-07-letta-code-migration-assessment.md)
**Risk:** Low (assessment only; Phase 0 is validation with no disruption to existing agents)
**Estimated effort:** Phase 0: 1-2 weeks; Phase 1: 1 week; Phase 2: 5 weeks; Phase 3: ongoing

**Problem:** Letta is shifting development focus from standard agents to "Letta Code" agents (client-side bash/skills execution). The PA ecosystem is headless and programmatically invoked (slackbot, scheduler, n8n), which is incompatible with Letta Code's interactive model. Need to understand migration path and position for future Letta features.

**Recommendation:** Permanent hybrid architecture. Standard Letta agents keep all programmatic workflows. A new Letta Code companion agent provides interactive terminal access. Complex tools gradually extracted into HTTP microservices callable from either model.

**Critical blocker:** Letta Code skills require a connected client process — agents invoked by slackbot/scheduler cannot rely solely on skills unless daemon mode is confirmed.

**Prerequisites for Phase 0:** Install gws CLI and omnifocus-cli on host (both currently Docker-only). gws credentials already on host. omnifocus-cli's `bridge.py` has direct osascript path on macOS (bypasses HTTP bridge).

---

## 22. Curator Radar — Multi-Platform Curator Discovery (CODE COMPLETE)

**Status:** Code complete (GitHub + Twitter), pending deployment (DB setup, backfill, scheduler jobs)
**Plan:** [2026-03-08-curator-radar.md](2026-03-08-curator-radar.md)
**Twitter design:** [2026-03-09-twitter-curator-discovery-design.md](2026-03-09-twitter-curator-discovery-design.md)
**Risk:** Low (new service, no existing system dependencies)

**Problem:** No systematic way to discover interesting GitHub repos or high-signal Twitter accounts. Manual browsing misses repos/accounts from trusted curators.

**Solution:** FastAPI microservice (port 5145) with two curator discovery engines:
1. **GitHub:** Backfills stargazer data, computes IDF-weighted overlap scores, monitors top curators' WatchEvents, weekly Slack digest.
2. **Twitter:** Reads bookmarked tweet IDs from Smaug's archive, fetches likers via Favoriters GraphQL endpoint, scores overlap with same IDF algorithm, auto-manages a private Twitter List of top curators.

**Key components:**
- Supabase PostgreSQL schema (`curator_radar` schema)
- GitHub API client + Twitter GraphQL client (both with adaptive rate limiting)
- Backfill pipelines for stargazer history + tweet likers
- Scoring engine: IDF-weighted overlap (+ earlyness for GitHub)
- Daily Twitter pipeline: ingest → fetch likers → score → sync list
- Weekly Slack digest with GitHub + Twitter sections
- Letta tool (`query_curator_radar`) for agent access
- Reads Smaug output for bookmark data (volume mount, no duplicate auth)

**To deploy:**
1. Create `curator_radar` database + user in Supabase
2. Set `GITHUB_TOKEN` in `.env`
3. `docker-compose up -d curator-radar`
4. Run migration: `migrate_curator_platform.py` (if existing data)
5. Register scheduler jobs (GitHub daily monitor, Twitter daily pipeline, weekly digest)
6. Run initial backfills (GitHub stars, Twitter likers)

---

## 23. Smaug — Twitter/X Bookmarks Archival (ACTIVE)

**Status:** Deployed, running every 6 hours via launchd
**Design:** [2026-03-08-smaug-twitter-bookmarks-design.md](2026-03-08-smaug-twitter-bookmarks-design.md)
**Upstream:** [github.com/alexknowshtml/smaug](https://github.com/alexknowshtml/smaug)
**Risk:** Low (standalone host tool, no internal service dependencies)

**What:** Archives Twitter/X bookmarks to structured markdown with AI categorization (Claude Code). bird CLI fetches via Twitter's GraphQL API using browser cookies. Output: `bookmarks.md` master archive + `knowledge/tools/` and `knowledge/articles/` with YAML frontmatter.

**Components:**
- bird CLI (from npm, global install) — Twitter GraphQL wrapper with pagination
- Smaug (Node.js) — `/Volumes/main-drive/ai-PA/smaug/`
- Output — `/Volumes/main-drive/ai-PA/smaug-data/`
- launchd — `com.ai-pa.smaug`, every 6 hours

**Initial backfill:** 993 bookmarks processed (Feb 2024 → Mar 2026): 15 tools, 18 articles, 12 videos, 948 tweets.

**Downstream consumer:** Curator Radar (Item 22) reads `smaug-data/bookmarks.md` and `.state/bookmarks-state.json` to ingest tweet IDs for Twitter curator discovery. Smaug's output files are the single source of truth for bookmarked tweets.

---

**Completed:** Items 1-7, 12, 15, 18 — archive embedding migration, completion feedback loop, meeting follow-up pipeline (verified + proposed items), OmniFocus sync, Slack pipeline, agent outbound notifications, cross-agent awareness Phase 1 + identity mapping, ExFAT → APFS migration, direct Calendar API for scheduling.
