---
title: "Unit 1 — Interactive /ws verification spike: findings"
date: 2026-08-12
status: complete (Sections A–F; minor build-time confirmations noted)
plan: docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
---

# Unit 1 Spike Findings (go/no-go)

## OVERALL VERDICT: **GO for M1** — and the full-picture probes make the fast-follows MORE feasible, not less

The M1 continuity core is **validated on the live Letta 0.30.19 App Server** (Sections C): multi-client subscribe+inject+observe works, observer renders the injector's turn, observer is not a writer (R1-safe), concurrent sends are **server-queue-serialized** (no client lock needed), long turns stream with no stall (two samples), and a bare health-ping stays responsive during a turn (forward-progress liveness required). **No kill-shot.**

The deferred "full picture" probes (Sections D–F) **net FAVORABLE**:
- The App Server serves **no native Letta REST in any mode** (D) — but that doesn't matter, because the **WS protocol is a complete runtime + management API** (E): full conversation CRUD (`conversation_create/list/update/fork/…`, empirically confirmed) and full approvals (`approval_request_message`/`approval_send`) all ride `/ws`. So the **rail (R6) is buildable entirely on WS** (no CLI/filesystem hacks), the **approval path is protocol-supported**, and **R3 is a small WS-inject adapter** — all funneled through the one sole-owner server (single-writer preserved for free).
- **Transport decision resolved:** client-core is **raw-WS-primary** (the SDK covers only runtime/session/stream, not conversation CRUD / approvals / subagent-state — all of which the full client needs). Raw WS is one ordered protocol (`event_seq`), no observer-API gap, no pre-1.0 churn.
- Stall not reproduced on the local model in two long-turn samples (risk downgraded; watchdog stays).

**Net plan changes:** drop the flock-fallback (server serializes); keep the forward-progress watchdog; **client-core = raw-WS-primary**; **rail/approvals/R3 are WS-protocol features, not a re-architecture**; sole owner runs **with `--openai-api`** (keeps enrichment `/v1/responses`; WS coexists). The architecture is *cleaner* than the plan assumed: one WS protocol for runtime + management + approvals.

**Environment:** live home server, `letta 0.30.19 (Letta Code)`. The enrichment App Server (`letta server --backend local --openai-api`) is **already running on `ws://127.0.0.1:4577`** (booted by `letta-push-receiver`), so probes run against it — no second server started (a second `letta server` on `lc-local-backend` would be a 5th writer).

## Section A — Reconnaissance (read-only, DONE)

### A1. Live multi-writer state on `lc-local-backend` — CONFIRMED (4 writers)
The pre-existing race the plan describes is live right now:
- enrichment App Server `letta server --backend local` on **:4577** (PID 4093 at probe time)
- an interactive `letta --backend local --agent …` session (PID 97372)
- `letta-local-runner` on **:8920** (PID 1036, `com.ai-pa.letta-local-runner`)
- Letta **Desktop app** (PID 1002) — cron-lease holder

→ Confirms the plan's premise; and the sole-owner cutover (Unit 8) must quiesce all four. The already-running App Server is the one to probe against.

### A2. Agent-initiated turns' REAL source = `scheduler-service`, NOT the letta cron
- The letta-code cron (`crons.json` / Desktop lease) is **empty** (user-confirmed) → the cron-lease "go/no-go" is a red herring for R3's payoff.
- `scheduler-service` (:8087) + `scheduler-mcp` (:8088) are **up, healthy (36h)**. On job fire, `scheduler-service/src/scheduler_service/services/actions.py:393` **POSTs `{"messages":[{role,content}]}` to `LETTA_CALLBACK_URL` = `http://letta:8283/v1/agents/{agent_id}/messages`** → into the **Docker Letta**.
- So `scheduler-service` is a REST turn-**initiator**, NOT an `lc-local-backend` filesystem writer (does not threaten single-writer).
- **R3 implication:** the "10:55 fix" reduces to **re-pointing `LETTA_CALLBACK_URL` at the sole-owner + mapping job `agent_id`s Docker→local** — a config change, not a cron-lease fight. **BUT see B2:** the target endpoint (`/v1/agents/{id}/messages`) does not exist on the `--openai-api` App Server, so the re-point path is not as simple as swapping the host.

## Section B — App Server surface (read-only, DONE)

### B1. `/v1/models` — the local fleet is exposed by friendly name
`Mission Control (local)`, `calendar-agent_copy-local`, `pulse-monitor-agent-local`, `tasks-agent-local`, `docs-and-transcripts-agent-local`, `email-agent-local`. (OpenAI-route model id = friendly agent name, per prior memory.)

### B2. The `--openai-api` App Server is OpenAI-compat ONLY — no native Letta REST
Route-existence probe (POST=400/422 = route exists; 404/404 = absent):

| Route | GET | POST | Verdict |
|---|---|---|---|
| `/v1/models` | 200 | 404 | exists (GET) |
| `/v1/responses` | 404 | 400 | **exists** |
| `/v1/chat/completions` | 404 | 400 | **exists** |
| `/v1/agents/` | 404 | 404 | **absent** |
| `/v1/conversations/` | 404 | 404 | **absent** |
| `/v1/agents/{id}/messages` | 404 | 404 | **absent** |
| `/v1/messages` | 404 | 404 | **absent** |
| `/health`, `/v1/health` | 404 | — | absent |

**Plan-shaping consequences:**
1. **Rail CRUD (R6 fast-follow)** cannot use App Server REST — no `/v1/conversations/*`. Conversation create/rename/fork/delete must come from the **WS runtime protocol** (if it supports management — UNPROBED) or the letta-code **CLI** (which writes `lc-local-backend` directly = a *second writer*, conflicting with sole-ownership). This is an open architectural gap for the rail.
2. **R3 scheduler re-point** cannot POST to `/v1/agents/{id}/messages` on this server — absent. Delivery would need WS-inject (complex for a simple HTTP scheduler) or `/v1/responses` (stateless fresh-conv = wrong for continuity). Or a server-mode change.
3. **Core question raised:** can ONE `letta server` serve BOTH the OpenAI surface (enrichment `/v1/responses`) AND native Letta REST (rail + R3)? `--openai-api` appears to *replace* the native REST surface. Needs a probe of `letta server --backend local` **without** `--openai-api` (does it serve native REST + `/ws`? can both coexist?) — which requires carefully starting a server (a writer) and is gated on user go-ahead.
4. **M1 core is NOT blocked by this:** M1 uses a single fixed conversation over `/ws`; `default` auto-creates on first inject (per prior spike), so M1 needs no conversation CRUD. The gaps above hit the *fast-follows* (rail, R3), not the M1 continuity proof.

## Section C — WS continuity + gating probes (DONE — live injection on docs agent / `default`)

Run against the existing `:4577` server, targeting the low-stakes **docs** agent (`agent-local-3898b33a…`) on its `default` conversation (a handful of benign no-tool turns — the only side effect; harmless utility-agent thread pollution). Protocol confirmed identical to the origin spike.

### Protocol shape (captured on this server)
`runtime_start {request_id, agent_id, conversation_id}` → `runtime_start_response`; `input {runtime, payload.kind:"create_message"}`; server broadcasts `update_device_status` / `update_loop_status` / `update_queue` / `update_subagent_state` / `stream_delta` / `turn_finished`. **`turn_finished` carries `event_seq` (per-connection server sequence — the ordered-merge key the review wanted), `run_id`, `idempotency_key`, `runtime{agent_id,conversation_id}`.** `update_subagent_state` **is** emitted on normal turns (raw-WS side-channel is available). **Conversation gotcha reconfirmed:** an arbitrary conversation name does NOT auto-create (inject → `turn_finished` with zero deltas); only `default` auto-creates.

### Gate results
- ✅ **[R5 core] Observer renders injector's turn — PASS.** Two clients `runtime_start` on the same `{agent, conversation}`; A injects, **B (pure observer, never injects) received all 19 `stream_delta` + `turn_finished`, same `run_id` (local-run-118)**. The continuity primitive works on this server.
- ✅ **[R1] Read-only observer is NOT a writer — PASS.** B observes without injecting and without blocking A's turn; the submit queue is keyed by `client_message_id` of actual submits, so a pure observer adds nothing. An observer connection is benign for single-writer.
- ✅ **[R5 arbitration] Concurrent send — RESOLVED FAVORABLY (server queue-serializes).** Two clients injected distinct prompts simultaneously → **two distinct runs (local-run-120, -121)**, and `update_queue` showed a message **queued (`q-1`) then removed/processed** — i.e. the server serializes concurrent sends through a per-`{agent,conversation}` queue, one active turn at a time. **Neither interleave (chaos) nor drop.** ⇒ the client-core needs **no shared cross-client lock for correctness**; the plan's "flock fallback if interleave" branch is **unnecessary** (server handles it). Optional client UX only ("queued behind another turn").
- ✅ **[Stall] Long turn — NO STALL observed.** 250-word prompt → **397 `stream_delta`, clean `turn_finished` at 7.4s** (first delta 3.7s). *Caveat:* the #99 stall is intermittent/length+model-sensitive; one clean sample on `deepseek-v4-flash` cannot rule it out — the watchdog stays load-bearing and the sidecar-re-home decision stays open pending longer observation on heavier models.
- ✅ **[Watchdog liveness, review #12] CONFIRMED empirically.** A bare `GET /v1/models` ping stayed **2–11 ms during the live streaming turn** → a bare endpoint ping would NOT detect a stall. Validates the plan's **forward-progress** liveness design (stream-delta/`loop_status` advancement), not a bare ping.

## Section D — Server-mode probe on a CLONED backend (DONE 2026-08-12)

Cloned `lc-local-backend` (agents/providers/memfs, empty conversations, 26M) to `/private/tmp/lc-clone-probe`; started a **non-`--openai-api`** `letta server --backend local --listen ws://127.0.0.1:4599` against the clone (single-writer preserved — never touched the live backend; enrichment stayed on :4577). Torn down after (server killed, clone removed).

### D1. The letta-code App Server NEVER serves native Letta REST — in EITHER mode
| Route | `--openai-api` (:4577) | non-`--openai-api` (:4599 clone) |
|---|---|---|
| `/v1/models` | 200 | **404** |
| `/v1/responses`, `/v1/chat/completions` | exists (400 on bad body) | **404** |
| `/v1/agents`, `/v1/conversations`, `/v1/agents/{id}/messages` | 404 | **404** |
| `/ws` | works | **works** (runtime_start_response OK) |

**So:** `--openai-api` ADDS the OpenAI shim (`/v1/models`, `/v1/responses`, `/v1/chat/completions`); **without it there is NO HTTP surface at all, only `/ws`.** Native Letta REST (agents/conversations/messages CRUD) is a property of the **full Docker Letta (Python framework)**, NOT the letta-code local App Server, in any mode.

### D2. Consequences (fast-follows; M1 unaffected)
- **Sole-owner runs WITH `--openai-api`** — it's the only way to keep enrichment's `/v1/responses`, and `/ws` coexists. Native REST is simply never on the table.
- **Rail conversation CRUD (R6) cannot be REST.** Create/rename/fork/delete must go through either the **WS runtime protocol** (does it expose conversation-lifecycle commands? — STILL UNPROBED, a deeper rail investigation) or the **letta-code CLI / filesystem** (`--new` writes `lc-local-backend/conversations/` — a *writer*, so it must be funneled through the sole owner to preserve single-writer) + out-of-band `conversation_meta`. The pa-web-ui rail was built on Docker Letta's `/v1/conversations/*` REST, which **does not exist** on the local App Server — so the rail is a genuine re-architecture, not a re-point.
- **R3 delivery (scheduler-service) = a WS-inject adapter, not a REST re-point.** `scheduler-service` POSTs to `/v1/agents/{id}/messages` today; that endpoint doesn't exist on the App Server, so agent-initiated turns into the continuity conversation must be delivered via the **WS protocol** (`runtime_start`+`input`) — scheduler-service needs a small WS injector or a REST→WS bridge helper.

## Section E — WS protocol richness (DONE 2026-08-12) — REVERSES the rail concern

Read the WS message vocabulary from the installed letta-code bundle (`/opt/homebrew/lib/node_modules/@letta-ai/letta-code/letta.js`, 35M) and **empirically confirmed** against the live `:4577` server.

### E1. The WS protocol is a FULL conversation-management + approval API (not just runtime)
Message types present in the client (each with a paired `_response`):
- **Conversation CRUD:** `conversation_create`, `conversation_list`, `conversation_retrieve`, `conversation_update` (rename + `archived` flag = delete), `conversation_fork`, `conversation_compact`, `conversation_recompile`, `conversation_messages_list`, `conversation_open`/`conversation_close`, `switch_conversation`, `conversation_search`, `conversation_titles`.
- **Approvals:** `approval_request_message`, `approval_pending`(`_at_stream_end`), `approval_send`, `approval_response`(`_message`), `approval_preview`, `approval_result`, `approval_recovery`, `approval_cancel`, `approval_boundary`.
- **Runtime (already seen):** `runtime_start`, `input`/`create_message`, `stream_delta`, `update_loop_status`, `update_queue`, `update_subagent_state`, `turn_finished`.

**Empirical confirmation:** `{"type":"conversation_list","request_id":"cl1","agent_id":AG}` → `{"type":"conversation_list_response","success":true,"conversations":[…20…]}`, each `{id, agent_id, archived, archived_at, created_at, updated_at}`. Clean request/response RPC over `/ws`. (Delete = archive via `conversation_update`; no separate delete op.)

### E2. Consequences — the fast-follows are MUCH better than Section D implied
- **The rail (R6) is buildable ENTIRELY on `/ws`** — full conversation CRUD is a WS-client feature, empirically working. This **reverses** the Section-D worry ("rail is a re-architecture / CLI-filesystem hacks"). No native REST needed; no CLI/filesystem writes needed; the WS protocol *is* the management API, funneled through the one sole-owner server (single-writer preserved for free).
- **Approval path (feasibility finding #4) is protocol-supported** — `approval_request_message` is a broadcast frame (like `stream_delta`), so it reaches observers; `approval_send`/`approval_response` resolves it. Cross-surface approval is feasible over raw WS (the SDK just doesn't surface it).
- **R3 delivery (scheduler-service)** = a small WS-inject adapter (`conversation` targeting + `input`), mechanism confirmed present.
- **Transport reframe (strengthens adversarial finding #13):** the SDK (`@letta-ai/letta-agent-sdk`) covers only runtime/session/stream; it does NOT cover conversation CRUD, approvals, or `update_subagent_state` — all of which a full client (rail + approvals + subagent panels) needs, and all of which **raw WS covers uniformly**. So the client-core is better built **raw-WS-primary** (one protocol for runtime + management + approvals), with the SDK optional convenience for the basic chat path — not "SDK primary + thin side-channel."

### E3. Terminal client (finding #9) — stock-TUI-attach is architecturally viable
`letta server --listen` = App Server mode (the sole-owner). The Desktop app's `letta remote --env-name` is the *cloud-environment* client mode (different). A letta-code/SDK client on the `remote` backend attaches to a local App Server and — since observers receive broadcasts (Section C) — **receives external turns** (the old "TUI can't receive external turns" was the standalone `--backend local` TUI). Exact stock-TUI attach flag to confirm at Unit 5 build; greenfield REPL is the fallback, not the default.

## Section F — Heavier-turn stall (DONE 2026-08-12)
600-word prompt on docs (`deepseek-v4-flash`): **835 deltas, max inter-delta gap 0.45s, clean `turn_finished` at 10.7s — no stall.** Two long-turn samples now clean. The #99 stall is not reproduced on the local model; historical occurrences were `chatgpt_oauth`/`Kimi`. **Verdict:** stall risk downgraded (not reproduced on the local fleet's models) but not eliminated (intermittent) → the forward-progress watchdog stays load-bearing; the `letta-bg-fix-sidecar` re-home is likely unnecessary but kept as an option pending longer production observation.

### Still-deferred (low priority, confirm at build time)
- [ ] Exact stock-TUI attach flag/env for the App Server (Unit 5)
- [ ] Live approval round-trip end-to-end (protocol confirmed present; exercise during rail/approval build)
- [ ] Longer-horizon (days) constant-on stability + occasional-stall watch (production observation)

## Interim verdicts
- **Foundation still plausible for M1** (`/ws` present, server on 0.30.19, fleet exposed). No kill-shot yet.
- **New architectural constraint:** the sole-owner server's surface is OpenAI-only under `--openai-api`; native management REST is absent, which pushes rail + R3 onto WS-protocol or a server-mode decision — a fast-follow concern, not an M1 blocker, but it changes those later units.
- **R3 is cheaper *and* more constrained than the plan assumed:** source is a re-pointable REST scheduler (good), but its target endpoint isn't on the App Server (constraint).
