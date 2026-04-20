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

Phase 2 also introduces the project's first URL-state convention
(`?conv=conv-abc…` deep-links), the first multi-pane layout (left
rail + main + right Task Review Sidebar), and the first backfill
migration on `pa_web` tables.

Covers requirements **R9–R11** and **R18** from the origin doc.

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

### Multi-conversation + persistent fork UX (R9–R11, R18)
- **R9.** Conversations are first-class; user can create, switch,
  rename, soft-delete (30-day trash).
- **R10.** "Fork from here" per-message action →
  `POST /v1/conversations/{id}/fork?agent_id=...` (response shape
  verified empirically in Unit 2.1).
- **R11.** No archive tier, no full-text search, no pinned-primary
  concept in v1.
- **R18.** Cold PWA open → most-recently-active conversation for MC
  (via Letta `conversations.list` ordered by `last_message_at`).

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
- Conversation CRUD (create, rename, soft-delete with 30-day trash)
- Conversation switcher UI (left rail + mobile drawer)
- Per-message "Fork from here" action
- Per-conversation subprocess isolation (leveraging Phase 1's pool)
- URL deep-link convention (`?conv=<uuid>`)
- Database schema extension on 4 `pa_web` tables
- Backfill: existing conversations get assigned a "main" conv per
  session_id

**Out of scope:**
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
  Separate from `pa_web.conversations` (which stores per-message
  records) to avoid overloading. Columns: `conversation_id TEXT PK`,
  `agent_id TEXT`, `session_id TEXT`, `label TEXT`, `parent_conversation_id
  TEXT NULL`, `created_at`, `renamed_at NULL`, `deleted_at NULL`
  (soft-delete + 30-day purge). `session_id` links conversations to
  devices so phone/desktop can share a conversation list.
- **Source of truth for conversation LIST is Letta server.**
  `GET /v1/conversations/?agent_id=MC&order_by=last_message_at&limit=100`
  is authoritative. `pa_web.conversation_meta` caches local metadata
  (label, parent link, soft-delete flag) that Letta doesn't track.
  Listing endpoint is a JOIN: hit Letta for the canonical list, then
  enrich with local metadata.
- **Source of truth for conversation CONTENT stays in `pa_web.conversations`
  for Phase 2.** Display rehydration reads `pa_web.conversations`
  filtered by `conversation_id`. Migrating to Letta's messages API is
  Phase 3 or later — out of Phase 2 scope because the event shapes
  would require another translation layer.
- **URL convention: query param `?conv=<uuid>` + `history.replaceState`.**
  Query param is standard SPA, survives refresh, doesn't conflict
  with the hash (already empty). `replaceState` on switcher click
  (no nav stack pollution); `popstate` handler reacts to browser
  back/forward. Deep-links are shareable across Tailscale devices.
- **Soft-delete: `deleted_at` column + daily cron purge.** UI hides
  deleted conversations by default but shows them in a "Trash" tab.
  Purge cron (Phase 2.5 or manual script) removes rows with
  `deleted_at < now() - interval '30 days'`. Letta server's own
  conversation isn't deleted at soft-delete time — only at purge
  (so un-delete within 30 days restores everything). Purge calls
  `DELETE /v1/conversations/{id}/` on the Letta server in addition
  to local DDL cleanup.
- **Fork UI: auto-switch to the new fork.** After `POST
  /api/conversations/:id/fork` succeeds, `pushState` to the new
  `conv=` URL and reload history. User stays in context of "I wanted
  to explore this branch" — forking and immediately staying on the
  parent would be surprising.
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
- **Conversation label: user-provided at create time OR auto-generated
  "New conversation <local-time>".** Rename endpoint lets the user
  fix it. No LLM-based auto-naming in Phase 2 (keeps the switcher
  free of backend round-trips for a cosmetic concern).
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
- **URL convention?** Resolved: query param `?conv=<uuid>` with
  `replaceState`. Deep-linkable, refresh-safe, no hash collision.
- **Soft-delete retention?** Resolved: 30-day via `deleted_at`
  timestamp + daily purge cron. Purge propagates to Letta server
  (DELETE /v1/conversations/{id}/).
- **Fork mid-stream?** Resolved: HTTP 409 if parent handle in_flight.
- **Conversation label auto-naming?** Resolved: `"New conversation
  <timestamp>"` default; user can rename. No LLM call.
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
- **[Affects Phase 2.5][Technical]** Daily soft-delete purge cron.
  Options: pa-web-ui at startup checks once per day; scheduler-service
  job; systemd timer on the host. Default: pa-web-ui self-schedules
  (pure Python, no new service). Deferred to a Phase 2.5 follow-up
  commit once the core switcher is stable.
- **[Affects Phase 2 observability][Technical]** `/api/subprocess/status`
  currently reports handles across all conversations. With per-conv
  subprocesses, that list grows. Unit 1.6's endpoint already handles
  this correctly via `list_handles()`, but UX may want to group by
  "active" vs "idle".

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
  session_id TEXT                 -- creating device
  label TEXT
  parent_conversation_id TEXT NULL
  created_at TIMESTAMP
  renamed_at TIMESTAMP NULL
  deleted_at TIMESTAMP NULL
  metadata JSONB                  -- reserved
```

### Request flow — conversation switch

```
user clicks sidebar entry for conv-B
  → chat.js: conversationRail.switchTo("conv-B")
  → chat.js: this.conversationId = "conv-B"; this.lastSeqId = null
  → chat.js: history.replaceState({}, "", "?conv=conv-B")
  → chat.js: loadConversationHistory("conv-B")
     → GET /api/conversations/<session_id>?conversation_id=conv-B
     → renders thread-cards from pa_web.conversations rows
  → next message send includes conversation_id=conv-B
     → POST /stream routes to SubprocessRegistry.ensure(MC, "conv-B")
     → pool spawns a new subprocess if conv-B is cold; else reuses
```

### Request flow — fork from assistant message

```
user clicks "…" → "Fork from here" on message M in conv-A
  → chat.js: fetch POST /api/conversations/conv-A/fork
     with body {"parent_request_id": M.request_id, "label": optional}
  → backend: check SubprocessRegistry handle for conv-A:
     - if handle.in_flight: return 409 {error: "parent_conversation_streaming"}
  → backend: POST http://letta:8283/v1/conversations/conv-A/fork/?agent_id=MC
     - response: {id: "conv-C", label: "...", parent_conversation_id: "conv-A"}
  → backend: INSERT INTO pa_web.conversation_meta
       (conversation_id="conv-C", parent_conversation_id="conv-A",
        agent_id=MC, session_id=<caller>, label=<from body or autogen>,
        created_at=now())
  → backend: return 201 {conversation_id: "conv-C", label: "...", parent_conversation_id: "conv-A"}
  → chat.js: conversationRail.add(new conv); auto-switch to conv-C
```

### Layout

```
┌─ page-layout (flex) ──────────────────────────────────────────┐
│ ┌─ conv-rail (aside, fixed-left, z=99) ─┐  ┌─ container ────┐ │
│ │ Conversations                         │  │ chat main pane │ │
│ │ ▸ Active                              │  │                │ │
│ │   • Fork #3                           │  │                │ │
│ │   • Grocery planning                  │  │                │ │
│ │   • default                           │  │                │ │
│ │ ▸ Trash (7)                           │  │                │ │
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
     `pa_web.conversation_meta` → filter out `deleted_at IS NOT NULL`
     unless `?include_deleted=true`. Returns `{conversations: [{id,
     label, agent_id, last_message_at, parent_conversation_id,
     created_at, deleted_at}]}`.
   - `POST /api/conversations`: body `{label?: string}`. Calls
     `POST /v1/conversations/` on Letta with `agent_id=MC, label=...`.
     Inserts `conversation_meta` row. Returns the created conv.
   - `PATCH /api/conversations/<id>`: body `{label?: string,
     deleted_at?: "clear"|<ISO-8601>}`. Updates `conversation_meta`
     locally; does NOT call Letta for rename (Letta server doesn't
     expose conversation label in the way we care about; local is
     SoT for labels).
   - `DELETE /api/conversations/<id>`: atomic sequence:
     1. UPDATE `conversation_meta` SET `deleted_at = now()`.
     2. If a live handle exists in the subprocess_registry for this
        conv_id, walk `handle.subscribers` and push
        `{"type": "conversation_deleted", "conv_id": <id>}` into each
        subscriber's queue BEFORE calling `invalidate()`. This gives
        attached SSE clients a clean terminal event; chat.js handles
        it by redirecting to MRU. Without this step, subscribers
        time out silently and chat.js may auto-retry into a fresh
        subprocess on a deleted conv.
     3. `subprocess_registry.invalidate(conv_id)` — kills the handle
        + subprocess.
     4. (`/stream` dispatch in Phase 1 must also check
        `conversation_meta.deleted_at` on each new request; if set,
        return HTTP 410 Gone `{"error": "conversation_deleted"}`.
        Prevents reconnect races.)
     Does NOT call Letta (soft-delete — Letta copy survives until
     Phase 2.5 purge).
   - `POST /api/conversations/<id>/fork`: body `{label?: string,
     parent_request_id?: string}`. Flow:
     1. Check `conversation_meta.deleted_at` on parent — if set,
        return HTTP 410 Gone.
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
  with local meta; `deleted_at` filter works.
- Happy path: `POST /api/conversations` creates conv on Letta AND
  inserts local meta; returns `{id, label, agent_id, created_at}`.
- Edge case: `POST /api/conversations` — Letta returns 500; local
  meta is NOT inserted (no ghost rows).
- Happy path: `PATCH` renames, `DELETE` soft-deletes, subsequent
  `GET` filters appropriately.
- Happy path: `POST /api/conversations/<id>/fork` creates a fork
  with parent link; subsequent `GET /api/conversations` shows both.
- Error path: `POST /api/conversations/<id>/fork` when parent is
  streaming → HTTP 409 `{error: "parent_conversation_streaming"}`.
- Flag OFF: every new route returns HTTP 404.
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

### Unit 2.2: Conversation switcher UI + left rail

**Goal:** User-facing conversation list rail, with create / rename /
soft-delete actions and a Trash view. Mirrors the right Task Review
sidebar's visual vocabulary. URL deep-link support (`?conv=<uuid>`).
Feature-flagged.

**Requirements:** R9, R11, R18

**Dependencies:** Unit 2.1

**Files:**
- Modify: `pa-web-ui/templates/index.html` — add `<aside
  id="conversation-rail" class="conversation-rail">` sibling BEFORE
  `.container`; add a toggle button (`#conversation-rail-toggle`).
- Modify: `pa-web-ui/static/css/styles.css` — `.conversation-rail`
  styles mirroring `.task-sidebar` pattern with `left: -380px` and
  z-index=99 (right sidebar stays at 100).
- Create: `pa-web-ui/static/js/conversation_rail.js` — standalone
  class `ConversationRail` handling list fetch, render, switch,
  create, rename, soft-delete, restore, URL-state sync.
- Modify: `pa-web-ui/static/js/chat.js` — initialize
  `window.conversationRail` on DOMContentLoaded; on conv switch,
  update `this.conversationId`, clear `lastSeqId`, refetch history,
  replaceState.
- Modify: `pa-web-ui/templates/index.html` — add
  `<script src="/static/js/conversation_rail.js?v=1"></script>` before
  chat.js script tag (load order matters — chat.js references
  `window.conversationRail`).

**Approach:**

1. **CSS layout.** Add `.conversation-rail` with fixed-left
   positioning, 360px wide, `left: -380px` slide-in. Toggle button
   on the outer edge (mirror of right sidebar's toggle). Z-index 99.
   Mobile: full-width overlay above 640px, same slide-in below.

2. **Rail component.** `ConversationRail` class:
   - `init()`: fetch `/api/conversations`, parse URL `?conv=<uuid>`,
     select the matching entry if present else most-recently-active
     (per R18). Bind click handlers.
   - `render(list)`: two sections — "Active" and "Trash (N)".
     Each entry shows label, last-activity timestamp, and a `⋯`
     menu for Rename / Delete / Restore / Permanently delete.
   - `switchTo(conv_id)`: updates rail highlight, calls
     `window.chatUI.switchConversation(conv_id)`, pushes URL state.
   - `create()`: prompts for label (or auto-generates), calls
     `POST /api/conversations`, re-renders, auto-switches.
   - `rename(conv_id, label)`: `PATCH /api/conversations/<id>`.
   - `softDelete(conv_id)`: `DELETE /api/conversations/<id>`;
     re-renders (entry moves to Trash tab).
   - `restore(conv_id)`: `PATCH` with `deleted_at: "clear"`.

3. **URL state.** On rail switch:
   `history.replaceState({}, '', '?conv=<uuid>')`.
   On boot: `const params = new URLSearchParams(window.location.search);
   const conv = params.get('conv');`. If present AND valid, select
   that conversation. On `popstate`: re-parse URL and switch.

4. **chat.js integration.**
   `ChatUI.switchConversation(conv_id)`:
   - `this.conversationId = conv_id`
   - `this.lastSeqId = null` (ring-buffer floor is per-conv; new conv
     has no replay state)
   - `this.loadConversationHistory(conv_id)` — pass conv_id (Unit
     2.4 wires loadConversationHistory to accept this)
   - `this._resetUIForConversationSwitch()` — clear thread cards,
     reset `threads` Map
   - NOTE: does NOT cancel any in-flight subprocess turn on the OLD
     conversation; that conv keeps streaming, user simply isn't
     watching. If they switch back before `done`, Phase-1's subscribe
     mechanism catches them up via `since=lastSeqIdAtLeave`.

5. **CSRF token scope.** All new routes continue to require CSRF
   double-submit. The existing `paCsrfHeaders()` helper handles it.

**Patterns to follow:**
- `pa-web-ui/static/js/sidebar.js` — structural template for the
  class-based sidebar.
- Existing `#task-sidebar` DOM and CSS — visual vocabulary.
- `pa-web-ui/static/js/chat.js::ensureThinkingAccordion` — collapse
  pattern if needed for Active/Trash sections.

**Test scenarios:**
- Happy path: rail renders on page load with Active and Trash
  sections; URL `?conv=<uuid>` selects correctly.
- Happy path: click an entry → conversationId updates, history
  reloads, URL updates.
- Happy path: Create → prompt → new conv appears, auto-switches.
- Happy path: Rename → label updates inline; refresh persists.
- Happy path: Soft-delete → moves to Trash; restore moves back.
- Edge case: deep-link to a soft-deleted conv → select the
  conv and show a banner "This conversation is in trash — restore?".
- Edge case: deep-link to a non-existent conv → fall back to MRU
  conv, log a console warning.
- Error path: `/api/conversations` returns 500 → rail shows an
  error state with a retry button.
- Integration: open on phone + desktop with same session — switching
  on one device does NOT force the other to switch (per-device state).

**Verification:**
- Manually create, rename, delete, restore a conversation. Refresh
  the page. State persists.
- Deep-link URL works on both desktop and phone within the Tailnet.
- Task Review Sidebar still opens/closes without collision with the
  left rail.
- Lighthouse/performance: rail fetch is non-blocking for chat.

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
renamed to `pa_chat_device_id` semantically. URL deep-link on
refresh lands on the correct conversation with the correct history.

**Requirements:** R9, R18, R19

**Dependencies:** Unit 2.2

**Files:**
- Modify: `pa-web-ui/static/js/chat.js`:
  - Rename `pa_chat_session_id` localStorage key to
    `pa_chat_device_id`. Read-fallback: if `pa_chat_session_id`
    exists and `pa_chat_device_id` does not, migrate the value and
    delete the old key (one-shot).
  - `loadConversationHistory(conversation_id)` takes a conv_id; when
    null/undefined, omits the filter (back-compat with flag-OFF).
  - `popstate` handler parses URL and switches conv.
- Modify: `pa-web-ui/app.py` — `GET /api/conversations/<session_id>`
  already accepts `?conversation_id=` (from Unit 2.1); this unit just
  consumes it.
- Modify: `pa-web-ui/tests/test_stream_direct.py` — add test for
  per-conv history filter.

**Approach:**
1. **device_id rename.** In chat.js:
   ```
   const OLD_KEY = 'pa_chat_session_id';
   const NEW_KEY = 'pa_chat_device_id';
   let deviceId = localStorage.getItem(NEW_KEY);
   if (!deviceId) {
     deviceId = localStorage.getItem(OLD_KEY) || crypto.randomUUID();
     localStorage.setItem(NEW_KEY, deviceId);
     localStorage.removeItem(OLD_KEY);
   }
   ```
   This keeps existing users' IDs stable (they don't lose state).

2. **loadConversationHistory parameterized.**
   ```
   async loadConversationHistory(conv_id = this.conversationId) {
     const url = conv_id
       ? `/api/conversations/${this.sessionId}?conversation_id=${conv_id}`
       : `/api/conversations/${this.sessionId}`;
     // ... existing fetch + render logic
   }
   ```

3. **URL popstate.**
   ```
   window.addEventListener('popstate', () => {
     const params = new URLSearchParams(window.location.search);
     const conv = params.get('conv') || 'default';
     if (conv !== this.conversationId) {
       this.switchConversation(conv);
     }
   });
   ```

4. **Initial load order.** On DOMContentLoaded:
   a. ChatUI constructor reads device_id (migrating from
      session_id if needed)
   b. ConversationRail.init() fetches `/api/conversations` AND
      parses URL
   c. Rail resolves the "which conv to select" decision (URL param
      > MRU fallback) and calls `switchConversation()` ONCE
   d. switchConversation calls `loadConversationHistory(conv_id)`
   This sequencing avoids a double history fetch.

5. **switchConversation explicitly closes the previous SSE stream.**
   Without this, the old conversation's EventSource / fetch reader
   keeps consuming events that are then silently dropped by the
   now-wrong `conversationId` check — wasted bandwidth and potential
   UI races. Revised:
   ```
   async switchConversation(newConvId) {
     // 1. Close any in-flight SSE reader for the old conv.
     if (this._currentStreamAbort) {
       this._currentStreamAbort.abort();
       this._currentStreamAbort = null;
     }
     // 2. Reset state.
     this.conversationId = newConvId;
     this.lastSeqId = null;
     this._resetUIForConversationSwitch();
     // 3. Load durable history from pa_web.conversations.
     await this.loadConversationHistory(newConvId);
     // 4. If the new conv is currently streaming (handle.in_flight),
     //    re-subscribe with since=<current_seq_id> to pick up the
     //    live continuation. Checked via the subscribe endpoint;
     //    /api/subprocess/status exposes in_flight per conv.
     const status = await fetch(
       `/api/subprocess/status?conv=${newConvId}`).then(r => r.json());
     if (status.handles?.[0]?.in_flight) {
       this._resumeStream(newConvId, status.handles[0].current_seq_id);
     }
     // 5. URL sync (replaceState, no nav stack pollution).
     history.replaceState({}, '', `?conv=${newConvId}`);
   }
   ```
   `streamResponse()` stores its `AbortController` on
   `this._currentStreamAbort` so switchConversation can cancel cleanly.

**Patterns to follow:**
- Existing localStorage migration patterns (none in repo — this is
  the first; convention established here).

**Test scenarios:**
- Happy path: fresh browser → device_id minted, default conv
  selected, default history rendered.
- Migration: existing `pa_chat_session_id` → `pa_chat_device_id`
  (same value); old key removed.
- Deep-link: `?conv=<uuid>` → correct history rendered on load.
- Popstate: back button from conv-B to conv-A swaps history cleanly.
- Integration: switch conv-A → send message → switch to conv-B →
  switch back to conv-A → message is still there.

**Verification:**
- DevTools localStorage inspection shows only the new key name.
- History for three distinct convs rendered correctly on refresh.
- Browser back/forward navigates conversations without full reload.

---

## System-Wide Impact

- **DB schema:** one new table (`conversation_meta`), four column
  additions, one column rename. Forward-only. Nullable new columns
  default to `'default'` after backfill. Flag-OFF rollback leaves
  these present but inert.
- **Letta server load:** additional `GET /v1/conversations/` on page
  load + `POST /v1/conversations/{id}/fork/` per fork action.
  Self-hosted Letta 0.16.7 is single-instance; load increase is
  negligible (single user).
- **Subprocess pool load:** per-conversation subprocesses replace
  the shared `default` pool. With max_concurrent=5 (Phase 1
  default), users with >5 active conversations trigger LRU
  eviction. Cold-start for an evicted conv is ~10s on next activity
  (same as Phase 1 cold spawn). Consider raising max_concurrent or
  adding per-user configuration if this becomes painful.
- **URL space:** introduces `?conv=` as the first query param. Any
  future query-param addition should check for namespace collision.
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
    UUIDs in URL query params (`?conv=<uuid>`) rely on the Tailscale
    perimeter for confidentiality. Within the Tailnet, all conversations
    are mutually visible by design. Outside the Tailnet, ingress_guard
    blocks access regardless of whether an attacker knows a conv_id.
  - **All new SQL writes use psycopg2 `%s` parameterization — no
    string formatting.** Plan explicitly requires this for every
    new route in Unit 2.1; existing `save_conversation_message` and
    friends already follow this convention.
- **LettaBot Telegram:** unaffected. Telegram continues to use
  LettaBot's own `default` conversation. Phase 2's web-UI
  conversations diverge from Telegram's thread — the origin-doc
  intent of "separate surfaces over time" is now realized.

## Risk Analysis & Mitigation

- **Risk: Schema migration breaks Phase 1 deploys.** `ensure_pa_web_schema()`
  short-circuit bug means existing deployments skip the new DDL.
  Mitigation: Unit 2.1 removes the short-circuit; all new DDL is
  `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` idempotent. Verified
  by `test_pa_web_schema.py` against both fresh and Phase-1-era DBs.
- **Risk: Fork API response shape differs from plan assumptions.**
  Plan assumes `.id`, `.label`, `.agent_id`, optional
  `.parent_conversation_id`. Mitigation: Unit 2.1's first step is
  a live probe; plan explicitly adjusts if fields differ. Low
  severity — the probe is 1 hour of work, not a week.
- **Risk: Letta `order_by=last_message_at` rejects on 0.16.7.**
  0.16.6 → 0.16.7 upgrade had a column drift that broke this.
  Mitigation: Unit 2.1 smokes `order_by=last_message_at`; falls back
  to `order_by=created_at` with a warning log if it fails.
- **Risk: User creates >5 active conversations; LRU eviction causes
  cold-starts.** Mitigation: document in operational notes.
  Consider `PA_WEB_UI_MAX_SUBPROCESSES=8` or `=10` as a user-tunable
  if the ceiling bites.
- **Risk: Fork UI auto-switch surprises the user.** They may want
  to stay in the parent to verify, then go to the fork. Mitigation:
  add a subtle toast "Switched to fork: <label>. Click to undo."
  with a 5s window to switch back to parent. Defer to post-feedback
  iteration if UX surfaces the need.
- **Risk: URL deep-link shared between devices without Tailscale
  device auth context.** The CSRF cookie is device-scoped; a URL
  shared from phone to laptop works because both Tailnet devices
  hit the server, each with their own cookie. Mitigation: existing
  — R21 already documents Tailscale as perimeter; sharing URLs is
  a first-party, single-user action.
- **Risk: Concurrent forks from two devices on the same parent.**
  Two fork requests race; both succeed; the user ends up with two
  new convs. Mitigation: document behavior. Not a race condition
  in the harmful sense — just a duplication the user can delete
  one of. Fix in Phase 3 if reported.
- **Risk: Soft-deleted conversation's subprocess keeps running.**
  Mitigation: on `DELETE /api/conversations/<id>`,
  `subprocess_registry.invalidate(conv_id)` to kill the handle.
  Document in Unit 2.1 approach.
- **Risk: Trash purge cron deletes conversations users wanted.**
  Mitigation: 30-day window is generous; purge is opt-in-gated by a
  separate flag; Phase 2.5 follow-up rather than initial ship.
- **Risk: `pa_web.conversations.conversation_id` backfill
  overwrites data.** Mitigation: `UPDATE ... WHERE conversation_id
  IS NULL` — only nulls; idempotent.

## Phased Delivery

### Phase 2 (this plan)
Units 2.0 through 2.4. Ships: Letta probe references, first-class
conversations, switcher UI, per-message fork, deep-link. Rollback:
`PA_WEB_UI_PHASE_2_ENABLED=false` hides UI and returns HTTP 503 on new
routes. Backfilled `conversation_id=<default_uuid>` remains valid
(a real Letta UUID matching MC's `default` alias).

### Phase 2.5 (follow-up commit)
Soft-delete purge cron — 30-day retention. Pure Python self-scheduled
inside pa-web-ui; no new service. Ships only after Phase 2 stable
(same 7-day burn pattern as Phase 1).

**Purge scope is the full data footprint, not just metadata.** For
each conv_id with `conversation_meta.deleted_at < now() - interval
'30 days'`:
1. `DELETE FROM pa_web.conversations WHERE conversation_id = <id>`
2. `DELETE FROM pa_web.thread_exchanges WHERE conversation_id = <id>`
3. `DELETE FROM pa_web.routing_signals WHERE conversation_id = <id>`
4. `DELETE FROM pa_web.response_feedback WHERE conversation_id = <id>`
5. `DELETE FROM pa_web.conversation_meta WHERE conversation_id = <id>`
6. `DELETE http://letta:8283/v1/conversations/<id>/` (Letta server copy)
All six in a single transaction; log the row counts deleted.
Operational caveat: nightly backups at `/Volumes/main-filestore/
ai-PA-backups/` retain purged data for the backup retention window.
Documented in `docs/security/pa-web-ui-threat-model.md` as part of
Unit 1.6's threat-model update (expected retention = 30 days + backup
window, not 30 days absolute).

### Phase 3 (future plan)
`/btw` ephemeral BtwPane. Depends on Unit 2.1 fork API knowledge;
otherwise independent.

### Phase 4 (future plan)
PWA manifest, service worker, mobile polish, threat-model addendum.

## Documentation / Operational Notes

- **Docs to write / update:**
  - `docs/reference/letta-conversations-fork.md` — Unit 2.1 deliverable.
  - Update `docs/security/pa-web-ui-threat-model.md` — add new routes
    to the ingress-guard scope documentation.
  - Update `pa-web-ui/README.md` — document the left-rail UX, deep-link
    URL convention, conversation-meta table.
  - Update `CLAUDE.md` — note that pa-web-ui has per-conversation
    subprocesses and a conversation switcher; the shared `default`
    conversation is a legacy bucket.
  - Update `MEMORY.md` — record the conversation-meta schema so
    future debugging sessions know where to look for conversation
    state.
- **Operational notes:**
  - Feature flag `PA_WEB_UI_PHASE_2_ENABLED` is the single UI
    rollback; DB schema stays forward.
  - `PA_WEB_UI_MAX_SUBPROCESSES` (Phase 1 env var) governs how many
    concurrent conversations have warm subprocesses. Default 5.
  - Daily cron for trash purge: deferred to Phase 2.5.
  - Fork API response shape is captured in
    `docs/reference/letta-conversations-fork.md`; treat that as the
    source of truth for the shape the code depends on.
- **Rollout sequence:**
  1. Ship Unit 2.1 — schema + backend routes behind the flag (flag
     OFF). Verify schema migration on the live DB.
  2. Ship Units 2.2–2.4 — UI + frontend integration, still flag OFF.
  3. Enable flag in a quiet window. Create a test conversation,
     fork a message, verify both appear in the rail and on Letta.
  4. Monitor `/api/subprocess/status` for per-conv subprocess count
     growth.
  5. After 48h of flag-on stability, remove the 404-on-flag-OFF
     guard (code becomes permanent). Flag itself stays as an emergency
     killswitch for a further 7 days.
  6. After total 9–10 days, retire the flag entirely in a Phase 2.5
     cleanup commit.

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
