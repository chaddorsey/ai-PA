---
title: "pa-web-ui direct letta-code subprocess migration with multi-conversation, fork UX, and PWA polish"
type: feat
status: active
date: 2026-04-20
deepened: 2026-04-20
origin: docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md
---

# pa-web-ui → direct letta-code migration (Phase 1 implementation-ready; Phases 2–4 roadmap)

## Overview

Replace pa-web-ui's LettaBot HTTP API backend with per-conversation letta-code
subprocesses spawned and managed by pa-web-ui itself, then layer
multi-conversation + persistent fork UX, ephemeral `/btw` side-queries, and
PWA mobile polish on top. Deliver backend-first in four phases; each phase
ships user-visible value and can be rolled back independently. LettaBot
continues running for its Telegram channel role; its HTTP API retires at the
end of Phase 1 once pa-web-ui no longer depends on it.

This plan implementation-defines Phase 1. Phases 2–4 are captured at
roadmap level here and will get their own dedicated plan files at the start
of each phase, using this plan's Key Decisions and System-Wide Impact
sections as their inputs.

## Problem Frame

(See origin: `docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md`)

Today pa-web-ui's `/stream` endpoint POSTs to `http://host.docker.internal:8080/v1/chat/completions`
(LettaBot's OpenAI-compatible handler). That handler drops `reasoning`,
`tool_result`, and other internal letta-code stream-json event types,
runs a single shared subprocess with `--no-memfs`, and pins cwd to
LettaBot's own directory. Meanwhile, pa-web-ui's `chat.js` already has
rendering handlers for the rich event set — the data shape it expects
never reaches the browser.

The primary user is one power user running a personal AI assistant stack
on self-hosted Letta 0.16.7. Web UI is their primary interaction surface
(not a CLI, not Telegram), with a PA-focused Task Review Sidebar they
depend on. Phone + desktop should continue the same conversation
seamlessly. The CLI's fork primitives (`client.conversations.fork()`,
`/btw` BtwPane) are available on the self-hosted server
(verified HTTP 200), so both persistent-fork and ephemeral-/btw UX
patterns are buildable without waiting on upstream.

## Requirements Trace

All 28 requirements from the origin document are carried forward. Two
amendments identified during planning research are folded in as R4b and R7b;
otherwise wording is preserved.

### Backend subprocess management (R1–R5)
- **R1.** One letta-code subprocess per `(agent_id, conversation_id)`; all attached devices share it.
- **R2.** Lazy spawn on first message to a conversation; rehydrate from Letta server on cold-start after eviction.
- **R3.** Subprocess cwd is a **curated subdirectory** (e.g., `/workspace-safe/`) that carves out `.env`, credential files, and backup directories from the repo root — not `/Volumes/main-drive/ai-PA/` unscoped. Letta `.letta/` config and `omnifocus-cli/skills/` remain accessible. No per-conversation cwd in v1. (Revised during review deepening — exposing the entire repo root via Bash under `--yolo` is a secret-exfiltration primitive.)
- **R4.** `Task` remains in `--disallowedTools` until upstream #3205 resolves.
- **R4b** (amendment — from research). `TodoWrite` is permanently disallowed (silent failures / stuck sessions per LettaBot and user memory). Also disallowed: **`EnterPlanMode`, `AskUserQuestion`** — both are `INTERACTIVE_APPROVAL_TOOLS` in the letta-code SDK and require a control-protocol response which our Python backend implements but should avoid needing (keeping the agent's surface tighter). Effective disallowed list: `Task,TodoWrite,EnterPlanMode,AskUserQuestion`. Re-evaluate each independently as upstream fixes land.
- **R5 (revised during Phase-1 live smoke).** **Memfs is Letta-Cloud-only on letta-code 0.23.8** — `letta-code: --memfs is only available on Letta Cloud (api.letta.com)` (stderr captured on self-hosted Letta 0.16.7; subprocess exits rc=1 when `--memfs` is passed). Original R5 assumed memfs was universally available; it is not. Phase 1 runs with `memfs_enabled=false`. The host `~/.letta/agents/` → container `/root/.letta/agents/` bind-mount is still in place so Phase-2-or-later work can enable memfs if upstream self-hosted parity lands. Agent memory continues to live in Letta server (the authoritative store); the "live filesystem" rendering memfs would add is deferred.

### Event stream fidelity (R6–R8)
- **R6.** Backend forwards every stream-json event type without filtering. Includes letta-code's **control-protocol messages** (`type: "control_request"` / `"control_response"` / `"system"`, with `init` subtype populating `agent_id` / `memfs_enabled` / `conversation_id`). Backend must implement the control-response path — not just read-only stdout parsing — or approval-bearing turns hang indefinitely.
- **R7.** Token-by-token SSE fanout to all attached devices; second device joining mid-stream renders alongside first device with identical state.
- **R7b** (amendment — from research). Assign a monotonic `seq_id` to every event per conversation; mid-stream joining clients may send `?since=<seq_id>` to replay missed events from a server-side ring buffer. Ring buffer sized by **bytes + turn boundary**, not fixed event count: retain events back to the most recent completed turn, or last ~2 MB, whichever is smaller. Below that, the client is told "resync from full history" and re-fetches via existing `loadConversationHistory()`.
- **R7c** (new — from review). **Concurrent-send policy:** at most one in-flight turn per conversation. If a second device POSTs while a turn is streaming on that conversation, the server responds with HTTP 409 + SSE event `{type: "turn_locked", "current_device_id": "...", "seq_id": <current>}`. The UI on the second device shows a banner "another device is composing" with an option to override (forfeits the first device's turn and takes over). Default is wait. R19's "peers, no active device" is amended: devices are peers for *reading*; writes are serialized per turn. Claude.ai and ChatGPT use the same pattern.
- **R8.** Frontend `chat.js` event handlers already exist for rich events; Phase 1 tunes default display conventions (R12) but does not rewrite renderers. New event types required in Phase 1: `turn_locked` (R7c), `control_request` (R6, but normally handled by backend without UI surfacing).

### Multi-conversation + persistent fork UX (R9–R11, Phase 2)
- **R9.** Conversations are first-class; user can create, switch, rename, soft-delete (30-day trash).
- **R10.** "Fork from here" per-message action → `POST /v1/conversations/{id}/fork?agent_id=...` (no request body, per OpenAPI spec).
- **R11.** No archive tier, no full-text search, no pinned-primary concept in v1.

### Event rendering conventions (R12–R13)
- **R12.** text inline; tool_call header prominent with collapsible args; tool_result 1–2 line preview with click-to-expand monospace; reasoning/thinking collapsed accordion; routing/token/usage/done/ping stay internal; error prominent alert.
- **R13.** Keyboard hints mirror letta-code: `[esc]` dismisses, `[j]` promotes ephemeral fork to persistent.

### Ephemeral /btw (R14–R17, Phase 3)
- **R14.** `/btw <question>` typed in chat input passes through to active subprocess's slash-command dispatcher (verification gated — see Deferred Questions).
- **R15.** BtwPane: right drawer on desktop (~35% width), bottom sheet on mobile (drag-to-dismiss).
- **R16.** Dismissed /btw forks auto-delete after 7 days unless promoted.
- **R17.** `/btw` invocation via chat-input slash command and `Cmd+/` keyboard shortcut.

### Device sync + default view (R18–R19)
- **R18.** Cold PWA open → most-recently-active conversation for MC (via Letta `conversations.list` ordered by `last_message_at`). (Revised 2026-04-20: original wording said `last_run_completion`; Phase 2's Unit 2.0 probe confirmed `last_message_at` is the operative field on Letta 0.16.7. If the probe surfaces a different stable field, both plans update together.)
- **R19.** Server owns conversation state; devices are thin clients; no active-device concept.

### PWA mobile (R20–R22, Phase 4)
- **R20.** PWA manifest, service worker, responsive layouts for phone viewport.
- **R21.** Tailscale-only access; no app-level auth.
- **R22.** Offline: read cache only; queue send attempts, flush on reconnect.

### Retirement of LettaBot HTTP API (R23–R25)
- **R23.** After Phase 1 stable, remove `LETTABOT_API_URL`/`LETTABOT_API_KEY` from pa-web-ui's compose block; clean up vestigial references in slackbot, scheduling-orchestrator-api, slack-mcp-server (code verified: none actually call LettaBot).
- **R24.** LettaBot process stays for Telegram; heartbeat remains user-controlled.
- **R25.** Full LettaBot retirement deferred until self-hosted Letta Code Channels lands.

### Observability (R26–R28)
- **R26.** `/api/subprocess/status` endpoint: conversation_id, pid, uptime, last-activity, event counts. **Gated by the same CSRF/Origin check as `/stream` (R29)** to prevent Tailnet-visible conversation-id enumeration.
- **R27.** Crash logging to a **container-visible path** (`/app/logs/subprocess-<conversation_id>.log` inside container, bind-mounted to `~/Library/Logs/pa-web-ui/` on host). Log writer applies a **secret-redaction pass** against known patterns (`sk-*`, `xoxb-*`, `xapp-*`, `Bearer ...`, 40+ char hex tokens, email addresses) before writing stdout/stderr tails. Request-id correlation in SSE events.
- **R28.** Metrics surfaced via `/api/subprocess/status` only (current-state, not time-series): concurrent subprocess count, per-conversation last-eviction timestamp, last cold-start latency, per-conversation event count. Full time-series metrics overshoot single-user operation; revisit if problems arise.

### Security hardening (R29–R30, new in plan revision)
- **R29.** `/stream`, `/api/subprocess/status`, and any new state-changing routes gate access on: (a) Origin/Referer allowlist for the Tailscale hostname(s) only, (b) CSRF token bound to the device_id, (c) explicit Host-header allowlist at the Flask layer. Tailscale is the network perimeter; R29 adds the HTTP-layer perimeter that prevents a non-Tailscale browser tab from exploiting `--yolo` Bash via CSRF.
- **R30.** Subprocess spawn uses an **explicit `env=` dict** — not inherited from the pa-web-ui container. Only `LETTA_BASE_URL`, `PATH` (with skills dirs prepended), and any letta-code-specific config vars are passed. `.env` values (DB passwords, OPENAI_API_KEY, etc.) are NOT in the subprocess's environment. Combined with R3's curated cwd, this ensures a prompt-injection cannot reach secrets via either `os.environ` or `cat .env`. `.lettaignore` at the curated cwd adds a second line of defense for anything Read/Edit/Write might find.

## Scope Boundaries

- Telegram stays with LettaBot (not migrating).
- `Task` and `TodoWrite` remain disallowed (no attempt to flip either tonight or this phase).
- Not cloning letta-oss-ui visually or behaviorally wholesale; event-rendering conventions and keyboard vocabulary only.
- No "projects" as a first-class entity in v1.
- No app-level auth in v1; Tailscale is the perimeter.
- No full-text search, archive tier, pinning, conversation folders, or branch-from-specific-message (Claude.ai "edit and retry" style) in v1.
- Task Review Sidebar (`sidebar.js` + 8 `app.py` routes) stays untouched.
- This plan implementation-defines **Phase 1 only**; Phases 2–4 are roadmap-level and will get dedicated plans when they're next up.

## Context & Research

### Relevant Code and Patterns

- `pa-web-ui/app.py` — `stream()` function with three dispatch paths: `stream_coordination()` (slash `/mprep`), `stream_mission_control()` (default, the migration target), and inline `generate()` (slash-routed via pa-routing-handler). Queue-based keepalive pattern with `KEEPALIVE_PING_INTERVAL = 15.0` is reused across all three.
- `pa-web-ui/app.py::ensure_pa_web_schema()` — idempotent DB schema creation on startup; the migration will extend this to add `conversation_id` to existing tables.
- `pa-web-ui/static/js/chat.js::streamResponse()` — SSE consumer with existing handlers for routing / tool_call / tool_result / thinking / text / token / usage / done / ping / error. `sseBuffer` handles cross-chunk SSE boundaries.
- `pa-web-ui/static/js/chat.js::loadConversationHistory()` — fetches `/api/conversations/{session_id}` and groups messages by `metadata.request_id` into thread-cards. Will need update in Phase 2 to accept `conversation_id` parameter.
- `pa-web-ui/static/js/chat.js::ensureThinkingAccordion()` + `updateThinkingContent()` — existing collapsible-region pattern; extend for tool_call/tool_result per R12.
- `pa-web-ui/static/js/sidebar.js` — fully decoupled from chat; `.page-layout .container + .task-sidebar` two-column CSS layout. No wiring to touch in Phase 1; Phase 2 must coexist in layout.
- `lettabot/src/core/session-manager.ts` — **the canonical reference for the subprocess pool pattern.** Specific functions to mirror:
  - `ensureSessionForKey()` + `_createSessionForKey()` — keyed pool with lazy creation
  - `sessionCreationLocks` — coalesced-creation guard; prevents races when two devices attach simultaneously to a cold conversation
  - `sessionGenerations` — invalidation-during-init safety
  - LRU eviction that **excludes in-flight keys from `processingKeys` set**
  - `withSessionTimeout` — 60 s default wrapping `initialize`/`send`/`bootstrapState` so a wedged subprocess doesn't hang the parent
  - `mergeToolArgs()` — tool_call argument dedupe across delta and cumulative chunk modes (essential — pa-web-ui's current handler does NOT dedupe and will render malformed args on some models)
- `lettabot/src/core/session-manager.ts:175` — `--yolo` / `bypassPermissions` is non-negotiable for headless. Mirror directly.
- `lettabot/node_modules/@letta-ai/letta-code-sdk/dist/index.js::buildCliArgs()` — canonical CLI argument construction reference (lines ~27–156).
- `scheduler-service/src/scheduler_service/services/actions.py` — one-shot `asyncio.create_subprocess_exec` precedent. **Not directly applicable** for long-lived streaming; noted for pattern-language only.

### Institutional Learnings

- **SSE streaming issue analysis** (`docs/debugging/sse_streaming_issue_analysis.md`) — prior incident; five SSE failure modes documented. `X-Accel-Buffering: no` is mandatory on every response; 15-second keepalive is the cure for 48-second silent tool-execution gaps.
- **Letta upgrade schema drift** (`memory/project_letta_upgrade_migration.md`) — the 0.16.6 → 0.16.7 upgrade silently broke conversations when `last_message_at` column was missing. Any upgrade must re-smoke-test `/v1/conversations/{id}/fork` before trusting it.
- **Letta API gotchas** (`memory/MEMORY.md`):
  - Trailing-slash 307-redirects; use `-L` or trailing slash.
  - `PATCH /v1/agents/{id}` with `tool_ids` or `block_ids` **REPLACES** the full list (GET → append → PATCH pattern required if any plan step touches agent config).
  - Messages API wants `{"messages": [...]}`, not bare `{"role":"user",...}`.
- **Docker stdin pipe 64KB deadlock** (`memory/docker-lessons.md`) — doesn't affect this plan's design (subprocess runs inside pa-web-ui container; no `docker exec -i` involved), but is a caution if a future iteration moves subprocesses out of the container.
- **Drive RAG zombie-retry lesson** (`memory/project_drive_rag_sync.md`) — client-side retries during slow cold-starts produce duplicate subprocesses. Frontend `/stream` fetch must explicitly disable retries.
- **TodoWrite block** (`memory/feedback_todowrite_blocked.md`) — confirmed 2026-04-01 that unblocking produces stuck sessions; use `manage_todo` instead. Origin-doc R4 must be extended (amendment R4b above).

### External References

External research skipped — local patterns (LettaBot TypeScript reference + existing Flask SSE + Python stdlib) cover Phases 1–3 completely. PWA specifics for Phase 4 (service-worker caching strategies, iOS install flow quirks) will get a targeted external pass when Phase 4 starts its own plan.

## Key Technical Decisions

- **Subprocess runs inside pa-web-ui container with a _curated_ bind mount, not the repo root.** Alternatives considered: host-side runner via IPC (adds a new service and network hop), bind-mounted host `letta-code` binary (fragile). Decision: add Node + `@letta-ai/letta-code@0.23.8` to pa-web-ui's Dockerfile; mount a curated ai-PA subdirectory (excluding `.env`, `smaug-data/.state/`, `*credentials*.json`, `.granola-tokens.json`, `pa-web-ui/letta-credentials/`, and other secret-bearing paths) into the container as `/workspace-safe`. Subprocess cwd = `/workspace-safe`. Skills directories in `omnifocus-cli/skills/` are explicitly included; `.letta/` config is included. **Revised from pre-review plan** which used the repo root — that exposed every credential via Bash under `--yolo`. (See R3, R5, R30.)
- **Conversation ID strategy.** Server-side conversation IDs are UUIDv4 (regex-validated); arbitrary strings like `pa-web-ui-default` are rejected with HTTP 422. Two acceptable approaches: (a) **built-in "default" alias** — letta-code's `--conversation default` resolves to the agent's server-side default conversation (already used by LettaBot PID 31889 for MC; multi-consumer same-conversation semantics validated by review deferred questions); (b) **pre-create-and-persist** — pa-web-ui POSTs `/v1/conversations/` on first run, persists the returned `conv-<uuid>` in `pa_web.conversations` under a stable internal key, and uses that for subsequent spawns. Phase 1 uses **(a)**: reuse `default`, accept shared-consumer semantics with LettaBot (both clients stream from the same conversation; Telegram and web UI see each other's messages — consistent with "same agent, same memory, different surfaces" brainstorm intent). Phase 2's switcher creates new conversations via (b).
- **Control protocol is in scope for Phase 1.** letta-code's stream-json is bidirectional. The subprocess emits `type: "control_request"` messages for approvals (even under `--yolo`, `INTERACTIVE_APPROVAL_TOOLS` like `AskUserQuestion` / `EnterPlanMode` fire); backend must respond with `type: "control_response"` on stdin or turns hang forever. Unit 1.2's scope is therefore the letta-code transport + session layer reimplemented in Python (init handshake populating `agent_id`/`memfs_enabled`/`conversation_id`; `bootstrapState()` approval probe before first send; `lastCompletedRunIds` stale-run filtering; approval-conflict recovery via `recover_pending_approvals` subtype). **Revised from pre-review plan** which characterized this as "port session-manager patterns" — the actual reimplementation is 2–3× broader. R4b's expanded disallow list (`Task,TodoWrite,EnterPlanMode,AskUserQuestion`) reduces but does not eliminate this need — `manage_todo` and the tool-approval flow generally still use the control protocol.
- **Threading model: extend the existing pattern, don't switch to asyncio.** pa-web-ui today uses `threading.Thread(target=..., daemon=True)` + `queue.Queue` for its SSE pipelines. Migration keeps this shape: one reader thread per subprocess as the single producer, one subscriber queue per attached SSE client as N consumers, one writer path (control responses + user messages) synchronized via a per-subprocess `threading.Lock` around stdin.
- **Per-conversation pub/sub fan-out keyed by `conversation_id` (not `session_id`).** Session IDs identify devices; conversations identify agent threads. Two devices on the same conversation share the subprocess and subscribe to the same event stream. Concurrent writes are serialized per R7c (turn lock, 409 on overlap).
- **Monotonic `seq_id` per conversation + turn-aware ring buffer for replay.** Ring buffer retains events back to the start of the most-recent-completed turn, capped at ~2 MB per conversation. Below the buffer's `seq_id` floor, the client is told "resync from full history" and re-fetches via existing `loadConversationHistory()`. **Revised from pre-review plan's fixed 500-event buffer** which was insufficient for realistic tool-heavy turns.
- **Port `mergeToolArgs` verbatim, reimplement session-manager concurrency patterns pragmatically.** `mergeToolArgs` has a concrete documented bug it fixes (tool_call chunking differs by model) — port directly, including the "flush on semantic boundary, not `stream_event`" rule. Session-manager's generation counters / LRU-with-active-exclusion / timeout wrappers are proven concurrency patterns but may be over-sized for single-user working set of 1–2 active subprocesses; implement the mechanisms but accept simpler defaults (max concurrent=5 fine; generation counter maintained but unlikely to fire). Test coverage specifically for the patterns listed, to catch regressions if the single-user workload ever grows.
- **Session-ID vs conversation-ID vs device-ID split in localStorage.** Current `pa_chat_session_id` (UUID v4) is repurposed as `pa_chat_device_id` (semantic rename; UUID value preserved). A separate `conversation_id` tracks the active conversation in sessionStorage AND URL fragment (deep-linkable — e.g., `/?conv=conv-abc...`). Phase-1 default: `conversation_id` omitted → server defaults to the MC agent's built-in `default` conversation.
- **Backend filters no events; frontend's unknown-type-ignore default handles forward compatibility.** `chat.js:streamResponse()`'s if/else chain has no `else` default — unknown event types are silently ignored. New event types (`turn_locked`, `control_request`) add handlers; others land without coordinated frontend changes.
- **Feature flag shape: per-phase environment variable; 7-day parallel-path window.** Each phase has `PA_WEB_UI_PHASE_N_ENABLED` env var; flag toggle + container restart = rollback. Unit 1.6's removal of `stream_mission_control()` is gated on **7 days** of flag-on operation with a named crash/error budget, not 48 hours — the shorter window misses Letta-upgrade-day edge cases and LettaBot-session-eviction effects on Telegram. (Revised from 48 h during review.)
- **Phase 1's entry point is a parallel code path, not an in-place replacement.** `stream_mission_control()` stays intact; a new `stream_mission_control_direct()` goes next to it behind the Phase 1 flag. Only when Phase 1 is verified stable does the LettaBot path get removed (Unit 1.6).
- **Threat model is Phase 1 scope, not Phase 4.** R29 (CSRF/Origin) and R30 (env hardening) are Phase 1 requirements. A separate `docs/security/pa-web-ui-threat-model.md` documents the bind-mount scope, Bash+yolo authority, and incident-response story, and lands with Unit 1.0 (new — see below). Deferring this to Phase 4 shipped the exposure three phases before its mitigation.

## Open Questions

### Resolved During Planning

- **Where does the subprocess run — host or container?** Resolved: inside pa-web-ui container with a **curated** bind mount (`/workspace-safe`), not the repo root. See Key Decisions.
- **What conversation ID does Phase 1 use?** Resolved: `default` (MC agent's server-side built-in alias). Arbitrary strings are rejected HTTP 422 (empirically verified). Phase 2 creates real UUIDv4 conversations via `POST /v1/conversations/`. Shared-consumer semantics with LettaBot's Telegram subprocess on the same `default` conversation are intentional — same agent, same memory, different surfaces.
- **Is the bare subprocess approach sufficient, or do we need to implement letta-code's control protocol?** Resolved: **the control protocol is Phase 1 scope**. Unit 1.2 includes init handshake, bootstrapState, stale-run filtering, and approval-conflict recovery. Pre-review plan misclassified this as "port patterns"; it's a transport reimplementation.
- **asyncio vs threading for subprocess I/O?** Resolved: threading. Extends existing pattern.
- **SSE vs WebSocket for fanout?** Resolved: SSE.
- **tool_call argument deduplication?** Resolved: implement `merge_tool_args()` mirroring LettaBot's `mergeToolArgs` **with the semantic-boundary flush rule** (not every `stream_event`).
- **Should cwd be configurable per conversation?** Resolved: no in v1.
- **TodoWrite / Task / EnterPlanMode / AskUserQuestion status?** Resolved: all disallowed. See R4b.
- **Ring buffer sizing?** Resolved: turn-aware, capped at ~2 MB per conversation. Below floor → client resyncs via existing `loadConversationHistory()`.
- **Concurrent-send policy?** Resolved per R7c: turn lock; second device gets HTTP 409 + `turn_locked` SSE event + banner UI with override option.
- **Rollback window?** Resolved: 7 days flag-on with named crash/error budget before Unit 1.6 removes old path. 48 h was too short.
- **Memfs path and MC memory migration?** Resolved: bind-mount host `~/.letta/agents/` → container; preserves MC's existing memory accumulated under LettaBot. See R5.
- **Threat model scope?** Resolved: Phase 1 scope (R29, R30) — NOT deferred to Phase 4. Unit 1.0 (new) codifies it before Unit 1.1 touches the Dockerfile.

### Deferred to Implementation

- **[Affects Unit 1.1][Technical]** Exact `letta-code` install mechanism in pa-web-ui Dockerfile. `npm install -g @letta-ai/letta-code@0.23.8` or bundle via a specific Node base image? Node 20 vs 22? Pin or track latest? Decide during Unit 1.1 with a minimal Dockerfile experiment.
- **[Affects Unit 1.0, 1.1][Technical — verify before Unit 1.1]** Exact list of paths to carve out of the curated bind mount. Starting list: `.env`, `.env.*`, `smaug-data/.state/`, `*credentials*.json`, `.granola-tokens.json`, `.granola-client.json`, `pa-web-ui/letta-credentials/`, `gws-bridge/credentials.json`, `.letta/credentials*`, any `*.pem`, `*.key`, SSH material. Audit `/Volumes/main-drive/ai-PA/` comprehensively as part of Unit 1.0 and pin the list in a `docs/security/pa-web-ui-threat-model.md` inventory.
- **[Affects Unit 1.3][Technical]** Exact stream-json schema for every event type letta-code 0.23.8 emits (including control-protocol subtypes). The SDK source documents many; exhaustive enumeration requires running the subprocess with a known prompt and capturing every emission. Do this during Unit 1.3; add a schema validation layer that logs unknown event types.
- **[Affects Unit 1.4][Technical]** Ring buffer implementation — tuple of `(seq_id, event, byte_size)` in `collections.deque`, plus a turn-boundary index. Eviction policy evicts oldest events when byte cap exceeded, but never evicts across a turn boundary that would leave the client mid-turn on resync. Confirm during Unit 1.4.
- **[Affects Unit 1.2][Resolved in plan]** Process-level singleton vs module-level dict for the subprocess registry. Resolved: single global `SubprocessRegistry` class instance instantiated at app startup (holds `Dict[str, SubprocessHandle]` internally, guarded by `threading.Lock`). Flask reloader (`debug=True`) would create two copies; production uses `debug=False`.
- **[Affects Unit 1.2][Technical]** Stdin write back-pressure and failure handling: write timeout (analogous to LettaBot's `withSessionTimeout`), `BrokenPipeError` → invalidate and respawn, partial-write handling (flush + length-framing if individual JSON lines grow past buffer). Decide during Unit 1.2 implementation.
- **[Affects Unit 1.5][Technical — part of Unit 1.0 threat model]** Conversation access binding — since devices are identified by `device_id` cookie and conversation selection is client-driven, a Tailnet attacker with knowledge of a `conv_id` can subscribe to another user's stream. For a single-user PA the attacker model is "any Tailnet device" = "my own devices" = acceptable. But document this in the threat model so future multi-user expansion (if ever) knows to add device→conversation ACLs.
- **[Affects R14–R16][Needs research — Phase 3]** Does letta-code's `/btw` slash-command dispatch when sent over stream-json `--input-format`? If not, backend must intercept and call `conversations.fork` directly, then spawn an ephemeral subprocess for the fork. Verify early in Phase 3 planning with a 10-minute reproducer.
- **[Affects Unit 2.1][Needs research — Phase 2]** Response body shape of `POST /v1/conversations/{id}/fork` on Letta 0.16.7. Write a small `docs/reference/letta-conversations-fork.md` capturing request params, response shape, memory/block copy behavior before Phase 2 starts.
- **[Affects Phase 2][Technical]** Fork parent-child storage: `parent_conversation_id` column on `pa_web.conversations`, or rely on Letta server's own conversation metadata. Depends on fork response shape.
- **[Affects Phase 2][Technical]** `pa_web.response_feedback` already has an INTEGER `conversation_id` column (FK-ish); Phase 2 plans a TEXT `conversation_id` column elsewhere for Letta conv UUIDs. Resolve naming collision during Unit 2.1.
- **[Affects Phase 2][Technical]** Rollback story for Phase 2 schema change (add `conversation_id` column + backfill). Container-restart rollback doesn't unwind DDL. Design explicit down-migration or accept schema as forward-only.
- **[Affects Phase 4][Technical]** Service worker caching strategy and CDN-deps localization. Phase-4 detail.
- **[Affects Phase 1 cleanup][Technical]** Consolidate `MISSION_CONTROL_AGENT_ID` and `MC_AGENT_ID` constants in app.py. One-line fix during Unit 1.6 (**after** Unit 1.5 stabilizes — do NOT consolidate earlier or the parallel-path strategy breaks).

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for
> review, not implementation specification. The implementing agent should
> treat it as context, not code to reproduce.*

### Subprocess pool + fan-out topology (with ingress guard + control protocol)

```mermaid
flowchart LR
    subgraph Browser
        D1[Device 1<br/>chat.js SSE<br/>+CSRF token]
        D2[Device 2<br/>chat.js SSE<br/>+CSRF token]
    end
    subgraph pa-web-ui[pa-web-ui Flask]
        IG[ingress_guard<br/>Origin/CSRF/Host]
        R[/stream route<br/>+keepalive]
        SUB[SubprocessRegistry<br/>keyed by conv_id]
        PUB[Per-conv<br/>Subscriber queues<br/>+ turn-aware<br/>ring buffer ~2MB]
        RT[Reader thread<br/>parses stream-json<br/>stamps seq_id<br/>routes control_request]
        CTRL[Control-response<br/>writer<br/>stdin-locked]
    end
    subgraph letta-code["letta-code subprocess<br/>env=explicit dict per R30"]
        LC[node letta.js<br/>--agent MC<br/>--conversation default<br/>--output-format stream-json<br/>--input-format stream-json<br/>--yolo<br/>cwd=/workspace-safe]
    end
    subgraph Letta[Letta 0.16.7]
        LS[Server at localhost:8283]
    end

    D1 -- POST /stream --> IG
    D2 -- POST /stream --> IG
    IG -- allow --> R
    R -- get or spawn --> SUB
    SUB -- owns --> LC
    LC -- stdout stream-json --> RT
    RT -- user-facing events --> PUB
    RT -- control_request --> CTRL
    CTRL -- control_response<br/>on stdin --> LC
    PUB -- SSE events + pings<br/>to each subscriber --> D1
    PUB -- SSE events + pings<br/>to each subscriber --> D2
    LC -- /v1/agents/... --> LS
```

Notes on the diagram:
- `IG` (Unit 1.0) runs before route dispatch; rejects non-allowlisted Origins, Host mismatches, and missing/mismatched CSRF tokens with HTTP 403/421.
- `R` blocks on its subscriber queue with 15-s keepalive; emits `ping` on timeout.
- `RT` is one thread per live subprocess; it's the single publisher for that conversation's pub-sub. It also routes `control_request` events to `CTRL` rather than forwarding them to subscribers.
- `CTRL` is a separate writer path that shares the stdin lock with the user-message writer. Control responses do NOT consume a turn (no `in_flight` flag).
- `SUB` enforces LRU eviction (max 5 concurrent subprocesses, excluding handles that are `in_flight=True` or have active subscribers), generation counters for invalidation-during-init, creation-lock coalescing, and timeout wrappers — all patterns from LettaBot's session-manager.
- Devices attaching mid-stream optionally pass `since=<seq_id>`; the subscriber queue is seeded from the ring buffer before joining the live stream. If the `seq_id` floor has been evicted, the subscriber receives a `resync_required` marker instead and refetches via `loadConversationHistory()`.

### Subprocess spawn arg shape (pseudo-code, directional only)

```
letta-code invocation for conversation conv-XXX (or "default" in Phase 1):
  /usr/bin/node /opt/letta-code/letta.js
    --agent agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
    --conversation default               # Phase 1; UUIDv4 conv-<uuid> in Phase 2
    --output-format stream-json
    --input-format stream-json
    --yolo
    --allowedTools Bash,Read,Edit,Write,Glob,Grep,web_search,conversation_search,manage_todo
    --disallowedTools Task,TodoWrite,EnterPlanMode,AskUserQuestion
  cwd: /workspace-safe                   # curated bind mount, NOT repo root
  env (explicit dict per R30, nothing inherited):
       LETTA_BASE_URL=http://letta:8283
       PATH=/app/skills/bin:/usr/local/bin:/usr/bin:/bin
       HOME=/root                        # memfs at /root/.letta/agents/$AGENT_ID/memory/
  stdio: pipe, pipe, pipe
```

### Event flow (Phase 1, happy path with control protocol)

```
user message → POST /stream {message, conversation_id, device_id, csrf_token}
  → ingress_guard: Origin allowlist + CSRF match + Host allowlist
  → registry.ensure(conv_id) → subprocess (spawn or reuse)
     - if spawn: wait for {type:"system", subtype:"init"} → populate handle init state
     - bootstrapState() probes pending approvals; recover_pending_approvals if stale
  → handle.send(message)
     - acquire stdin lock; check in_flight flag (409 + turn_locked if set)
     - write {"type":"user","content":msg,"run_id":"<new>"} + \n + flush
     - release lock; set in_flight=True
  → subprocess stdout emits stream-json events
  → reader thread parses each line
     - control_request → control-response writer handles (auto-approve under --yolo)
     - system/init late → warn + drop
     - result/done → forward + add run_id to lastCompletedRunIds + clear in_flight
     - other → stamp seq_id, append to ring buffer, fan out to subscribers
  → each subscriber's /stream generator yields SSE-formatted events to its device
```

### Concurrent-send flow (R7c)

```
device A turn in progress on conv X; device B POSTs /stream for conv X:
  → ingress_guard: pass
  → registry.ensure("X") → existing handle (in_flight=True)
  → handle.send(msg) raises TurnLockedException
  → route handler returns HTTP 409 with body:
       {"type":"turn_locked","current_device_id":"A","seq_id":<handle.current_seq_id>}
  → device B UI shows "another device composing" banner
  → user on B optionally clicks "Take over" → POST /stream with override=true
       → cancels A's turn; new turn begins on B
```

### Cross-device resume flow

```
phone wakes up, POST /stream {conversation_id:"default", device_id:..., since:42}
  → ingress_guard: Origin+CSRF ok
  → registry.ensure(conv_id) (no-op if already alive)
  → handle.subscribe(since=42)
     - if 42 >= ring_buffer.oldest_seq_id: seed queue with buffered[43..head]
     - else: seed queue with {"type":"resync_required"}; client refetches history
  → subscriber joins live stream
  → phone renders replayed events + continues live
```

## Implementation Units

### Phase 1: Backend decoupling + event fidelity (implementation-ready)

- [ ] **Unit 1.0: Threat model + ingress hardening (R29, R30)**

**Goal:** Codify the Phase-1 security posture and the pa-web-ui HTTP-ingress hardening **before** the subprocess pool lands. Produces the threat-model doc, the curated bind-mount inventory, and the CSRF/Origin middleware.

**Requirements:** R29, R30 (both new Phase-1 requirements added during review revision)

**Dependencies:** None — this is a foundation unit.

**Files:**
- Create: `docs/security/pa-web-ui-threat-model.md` (threat model + bind-mount carve-out inventory + incident-response playbook)
- Create: `pa-web-ui/ingress_guard.py` (Flask before-request hook — Origin allowlist, CSRF token check, Host-header allowlist)
- Modify: `pa-web-ui/app.py` (register ingress guard at app init; add CSRF token emission endpoint)
- Modify: `pa-web-ui/static/js/chat.js` (fetch a CSRF token on load, include in `/stream` POST body)
- Modify: `pa-web-ui/static/js/sidebar.js` (include CSRF token on state-changing routes)
- Create: `pa-web-ui/.lettaignore` at the root of the curated bind mount (excludes secrets at the letta-code level as second line of defense)
- Modify: `docker-compose.yml` (configure Tailscale hostname(s) as environment variable for the Origin allowlist)
- Test: `pa-web-ui/tests/test_ingress_guard.py` (CSRF + Origin scenarios)

**Approach:**
- **Threat model doc**: articulate the single-user PA context, enumerate what the subprocess can read (curated workspace contents), what it cannot (`.env`, credentials, SSH material), what happens if Tailscale is compromised (acceptable risk: Tailscale device auth + user attention, but no app-layer auth means a compromised Tailnet device gets PA access). Incident response: how to kill the subprocess pool (`docker compose restart pa-web-ui`), how to wipe memfs to contain prompt-injection-written content (`docker volume rm`, with caveat that it clears agent memory).
- **Carve-out inventory**: audit `/Volumes/main-drive/ai-PA/` exhaustively. Produce a grep for obvious secret patterns (AWS keys, `sk-*`, `xoxb-*`, `Bearer `, API key comments) and pin every match to the exclusion list. This IS the definition of "curated" for Unit 1.1's bind mount.
- **CSRF token**: double-submit cookie pattern. Token generated per session, stored in a SameSite=Strict cookie and mirrored in `pa_chat_csrf_token` localStorage. State-changing routes (`/stream`, any new `/api/*` POST/PATCH/DELETE) compare cookie vs header/body token. Reads (`/api/subprocess/status`, `/api/tasks`) check Origin only.
- **Origin allowlist**: env var `PA_WEB_UI_ALLOWED_ORIGINS` (comma-separated hostnames and Tailscale MagicDNS names). Requests with an Origin or Referer outside the list get HTTP 403. Requests with no Origin/Referer (e.g., curl, server-to-server) are allowed only for explicitly-marked internal endpoints.
- **Host-header allowlist**: separate middleware — HTTP 421 for unrecognized Host headers (DNS-rebind mitigation).
- **`.lettaignore`** at the curated cwd root: `.env`, `.env.*`, `*credentials*`, `*.pem`, `*.key`, `.granola-*.json`, `smaug-data/.state/`. Letta-code's `.lettaignore` honors this for `@file` completion and — verified during Unit 1.1 smoke — also for Bash's working context (second line of defense; bind-mount scope is the primary defense).

**Execution note:** Start with a failing integration test that hits `/stream` from a non-allowlisted Origin and asserts HTTP 403. Then build the guard to pass.

**Patterns to follow:**
- `CORS(app)` is already enabled in pa-web-ui; the guard adds a narrower allowlist on top without removing CORS (CORS is for preflight; the guard is for state changes).
- Letta server's no-auth-from-loopback posture (we keep; the guard is only between browser and pa-web-ui, not between pa-web-ui and Letta).

**Test scenarios:**
- Happy path: request from `https://pa-web-ui.tailnet-name.ts.net` Origin → allowed.
- Happy path: sidebar polls `/api/tasks` (GET) with valid Origin → allowed.
- Edge case: no Origin header (curl, CLI) hitting `/stream` → HTTP 403.
- Error path: Origin from a non-allowlisted domain (`https://attacker.example`) → HTTP 403.
- Error path: POST `/stream` with body CSRF token mismatched to cookie → HTTP 403.
- Error path: POST `/stream` with missing CSRF token → HTTP 403.
- Error path: Host header = IP address instead of Tailscale name → HTTP 421 (DNS-rebind mitigation).
- Integration: CSRF token refresh cycle — long-lived session gets a new token on page reload without breaking in-flight SSE.

**Verification:**
- `docs/security/pa-web-ui-threat-model.md` exists and passes user review.
- Curated-path carve-out inventory is committed and references every known secret location.
- Browser-initiated chat round-trip still works end-to-end.
- `curl -X POST http://pa-web-ui.tailnet/stream -d '{"message":"hi"}'` from a shell returns HTTP 403 (no Origin, no CSRF token).

- [ ] **Unit 1.1: Letta-code runtime in pa-web-ui image + curated bind mount + memfs at correct path**

**Goal:** pa-web-ui's container can invoke `letta --agent X --conversation default --output-format stream-json ...` against the curated workspace at `/workspace-safe` with `.letta/` config and skills available, and MC's existing memory at `~/.letta/agents/<mc-id>/memory/` visible to the subprocess.

**Requirements:** R3, R5, R30 (partial — the bind-mount scoping part)

**Dependencies:** Unit 1.0 (carve-out inventory + threat model must exist before mount scope is decided)

**Files:**
- Modify: `pa-web-ui/Dockerfile` (add Node 20 + `@letta-ai/letta-code@0.23.8` global install)
- Modify: `pa-web-ui/requirements.txt` (no change expected; Python deps unchanged)
- Modify: `docker-compose.yml` (pa-web-ui block: curated bind mount from the Unit-1.0 inventory; bind-mount host `~/.letta/agents/` → container `/root/.letta/agents/` read-write; PA_WEB_UI_PHASE_1_ENABLED env var default false)
- Test: `pa-web-ui/tests/test_subprocess_env.py` (new; minimal smoke — subprocess spawn, agent-list round-trip, memfs-path visibility)

**Approach:**
- Use `node:20-bookworm-slim` as a build stage; copy node+npm binaries into the Python image. Install letta-code globally with exact version pin.
- **Curated bind mount**: instead of `./:/workspace:rw`, enumerate the included paths from Unit 1.0's inventory. Options:
  - (a) Bind each required subdirectory individually into `/workspace-safe/` (e.g., `.letta/`, `omnifocus-cli/`, `letta/`, `docs/`, `smaug-data/bookmarks.md`, etc.) — verbose but scoped precisely.
  - (b) Bind the repo root read-only into an internal layer, then overlay tmpfs masks for excluded paths — fragile.
  - **Recommended: (a)** with explicit list in compose; add new entries as needs arise.
- **Memfs path**: bind-mount host `/Users/dorseyhomeserver/.letta/agents/` → container `/root/.letta/agents/` (rw). MC's existing memory accumulated under LettaBot is immediately visible. Other agents' memory is also visible (acceptable — subprocess only spawns for MC's agent_id in Phase 1).
- **env dict prep**: document in this unit what env vars the subprocess should inherit (empty list except `LETTA_BASE_URL` and a curated `PATH`). Implementation of the restricted `env=` dict is Unit 1.2's spawn logic, but the compose block should NOT rely on container-level env inheritance for anything subprocess-specific.

**Patterns to follow:**
- Other services' Dockerfile patterns (slackbot, gws-bridge) for Python-plus-binary combos.
- Curated bind-mount listings in other Docker-Compose files on the project (no direct precedent in this repo; pattern-new but well-understood Docker idiom).

**Test scenarios:**
- Happy path: `docker compose exec pa-web-ui letta --version` returns `0.23.8 (Letta Code)`.
- Happy path: `docker compose exec pa-web-ui ls /workspace-safe/.letta/` returns existing config files.
- Happy path: `docker compose exec pa-web-ui ls /root/.letta/agents/agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef/memory/` — MC's existing memory directory visible.
- Edge case: `docker compose exec pa-web-ui ls /workspace-safe/.env` → no such file (carved out).
- Edge case: `docker compose exec pa-web-ui ls /workspace-safe/smaug-data/.state/` → no such file (carved out).
- Edge case: container restart preserves content under `/root/.letta/agents/` because it's bind-mounted from the host (host's directory is the source of truth; container doesn't own it).
- Edge case: `docker compose exec pa-web-ui letta --conversation default --agent agent-90b2e860-... -p "hello" --output-format stream-json` emits parseable stream-json including a `system init` event with `agent_id`, `memfs_enabled=true`, and `conversation_id` matching MC's default.
- Error path: subprocess spawn with invalid agent ID returns recognizable exit code / stderr.

**Verification:**
- `docker compose exec pa-web-ui letta agents list` returns our 44 agents.
- A manual `letta -p "hello" --conversation default --agent agent-90b2e860-... --output-format stream-json` invocation inside the container emits parseable stream-json and does not expose `.env` contents to the subprocess (test: prompt injection asking `cat /workspace-safe/.env` fails with "No such file").
- Letta-code's `system init` event reports `memfs_enabled=true` and the conversation's current `message_count` > 0 (demonstrating that MC's memory rehydrated from the bind mount).

- [ ] **Unit 1.2: Subprocess pool + keyed registry + control-protocol transport (Python reimplementation of letta-code-sdk session layer)**

**Goal:** A module-level `SubprocessRegistry` that spawns, pools, evicts, and invalidates letta-code subprocesses keyed by `(agent_id, conversation_id)`. Each handle owns the full bidirectional transport: init handshake, control-request/response path, stale-run filtering, approval-conflict recovery. Thread-safe.

**Requirements:** R1, R2, R4, R4b, R6 (the control-protocol half), R30 (the env= dict)

**Dependencies:** Unit 1.1

**Files:**
- Create: `pa-web-ui/subprocess_pool.py` (new module — SubprocessRegistry class, SubprocessHandle class, spawn/evict/control logic)
- Create: `pa-web-ui/tests/test_subprocess_pool.py` (new — pool lifecycle + control-protocol tests)
- Modify: `pa-web-ui/app.py` (import + instantiate registry at module scope; install SIGTERM handler)

**Approach:**
- **`SubprocessRegistry`**: class instance with `Dict[str, SubprocessHandle]` keyed by `conv_id`, guarded by `threading.Lock`, plus `sessionCreationLocks: Dict[str, threading.Event]` and `sessionGenerations: Dict[str, int]` matching LettaBot's patterns.
- **`SubprocessHandle`**: owns process handle, stdin/stdout/stderr streams, last-used ts, generation counter, creation lock, in-flight flag, subscriber list (populated by Unit 1.4), ring buffer (Unit 1.3), init state (`agent_id`, `memfs_enabled`, `conversation_id`, `model`, `tools`), pending control-request map for approval-response correlation.
- **`ensure(agent_id, conv_id) -> SubprocessHandle`**: GET-if-alive-or-creating fast path; else acquire creation lock; else spawn.
- **Spawn**: compose CLI args (High-Level Technical Design section updated below), `subprocess.Popen(..., stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd="/workspace-safe", env={explicit dict per R30})`. Wait for `type: "system", subtype: "init"` event (Unit 1.3's reader surfaces it); populate handle's init state from it. Up to 60 s timeout on init — longer than pre-review plan's spawn timeout to accommodate memfs hydration.
- **Control protocol**: when reader (Unit 1.3) receives `type: "control_request"`, look up the subtype:
  - `recover_pending_approvals`: respond with either approvals auto-affirmed (matching LettaBot's `--yolo` behavior for non-INTERACTIVE_APPROVAL_TOOLS) or rejected (for INTERACTIVE types — but those are in `--disallowedTools` per R4b, so should never be invoked).
  - `approval` (general): auto-approve under `--yolo` semantics.
  - Unknown subtype: log warning, send generic denial, continue.
- **Stale-run filtering**: maintain `lastCompletedRunIds: Set[str]` per handle. When reader parses a run-id in an event, drop events belonging to a run the handle already marked complete — prevents late emissions from leaking across turns.
- **`bootstrapState()`**: on first use of a handle (or after eviction+respawn), send a probe asking the server about pending approvals for this conversation. If any are stale (from a crashed earlier run), call `recover_pending_approvals`. Before returning to caller, confirm the subprocess is ready to accept a new user message.
- **Send (user message)**: acquire per-handle stdin lock; check `in_flight` flag — if set, raise `TurnLockedException` (caller converts to HTTP 409 per R7c). Else set in_flight, write `{"type":"user","content":msg,"run_id":"<new>"}` + newline, flush. Release lock.
- **Send (control response)**: separate path — acquire stdin lock, write `{"type":"control_response",...}`, flush. Does NOT set in_flight.
- **Eviction**: LRU over `last_used` ts; exclude handles with `in_flight=True` OR any attached subscribers. Max concurrent default 5.
- **Invalidation**: generation counter bumps on any error; subsequent `ensure()` calls see stale generation → discard + respawn.
- **Shutdown**: SIGTERM handler closes every subprocess cleanly before Flask exits. Drain stdin, send terminate signal, wait up to 5 s, SIGKILL if still alive.

**Execution note:** This is a reimplementation of the letta-code-sdk TypeScript `SubprocessTransport` + `Session` layers in Python, not just a "port of session-manager." Budget accordingly.

**Patterns to follow:**
- `lettabot/node_modules/@letta-ai/letta-code-sdk/dist/index.js::SubprocessTransport` and `Session` — control-protocol reference.
- `lettabot/src/core/session-manager.ts::ensureSessionForKey`, `sessionCreationLocks`, `sessionGenerations`, LRU logic — concurrency-pattern reference.
- Existing pa-web-ui module-level state pattern (e.g., `http_client = httpx.Client(...)` at module scope).

**Test scenarios:**
- Happy path: first `ensure("default")` spawns; second call returns the same handle.
- Happy path: `ensure("conv-A-uuid")` and `ensure("conv-B-uuid")` concurrently spawn two distinct subprocesses.
- Happy path: init event arrives → handle populated with agent_id, memfs_enabled, conversation_id from the event payload.
- Happy path: `bootstrapState()` runs before first send; no pending approvals → proceeds; pending approval present → sends `recover_pending_approvals` control response → waits for ack → then returns ready.
- Edge case: two threads simultaneously call `ensure("conv-C")`; only one subprocess spawned (creation-lock coalescing). Both return the same handle.
- Edge case: LRU eviction with 6 active conversations and max=5 → oldest-unused evicted; one with active subscribers or in_flight=True is not evicted.
- Edge case: send returns TurnLockedException when in_flight=True; caller (Unit 1.5) converts to HTTP 409.
- Edge case: stale run — reader surfaces event with `run_id` that's in `lastCompletedRunIds` → event dropped, not forwarded to subscribers.
- Error path: subprocess spawn fails (missing letta binary) → exception propagates; next `ensure()` retries cleanly.
- Error path: subprocess init timeout (60 s no init event) → kill + exception.
- Error path: generation-counter invalidation — if `invalidate("conv-A")` runs during an in-progress init, the completing init is discarded and next `ensure()` respawns.
- Error path: control_request for an unknown subtype → generic denial, continue; warning logged.
- Error path: stdin `BrokenPipeError` on send → invalidate handle, next `ensure()` respawns, original send returns error.
- Error path: SIGTERM during active streams — handler kills all subprocesses (graceful TERM→5s wait→KILL); process exits 0.
- Integration: real spawn → init event received with expected agent_id → send "hello" → at least one parseable event returned within 5 s → subprocess responds to SIGTERM within 5 s.
- Integration: concurrent-send scenario — send turn 1, while streaming send turn 2 → second send gets TurnLockedException.
- Integration: env=dict enforcement — spawn subprocess then attempt `Bash: echo $POSTGRES_PASSWORD` → empty/error; `echo $LETTA_BASE_URL` → returns the configured URL.

**Verification:**
- Three conversations open, three subprocesses visible via `docker compose exec pa-web-ui ps -ef`.
- Killing a subprocess manually (`kill -9 <pid>`) → next message to that conversation respawns it.
- `registry.shutdown()` cleanly terminates all children (observable via `ps -ef` before/after).
- Subprocess env inspection shows no `POSTGRES_PASSWORD`, no `OPENAI_API_KEY`, no `SLACK_BOT_TOKEN` — only `LETTA_BASE_URL` and `PATH`.

- [ ] **Unit 1.3: Stream-json reader with tool-call dedup + seq_id stamping + event envelope**

**Goal:** One reader thread per live subprocess parses stdout line-by-line, deduplicates tool_call args, stamps a monotonic `seq_id`, appends events to the ring buffer, and publishes to subscribers. Handles partial-line buffering, non-JSON stderr noise, and stream end cleanly.

**Requirements:** R6, R7, R7b

**Dependencies:** Unit 1.2

**Files:**
- Modify: `pa-web-ui/subprocess_pool.py` (add `SubprocessHandle.reader_thread` function body, `merge_tool_args`, ring buffer, seq_id counter)
- Create: `pa-web-ui/tests/test_stream_parser.py` (new — parser tests with canned stream-json fixtures)
- Create: `pa-web-ui/tests/fixtures/stream_json_samples/` (new — canned stdout samples: happy path, tool_call-chunked, malformed lines, stderr mixed, mid-line chunk split)

**Approach:**
- Reader loop: `for line in iter(process.stdout.readline, b""):` decode UTF-8, strip, skip empty.
- Per line: try `json.loads`; on `JSONDecodeError`, log at debug level and continue (stderr occasionally lands in stdout on some builds).
- **Route by event type**:
  - `system`+`init` → populate `handle.agent_id`, `memfs_enabled`, `conversation_id`, model, tools. Signal init-complete via `handle.init_event`.
  - `control_request` → hand off to the control-response handler (Unit 1.2). Do NOT forward to subscribers (internal protocol).
  - `result` / `done` → forward to subscribers AND add run_id to `handle.lastCompletedRunIds`; clear `in_flight` flag.
  - All other types → forward to subscribers.
- `merge_tool_args(buffered_args, new_chunk)`: handle both delta-style and cumulative-style chunking. **Flush buffered tool_call only when a non-`stream_event` semantic event arrives** (not on every chunk). LettaBot's `mergeToolArgs` is the reference.
- seq_id: monotonic `int` counter per subprocess; stamp on each emitted event before fanout.
- Ring buffer: `collections.deque` with custom eviction — never evict events that would leave the buffer below a turn boundary; cap total size to ~2 MB (approximate byte count per event). Track `turn_start_seq_id` markers for replay integrity.
- Envelope: each event augmented with `{seq_id, emitted_at, request_id}` metadata.
- Reader thread exits cleanly on EOF (subprocess exited) or read error; sets `handle.alive=False`; notifies subscribers of `{type: "done", reason: "subprocess_exited"}`.

**Patterns to follow:**
- `lettabot/src/core/session-manager.ts::handleMessage()` and `messages()` — stream-json iteration pattern.
- `lettabot/src/core/session-manager.ts::mergeToolArgs` (~lines 624–655).

**Test scenarios:**
- Happy path: a stream-json fixture with alternating `reasoning`, `tool_call`, `tool_result`, `text`, `done` → parsed in order; each event has monotonically-increasing seq_id.
- Edge case: tool_call args chunked across 5 lines (delta mode) → single merged `tool_call` event with complete args.
- Edge case: tool_call args chunked as cumulative JSON (each chunk contains the full-so-far args) → single event with final args only.
- Edge case: mid-line buffer boundary (readline returns partial line due to buffering) → handle returns only complete lines; next readline continues correctly.
- Edge case: stderr text interleaved into stdout (non-JSON) → skipped silently, reader continues.
- Edge case: malformed JSON line → logged at debug; parser does not crash.
- Error path: subprocess killed mid-stream → reader exits, final event is a synthetic `{type: "done", reason: "subprocess_exited"}` visible to subscribers.
- Integration: reader thread + real subprocess → after sending "hello" on stdin, at least one `text` event reaches a test subscriber queue within 5 s.

**Verification:**
- Capture real stdout from a sample interaction; replay through parser; event types seen include at least `reasoning`, `tool_call`, `tool_result`, `text`, `done`.
- `merge_tool_args` unit tests pass both delta and cumulative scenarios.

- [ ] **Unit 1.4: Per-conversation pub/sub fanout with seq_id-based resume**

**Goal:** Subscribers can attach to a conversation's event stream, optionally resume from a given `seq_id`, and receive events live thereafter. Disconnection cleanly removes the subscriber without affecting others.

**Requirements:** R7, R7b, R19

**Dependencies:** Unit 1.3

**Files:**
- Modify: `pa-web-ui/subprocess_pool.py` (add `Subscriber` class; `SubprocessHandle.subscribe(since=None) -> queue.Queue`, `unsubscribe(queue)`)
- Create: `pa-web-ui/tests/test_fanout.py` (new — subscriber behavior tests)

**Approach:**
- Each `SubprocessHandle` owns a `subscribers: List[queue.Queue]` list, guarded by a lightweight lock.
- `subscribe(since: Optional[int]) -> queue.Queue`: create a new `queue.Queue(maxsize=1000)`. If `since` is provided AND `since >= handle.ring_buffer.oldest_seq_id` (buffer still has it), seed with ring-buffer entries where `seq_id > since`. If `since < oldest_seq_id` (buffer evicted it), return a special queue pre-seeded with `{"type": "resync_required", "reason": "ring_buffer_evicted"}` — client fetches full history via `loadConversationHistory()` and then re-subscribes with `since=None`. Add to subscribers list. Return.
- `unsubscribe(q)`: remove from subscribers; drain and discard any pending.
- Reader thread (Unit 1.3) on each parsed event: iterate subscribers; for each, try `put_nowait(event)`. On `queue.Full`, **emit a `{"type": "slow_subscriber"}` marker to that subscriber** (so its client can log/degrade gracefully) before dropping — not silent-drop. If a subscriber repeatedly (N=10) fails `put_nowait`, force-unsubscribe it.
- `/stream` endpoint (Unit 1.5) calls `subscribe()`, yields from the queue with keepalive timeout, calls `unsubscribe()` on `GeneratorExit`.

**Patterns to follow:**
- Existing `pa-web-ui/app.py::stream_mission_control()` queue-based SSE pattern — generalized from 1:1 to 1:N.

**Test scenarios:**
- Happy path: two subscribers attached, one event published → both receive it.
- Happy path: subscriber with `since=10` → receives seq_id 11, 12, 13, ... from buffer, then joins live.
- Edge case: subscriber attaches with `since` higher than any buffered → receives only live events (no replay).
- Edge case: subscriber attaches with `since=None` → receives only live events (no replay).
- Edge case: ring buffer has evicted events older than `since` → subscriber receives everything still in buffer; missed events are gone (acceptable under R7b — user-visible as "some events dropped during extended offline").
- Error path: slow subscriber fills its queue → `put_nowait` raises Full; reader drops event for that subscriber only, logs a warning. Other subscribers continue.
- Error path: subscriber disconnects mid-stream (GeneratorExit in Flask) → queue removed cleanly; no effect on other subscribers or reader.
- Integration: spawn subprocess, send a message, two subscribers see identical events in identical order.

**Verification:**
- Manual: open two browser tabs to the same conversation → both render identical token stream in real time.
- Kill one tab → other continues uninterrupted; subprocess stays alive.

- [ ] **Unit 1.5: New `/stream` backend path routing through subprocess pool**

**Goal:** The `/stream` endpoint has a new code path (feature-flagged) that dispatches to the subprocess pool instead of LettaBot's HTTP API. On flag off, existing behavior is unchanged. Event types emitted on the SSE match what `chat.js` already renders.

**Requirements:** R6, R7, R12, R23 (precondition for retirement)

**Dependencies:** Unit 1.2, 1.3, 1.4

**Files:**
- Modify: `pa-web-ui/app.py` (`stream()` route; add new `stream_mission_control_direct()` function; feature-flag dispatch)
- Modify: `pa-web-ui/templates/index.html` (no change expected; frontend stays on `/stream`)
- Modify: `pa-web-ui/static/js/chat.js` (small change: explicitly disable fetch retries on `/stream` per learning #10; pass `device_id` and optional `since` params)
- Create: `pa-web-ui/tests/test_stream_direct.py` (new — route-level integration tests with mocked subprocess pool)

**Approach:**
- **Ingress gate (R29)**: `stream()` already runs behind Unit 1.0's `ingress_guard` middleware — CSRF + Origin + Host check happen before dispatch.
- New route handler `stream_mission_control_direct()`:
  1. Parse request body: `message` (may be empty for resume-only), `conversation_id` (defaults to the string `"default"` — the MC agent's built-in default alias), `device_id`, optional `since` (seq_id from disconnect).
  2. `handle = registry.ensure(agent_id=MC_AGENT_ID, conv_id=conversation_id)`.
  3. If `message` is non-empty:
     - try `handle.send(message)`. If it raises `TurnLockedException`, return HTTP 409 with `{"type": "turn_locked", "current_device_id": ..., "seq_id": handle.current_seq_id}` (no SSE stream).
     - On success, proceed.
  4. `queue = handle.subscribe(since=since)`.
  5. Return an SSE generator that yields events from the queue with 15-s `queue.get(timeout=15)` → emit `ping` on empty. On event, format as SSE `data: {...}\n\n`.
  6. On `GeneratorExit` or on `{type: "result"}` / `{type: "done"}`, call `handle.unsubscribe(queue)`.
  7. `X-Accel-Buffering: no` response header mandatory.
- Preserve `request_id` stamping in events for client-side correlation.
- Feature-flag dispatch in `stream()`: if `PA_WEB_UI_PHASE_1_ENABLED and not coordination and not slash_routed`, route to `stream_mission_control_direct()`; else existing `stream_mission_control()`.
- **Resume variant**: `POST /stream` with empty `message` and `since=<seq_id>` is the resume path (same route, different request shape). GET is NOT supported — keeps auth guards consistent.

**Patterns to follow:**
- `pa-web-ui/app.py::stream_mission_control()` — SSE envelope, keepalive, `GeneratorExit` handling.
- `pa-web-ui/app.py::generate()` inline slash-routed path — the passes-events-through pattern (no OpenAI-compat translation).

**Test scenarios:**
- Happy path (feature flag OFF): `/stream` behaves identically to pre-migration baseline.
- Happy path (flag ON, no slash, no `/mprep`): message routes to subprocess pool; response streams text + tool_call + reasoning events to browser.
- Edge case (flag ON): `conversation_id` not provided → server defaults to the string `"default"` (MC agent's built-in alias). Arbitrary names like `pa-web-ui-default` are rejected HTTP 422 by Letta (UUIDv4-regex validator on the server side — empirically verified during review). Shared-consumer semantics with LettaBot's Telegram subprocess on the same `default` conversation are intentional for Phase 1; Phase 2 introduces real per-conversation routing via `POST /v1/conversations/` + persisted UUIDs.
- Edge case (flag ON): client sends `since=<integer>` query → subscriber seeded from ring buffer.
- Error path (flag ON): subprocess pool fails to spawn (missing binary, timeout) → SSE emits `{type: "error", message: "..."}` and closes cleanly; client sees error card.
- Error path (flag ON): client disconnects mid-stream → `GeneratorExit`, subscriber cleaned up; subprocess stays alive; other clients continue unaffected.
- Integration: two browser tabs on the conversation → both render the same event stream; killing one tab has no effect on the other.
- Integration: flag toggle mid-deployment → existing open SSE streams finish on their original code path; new streams pick up the new path.

**Verification:**
- Browser chat round-trip works end-to-end with flag ON.
- Reasoning events render in the existing thinking accordion.
- `docker logs pa-web-ui` shows parsed stream-json events without errors over a 5-minute session.
- Cold-start latency (first message after eviction) ≤ 10 s, warm-start ≤ 500 ms.

- [ ] **Unit 1.6: Observability + cleanup + LettaBot HTTP API retirement**

**Goal:** Phase 1 is production-shaped: subprocesses are observable, crashes are logged, SIGTERM is handled, and the LettaBot HTTP API references can come out once the flag is on by default.

**Requirements:** R23, R26, R27, R28

**Dependencies:** Unit 1.5 stable in production

**Files:**
- Modify: `pa-web-ui/app.py` (new routes: `GET /api/subprocess/status`; SIGTERM handler; consolidate `MISSION_CONTROL_AGENT_ID` and `MC_AGENT_ID`)
- Modify: `pa-web-ui/subprocess_pool.py` (metrics hooks: `concurrent_subprocess_count`, `eviction_count`, per-conv `event_count`, crash log writers)
- Modify: `docker-compose.yml` (remove `LETTABOT_API_URL` and `LETTABOT_API_KEY` from pa-web-ui block; leave LettaBot container unchanged; remove vestigial `LETTABOT_API_KEY` from slackbot, scheduling-orchestrator-api, slack-mcp-server blocks)
- Modify: `.env` (remove `LETTABOT_API_URL` if present; keep `LETTABOT_API_KEY` in .env for now since LettaBot still uses it for its own auth — but document as Telegram-only going forward)
- Create: `pa-web-ui/tests/test_status_endpoint.py`

**Approach:**
- `/api/subprocess/status`: return JSON of every live handle — conv_id, pid, uptime, last_used, generation, event_count, subscriber_count. **Gated by ingress_guard** (R29) — returns HTTP 403 for non-allowlisted Origins.
- SIGTERM: install with `signal.signal(SIGTERM, handler)`; handler calls `registry.shutdown()` which closes every subprocess cleanly (graceful TERM → 5 s wait → SIGKILL) before Flask exits.
- **Crash logging path**: write to `/app/logs/subprocess-<conv_id>-<timestamp>.log` inside container; docker-compose bind-mounts `/app/logs/` to host `~/Library/Logs/pa-web-ui/`. (Revised — pre-review plan's direct-host-path assumption doesn't work inside Linux container.) Rotate: one file per crash window, keep last 20 per conversation.
- **Crash log redaction**: run stdout/stderr tails through a regex scrubber before writing. Patterns redacted: `sk-[a-zA-Z0-9-_]{20,}` (API keys), `xoxb-[a-zA-Z0-9-]{20,}` and `xapp-[a-zA-Z0-9-]{20,}` (Slack), `Bearer [A-Za-z0-9._-]+`, `[a-f0-9]{40,}` (long hex), emails (`\b\w+@\w+\.\w+\b`), and anything matching values listed in `.env` (read once at startup into a deny set). Replace with `[REDACTED]`.
- Consolidate constants: pick `MC_AGENT_ID` (shorter), update all references, add deprecation comment on any lingering alias. Do this ONLY in Unit 1.6 — premature consolidation breaks the parallel-path strategy.
- LettaBot retirement: once Phase 1 flag has been default-on for **7 days** with a **defined crash/error budget** (< 1 subprocess crash per day, no user-reported regressions, Letta-server round-trip latency within 10% of pre-migration baseline) remove env vars and old `stream_mission_control()` function. LettaBot container keeps running; the port 8080 listener persists but pa-web-ui stops hitting it.
- **Before Unit 1.6 commit: smoke-test Telegram-via-LettaBot** continues working after removing pa-web-ui's dependence, specifically validating that LettaBot's session LRU doesn't evict Telegram's session on next idle tick without pa-web-ui's keep-alive.

**Patterns to follow:**
- Other services' `/health` and `/status` endpoints; pa-web-ui already has `/health`.
- Existing pa-web-ui module-level logger setup.

**Test scenarios:**
- Happy path: `GET /api/subprocess/status` returns empty list (no conversations active); after a message, contains one entry with expected fields.
- Edge case: SIGTERM during active streams → all subprocesses reaped; `docker compose logs pa-web-ui` shows clean shutdown.
- Error path: subprocess crashes (simulate via kill -9) → crash log created at expected path with stdout/stderr tail; registry removes the handle.
- Integration: `/api/subprocess/status` shows accurate state across a full message cycle.

**Verification:**
- After 7 days of Phase 1 flag-on operation, metrics show crash count within budget (< 1/day) with any crashes correlated to known events.
- `docker logs pa-web-ui` shows no references to `LETTABOT_API_URL` after Unit 1.6 cleanup.
- Telegram messaging via LettaBot continues to work (smoke-test a DM → MC replies) **before** the Unit 1.6 commit lands.
- Ingress-guard 403 rate on legitimate traffic is zero over the window.
- Ring-buffer `resync_required` emission rate is within budget (implies normal operation with occasional phone-offline resumes, not constant replay failure).

### Phase 2: Multi-conversation switcher + persistent fork UX (roadmap)

Execution-ready plan for Phase 2 will be written as `docs/plans/YYYY-MM-DD-002-feat-pa-web-ui-conversation-switcher-plan.md` when Phase 1 is stable. High-level unit sketches:

- **Unit 2.1: Letta fork API reference + schema migration.** Probe `POST /v1/conversations/{id}/fork`, document request/response in `docs/reference/letta-conversations-fork.md`. Add `conversation_id` column to `pa_web.conversations`, `pa_web.routing_signals`, `pa_web.thread_exchanges`, `pa_web.response_feedback`. Backfill with a default "main" conversation per existing session_id.
- **Unit 2.2: Conversation list + switcher UI.** Left rail on desktop, hamburger drawer on mobile. `GET /api/conversations` (Letta `conversations.list?agent_id=MC&order_by=last_message_at`). Create / rename / soft-delete actions.
- **Unit 2.3: Per-message "Fork from here" action.** Menu on every assistant message; calls `POST /v1/conversations/{id}/fork?agent_id=MC`. Stores parent link in `pa_web.conversations`. Adds to switcher with parent indicator.
- **Unit 2.4: Conversation-history rehydration on switch.** `loadConversationHistory()` takes `conversation_id` parameter; frontend's `pa_chat_session_id` becomes `pa_chat_device_id`; conversation_id separately tracked in URL.

Phase 2 success criterion (from origin doc): switcher lists MC's conversations, create/rename/soft-delete work, forks show parent link, two browsers on the same conversation see identical live stream with no desync.

### Phase 3: `/btw` ephemeral BtwPane UX (roadmap)

Plan file `docs/plans/YYYY-MM-DD-003-feat-pa-web-ui-btw-pane-plan.md` when Phase 2 is stable. High-level units:

- **Unit 3.1: `/btw` dispatch verification + implementation.** Test whether sending `/btw X` over stream-json invokes letta-code's slash-command dispatcher. If yes: minimal backend work; BtwPane receives events by subscribing to the fork's subprocess. If no: backend intercepts `/btw` → calls `conversations.fork` → spawns ephemeral subprocess → streams to BtwPane. Answer drives implementation scope.
- **Unit 3.2: BtwPane frontend component.** Right drawer on desktop (~35% width), bottom sheet on mobile (drag-to-dismiss). `[esc]` / `[j]` keyboard handlers.
- **Unit 3.3: Promotion flow + 7-day soft-delete.** `[j] Keep & Switch` adds the fork to the conversation switcher. Dismissed forks auto-delete after 7 days via a daily cron.

Phase 3 success criterion: `/btw question` in chat opens BtwPane with streaming response while main chat remains interactive. Promotion puts the fork in the switcher. Dismissed forks don't accumulate.

### Phase 4: PWA mobile polish + observability (roadmap)

Plan file `docs/plans/YYYY-MM-DD-004-feat-pa-web-ui-pwa-polish-plan.md`. High-level units:

- **Unit 4.1: PWA manifest + responsive CSS + local static deps.** `manifest.json`, icons, theme color. Mobile layout (switcher as drawer, BtwPane as bottom sheet, touch hit targets). Move `marked.js` + `sortablejs` from CDN to local static.
- **Unit 4.2: Service worker (offline-read + queued-send).** Cache static assets; cache recent conversation history for offline read; queue send attempts when offline; flush on reconnect.
- **Unit 4.3: Mobile-specific threat-model addendum.** The Phase-1 `docs/security/pa-web-ui-threat-model.md` already articulates the single-user model and ingress posture. Phase 4 adds a PWA-specific addendum covering service-worker attack surface, cached-response exposure on lost-device scenarios, and iOS home-screen install revocation story.

Phase 4 success criterion: PWA installable on iOS + Android. Phone resuming live stream from desktop-in-progress response. Conversation switcher accessible on mobile.

## System-Wide Impact

- **Interaction graph:**
  - pa-web-ui gains a long-lived subprocess pool; gains a curated bind mount at `/workspace-safe` (NOT the repo root); gains a host-side bind mount of `~/.letta/agents/` for memfs.
  - LettaBot HTTP API port 8080 loses its one real consumer (pa-web-ui). Still serves its Telegram adapter role internally.
  - Slackbot / scheduling-orchestrator-api / slack-mcp-server lose their vestigial `LETTABOT_API_KEY` env vars.
  - Letta server sees many more concurrent conversations and fork calls in Phase 2+; current 0.16.7 verified stable under this load.
  - Frontend chat.js's event handlers are unchanged in Phase 1 aside from two new handlers: `turn_locked` (R7c) and `resync_required` (R7b); Phase 2 adds conversation switcher logic; Phase 3 adds BtwPane.
- **Security surface (new in Phase 1):**
  - **HTTP ingress gate**: Phase 1 adds an app-layer guard (Origin allowlist + CSRF double-submit + Host-header allowlist) on `/stream`, `/api/subprocess/status`, and any state-changing route. Tailscale remains the network perimeter; the guard prevents a non-Tailnet browser tab from CSRF-exploiting `--yolo` Bash via a subprocess.
  - **Curated bind mount**: `/workspace-safe` excludes `.env`, `smaug-data/.state/`, `*credentials*.json`, `.granola-tokens.json`, `pa-web-ui/letta-credentials/`, and other secret-bearing paths (full inventory in `docs/security/pa-web-ui-threat-model.md`). Skills directories and `.letta/` config remain accessible.
  - **Explicit subprocess env dict**: `subprocess.Popen(env=...)` passes only `LETTA_BASE_URL`, `PATH`, `HOME`; `.env`-derived secrets (DB passwords, OPENAI_API_KEY, SLACK_BOT_TOKEN, etc.) are NOT in the subprocess's environment. Combined with the curated mount, a prompt-injection cannot reach secrets via `os.environ` or `cat .env`.
  - **`.lettaignore`** at `/workspace-safe/` root as a second line of defense against Read/Edit/Write/Glob paths the subprocess might discover.
  - **Crash-log redaction**: stdout/stderr tails run through a regex scrubber (Slack/Bearer/hex/email/API-key patterns + `.env` value deny-set) before hitting disk.
- **Error propagation:** Subprocess errors surface as SSE `error` events; client renders as error card (existing behavior). Pool-level errors (spawn failure, eviction collision) are logged + surfaced as SSE errors rather than HTTP 500. Client-side retries are explicitly disabled to prevent duplicate-subprocess creation during cold-start. Concurrent-send attempts return HTTP 409 + `turn_locked` (R7c) — these are not errors, but the client treats them as a flow-control signal with override UI.
- **State lifecycle risks:**
  - Memfs persistence is via bind-mount of host `~/.letta/agents/`; the host's directory is the source of truth. `docker compose down` does not wipe it; only `rm -rf ~/.letta/agents/` on the host does.
  - Ring buffer is in-memory (per-conv, ~2 MB byte-bounded with turn-boundary integrity); restart loses replay history for currently-open streams. Acceptable under R7b — clients see `resync_required` and refetch via `loadConversationHistory()`.
  - Per-conv lock + creation-lock + in-flight flag + generation counter prevent races but require rigorous exception handling — any unhandled exception in the spawn path must release locks AND bump the generation so next `ensure()` respawns cleanly.
  - Subprocess zombies: SIGTERM handler is the last line of defense; worst-case, container restart reaps everything.
- **API surface parity:**
  - `/stream` continues to serve coordination (`/mprep`) and slash-routed paths (`/calendar`, etc.) unchanged — these do NOT go through the subprocess pool. Feature-flag dispatch in `stream()` routes only the Mission Control default path to the subprocess pool when `PA_WEB_UI_PHASE_1_ENABLED=true`.
  - Task Review Sidebar's 8 routes unchanged (pass through ingress_guard but otherwise untouched).
  - New `/api/subprocess/status` endpoint for observability, gated by the ingress guard to prevent Tailnet-visible conversation-id enumeration.
  - New CSRF-token emission endpoint (small — a single GET returning the current session's token).
- **Integration coverage:** Multiple cross-layer scenarios that unit tests won't catch — send a real message, verify SSE reaches both tabs, verify memfs survives container restart, verify SIGTERM shuts down cleanly, verify subprocess env is scrubbed, verify a non-Tailnet Origin is rejected, verify concurrent-send turn-lock. Plan includes these as integration test scenarios in each unit.

## Risk Analysis & Mitigation

- **Risk: Subprocess pool bugs wedge the web UI for all users.** Mitigation: feature flag `PA_WEB_UI_PHASE_1_ENABLED=false` → instant rollback to LettaBot path. Keep old `stream_mission_control()` code intact through end of Phase 1. Don't remove until 7 days of stable flag-on operation with a named crash/error budget (see Operational Notes).
- **Risk: Control-protocol gap causes hung turns.** If the subprocess emits `control_request` (approval / recover_pending_approvals / etc.) and the backend never responds, the turn hangs indefinitely and the user sees only a spinner. Mitigation: Unit 1.2 implements the full control-response path with `--yolo` semantics (auto-approve non-INTERACTIVE tools, deny INTERACTIVE tools which are already in `--disallowedTools`). Unit 1.3 tests explicitly exercise a control_request scenario. Unknown subtypes get a generic denial + warning log rather than silence.
- **Risk: tool_call arg merging diverges from upstream behavior for some model.** Mitigation: port LettaBot's exact `mergeToolArgs` algorithm **with the semantic-boundary flush rule** (not every `stream_event`). Add fixture-based tests for both delta and cumulative modes. Monitor `/api/subprocess/status` for event-shape anomalies.
- **Risk: Concurrent sends from two devices corrupt a turn.** Mitigation: R7c turn lock — `handle.in_flight` gate in `send()`; second sender receives `TurnLockedException` → HTTP 409 + `turn_locked` SSE event. UI on second device surfaces banner with override option. Integration test in Unit 1.2 exercises this.
- **Risk: Secret exfiltration via prompt injection.** An injected prompt could ask the subprocess to `cat .env`, `echo $POSTGRES_PASSWORD`, or `Read /app/pa-web-ui/letta-credentials/...`. Mitigation: **defense in depth** — (1) R30's explicit `env=` dict scrubs all `.env`-sourced vars from the subprocess; (2) R3's curated bind mount at `/workspace-safe` excludes credential paths at the filesystem level; (3) `.lettaignore` adds a letta-code-level exclusion for `@file` and discovered paths; (4) Unit 1.0's threat-model doc pins the carve-out inventory against drift. Ensures any one mitigation failing is caught by the others.
- **Risk: CSRF exploit of `/stream` from a non-Tailnet browser tab.** Mitigation: R29 — Origin allowlist + CSRF double-submit + Host allowlist in ingress_guard middleware. Runs before route dispatch on `/stream`, `/api/subprocess/status`, and any state-changing route. Unit 1.0 integration tests cover happy path + missing Origin + mismatched CSRF + bad Host.
- **Risk: Ring-buffer exhaustion under tool-heavy turns drops replay.** Old plan's fixed 500-event buffer insufficient for realistic PA sessions (Bash outputs can exceed that in a single turn). Mitigation: R7b — byte-bounded (~2 MB) + turn-boundary-preserving ring buffer. Below floor, client receives `resync_required` and refetches via `loadConversationHistory()`; no silent event loss.
- **Risk: Cold-start latency breaks UX on first message.** Mitigation: pre-warm the MC `default` conversation subprocess at pa-web-ui startup (one process, cheap). User never sees cold-start for the common conversation. Measure during Phase 1 testing; add pre-warm logic to Unit 1.6 if needed. Target: cold-start ≤ 10 s, warm-start ≤ 500 ms.
- **Risk: Memfs bind-mount drift if host `~/.letta/agents/` is touched by another tool.** LettaBot's subprocess also reads/writes this path. Mitigation: by design — same agent, same memory. Document that any agent-memory manipulation tool (memory-block edits, archival rebuild) needs a coordinated session across both LettaBot and pa-web-ui consumers, not just one.
- **Risk: Letta upgrade silently breaks fork API.** Mitigation: Phase 2 starts with a smoke-test that runs `conversations.fork` against a known conversation. If it fails, Phase 2 aborts and the upgrade-migration procedure kicks in (see `memory/project_letta_upgrade_migration.md`).
- **Risk: Image bloat from adding Node.** Mitigation: multi-stage Dockerfile; document expected size delta (+200–300 MB). Acceptable for a self-hosted single-user PA.
- **Risk: Flask dev server in production is discouraged.** Not a regression — pa-web-ui has always used Flask dev server. Phase 4 can consider Gunicorn if needed; out of scope here.
- **Risk: Shared-consumer semantics on `default` conversation surprise the user.** Phase 1 routes pa-web-ui and LettaBot's Telegram subprocess to the same MC `default` conversation; Telegram and web UI will see each other's messages. Mitigation: document in the operational notes + threat model. Phase 2 introduces per-conversation UUIDs that separate the two surfaces cleanly.

## Phased Delivery

### Phase 1 (this plan)
Units 1.1 through 1.6. Ships: direct subprocess backend, SSE fanout with seq_id resume, rich event rendering, observability, LettaBot HTTP API retirement. Rollback: feature flag off.

### Phase 2 (future plan)
Units 2.1 through 2.4. Ships: conversation switcher, persistent fork UX, multi-device same-conversation sync. Rollback: revert switcher feature flag; existing default-MC behavior remains.

### Phase 3 (future plan)
Units 3.1 through 3.3. Ships: `/btw` BtwPane ephemeral side-query UX. Rollback: /btw slash-command interception disabled; user sees same pre-Phase-3 UX.

### Phase 4 (future plan)
Units 4.1 through 4.3. Ships: PWA manifest, service worker, mobile layout, local static assets, threat-model doc. Rollback: manifest link tag removed; app reverts to non-PWA browser page.

## Documentation / Operational Notes

- **Docs to write / update:**
  - `docs/security/pa-web-ui-threat-model.md` — **Phase 1 prereq** (Unit 1.0 deliverable). Single-user PA threat model; curated bind-mount carve-out inventory; R30 env-scrub rationale; R29 ingress-guard rationale; incident-response playbook (kill pool, wipe memfs, revoke Tailnet device). Living document — updated when exclusion list or allowed-origin list changes. (Moved from Phase 4; deferring it meant shipping the exposure three phases before its mitigation.)
  - `docs/reference/letta-conversations-fork.md` — Phase 2 prereq; captures fork API shape empirically.
  - `pa-web-ui/README.md` — document the new subprocess pool architecture; pointer to LettaBot session-manager as reference; note the curated bind mount + env-scrub posture.
  - Update `CLAUDE.md` — note that pa-web-ui now spawns its own letta-code subprocesses; don't assume LettaBot is the chat backend; reference the threat-model doc.
  - Update `MEMORY.md` — record the architectural shift so future sessions know pa-web-ui has its own subprocess pool and that `/workspace-safe` is the cwd (not the repo root).
- **Operational notes:**
  - Feature flag `PA_WEB_UI_PHASE_1_ENABLED` is the single rollback switch for the dispatch path; document in deployment runbook.
  - `PA_WEB_UI_ALLOWED_ORIGINS` env var controls the ingress-guard Origin allowlist; document in deployment runbook with the Tailscale MagicDNS name(s).
  - `/api/subprocess/status` is new and gated by the ingress guard; add to health-check dashboards if used (dashboard must present a valid Origin or the request will 403).
  - SIGTERM handling adds a few seconds to graceful shutdown; set `docker compose stop --timeout 30` (or adjust).
  - Memfs bind-mount: host `~/.letta/agents/` → container `/root/.letta/agents/`. Host path is the source of truth and is already in the existing backup scope. `docker compose down` does NOT wipe it.
  - Crash log path: container `/app/logs/` bind-mounted to host `~/Library/Logs/pa-web-ui/`. Rotation: one file per crash window, last 20 per conversation.
  - First Phase 1 deploy: flag OFF. Enable via redeploy after smoke-test in a quiet window. Observe for 7 days against the named crash/error budget. Then retire LettaBot path code (Unit 1.6 second commit).
- **Rollout sequence:**
  1. Ship Unit 1.0 (threat model + ingress guard + `.lettaignore`). Runs at all flag states — tightens the HTTP perimeter even on the pre-migration LettaBot-backed code path.
  2. Ship Units 1.1–1.5 behind flag `PA_WEB_UI_PHASE_1_ENABLED`, flag OFF in production.
  3. Enable flag in a low-traffic window, send test messages including one that exercises a Bash tool (to validate the control-protocol path), verify rich event rendering and multi-tab parity.
  4. Monitor `/api/subprocess/status`, crash log directory, memory/CPU on pa-web-ui, and — crucially — that LettaBot's Telegram path remains unaffected.
  5. **Crash/error budget for the 7-day window**: < 1 subprocess crash per day, zero user-reported chat regressions, Letta-server round-trip latency within 10% of pre-migration baseline, zero instances of stream event loss (observed via client-side `resync_required` frequency), zero ingress-guard 403s from legitimate clients. A breach of any threshold pauses the clock and either fixes-forward or flags OFF for debug.
  6. If clean for 7 days, ship Unit 1.6 (remove old path + env vars + run Telegram smoke-test). If issues, flag OFF, debug, re-try the 7-day window from day zero.

## Sources & References

- **Origin document:** `docs/brainstorms/2026-04-20-pa-web-ui-letta-code-migration-requirements.md`
- **Related code (target):**
  - `pa-web-ui/app.py` — 3397 lines, the migration target
  - `pa-web-ui/static/js/chat.js` — 1402 lines, existing rich-event handlers
  - `pa-web-ui/static/js/sidebar.js` — decoupled Task Review Sidebar, unchanged
  - `pa-web-ui/Dockerfile`, `pa-web-ui/requirements.txt`
- **Related code (reference):**
  - `lettabot/src/core/session-manager.ts` — canonical subprocess pool pattern
  - `lettabot/node_modules/@letta-ai/letta-code-sdk/dist/index.js` — CLI arg + stream-json protocol reference
  - `lettabot/src/api/server.ts:558` and `lettabot/src/api/openai-compat.ts` — what we're moving off of
- **Related plans/docs:**
  - `docs/debugging/sse_streaming_issue_analysis.md` — prior SSE failure modes
  - `docs/plans/2026-01-25-letta-conversations-scheduler-pilot.md` — conversations isolate context, not memory
  - `memory/project_letta_upgrade_migration.md` — upgrade procedures + fork API smoke-test recipe
  - `memory/feedback_todowrite_blocked.md` — TodoWrite must stay disallowed
  - `memory/MEMORY.md` — general Letta API gotchas
- **External references:**
  - Letta Code PRs #1539 (fork subagent type) and #1596 (/btw BtwPane) at `letta-ai/letta-code` — design intent reference
  - `https://docs.letta.com/letta-code/subagents/` — subagent types including `fork`
  - Letta OSS UI (`letta-ai/letta-oss-ui`) — track patterns for event rendering and keyboard vocabulary; do not clone
- **Upstream issues tracked:**
  - `letta-ai/letta#3205` — Task subagent approval bug; blocks R4 relaxation until resolved
  - Future: `/v1/environments/register` support on self-hosted — unblocks eventual Letta Code Channels adoption + full LettaBot retirement
