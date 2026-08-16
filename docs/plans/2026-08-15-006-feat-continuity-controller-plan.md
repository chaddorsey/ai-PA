---
title: "feat: Continuity Controller — resident sole client of the App Server"
type: feat
status: active
date: 2026-08-15
origin: docs/brainstorms/2026-08-15-continuity-controller-requirements.md
deepened: 2026-08-15
---

# feat: Continuity Controller — resident sole client of the App Server

## Overview

Build the resident **Continuity Controller** adopted in the 2026-08-15 architecture pivot: a
launchd-supervised daemon that is the App Server's only interactive WebSocket client — permanent
subscriber for every hot runtime, sole submitter of all turns, journal keeper, R12–R15 router,
external-tool registrar, and the single authenticated boundary that every surface (terminal, web,
later phone/glasses) connects through. The peer-client architecture is superseded; the built
packages (`clients/letta-continuity-core`, `clients/letta-terminal`) are salvaged as parts, per
R22.

## Problem Frame

Three live-verified platform behaviours punish ephemeral connections holding durable
responsibilities: a running turn is cancelled when its last subscribed client detaches
(`docs/followups/captures/q5-detach-cancels.jsonl`); a queued message dies silently with its
submitting socket (Q3, `docs/followups/2026-08-15-continuity-ownership-live-captures.md`); and a
browser cannot authenticate a WS upgrade at all (D2.2,
`docs/followups/2026-08-15-app-server-docs-vs-implementation.md`). Surfaces are ephemeral by
definition, so the durable responsibilities move into one resident controller — the integration
pattern the App Server documentation itself prescribes. Full rationale and operator decisions:
the origin document (R21–R29) and the adopted sketch
(`docs/plans/2026-08-15-continuity-fresh-design-sketch.md`).

## Requirements Trace

- **R21** — resident controller: permanent subscriber, sole submitter, journal, router,
  external-tool registrar, single auth boundary; surfaces connect only to it. *(Units C3–C5)*
- **R22** — salvage-only assessment of the built packages; attribution/turn-completion resolved
  as controller data. *(Unit C2, consumed by C3–C6)*
- **R23** — three-lane routing table (Kinara / direct / fan-out). *(Units C7–C8, C10)*
- **R24** — direct exchanges live in the specialist's own thread, rendered inline; async
  Kinara digest. *(Unit C8)*
- **R25** — route forms: explicit address, per-thread binding, Kinara-managed (auditable);
  no static operator rule config. *(Unit C8)*
- **R26** — direct-route specialists are hot-set members. *(Units C3, C8)*
- **R27** — one orchestration pattern registry; Kinara-as-orchestrator and -as-reporter.
  *(Unit C10a)*
- **R28** — tiered surface protocol: mandatory core + declared capability sets, per-surface
  degradation, nothing silently lost. *(Units C5–C6, C9)*
- **R29** — multiple live Kinara conversations from day one; R13/R15 load-bearing. *(Units C3, C7)*
- Carried forward from R1–R20 (see origin): sole-owner App Server (R1, built as Units 2–3 on
  this branch), supervision/watchdog (R16), visible reconnect + catch-up (R17), hot/cold/archive
  (R18), clone-and-validate cutover (R19), loopback-first auth (R20).
- **Success criteria** (origin): direct lane adds no model hop; a named pattern is
  invoker-agnostic; a core-tier-only surface gets full continuity; proofs P1–P5 pass with
  reverting mutations (G9). Proof ownership: **P1/P2 → C1** (P1 additionally pinned as a
  permanent live contract test), **P3/P4 → C4** live scenarios, **P5 → C5** live scenarios on a
  permission-mode-flipped clone; the full P1–P5 checklist is re-run in C10b's cutover
  verification.

## Scope Boundaries

- Enrichment keeps calling the App Server's stateless `/v1/responses` shim directly — it is not
  a surface and does not route through the controller. "Sole client" means the interactive `/ws`
  path.
- No out-of-band delivery channel as primary path; no hand-edited routing-rule config; no
  architecture-comparison retrospective beyond the salvage map; legacy Docker Letta untouched.
- Phone/glasses surfaces, relevance-inferred landing (the middle clause of R13), and
  notification push targets beyond attached surfaces are out of this plan (fast-follows on the
  same controller protocol).
- The cutover (quiescing incumbents, loading the App Server plist) stays the final unit; nothing
  before it touches the live `lc-local-backend` writers.

## Context & Research

### Relevant Code and Patterns

- `clients/letta-continuity-core/` — raw-WS client core (vitest, biome, tsx-run, no build):
  `src/protocol.ts` (frame strings + `validateInboundFrame` + version pins), `src/ws.ts`
  (bounded RPC), `src/stream.ts` (event_seq ordering), `src/catchup.ts` (snapshot + watermark —
  dedup known broken live), `src/connection.ts` (reconnect budget), `src/ownership.ts`
  (attribution — mooted by this architecture), `src/index.ts` (facade). Test assets to reuse:
  `test/helpers/mockServer.ts` (exported `./testing`), `test/helpers/harness.ts`,
  `test/double-fidelity.test.ts`, `test/protocol.contract.test.ts`, `test/live.contract.test.ts`
  (clone-server gate), `test/version-pin.test.ts`, mutation harness `clients/tools/mutate.mjs` +
  `clients/tools/mutations.mjs` (81 entries), capture harness `clients/tools/capture-ownership.mjs`,
  disposable-agent tool `clients/tools/scratch-agent.mjs`.
- `clients/letta-terminal/` — `src/render.ts`, `src/sanitize.ts`, `src/session.ts`, `src/cli.ts`,
  `src/main.ts`; spawn-binary harness `test/helpers/spawnCli.ts` (PIPESTATUS, `| head`, pty via
  `script(1)`); deploy wrapper `bin/letta-continuity` → `~/bin` (untracked live copy convention).
- Units 2–3 (built, committed, not deployed):
  `letta-push-receiver/src/letta_push_receiver/supervisor.py` (flock tripwire on
  `<backend>/.owner.lock`, single kill authority, 20s responsiveness + 300s forward-progress
  watchdog, foreign-writer rescan), `scripts/run-letta-app-server.sh`,
  `letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist` (tracked reference copy).
- Vendor protocol truth: `@letta-ai/letta-code` ships a types-only, browser-safe export
  `./app-server-protocol` (`protocol_v2.d.ts`). The WS protocol is the full API: runtime frames
  + `conversation_create/list/retrieve/update/fork/compact/messages_list/open/close/search/titles`
  + the `approval_*` family (spike §E).
- Scheduler fire path: `scheduler-service/src/scheduler_service/services/actions.py` (~370–420)
  POSTs `{"messages":[...]}` to `LETTA_CALLBACK_URL` (`/v1/agents/{agent_id}/messages` shape) —
  an endpoint the App Server does not serve; the controller will.
- launchd conventions: tracked reference plist in-repo + `scripts/` wrapper pinning PATH/locale;
  logs under `~/Library/Logs/<service>/` (never `/Volumes` → EX_CONFIG/78); `KeepAlive` +
  `ThrottleInterval`.
- Persistence conventions: repo daemons use Postgres `pa_web` (`pa-web-ui/app.py:317`
  `conversation_meta` DDL; `gmail-watch-service/.../task_queue_writer.py`); SQLite only in
  scrapers. This plan deliberately deviates for controller-internal state — see Key Technical
  Decisions.

### Institutional Learnings

- **Bind to vendor types; don't re-derive from captures** — four review rounds transcribed the
  protocol by hand while `protocol_v2.d.ts` shipped in the installed package
  (`docs/followups/2026-08-15-app-server-docs-vs-implementation.md` §D).
- **Turn completion is a disjunction**: per-run `stop_reason` delta live (`requires_approval` =
  continuation), `loop_error.is_terminal` for faults, idle only as reconnect-seam fallback,
  wall-clock timeout as backstop; filter `subagent_id` (design brief §A1, round-4 findings).
- **Idle ≠ turn over** (`WAITING_ON_INPUT` fires between accepted input and its run);
  **two inputs on one socket get deferred acks, never queue frames** — controller must keep its
  own per-runtime queue rather than reading server queue frames (live captures Q2).
- **Replay/dedup mechanisms are documented, use them**: `idempotency_key` per broadcast, `otid`
  as the stable per-message key (`delta.id` namespaces are disjoint from snapshot ids), `sync`
  for runtime-state replay, `runtime_start.wait_for_replay`, `recover_approvals` default-true;
  transcript source is `conversation_messages_list` only (docs-vs-impl §B; the `otid` keying
  comes from `docs/followups/2026-08-13-continuity-core-approval-correlation.md`, not §B — and
  `otid` is optional in the vendor types).
- **Approvals**: broadcast to all subscribers, server settles the race — answer unconditionally,
  send-then-record, clear answered-set on reconnect; currently unobservable under
  `permission_mode: unrestricted` (pinned by a live contract test) — approval findings are
  conditional (`docs/followups/2026-08-13-continuity-remediation-closeout.md`).
- **Falsifiability standard (G9)**: three review rounds shipped defects under green tests; the
  standard now in force is one named mutation per fix (`clients/tools/mutate.mjs`), doubles
  modeling real wire behaviour, and subprocess tests spawning the real binary
  (`docs/plans/2026-08-14-001-fix-continuity-test-binding-goal.md`). This plan inherits it
  wholesale.
- **Reconnect lifecycle traps**: recovery = a connection surviving `stabilityMs`, not one that
  opens; identity-guard close handlers; validate `event_seq` (`Number.isSafeInteger`) or a
  poisoned frame latches the watermark (`docs/followups/2026-08-13-continuity-final-review-findings.md`).
- **Server/disk version drift is real** (running 0.30.19 with 0.30.20 on disk) — gates must
  check the *running* server's reported version.
- **launchd**: logs on `/Volumes` = silent exit 78; launchd children get no user PATH/Keychain.
- **Silent stall #99** is cross-provider; watchdog liveness must be forward-progress, not a ping
  (already embodied in `supervisor.py`).

### External References

- App Server docs (fetched 2026-08-15): overview, quickstart, protocol lifecycle, integration
  patterns, external tools — https://docs.letta.com/platform/app-server. Notables for this plan:
  the controller pattern (registry in own DB, per-runtime turn locking, reducer-over-log,
  "App Server can restart — recover from your own database"), `external_tool_call_request`
  routed only to the registering connection, `--ws-auth capability-token|signed-bearer-token`
  for non-loopback listeners.

## Key Technical Decisions

- **Controller is a Node/TypeScript daemon in `clients/`** (working name
  `clients/continuity-controller/`): the salvage is TS, the vendor protocol types are TS, and
  the vitest/mutation/mock-server tooling carries over directly. Python (the `supervisor.py`
  precedent) would orphan all of it.
- **Wire types bind to `@letta-ai/letta-code/app-server-protocol`** with compile-time
  assignability checks; `protocol.ts`'s runtime validation, drift guards, and version pins are
  salvaged on top. The pin gates the **running** server's reported version, not the binary on
  disk. Resolution mechanism (decided 2026-08-15): the CLI package becomes a **devDependency of
  `clients/continuity-controller`, pinned to the version the supervisor runs** — types resolve
  normally, and a server upgrade cannot silently compile against stale definitions (rejected
  alternative: a committed snapshot, whose skipped refresh fails quietly).
- **Two WS connections: anchor + worker (pending C1 confirmation).** The learnings add a
  constraint the sketch missed: the controller itself becomes the last subscriber, so a
  controller crash/restart would cancel every in-flight turn. Mitigation: a minimal **anchor**
  process (subscribe-only, separately supervised) holds `runtime_start` subscriptions for the
  hot set so the feature-rich worker can restart without killing turns. *This is a deliberate,
  learnings-driven revision of the sketch's single-socket design (sketch §2), pending C1.*
  Design rules that C3 must honor: **both connections subscribe to every hot runtime** — the
  worker's subscription is the one journaled from; the anchor's exists purely for crash-overlap
  (a `sync` on a fresh connection is not shown to create a subscription, so the worker must
  `runtime_start` too). The anchor stays near-zero-logic by **reading the registry read-only**
  and re-issuing `runtime_start`s when the worker signals a hot-set change; the window in which
  a newly-warmed runtime is worker-only-subscribed is a journaled known exposure. C1 proves the
  takeover semantics ("no other subscribed client **can take over**" implies a second subscriber
  prevents cancellation) — including S5's harder question: worker-registered external tools and
  approvals die with the worker's *connection* even when the anchor holds the turn, so worker
  reconnect must re-register tools and any in-flight `external_tool_call_request` orphaned by
  the restart is journaled FAILED-VISIBLE. If the platform disagrees on takeover, fall back to
  accepting restart-cancels-turns with visible journal failure marks, and say so in the goals
  doc.
- **Controller-side per-runtime turn queue** (never rely on server queue frames): at most one
  active controller-submitted turn per `{agent_id, conversation_id}`; queued messages persist in
  controller state so nothing dies with a socket — this closes loss path Q3 for the
  *server-side-queued* mode. The remaining seam is the **submitting window**: a worker crash
  between the socket write and the ack/commit leaves one message in an unknown state. Protocol:
  persist `state=submitting` *before* the socket write; on recovery, reconcile against
  `conversation_messages_list` keyed by `client_message_id`→`otid` (C1 verifies this mapping is
  actually recoverable from the transcript); resubmit only on confirmed absence — duplicate
  turns on a shared conversation are the documented hazard (docs-vs-impl §A4).
- **Turn terminality = the disjunction** (stop_reason delta | `loop_error.is_terminal` | idle
  fallback at reconnect seams | wall-clock backstop), with `subagent_id` filtering; every turn
  leaves the state machine visibly (G5). The wall-clock arm is **coupled to `abort_message`**:
  on timeout the controller sends abort, confirms (abort response or subsequent terminal
  signal), marks FAILED-VISIBLE, and only then releases the queue — a locally-timed-out but
  still-running server turn would otherwise head-of-line-block every subsequent message into
  serial timeouts. Operator-initiated abort is a surface-protocol capability (C5/C6), so a
  runaway turn can be killed from any surface.
- **Controller-internal state (registry, journal, routes, queues) lives in host-local SQLite**,
  a deliberate deviation from the repo's Postgres-`pa_web` daemon convention. Rationale: the
  controller must be up and journaling when Docker/supabase is down (it guards against exactly
  that class of outage), it is a single-writer daemon (SQLite's sweet spot), and its data is
  device-local operational state, not shared product state. `pa_web.conversation_meta` remains
  the reference model for rail metadata and is migrated into the registry at the web-surface
  unit. Operational hardening (review-added): WAL mode; DB directory 0700, files 0600; a
  boot-time integrity check that **degrades visibly** rather than starting with an empty
  authority (routes/registry/unseen markers are reconstructable from nowhere — only the journal
  can be rebuilt from `conversation_messages_list`); deliberate inclusion of the SQLite files in
  `deployment/scripts/backup.sh`'s host-data section at C3; retention/compaction revisited at
  the C10 soak or when the journal first exceeds a size threshold set in C3, whichever comes
  first. If review prefers convention over independence, this is the decision to challenge.
- **R3 delivery = the controller speaks the scheduler's existing dialect**: it serves
  `POST /v1/agents/{agent_id}/messages` so `scheduler-service` re-points `LETTA_CALLBACK_URL`
  (to `host.docker.internal:<port>` — the container cannot reach host loopback directly, and
  that proxy makes the ingress reachable from **every** container on the box, so interface
  binding is not the control). The ingress therefore **requires a shared-secret bearer header**
  (reuse `SCHEDULER_API_KEY` via scheduler env — still a config-only change on that side);
  unauthenticated POSTs are rejected and journaled. Response semantics are a stated decision,
  not an accident: **202-on-accept** — the scheduler's execution records become *delivery*
  records; turn outcome is controller-journal truth (documented in the cutover runbook).
  Cutover prerequisite: inventory `route=letta` jobs and map Docker→local agent ids per job
  (one env var moves for all jobs; the 2026-08-12 spike flagged this mapping as required).
- **Auth**: App Server stays loopback/no-auth. Controller: loopback surfaces (terminal) use a
  file-permission token — generated at first boot under
  `~/Library/Application Support/continuity-controller/` mode 0600, rotatable on demand; this
  makes *user-level code* the explicit trust boundary, and approval-answering authority rides
  on it. Browser surfaces use tickets minted over the existing authenticated HTTPS path
  (browsers can't set WS headers): **single-use, seconds-order TTL, consumed via a first-frame
  auth message on the open socket — never in the WS URL** (query strings leak through
  Cloudflare/proxy logs). The concrete identity of that HTTPS path is named and recorded as a
  security dependency at C9. One boundary, per G8/R20.
- **Approvals**: controller answers the server unconditionally per settled facts (send-then-
  record), and separately runs its own surface-facing arbitration (first answer wins; others see
  resolution; held pending + badge when nobody attached, recovered via `recover_approvals`).
- **Supervision**: reuse the Units 2–3 idioms — tracked reference plist + `scripts/` wrapper,
  logs under `~/Library/Logs/continuity-controller/`, forward-progress liveness (a periodic
  `sync` round-trip with deadline), single kill authority. The controller does not supervise the
  App Server; `supervisor.py` keeps that job.

## Open Questions

### Resolved During Planning

- *Where does the controller live and in what language?* → TS daemon in `clients/`, for salvage
  and vendor-type reasons (above).
- *How does the scheduler reach the controller?* → its existing `LETTA_CALLBACK_URL` POST shape,
  served by the controller (above).
- *What is the transcript/dedup ground truth?* → `conversation_messages_list` + `otid` +
  `idempotency_key` + `wait_for_replay` (documented mechanisms; the invented ones are retired).
- *Does the controller supervise the App Server?* → No; `supervisor.py` (Units 2–3) keeps that
  role. Two peer services under launchd.

### Deferred to Implementation

- Exact SQLite driver and schema details; journal retention/compaction policy (R18 prune ages) —
  after real volume is observed.
- One worker socket for all runtimes vs per-runtime sharding — start with one (+ anchor); shard
  only if C1/C7 show ordering or throughput pressure.
- Digest batch-window sizing — the design is decided (batched, muted, operator-preempts,
  route-origin thread mapping); only the window cadence needs tuning against real use.
- Relevance-inferred landing (R13 middle clause) — out of plan; tag → default precedence ships
  first.
- Whether approvals become observable once permission modes are used in anger — the pinned live
  test is the tripwire.
- Web-surface framing (SvelteKit vs minimal) and `conversation_meta` migration mechanics — C9.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not
> implementation specification. The implementing agent should treat it as context, not code to
> reproduce.*

```
                       ┌─────────────────────────────────────────────┐
                       │ App Server (sole owner, :4577, --openai-api)│
                       │ supervised by letta-push-receiver/supervisor│
                       └────────▲──────────────▲─────────────▲───────┘
                        ws /ws  │       ws /ws │             │ http /v1/responses
                     (subscribe-│only)         │             │ (enrichment + fan-out lane,
                       ┌────────┴───┐  ┌───────┴──────────┐  │  unchanged callers)
                       │  ANCHOR    │  │  WORKER          │──┘
                       │ hot-set    │  │ turn queue/submit│
                       │ runtime_   │  │ journal reducer  │
                       │ start only │  │ router (3 lanes) │
                       └────────────┘  │ ext tools        │
                        (separately    │ surface API      │
                         supervised)   └───┬────────┬─────┘
                                           │        │        SQLite: registry · journal ·
                              loopback WS+ │        │ HTTPS   routes · queues · unseen
                              token        │        │ ticket
                                     ┌─────┴──┐  ┌──┴──────┐      ┌────────────────────┐
                                     │terminal│  │ web …   │      │ scheduler-service ──┼─▶ POST /v1/agents/{id}/messages
                                     └────────┘  └─────────┘      └────────────────────┘   (served by WORKER, loopback)

Turn state machine (worker, per accepted message):
  accepted → queued(controller) → submitted → streaming → terminal
  terminal ∈ {stop_reason, loop_error.is_terminal, aborted, idle-fallback, timeout→FAILED-VISIBLE}
```

*(The anchor+worker split is a learnings-driven revision of the sketch's single-socket design,
pending C1's takeover proof — see Key Technical Decisions. Both connections subscribe to every
hot runtime; the worker's subscription is the journaled one.)*

## Implementation Units

Grouped in phases; each phase is independently landable. Unit labels are C1–C10 to avoid
collision with the superseded M1 Units 1–8.

### Phase A — Ground truth (gating)

- [x] **Unit C1: P1/P2 platform spike — anchor viability and multiplex shape** *(GO recorded —
  docs/plans/2026-08-15-006-controller-spike-findings.md)*

**Goal:** Prove or kill the load-bearing platform assumptions before controller code exists.

**Requirements:** P1–P2 proof obligations (sketch §8); informs the anchor decision.

**Dependencies:** None. Runs against a clone backend on an alternate port (never live :4577
runtimes), reusing `clients/tools/capture-ownership.mjs` scenario style and
`clients/tools/scratch-agent.mjs`.

**Files:**
- Create: `clients/tools/capture-controller-spike.mjs` (scenarios), findings appendix
  `docs/plans/2026-08-15-006-controller-spike-findings.md`
- Test: S1 is additionally **promoted into the permanent opt-in live contract suite** as a
  version-gated test ("a second subscriber holds a detached turn alive") run at every server
  version bump — cancellation-on-detach is *behavior*, not types, and the vendor-type binding
  cannot catch it changing. Other scenarios double as the named capture artifacts.

**Approach:** Six scenarios, each producing a capture file: (S1) client A starts a 25s+ tool
turn, client B stays subscribed, A detaches → does the turn complete? (the P1 question — B is
the anchor stand-in); (S2) same but B subscribes *after* the turn starts (late anchor);
(S3) two messages submitted through one socket with a controller-style local queue (submit
second only on first's terminality) → confirm clean serialization and terminality detection via
the disjunction, and confirm the submitted `client_message_id` is **recoverable from
`conversation_messages_list` (as `otid` or otherwise)** — the exactly-once reconciliation in C4
depends on it, and note which message classes carry null `otid`; (S4) submitting socket dies
with one message queued *at the server* vs queued *locally* → demonstrate the loss mode and its
absence under local queueing; (S5) client A registers an external tool, starts a turn that will
call it, and dies mid-turn while B stays subscribed → record the fate of the in-flight tool
call and any pending approval (does it error, hang, or terminate the turn?), then A reconnects
and re-registers → can a subsequent call succeed? — this is the anchor's real value
proposition (safe worker restarts) for the turns that matter; (S6) turns submitted to two
*different* runtimes through one socket while both stream → is Q2's deferred-ack serialization
per-runtime or per-socket? (decides worker-socket sharding before C7, not after).

**Test scenarios:**
- Happy path: S1 turn runs to completion with output captured by B after A detaches.
- Edge case: S2 late-subscriber takeover; S1 repeated with B on a separate *process*; S6
  cross-runtime concurrency on one socket with per-connection `event_seq` intact.
- Error path: S4 server-side-queued message vanishes (expected, documents the hazard); locally
  queued message survives and submits; S5 orphaned tool call's observed fate recorded.
- Integration: terminality disjunction correctly closes S3's first turn (stop_reason observed;
  no reliance on `turn_finished`); S3 `client_message_id`→transcript mapping verified.

**Verification:** Findings doc states, with capture-file evidence: whether a second subscriber
prevents detach-cancellation (GO for anchor) or not (fallback: restart-cancels-turns accepted
and journal-marked; goals doc updated); the observed S5 tool-call fate (shapes C3/C7's
re-registration contract); the S6 answer (socket sharding decision); the S3 mapping answer
(shapes C4's reconciliation). Explicit go/no-go recorded before Phase B starts.

- [x] **Unit C2: Salvage map (R22)** *(docs/plans/2026-08-15-006-salvage-map.md)*

**Goal:** Assign every module of the two built packages to controller-side, surface-side, or
retire; decide evolve-in-place vs fork for the core package.

**Requirements:** R22.

**Dependencies:** None (parallel with C1).

**Files:**
- Create: `docs/plans/2026-08-15-006-salvage-map.md`
- Modify: none in this unit (assessment only).

**Approach:** Expected shape, to be confirmed against the code: controller-side — `ws.ts`,
`connection.ts`, `stream.ts`, `catchup.ts` (rebuilt on `otid`/`idempotency_key`), protocol
validation + version pins (rebound to vendor types), `test/helpers/mockServer.ts` + harness +
`double-fidelity` + contract/live/version-pin tests + `mutate.mjs`/`mutations.mjs`;
surface-side — terminal `render/sanitize/session/cli/main` + `spawnCli.ts` harness + deploy
wrapper; retire — `ownership.ts` attribution (controller stamps origin as data), `pointer.ts`
(subsumed by the registry), approval auto-deny responder (replaced by controller arbitration),
`fanout.ts`/`evict.ts`/`trust.ts` per-file judgment. Exception (operator decision 2026-08-15):
the terminal's existing direct raw-WS transport is **not** retired — it is kept installable as
the emergency break-glass client (see System-Wide Impact), so the salvage map must preserve a
working direct path alongside the controller transport. Recommendation to carry: **evolve
`letta-continuity-core` in place** into the controller's App-Server client library (its README
role barely changes; the mutation history stays attached) rather than forking.

**Verification:** Every source file in both packages appears exactly once in the map with a
destination and one-line justification; the mutation-harness entries that guard retiring code
are listed for retirement alongside it.

### Phase B — Controller core

- [x] **Unit C3: Controller skeleton — registry, hot set, anchor, supervision** *(soak verification pending its 1h window — all other criteria green)*

**Goal:** A supervised daemon that holds the anchor+worker connections, keeps the runtime
registry, and subscribes the hot set — no turns yet.

**Requirements:** R21, R26 (hot-set membership), R29 (multiple live Kinara threads), R16-idiom.

**Dependencies:** C1 (anchor go/no-go), C2 (salvage destinations).

**Files:**
- Create: `clients/continuity-controller/` package (`src/app-server-client/` from salvage,
  `src/registry.ts`, `src/hotset.ts`, `src/anchor.ts`, `src/state/` SQLite layer,
  `src/main.ts`), `scripts/run-continuity-controller.sh`,
  `clients/continuity-controller/launchd/com.ai-pa.continuity-controller.plist` (tracked
  reference copy; logs `~/Library/Logs/continuity-controller/`)
- Modify: `clients/letta-continuity-core/*` per the salvage map
- Test: `clients/continuity-controller/test/registry.test.ts`, `test/hotset.test.ts`,
  `test/anchor.test.ts` (against the salvaged mock App Server)

**Approach:** Registry rows = `{agent_id, conversation_id, label, hot|cold, surface origin
metadata}`; boot sequence = read registry → **both** anchor and worker issue `runtime_start`
(with `wait_for_replay`) per hot runtime — the worker's subscription is the one journaled
from, the anchor's exists for crash-overlap only (dual-subscription rule; a bare `sync` is not
shown to create a subscription). Hot-set changes: worker updates the registry and signals the
anchor, which re-reads (read-only) and adjusts its `runtime_start`s; the worker-only window on
a freshly-warmed runtime is journaled as a known exposure. Worker reconnect **re-registers all
external tools** before resuming submissions; any in-flight `external_tool_call_request`
orphaned by the restart is journaled FAILED-VISIBLE (contract shaped by C1's S5 answer).
Conversation creation goes through the registry (WS `conversation_create`; the pre-exist gotcha
lives here). SQLite opened in WAL mode, 0700 dir/0600 files, boot integrity check that degrades
visibly; backup.sh host-data inclusion decided and wired here. Forward-progress liveness:
periodic worker `sync` round-trip with deadline, surfaced via a liveness file the plist watchdog
can act on.

**Execution note:** Inherit the mutation-harness standard from the first commit: every
behavioural fix or load-bearing property added in C3+ lands with a named entry in the
controller's mutation list.

**Test scenarios:**
- Happy path: boot with 3 registry rows (2 hot) → exactly 2 `runtime_start`s on the anchor AND
  2 on the worker; worker-received deltas flow with the anchor absent, and vice versa (dual
  subscription proven in both directions).
- Edge case: registry row for a conversation the server doesn't know → visible boot warning,
  row marked broken, other rows unaffected. Cold row warmed on demand promotes to hot.
- Error path: App Server down at boot → bounded reconnect with `reconnecting` state persisted;
  recovery only counts after the stability window (per learnings). Anchor death → supervised
  restart re-subscribes; worker keeps serving reads from journal meanwhile.
- Integration: kill -9 the worker mid-`sync`; relaunch recovers registry from SQLite and
  re-attains subscriptions without duplicate `runtime_start` side effects.

**Verification:** Daemon runs under launchd on a clone backend for an hour with hot-set
subscriptions held; logs in `~/Library/Logs`; liveness file fresh; zero writes to live backend.

- [x] **Unit C4: Turn pipeline — queue, submission, terminality, journal** *(P3/P4 passed live on clone 2026-08-16)*

**Goal:** The controller becomes the sole submitter: accepts messages, queues per runtime,
submits, tracks the turn state machine, journals every event exactly once, marks failures
visibly.

**Requirements:** R21 (sole submitter, journal), G5; closes loss paths Q2/Q3; owns proofs
**P3** (replay complete and deduplicated after controller restart) and **P4** (silence
impossible after App Server kill), each with its reverting mutation.

**Dependencies:** C3.

**Files:**
- Create: `src/turns.ts` (state machine + per-runtime queue), `src/journal.ts` (reducer:
  `event_seq` order, `idempotency_key` dedup, `otid` reconciliation vs
  `conversation_messages_list`), `src/terminality.ts` (the disjunction)
- Test: `test/turns.test.ts`, `test/journal.test.ts`, `test/terminality.test.ts`, plus a live
  opt-in `test/live.controller.contract.test.ts` (clone backend, scratch agent)

**Approach:** Every accepted message gets a controller-minted `client_message_id` (nonce-prefixed
per origin surface — `request_id` is connection-local, per learnings) and a durable queue row
before any socket write; the row moves to `state=submitting` *before* the write, so a crash in
the write→ack window is reconcilable: on recovery, check `conversation_messages_list` for the
`client_message_id` (via `otid`, per C1's S3 answer; fallback key for null-`otid` rows =
snapshot message id + role) and resubmit only on confirmed absence. Submit next only on
terminality of the current; **wall-clock timeout sends `abort_message`, confirms, marks
FAILED-VISIBLE, then releases the queue** (never releases while the server may still be
running the turn). Journal is append-only with the turn's state transitions as first-class
rows; a turn orphaned by an App Server restart is marked FAILED-VISIBLE, never silently absent.
`subagent_id`-carrying deltas journal under the parent turn but never terminate it.

**Test scenarios:**
- Happy path: two messages to one runtime → serialized submission; journal shows both turns
  each reaching `stop_reason` terminality exactly once.
- Edge case: duplicate delivery of a replayed frame (same `idempotency_key`) journals once;
  `requires_approval` stop_reason does NOT terminate; a foreign turn (scheduler-injected)
  journals identically to a surface turn; poisoned `event_seq` (non-safe-integer) rejected
  without latching the watermark.
- Error path: `loop_error.is_terminal` → turn FAILED-VISIBLE with the error journaled; App
  Server killed mid-stream → on reconnect, `sync` + `conversation_messages_list`/`otid`
  reconciliation either completes the record or marks FAILED-VISIBLE (this is proof **P4**); a
  queued-but-unsubmitted message survives worker restart (SQLite) and submits after recovery;
  worker crash *between socket write and ack* → recovery reconciles via `client_message_id`
  and does not double-submit (exactly-once test); wedged turn → wall-clock timeout → abort →
  FAILED-VISIBLE → the next queued message actually runs (no head-of-line cascade).
- Integration: mock server's orphan-run and deferred-close behaviours (existing double
  fidelity) exercised against the full pipeline; live opt-in test runs one real tool turn end
  to end on the clone.

**Verification:** With the App Server restarted mid-turn during the live test, the journal
contains no turn in a non-terminal state and no duplicated message rows; kill-and-restart the
*controller* mid-stream and the journal holds each event exactly once, in order (proof **P3**);
the mutation list covers queue durability, dedup, the abort coupling, the submitting-window
reconciliation, and each disjunction arm.

- [x] **Unit C5: Surface protocol — core tier + auth + approvals arbitration** *(P5 passed live on permission-flipped clone; two-surface session green on launchd worker)*

**Goal:** The authenticated controller↔surface API: attach, replay-from-cursor, send, presence;
capability declaration; approval fan-out with first-answer-wins.

**Requirements:** R28, R21 (auth boundary), G8; approval settled facts; owns proof **P5**
(approval survives absence) — exercised on the **clone backend with a restrictive permission
mode set for the scratch agent** (safe there; the live unrestricted pin remains the production
tripwire), so approval arbitration is proven against a real `control_request`, not only mocks.

**Dependencies:** C4.

**Files:**
- Create: `src/surface/server.ts` (loopback WS + HTTP), `src/surface/protocol.ts` (the tiered
  contract — versioned from day one), `src/surface/auth.ts` (file-permission token now; ticket
  mint endpoint stubbed for C9), `src/approvals.ts`
- Test: `test/surface.protocol.test.ts`, `test/approvals.test.ts`, `test/auth.test.ts`

**Approach:** Attach = authenticate → declare capabilities → name conversation → receive journal
tail from a client-stated cursor + live events; send = hand over message, receive
`client_message_id` receipt (delivery is then C4's inspectable problem); presence =
focused/background/gone, feeding C7's routing. The **initial capability-set taxonomy is pinned
here** (the origin deferred it to this plan): `core` (mandatory: attach·replay·send·presence),
`abort` (operator-initiated turn kill), `approvals`, `rail` (conversation CRUD), `notify`
(awareness rendering), `direct` (direct-lane addressing), `subagent` (subagent-state
rendering) — with a stated degradation rule per set (approvals → another capable surface or
held-pending; notify → unseen markers; others → feature simply absent for that surface).
Loopback token per the Auth decision (0600 file, boot-generated, rotation; user-level code is
the trust boundary). Approvals: controller answers the App Server per settled facts and
arbitrates surfaces separately; if no surface holds the approval capability, hold pending +
unseen marker (recovery via `recover_approvals` on restart). Undeclared capabilities degrade
per R28, never drop.

**Test scenarios:**
- Happy path: two surfaces attached; a message from one appears on the other via journal+live
  within the same event ordering; replay from a stale cursor is gapless and duplicate-free
  (`otid`-keyed).
- Edge case: surface attaches mid-turn → receives the partial turn coherently; core-tier-only
  surface never receives approval frames but the approval still resolves (held or via another
  surface); presence flapping doesn't duplicate replay.
- Error path: bad token → clean rejection, no state; surface killed mid-send after receipt →
  message still delivered (C4 ownership); controller restart mid-attach → surface reconnect
  replays from cursor with zero loss (the G5 criterion).
- Integration: approval requested with two capable surfaces attached — first answer wins,
  second surface sees resolution, server acked exactly once; live opt-in on the
  permission-flipped clone: real `control_request` with zero surfaces attached → held pending,
  recovered across a controller restart via `recover_approvals`, answerable on next attach
  (proof **P5**); operator abort from a surface kills a running turn and the journal shows
  `aborted` terminality.

**Verification:** A scripted two-surface session on the clone demonstrates origin-doc success
criterion 1 (interchangeable use, nothing lost); protocol version + capability sets documented
in the package README.

### Phase C — Surfaces and delivery

- [x] **Unit C6: Terminal surface on the controller** *(UX contract green through the swap; detach-mid-turn inversion demonstrated live on clone)*

**Goal:** `letta-continuity` (terminal) speaks the surface protocol instead of raw App-Server
WS — the first real surface, core tier + approvals + direct-lane addressing.

**Requirements:** R28, R21 ("no surface connects directly"), origin success criterion 3.

**Dependencies:** C5 (protocol), C2 (salvage: render/sanitize/session survive).

**Files:**
- Modify: `clients/letta-terminal/src/session.ts` (transport swap behind the `SessionCore`
  seam), `src/cli.ts`, `src/main.ts`, `bin/letta-continuity`
- Test: `clients/letta-terminal/test/` — session tests against a controller stub; spawn-binary
  suite (`test/helpers/spawnCli.ts`) re-pointed at a controller test instance

**Approach:** The render/sanitize/NDJSON/exit-code behaviours are already reviewed and
mutation-bound — preserve them; only the transport under `SessionCore` changes. Add
`@specialist` address parsing (thin: the controller owns routing; the terminal just passes the
address through) and an abort command (the C5 `abort` capability). Attribution labels now come
from controller data, deleting the local attribution machinery — and **every string rendered
to the TTY passes the existing sanitizer**: attribution labels, conversation labels, route
aliases, awareness text, not just message bodies (some of these are Kinara-authored via
`manage_routes`; an escape-bearing label must not be able to spoof the attribution mark),
with a mutation-bound escape-sequence-label test.

**Test scenarios:**
- Happy path: interactive turn renders streamed output; `--json` NDJSON shape unchanged
  (golden-file diff against the pre-swap suite).
- Edge case: `@calendar check tomorrow` renders the specialist's reply inline with the
  specialist attribution mark; reconnect banner on controller restart, then gapless catch-up.
- Error path: FAILED-VISIBLE turn renders as failure and exits nonzero (mutation-bound, as
  today); controller unreachable → visible error, correct exit code, no hang (spawn-binary
  test through a real pipe, `| head` included).
- Integration: full binary spawn against a live controller+clone-server stack: type, see, kill
  terminal mid-turn, re-attach, turn completed and present.

**Verification:** The existing terminal UX contract (stdout/stderr split, sanitization, exit
codes) passes unchanged; detaching the terminal mid-turn no longer cancels the turn — the
inverse of the q5 capture, demonstrated live.

- [x] **Unit C7: Agent-initiated delivery — the 10:55 fix (G3)** *(10:55 passed live: real scheduler job → clone ingress → unseen → presented+consumed on attach; job inventory in 2026-08-15-006-scheduler-job-inventory.md)*

**Goal:** Scheduled and agent-initiated turns land, survive nobody-attached, and signal the
operator per R13(tag→default)/R14/R15.

**Requirements:** R3/G3, **R12** (the outbound direct inline card, clearly non-Kinara, with
the Kinara-catch-up bookkeeping C8's digest dedupes against), R13–R15, R29; origin success
criterion 2.

**Dependencies:** C4 (foreign turns journal), C5 (awareness events to surfaces).

**Files:**
- Create: `src/ingress/scheduler.ts` (`POST /v1/agents/{agent_id}/messages`, loopback),
  `src/routing/landing.ts` (tag → default precedence), `src/routing/awareness.ts`
  (interrupt·badge·muted + unseen markers), external tool `notify_operator` registration
- Modify: scheduler side is config-only (`LETTA_CALLBACK_URL` re-point) — executed at C-phase
  cutover rehearsal, not before
- Test: `test/ingress.scheduler.test.ts`, `test/routing.landing.test.ts`,
  `test/routing.awareness.test.ts`

**Approach:** Ingress accepts the scheduler's existing body shape verbatim, requires the
shared-secret bearer (see Key Decisions — it is Docker-wide-reachable via
`host.docker.internal`, so the secret is the control, not the bind address), and responds
**202-on-accept** (turn outcome = controller-journal truth). Landing resolves conversation by
explicit tag else the agent's default thread (relevance inference deliberately out); the turn
then runs through C4 exactly like a surface turn. R12's **direct inline card** is built here:
specialist output that bypasses Kinara renders as a clearly-non-Kinara card with a catch-up
record Kinara ingests (C8's digest dedupes against these by shared item id). Awareness
directive is per-item, urgency-inferred default `badge`, overridable (including deliberately
muted); `notify_operator` (external tool on Kinara's runtime, registered by the worker —
re-registered on every worker reconnect per C3) lets the agent set it — uncapped in the
initial build, per the documented-risk posture in Risks &amp; Dependencies (operator decision
2026-08-15). Unseen markers persist per
`{conversation, surface-consumption}` so a later attach shows what arrived while away. Focus
never moves (R14) — the controller has no mechanism to move it, by design. Cutover
prerequisite owned here: the `route=letta` **job inventory and per-job Docker→local agent-id
disposition** (jobs with no local equivalent need an explicit decision, not a silent 4xx).

**Test scenarios:**
- Happy path: scheduler POST with an explicit conversation tag lands in that thread; attached
  surface streams it live with a `badge` awareness event; untagged POST lands in the default
  thread.
- Edge case: POST while zero surfaces attached → turn completes (anchor), journal holds it,
  unseen marker set; next attach replays it (THE 10:55 test). Two POSTs to one runtime →
  serialized by C4's queue. `notify_operator(interrupt)` on a non-focused thread raises
  interrupt on the focused surface without moving focus.
- Error path: POST for an unknown agent → 4xx with body, journaled as rejected ingress
  (visible, G5); POST without the bearer secret → 401, journaled, no state; turn that errors
  mid-run still sets the unseen marker with failure state.
- Integration: end-to-end with a real scheduler-service job against the clone stack (rehearsal
  of the config re-point).

**Verification:** The motivating scenario passes live on the clone: a scheduled turn fires with
no client attached, is not cancelled, and is visibly waiting (badge + unseen) on next attach —
origin success criterion 2, first clause and second clause both.

- [x] **Unit C8: Direct lane — routes, inline rendering, Kinara digest** *(live on clone: accept→submit 1ms, zero Kinara turns in the exchange window, inline attributed render, digest batched to the route-origin thread)*

**Goal:** Predetermined operator↔specialist routing with zero model hops: explicit address,
per-thread binding, Kinara-managed routes; specialist threads render inline; Kinara catches up
asynchronously.

**Requirements:** R23–R26; origin success criterion "direct lane".

**Dependencies:** C6 (a surface that can address), C7 (awareness machinery reused for direct
inline rendering).

**Files:**
- Create: `src/routing/routes.ts` (route table: address aliases, thread bindings,
  Kinara-authored rules; every mutation journaled → auditable), `src/routing/digest.ts`
  (async Kinara catch-up), external tool `manage_routes` for Kinara
- Modify: `src/surface/protocol.ts` (inline-foreign-thread rendering events; bind/unbind
  commands), terminal bind/unbind command
- Test: `test/routing.routes.test.ts`, `test/routing.digest.test.ts`

**Approach:** A route resolves *before* any model call: address match → target
`{specialist, conversation}` (creating/warming it via the registry, hot per R26); bound thread →
everything routes until unbound. Routing semantics for Kinara-authored routes: targets
limited to registry-known specialists (a route must point at a real agent); **an explicit
`@address` always beats any authored route**; every route mutation is journaled with author
(R25's audit requirement) — no confirmation gates or push-notification of changes in the
initial build, per the documented-risk posture in Risks &amp; Dependencies. The exchange
journals in the specialist's thread; the operator's attached surface renders it inline via a
foreign-thread event carrying attribution.
Digest (decided 2026-08-15): recaps are **real turns** — there is no protocol operation that
injects context without producing a turn — **batched per Kinara conversation** and submitted
only when no operator message is pending for that runtime (**operator messages always preempt
digests** in the C4 queue); an exchange maps to the Kinara thread **whose route or binding
produced it**, else the default thread — never fanned out to all threads; digest turns carry a
**muted** awareness directive so neither the digest nor Kinara's acknowledgment badges the
operator; dedupe against R12 direct cards by shared item ids.

**Test scenarios:**
- Happy path: `@calendar …` from the terminal produces a specialist turn with no Kinara turn
  anywhere in the journal; the reply renders inline attributed; a digest row lands for Kinara
  and is delivered on her next idle.
- Edge case: bind thread → plain messages route direct; unbind restores Kinara lane; address
  for a cold specialist warms it (visible warm-up state, R18); Kinara authors a route via
  `manage_routes` → journaled audit entry, route active without restart.
- Error path: address matching no route/agent → visible error to the surface, nothing
  submitted; digest submission failing → retried, never silently dropped.
- Integration: latency evidence — capture timestamps showing direct-lane submission latency is
  controller-only (no inference in the path) vs the Kinara-lane baseline.

**Verification:** Origin success criterion for the direct lane demonstrated with timestamped
captures; route audit log shows every route mutation with author.

### Phase D — Rich surface, orchestration, cutover

- [ ] **Unit C9: Web surface (rail + full capability set)**

**Goal:** Browser surface on the controller: conversation rail (create/rename/fork/
archive-with-undo), live chat, awareness rendering — restoring pa-web-ui's conversation
features on the shared runtime (G6).

**Requirements:** R28 (full tier), R6/G6; browser-mediator mandate.

**Dependencies:** C5 (ticket auth), C7 (awareness), C8 (inline direct rendering). Coarser than
earlier units by design; refine at pickup.

**Files:**
- Create: web app package (framing decided at pickup — see deferred), controller ticket-mint
  endpoint behind the existing authenticated HTTPS path
- Modify: `src/surface/auth.ts` (tickets), registry (import of `pa_web.conversation_meta`
  labels/parent links)
- Test: surface-protocol conformance suite reused; Playwright smoke for rail actions.

**Pickup gate:** expand this unit to full unit format (files, scenarios, verification) and
record it in this plan before implementation begins.

**Approach:** Rail = registry queries + WS `conversation_*` RPCs through the controller
(delete = archive + undo window, per the WS protocol's archive semantics). Live chat over the
same surface protocol as the terminal — the point of R28 is that this unit adds *capabilities*,
not architecture. Tickets per the Auth decision (single-use, seconds-TTL, first-frame auth,
never in the URL); the concrete authenticated HTTPS path is **named here and recorded as a
security dependency** of the controller boundary. The `conversation_meta` import is
**idempotent and re-runnable** (keyed on `conversation_id`; registry wins after the first
controller write) because pa-web-ui keeps writing until C10b retires its chat transport — the
final delta-import happens in the cutover runbook.

**Test scenarios (initial):** rail CRUD round-trips including fork parent links and
archive-undo; two browsers + one terminal on one conversation, nothing lost; ticket
expiry/renewal; unseen badges match journal truth after a detached scheduled turn.

**Verification:** Origin success criteria 1 and 3 demonstrated across terminal + browser.

- [ ] **Unit C10a: Orchestration pattern registry (R27)**

**Pickup gate:** expand to full unit format in this plan before implementation begins.

**Goal:** Named patterns: participants, fan-out via `/v1/responses`, synthesis target;
invocable by Kinara (`fan_out`/pattern tool), operator, scheduler; results to
Kinara-as-reporter when she didn't originate.

**Requirements:** R27.

**Dependencies:** C7 (delivery for reporter results), C8 (external-tool machinery). **Not a
dependency of the cutover** — fan-out callers use the unchanged `/v1/responses` shim, so C10b
may ship first.

**Files:** `src/patterns/` + tests.

**Test scenarios (initial):** one pattern invoked three ways yields the same journaled result
differing only in presenter; pattern participant failure → partial-result synthesis with the
failure visible.

**Verification:** A named pattern is invoker-agnostic (origin success criterion), demonstrated
in the journal.

- [ ] **Unit C10b: Cutover (R19)**

**Pickup gate:** expand to full unit format in this plan before implementation begins.

**Goal:** Clone-and-validate rehearsal already done piecewise in C3–C9; execute for real —
load both plists, re-point `LETTA_CALLBACK_URL` (with the bearer secret and the per-job
agent-id dispositions from C7's inventory), run the final `conversation_meta` delta-import,
flip terminal then web, quiesce incumbent writers, retire the
`scripts/restore-letta-app-server.py` stopgap; instant rollback = re-point back + unload.

**Requirements:** R19/G7.

**Dependencies:** C7–C9 for the full cutover. C10a explicitly not required. **Staged per the
execution goal (`docs/plans/2026-08-15-007-feat-continuity-controller-goal.md`): the
terminal-first portion (services live, scheduler re-pointed, `lc-local-backend` writers
quiesced) executes after C8 — pa-web-ui runs on the separate Docker backend and continues in
parallel; the web flip and pa-web-ui chat-transport retirement land with C9 in the follow-on
goal.**

**Files:** cutover runbook `docs/runbooks/continuity-controller-cutover.md` (steps, checks,
rollback, the 202-accept semantics change, the break-glass posture); modify launchd reference
plists as needed.

**Test scenarios (initial):** cutover rehearsal on clone passes all origin success criteria
and the full **P1–P5 checklist**; rollback rehearsal restores incumbents in under a minute.

**Verification:** Post-cutover soak: the six origin/goals success criteria pass on the live
system; P1–P5 re-verified; goals doc statuses updated (G1–G8) with a new "last reality check"
date.

## System-Wide Impact

- **Interaction graph:** scheduler-service (config re-point only), letta-push-receiver
  supervisor (peer service, unchanged), enrichment `/v1/responses` callers (unchanged),
  pa-web-ui (runs in parallel until C10b retires its chat transport; Task Review Sidebar ports
  separately), `~/bin/letta-continuity` wrapper (transport swap), launchd service set (+1
  service, +1 if the anchor is its own process).
- **Error propagation:** platform failures surface as journal FAILED-VISIBLE states → surface
  render + nonzero exits; **controller-down = total operator lockout** — stated plainly: a
  worse availability floor than the peer-client model, where a healthy App Server stayed
  reachable from any terminal. Accepted, with a **full break-glass** (operator decision
  2026-08-15): the direct raw-WS terminal client remains installable for emergencies, with the
  runbook stating explicitly that single-submitter ownership and attribution guarantees are
  suspended while it is in use. Surfaces otherwise show reconnecting (they hold no durable
  state to lose); App-Server-down = controller journals the gap and reconciles via
  `sync`/`conversation_messages_list` on return.
- **State lifecycle risks:** journal double-ingest (guarded by `idempotency_key`/`otid` tests),
  registry divergence from server conversation list (reconciled at boot; broken rows visible),
  SQLite growth (retention deferred, R18 prune deliberate), unseen-marker leaks (cleared on
  surface-consumption acknowledgment only).
- **API surface parity:** the surface protocol is the parity boundary by design — terminal and
  web consume the same contract, so parity gaps become missing capability declarations, not
  divergent code paths. The scheduler dialect endpoint must stay bug-compatible with
  `actions.py`'s body shape.
- **Integration coverage:** the clone-stack end-to-end suite (spawned controller + spawned
  `letta server` + spawned terminal binary) is the load-bearing layer, per the institutional
  finding that some defects only appear through real pipes and real processes.

## Risks & Dependencies

- **P1 fails (anchor doesn't hold turns)** → fallback documented in C1; G2/G3 wording in the
  goals doc changes; the rest of the architecture stands.
- **Controller SPOF** → anchor split (blast radius), launchd supervision, surfaces reconnect,
  authority in SQLite not memory; accepted residual: a dual anchor+worker outage cancels
  in-flight turns — journaled visibly.
- **Server upgrades change the WS protocol** → vendor-type binding + running-server version
  gate + the live contract test against the clone; the pin fails loudly, not silently.
- **#99-class silent stalls** → wall-clock backstop arm of the terminality disjunction +
  supervisor's forward-progress probe remain independent detectors.
- **Agent-held control-plane tools — documented, accepted risk (operator decision
  2026-08-15):** `manage_routes`, `notify_operator`, and `fan_out` are levers a prompt-injected
  agent could pull (Kinara routinely ingests external email/Slack/web content). The initial
  build ships **journal audit only** (R25) — no rate caps, fan-out budgets, or confirmation
  gates. Staged hardening options recorded for when evidence warrants them: per-runtime
  interrupt rate caps (excess degrades to badge), per-invoker fan-out budget/concurrency caps,
  awareness events or operator acknowledgment on thread-rebinding.
- **Scope gravity in Phase D** → C9/C10a/C10b are deliberately coarse, each carrying an
  explicit pickup gate: expand to full unit format in this plan before implementation begins.
- **Sequencing:** C1 gates Phase B; C5 gates all surfaces; nothing before C10 touches live
  writers.

## Documentation / Operational Notes

- Update `docs/architecture/multi-surface-continuity-goals.md` statuses at C10 (and at C1 if
  the anchor answer changes G2's qualification).
- New runbooks: controller cutover (C10); controller ops (logs, liveness file, SQLite location,
  clone-stack test invocation).
- Tracked-reference-plist convention: both new plists get repo reference copies; live copies
  remain hand-synced (existing known gap, unchanged).
- The salvage map (C2) doubles as the deprecation notice for retired modules and their mutation
  entries.

## Sources & References

- **Origin document:** `docs/brainstorms/2026-08-15-continuity-controller-requirements.md`
- Adopted design: `docs/plans/2026-08-15-continuity-fresh-design-sketch.md`
- Platform truth: `docs/followups/2026-08-15-app-server-docs-vs-implementation.md`,
  `docs/followups/2026-08-15-continuity-ownership-live-captures.md` (+ `docs/followups/captures/`),
  `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md`
- Standards: `docs/plans/2026-08-14-001-fix-continuity-test-binding-goal.md` (falsifiability),
  `docs/followups/2026-08-13-continuity-remediation-closeout.md` (approval settled facts)
- Superseded but load-bearing history: `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md`,
  `docs/plans/2026-08-15-005-continuity-ownership-design-brief.md`,
  `docs/plans/2026-08-15-004-continuity-fix-forward-closeout.md`
- External: https://docs.letta.com/platform/app-server (overview, quickstart,
  protocol-lifecycle, integration-patterns, external-tools)
