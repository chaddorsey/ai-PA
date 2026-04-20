# pa-web-ui

Flask web interface for Mission Control and other Letta agents in the
personal-assistant stack. This is the operator's primary chat surface;
Telegram (via LettaBot) is the secondary phone surface.

## Architecture summary

pa-web-ui's chat path evolved in two phases:

1. **Phase 1 (shipped 2026-04-20).** Direct letta-code subprocess
   backend. pa-web-ui spawns `letta --output-format stream-json ...`
   subprocesses directly rather than POSTing to LettaBot's HTTP
   gateway. See `docs/plans/2026-04-20-001-feat-pa-web-ui-letta-code-migration-plan.md`
   and `docs/security/pa-web-ui-threat-model.md`.
2. **Phase 2 (shipped 2026-04-20).** First-class conversations:
   create / rename / hard-delete with undo / fork from any message;
   left-side conversation rail; per-device "last conv" via
   localStorage; LLM auto-naming on first turn. See
   `docs/plans/2026-04-20-002-feat-pa-web-ui-conversation-switcher-plan.md`.

## Feature flags

| Env var | Default | Purpose |
|---|---|---|
| `PA_WEB_UI_PHASE_1_ENABLED` | `false` | Route `/stream` through the direct subprocess pool. Off falls back to LettaBot HTTP gateway. |
| `PA_WEB_UI_PHASE_2_ENABLED` | `false` | Expose the conversation-switcher rail + CRUD + fork routes. Off leaves Phase-1 chat working. |
| `PA_WEB_UI_AUTONAME_ENABLED` | `true` | LLM auto-naming on first turn. Flip off to keep labels as timestamps. |
| `PA_WEB_UI_AUTONAME_MODEL` | `gpt-5.4-mini` | Model passed to litellm for auto-name calls. |

Rollback for any of these: flip flag → `docker compose up -d pa-web-ui`
(no rebuild needed). Schema stays forward-only; flag-off leaves
migrated data in place, harmlessly.

## Key files

- **`app.py`** — Flask routes, DB helpers, subprocess-pool wiring,
  CRUD handlers.
- **`subprocess_pool.py`** — letta-code subprocess registry with
  per-conversation isolation, turn-lock, LRU eviction, and
  byte-bounded ring buffer.
- **`ingress_guard.py`** — Origin allowlist + CSRF double-submit +
  Host allowlist. Runs before every route dispatch.
- **`static/js/chat.js`** — SSE consumer, thread-card rendering, fork-
  from-here action, conversation switch.
- **`static/js/conversation_rail.js`** — left-rail component (Phase 2).
- **`static/js/sidebar.js`** — right-rail Task Review Sidebar
  (pre-dates Phase 1; not touched by the migration).

## Schema (pa_web)

| Table | Purpose | Phase-2 additions |
|---|---|---|
| `pa_web.conversations` | Per-message log. | `conversation_id TEXT` |
| `pa_web.routing_signals` | Slash-command learning signal. | `conversation_id TEXT` |
| `pa_web.thread_exchanges` | Request-ID-grouped thread history. | `conversation_id TEXT` |
| `pa_web.response_feedback` | Thumbs up/down + agent correction. | `conversation_id TEXT`; old `conversation_id INTEGER` renamed to `local_conversation_pk`. |
| `pa_web.conversation_meta` | (new in Phase 2) Conv-level metadata: label, parent link, `user_renamed` gate. |

`user_renamed` gates auto-naming: once the user manually renames a
conversation (via the rail's inline-edit, which sends `PATCH
/api/conversations/<id>`), the LLM auto-namer never touches the label
again. The UPDATE is race-safe via `WHERE user_renamed = FALSE`.

`conversation_id` backfill resolves MC's `"default"` alias to its real
UUID once at startup (see
`docs/reference/letta-default-alias-resolution.md`). Phase-1 rows get
labeled "Main" in the rail.

## Conversation semantics

- **Main conversation.** Phase-1 shared default — same thread Telegram
  writes to. Labeled "Main" in the rail; `user_renamed=TRUE` so auto-
  naming leaves it alone.
- **New conversation.** Created via the `+` button in the rail. Gets
  a timestamp default label; auto-renames on first turn completion.
- **Fork.** Click the `Fork ↳` link on any assistant message card, or
  `⋯` → "Fork from here" in the rail. **Memory is shared with the
  parent** (Letta blocks are agent-scoped). A banner at the top of the
  forked conversation makes this explicit.
- **Delete.** Hard-delete with 10-second client-side undo toast.
  Deletes from all five `pa_web` tables + Letta server copy. Close
  the tab within the undo window → delete never fires (conv
  survives).

## Local state

| Key | Scope | Purpose |
|---|---|---|
| `pa_chat_device_id` | localStorage, per device | Stable UUID for this browser/device. Phase 2 renamed from `pa_chat_session_id`; a one-shot migration preserves the value. |
| `pa_last_conv_id` | localStorage, per device | Most-recently-selected conversation. Restored on page load before Letta's MRU fallback. |
| `pa_device_id` | cookie, SameSite=Strict | Set by `ingress_guard`. Used for CSRF pairing and the subprocess-pool turn-lock device_id. |
| `pa_csrf_cookie` | cookie, SameSite=Strict, HttpOnly=false | CSRF token, mirrored in `X-CSRF-Token` header on state-changing requests. |

## Running tests

```bash
cd pa-web-ui
python3 -m pytest tests/ -v
```

Container-only smoke tests (test_subprocess_env.py) require
`/workspace-safe` bind mount and auto-skip on the host.

## Deferred (gated on 7-day stability windows)

- Phase 1: remove `LETTABOT_API_URL` / `LETTABOT_API_KEY` from the
  pa-web-ui docker-compose block; delete `stream_mission_control()`;
  consolidate `MISSION_CONTROL_AGENT_ID` and `MC_AGENT_ID` aliases.
- Phase 2: retire `PA_WEB_UI_PHASE_2_ENABLED` flag entirely (keep
  `PA_WEB_UI_AUTONAME_ENABLED` as a permanent runtime toggle).

## Roadmap

- **Phase 3** (unplanned): `/btw` ephemeral BtwPane for side-queries
  that don't pollute the main thread. Opens when Phase 2 is stable.
- **Phase 4** (unplanned): PWA manifest, service worker, mobile
  layout polish, threat-model addendum for service-worker attack
  surface.
