---
title: "pa-web-ui Phase 2: multi-conversation switcher + persistent fork UX"
type: feat
status: active
date: 2026-04-20
origin: docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md
depends-on: docs/plans/2026-04-20-001-feat-pa-web-ui-letta-code-migration-plan.md
---

# pa-web-ui Phase 2 — multi-conversation switcher + persistent fork UX

## Overview

Phase 1 landed the direct letta-code subprocess backend, feature-flagged
behind `PA_WEB_UI_PHASE_1_ENABLED`. All Phase 1 conversations route to
the MC agent's shared `default` conversation (same thread Telegram via
LettaBot uses). Phase 2 promotes conversations to first-class entities:
users can **create, switch, rename, and soft-delete** conversations
from a left rail, and **fork any assistant message** into a new
persistent conversation. Each conversation spawns its own letta-code
subprocess via the Phase 1 pool (which is already keyed by `conv_id`
and needs no changes).

Phase 2 also introduces the project's first multi-pane layout (left
rail + main + right Task Review Sidebar), the first backfill migration
on `pa_web` tables, and the first LLM-based auto-naming feature.

Covers origin-doc requirements **R9** (amended during planning from
30-day trash to hard-delete-with-undo), **R10**, **R11**, **R18**
(amended from URL deep-link to per-device localStorage), and adds
**R-auto-name** (LLM rename on first turn).

## Problem Frame

(See origin: `docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md`)

Today, the web UI is a single-threaded chat view. All messages land in
the MC agent's `default` conversation — which is ALSO the thread
LettaBot's Telegram subprocess uses. Phone and desktop see the same
stream, but so does Telegram. There is no way to:

- Start a distinct conversation without cross-contaminating context
- Return to an older conversation after switching
- Fork from "the state of the world after message N" to explore an
  alternative without polluting the main thread
- Deep-link to a specific conversation (e.g., share a URL to the
  laptop from the phone)

Phase 2 delivers these capabilities. The Task Review Sidebar stays
untouched (pre-existing right overlay; not in Phase 2 scope). The
`/btw` ephemeral side-query UX is Phase 3, not 2 — Phase 2 is **only**
persistent forks.

## Requirements Trace

All origin-doc requirements are carried forward. Phase 2 primarily
resolves R9, R10, R11, and R18; other Phase 1 requirements remain in
force and are noted where Phase 2 touches them.

### Multi-conversation + persistent fork UX (R9–R11, R18, R-auto-name)
- **R9 (amended during planning).** Conversations are first-class;
  user can create, switch, rename, delete. Delete is **hard-delete
  with 10s client-side undo toast**, NOT 30-day soft-delete trash.
  Amendment rationale: product + scope reviewers converged — a
  single-user PA with nightly backups doesn't need trash-tier
  recovery; 10s toast covers the real mis-click case and eliminates
  a trash tab + restore flow + purge cron + Phase 2.5 follow-up.
- **R10.** "Fork from here" per-message action →
  `POST /v1/conversations/{id}/fork?agent_id=...` (probed in Unit 2.0).
- **R11.** No archive tier, no full-text search, no pinned-primary
  concept in v1.
- **R18 (amended).** Cold PWA open → most-recently-active conversation
  for MC. Resolution order: (1) `localStorage['pa_last_conv_id']` per
  device if the value is still valid in the current conv list; (2)
  otherwise, MRU from Letta `conversations.list?agent_id=MC&order_by=last_message_at`.
  Amendment rationale: scope reviewer — URL deep-link (`?conv=<uuid>`
  + replaceState + popstate) was overbuilt for a single user. Per-
  device localStorage preserves the within-device "last I was in conv
  B" experience without URL machinery.
- **R-auto-name (new in Phase 2).** Conversations auto-rename to an
  LLM-generated summary after the first turn completes, unless the
  user has manually set a label. Fired in-band on the existing SSE
  event pipeline; cheap (~$0.00004 per rename via gpt-4.1-mini);
  gated by `PA_WEB_UI_AUTONAME_ENABLED` (default true) for killswitch.

### Carried forward from Phase 1 (constraints Phase 2 honors)

**Subprocess model (R1–R3):**
- Phase 2 passes real conv UUIDs to `SubprocessRegistry.ensure(agent_id, conv_id)`.
  No registry changes — verified against `test_distinct_convs_spawn_distinct_subprocesses`.

**Disallowed tools (R4, R4b):** unchanged.

**Event fidelity + seq_id resume (R6, R7, R7b):**
- Each conversation has its own ring buffer already (Phase 1). Phase 2's
  conversation switch resets `lastSeqId` and refetches history — no resume
  across switches.

**Turn-lock (R7c):**
- Phase 2's "Fork from here" checks the parent conversation's in_flight
  flag; fork is rejected with HTTP 409 if the parent is streaming.

**Server owns state, devices are thin (R19):**
- Phase 2 still reads from `pa_web.conversations` for history display
  (pragmatic — migrating display to Letta's messages API is Phase 3 or later).

**Ingress + env hardening (R29, R30):**
- All new routes pass through the Phase 1 `ingress_guard`. No new secrets in env.

## Scope Boundaries

**In scope:**
- Conversation CRUD (create, rename, **hard-delete with 10s undo toast**)
- Conversation switcher UI (left rail + mobile drawer)
- Per-message "Fork from here" action
- Per-conversation subprocess isolation (leveraging Phase 1's pool)
- **LLM auto-naming** after first turn (in-band on the SSE pipeline;
  user rename wins via `user_renamed` flag)
- **Per-device last-used conv** via `localStorage['pa_last_conv_id']`
  (R18 resolution; no URL state)
- Database schema extension on 4 `pa_web` tables
- Backfill: existing Phase-1 history points at MC's real `default`
  Letta conv UUID (resolved in Unit 2.0)

**Out of scope:**
- Soft-delete / trash / restore / 30-day purge — removed per R9 amendment
- URL deep-link (`?conv=<uuid>`) + `replaceState` + `popstate` —
  removed per R18 amendment
- `/btw` ephemeral side-queries (**Phase 3**)
- PWA manifest / service worker / offline (**Phase 4**)
- Archive tier, full-text search, pinned-primary (**v1 non-goal per R11**)
- Branch-from-specific-user-message (Claude.ai "edit and retry") —
  Letta's fork is conversation-level, not message-level
- Migrating history display from `pa_web.conversations` to Letta's
  messages API (Phase 3 or later)
- Multi-agent conversations (Phase 2 is MC-only; slash-routed agent
  paths are unaffected)
- Cross-agent forks (fork preserves `agent_id`; parent and child share
  the same agent)
- Conversation sharing / permissions (single-user PA)

## Context & Research

### Relevant Code and Patterns

- `pa-web-ui/app.py::ensure_pa_web_schema()` at **L179–246** —
  **short-circuit bug** at L185–187: returns early if the schema
  already exists. New tables/columns inside this function never
  execute on existing deploys. Unit 2.1 either removes the
  early-return or adds a post-guard `ensure_pa_web_schema_v2()` block
  that runs unconditionally with `IF NOT EXISTS` idempotency.
- `pa-web-ui/app.py` schema definitions:
  - `pa_web.conversations` L192–201: `id SERIAL`, `session_id TEXT`,
    `role TEXT`, `message TEXT`, `agent_id TEXT`, `agent_name TEXT`,
    `metadata JSONB`, `created_at TIMESTAMP`. **No `conversation_id`.**
  - `pa_web.routing_signals` L203–211: no `conversation_id`.
  - `pa_web.thread_exchanges` L213–224: no `conversation_id`.
  - `pa_web.response_feedback` L226–237: **has `conversation_id
    INTEGER` at L235** — unused by the current frontend (grep in
    chat.js confirms). Unit 2.1 renames to `local_conversation_pk`
    (safer than drop; reversible).
- `pa-web-ui/app.py::GET /api/conversations/<session_id>` at
  **L832–841** — returns flat message list; no conv-scoping.
  Unit 2.1 adds an optional `?conversation_id=` query param and a
  sibling `GET /api/conversations` (no arg) that lists all convs for
  the active agent.
- `pa-web-ui/static/js/chat.js::loadConversationHistory()` at
  **L298–350** — iterates `msg.metadata?.request_id` buckets into
  thread-cards. Unit 2.4 parameterizes on `conversation_id`.
- `pa-web-ui/static/js/chat.js` at **L113–115** — placeholder:
  `this.conversationId = 'default'; // Phase 2 sets per-conversation
  via URL fragment`. Unit 2.4 wires this up.
- `pa-web-ui/static/js/chat.js` send path at **L1053–1068** — already
  sends `conversation_id: this.conversationId || 'default'` on
  `/stream`. Phase 1's `_dispatch_mission_control_direct` (app.py
  L1419–1498) receives it. **The plumbing Phase 2 needs is already
  there** — Phase 2 only has to set a real UUID instead of `"default"`.
- `pa-web-ui/subprocess_pool.py::SubprocessRegistry._handles` at
  **L639** keyed solely on `conv_id`. `test_distinct_convs_spawn_distinct_subprocesses`
  (tests/test_subprocess_pool.py L254–272) already proves isolation.
  **No pool changes needed.**
- `pa-web-ui/templates/index.html` at **L15–16** — `.page-layout >
  .container` is `display: flex` (styles.css L869–874). The
  right-side Task Review Sidebar at **L66** is `position: fixed;
  right: -380px` slide-in (styles.css L949–966) — **NOT in the flex
  flow**. A left rail can slot in as a new flex child of `.page-layout`
  BEFORE `.container` with no grid rewrite.
- `pa-web-ui/templates/index.html` at **L59–76** — existing
  right-sidebar toggle pattern (fixed-position `<aside>`, `.open`
  class flips `translateX`). Unit 2.2's left rail mirrors this with
  `#conversation-rail` / `.conversation-rail-toggle` and its own
  `.open` class — NO z-index collision if kept distinct.
- `pa-routing-handler/src/pa_routing/services/conversation_service.py`
  — only existing `letta.conversations.*` consumer in the repo. Calls
  `.create(agent_id, label)` and reads `.id`. **No prior `.fork()` or
  `.list()` usage anywhere.** Unit 2.1 is greenfield on those APIs.
- `letta/granola_mcp_to_archival.py` L203–212 — one other real-world
  `POST /v1/conversations/` usage pattern in the repo (writes a label,
  reads back `id`). Unit 2.1 mirrors this shape.

### Institutional Learnings

- **Letta 307 redirect on missing trailing slash** (MEMORY.md) —
  applies verbatim to `GET /v1/conversations/` and the fork endpoint.
  Use trailing slash or `-L` with curl.
- **Letta default listing limit is low** (MEMORY.md notes it's 10 for
  agent tools). Unit 2.1 passes explicit `limit=100` on
  `conversations.list`. Revisit if user accumulates >100 conversations.
- **PATCH with list fields REPLACES, not appends** (MEMORY.md,
  `feedback_block_ids_replace.md`) — not currently relevant to Phase 2
  (no list-field patches planned) but retained as a standing Letta
  API gotcha.
- **Letta upgrade schema drift risk** (`memory/project_letta_upgrade_migration.md`):
  the 0.16.6 → 0.16.7 upgrade silently broke conversations when
  `last_message_at` column went missing. Unit 2.1 smoke-tests
  `order_by=last_message_at` before trusting it.
- **No migration framework in pa-web-ui**. All schema bootstrap is
  idempotent `IF NOT EXISTS` DDL at startup. No down-migrations
  anywhere in the repo. **Forward-only is the convention** — accept
  it; mitigate via nullable columns + feature-flag rollback of the UI.
- **No `docs/solutions/` exists** — there is no curated learnings
  corpus for this project. External patterns + repo conventions are
  primary sources.
- **No URL-state handling anywhere in static/js/** — grep for
  `hashchange`, `popstate`, `URLSearchParams`, `pushState` returns
  zero hits. Phase 2 is the first feature to introduce URL-driven
  state. Convention is greenfield.

### External References

External research skipped — Phase 2 is a narrow add-on to Phase 1 with
no net-new technology. Letta fork API semantics come from the live
probe in Unit 2.1; sidebar/rail UI patterns are mirrored from the
existing Task Review Sidebar; deep-linking via query param is
standard-enough SPA convention.

## Key Technical Decisions

- **Schema extension strategy: add nullable TEXT `conversation_id` to
  all four `pa_web` tables; handle the `response_feedback.conversation_id
  INTEGER` collision via coordinated rename PLUS code update in the same
  commit.** Post-review correction: initial plan claimed the INTEGER
  column was "grep-verified unused by the frontend" — which was true but
  INCOMPLETE. `app.py:417, 427, 438, 867` actively write this column via
  `save_response_feedback()` and `/api/feedback`. A standalone rename
  would silently break feedback ingestion on Phase 1. Unit 2.1 therefore
  performs three coordinated changes in one commit: (1) `ALTER TABLE ...
  RENAME COLUMN conversation_id TO local_conversation_pk` **wrapped in
  an `information_schema.columns` type-check guard** (RENAME has no
  `IF EXISTS` form and must not fail on re-run — startup bootstrap
  runs every boot); (2) update `save_response_feedback()` signature and
  the `/api/feedback` route to reference `local_conversation_pk`; (3) add
  the new TEXT `conversation_id` column across all four tables.
- **Fix the `ensure_pa_web_schema()` short-circuit bug.** The existing
  function at app.py L185–187 returns early if the `pa_web` schema
  already exists. This means Phase 2's new DDL (ALTER TABLE ADD
  COLUMN, new `pa_web.conversation_meta` table) would never run on
  existing deployments. Fix: remove the early-return; rely on `IF NOT
  EXISTS` idempotency for CREATE TABLE / ADD COLUMN / CREATE INDEX, and
  wrap the one non-idempotent operation (RENAME COLUMN) in an explicit
  `information_schema.columns` type-check `DO $$ ... END $$` guard
  so double-execution is a no-op.
- **Backfill: resolve MC's `default` alias to its real Letta conv UUID
  ONCE at migration time; use THAT UUID as the backfill value.** Post-
  review correction. Original plan proposed backfilling with the literal
  string `"default"`, which is a letta-code CLI alias — not a UUID.
  `GET /v1/conversations/?agent_id=MC` returns real UUIDs; a
  `"default"` local row would never match under LEFT JOIN. Creating a
  fresh Letta conv and migrating history into it causes split-brain
  (local pa_web.conversations has messages; Letta's new conv has zero
  message records from its perspective — forks would carry no context).
  **Solution: resolve the alias.** letta-code already stores its idea
  of MC's "default" conv as a real UUID on the Letta server
  (`/v1/agents/{MC}/` or a one-shot `letta -p '' --conversation
  default --output-format stream-json` init event exposes it). Unit
  2.1's probe captures this UUID and uses it as the backfill value:
  ```
  default_uuid = <probed from Letta>
  UPDATE pa_web.conversations SET conversation_id = <default_uuid>
    WHERE conversation_id IS NULL
  -- repeat for routing_signals, thread_exchanges, response_feedback
  INSERT INTO pa_web.conversation_meta
    (conversation_id=<default_uuid>, agent_id=MC, label='Main',
     session_id=NULL, created_at=<min(pa_web.conversations.created_at)>)
    ON CONFLICT DO NOTHING
  ```
  Invariant preserved: pa_web.conversations messages and Letta's server
  conv converge on the same UUID. Fork from Main works. Telegram
  continues writing to MC's `default` alias — same server-side conv,
  visible alongside web UI's activity.
- **Backfill runs in a bounded background thread, not on the Flask
  startup path.** Post-review correction. Original plan put the UPDATE
  inside `ensure_pa_web_schema()` at startup. Risk: UPDATE on a loaded
  `pa_web.conversations` could exceed the Docker healthcheck window
  (30s), triggering restart loops. Revised sequence:
  1. At bootstrap: schema DDL only (ADD COLUMN, CREATE TABLE, RENAME
     with guard). These are metadata operations; fast.
  2. Flask starts serving.
  3. A one-shot background thread runs the backfill in batches of
     1000 rows per commit: `UPDATE ... WHERE conversation_id IS NULL
     AND id < (SELECT MIN(id)+1000 FROM ... WHERE ...)`. Logs row
     count pre/post. Expected: minuscule for this deployment, finishes
     in seconds.
  4. The `conversation_meta` INSERT runs after the backfill completes.
  5. Phase-2 UI/routes remain feature-flag-gated until backfill is
     complete (check via a `PA_WEB_UI_BACKFILL_COMPLETE` flag stored
     in-memory; flag-on routes return 503 "migration in progress" if
     backfill hasn't finished).
- **New `pa_web.conversation_meta` table for conv-level metadata.**
  Separate from `pa_web.conversations` (the per-message log) because
  per-conversation attributes are 1:N with message rows. Columns:
  `conversation_id TEXT PK`, `agent_id TEXT`, `session_id TEXT`,
  `label TEXT`, `parent_conversation_id TEXT NULL`, `user_renamed
  BOOLEAN NOT NULL DEFAULT FALSE`, `created_at`, `renamed_at NULL`,
  `metadata JSONB`. `user_renamed` is the gate for LLM auto-naming
  (see R-auto-name decision below) — once the user manually renames,
  auto-name never fires again on that conversation. No `deleted_at`
  column — delete is hard per R9 amendment. `session_id` records the
  creating device for attribution only (list is shared across the
  user's Tailnet devices).
- **Source of truth for conversation LIST is Letta server.**
  `GET /v1/conversations/?agent_id=MC&order_by=last_message_at&limit=100`
  is authoritative. `pa_web.conversation_meta` caches local metadata
  (label, parent link, `user_renamed` flag) that Letta doesn't track.
  Listing endpoint is a JOIN: hit Letta for the canonical list, then
  enrich with local metadata.
- **Source of truth for conversation CONTENT stays in `pa_web.conversations`
  for Phase 2.** Display rehydration reads `pa_web.conversations`
  filtered by `conversation_id`. Migrating to Letta's messages API is
  Phase 3 or later — out of Phase 2 scope because the event shapes
  would require another translation layer.
- **Per-device last-used conv via `localStorage['pa_last_conv_id']`.**
  No URL state. On page load: read the localStorage key; if it's a
  valid UUID in the current list, open that conv; else fall back to
  Letta's MRU. On rail switch: write the new UUID to localStorage.
  Rationale: product + scope reviewers pushed back on URL deep-link
  as vanity for a single-user PA; localStorage gives the "where I
  was yesterday" experience per device without the replaceState +
  popstate + URLSearchParams + deep-link-to-deleted edge cases. If
  cross-device URL sharing ever becomes a real workflow, adding
  `?conv=<uuid>` back later is a 20-line follow-up.
- **Delete is hard-delete with client-side 10s undo toast.** R9
  amended — no soft-delete, no trash, no purge cron. Flow:
  1. User clicks `⋯` → Delete on a rail row.
  2. chat.js: optimistically hides the row, shows a toast
     "Deleted <label>. Undo." with a 10s visible countdown.
  3. If user clicks Undo within 10s: cancel the pending server call;
     rail re-adds the row at its original position.
  4. If 10s expires OR toast is dismissed (click-X, tab-close): fire
     `DELETE /api/conversations/<id>` to the server, which in one
     transaction DELETEs from all 4 pa_web tables + conversation_meta
     + the Letta server copy (`DELETE /v1/conversations/{id}/`).
  5. If the user closes the tab BEFORE the 10s expires, the server
     never sees the delete — conversation survives. Acceptable for a
     single-user PA; user can delete again. Backups at
     `/Volumes/main-filestore/ai-PA-backups/` provide a further
     recovery layer outside the UI.
- **Fork UI: auto-switch to the new fork.** After `POST
  /api/conversations/:id/fork` succeeds, write the new conv_id to
  localStorage and re-render the rail with the new conv selected.
  User stays in the context of "I wanted to explore this branch" —
  forking and staying on the parent would be surprising. A 5s toast
  "Switched to fork. Back to parent." lets the user undo the switch
  (client-only — no server call; just updates localStorage and
  reloads history).
- **Fork turn-lock (R7c) check is server-side AND atomic.** Post-
  review correction. Original plan said "check handle.in_flight, then
  POST to Letta" — leaving a TOCTOU window where the reader thread
  can flip `in_flight` mid-check and a concurrent tab can start a new
  turn before the Letta POST completes. Revised critical section:
  ```
  with handle.state_lock:           # held across the full fork call
      if handle.in_flight:
          raise ParentStreamingException  # → HTTP 409
      handle.forking = True          # new guard flag; prevents
                                     # concurrent send() from flipping
                                     # in_flight while we're POSTing
  try:
      fork_response = letta.post(f'/v1/conversations/{parent}/fork/')
      INSERT INTO conversation_meta ...
  finally:
      with handle.state_lock:
          handle.forking = False
  ```
  `SubprocessHandle.send()` in subprocess_pool.py must check `forking`
  alongside `in_flight` and raise `TurnLockedException` if either is
  true. The nil-handle case (parent is cold / never warmed / LRU-
  evicted) treats as "not in flight, proceed" — safe because within a
  single pa-web-ui instance, the registry is the only in-flight
  authority. Handle is missing → no turn can be in flight.
- **Letta fork copy semantics: PROBED AS UNIT 2.0 PRE-PLAN GATE.** Post-
  review correction. Original plan deferred the probe to Unit 2.1's
  "first step" — but adversarial reviewer flagged this as a design-
  load-bearing unknown. MC has shared memory blocks (`block-90300b77`
  extracted_tasks, calendar, preferences, etc.). If Letta fork
  deep-copies blocks: fork's edits don't propagate — user sees diverged
  world-state without warning. If Letta fork shares block IDs by
  reference: fork mutations pollute the parent — defeats the
  exploratory-branch UX. Neither is acceptable silently. Unit 2.0
  (new, documented below) runs the probe BEFORE any plan commitment
  to Unit 2.1's UI surface, with three pre-planned branches:
  - Branch A (deep-copy blocks): ship as-is; fork is a genuine
    isolated state snapshot; document this in the fork banner
    ("This fork has its own copy of shared memory").
  - Branch B (shared block IDs): fork UI requires an explicit block
    detachment step before any write is accepted, OR we block fork
    on MC and limit to other agents.
  - Branch C (no block context at all): fork is essentially a new
    conv with only the message history — reframe UX to set expectations.
- **Conversation label: auto-timestamp on create; LLM-renamed after
  first turn; manual rename wins forever.** (R-auto-name.) Flow:
  1. `POST /api/conversations` creates with label = `"New conversation
     <YYYY-MM-DD HH:MM>"` (local timezone, client-submitted since
     client knows user's TZ). `user_renamed=FALSE`. No LLM call yet.
  2. On the first `result` event in the conversation, the Phase-1
     translation layer (`app.py::_stream_direct_generator`) checks:
     `user_renamed IS FALSE AND label matches the timestamp pattern`.
     If so, it fires an in-band one-shot to litellm:
     ```
     model     = "gpt-4.1-mini"
     prompt    = f"Summarize this in 3-6 words as a conversation title: "
                 f"{first_user_message}"
     max_tokens = 20
     timeout   = 3s (silent fail on timeout)
     ```
  3. On success: `UPDATE conversation_meta SET label=<new>,
     renamed_at=now() WHERE conversation_id=<id> AND user_renamed=FALSE`
     (the predicate makes it race-safe: a user rename between the LLM
     call and the UPDATE wins). Then emit a NEW SSE event BEFORE the
     `done` event:
     `{"type": "conversation_label_updated", "conv_id": <id>, "label": <new>}`.
  4. chat.js handles the event by calling
     `window.conversationRail.updateLabel(conv_id, new_label)` — the
     rail row's text flips live within ~1s of first turn completing.
  5. If the user renames manually (via rail `⋯` → Rename), `PATCH
     /api/conversations/<id>` sets `user_renamed=TRUE`. Auto-name
     never fires again on this conversation.
  6. Feature-flagged: `PA_WEB_UI_AUTONAME_ENABLED` (default true).
     If false, skip the litellm call entirely; labels stay as
     timestamps. If litellm is unreachable / slow / errors, silent
     fail; labels stay as timestamps. No user-visible error surface.
  7. Cost: gpt-4.1-mini at ~200 input + 20 output tokens per rename
     ≈ $0.00004. At 50 new conversations/month ≈ $0.002/month. Already
     in litellm infra — no new API key.
  8. Integration posture: this is first-class, not a bolt-on. It
     reuses the existing event pipeline (new event type joins `text`,
     `tool_call`, `done`), the existing `conversation_meta` schema
     (adds `user_renamed`), and the existing rename UX (user rename
     wins via the same flag). Unit 2.5 implements it; tests in
     `test_stream_direct.py` cover the schema-drift-safe predicate
     and the skipped-when-flag-off path.
- **Left-rail UI mirrors the right-sidebar pattern.** Same
  fixed-position `<aside>` + `.open` class toggling + tabbed inner
  content. Rationale: consistent UX vocabulary and no CSS grid
  rewrite. Explicit z-index namespacing (right sidebar at z-index
  100; left rail at 99) to avoid overlap when both open on mobile.
- **No migrations framework added.** Forward-only DDL via an updated
  `ensure_pa_web_schema()`. The feature flag (new
  `PA_WEB_UI_PHASE_2_ENABLED`) gates the UI and backend routes;
  rollback is flag-off + container restart. Backfilled `conversation_id
  = <default_uuid>` remains correctly populated even after flag-off —
  it's a valid UUID matching a real Letta conversation.
- **Phase-1 → Phase-2 migration path resolves the `default` alias.**
  (See "Backfill" decision above for the procedure.) The result is
  that Phase-1 history appears in the switcher as a single conversation
  labeled "Main" corresponding to MC's real `default` conv on the Letta
  server. Telegram continues writing to the same conv via the alias —
  no surface divergence. Subsequent conversations users create get
  their own real Letta UUIDs. There is NO synthetic bucket and NO
  legacy namespace; everything routes through a single UUID-keyed
  space from migration onward.

## Open Questions

### Resolved During Planning

- **Source of truth for conversation list?** Resolved: Letta server
  canonical + `pa_web.conversation_meta` enrichment JOIN.
- **Response shape of `POST /v1/conversations/{id}/fork`?** Unit 2.1
  probes live and documents in
  `docs/reference/letta-conversations-fork.md`. Based on the existing
  `letta.conversations.create` signature precedent
  (`pa-routing-handler/services/conversation_service.py`), the
  response likely has `.id`, `.label`, `.agent_id`, and possibly
  `.parent_conversation_id` fields. Plan assumes these; Unit 2.1
  verifies and adjusts.
- **parent_conversation_id: local column or Letta metadata?**
  Resolved: local column in `pa_web.conversation_meta`. Rationale:
  Letta may not expose `parent_conversation_id` in the list API, and
  we need it for fast switcher-tree rendering.
- **INTEGER / TEXT conversation_id collision?** Resolved: rename
  existing `response_feedback.conversation_id` to `local_conversation_pk`,
  reserve the `conversation_id` name for the new TEXT Letta UUID column
  across all four tables. **Coordinated code update in the same commit**
  (`save_response_feedback` + `/api/feedback` route in app.py) — the
  column is actively written (app.py:417, 427, 438, 867), so a
  standalone rename silently breaks feedback ingestion.
- **Backfill value?** Resolved: the real UUID behind MC's `default`
  alias, probed once during Unit 2.0. `"default"` as a literal TEXT
  value would never match the Letta list's UUIDs under LEFT JOIN.
  Creating a fresh Letta conv for backfill causes split-brain
  (pa_web.conversations has messages; Letta's new conv doesn't).
  Resolving the existing alias preserves Phase-1 invariant and
  converges both sides on one UUID.
- **Fork copy semantics probe scheduling?** Resolved: moved from Unit
  2.1's first step to a dedicated Unit 2.0 pre-plan gate. Probe
  outcome branches Unit 2.3 scope (see "Letta fork copy semantics"
  decision above).
- **URL convention?** Resolved: NO URL state. Per-device
  `localStorage['pa_last_conv_id']` handles the "where was I last"
  experience; MRU from Letta fallback for fresh browsers. If cross-
  device URL sharing becomes a real workflow, adding it back is a
  ~20-line follow-up.
- **Delete semantics?** Resolved: hard-delete with 10s client-side
  undo toast. No soft-delete, no trash tier, no purge cron, no
  Phase 2.5. On confirmed delete, server transaction removes all 4
  pa_web tables + conversation_meta + Letta server copy.
- **Fork mid-stream?** Resolved: HTTP 409 if parent handle in_flight.
- **Conversation label auto-naming?** Resolved: LLM-auto-name on
  first turn completion (R-auto-name). gpt-4.1-mini in-band on the
  SSE pipeline; `user_renamed` column gates replays; feature-flagged
  for killswitch. See Unit 2.5.
- **Left rail z-index vs right sidebar?** Resolved: 99 vs 100
  respectively; explicit in CSS.

### Deferred to Implementation

- **[Affects Unit 2.0][Needs research — pre-plan gate]** Fork response
  shape + memory-block copy semantics + `order_by=last_message_at`
  support on Letta 0.16.7 + `default` alias resolution path. All
  probed together in Unit 2.0; outputs drive Unit 2.1's Branch A/B/C
  choice and the backfill UUID. See Unit 2.0 details below.
- **[Affects Unit 2.2][Technical]** Mobile left-rail UX: slide-in
  from the left edge (mirroring the right sidebar)? Or a hamburger
  menu? Mirroring is simpler (one pattern, two positions); hamburger
  is more conventional on mobile. Default: mirror — consistency with
  the existing Task Review sidebar. Revisit after one week of mobile use.
- **[Affects Unit 2.3][Technical]** Fork-from-here button
  affordance — always visible on hover? Hidden behind a `⋯` menu?
  Default: `⋯` menu (avoids visual clutter). Menu item shows the
  keyboard hint `[j]` per R13 (reuse letta-code's keyboard vocabulary).
- **[Affects Unit 2.4][Resolved in plan]** Rename
  `pa_chat_session_id` localStorage key to `pa_chat_device_id`
  (semantic rename; value unchanged). Execute in Unit 2.4; read old
  key as fallback so already-open tabs don't lose state.
- **[Affects Phase 2 observability][Technical]** `/api/subprocess/status`
  currently reports handles across all conversations. With per-conv
  subprocesses, that list grows. Unit 1.6's endpoint already handles
  this correctly via `list_handles()`, but UX may want to group by
  "active" vs "idle".
- **[Affects Unit 2.5][Technical]** Exact litellm endpoint URL and
  model name for the auto-name one-shot. Default: `gpt-4.1-mini`
  via the existing litellm proxy at `http://litellm:4000` (already
  wired up for Phase 1 MC). Revisit if the model deprecates or if
  a Haiku-tier model turns out to give better titles — small
  experimentation budget during Unit 2.5.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance
> for review, not implementation specification.*

### Schema shape (post-Unit-2.1)

```
pa_web.conversations
  id SERIAL PK
  session_id TEXT
  role TEXT
  message TEXT
  agent_id TEXT
  agent_name TEXT
  metadata JSONB
  created_at TIMESTAMP
  conversation_id TEXT           -- NEW; backfilled to "default"

pa_web.routing_signals
  ... existing columns ...
  conversation_id TEXT           -- NEW

pa_web.thread_exchanges
  ... existing columns ...
  conversation_id TEXT           -- NEW

pa_web.response_feedback
  ... existing columns ...
  local_conversation_pk INTEGER  -- RENAMED from conversation_id
  conversation_id TEXT           -- NEW

pa_web.conversation_meta          -- NEW
  conversation_id TEXT PK         -- Letta UUID
  agent_id TEXT
  session_id TEXT                 -- creating device (attribution only)
  label TEXT
  parent_conversation_id TEXT NULL
  user_renamed BOOLEAN NOT NULL DEFAULT FALSE  -- gates auto-rename
  created_at TIMESTAMP
  renamed_at TIMESTAMP NULL
  metadata JSONB                  -- reserved
```

### Request flow — conversation switch

```
user clicks sidebar entry for conv-B
  → chat.js: conversationRail.switchTo("conv-B")
  → chat.js: abort current EventSource/fetch reader if any
  → chat.js: this.conversationId = "conv-B"; this.lastSeqId = null
  → chat.js: localStorage.setItem('pa_last_conv_id', 'conv-B')
  → chat.js: loadConversationHistory("conv-B")
     → GET /api/conversations/<session_id>?conversation_id=conv-B
     → renders thread-cards from pa_web.conversations rows
  → if /api/subprocess/status shows conv-B in_flight:
     → re-subscribe with since=<current_seq_id> to resume live tokens
  → next message send includes conversation_id=conv-B
     → POST /stream routes to SubprocessRegistry.ensure(MC, "conv-B")
     → pool spawns a new subprocess if conv-B is cold; else reuses
```

### Request flow — auto-rename after first turn

```
first user message in conv-C (label still the timestamp default)
  → letta-code subprocess streams events through the Phase-1 pipeline
  → reader thread emits: text, text, text, ..., result
  → app.py::_stream_direct_generator translator layer, on seeing `result`:
     if PA_WEB_UI_AUTONAME_ENABLED
        AND conversation_meta.user_renamed = FALSE
        AND conversation_meta.label matches '^New conversation \d{4}-\d{2}-\d{2}':
       → litellm.complete(model=gpt-4.1-mini, prompt=<summarize first user msg>, 3s timeout)
       → on success: UPDATE conversation_meta SET label=<new>, renamed_at=now()
                     WHERE conversation_id=<id> AND user_renamed=FALSE
       → emit SSE: {"type": "conversation_label_updated", "conv_id": ..., "label": ...}
     → emit SSE: {"type": "done", ...}
  → chat.js.handleEvent('conversation_label_updated', ev):
     → window.conversationRail.updateLabel(ev.conv_id, ev.label)
     → rail DOM's row text flips in place
  → chat.js.handleEvent('done', ev):
     → existing terminal handler (no change)
```

### Request flow — hard-delete with undo toast

```
user clicks ⋯ → Delete on conv-X row
  → chat.js: conversationRail.softHide(conv-X)  # visual only
  → chat.js: show toast "Deleted <label>. Undo. [■■■■■■■■■□] 10s"
  → chat.js: schedule DELETE call at T=10s via setTimeout
  → if user clicks Undo within 10s:
     → clearTimeout; conversationRail.unHide(conv-X)
     → no server call; conv still exists
  → if 10s expires OR toast dismissed OR user sends next message:
     → DELETE /api/conversations/conv-X
        → backend transaction:
          DELETE FROM pa_web.conversations WHERE conversation_id = conv-X
          DELETE FROM pa_web.thread_exchanges WHERE ...
          DELETE FROM pa_web.routing_signals WHERE ...
          DELETE FROM pa_web.response_feedback WHERE ...
          DELETE FROM pa_web.conversation_meta WHERE conversation_id = conv-X
          DELETE http://letta:8283/v1/conversations/conv-X/
        → invalidate subprocess handle (if any) after pushing
          {type:"conversation_deleted"} to attached subscribers
  → if user closes tab before 10s expires:
     → server never sees the delete; conv survives
     → acceptable for a single-user PA; backups provide further recovery
```

### Request flow — fork from assistant message

```
user clicks "…" → "Fork from here" on message M in conv-A
  → chat.js: fetch POST /api/conversations/conv-A/fork
     with body {"parent_request_id": M.request_id, "label": optional}
  → backend: acquire handle.state_lock for conv-A (if handle exists)
     - if handle.in_flight OR handle.forking: 409 parent_conversation_streaming
     - else set handle.forking = True (releases lock)
  → backend: POST http://letta:8283/v1/conversations/conv-A/fork/?agent_id=MC
     - validate response: id present and UUID-shaped else 502 Bad Gateway
     - response: {id: "conv-C", label: "...", parent_conversation_id: "conv-A"}
  → backend: INSERT INTO pa_web.conversation_meta
       (conversation_id="conv-C", parent_conversation_id="conv-A",
        agent_id=MC, session_id=<caller>, label=<from body or autogen>,
        user_renamed=FALSE, created_at=now())
  → backend: re-acquire handle.state_lock, set handle.forking = False
  → backend: return 201 {conversation_id: "conv-C", label: "...", parent_conversation_id: "conv-A"}
  → chat.js: conversationRail.add(new conv); auto-switch to conv-C
  → chat.js: localStorage.setItem('pa_last_conv_id', 'conv-C')
  → chat.js: 5s toast "Switched to fork. Back to parent." (undo)
```

### Layout

```
┌─ page-layout (flex) ──────────────────────────────────────────┐
│ ┌─ conv-rail (aside, fixed-left, z=99) ─┐  ┌─ container ────┐ │
│ │ Conversations                  [+New] │  │ chat main pane │ │
│ │ • Main                                │  │                │ │
│ │ • DSLP draft review                   │  │                │ │
│ │ • ↳ Fork of DSLP draft review         │  │                │ │
│ │ • Grocery planning                    │  │                │ │
│ │                                       │  │                │ │
│ │ (no Trash section — hard-delete + 10s │  │                │ │
│ │  undo toast replaces soft-delete)     │  │                │ │
│ └──────────────────────────────────────┘   └────────────────┘ │
│                                        ┌─ task-sidebar (z=100)┐│
│                                        │ Tasks (right overlay)││
│                                        └──────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

## Implementation Units

### Unit 2.0: Letta fork + "default" alias probe (pre-plan gate)

**Goal:** Empirically determine two Letta 0.16.7 behaviors that are
load-bearing for the rest of Phase 2. No code changes ship from this
unit — the output is a reference document that may revise Unit 2.1's
scope.

**Requirements:** R10 (fork), R18 (MRU ordering)

**Dependencies:** None (runs before Unit 2.1)

**Files:**
- Create: `docs/reference/letta-conversations-fork.md` — empirical
  reference.
- Create: `docs/reference/letta-default-alias-resolution.md` — how
  "default" on an agent maps to a real UUID.

**Approach:**
1. **Resolve MC's `default` conv to a UUID.** Several candidate paths:
   ```bash
   # Path A: agent metadata may expose current conv
   curl -s "http://letta:8283/v1/agents/<MC>/" | jq
   # Path B: one-shot letta-code prompt captures init event with UUID
   docker compose exec pa-web-ui bash -lc \
     'letta --agent <MC> --conversation default --output-format stream-json -p "" 2>/dev/null | head -1 | jq'
   # Path C: conversations.list with agent filter
   curl -s "http://letta:8283/v1/conversations/?agent_id=<MC>&limit=20" | jq
   ```
   Record the UUID, its stability (does resolving the alias twice
   return the same UUID?), and the preferred resolution path for
   Unit 2.1's migration.
2. **Probe fork semantics.** Fork MC's `default` conv to a test conv:
   ```bash
   curl -v -X POST \
     "http://letta:8283/v1/conversations/<default_uuid>/fork/?agent_id=<MC>"
   ```
   Capture the response body exactly. Then inspect the fork vs the
   parent:
   - Does the fork have its own message history (`GET
     /v1/conversations/{fork_id}/messages`)? Does it match the
     parent's history at fork time, or is it empty?
   - Does the fork see the parent's memory blocks (`GET
     /v1/agents/{MC}/core-memory/blocks` viewed via the fork)?
   - If the fork mutates a shared block (e.g., extracted_tasks),
     does the parent see the mutation?
   - Does `order_by=last_message_at` work on `GET /v1/conversations/`?
     If not, what values does the server accept?
3. **Write both reference docs.** Include observed request/response
   JSON verbatim, the stability characteristics, and — for fork —
   classify into Branch A / B / C per the "Letta fork copy semantics"
   decision above. Unit 2.1 then executes the matching plan.

**Test scenarios:**
- Probe is a notebook-style investigation, not a pytest suite.
  Reference docs are the deliverable. If Unit 2.1 discovers schema
  drift later (e.g., fork response shape changed in a 0.16.8 upgrade),
  re-run the probe; bump version notes.

**Verification:**
- `docs/reference/letta-conversations-fork.md` and
  `docs/reference/letta-default-alias-resolution.md` exist and are
  reviewed by the user before Unit 2.1 opens.

---

### Unit 2.1: Schema extension + conversation list/CRUD backend + fork API reference

**Goal:** `pa_web` schema supports per-conversation data; backend
exposes CRUD for conversations (list, create, rename, soft-delete,
fork); `docs/reference/letta-conversations-fork.md` documents the
Letta fork API's actual response shape. Phase-2 feature flag added
(default OFF).

**Requirements:** R9, R10, R11, R18

**Dependencies:** Phase 1 complete and stable (it is, as of 2026-04-20)

**Files:**
- Modify: `pa-web-ui/app.py` — fix `ensure_pa_web_schema()` short-circuit
  bug; add new DDL (ALTER + CREATE TABLE conversation_meta); add new
  routes `GET /api/conversations`, `POST /api/conversations`,
  `PATCH /api/conversations/<id>`, `DELETE /api/conversations/<id>`,
  `POST /api/conversations/<id>/fork`; extend existing
  `GET /api/conversations/<session_id>` with optional
  `?conversation_id=` filter.
- Modify: `docker-compose.yml` — add `PA_WEB_UI_PHASE_2_ENABLED` env
  var (default false).
- Create: `docs/reference/letta-conversations-fork.md` — live-probe
  documentation of request params, response shape, and copy semantics.
- Create: `pa-web-ui/tests/test_conversations_api.py` — CRUD and fork
  route tests with mocked Letta server.
- Create: `pa-web-ui/tests/test_pa_web_schema.py` — idempotency of
  the updated schema bootstrap.

**Approach:**

1. **Consume Unit 2.0's probe output.** Unit 2.0 wrote the fork
   reference doc and the default-alias-resolution doc. Use those as
   input — do NOT re-probe during Unit 2.1. If Unit 2.0 classified
   the fork as Branch B or C, adjust Unit 2.3 scope accordingly
   (see Unit 2.0's branches under "Letta fork copy semantics" in
   Key Decisions).

2. **Fix schema bootstrap.** Remove the early-return at
   `ensure_pa_web_schema()` L185–187. Replace with a comment
   explaining the idempotency convention. Existing CREATE TABLE /
   CREATE INDEX statements already use IF NOT EXISTS.

3. **Extend DDL.** New statements inside `ensure_pa_web_schema()`:
   - `ALTER TABLE pa_web.conversations ADD COLUMN IF NOT EXISTS
     conversation_id TEXT;` (and three more for the sibling tables).
   - `CREATE TABLE IF NOT EXISTS pa_web.conversation_meta (...);`
   - **Guarded RENAME (not idempotent without the guard):**
     ```sql
     DO $$
     BEGIN
       IF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='pa_web'
                  AND table_name='response_feedback'
                  AND column_name='conversation_id'
                  AND data_type='integer') THEN
         ALTER TABLE pa_web.response_feedback
           RENAME COLUMN conversation_id TO local_conversation_pk;
       END IF;
     END $$;
     ```
     This guard ensures the second container startup is a no-op —
     ensure_pa_web_schema() runs every boot.

4. **Coordinated code update for response_feedback.** In the SAME
   commit as the DDL:
   - `save_response_feedback()` in app.py:417 renames its parameter
     from `conversation_id: int` → `local_conversation_pk: int`,
     updates the INSERT column list at app.py:427 (and VALUES slot
     at app.py:438) to use `local_conversation_pk`.
   - `/api/feedback` route at app.py:867 renames the call kwarg to
     match. Also inspects the request body for EITHER
     `local_conversation_pk` (new field) OR legacy `conversation_id`
     (back-compat for any stale tab); if both present, new takes
     precedence.
   - Add a pytest that POSTs to `/api/feedback` with a legacy body
     and asserts row insert succeeds under the renamed column.
   - **Without this coordination the feedback path breaks silently
     on deploy.** Grep confirms references at app.py:417, 427, 438,
     867 — all must update together.

5. **Backfill (runs in a background thread AFTER Flask starts
   serving).** Sequence:
   - On startup, `ensure_pa_web_schema()` completes DDL only.
   - A separate thread `_run_phase2_backfill()` fires with a small
     delay (5s) to let Flask bind, then:
     ```python
     default_uuid = _resolve_mc_default_conv()
     # See docs/reference/letta-default-alias-resolution.md for
     # which endpoint populates this.
     for table in ("conversations", "routing_signals",
                   "thread_exchanges", "response_feedback"):
         batch_update(table, where="conversation_id IS NULL",
                      set_=f"conversation_id = '{default_uuid}'",
                      batch_size=1000)
     _insert_conversation_meta_default(default_uuid)
     _mark_backfill_complete()
     ```
   - `_resolve_mc_default_conv()` uses the resolution path Unit 2.0
     identified (likely `GET /v1/agents/{MC}/` or a zero-prompt
     letta-code one-shot).
   - A module-level flag `_BACKFILL_COMPLETE` gates Phase-2 routes:
     POST/PATCH/DELETE/fork return HTTP 503
     `{"error": "backfill_in_progress"}` until the thread finishes.
   - GET/list routes can serve during backfill (read-only).

6. **CRUD routes.** All gated by ingress_guard (Phase 1) AND the new
   `PA_WEB_UI_PHASE_2_ENABLED` flag. When flag is OFF, routes return
   HTTP 503 `{"error": "feature_disabled", "flag":
   "PA_WEB_UI_PHASE_2_ENABLED"}` — 503 is clearer for debugging than
   404; Tailscale is the real perimeter, so information hiding at
   the app layer is paranoid.
   - `GET /api/conversations`: fetch Letta list → LEFT JOIN with
     `pa_web.conversation_meta`. Returns `{conversations: [{id, label,
     agent_id, last_message_at, parent_conversation_id, created_at,
     user_renamed}]}`. No deleted-filter branch — hard-delete removes
     rows entirely; there's nothing to filter.
   - `POST /api/conversations`: body `{label?: string}`. Calls
     `POST /v1/conversations/` on Letta with `agent_id=MC, label=...`.
     Inserts `conversation_meta` row with `user_renamed=FALSE` (since
     label is either the default timestamp or user-provided at create).
     Note: if body includes a label, `user_renamed=TRUE` (user
     explicitly named it — auto-name must not overwrite). Returns the
     created conv.
   - `PATCH /api/conversations/<id>`: body `{label: string}`. Updates
     `conversation_meta.label` and sets `user_renamed=TRUE` + bumps
     `renamed_at`. Does NOT call Letta (local is SoT for labels).
     Emits `{"type": "conversation_label_updated"}` to any attached
     subscribers so other tabs on the same conv see the rename live.
   - `DELETE /api/conversations/<id>`: **hard-delete in a single
     transaction.** Atomic sequence:
     1. If a live handle exists in subprocess_registry, walk
        `handle.subscribers` and push
        `{"type": "conversation_deleted", "conv_id": <id>}` into each
        queue.
     2. `subprocess_registry.invalidate(conv_id)` — kills the
        subprocess.
     3. Begin transaction:
        - `DELETE FROM pa_web.conversations WHERE conversation_id = <id>`
        - `DELETE FROM pa_web.thread_exchanges WHERE conversation_id = <id>`
        - `DELETE FROM pa_web.routing_signals WHERE conversation_id = <id>`
        - `DELETE FROM pa_web.response_feedback WHERE conversation_id = <id>`
        - `DELETE FROM pa_web.conversation_meta WHERE conversation_id = <id>`
     4. Commit.
     5. `DELETE http://letta:8283/v1/conversations/<id>/` (Letta
        server copy). This is outside the transaction — if it fails,
        log it and continue (the local DELETE already succeeded;
        orphan Letta conv can be cleaned up via a reconciliation job).
     `/stream` dispatch in Phase 1 must also check for a nonexistent
     conv_id on each new request; if `conversation_meta` has no row,
     return HTTP 410 Gone `{"error": "conversation_deleted"}`.
     Prevents reconnect races.
   - `POST /api/conversations/<id>/fork`: body `{label?: string,
     parent_request_id?: string}`. Flow:
     1. Check that parent `conversation_meta` row still exists —
        if not (user hard-deleted it), return HTTP 410 Gone.
     2. Acquire parent's `handle.state_lock` (if handle exists);
        nil handle = parent is cold, proceed. Under the lock:
        ```
        if handle.in_flight or handle.forking:
            raise HTTP 409 {"error": "parent_conversation_streaming"}
        handle.forking = True
        ```
     3. Call Letta fork (POST to `/v1/conversations/{id}/fork/`).
        The `forking` flag prevents concurrent `send()` from starting
        a new turn during the Letta network round-trip.
     4. Validate Letta response shape: assert `id` present and
        UUID-shaped; reject 200-with-bad-shape as HTTP 502 Bad
        Gateway `{"error": "letta_malformed_fork_response"}`.
     5. INSERT `conversation_meta` row with
        `parent_conversation_id=<id>`, label defaulted/explicit,
        session_id = requesting device, created_at = now.
     6. Release `handle.forking = False` under the lock.
     7. Return HTTP 201 with the new conv.
     `SubprocessHandle.send()` in subprocess_pool.py must be updated
     (in the same commit) to check both `in_flight` AND `forking` and
     raise `TurnLockedException` on either.

6. **History filter.** Extend
   `GET /api/conversations/<session_id>` with `?conversation_id=`:
   add `AND conversation_id = %s` to the SQL WHERE when provided.
   Default behavior (no filter) unchanged for back-compat.

**Patterns to follow:**
- Phase 1's `_dispatch_mission_control_direct` pattern for
  subprocess-registry interaction (state lock checks; exception
  translation to HTTP status).
- `pa-routing-handler/src/pa_routing/services/conversation_service.py`
  for the `POST /v1/conversations/` shape.
- `letta/granola_mcp_to_archival.py:203–212` for auth + response
  parsing.
- `pa-web-ui/app.py::save_conversation_message` for psycopg2
  idempotent writes under `with get_db_connection() as conn`.

**Test scenarios:**
- Happy path: schema bootstrap on a fresh DB creates all tables and
  columns; second run is a no-op (IF NOT EXISTS holds).
- Happy path: schema bootstrap on a Phase-1-era DB (schema exists,
  but new columns don't) correctly ADDs the new columns and the
  conversation_meta table.
- Edge case: response_feedback with existing rows and a populated
  INTEGER conversation_id has those values preserved in the renamed
  `local_conversation_pk` column.
- Happy path: `GET /api/conversations` returns Letta list JOINed
  with local meta.
- Happy path: `POST /api/conversations` creates conv on Letta AND
  inserts local meta; returns `{id, label, agent_id, created_at,
  user_renamed}`; `user_renamed=FALSE` when no label supplied;
  `user_renamed=TRUE` when label supplied.
- Edge case: `POST /api/conversations` — Letta returns 500; local
  meta is NOT inserted (no ghost rows).
- Happy path: `PATCH /api/conversations/<id>` with `label` sets
  `user_renamed=TRUE`; subsequent auto-name skips this conv.
- Happy path: `DELETE /api/conversations/<id>` removes rows from all
  5 tables + Letta; subsequent `GET /api/conversations/<sid>?conversation_id=<id>`
  returns empty list (nothing to rehydrate); subsequent `GET
  /api/conversations` does not include the deleted conv.
- Edge case: `DELETE` on a conv with an active subprocess handle —
  subscriber receives `{type: "conversation_deleted"}` SSE event
  before handle.invalidate fires.
- Edge case: `DELETE` where Letta server DELETE returns 500 — local
  tables still cleared; log written; Letta orphan flagged for
  reconciliation.
- Happy path: `POST /api/conversations/<id>/fork` creates a fork
  with parent link; subsequent `GET /api/conversations` shows both.
- Error path: `POST /api/conversations/<id>/fork` when parent is
  streaming → HTTP 409 `{error: "parent_conversation_streaming"}`.
- Error path: `POST /api/conversations/<id>/fork` when parent is
  deleted → HTTP 410 Gone.
- Error path: `POST /api/conversations/<id>/fork` when Letta returns
  a 200 with a malformed body (no `id`) → HTTP 502 Bad Gateway;
  no conversation_meta row inserted.
- Flag OFF: every new route returns HTTP 503.
- Integration: end-to-end fork smoke with a live Letta server —
  verifies the fork API reference doc is accurate.

**Verification:**
- `docs/reference/letta-conversations-fork.md` exists and matches
  observed server behavior.
- DB inspection after bootstrap shows 4 tables with `conversation_id`
  and a new `conversation_meta` table.
- Flag-OFF behavior preserves Phase-1 behavior exactly (smoke a
  round-trip via /stream to confirm).
- Full pytest suite passes.

---

### Unit 2.2: Conversation switcher UI + left rail + undo toast

**Goal:** User-facing conversation list rail with create / rename /
hard-delete (with 10s undo toast) actions. Mirrors the right Task
Review sidebar's visual vocabulary. Per-device last-used selection via
localStorage. Feature-flagged.

**Requirements:** R9 (amended), R11, R18 (amended)

**Dependencies:** Unit 2.1

**Files:**
- Modify: `pa-web-ui/templates/index.html` — add `<aside
  id="conversation-rail" class="conversation-rail">` sibling BEFORE
  `.container`; add a toggle button (`#conversation-rail-toggle`).
  Add `<div id="undo-toast-container">` near the bottom for toast
  rendering.
- Modify: `pa-web-ui/static/css/styles.css` — `.conversation-rail`
  styles mirroring `.task-sidebar` pattern with `left: -380px` and
  z-index=99 (right sidebar stays at 100). `.undo-toast` styles for
  the 10s countdown toast.
- Create: `pa-web-ui/static/js/conversation_rail.js` — standalone
  class `ConversationRail` handling list fetch, render, switch,
  create, rename, hard-delete (with 10s client-side timer).
- Modify: `pa-web-ui/static/js/chat.js` — initialize
  `window.conversationRail` on DOMContentLoaded; on conv switch,
  abort current EventSource, update `this.conversationId`, clear
  `lastSeqId`, refetch history, write `pa_last_conv_id` to localStorage.
- Modify: `pa-web-ui/templates/index.html` — add
  `<script src="/static/js/conversation_rail.js?v=1"></script>` before
  chat.js script tag (load order matters — chat.js references
  `window.conversationRail`).

**Approach:**

1. **CSS layout.** Add `.conversation-rail` with fixed-left
   positioning, 360px wide, `left: -380px` slide-in. Toggle button
   on the outer edge (mirror of right sidebar's toggle). Z-index 99.
   Mobile (≤768px): full-width overlay; opening the right Task
   Review sidebar auto-closes the left rail and vice versa (mutually
   exclusive on narrow viewports). Desktop (>768px): both can
   coexist.

2. **Rail component.** `ConversationRail` class:
   - `init()`: fetch `/api/conversations`. Select conv via resolution
     order: (a) `localStorage['pa_last_conv_id']` if valid in the
     fetched list, (b) MRU from the list per R18. Bind click handlers.
   - `render(list)`: ONE flat list (no Active/Trash split — hard-
     delete means no trash exists). Each row shows label, last-activity
     timestamp, parent indicator if forked (`↳` prefix, 1-level only),
     and a `⋯` menu for Rename / Delete / Fork-from-here.
   - `switchTo(conv_id)`: updates rail highlight, calls
     `window.chatUI.switchConversation(conv_id)`, writes
     `localStorage['pa_last_conv_id']`.
   - `create()`: inline-insert a new row in edit mode; on Enter/blur,
     POST `/api/conversations` with the typed label (or the default
     timestamp if empty), then auto-switch. If POST fails, remove the
     row and show a toast.
   - `rename(conv_id)`: inline-edit the row's label (double-click or
     ⋯ → Rename enters edit mode). On commit, PATCH
     `/api/conversations/<id>` with the new label; server sets
     `user_renamed=TRUE`.
   - `updateLabel(conv_id, new_label)`: external-source label change
     (e.g., Unit 2.5's auto-rename event) — update DOM in place.
   - `delete(conv_id)`: optimistic UI (hide row), show 10s undo toast,
     schedule `DELETE /api/conversations/<id>` at T=10s. If Undo is
     clicked, clearTimeout + un-hide. If another Delete is clicked on
     a different conv within the first toast's window, the first
     toast's DELETE fires immediately (no queue).
   - `addAndSwitch(conv)`: used by Unit 2.3 post-fork — inserts new
     conv into list, switches to it.

3. **Undo toast component.** A small `<div class="undo-toast">`
   floating bottom-right: `Deleted "<label>". [Undo] [■■■■■■□□□□]`.
   Progress bar animates over 10s via CSS transition. Click Undo
   fires `clearTimeout` + removes toast + unhides row. Click the ✕
   dismisses the toast AND fires the DELETE immediately (user
   explicitly committed). Dismiss on tab close is acceptable — server
   never hears about it, so conv survives.

4. **chat.js integration.**
   `ChatUI.switchConversation(newConvId)`:
   - Abort any active EventSource via `this._currentStreamAbort.abort()`.
   - `this.conversationId = newConvId`
   - `this.lastSeqId = null`
   - `this._resetUIForConversationSwitch()` — clear thread cards,
     reset `threads` Map
   - `localStorage.setItem('pa_last_conv_id', newConvId)`
   - `await this.loadConversationHistory(newConvId)` (Unit 2.4)
   - Check `/api/subprocess/status?conv=<newConvId>` — if in_flight,
     re-subscribe with `since=<current_seq_id>` to continue live
     rendering.

5. **CSRF token scope.** All new routes continue to require CSRF
   double-submit. The existing `paCsrfHeaders()` helper handles it.

**Patterns to follow:**
- `pa-web-ui/static/js/sidebar.js` — structural template for the
  class-based sidebar.
- Existing `#task-sidebar` DOM and CSS — visual vocabulary.
- `pa-web-ui/static/js/chat.js::ensureThinkingAccordion` — inline-
  edit pattern for rename.

**Test scenarios:**
- Happy path: rail renders on page load with a single flat list.
  `localStorage['pa_last_conv_id']` selects correctly if valid.
- Happy path: click an entry → conversationId updates, history
  reloads, EventSource aborts cleanly, new one subscribes if in_flight.
- Happy path: Create → inline edit → Enter → new conv appears and
  auto-switches.
- Happy path: Rename → inline edit → Enter → server PATCH → label
  updates; `user_renamed=TRUE` persists.
- Happy path: Delete → row hides, toast shows 10s countdown. Wait
  out → DELETE fires → row is permanently gone.
- Undo: Delete → click Undo within 10s → row re-appears; no server
  call.
- Dismiss-forces-commit: Delete → click toast ✕ → DELETE fires
  immediately.
- Tab close: Delete → close tab → no server call; conv survives.
- Label update: server pushes `conversation_label_updated` SSE (from
  Unit 2.5) → rail row label flips in place.
- Edge case: `localStorage['pa_last_conv_id']` points at a conv that
  no longer exists → fall back to MRU, log console warning.
- Error path: `/api/conversations` returns 500 → rail shows error
  state with retry.
- Error path: DELETE returns 500 on fire — toast shows "Delete
  failed. Retry?"; row re-appears.
- Integration: open on phone + desktop with same session — switching
  on one device does NOT force the other to switch (per-device
  `localStorage`).
- Mobile: tapping a row auto-closes the rail after 150ms.
- Mobile: opening the right Task Review sidebar auto-closes the left
  rail.

**Verification:**
- Manually create, rename, delete a conversation. Refresh the page.
  State persists (create + rename survives; delete is gone).
- `localStorage['pa_last_conv_id']` visible in DevTools and matches
  current selection.
- Task Review Sidebar still opens/closes without collision with the
  left rail.

---

### Unit 2.3: Per-message "Fork from here" action

**Goal:** Each assistant message card exposes a "Fork from here"
affordance that creates a new conversation branched from the
parent's current state. Success auto-switches to the fork; failure
surfaces as a card error.

**Requirements:** R10, R11, R13

**Dependencies:** Unit 2.1, Unit 2.2

**Files:**
- Modify: `pa-web-ui/static/js/chat.js` — add `⋯` menu to assistant
  message cards; menu item "Fork from here" ([j] hint per R13);
  click handler calls backend and switches to new conv.
- Modify: `pa-web-ui/static/css/styles.css` — menu styling.
- Modify: `pa-web-ui/static/js/conversation_rail.js` — on fork
  success, add the new conversation to the Active list with a
  "Fork of <parent>" visual indicator; `↳` prefix or similar.
- Modify: `pa-web-ui/tests/test_conversations_api.py` — add
  fork-specific scenarios (parent streaming, parent soft-deleted,
  parent doesn't exist, concurrent fork requests).

**Approach:**
1. **Menu affordance.** On every rendered assistant thread-card
   (inside `renderHistoryThread()` and the live stream handler), add
   a `⋯` button that toggles a dropdown with "Fork from here".
   Keyboard: `j` with the card focused (per R13). Hover-reveal on
   desktop; always-visible on mobile.

2. **Click handler.**
   - Grab the assistant message's `request_id` from the thread card.
   - POST `/api/conversations/<current-conv>/fork` with `{
     parent_request_id: <request_id>, label: <auto or prompt> }`.
   - On 201: call `window.conversationRail.addAndSwitch(response.id)`
     which inserts the new conv into the rail and switches.
   - On 409 (parent streaming): show an in-card error "Can't fork
     while the conversation is still streaming — wait for the turn
     to complete." Auto-retry after `done` event? No — single retry
     risk is real (duplicate forks). Surface the error and let the
     user retry manually.
   - On 500: generic error card with a retry button.

3. **Fork tree display.** In the rail's Active list, a fork shows
   as `↳ <label>` under its parent IF the parent is also in the
   visible list. If the parent is in trash or outside the current
   page's limit, the fork renders flat with no prefix. Simple
   1-level indentation only — Phase 2 is not a tree-view feature.

4. **parent_request_id semantics.** In Phase 2's storage model, the
   fork's `parent_conversation_id` is persisted, and the
   `parent_request_id` is preserved as metadata inside
   `conversation_meta.metadata` JSON blob (`{forked_at_request_id:
   "..."}`). Letta's fork API is conversation-level, not
   message-level, so the `parent_request_id` is purely UX
   bookkeeping — it shows up as "Forked after: <message>" in the
   new conv's banner.

**Patterns to follow:**
- Phase 1's chat.js `⋯` menu hookup (if any exists; otherwise fresh).
- Existing collapsible-region pattern (`ensureThinkingAccordion`).

**Test scenarios:**
- Happy path: fork button click → new conv appears in rail, page
  switches to it, banner reads "Forked from <parent-label> after
  <message>".
- Turn-lock: try to fork while the parent is mid-stream → 409 +
  inline error.
- Keyboard: `j` on focused card triggers fork.
- Edge case: fork a fork (multi-level) → both parent links tracked.
- Error path: Letta returns 500 on fork → error card; local
  conversation_meta is NOT created.
- Integration: fork → switch → send message in fork → verify the
  parent conversation still has its original thread intact.

**Verification:**
- Fork a real MC conversation; inspect both on the Letta server and
  in `pa_web.conversation_meta`. Parent link correct.
- Send a divergent message in the fork; parent unchanged.

---

### Unit 2.4: Per-conversation history rehydration + device_id rename

**Goal:** `loadConversationHistory()` correctly rehydrates per
conversation. Frontend `pa_chat_session_id` localStorage key is
renamed to `pa_chat_device_id` semantically. Per-device last-used
conv selection via `localStorage['pa_last_conv_id']`. No URL state.

**Requirements:** R9, R18 (amended), R19

**Dependencies:** Unit 2.2

**Files:**
- Modify: `pa-web-ui/static/js/chat.js`:
  - Rename `pa_chat_session_id` localStorage key to
    `pa_chat_device_id` (one-shot migration; preserves UUID value).
  - `loadConversationHistory(conversation_id)` takes a conv_id;
    when null/undefined, omits the filter (back-compat with flag-OFF).
  - `switchConversation` writes `pa_last_conv_id` on every switch.
  - AbortController-based cancellation of the previous `/stream`
    fetch reader.
- Modify: `pa-web-ui/app.py` — `GET /api/conversations/<session_id>`
  already accepts `?conversation_id=` (Unit 2.1); this unit consumes it.
- Modify: `pa-web-ui/tests/test_stream_direct.py` — add test for
  per-conv history filter.

**Approach:**

1. **device_id rename (one-shot, idempotent).**
   ```js
   const OLD_KEY = 'pa_chat_session_id';
   const NEW_KEY = 'pa_chat_device_id';
   let deviceId = localStorage.getItem(NEW_KEY);
   if (!deviceId) {
     deviceId = localStorage.getItem(OLD_KEY) || crypto.randomUUID();
     localStorage.setItem(NEW_KEY, deviceId);
     localStorage.removeItem(OLD_KEY);
   }
   ```
   Keeps existing users' IDs stable across the rename.

2. **loadConversationHistory parameterized.**
   ```js
   async loadConversationHistory(conv_id = this.conversationId) {
     const url = conv_id
       ? `/api/conversations/${this.sessionId}?conversation_id=${conv_id}`
       : `/api/conversations/${this.sessionId}`;
     // ... existing fetch + render logic
   }
   ```

3. **switchConversation (no URL state).**
   ```js
   async switchConversation(newConvId) {
     // 1. Abort any active EventSource/fetch reader for old conv.
     if (this._currentStreamAbort) {
       this._currentStreamAbort.abort();
       this._currentStreamAbort = null;
     }
     // 2. Reset state.
     this.conversationId = newConvId;
     this.lastSeqId = null;
     this._resetUIForConversationSwitch();
     // 3. Persist per-device last-used.
     localStorage.setItem('pa_last_conv_id', newConvId);
     // 4. Load durable history.
     await this.loadConversationHistory(newConvId);
     // 5. If the new conv is streaming, resume live.
     const status = await fetch(
       `/api/subprocess/status?conv=${newConvId}`
     ).then(r => r.json());
     if (status.handles?.[0]?.in_flight) {
       this._resumeStream(newConvId, status.handles[0].current_seq_id);
     }
   }
   ```
   `streamResponse()` stores its `AbortController` on
   `this._currentStreamAbort` so switchConversation cancels cleanly.

4. **Initial load order (DOMContentLoaded):**
   a. ChatUI constructor reads `pa_chat_device_id` (with one-shot
      migration from `pa_chat_session_id`).
   b. ConversationRail.init() fetches `/api/conversations`.
   c. Rail resolves selection: read `pa_last_conv_id` from
      localStorage; if valid in the fetched list, use it; otherwise
      fall back to MRU from the Letta list.
   d. Rail calls `switchConversation(selected_conv_id)` ONCE.
   This avoids a double history fetch.

**Patterns to follow:**
- `fetch` + `AbortController` pattern — standard browser API, no
  library dependency.

**Test scenarios:**
- Happy path: fresh browser → device_id minted; no
  `pa_last_conv_id`; rail picks MRU from Letta list.
- Migration: existing `pa_chat_session_id` → `pa_chat_device_id`
  (same UUID value); old key removed.
- Happy path: `pa_last_conv_id` points at valid conv → selected on
  load.
- Edge case: `pa_last_conv_id` points at deleted/nonexistent conv
  → fall back to MRU, console warning.
- Integration: switch conv-A → send message → switch to conv-B →
  switch back to conv-A → message is still there (from
  pa_web.conversations history).
- AbortController: switch mid-stream → old EventSource is aborted;
  no stale `onmessage` fires on the new conv.

**Verification:**
- DevTools: localStorage shows `pa_chat_device_id` (not
  `pa_chat_session_id`) and `pa_last_conv_id` reflects current
  selection.
- Network tab: on switch, the old `/stream` connection closes; the
  new one subscribes if in_flight.
- History for three distinct convs rendered correctly on refresh.

---

### Unit 2.5: LLM auto-naming on first turn

**Goal:** Conversations get useful LLM-generated titles after their
first turn completes. Ships in Phase 2 as a first-class feature
(not a dangling follow-up). User manual rename wins forever via
`user_renamed` gate.

**Requirements:** R-auto-name (new in Phase 2)

**Dependencies:** Unit 2.1 (schema + conversation_meta row exists),
Phase 1 translation layer in `_stream_direct_generator`.

**Files:**
- Modify: `pa-web-ui/app.py`:
  - In `_stream_direct_generator`: after the terminal `result`
    event is translated but BEFORE the `done` event is yielded,
    check auto-name preconditions and fire the litellm call inline.
  - Add `_autoname_conversation(conv_id, first_user_message)` helper
    that calls litellm and updates `conversation_meta` race-safely.
  - Emit a new `{"type": "conversation_label_updated"}` event on
    success.
- Modify: `pa-web-ui/static/js/chat.js`:
  - Add event handler for `conversation_label_updated` that calls
    `window.conversationRail.updateLabel(conv_id, new_label)`.
- Modify: `docker-compose.yml` — add
  `PA_WEB_UI_AUTONAME_ENABLED=${PA_WEB_UI_AUTONAME_ENABLED:-true}`
  env var.
- Create: `pa-web-ui/tests/test_autoname.py` — unit tests with
  litellm mocked.

**Approach:**

1. **Trigger point.** In `_stream_direct_generator`, after the
   `result` event is translated to `done`:
   ```python
   if event_type == "result":
       # Existing: map to done event.
       done_event = {"type": "done", "result": ..., ...}
       # NEW: auto-name check before yielding done.
       if PA_WEB_UI_AUTONAME_ENABLED and conv_id and first_user_message:
           new_label = _autoname_conversation(conv_id, first_user_message)
           if new_label:
               yield f"data: {json.dumps({'type':'conversation_label_updated',
                                          'conv_id': conv_id,
                                          'label': new_label})}\n\n"
       yield f"data: {json.dumps(done_event)}\n\n"
   ```
   `first_user_message` is captured by the route handler before
   calling `send()` and carried into the generator as a closure.

2. **`_autoname_conversation` helper (psycopg2-parameterized).**
   ```python
   def _autoname_conversation(conv_id: str, first_user_message: str) -> Optional[str]:
       # Race-safe precondition check.
       with get_db_connection() as conn, conn.cursor() as cur:
           cur.execute("""
             SELECT label, user_renamed FROM pa_web.conversation_meta
              WHERE conversation_id = %s
           """, (conv_id,))
           row = cur.fetchone()
           if not row:
               return None
           label, user_renamed = row
           if user_renamed:
               return None
           if not re.match(r'^New conversation \d{4}-\d{2}-\d{2}', label or ''):
               return None  # label is not the default pattern — treat as user-set
       # Call litellm (3s timeout; swallow failures silently).
       try:
           resp = httpx.post(
               f"{LITELLM_URL}/v1/chat/completions",
               json={
                   "model": "gpt-4.1-mini",
                   "messages": [{
                       "role": "user",
                       "content": f"Summarize this in 3-6 words as a "
                                  f"conversation title (no quotes, no "
                                  f"period): {first_user_message[:500]}"
                   }],
                   "max_tokens": 20,
                   "temperature": 0.3,
               },
               timeout=3.0,
           )
           resp.raise_for_status()
           new_label = resp.json()["choices"][0]["message"]["content"].strip()
           new_label = new_label.strip('"\'').strip()[:80]  # cap + clean
       except Exception as exc:
           logger.warning("autoname_litellm_failed", conv_id=conv_id, error=str(exc))
           return None
       # Race-safe UPDATE: user_renamed predicate guards against a
       # user rename happening between our SELECT and UPDATE.
       with get_db_connection() as conn, conn.cursor() as cur:
           cur.execute("""
             UPDATE pa_web.conversation_meta
                SET label = %s, renamed_at = %s
              WHERE conversation_id = %s AND user_renamed = FALSE
           """, (new_label, datetime.utcnow(), conv_id))
           conn.commit()
           if cur.rowcount == 0:
               return None  # lost the race; user wins
       return new_label
   ```

3. **Frontend handler in chat.js (alongside existing event
   translations):**
   ```js
   } else if (event.type === 'conversation_label_updated') {
     if (window.conversationRail) {
       window.conversationRail.updateLabel(event.conv_id, event.label);
     }
     continue;  // don't render in the chat pane
   }
   ```

4. **Feature flag.** `PA_WEB_UI_AUTONAME_ENABLED` (default `true`).
   If false, skip the litellm call entirely. No user-visible
   difference beyond titles staying as timestamps.

5. **Cost accounting.** Each call: ~200 input + ~20 output tokens
   via gpt-4.1-mini through the existing litellm proxy. At
   ~$0.00004/call and 50 new conversations/month, ~$0.002/month
   incremental. Cost is visible in the existing litellm spend logs.

**Patterns to follow:**
- Phase 1's `_translate_letta_code_event` and
  `_stream_direct_generator` — insert the auto-name path in the
  same flow, same commit style.
- Existing psycopg2 parameterized-write pattern.
- httpx timeout pattern from existing app.py.

**Test scenarios:**
- Happy path: new conv with timestamp label + user_renamed=FALSE →
  fires litellm mock → label updates → SSE event emitted → chat.js
  calls updateLabel.
- Flag off: PA_WEB_UI_AUTONAME_ENABLED=false → no litellm call, no
  SSE event, label stays as timestamp.
- User rename wins race: concurrent PATCH sets user_renamed=TRUE
  between SELECT and UPDATE → UPDATE WHERE user_renamed=FALSE
  touches 0 rows; no SSE event emitted.
- User rename wins pre-check: user_renamed=TRUE when the auto-name
  fires → SELECT returns user_renamed=True → skip; no litellm call.
- Custom label at create: POST /api/conversations with a user-
  supplied label sets `user_renamed=TRUE`; first-turn auto-name
  skips.
- litellm timeout: mock returns after 5s → our 3s timeout fires →
  warning logged, no label update, done event still emits normally.
- litellm 500: mock raises → warning logged, no label update, done
  event still emits normally.
- Malformed response: mock returns {choices: []} → warning logged,
  no label update.
- Second turn on already-renamed conv: label no longer matches
  timestamp pattern → skip (belt-and-suspenders even without
  user_renamed).

**Verification:**
- Manually: create a new conversation, send a first message about a
  specific topic, observe the rail label flip to an LLM-generated
  title within ~1s after the response completes.
- Rename manually via the rail; send another message; verify label
  doesn't change.
- Toggle flag off, restart, create a conv, send a message; verify
  label stays as the timestamp.
- Inspect litellm spend logs: per-rename cost ≈ $0.00004.

---

## System-Wide Impact

- **DB schema:** one new table (`conversation_meta`), four column
  additions (`conversation_id TEXT`), one column rename
  (`response_feedback.conversation_id INTEGER → local_conversation_pk`
  with coordinated code update). Forward-only. Nullable `conversation_id`
  columns backfilled to the real UUID behind MC's `default` alias.
  Flag-OFF rollback leaves schema in place but the UI hidden.
- **Letta server load:** additional `GET /v1/conversations/` on page
  load + `POST /v1/conversations/{id}/fork/` per fork + `DELETE
  /v1/conversations/{id}/` per hard-delete. Self-hosted 0.16.7 is
  single-instance and single-user; load increase is negligible.
- **litellm load (new in Phase 2 Unit 2.5):** one completion call per
  new conversation's first turn via the existing litellm proxy
  (gpt-4.1-mini, ~200 input + ~20 output tokens, ~$0.00004 per call).
  Fire-and-forget-on-failure — a down litellm doesn't block chat.
- **Subprocess pool load:** per-conversation subprocesses replace
  the shared `default` pool. With max_concurrent=5 (Phase 1
  default), users with >5 active conversations trigger LRU
  eviction. Cold-start for an evicted conv is ~10s on next activity.
  Consider raising `PA_WEB_UI_MAX_SUBPROCESSES` to 8–10 if the
  ceiling bites.
- **Frontend load:** one new JS file (~5KB) + CSS additions (~2KB).
  No external dependencies. Service worker deferred to Phase 4.
- **Task Review Sidebar:** untouched. The right overlay and left
  rail coexist by distinct z-index + non-overlapping fixed positions.
- **Security posture:** All new routes gated by Phase 1's
  `ingress_guard` (CSRF + Origin + Host). R30 env scrub on subprocesses
  unchanged. Phase 2 adds four guardrails documented in
  `docs/security/pa-web-ui-threat-model.md` (to be updated as part of
  Unit 2.1):
  - **Conversation list is SHARED across the user's Tailnet devices.**
    `session_id` on `conversation_meta` records the creating device
    for attribution/debug only, NOT for access control. Any Tailnet
    device can read, rename, delete, or fork any conversation — this
    is intentional for single-user multi-device UX and consistent
    with the Phase 1 threat model.
  - **Conversation labels are rendered with `textContent`,
    not `innerHTML`.** Rail entries, "Forked from <label>" banners,
    and any other consumer-facing label surface use DOM
    `createTextNode` / `textContent` to ensure HTML metacharacters
    in labels are treated as text. Server-side cap: label ≤ 200 chars
    (enforced in POST/PATCH handlers).
  - **Conversation IDs are treated as non-secret identifiers.** Letta
    UUIDs are not in URLs (Phase 2 dropped deep-links); they flow
    through JSON bodies and SSE events protected by the ingress guard.
    Within the Tailnet, all conversations are mutually visible by
    design. Outside the Tailnet, ingress_guard blocks access regardless
    of whether an attacker knows a conv_id.
  - **All new SQL writes use psycopg2 `%s` parameterization — no
    string formatting.** Plan explicitly requires this for every
    new route in Unit 2.1; existing `save_conversation_message` and
    friends already follow this convention.
- **LettaBot Telegram:** unaffected. Telegram continues to use
  LettaBot's own `default` conversation. Phase 2's web-UI
  conversations diverge from Telegram's thread — the origin-doc
  intent of "separate surfaces over time" is now realized.

## Risk Analysis & Mitigation

- **Risk: Schema migration breaks on re-run.** `ALTER TABLE RENAME
  COLUMN` has no `IF EXISTS` form, and `ensure_pa_web_schema()` runs
  on every boot. Mitigation: Unit 2.1 wraps the RENAME in a
  `information_schema.columns` type-check `DO $$ ... END $$` guard
  so the second boot is a no-op. All other new DDL uses `IF NOT
  EXISTS` idempotency.
- **Risk: `response_feedback.conversation_id` rename silently breaks
  `/api/feedback`.** The column is actively written by `save_response_feedback`
  + the `/api/feedback` route. Mitigation: Unit 2.1 does RENAME + code
  update in the same commit; pytest exercises the endpoint under the
  new column name.
- **Risk: Backfill UPDATE exceeds healthcheck window.** Mitigation:
  backfill runs in a background thread after Flask starts serving,
  not on the synchronous startup path. Batched at 1000 rows per
  commit. Phase-2 mutation routes return 503 until backfill completes.
- **Risk: Fork API response shape differs from plan assumptions.**
  Mitigation: Unit 2.0 probes live before Unit 2.1 commits; plan has
  three pre-framed branches (A/B/C) for block-copy semantics.
- **Risk: Letta `order_by=last_message_at` rejects on 0.16.7.**
  Mitigation: Unit 2.0 smokes it; fallback to `order_by=created_at`
  with a warning log if it fails.
- **Risk: User creates >5 active conversations; LRU eviction causes
  cold-starts.** Mitigation: document in operational notes.
  `PA_WEB_UI_MAX_SUBPROCESSES=8` or `=10` as a user-tunable if the
  ceiling bites in practice.
- **Risk: Fork UI auto-switch surprises the user.** Mitigation:
  5s undo toast on auto-switch; part of Unit 2.3 spec (not deferred).
- **Risk: Concurrent forks from two devices on the same parent.**
  Mitigation: `handle.forking` flag + per-handle state_lock prevent
  the parent from flipping in_flight mid-fork. Two genuinely
  concurrent forks both succeed and create two children — acceptable
  duplication the user can delete one of.
- **Risk: Auto-name fires concurrent with user manual rename.**
  Mitigation: `UPDATE ... WHERE user_renamed=FALSE` predicate; if
  the user renamed between the auto-name's SELECT and UPDATE, the
  UPDATE touches 0 rows and no SSE event fires. User rename wins.
- **Risk: Auto-name adds user-visible latency.** Mitigation: the
  litellm call fires AFTER the `result` event is translated but
  BEFORE `done` — so the assistant reply is already complete on
  screen. The extra ~1s shifts only the "done" indicator, not the
  reply. 3s timeout on the litellm call caps the worst case.
- **Risk: litellm outage fails auto-name silently.** Mitigation:
  try/except around the httpx call; on any failure, log a warning,
  skip the SSE event, let `done` fire normally. Label stays as
  timestamp — user can rename manually. No user-visible error.
- **Risk: 10s undo window is too short / too long.** Mitigation:
  starts at 10s; if user feedback surfaces friction, bump to 15s
  via a single constant. Tab-close-before-expiry leaves the conv
  intact — acceptable for a single-user PA with nightly backups.
- **Risk: Hard-delete of an actively-streaming conversation
  orphans the SSE client.** Mitigation: DELETE route pushes
  `{type: "conversation_deleted"}` to every attached subscriber
  BEFORE `invalidate()` kills the handle. chat.js handles the
  event by redirecting to MRU.

## Phased Delivery

### Phase 2 (this plan)
Units 2.0 through 2.5. Ships: Letta probe references (2.0),
first-class conversations + hard-delete with undo toast + response_feedback
rename (2.1), switcher UI with left rail (2.2), per-message fork
(2.3), per-device last-used history rehydration (2.4), LLM
auto-naming (2.5). Rollback: `PA_WEB_UI_PHASE_2_ENABLED=false`
hides UI and returns HTTP 503 on new routes.
`PA_WEB_UI_AUTONAME_ENABLED=false` separately kills auto-naming if
needed. Schema stays forward; backfilled `conversation_id=<default_uuid>`
is valid regardless of flag state.

No Phase 2.5 follow-up. The auto-naming that originally would have
lived there ships in Phase 2 core as Unit 2.5; the soft-delete purge
that also would have lived there is no longer needed (hard-delete +
undo toast replaces it).

### Phase 3 (future plan)
`/btw` ephemeral BtwPane. Depends on Unit 2.0 fork probe knowledge;
otherwise independent.

### Phase 4 (future plan)
PWA manifest, service worker, mobile polish, threat-model addendum.

## Documentation / Operational Notes

- **Docs to write / update:**
  - `docs/reference/letta-conversations-fork.md` — Unit 2.0 deliverable.
  - `docs/reference/letta-default-alias-resolution.md` — Unit 2.0
    deliverable.
  - Update `docs/security/pa-web-ui-threat-model.md` — add new routes,
    the shared-list-across-devices invariant, textContent rendering
    rule, and psycopg2 parameterization convention to the ingress-
    guard scope documentation.
  - Update `pa-web-ui/README.md` — document the left-rail UX,
    per-device `pa_last_conv_id` convention, conversation_meta schema,
    hard-delete semantics, auto-naming behavior.
  - Update `CLAUDE.md` — note that pa-web-ui has per-conversation
    subprocesses and a first-class conversation switcher with LLM
    auto-naming.
  - Update `MEMORY.md` — record the conversation_meta schema and
    the `user_renamed` gate so future debugging sessions know where
    to look.
- **Operational notes:**
  - `PA_WEB_UI_PHASE_2_ENABLED` — single rollback for UI + new
    routes. Schema stays forward.
  - `PA_WEB_UI_AUTONAME_ENABLED` (default true) — separate killswitch
    for auto-naming if litellm misbehaves.
  - `PA_WEB_UI_MAX_SUBPROCESSES` (Phase 1 env var, default 5) —
    raise to 8–10 if >5 concurrent convs is a real workflow.
  - Fork API response shape in `docs/reference/letta-conversations-fork.md`
    is the source of truth.
  - Auto-naming cost visible in existing litellm spend logs; budget
    at ~$0.002/month at 50 new convs/month.
- **Rollout sequence:**
  1. Run Unit 2.0 probes. Commit reference docs. Confirm fork
     Branch A/B/C with user before opening Unit 2.1.
  2. Ship Unit 2.1 — schema DDL + backend routes behind the flag
     (flag OFF). Verify schema migration + backfill on the live DB.
  3. Ship Units 2.2–2.5 — UI + frontend integration + auto-naming,
     still flag OFF.
  4. Enable flag in a quiet window. Create a test conversation, send
     a message, verify auto-naming fires (or explicitly disable it
     first via PA_WEB_UI_AUTONAME_ENABLED=false if you want to smoke
     each piece independently). Fork a message; verify both appear
     in the rail.
  5. Monitor `/api/subprocess/status`, litellm spend logs, and the
     crash log directory for 7 days.
  6. After 7 days of flag-on stability, retire the flag in a small
     cleanup commit. Keep PA_WEB_UI_AUTONAME_ENABLED as a permanent
     runtime toggle (don't remove — useful killswitch).

## Sources & References

- **Origin document:** `docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md`
- **Upstream plan:** `docs/plans/2026-04-20-001-feat-pa-web-ui-letta-code-migration-plan.md`
- **Related code (target):**
  - `pa-web-ui/app.py` — schema bootstrap, existing conversation
    routes, CSRF + ingress_guard wiring
  - `pa-web-ui/static/js/chat.js` — conversation switch wiring,
    history rehydration, URL state
  - `pa-web-ui/static/js/sidebar.js` — pattern template for the
    left rail
  - `pa-web-ui/templates/index.html`, `static/css/styles.css` —
    layout
  - `pa-web-ui/subprocess_pool.py` — already multi-conv-ready
- **Related code (reference):**
  - `pa-routing-handler/src/pa_routing/services/conversation_service.py`
    — only existing `letta.conversations.create` consumer
  - `letta/granola_mcp_to_archival.py:203–212` — another `POST
    /v1/conversations/` precedent
- **Related plans/docs:**
  - `memory/project_letta_upgrade_migration.md` — schema-drift
    warning
  - `memory/feedback_block_ids_replace.md` — PATCH-replaces pattern
    (not currently used but retained as a Letta API gotcha)
  - `memory/MEMORY.md` — trailing-slash, default-limit
- **Upstream issues tracked:**
  - No Phase 2-specific upstream blockers. Fork API verified working
    at HTTP 200 in the origin doc.
