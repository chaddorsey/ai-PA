---
title: "feat: Multi-Surface Agent Continuity — Milestone 1 (web + terminal on one sole-owner App Server)"
type: feat
status: active
date: 2026-08-12
deepened: 2026-08-13
origin: docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md
---

# Multi-Surface Agent Continuity — Milestone 1 (web + terminal)

## Overview

Stand up **one launchd-supervised Letta App Server** as the sole owner of `~/.letta/lc-local-backend`, and build **two greenfield peer clients** — a text-first **terminal** client and a minimal **web** client — that both subscribe to the *same* live `{local MC agent, conversation}` on that server. Typing in one appears in the other; both render agent turns live. This proves **single-conversation cross-surface mirroring** and establishes the durable *runtime* foundation (single-writer server, watchdog supervision, reconnect/catch-up, clone-and-validate cutover) that later surfaces reuse. **It does not, by itself, validate the vision's hard problems** — relevance-routing, N-live-conversations, tiered cross-thread awareness, and cross-conversation arbitration (R12–R15) all remain unvalidated after M1 and must not be treated as de-risked by a passing single-conversation proof (see Scope Boundaries → "What M1 does NOT prove"). Nor does M1 fix the *motivating* problem — the detached scheduled turn (the "10:55 reminder"); that is R3, deferred and gated on the Unit 1 cron-lease go/no-go.

Both clients are **greenfield on `@letta-ai/letta-agent-sdk` (`remote` backend)** — *not* a port of pa-web-ui, whose subprocess pool and SSE transport exist only to work around the local-backend concurrency bug the App Server erases. pa-web-ui's genuinely good ideas (conversation rail UX + `conversation_meta` model, `ingress_guard` hardening, the task/follow-up sidebar) are borrowed as *design* and ported on their own timelines as fast-follows.

## Problem Frame

The PA agent is reachable only through fragmented, independent runtimes that don't share state (stock TUI, pa-web-ui subprocess pool, Desktop app). Nothing composes: TUI ergonomics vs. web features is an either/or; scheduled turns fire detached ("the 10:55 reminder that never appeared"); concurrent runtimes on one conversation cause a multi-writer race. The supported fix (validated by spike on Letta 0.30.19) is **one App Server owning the runtime/store, with many peer clients subscribed to a given `{agent_id, conversation_id}`**. See origin: `docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md`.

**Milestone 1 scope decisions (this plan):**
- Web client is **greenfield on the Agent SDK**, minimal chat (single conversation) — rail + task sidebar are fast-follows.
- Both clients attach to the **existing local MC** (`agent-local-*`) on `lc-local-backend`. The old pa-web-ui (Docker Letta, `agent-90b2e860`) keeps running in parallel during transition and is retired later; its Docker-MC history is archived/qmd-recallable, **not** live-migrated.
- **Agent-initiated turns (R3)** are a fast-follow gated on a cron-lease spike, not in this milestone.

## Requirements Trace

Milestone-1 requirements (from origin doc). IDs are the origin's, grouped by theme:

**Architecture & Ownership**
- **R1** — single App Server sole-owns the runtime/conversation store; no other process concurrently writes the same live backend. (Units 2, 3, 8)
- **R4** — multi-writer race eliminated as a consequence of R1. (Units 3, 8)
- **R19** — non-disruptive consolidation with **clone-and-validate** cutover + rollback. (Unit 8)
- **R20** — loopback-first auth: `/ws` binds loopback, no client auth. **M1 decision:** the web surface is **loopback/LAN-only** (reachable on-box or over the existing private network — Tailscale/SSH — with **no new public Cloudflare tunnel**); `ingress_guard` provides CSRF/rebind hardening, not authN. Remote public web + its real authentication are **explicitly deferred** to the rail milestone (R20's remote clause is *not yet satisfied* in M1; terminal covers remote use). (Units 2, 6)

**Runtime & Availability**
- **R2 / R2b** — runtime keeps agents/conversations continuously available; surfaces are peer clients subscribed to a live `{agent, conversation}`; a turn on one renders on all. (Units 2, 4, 5, 6, 7)
- **R16** — supervised sole owner with **stall-catching watchdog** (not just crash-restart). (Units 2, 3)

**Client Surfaces**
- **R5** — web + terminal both subscribe to the *same* live conversation; typing in one appears in the other; both see agent turns live. **(primary success criterion — Unit 7)**
- **R7** — terminal client is a text-first lightweight attach point re-platformed onto the client protocol. (Unit 5)
- **R17** — client-visible "reconnecting…" state + catch-up on reconnect. (Units 4, 7)

**Lifecycle**
- **R18** — bounded hot/cold/archive conversation lifecycle. (Unit 8, partial; thresholds + warm-on-attach deferred)

Carried forward but **deferred past milestone 1** (tracked, not built here): **R6** (full web rail rebuild + conversation_meta), **R3/R9** (agent-initiated turns + native notifications, needs cron-lease spike), **R8/R10/R11** (phone / ambient dashboard / Halo-Noa), and **R12–R15** hub-and-spoke routing behavior (relevance-routing, tiered awareness) which presuppose the rail + multiple conversations. Milestone 1 is single-conversation continuity; the routing model layers on afterward.

## Scope Boundaries

- **Web + terminal only.** No phone, notifications, dashboard, or glasses.
- **Single conversation** on the local MC. No rail (create/rename/fork/delete-undo) in this milestone — fast-follow.
- **No task/follow-up sidebar** in this milestone — separate port, fast-follow.
- **No agent-initiated/scheduled turns** — needs the cron-lease spike first (fast-follow).
- **No live migration** of pa-web-ui's Docker-MC conversation history — archived/recallable, not carried across.
- **No off-loopback client** — `/ws` stays loopback; `--ws-auth` deferred to phone/glasses.
- **No public web exposure** — the M1 web surface is loopback/LAN-only (Tailscale/SSH); no new Cloudflare tunnel and no edge authN until the rail milestone.
- **Not** the hub-and-spoke routing model (R12–R15) — that presupposes the rail and multiple concurrent conversations.
- **Legacy Docker `letta:8283`** (separate backend) is untouched and out of scope.

**What M1 does NOT prove (guard against false confidence — adversarial finding #6):** the single-conversation mirroring proof exercises *one* conversation's single-active-turn arbitration — a different problem from routing/arbitrating across *many* conversations × surfaces. These remain **unvalidated** after M1: relevance-routing + landing precedence (R13), tiered cross-thread awareness (R15), N-live-conversations-per-agent lifecycle (R18 full), and cross-conversation arbitration. The rail milestone must re-validate arbitration at multi-conversation scale; do not assume M1 settled it.

## Context & Research

### Relevant Code and Patterns

- **Sole-owner supervisor to promote:** `letta-push-receiver/src/letta_push_receiver/app_server.py` — `class AppServer` launches `letta server --backend local --listen <APP_SERVER_LISTEN> --openai-api`, readiness = stdout line matching **`"listening on ws://"`** (60 s bounded), `shutdown()` = terminate→wait(5)→kill, `base_url` rewrites `ws://`→`http://`. Reuse near-verbatim as the standalone service's supervised process; move lifecycle *out* of the receiver.
- **Env builder (reuse for both dispatch surfaces):** `letta-push-receiver/src/letta_push_receiver/warm_pool.py::build_runtime_env()` — produces `PATH/HOME/TERM`, **`LETTA_LOCAL_BACKEND_DIR=~/.letta/lc-local-backend`** (currently *hardcoded* at ~line 101 — must become env-overridable for clone-validation), host-reachable URLs, curated `.env` creds. The sole-owner launcher MUST use this exact env or interactive tool calls silently degrade (Docker-hostname trap).
- **Enrichment client to keep:** `app_server_client.py::AppServerClient.enrich()` (`POST /v1/responses`, stateless fresh conv per task; `SLUG_TO_MODEL`) — unchanged except `base_url` now comes from config (`PA_APP_SERVER_URL`), not an in-process `AppServer`. `server.py::create_app()` shrinks: drop the `AppServer()` construction/lifecycle; keep the client + a plain dispatch (the external launchd service owns lifecycle).
- **Local-fleet registry:** `letta-push-receiver/.../config.py::DEFAULT_AGENTS` (slug → `agent-local-*` id + `~/bin/letta-<slug>` wrapper). The terminal client and any subscriber routing reuse this — do not re-derive.
- **Fan-out / turn-lock prior art (design reference, not ported):** `pa-web-ui/subprocess_pool.py` — `Subscriber` + `SubprocessHandle.subscribe(since=<seq_id>)` (ring-buffer replay, `resync_required` on eviction, slow-subscriber drop) and the **turn lock with device identity** (`in_flight_device_id`, `TurnLockedException(conv_id, current_device_id, seq_id)`, `send(device_id=…)` from `pa_device_id` cookie). This is the existing "which surface owns the turn" mechanism — the concept the SDK's fragile multi-writer correlation needs; reuse the *pattern* (single-writer-at-a-time arbitration) in the client-core.
- **Web security to borrow:** `pa-web-ui/ingress_guard.py::configure_ingress_guard(app)` — host-allowlist + origin-allowlist + CSRF double-submit (HMAC of `pa_device_id`), exemptions for `/health`/`/static`. Transport-independent; reuse for the new web surface.
- **Rail data model (design ref for fast-follow):** `pa_web.conversation_meta` DDL in `pa-web-ui/app.py:300-335` (`conversation_id` PK, `agent_id`, `label`, `parent_conversation_id` fork link, `user_renamed` auto-name gate, `metadata JSONB`). No migrations dir — schema is idempotent in-app DDL.
- **Terminal wrappers today (to quiesce at cutover):** `~/bin/letta-<slug>` → `letta --backend local --agent <agent-local-id> --conversation default` — direct backend writers, not clients. `LETTA_LAUNCH_DIR=/Volumes/main-drive/letta-launchpad` is the cwd convention (avoids walking the huge repo tree).
- **launchd exemplars:** `~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist` (closest analog — inlines the full local-backend env, `KeepAlive{SuccessfulExit:false}`, `ProcessType Background`) and `com.ai-pa.letta-push-receiver.plist`. Wrapper pattern: `scripts/run-*.sh` (`set -euo pipefail`, export `LANG/LC_ALL`, full env, `exec`). Keep a **tracked reference copy** of the new plist under the package (like `letta-local-runner/launchd/…`) since plists are not git-tracked.
- **Cutover substrate:** `scripts/snapshot-local-mode.sh` (tars `lc-local-backend/{agents,providers,conversations}` core separately from `memfs`) and `deployment/scripts/backup.sh:572-625`. **Neither captures `~/.letta/crons.json`** — add it before any cutover that touches scheduling.
- **Cron lease:** `~/.letta/crons.json` — `scheduler_owner{pid:1002,...}` = Desktop app holds the lease; tasks carry `agent_id`/`conversation_id`/`cron`/`prompt`. No repo code references it; owned by the letta-code binary. (Fast-follow concern; snapshot coverage is the only M1 touch.)

### Institutional Learnings

- **Silent-stall (#99) is provider-agnostic and length/timing-sensitive**, living in the `stream_tokens:true` path. The `letta-bg-fix-sidecar` (rewrites `stream_tokens:true→false`) sits in front of **Docker `letta:8283`**, **not** the local App Server `/ws` path. The passing spike used a trivial "PONG" turn — too short to trigger the stall. **Must probe a long streamed `/ws` turn** and decide whether to re-home the sidecar in front of the App Server's HTTP surface or rely on the R16 watchdog. (`feedback_letta_silent_stall_global.md`)
- **Single-writer on `lc-local-backend` is a hard filesystem constraint** — two servers keep divergent in-memory conversation projections = the exact 10:55 race. Exactly one process may open the backend. (`project_local_memfs_gitea_sync.md`, origin Key Decisions)
- **Local-mode tools run on the HOST; Docker-internal hostnames fail silently** — the sole-owner launch env must be the full curated `build_runtime_env()` (host-reachable URLs + creds). (`feedback_local_runner_docker_hostnames.md`)
- **`message_buffer_autoclear: false` REQUIRED on memfs agents** or approvals break (PATCH before `/memfs enable`). Verify MC-local has it. (MEMORY.md)
- **launchd EX_CONFIG/78** — `StandardOutPath`/`StandardErrorPath` must live under `~/Library/Logs/…`, never `/Volumes/…`. Plists not git-tracked; never `git add -A`. (`feedback_launchd_exconfig_and_ipv6_fallback.md`)
- **`"default"` is not a server-side alias** — resolve the real conversation UUID via `GET /v1/conversations/?agent_id=<id>&order_by=last_message_at&limit=1`. Fork shares memory blocks; `parent_conversation_id` is tracked client-side, not server-side. (`docs/reference/letta-default-alias-resolution.md`, `letta-conversations-fork.md`)
- **hot/cold/archive substrate exists** — `qmd` over `~/.letta/history-archive/` is built and validated for history *recall*, but **warm-on-attach (COLD → live runtime rehydration) is a different, unproven mechanism** the archive pattern doesn't cover. (`project_plane2_history_archive.md`)
- **pa-web-ui deploy** — `app.py` image-baked, `static/` volume-mounted; real rebuilds (not just `docker cp`) for Python changes; `.dockerignore` guards the 44 GB context. (`project_pa_web_ui_deploy.md`)

### External References

- **`@letta-ai/letta-agent-sdk@0.7.1`** — evaluated and **NOT used as the client base** (see Key Decisions: raw-WS-primary). Retained here as the *reference for why*: it wraps only `runtime_start`/session/`stream()` (as `createSession`/`resumeSession`, `send()`, `listMessages()`, `abort()`, `recoverPendingApprovals()`, `createTranscriptAccumulator()`) and **does not cover** conversation CRUD, approvals, or `update_subagent_state` — all of which the full client + rail need and which raw WS covers uniformly on one ordered connection. (It also drops foreign `turn_finished` and doesn't auto-replay on reconnect.) May be revisited as optional convenience for the basic-chat path only. Docs: docs.letta.com/agent-sdk, github.com/letta-ai/letta-oss-ui.
- **Raw WS is the actual client contract** — the letta-code internal protocol (see Unit 1 findings Sections C/E for the empirically-confirmed frames: `runtime_start`→`runtime_start_response`, `input`/`create_message`, `conversation_*` RPCs, `approval_*`, `stream_delta`/`update_subagent_state`/`turn_finished` each with a per-connection `event_seq`). It is unversioned/undocumented (letta 0.30.19) — hence the protocol-coupling mitigations in Key Decisions.
- **Prior spike:** `docs/plans/2026-08-12-dispatch-surface-spike.md` — `--backend local` REQUIRED (else `--openai-api` hits cloud, fails on missing `LETTA_API_KEY`); OpenAI-route model id = friendly agent name (only relevant to `/v1/responses`).

## Key Technical Decisions

- **Both clients greenfield on a shared client-core; transport is RAW-WS-PRIMARY — decided by Unit 1 (adversarial finding #13, resolved).** pa-web-ui's transport is workaround baggage for a bug the App Server removes. Unit 1 (Section E) found the WS protocol is a *complete* runtime + management API (conversation CRUD, approvals, subagent-state, messages, runtime) — whereas the SDK (`@letta-ai/letta-agent-sdk`) covers **only** runtime/session/stream and drops conversation CRUD, approvals, and `update_subagent_state` (all of which the full client + rail need), plus pre-1.0 churn (24 versions/7 weeks). Therefore the client-core speaks **raw WS as its primary protocol** (one ordered connection, `event_seq` for ordering — no cross-stream merge, no observer-API gap, no version churn). The SDK is optional convenience for the basic chat path only, isolated behind the client-core and pinned if used. Raw WS was already proven end-to-end (Unit 1 Sections C/E).
- **Pin the `letta server` binary version alongside the SDK (feasibility finding #17).** The SDK↔server protocol is a two-sided contract; pinning only the SDK is half a pin. Record the validated `letta`/letta-code server version (spike was 0.30.19), assert it at launcher startup and in the plist reference, and re-run the Unit 1 compatibility probe on any server upgrade — treat SDK-version ⇄ server-version as one coupled dependency.
- **Protocol-coupling is the price of raw-WS-primary — mitigate it explicitly (architecture review).** Raw-WS-primary trades the SDK's *discoverable-but-incomplete* versioned contract for the WS protocol's *complete-but-undiscoverable* one: the wire frames are letta-code's **internal, unversioned, undocumented** IPC (reverse-engineered from a 35 MB `letta.js`, which shipped 24 versions in 7 weeks), so a routine binary bump can rename a field with **no build-time failure — only runtime mis-parse**, and enrichment shares the same server. Mitigations, all required: (1) a committed **contract test** that round-trips every frame the client uses (`runtime_start`→response, `conversation_list`/`conversation_create`→response, `stream_delta`/`turn_finished` shape + `event_seq` presence) against the pinned server and **fails loudly, gating every server upgrade** (not the manual "re-run the probe" step); (2) **confine all message-type strings + frame shapes to a single `protocol.ts`** both clients (and the future rail) import — no framing leaks elsewhere; (3) a **client-side server-version assertion at the WS hello** that refuses/warns on any version but the pinned `letta 0.30.19` (a launcher-side check is defeated by a between-launch Homebrew bump). **Reject the SDK-hybrid** (SDK for runtime + raw-WS for CRUD/approvals): `event_seq` is *per-connection* (Unit 1 §C), so a second connection reintroduces the cross-`event_seq` merge race the flip just removed.
- **Approval policy needs a named enforcement point that fails CLOSED (architecture review, finding #4).** M1 "blocks interactive-approval tools," but a server-launch tool-block flag may not exist or may not be per-conversation, and an injected turn that hits `approval_request_message` with no responder **hangs both surfaces** — the exact stall the policy exists to prevent. Enforcement: verify the local MC's attached tool set; and have the client-core — **the injecting client only** (observers must not, to avoid duplicate responses) — auto-send `approval_send=deny` on any `approval_request_message`, so an approval-gated turn **fails closed (bounded deny/error), never hangs**. The full `approval_send=allow` round-trip is the rail/approval milestone.
- **Cross-client turn arbitration is enforced by the SERVER — CONFIRMED by Unit 1 (2026-08-12): the server queue-serializes.** Unit 1 probed two independent connections injecting concurrently to one `{agent, conversation}`: the server ran **two distinct runs serialized through a per-`{agent,conversation}` queue** (`update_queue` showed the second message queued then processed), one active turn at a time — **neither interleave nor drop.** ⇒ the client-core needs **NO shared cross-client lock for correctness**; the previously-planned "flock fallback if interleave" branch is **removed** (unnecessary). The client-core's only job here is optional UX — surface "queued behind another turn" if desired. (The per-process client lock the review warned against is simply not needed.)
- **Enrichment decoupling must DELETE the warm-pool local-backend fallback, not merely bypass it.** Rationale: the current `server.py` degrade path (`pool.dispatch` → `WarmPool` → `letta --backend local` with `LETTA_LOCAL_BACKEND_DIR=lc-local-backend`) *itself forks a second writer* on the backend — so "degrade-don't-crash" as written re-arms the 10:55 race precisely when the App Server is unhealthy (a restart/stall window), and stickily (if the App Server is down at receiver boot, `app_client` stays `None` and every push routes to the writer until the receiver restarts). The true invariant is R1, not liveness: when the App Server is unreachable, `/push` returns **503 (retryable upstream)** and no receiver code path opens the backend.
- **Tool-approval path has an explicit M1 policy (feasibility finding #4).** MC invokes tools that can emit approval/control requests; an approval-gated injected turn must not silently stall both surfaces. M1 policy (mirroring pa-web-ui): auto-allow non-interactive tools (`--yolo`-style) and **block interactive-approval tools** for the shared conversation, so no turn waits on a cross-surface approval UI in M1; full cross-surface approve/resolve (`recoverPendingApprovals()`) is a fast-follow. Unit 1 probes whether a pending-approval event even reaches the observer; Units 4/5/6 carry an approval test scenario; the richer cross-surface approval UX lands with the rail.
- **R1 is enforced structurally, not operationally.** Rationale: review found single-writer stated but enforced nowhere — against the degrade path, resurrecting launchd jobs, cross-client sends, or env leaks. Unit 3 owns an active enforcement thread (advisory lifetime lockfile as a tripwire + source-removal of every other writer), and the env override that lets a clone-validation server point elsewhere is **scoped to the App Server launcher only**, never inherited by any process that also runs the warm pool (a leaked `LETTA_LOCAL_BACKEND_DIR` points a warm subprocess at the wrong dir).
- **Sole-owner App Server is its own launchd service** (`com.ai-pa.letta-app-server`); enrichment (`letta-push-receiver`), web, and terminal are all clients. Rationale: origin decision — decouples enrichment lifecycle from interactive uptime, single supervision point for R16. Promote `AppServer` supervisor out of the receiver.
- **Reuse `build_runtime_env()` for the sole-owner launch; make `LETTA_LOCAL_BACKEND_DIR` env-overridable.** Rationale: identical env for both dispatch surfaces prevents the Docker-hostname silent-degrade; env-overridable dir is required for clone-validate cutover.
- **Watchdog treats stall as restart trigger, not just crash.** Rationale: documented silent-stall is hung-but-alive; launchd `KeepAlive` won't catch it. Health-ping → kill+restart, reusing the sidecar-era learning.
- **Attach to the existing local MC; do not live-migrate Docker-MC web history (explicit accepted tradeoff — finding #3).** Rationale: web is on a *different* backend/agent today; the vision is one Kinara on local. This is not a costless simplification: the user's prior **web** conversations (Docker-MC) become **search-only** (qmd-recallable), not visible-on-scroll in the new surface — the user has accepted this. Two guards: (1) a pre-cutover **identity-equivalence verification** that local-MC really is "Kinara" and not a diverged lineage branch (Unit 8); (2) if visible web history ever must come across, a one-time transcript import is a separately-tracked item, not silent scope.
- **Clone-and-validate cutover.** Rationale: single-writer forbids parallel-running two servers on the real backend; validate on a snapshot clone, then quiesce incumbents and repoint, original as rollback (origin R19).
- **The stock `--backend local` TUI is retired for the fleet backend and replaced by the Unit 5 terminal client.** Rationale: the current TUI (`~/bin/letta-<slug>` → `letta --backend local …`) is a *direct writer* to `lc-local-backend`; once the App Server sole-owns that backend, running the TUI concurrently is a second writer and reintroduces the projection-divergence race (R1/R4). A separate harness that opens the backend directly is a competing writer, not a peer — only a *client* of the App Server shares the runtime safely. The greenfield terminal client is that client. It is **better on continuity** (it can receive external/agent-initiated turns, which the stock TUI structurally cannot) but **worse on ergonomics** on day one (a from-scratch REPL loses the stock TUI's mature input editing/history/approvals UX) — so "strictly better" was an overstatement. **Because the cheaper option that keeps those ergonomics is TUI-in-server-attach mode (`LETTA_BASE_URL=…:4577` as a pure client, not `--backend local`), Unit 1 now probes whether that works** (adversarial finding #9); if it does, prefer it and treat the greenfield REPL as the fallback. The stock TUI in `--backend local` mode remains usable only against backends the App Server does **not** own (scratch, or Docker Letta).

## Open Questions

### Resolved During Planning

- **Port pa-web-ui or greenfield?** → Greenfield; borrow rail UX + `conversation_meta` model, `ingress_guard`, and the task sidebar as *design*, ported on their own timelines. (User decision, this session.)
- **Same or separate App Server instance from enrichment?** → One sole owner; enrichment becomes a client. (Origin, resolved.)
- **How much web richness in M1?** → Minimal chat (single conversation) proving continuity; rail + sidebar fast-follow. (User decision.)
- **Agent-initiated turns in M1?** → No; fast-follow gated on a cron-lease spike. (User decision.)
- **Does making web a client require a data migration?** → No — attach to existing local MC; Docker-MC history archived, not migrated.
- **Is pa-web-ui a single-writer conflict?** → No; it writes Docker Letta, not `lc-local-backend`. It can run in parallel during transition.
- **Client base?** → **Raw-WS-primary client-core** (RESOLVED by Unit 1 Section E). The WS protocol is a complete runtime + conversation-management + approval API; the SDK covers only runtime/session/stream, so the core speaks raw WS directly (one ordered connection, `event_seq`). SDK is optional convenience, not the foundation.
- **How is the greenfield web surface authenticated/reachable in M1?** → **Loopback/LAN-only** (on-box or Tailscale/SSH), no new public Cloudflare tunnel, no edge authN; `ingress_guard` is CSRF/rebind hardening only. Remote public web + real authN deferred to the rail milestone. (User decision, review.)
- **Unit 1 probe outcomes (all RESOLVED 2026-08-13, see findings doc):** silent-stall — not reproduced in 2 long-turn samples (watchdog stays; sidecar re-home likely unnecessary); concurrent-send — **server queue-serializes** (no client lock); observer — **not a writer** (R1-safe); conversation management — **full WS CRUD** exists (rail is a WS fast-follow, not a rebuild); approvals — **WS-supported**; transport — **raw-WS-primary**; TUI-attach — architecturally viable (confirm exact flag at Unit 5); sole owner — runs **with `--openai-api`**.

### Deferred to Implementation

- **Longer-horizon stall watch:** the #99 stall wasn't reproduced on the local models in samples, but it's intermittent — keep the forward-progress watchdog load-bearing and watch production before deciding whether to relocate/retire the `letta-bg-fix-sidecar`.
- ✅ **[RESOLVED by Unit 1 Sections D+E — net FAVORABLE for the fast-follows] The App Server is WS-first; the WS protocol is a full runtime + management API.** No native Letta REST in either mode (Section D: non-`--openai-api` = `/ws` only; `--openai-api` adds the OpenAI shim). BUT the **WS protocol exposes full conversation CRUD** (`conversation_create/list/retrieve/update[=rename+archive]/fork/messages_list/compact/search`, empirically confirmed) **and full approvals** (`approval_request_message`/`approval_send`/`approval_response`). **Consequences:** (a) **sole owner runs WITH `--openai-api`** (keeps enrichment `/v1/responses`; `/ws` + WS-management coexist); (b) **the rail (R6) is buildable entirely on `/ws`** — NOT a re-architecture — funneled through the one sole-owner server (single-writer preserved for free); (c) **approval path (finding #4) is protocol-supported** (broadcast + resolve over WS); (d) **R3 delivery = a small WS-inject adapter** for `scheduler-service`. **Transport reframe:** the SDK covers only runtime/session/stream (not conversation CRUD, approvals, or `update_subagent_state`), so the client-core is better **raw-WS-primary** (one protocol for everything) with the SDK optional for the basic chat path — see revised Key Decision. **M1 unaffected.**
- **Do the rail's `/v1/conversations/*` (create/rename/fork/delete) endpoints exist on the App Server?** — probe in Unit 1 (informs the fast-follow rail, not M1 blocking).
- **Web surface deployment: host Node process vs. Docker container.** Recommendation: a small **host** Node process (loopback to `127.0.0.1:4577`, simplest for R20). If Docker is preferred, the WS client must dial `host.docker.internal:4577`. Resolve when scaffolding Unit 6.
- **hot/cold/archive thresholds (hot-set size, prune age) and the warm-on-attach mechanism** — R18 tuning; warm-on-attach (COLD→live runtime) is unproven and needs its own probe. M1 keeps a small always-hot set; pruning wiring is minimal.
- **Cron-lease ownership** — does `letta server` claim/honor the `crons.json` `scheduler_owner` lease, and can the Desktop app be stopped from contending? — the fast-follow spike (out of M1); M1 only adds `crons.json` to the snapshot set.
- Exact SDK method/type names may drift (pre-1.0) — verify against the pinned version at implementation.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
                 launchd: com.ai-pa.letta-app-server   (watchdog: forward-progress → kill+restart)
                         └── letta server --backend local --listen ws://127.0.0.1:4577 --openai-api
                              SOLE OWNER of ~/.letta/lc-local-backend
                              env = build_runtime_env()  (LETTA_LOCAL_BACKEND_DIR overridable)
                              exposes:  /v1/responses (enrichment)   /ws (runtime + conversation-CRUD + approvals)
                                   │                                    │
     ┌─────────────────────────────┘                 ┌──────────────────┴───────────────────┐
     │ letta-push-receiver (Flask :8099)              │ client-core (RAW-WS, one ordered connection)
     │   now a CLIENT: POST /v1/responses             │   runtime_start · input · stream(event_seq order:
     │   (stops booting its own server;               │     stream_delta+subagent_state+turn_finished, own+foreign)
     │    NO warm-pool fork-on-degrade)               │   · conversation_* RPCs · approval_* · reconnect+catchup
     │                                                │        │                         │
     │                                                │   ┌────┴─────┐            ┌───────┴────────┐
     │                                                │   │ terminal │            │ web (host Node)│
     │                                                │   │  client  │            │ ingress_guard  │
     │                                                │   │ (Node TS)│            │ browser⇄Node⇄WS│
     │                                                │   └──────────┘            └────────────────┘
     │                                                │        └──── same {agent, conversation} ────┘
     │                                                │        turn in one → renders in both (one ordered stream)
  RETIRE/redirect at cutover (single-writer invariant): letta-local-runner :8920, ~/bin/letta-* wrappers, Desktop cron lease
  (M1: single fixed conversation over /ws. Rail = the conversation_* RPCs, a WS fast-follow, not a rebuild.)
```

## Implementation Units

Grouped into three phases. Phase A de-risks and builds the runtime foundation; Phase B builds the shared client-core and the two clients; Phase C proves continuity and performs the safe cutover.

### Phase A — De-risk & Runtime Foundation

- [x] **Unit 1: Interactive `/ws` verification spike (go/no-go) — DONE 2026-08-13, VERDICT: GO.** Full results in `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md` (Sections A–F). Validated multi-client subscribe+inject+observe, observer-not-a-writer, server-queue-serialized concurrency (no client lock), no stall in samples, forward-progress-watchdog need; discovered the **WS protocol is a full runtime+management+approval API** (rail/approvals/R3 are WS features) and resolved **transport = raw-WS-primary**. The originals below are retained for provenance.

**Goal:** Prove the interactive path works on the real server before building clients: a raw-WS client connects to `letta server --backend local --openai-api`; two clients subscribe to one `{agent, conversation}`; one injects, both render a **long** streamed turn; observer receives deltas; `update_subagent_state` visible; and the long turn does **not** silently stall.

**Requirements:** R2, R5, R16 (de-risk)

**Dependencies:** None.

**Files:**
- Create: `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md` (findings, not code)
- Scratch spike scripts under the session scratchpad (throwaway; do not commit)

**Approach:**
- Launch `letta server --backend local --listen ws://127.0.0.1:4577 --openai-api` with `build_runtime_env()`; confirm readiness banner `"listening on ws://"`.
- Resolve the real MC conversation UUID via `GET /v1/conversations/?agent_id=<agent-local MC>&order_by=last_message_at&limit=1` (do **not** rely on the `"default"` literal); ensure the conversation pre-exists before inject.
- Two SDK `remote` clients `resumeSession(convUUID)`; client A `send()` a prompt that produces a **long** multi-hundred-token streamed answer (stall is length/timing-sensitive); assert client B's `stream()` renders the same deltas.
- On a raw-WS reader, confirm `update_subagent_state` frames for a delegated turn, and observe whether foreign `turn_finished` arrives.
- Probe: does the long turn ever complete server-side (`turn_finished`/`loop_status→WAITING_ON_INPUT`) but never render (the stall)? Record whether the sidecar must be re-homed.
- **Probe (GATES R5 — cross-client arbitration):** what does the App Server do when **two independent connections `send()` concurrently** to the same `{agent, conversation}` — reject-the-second (server enforces one-active-turn) or interleave? If it interleaves, cross-client single-writer needs a real shared lock (advisory conversation lease), which is a design change, not a client detail.
- **Probe (GATES R1 — phantom writer):** does a **second read-only subscription** (observe-only, no inject) get counted by the server as a writer/initiator, or is turn accounting strictly per-initiating-connection? A mis-counted observer would be a phantom second writer.
- Probe: does the SDK expose a **raw-frame tap** on its own WS socket (so the side-channel can reuse one connection), or must the side-channel open a second read-only subscription?
- **Probe (approval path — feasibility finding #4):** does an injected `/ws` turn that triggers a **tool approval** surface a pending-approval event to BOTH the initiator and the read-only observer, and can `recoverPendingApprovals()`/an approve call resolve it cross-surface? Decides the M1 approval policy (below).
- **Probe (SDK vs. raw-WS-for-both — adversarial finding #13):** the spike already proved raw WS end-to-end. In Unit 1, exercise BOTH the `@letta-ai/letta-agent-sdk` `remote` backend AND a raw-WS-for-both client for the observer render, and **decide from the findings** which the client-core uses — do not pre-commit to the SDK if raw-WS-for-both is simpler (one ordered connection, no seq-id merge, no pre-1.0 churn surface).
- **Probe (TUI-in-attach-mode — adversarial finding #9):** can the stock letta-code TUI attach to the App Server as a *pure client* via `LETTA_BASE_URL=…:4577` (not `--backend local`)? If yes, it preserves the mature TUI ergonomics and may be preferable to a greenfield REPL for the terminal surface (Unit 5).
- **Probe (agent-initiated-turn path — REVISED 2026-08-12, supersedes the cron-lease probe):** reconnaissance found the **real** scheduled-turn source is **`scheduler-service`** (healthy, live), which injects via **REST `POST {LETTA_CALLBACK_URL}` = `http://letta:8283/v1/agents/{agent_id}/messages`** into the **Docker Letta** — NOT the letta-code cron (`crons.json`/Desktop lease is empty per the user). `scheduler-service` is a REST turn-*initiator*, not an `lc-local-backend` filesystem writer. So R3's "10:55 fix" reduces to **re-pointing `LETTA_CALLBACK_URL` at the sole-owner App Server + mapping job `agent_id`s Docker→local**, not a cron-lease fight. **Probe:** does the App Server (`:4577`) serve `/v1/agents/{id}/messages` over REST, and does a turn injected that way **render on subscribed WS clients**? (That is the actual R3 delivery mechanism.) The letta-code cron lease is now only relevant as a *writer to quiesce at cutover* (single-writer), not as a scheduled-turn source. (Does not add R3 to M1.)
- **Probe (watchdog liveness — finding #12):** characterize a healthy-but-streaming server's out-of-band ping latency on a long turn, so Unit 3 can define liveness on *forward progress* rather than a bare ping (else the watchdog kills legitimate long turns).
- Probe (informational, for the rail fast-follow): do `/v1/conversations/` create/rename/fork/delete endpoints respond on this server?

**Execution note:** Throwaway spike. The deliverable is the findings doc + a go/no-go, not production code.

**Verification:**
- Two clients demonstrably render one injected long turn live.
- A clear written verdict on: silent-stall present/absent on `/ws`; subagent-state visible on raw WS; conversation-UUID resolution works; rail endpoints present/absent.
- **A verdict on the two gating probes:** (1) concurrent-`send()` behavior (reject vs. interleave) — decides whether R5 needs a shared conversation lock; (2) whether a read-only observer is counted as a writer — decides whether the side-channel is R1-safe. Units 3/4 consume both.
- If the stall reproduces, a decision recorded (re-home sidecar vs. watchdog-only) that Units 3/4 consume.

---

- [x] **Unit 2: Sole-owner App Server as a standalone launchd service** — DONE 2026-08-13 (code on branch `feat/msc-app-server-sole-owner`; NOT deployed — cutover is Unit 8). Added `letta_push_receiver/supervisor.py` (standalone entrypoint) + `scripts/run-letta-app-server.sh` + tracked `letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist`; made `build_runtime_env(backend_dir=None)` scoped-overridable + `AppServer(backend_dir=…)`; decoupled `server.py` to a pure client (always-constructed `AppServerClient(APP_SERVER_URL)`, **deleted the warm-pool fork fallback** → 503-retryable when unreachable, `is_reachable()` pre-check). 14 tests pass.

**Goal:** Promote the App Server supervisor out of `letta-push-receiver` into an independently-supervised launchd service that solely owns `lc-local-backend` and serves both `/v1/responses` and `/ws`; make enrichment a pure client.

**Requirements:** R1, R2, R16, R20

**Dependencies:** Unit 1 (go).

**Files:**
- Create: `scripts/run-letta-app-server.sh` (bash wrapper: `set -euo pipefail`, export `LANG/LC_ALL`, full env, `exec` the supervisor)
- Create: `letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist` (tracked reference copy)
- Create/modify: a standalone supervisor entrypoint reusing `letta_push_receiver/app_server.py::AppServer` (e.g. `python -m letta_push_receiver.app_server` or a tiny `__main__` in a new module) — lifecycle lives here, not in `server.py`
- Modify: `letta-push-receiver/src/letta_push_receiver/server.py` (drop `AppServer()` construction/lifecycle; keep `AppServerClient` pointed at `PA_APP_SERVER_URL`; remove the in-process `app_server.ensure()` restart calls)
- Modify: `letta-push-receiver/src/letta_push_receiver/warm_pool.py` (`build_runtime_env()` — make `LETTA_LOCAL_BACKEND_DIR` env-overridable, default unchanged)
- Modify: `letta-push-receiver/src/letta_push_receiver/config.py` if new env keys are needed
- Deploy artifact (not git): `~/Library/LaunchAgents/com.ai-pa.letta-app-server.plist`, logs under `~/Library/Logs/letta-app-server/`

**Approach:**
- **Supervision topology (pinned — see Unit 3):** launchd runs the **Python `AppServer` supervisor** (not `letta server` directly), so `KeepAlive` restarts the *supervisor* and the watchdog owns kill+restart of the `letta server` *child*; only the supervisor signals the child, so the two managers never race for one PID. plist: `KeepAlive` (`SuccessfulExit:false`), `RunAtLoad`, `ThrottleInterval 30`, `ProcessType Background`, `WorkingDirectory /Volumes/main-drive/ai-PA`, env inlined per the local-runner exemplar (host-reachable URLs + creds), **stdout/stderr under `~/Library/Logs/`** (EX_CONFIG/78 trap).
- **Enrichment decoupling (R1-safe):** `server.py` keeps `AppServerClient(base_url=PA_APP_SERVER_URL)` and submits `/v1/responses` dispatch; it no longer boots or restarts a server. **DELETE the warm-pool local-backend fallback:** when the App Server is unreachable, `/push` returns **503 (retryable upstream)** — it must NEVER call `pool.dispatch()`, because that forks `letta --backend local` on `lc-local-backend` = a second writer (the degrade path is itself the R1 violation). Remove `app_server.ensure()` from `_run_enrich` and remove/guard the `pool.dispatch` branch so no receiver code path opens the backend. Also treat a mid-flight App Server disconnect as **retryable**, not a completed 202 (see Unit 3 / Risks — restart drops in-flight tasks).
- **Env-override scoping:** the new env-overridable `LETTA_LOCAL_BACKEND_DIR` (in `build_runtime_env()`) is read **only by `run-letta-app-server.sh`** (and the clone-validation alt-launcher), never exported where the receiver/warm pool would inherit it — a leaked override points a warm subprocess at the wrong backend dir.
- Confirm the target MC-local agent has `message_buffer_autoclear:false`.

**Patterns to follow:** `letta-local-runner/launchd/com.ai-pa.letta-local-runner.plist`, `scripts/run-letta-push-receiver.sh`, existing `AppServer` readiness/shutdown logic.

**Test scenarios:**
- Happy path: `launchctl load` → server reaches readiness banner; `/v1/models` lists the local fleet; `/ws` accepts a `runtime_start`.
- Integration: enrichment `POST /push` still returns 202 and completes a `/v1/responses` task against the now-external server (no regression to the stabilized enrichment path).
- Error path: server killed → launchd restarts it within `ThrottleInterval`; enrichment dispatch during the gap **returns 503 and forks NO local subprocess** (assert the warm-pool path is gone — no `letta --backend local` child appears during an App Server outage).
- Error path: App Server down at receiver boot → `app_client` handling does not silently route every push to a warm-pool writer (the old sticky-fallback bug).
- Edge: `LETTA_LOCAL_BACKEND_DIR` override points the server at an alternate dir (clone) and it boots against it — and the override is NOT visible to a warm-pool subprocess env.
- Config: launchd logs land under `~/Library/Logs/…` (no EX_CONFIG/78).

**Verification:**
- Exactly one `letta server` process owns `lc-local-backend`; enrichment runs as a client with no self-booted server and **no fork-on-degrade**; restart-on-crash works; enrichment throughput unchanged.

---

- [x] **Unit 3: Structural R1 enforcement + stall-catching watchdog** — DONE 2026-08-13 (in `supervisor.py`, same branch). Advisory `flock` on `<backend>/.owner.lock` held for process lifetime (refuse-if-held); periodic foreign-writer re-scan tripwire (`ps`-based, excludes own child/pid); pinned supervision topology (launchd→supervisor, watchdog→child, single kill authority via `_restart_lock`); **forward-progress** stall watchdog (synthetic streamed `/ws` turn — NOT a bare ping — degrades to the fast responsiveness check if `websockets` absent) + fast crash/responsiveness loop; logs never echo the env. `bootout`+Disable of local-runner and the sidecar decision are deploy-time (Unit 8). Lock + foreign-scan + graceful-degrade unit-tested.

**Goal:** Make single-writer an *actively enforced* property, not an operational hope: an advisory lifetime lock as a tripwire, **source-removal** of every other writer, a pinned supervision topology, and a watchdog that restarts on a *stall* (hung-but-alive), not just a crash. (Root-cause fix for the review's central finding — R1 was enforced nowhere.)

**Requirements:** R1, R4, R16

**Dependencies:** Unit 2; Unit 1 verdicts (stall; concurrent-`send()`; observer-not-writer).

**Files:**
- Create: watchdog + lock logic in the standalone `AppServer` supervisor entrypoint (from Unit 2) — **forward-progress** liveness (stream-delta/`loop_status` advancement on a scratch turn, NOT a bare `/v1/models` ping — Unit 1 showed the ping stays 2–11 ms during a live turn and would miss a stall) → on N consecutive no-progress windows, terminate+respawn the `letta server` child; hold an **advisory `flock` lockfile** (e.g. `~/.letta/lc-local-backend/.owner.lock`) for the supervisor's lifetime and a **periodic (not boot-only) re-scan** for foreign openers
- Modify: `letta-local-runner` — `launchctl bootout` + a **tracked `Disabled` override** (record in the tracked plist reference copy + cutover runbook), since its `KeepAlive{SuccessfulExit:false}`+`RunAtLoad` self-resurrects on reboot; `launchctl stop` alone is transient
- Modify (conditional on Unit 1): re-home `letta-bg-fix-sidecar` in front of the App Server HTTP surface **only if** the stall reproduced on `/ws`
- Reference (enacted in Unit 8): the `~/bin/letta-*` wrappers are *replaced* by the Unit 5 client (direct-writer form removed, not merely discouraged); the Desktop cron lease is released **every boot**, not once

**Approach:**
- **Supervision topology (pinned):** launchd → Python `AppServer` supervisor; `KeepAlive` restarts the supervisor; the **watchdog (inside the supervisor) owns kill+restart of the `letta server` child**. Only the supervisor signals the child — launchd and the watchdog never contend for the same PID.
- **Enforce R1 by source-removal, backed by a tripwire.** The advisory lockfile only catches writers that *check* it — the stock `letta` binary does not — so the real mitigation is removing each writer at its source: degrade-path deletion (Unit 2), `bootout`+Disabled for local-runner, wrapper replacement + cron-lease release (Unit 8). The lockfile + periodic re-scan is the *tripwire* that surfaces a second opener (the dangerous case is one appearing *after* the App Server is up — the common case — so a boot-only check is insufficient).
- **Liveness = forward progress, not a bare ping (finding #12).** The silent-stall is length-sensitive, so a `/v1/models`/no-op ping can succeed while a streamed turn is hung, and conversely a legitimate long turn can be slow to answer an out-of-band ping — a naive ping either misses the stall or kills a healthy long turn. Define liveness on *observed forward progress* (stream-delta/token advancement or `loop_status` transitions on a scratch turn), calibrated against the Unit 1 healthy-streaming latency characterization. Thresholds conservative (avoid restart storms): evaluate every 15–30 s, restart after 2–3 consecutive no-progress windows; log every restart with cause; **never restart mid-observed-progress**.
- **Screen restart/startup logs for secrets (security finding #15):** the supervisor must not echo `build_runtime_env()` into logs; treat `~/Library/Logs/letta-app-server/` as secret-bearing.

**Test scenarios:**
- Happy path: healthy server → watchdog pings succeed, no restarts; lockfile held.
- Error path (stall sim): server made unresponsive → watchdog detects N misses → child killed+respawned → healthy; event logged.
- Edge: transient single missed ping (under threshold) does **not** restart (no flapping).
- Integration: `launchctl bootout` + Disabled override for local-runner survives a simulated reboot (it does not re-fork against the backend).
- Integration: a foreign `letta --backend local` opened against the backend while the App Server is up is detected by the periodic re-scan (tripwire fires), not silently ignored.
- Edge: launchd restart of the supervisor and a concurrent watchdog action do not double-signal the child.

**Verification:**
- A simulated stall is auto-recovered; a healthy server is never needlessly restarted; retired writers do not resurrect across a reboot; a second opener appearing after boot is detected; supervision topology has one unambiguous kill authority per PID.

### Phase B — Shared Client-Core & Clients

- [x] **Unit 4: Client-core library (raw-WS protocol client — one ordered connection)** — DONE 2026-08-13 (branch `feat/msc-app-server-sole-owner`). Built `clients/letta-continuity-core/` (TS, no SDK dep): `protocol.ts` (sole home of every frame string + strict drift guards + WS-hello version assertion), `ws.ts` (one loopback connection, `request_id`-keyed RPC, all waits bounded), `stream.ts` (`event_seq`-ordered single stream, own+foreign turns), `catchup.ts` (message-id watermark dedup, NOT `event_seq`), `connection.ts` (bounded reconnect state machine), `pointer.ts` (durable `{agent,conversation}` file). Protocol pinned from live 0.30.19 captures (`stream_delta.delta.id` = catch-up watermark; hello carries NO version field → contract test is the real upgrade gate). **56 tests** (55 offline against an in-process mock App Server + 1 opt-in live check, PASSED against `:4577` docs agent): ordered/foreign render, subagent-state inline, reconnect message-id dedup (no dup/loss), `conversation_list`/`create` RPC, concurrent-send server-serialized, approval fail-closed (injector auto-denies, observer silent), contract-drift fails loudly. Typecheck + biome lint clean.

**Goal:** One reusable module both clients import: a **raw-WS client** that speaks the App Server's full protocol on a **single ordered connection** — `runtime_start`, `input`, live render of all `stream_delta`/`update_subagent_state`/`turn_finished` (own *and* foreign, ordered by `event_seq`), the `conversation_*` management RPCs (create/list/retrieve/update/fork/messages_list — for later rail reuse), `approval_*`, plus connection-state + catch-up on reconnect. Raw-WS-primary per the resolved transport decision (Key Decisions); the SDK is not required.

**Requirements:** R2, R2b, R5, R17

**Dependencies:** Unit 1 (protocol confirmed empirically); can proceed in parallel with Unit 2/3 against the dev `:4577` server.

**Files:**
- Create: `clients/letta-continuity-core/` (TS package) — `src/ws.ts` (WS connect to `ws://127.0.0.1:4577/ws`, no auth on loopback, **server-version assertion at the WS hello** — warn/refuse on any version ≠ pinned `letta 0.30.19`), `src/protocol.ts` (**the sole home of every message-type string + frame shape** — nothing framing-related may leak elsewhere; typed frames + a `request_id`-keyed request/response RPC for the `conversation_*` ops), `src/stream.ts` (one ordered event stream: `stream_delta`/`update_subagent_state`/`update_queue`/`turn_finished` by `event_seq`; turn boundaries from `turn_finished`/`loop_status`), `src/catchup.ts` (`conversation_messages_list` snapshot + **message-id watermark dedup** on reconnect), `src/connection.ts` (state machine: connected / reconnecting / disconnected), `src/pointer.ts` (read the durable `{agent, conversation}` state file). **No `session.ts`/SDK, no `observer.ts` side-channel, no `arbitration.ts`, no `flock`** — one raw connection receives everything; the server queue-serializes.
- Create: `clients/letta-continuity-core/package.json` (a WS lib, e.g. `ws`; Node ≥ the installed letta-code's requirement). **No `@letta-ai/letta-agent-sdk` dependency for M1**.
- Test: `clients/letta-continuity-core/test/` — incl. a **committed contract test** that round-trips every used frame against the pinned server (`runtime_start`, `conversation_list`/`conversation_create`, `stream_delta`/`turn_finished` shape + `event_seq`) and **fails loudly** — this is the upgrade gate against silent protocol drift.

**Approach:**
- **One ordered connection is the whole design.** Unit 1 proved a single `/ws` connection receives *all* broadcasts for its subscribed `{agent, conversation}` — own turns, foreign turns, and `update_subagent_state` — each frame carrying a monotonic **`event_seq`**. So there is **no second observer connection and no cross-stream merge** (that entire problem, and the seq-id-merge risk, dissolves): render in `event_seq` order off the one stream. `turn_finished` (which *does* arrive for all turns on raw WS, unlike the SDK) marks boundaries.
- **Conversation targeting via a durable shared pointer (finding #7 + architecture review #5).** Do NOT resolve by recency (enrichment/agent turns pollute it) and do NOT use `default` (it auto-creates and is the target of the legacy `~/bin/letta-*` wrappers → cross-talk) and do NOT use the `/v1/conversations/` REST resolver (absent on the App Server — findings D1). Instead: a **dedicated conversation UUID created once via the `conversation_create` WS RPC at cutover** (Unit 8) and recorded in **one durable out-of-band location both clients read at startup** (a small state file — the minimal, file-sized precursor to the rail's `conversation_meta`). Both surfaces resolve the *same* UUID; Unit 7 asserts this under concurrent enrichment.
- **No arbitration (confirmed).** Concurrent sends are server-queue-serialized (Unit 1); the client submits and may render `update_queue` as an optional "queued…" indicator. No client lock, no flock.
- **Approvals fail CLOSED (M1 policy — Key Decision).** The **injecting client only** auto-sends `approval_send=deny` on any `approval_request_message` (observers do not, to avoid duplicate responses) so an approval-gated turn resolves to a bounded deny/error and never hangs both surfaces. Frames ride the same ordered stream; the `allow` round-trip is the rail/approval milestone.
- **Reconnect + catch-up dedup (architecture review #2 — the primary recovery path, not an edge).** A watchdog stall-restart (Unit 3) drops *all* connections at once, so catch-up is normal, not rare. On reconnect → `reconnecting` → `runtime_start` → `conversation_messages_list` snapshot → resume live. **Dedup MUST key on a conversation-stable coordinate (the last fully-received message id from the snapshot), NOT `event_seq`** — `event_seq` is *per-connection* and resets on reconnect, so it cannot bridge the replay↔live seam. Discard live frames belonging to messages at/before the watermark until a new message id appears; expose `reconnecting` to the UI.

**Patterns to follow:** the Unit 1 scratch probe scripts (the exact working frame shapes: `runtime_start`→`runtime_start_response`, `input`/`create_message`, `conversation_list`→`conversation_list_response`); `pa-web-ui/subprocess_pool.py` ring-buffer/`seq_id` replay concept (as design, for catch-up).

**Test scenarios:**
- Happy path: connect, `runtime_start`, `input` a turn, receive `stream_delta`→`turn_finished` in `event_seq` order.
- Integration: a *foreign* turn (second core instance injects) renders on this client's single stream, ordered, with its `turn_finished` — no second connection, no merge.
- Integration: `update_subagent_state` from a delegated turn renders inline on the one ordered stream (arrives with its own `event_seq`).
- Integration: `conversation_list`/`conversation_create` RPCs round-trip (`request_id`-keyed response) — the rail primitives work from the core.
- Error/reconnect (primary path): socket dropped mid-turn → `reconnecting` → reconnect + `conversation_messages_list` snapshot → resume live → assert **no duplicate** for the turn that both completed-in-snapshot and replays-on-live (message-id watermark, not `event_seq`); and **no loss**.
- Error path (contract drift): the contract test flags a changed/renamed frame field against a mock non-pinned server → fails loudly (upgrade gate works).
- Error path (approval fail-closed): an injected turn that triggers `approval_request_message` → the injecting client auto-`deny`s → turn resolves to a bounded deny/error, does NOT hang; an observer client does NOT also respond.
- Edge: `input` to a not-yet-created conversation → actionable error, not silent (Unit 1: arbitrary names don't auto-create; create via `conversation_create` first).
- Edge: concurrent sends from two cores → both honored, server-serialized (two runs), no loss/mis-attribution.

**Verification:**
- Two core instances on one conversation render each other's turns live on a single ordered stream; a mid-turn disconnect recovers via catch-up with no lost/duplicated messages; `conversation_*` RPCs work.

---

- [x] **Unit 5: Terminal client (greenfield, text-first)** — DONE 2026-08-13 (branch `feat/msc-app-server-sole-owner`). Built `clients/letta-terminal/`: `render.ts` (PURE event→text, so the loop is testable with no TTY), `session.ts` (render loop against a `SessionCore` seam), `cli.ts`, `main.ts` (readline + real `ContinuityCore`), plus a tracked `bin/letta-continuity` wrapper installed to `~/bin/letta-continuity`. **26 tests** (own-vs-peer labelling, attribution surviving ownership release at turn end, visible reconnect, queue-behind indicator, subagent activity, stream/line-break correctness, CLI parsing + exit codes). **Live verified** against `:4577`: a typed turn renders as `agent ›` and a turn injected from another surface renders live as `peer ›` — the terminal half of R5. Live run also caught two real bugs, both fixed with regressions (below). Reconnect visibility is covered offline; live disruption belongs to Unit 7, which owns the reconnect/catch-up proof.
>
> **Two bugs the live run caught that unit tests could not:**
> - **Every delta chunk carries a DISTINCT `delta.id`** (`letta-msg-26735`, `-26736`, …), so keying the output line on message id printed `agent › HE` / `agent › LL` / `agent › O`. Lines are now keyed on run + message type. The stub server was corrected to assign per-chunk ids so the offline suite reproduces the real shape. *(This also contradicts a documented assumption in `catchup.ts` — "many deltas share one `delta.id`" — which matters for finding #2; recorded there for Unit 7.)*
> - **A turn's stream ends with CONTROL deltas** — `usage_statistics` and `stop_reason` — and `stop_reason` carries **no `delta.id`**. The validator required an id on every `stream_delta`, so it rejected one legitimate frame on *every* turn. Now allowlisted via `CONTROL_DELTA_TYPES`; content deltas still fail loudly without an id, and an unknown control type fails too (intended upgrade-gate behaviour).
>
> **Scope note:** the plan's "reuse `DEFAULT_AGENTS` for slug→`agent-local-*`" is deliberately NOT implemented as a copied table — duplicating the Python registry into TypeScript would create a second source of truth that drifts silently. The client takes its target from the durable pointer instead (which is what M1's single fixed conversation actually needs); slug routing lands with the rail and multiple conversations.

> **Gate resolved 2026-08-13 — stock-TUI-attach is NOT available; build the greenfield REPL.**
> The stock letta-code TUI has no App-Server-client mode: `--backend` accepts only `cloud`/`local`
> (`serverKeyForBackendMode()` is a two-way branch), `LETTA_BASE_URL` drives the **REST** client
> (`api.letta.com`) which the App Server does not serve (Unit 1 §D), and the binary's only
> App-Server client (`createAppServerClient`) is used solely by `letta channel-gateway`
> — a headless channel relay with no TTY. Full evidence in the findings doc's open-items list.
> ⇒ the "Approach" step 1 below is closed; proceed directly to the greenfield fallback.
>
> **Gate side-effects landed the same day (commit on this branch), before any REPL code:**
> - **Unit 4 bug fixed — `conversation_create` never worked against a real server.** Its envelope
>   put `agent_id`/`title` at the top level, but the server's guard requires a **`body` object**
>   (`isConversationCreateCommand`); a guard-failing frame is dropped **silently** (no error, just
>   an RPC timeout). Unit 4's mock answered any shape, so the offline suite rubber-stamped it and
>   the live contract test never exercised create. This would have failed at **Unit 8 cutover**,
>   which mints the dedicated conversation UUID via exactly this RPC. Also fixed:
>   `conversation_list`'s agent filter must live in `query` (a top-level `agent_id` is ignored,
>   silently returning every agent's conversations). The mock now **enforces the server's guards**
>   and the contract test asserts **outbound** envelopes, so this class of bug fails offline.
> - **The version gate is now real.** Unit 4's `assertServerVersion` was a no-op (it looked for a
>   version on the hello and on REST, found none, and always returned `actual: null`). The
>   `app_server_info` RPC does report `letta_code_version`, `protocol_version`, and a capability
>   map, and answers *before* `runtime_start` — so `assertServerIdentity` now runs as a pre-hello
>   gate on every connect/reconnect (missing required capability → always throws; version/protocol
>   drift → per policy).
> - **0.30.20 vetted, pin widened.** The on-disk binary had moved to **0.30.20** while the running
>   server stayed on **0.30.19** in memory — so any restart would have silently changed versions.
>   The contract gate was run against a real 0.30.20 server on a **clone** backend (single-writer
>   preserved): `protocol_version` still 1, capabilities identical, all frames round-trip, real
>   streamed turn completes. Both versions now sit in `VALIDATED_SERVER_VERSIONS`.

**Goal:** A lightweight Node/TS terminal attach point onto the constant-on conversation, built on the client-core.

**Requirements:** R5, R7, R17

**Dependencies:** Unit 4.

**Files:**
- Create: `clients/letta-terminal/` — `src/main.ts` (REPL-ish loop: read input → `core.send()`; render streamed deltas + subagent state; show connection state), `package.json`
- Create: `~/bin/letta-continuity` wrapper (deploy artifact, not git) — `cd $LETTA_LAUNCH_DIR`, source creds, `exec node …`
- Test: `clients/letta-terminal/test/` (render loop against a stubbed core)

**Approach:**
- **First, evaluate stock-TUI-attach (adversarial finding #9).** Unit 1 established a letta-code App-Server-client receives broadcasts (so it *does* get external turns, unlike the standalone `--backend local` TUI). Before building a greenfield REPL, confirm the exact way to run the stock letta-code TUI as a pure App-Server client (attach to `:4577`, not `--backend local`). If it works, prefer it (keeps mature TUI ergonomics). The greenfield REPL below is the fallback.
- Greenfield fallback: a text-first Node/TS loop on the raw-WS client-core. Reuse `DEFAULT_AGENTS` (config.py) for slug→`agent-local-*`; default to MC-local; cwd = `LETTA_LAUNCH_DIR`. Stream deltas inline; render `update_subagent_state` inline (same ordered stream); show `reconnecting…`.
- No direct backend access — purely a WS client of the App Server (contrast with the retiring `~/bin/letta-*` wrappers).

**Patterns to follow:** existing `~/bin/letta-<slug>` wrapper conventions (cwd, creds sourcing) but pointing at the client, not `letta --backend local`.

**Test scenarios:**
- Happy path: send a message, see the streamed reply render to completion.
- Integration: a turn injected from the web client renders live in the terminal (one ordered stream).
- Edge: connection drops → terminal shows `reconnecting…`, then catches up and resumes.
- Edge: while the web client's turn is running, a terminal send is server-queued and runs after (no loss); optional "queued…" indicator.

**Verification:**
- The terminal renders both its own and the web client's turns live; degrades visibly (not silently) on disconnect.

---

- [ ] **Unit 6: Web client (greenfield, minimal chat)**

**Goal:** A minimal browser chat surface (single conversation) built on the client-core, with `ingress_guard` hardening — send + live bidirectional render, no rail yet.

**Requirements:** R5, R17, R20

**Dependencies:** Unit 4.

**Files:**
- Create: `clients/letta-web/` — `server/` (host Node process: serves the browser UI, holds **one** client-core WS to `127.0.0.1:4577`, and **fans out to N browsers** via a fan-out layer + `ingress_guard`), `web/` (minimal chat UI — send box, streamed transcript, subagent status, connection state), `package.json`
- Create: `server/fanout` — a fan-out layer **ported from `pa-web-ui/subprocess_pool.py`** (`RingBuffer` + per-subscriber bounded `Subscriber` queues + `subscribe(since=<bridge-local seq>)` + slow-subscriber drop + `resync_required`). **Re-stamp each upstream event with a bridge-local monotonic sequence** as the browser resume cursor — do NOT relay the upstream per-connection `event_seq` to browsers (it's meaningless after the bridge's own upstream reconnect), and do NOT let a slow/backgrounded browser back-pressure the upstream read loop.
- Create: security middleware port of `pa-web-ui/ingress_guard.py` semantics (host/origin allowlist + CSRF double-submit over a device cookie) in the Node server
- Test: `clients/letta-web/test/` (bridge send/stream; ingress-guard allow/deny)

**Approach:**
- **Deployment: a host Node process**, so the core dials `127.0.0.1:4577` (loopback, no auth per R20). (If instead containerized, the core must dial `host.docker.internal:4577` — decide at scaffolding; default to host process.)
- **Reachability (M1 decision — finding #2):** the Node server binds **loopback / the private network only** — reached on-box or over Tailscale/SSH — with **no new public Cloudflare tunnel**. So M1 needs no edge authN; `ingress_guard` is CSRF/rebind hardening on the private surface. Remote public web + a real authN gate (e.g. a Cloudflare Access policy) are deferred to the rail milestone. This keeps the injection surface (the bridge) off the public internet for M1 while the fidelity-hardened `ingress_guard` still guards cross-site/rebind on the LAN.
- The browser never holds the App Server WS directly (loopback-first): the on-box Node server is the WS client; the browser talks to it. **Security framing (findings #2):** loopback binding only stops off-box processes dialing `:4577` directly — the Node bridge is a *deliberate off-box→loopback relay*, so it IS the turn-injection surface. The acceptance criterion is "the bridge rejects unauthenticated/cross-site turn injection," not "`/ws` is loopback-bound."
- **ingress_guard port fidelity (finding #8):** the Node port must preserve the exact security invariants, not just "allow/deny" smoke tests — **timing-safe** token comparison (`hmac.compare_digest` equivalent); the exact exempt-path set (`/health`, static); and an explicit assertion that the **WS-upgrade / turn-inject route is NOT exempt**. **Cookie `secure` flag: reconcile with the *actual M1 transport*** (loopback/LAN over Tailscale per the auth decision — *not* the deferred Cloudflare path): set `secure` iff the surface is genuinely TLS-terminated, else keep `secure=False` as the Python original does for Tailscale — don't blind-copy either value. Reuse the existing Python test vectors.
- Minimal chat only: attach to the same `{local MC, conversation}` the terminal uses (via the shared pointer, not recency — see Unit 4); render deltas + subagent state on the one ordered stream; show reconnecting state. Single fixed conversation (rail is a WS fast-follow).

**Patterns to follow:** `pa-web-ui/ingress_guard.py` (security) and the pa-web-ui SSE fan-out shape (browser⇄Node bridge concept); the Unit 4 raw-WS client-core (the Node bridge holds one client-core WS and relays to the browser). *(Not the SDK web-chat example — transport is raw-WS.)*

**Test scenarios:**
- Happy path: type in the browser → streamed reply renders.
- Integration: a turn sent from the terminal renders live in the browser.
- Security: request with a disallowed Host/Origin is rejected; missing/invalid CSRF token on a state-changing request is rejected; `/health` and static assets are exempt.
- Edge: core disconnect → browser shows reconnecting, then catches up.
- Integration (fan-out): a second browser tab attaches to the same bridge and renders the same live turn; a browser reconnecting mid-turn replays from the bridge ring buffer via `subscribe(since=<bridge-local seq>)` — no full-history refetch, no lost in-flight turn.
- Edge (fan-out): a slow/backgrounded browser's queue overflows → that subscriber is dropped (`resync_required`), and the **upstream read loop is not back-pressured** (other browsers keep receiving).
- Config: the on-box Node server reaches the App Server on loopback (no off-box `/ws` exposure).

**Verification:**
- The browser and terminal drive the same conversation with live bidirectional render; ingress guard blocks rebind/CSRF; `/ws` is never exposed off-box.

### Phase C — Continuity Proof & Safe Cutover

- [ ] **Unit 7: Web↔terminal continuity validation + reconnect/catch-up**

**Goal:** Demonstrate and lock in the milestone's primary success criterion: the same live conversation is interchangeable across web and terminal with no lost/vanishing messages, including recovery after a disconnect.

**Requirements:** R2, R5, R17

**Dependencies:** Units 5, 6.

**Files:**
- Create: `docs/runbooks/multi-surface-continuity-m1-acceptance.md` (acceptance checklist + observed results)
- Create: `clients/` integration test exercising both clients against a dev App Server (if feasible to automate; otherwise a scripted manual acceptance run recorded in the runbook)

**Approach:**
- Drive an interleaved session: send from terminal, observe on web; send from web, observe on terminal; a multi-turn exchange with a long streamed answer (stall check); a delegated turn (subagent state visible on both).
- Disconnect one client mid-turn; confirm reconnect + `conversation_messages_list` catch-up (message-id watermark dedup) leaves both transcripts identical, with no duplicated or dropped messages (the "no vanishing messages" criterion, i.e. R4 held).

**Test scenarios:**
- Integration: turn from A appears in B within seconds, both directions.
- Integration: long streamed turn renders fully on both (no silent-stall) — ties back to Unit 1/3.
- Integration: both clients provably resolve the **same** conversation UUID **under concurrent enrichment activity** (guards finding #7 — no split-conversation false pass).
- Integration: a delegated turn renders acceptably on both from deltas + boundary inference **even without** subagent-state UI (subagent-state *rendering* is demoted to a fast-follow acceptance item per scope finding #18 — required is that a foreign turn doesn't appear frozen, not a sub-activity panel).
- Error path (approval): an approval-gated tool on the shared conversation follows the M1 policy (blocked/auto-allowed) and does **not** stall both surfaces (finding #4).
- Error/reconnect: kill web mid-turn → reconnect → transcripts match terminal exactly.
- Edge: rapid alternating sends → the server queue-serializes (confirmed Unit 1), no message loss or mis-attribution.

**Verification:**
- Acceptance runbook shows all criteria green; no message ever lands in one surface but not the other.

---

- [ ] **Unit 8: Clone-and-validate cutover, rollback, and minimal lifecycle**

**Goal:** Cut the sole-owner architecture into production without disrupting the running system, with an instant rollback path; establish the minimal hot/cold/archive posture and close backup gaps.

**Requirements:** R1, R4, R18 (partial), R19

**Dependencies:** Units 2, 3, 7.

**Files:**
- Modify: `scripts/snapshot-local-mode.sh` and `deployment/scripts/backup.sh` — add `~/.letta/crons.json` to the captured set
- Create: `scripts/cutover-app-server.sh` (orchestrates clone → validate-on-clone → quiesce incumbents → repoint → verify; documents rollback) — thin, reuses `snapshot-local-mode.sh`
- Create: `docs/runbooks/app-server-cutover-and-rollback.md`
- Reference: hot/cold/archive wiring to `~/.letta/history-archive` (qmd) — minimal for M1

**Approach:**
- **Clone:** `snapshot-local-mode.sh` to capture `lc-local-backend/{agents,providers,conversations}`; stand up a validation server via `LETTA_LOCAL_BACKEND_DIR=<clone>` + alt port; run the Unit 7 acceptance against the clone while incumbents stay up (no single-writer conflict — different dir).
- **Quiesce incumbents (at real cutover):** stop `letta-local-runner`, the `~/bin/letta-*` interactive wrappers, and release the Desktop app's `crons.json` lease. **SIGSTOP only the correct process subtree** (the orphaned-stopped-process-group rule auto-SIGCONTs a group leader) — verify with `ps -o stat=` (want `T`). For M1 (no agent-initiated turns) the cron lease need only be *not contending*; full lease migration is the fast-follow.
- **Pre-repoint snapshot (the real rollback point — finding #1):** the "original is untouched" assumption is false once the App Server begins writing the real backend at repoint. Take a **mandatory snapshot AT the quiesce moment** — after incumbents stop, before the sole owner writes — as the known-good restore point, and **quiesce the memfs↔Gitea sync during the cutover window** so the snapshot is consistent (memfs is excluded from the core tar and re-clones from Gitea, so a mid-sync snapshot is not self-consistent). Rollback = *restore that snapshot* + restart incumbents, not "the original is untouched."
- **Seed the M1 shared conversation (architecture review #5):** create a **dedicated conversation UUID** via the `conversation_create` WS RPC (not `default`, not recency, not the absent REST resolver) and write it to the durable `{agent, conversation}` state file both clients read at startup (`src/pointer.ts`). This is the file-sized precursor to the rail's `conversation_meta`.
- **Repoint:** flip the launchd service to the real backend, confirm sole ownership, run acceptance live.
- **Rollback:** restore the pre-repoint snapshot + restart incumbents; documented step-by-step (a multi-GB restore — "fast," not "instant").
- **Lifecycle (minimal — scope finding #11):** M1 keeps a small always-hot set (the few conversations in play), which is *default runtime behavior requiring no new code*. **Drop the prune-wiring deliverable** — a bloat M1 cannot produce; cold/archive prune + thresholds + warm-on-attach are deferred wholesale to the rail milestone (where multi-conversation growth actually appears).
- **MC identity-equivalence verification (finding #3):** before cutover, verify the local-MC (`agent-local-*`) the clients attach to is the intended "Kinara" — its memory blocks / canonical identity / context are current and not a diverged branch of the companion→kinara→MC→MC-local lineage — so the user is not silently switched to a different-feeling agent. Record the check in the cutover runbook.
- **Clone server binds loopback (security residual):** the alt-port validation server carries the full-creds env; it must bind `127.0.0.1` only (never a routable interface) — a second secret-bearing listener during cutover must not be off-box reachable.

**Test scenarios:**
- Happy path: acceptance passes on the clone, then on the real backend post-repoint.
- Integration: enrichment `/v1/responses` continues working across the cutover (client of the same server).
- Error/rollback: induced failure post-repoint → rollback to the original backend restores the prior working state; documented and rehearsed.
- Edge: quiesce step leaves no second writer on `lc-local-backend` (verified `T` state / no forking local-runner).
- Config: `crons.json` now present in snapshot/backup output.

**Verification:**
- Production runs on the sole-owner server with acceptance green; enrichment unaffected; a rehearsed rollback returns to the prior state; backups include `crons.json`; exactly one writer on the backend.

## System-Wide Impact

- **Interaction graph:** the sole-owner server becomes a shared dependency of enrichment (`/v1/responses`), web, and terminal. `letta-push-receiver/server.py` changes from server-owner to client **and loses its warm-pool local-backend fallback** (that fallback was a second writer). `letta-local-runner` is `bootout`+Disabled (not just stopped). The Desktop app's cron lease is released every boot (M1) / migrated (fast-follow).
- **Supervision topology:** launchd supervises the Python `AppServer` supervisor; the watchdog (in the supervisor) owns the `letta server` child. One kill authority per PID — launchd and watchdog never contend.
- **Error propagation:** server down/stalled must surface as a client-visible `reconnecting…` (R17) everywhere; enrichment returns **503-retryable** (never fork-on-degrade). The watchdog converts stalls into restarts. A restart drops live `/ws` subscriptions (clients reconnect + `conversation_messages_list` catch-up) **and** any in-flight `/v1/responses` task — so enrichment dispatch must treat a mid-flight disconnect as retryable, not a completed 202 (the current fire-and-forget 202 would silently drop the task).
- **State lifecycle risks:** single-writer is the core invariant — any second opener of `lc-local-backend` reintroduces the projection-divergence race (R4). Conversation `in_context_message_ids` can lag (empty-then-populated); clients must tolerate it. Constant-on threads bloat over time (R18) — minimal prune in M1, full policy deferred.
- **Protocol contract surface:** the client-core couples to letta-code's unversioned WS frames — the contract test + single `protocol.ts` + WS-hello version assertion (Key Decisions / Unit 4) are the parity guard; a server upgrade must re-run the contract test as a gate.
- **Two ordering seams beyond the steady-state single stream:** (a) reconnect replay↔live (dedup on message-id, not per-connection `event_seq` — Unit 4); (b) the web bridge's browser fan-out (re-stamp bridge-local seq, don't relay upstream `event_seq` — Unit 6). Both are where the "one ordered stream" simplicity does *not* hold and must be handled explicitly.
- **Integration coverage:** the cross-surface render (turn in one → both), the reconnect dedup seam, and the fan-out are the behaviors unit tests alone won't prove — Unit 7 (+ Unit 6 fan-out tests) exercise them against a real server.

## Risks & Dependencies

- **Silent-stall on `/ws` (downgraded by Unit 1, not eliminated).** Not reproduced in two long-turn samples on the local model (`deepseek-v4-flash`); the historical #99 stall was on `chatgpt_oauth`/`Kimi`. Risk remains (intermittent, model-sensitive). Mitigation: the R16 forward-progress watchdog stays load-bearing; the `letta-bg-fix-sidecar` re-home is likely unnecessary but kept as an option pending longer production observation on heavier models.
- **Protocol coupling to letta-code's unversioned internal WS (raw-WS-primary's core cost — architecture review).** A binary bump can rename a frame field with no build-time failure, only runtime mis-parse (and enrichment shares the server). Mitigation: committed **contract test as an upgrade gate** + all framing confined to `protocol.ts` + **WS-hello server-version assertion** (pinned `letta 0.30.19`). The SDK-hybrid is rejected (a second connection reopens the cross-`event_seq` merge race). This *replaces* the former SDK-churn/observer-gap risks (the SDK is no longer the base).
- **Reconnect/fan-out ordering seams (architecture review #2/#3).** `event_seq` is per-connection, so it can't bridge reconnect replay↔live (dedup on message-id — Unit 4) or the browser fan-out (bridge-local re-stamp — Unit 6). A watchdog restart forces the reconnect seam on all surfaces at once, so it's the *primary* path. Mitigation: the message-id watermark + the ported `subprocess_pool` ring-buffer fan-out.
- **Approval hang (architecture review #4).** An injected turn that hits `approval_request_message` with no responder hangs both surfaces. Mitigation: the injecting client auto-`deny`s (fail closed) — Key Decisions/Unit 4; Unit 7 asserts bounded deny, never hang.
- **Single-writer is enforced nowhere by default (root risk, from architecture review).** Four re-entry vectors reopen the backend after a one-time quiesce: (1) the enrichment **degrade path forks a writer** (deleted in Unit 2); (2) `letta-local-runner`'s `KeepAlive` **self-resurrects on reboot** (`bootout`+Disabled in Unit 3); (3) a **cron fire re-claims the Desktop lease** (released every boot); (4) a **human opens a `~/bin/letta-*` wrapper** (replaced by the client). Mitigation: structural source-removal of every writer + an advisory lifetime lockfile and periodic re-scan tripwire (Unit 3) + clone-validate cutover with correct-subtree SIGSTOP + `ps stat` verification (Unit 8). The lockfile is only a tripwire — the stock `letta` binary ignores it — so source-removal is the real guarantee.
- **In-flight enrichment loss on restart / blast-radius coupling.** One server now serves interactive continuity AND enrichment; a stall-triggered restart kills unrelated in-flight `/v1/responses` tasks, and enrichment's 202 is fire-and-forget (no persistence/idempotency). Mitigation: enrichment treats a mid-flight disconnect as retryable (Unit 2); full idempotency/queue-durability is a fast-follow if drops prove frequent. Thundering-herd reconnect catch-up is negligible at M1's two clients — a deferred concern for the rail milestone (N conversations × M surfaces).
- **Warm-on-attach unproven.** COLD→live-runtime rehydration isn't the same as qmd history recall. Mitigation: M1 keeps a small always-hot set; defer warm-on-attach + prune thresholds with an explicit probe.
- **Env completeness at launch.** Wrong/partial env silently degrades host tools. Mitigation: reuse `build_runtime_env()` verbatim.
- **launchd EX_CONFIG/78.** Logs on `/Volumes` fail spawn. Mitigation: logs under `~/Library/Logs/`.
- **Credential blast radius (security finding #14).** The sole owner is now one always-on, off-box-reachable (via the bridge) process holding all curated tokens (`POSTGRES_PASSWORD`, `GITEA_MEMFS_TOKEN`, `SLACK`/`GITHUB`/`GRANOLA`, Google creds), and it serves interactive turns — so an agent coaxed into dumping its env, or a bridge compromise, exposes every downstream credential at once (previously enrichment and interactive were separable). Mitigation for M1: accept explicitly as a single-user home box **and** don't log the env (Unit 3), bind the clone server loopback (Unit 8); a least-privilege split of interactive-vs-enrichment creds is a candidate fast-follow.
- **The motivating problem is deferred and its enabler is unverified.** M1 does not fix the detached scheduled turn (R3); that hinges on evicting the Desktop `crons.json` lease, an unrun probe. Mitigation: Unit 1 runs that probe as an informational **go/no-go for the whole effort's payoff** — a negative result should trigger a plan re-frame before further investment, not a silent fast-follow.

## Documentation / Operational Notes

- New runbooks: `docs/runbooks/app-server-cutover-and-rollback.md`, `docs/runbooks/multi-surface-continuity-m1-acceptance.md`; spike findings `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md`.
- New launchd service `com.ai-pa.letta-app-server` (plist not git-tracked; keep the tracked reference copy under `letta-push-receiver/launchd/`). Logs under `~/Library/Logs/letta-app-server/`.
- Backups: add `~/.letta/crons.json`; the sole-owner backend is already covered by `snapshot-local-mode.sh`/`backup.sh`.
- Update `project_multi_surface_continuity` memory when M1 lands (foundation live; fast-follows = rail, task sidebar, agent-initiated turns/cron lease).

## Sources & References

- **Origin document:** [docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md](docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md)
- Prior spike: `docs/plans/2026-08-12-dispatch-surface-spike.md`; corroborating WS frames `docs/research/2026-06-23-spike-findings.md`
- Reuse targets: `letta-push-receiver/src/letta_push_receiver/{app_server,app_server_client,server,warm_pool,config}.py`; `pa-web-ui/{subprocess_pool.py,ingress_guard.py,app.py}`; `scripts/snapshot-local-mode.sh`; `deployment/scripts/backup.sh`
- launchd exemplars: `letta-local-runner/launchd/com.ai-pa.letta-local-runner.plist`
- External: docs.letta.com/agent-sdk · github.com/letta-ai/letta-agent-sdk (`@letta-ai/letta-agent-sdk@0.7.1`) · github.com/letta-ai/letta-oss-ui
