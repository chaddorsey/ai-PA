---
date: 2026-04-20
topic: pa-web-ui-letta-code-migration
---

# pa-web-ui → direct letta-code migration with PWA-first, multi-conversation, fork-aware UX

## Problem Frame

Today pa-web-ui chats with Mission Control via LettaBot's OpenAI-compatible
HTTP endpoint (`POST http://host.docker.internal:8080/v1/chat/completions`).
LettaBot wraps a letta-code subprocess and translates its native stream-json
output into OpenAI chunks — in doing so it **drops** `reasoning`, `tool_result`,
`memfs` change events and other rich event types. It also runs a single shared
letta-code process with `--no-memfs` and a cwd pinned to LettaBot's own
directory. Slackbot / scheduling-orchestrator-api / slack-mcp-server all carry
vestigial `LETTABOT_API_KEY` env vars but already talk directly to the Letta
server, so pa-web-ui is the only real consumer of LettaBot's HTTP API surface.

For the one power user who runs this stack as a daily-driver PA:
- The web UI is the primary interaction surface (not a CLI, not Telegram)
- Phone + desktop should continue the same conversation seamlessly, with live
  token-by-token fan-out on whichever device is attached
- Letta-code's full feature surface should be exposed (memfs enabled,
  reasoning visible, tool_result rendered, skills loaded), and both fork
  UX patterns should be available: persistent "fork from here" for
  experimentation and ephemeral `/btw` for side-queries
- LettaBot remains the Telegram adapter (self-hosted lacks the
  `/v1/environments/register` endpoint required for Letta Code Channels per
  the Letta support thread), but its HTTP API should retire once pa-web-ui
  is migrated; LettaBot becomes a Telegram-only process afterward

The migration is backend-first-phased: each phase ships user-visible value
and can be rolled back independently. The eventual end-state is pa-web-ui
as a multi-conversation, fork-aware PWA with device-synced state, talking
directly to letta-code subprocesses, and LettaBot shrunk to a Telegram
bridge awaiting future Channels-on-self-hosted support.

## Requirements

**Backend subprocess management**
- R1. Pa-web-ui owns a pool of letta-code subprocesses keyed by `(agent_id, conversation_id)`. One subprocess per conversation; all devices attached to a conversation share that subprocess.
- R2. Subprocesses are spawned lazily on first message to a conversation. On cold-start after eviction, the conversation's message history rehydrates from the Letta server.
- R3. Fixed working directory for every subprocess: `/Volumes/main-drive/ai-PA/`. Skills and `.letta/` config load from there. No per-conversation cwd in v1 (future enhancement, not precluded).
- R4. Task remains in `--disallowedTools` until upstream #3205 is resolved. All other letta-code client-side tools (Bash, Read, Edit, Write, Glob, Grep, web_search, conversation_search, manage_todo) are enabled.
- R5. memfs is enabled (remove LettaBot's `--no-memfs`) so letta-code can use its scratch filesystem for multi-turn tasks.

**Event stream fidelity**
- R6. All letta-code stream-json event types flow to the browser without filtering: `text`, `tool_call`, `tool_result`, `reasoning`/`thinking`, `routing`, `token`, `usage`, `done`, `ping`, `error`, plus any others letta-code 0.23.8 emits. Backend does not strip events.
- R7. Token-by-token streaming is fanned out to all attached devices in real time via SSE. When a second device attaches mid-stream, it receives subsequent events live and can render alongside the first device with identical state.
- R8. The existing pa-web-ui frontend (`chat.js`) already has handlers for the rich event types; Phase 1 restores their source and tunes default display conventions per R12.

**Multi-conversation and persistent fork UX (Phase 2)**
- R9. Conversations are first-class entities in the UI. Users can create, switch, rename, and soft-delete conversations. Soft-deleted conversations live in a 30-day trash before hard-deletion.
- R10. Persistent forks are available via a per-message action ("Fork from here") that calls Letta's `POST /v1/conversations/{id}/fork` endpoint. Forks are auto-named (e.g., "fork @ <timestamp>"), renameable, and appear in the conversation list with a parent-link indicator.
- R11. No archive tier, no full-text search, no pinned-primary concept in v1 — most-recently-active is the default view behavior (R15).

**Event rendering conventions**
- R12. Default display conventions:
  - `text`: always inline
  - `tool_call`: header prominent, args collapsed by default, click to expand
  - `tool_result`: 1–2 line preview, collapsed by default, click to expand monospace block
  - `reasoning`/`thinking`: collapsed accordion (matches current chat.js pattern)
  - `routing`, `token`, `usage`, `done`, `ping`: internal — not shown in message stream
  - `error`: prominent alert inline
- R13. Keyboard hints match letta-code conventions where applicable: `[esc]` dismisses modals/panes, `[j]` promotes ephemeral fork to persistent. Mirroring letta-oss-ui's keyboard vocabulary where muscle memory carries across clients.

**Ephemeral /btw side-queries (Phase 3)**
- R14. `/btw <question>` typed in chat input passes through to the active letta-code subprocess's slash-command dispatcher, which forks the conversation in the background and streams the response into a **BtwPane** overlay. User remains in the original conversation throughout.
- R15. BtwPane is a right-side drawer on desktop (~35% width, backdrop blur, pushes main content) and a bottom sheet on mobile (drag-to-dismiss, ~75% screen height). It shows the question at top, the streamed response, and footer actions: `[esc] Dismiss` and `[j] Keep & Switch` (promote to persistent and navigate to the fork).
- R16. On dismiss without promote, the server-side fork is **soft-deleted after 7 days** unless the user promotes it before then. Prevents orphan accumulation from casual /btw use.
- R17. Invocation surfaces include the slash-command in chat input and a keyboard shortcut (`Cmd+/` initial choice, configurable). A discoverable button is optional polish.

**Device sync and default view**
- R18. When a PWA session opens cold (no URL param, no prior state), the UI resumes the user's most-recently-active conversation across any device. No explicit pinning of a "primary" conversation.
- R19. Conversation state is server-owned; devices are thin clients. Two devices on the same conversation are peers — no "active device" concept, no takeover semantics.

**PWA mobile polish (Phase 4)**
- R20. Pa-web-ui ships a PWA manifest (installable to home screen on iOS and Android), a service worker for offline-safe static asset caching, and responsive layouts tuned for phone viewport (conversation switcher as hamburger-opened drawer, BtwPane as bottom sheet, touch-friendly hit targets).
- R21. Access is gated by Tailscale network membership only. No app-level auth (login page, session cookies, device pairing) in v1. Document security posture: if a Tailscale-enrolled device is compromised, attacker has access — acceptable for single-user PA.
- R22. Offline behavior: read existing conversation history from cache; queue send attempts when offline and flush on reconnect. No offline-authored messages guaranteed in v1 (post-v1 enhancement).

**Retirement of LettaBot HTTP API**
- R23. Once Phase 1 ships and is stable, pa-web-ui no longer requires LettaBot's HTTP API. `LETTABOT_API_URL` / `LETTABOT_API_KEY` env vars are removed from pa-web-ui's docker-compose block. Vestigial `LETTABOT_API_KEY` / `ROVER_LETTABOT_API_KEY` env vars in slackbot / scheduling-orchestrator-api / slack-mcp-server (which never actually called LettaBot per code review) are cleaned up in the same sweep.
- R24. LettaBot's process continues to run for its Telegram channel role. `features.heartbeat.enabled` remains user-controlled (support agent suggested disabling to reduce noise; deferred).
- R25. When self-hosted Letta Code Channels becomes available in a future Letta release, LettaBot is a candidate for full retirement. Not in scope for this plan.

**Observability**
- R26. Per-subprocess health endpoint (`/api/subprocess/status`) returning conversation_id, pid, uptime, last-activity timestamp, and event counts.
- R27. Subprocess crash logging to `~/Library/Logs/pa-web-ui/subprocess-<conversation_id>.log`. Correlation via request-id header in SSE events.
- R28. Basic metrics exposed: concurrent subprocess count, eviction rate, cold-start latency, per-conversation message throughput.

## Success Criteria

- **Phase 1 success**: pa-web-ui chats with MC via its own letta-code subprocess pool. Reasoning events and tool_result blocks render in the browser that previously didn't. `LETTABOT_API_URL` removed from pa-web-ui's env. LettaBot's `/v1/chat/completions` endpoint can be disabled without breaking the web UI. Round-trip latency for the first post-migration user message is within 10% of pre-migration latency.
- **Phase 2 success**: Conversation switcher lists MC's conversations, supports create/rename/soft-delete, and shows persistent forks with parent indicators. "Fork from here" on any message creates a sibling conversation and navigates or reveals it. Two browsers attached to the same conversation both receive the same live token stream with no desync.
- **Phase 3 success**: `/btw <question>` in chat input opens BtwPane, streams response while main chat stays interactive. `[j] Keep & Switch` promotes the fork to persistent. Dismissed /btw forks auto-clean after 7 days.
- **Phase 4 success**: PWA installable on iOS and Android from the home screen. Phone opens conversation and receives live stream from an in-progress message on desktop. Conversation switcher accessible via drawer on phone. All features work over Tailscale with no login friction.

## Scope Boundaries

- **Not migrating Telegram** — LettaBot remains the Telegram adapter; self-hosted lacks the `/v1/environments/register` API that Letta Code Channels needs.
- **Not enabling Task** — stays in `--disallowedTools` until upstream #3205 resolves. If upstream fix lands mid-migration, we can flip the flag separately; not a dependency.
- **Not cloning letta-oss-ui visually or behaviorally wholesale** — we mirror event-rendering conventions and keyboard vocabulary (`[esc]`, `[j]`) for muscle-memory portability, but our PA-focused sidebar, task-review layer, and mobile-first PWA layout are distinct from letta-oss-ui's desktop-first design.
- **Not introducing "projects" as a first-class entity** — per-conversation cwd is deferred and not blocked by R3 (fixed cwd can evolve to per-conversation with an additive schema change later).
- **Not adding app-level auth in v1** — R21 commits to Tailscale-only. Login/cookie/pairing auth can be added later without architectural debt.
- **Not adding full-text search across conversations** in v1 — basic rename + list + soft-delete only.
- **Not retiring LettaBot fully** — it stays for Telegram; retirement is conditioned on upstream Channels support landing on self-hosted.
- **Not rewriting the Task Review Sidebar** or its 8 supporting `app.py` routes. The new conversation switcher is a separate component; they coexist in the Phase 2 layout.
- **Not offering conversation pinning, archiving, or branching-from-a-specific-message** (Claude.ai "edit and retry" style) in v1. Fork-from-here uses the current message as the fork point, which aligns with letta-code's `/btw` and fork-subagent semantics.

## Key Decisions

- **Per-conversation subprocess, device-shared**: one letta-code subprocess per conversation; all attached devices share it. Matches the "phone and desktop continue same conversation" requirement (R1, R7, R19). Rationale: any other session model either fragments state (per-browser-session) or serializes devices (per-user singleton).
- **Mid-stream fanout via SSE**: server pub/sub pattern. Each subprocess's stdout feeds a conversation-keyed subscriber list; every attached browser gets every event in real time (R7). Rationale: matches the user's expectation of truly continuous pickup across devices; avoids "snapshot transfer" complexity in fallback option.
- **Backend-first phased delivery**: Phase 1 decouples backend, Phase 2 adds switcher + persistent fork UX, Phase 3 adds /btw BtwPane, Phase 4 adds PWA mobile + observability polish. Each phase independently rollback-able. Rationale: user-visible value ships incrementally; risk is bounded per phase.
- **Fixed cwd at `/Volumes/main-drive/ai-PA/`**: matches LettaBot's current location; `.letta/` config and skills already live there. Simplest; not a lock-in — per-conversation cwd is an additive enhancement (R3).
- **Most-recently-active as the default view**: no pinning concept needed (R18). Removes one layer of UI state and matches Claude.ai / ChatGPT mobile behavior.
- **Tailscale-only auth for Phase 4**: no app-level auth layer. Same posture as current pa-web-ui (which has no auth) and aligns with the Letta server's no-auth-from-host-network posture. Security budget spent on defense-in-depth elsewhere (backups, upgrade safety, etc.), not on a login system for a single user.
- **Track letta-oss-ui patterns without cloning**: mirror event-rendering conventions (R12) and keyboard vocabulary (R13). Do not adopt letta-oss-ui's layout or look-and-feel wholesale — their UI is desktop-first and tool-first; ours is PA-first with a Task Review Sidebar they don't have.

## Dependencies / Assumptions

- **Letta 0.16.7 exposes `POST /v1/conversations/{id}/fork`** — confirmed during brainstorm (HTTP 200 against conv-20d6297a-...). If a future Letta upgrade changes the fork endpoint semantics or shape, Phases 2 and 3 may need rework.
- **Letta-code 0.23.8 emits `/btw` and `BtwPane` over stream-json** — confirmed that both strings exist in the shipped binary. Assumed (to be verified in Phase 3 planning) that sending `/btw X` over stream-json input-format dispatches to the slash-command handler and emits BtwPane-shaped events; if not, pa-web-ui must intercept the slash command and call the fork API directly.
- **Pa-web-ui's existing frontend event-handling** already covers the rich event set (confirmed via `chat.js` grep: handlers for `routing`, `tool_call`, `tool_result`, `thinking`, `text`, `token`, `usage`, `done`, `ping`, `error`). Phase 1 work is primarily on the *backend* to stop filtering events; frontend work is tuning display conventions, not writing new renderers.
- **Task Review Sidebar (`sidebar.js` + 8 `app.py` routes) remains functional throughout** — the migration must not break it. Sidebar's data sources are independent of the chat stream (they query Letta directly for extracted-tasks block contents), so no direct coupling, but the shared layout must accommodate the new conversation switcher.
- **Tailscale is enrolled on all devices that will access the PWA** — Phase 4 PWA mobile depends on this. Adding a device not on Tailscale requires either enrolling it or adding app-level auth (out of scope).
- **Slackbot / scheduling-orchestrator-api / slack-mcp-server do not actually call LettaBot's HTTP API** — verified via `grep` inside their containers; their `LETTABOT_API_KEY` env vars are vestigial. If future work in those services starts using LettaBot's API, the retirement assumption in R23 would need revisiting.

## Outstanding Questions

### Resolve Before Planning

(none — all product-framing decisions are captured in Key Decisions above.)

### Deferred to Planning

- **[Affects R14, R15][Needs research]** Does letta-code's `/btw` slash-command work when invoked over stream-json `--input-format`? Specifically: does sending `{"type":"user","content":"/btw what is the architecture?"}` cause the subprocess to fork + emit BtwPane-shaped events, or does our backend need to intercept `/btw` and call `client.conversations.fork()` directly? If the latter, the Phase 3 implementation is bigger. Validate early in Phase 3 planning with a simple reproducer.
- **[Affects R10][Needs research]** Exact shape of `POST /v1/conversations/{id}/fork` on Letta 0.16.7: does it accept a message cursor (fork-at-message-N) or always fork from current state? Does it return the new conversation ID in the response body? Does it copy archival memory, core memory block state, etc.? Probe during Phase 2 planning.
- **[Affects R7][Technical]** SSE vs WebSocket vs Server-Sent + client-polling for the fanout transport. Pa-web-ui already uses SSE for its `/stream` endpoint; extending SSE is the lowest-surprise path. WebSocket would allow bidirectional client→server messages without a separate POST, which might simplify some patterns. Evaluate during Phase 1 planning.
- **[Affects R1, R2][Technical]** Subprocess pool implementation details: Python `multiprocessing.Manager`? Dedicated supervisor thread? `asyncio.subprocess` with a per-conversation task? Flask's threading model complicates this somewhat. Decide during Phase 1 planning.
- **[Affects R9][Technical]** How to represent fork parent-child relationships in the conversation switcher. Letta server may already track this (via the fork API) or we may need to store a `parent_conversation_id` on our side. Probe during Phase 2 planning.
- **[Affects R15][Technical]** BtwPane mobile bottom-sheet implementation: native-ish via CSS `dvh` units + drag-to-dismiss JS? Use a library (e.g., Vaul)? Roll our own? Decide during Phase 3 planning.
- **[Affects R20][Technical]** Service worker strategy: pure static-asset caching (simplest), or also cache recent conversation history for offline read? Latter requires careful cache invalidation. Decide during Phase 4 planning.
- **[Affects R27][Technical]** Correlation ID propagation across subprocess boundary: how does a request-id set at the web layer make it into subprocess logs? Flask `request.environ` → subprocess env var per message? Decide during Phase 1 planning.
- **[Affects R16][Product-lite]** /btw 7-day soft-delete policy — does this get a user-visible "recently dismissed /btw" list for recovery? Probably no (adds complexity, /btw is by definition ephemeral), but revisit if users report losing side-queries they wanted to keep. Defer to Phase 3.

## Next Steps

→ `/ce:plan` for structured implementation planning (recommended)

The brainstorm is complete. All product-framing decisions are captured.
Planning should produce a phased plan with Phase 1 (backend decoupling +
event fidelity) as the immediate implementation target, and Phases 2–4
scoped but deferred pending Phase 1 validation.
