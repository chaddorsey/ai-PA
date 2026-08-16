# Multi-Surface Continuity on the App Server — A Fresh Design Sketch

**Status:** ADOPTED as the target architecture (2026-08-15 brainstorm). Decisions and new
requirements R21–R29 are recorded in
`docs/brainstorms/2026-08-15-continuity-controller-requirements.md`; the built peer-client
packages are to be assessed salvage-only. §10 below is annotated with resolutions.

**Method note.** This sketch was written *code-blind*, on purpose: its inputs are
`docs/architecture/multi-surface-continuity-goals.md`, the origin brainstorm
(`docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md`, R1–R20 and its
resolved routing/lifecycle decisions), and the published App Server documentation (overview,
quickstart, protocol lifecycle, integration patterns, external tools —
https://docs.letta.com/platform/app-server). It deliberately does not look at the client packages
built to date. The point is to derive the architecture the *platform documentation* leads to, so it
can be compared against the approach we actually took, and the differences examined on their merits.

**Revision (same day):** incorporated the origin doc's resolved decisions (R12–R15 routing,
R18 hot/cold/archive, spike-verified protocol facts) and operator guidance on fleet routing:
surfaces span basic-terminal → rich-web; orchestration/parallel-agent patterns must be flexible
and configurable with Kinara as key orchestrator or reporter; and **latency is the top
sensitivity**, so predetermined routes may send operator messages/commands *directly* to
specialist agents rather than through Kinara.

---

## 1. The problem, restated in platform terms

The goals document wants one live conversation, followed across surfaces, with the agent working
whether or not anyone is watching, and nothing silently lost. The platform gives us most of the
machinery for free — and then takes three specific things away:

1. **A turn does not outlive its last observer.** When no subscribed client is active, the App
   Server cancels the active turn. ("If no other subscribed client is active, App Server requests
   cancellation of its active turn" — protocol lifecycle.)
2. **A client's queued input dies with it.** Disconnect cleanup removes that connection's queued
   input, and nobody else is told.
3. **Browsers cannot reach the runtime directly.** A browser cannot send `Authorization: Bearer`
   on a WebSocket upgrade, so every browser-class surface (web, phone, glasses) needs an on-box
   mediator regardless of preference.

All three constraints share a structure: **they punish ephemeral connections for owning durable
responsibilities.** A surface is ephemeral by definition — the operator closes the laptop, the
phone sleeps, the terminal exits. Any design in which an ephemeral connection is the subscriber
that keeps a turn alive, the submitter that keeps queued input alive, or the credential-holder
that authenticates, will keep tripping over these constraints one at a time.

The App Server's own integration-patterns page names the missing piece: a **controller**. "The
server owns agent execution, tool preparation, turn queueing, and event streaming. Your
application owns product state." The docs then describe exactly what that controller should do:
keep a runtime registry in its own database, hold per-runtime turn locks, queue messages during
active runs, build event handlers as reducers over an append-only log, recover from its own
database because "App Server can restart," and extend the system through external tools rather
than protocol extensions.

So the design this documentation leads to is not "N peer clients on one runtime." It is:

> **One sole-owner App Server, one resident controller that is the App Server's only real client,
> and surfaces as thin, ephemeral views of the controller.**

## 2. The shape

```
                                   ┌──────────────────────────────┐
                                   │  App Server (sole owner)     │
                                   │  letta server --backend local│
                                   │  ws://127.0.0.1:<port>       │
                                   │  state: ~/.letta/lc-local-…  │
                                   └──────────────▲───────────────┘
                                                  │ one WS, always up
                                                  │ runtime_start per active
                                                  │ {agent, conversation}
┌───────────┐   authenticated      ┌──────────────┴───────────────┐
│ terminal  │◄────────────────────►│  Continuity Controller       │
├───────────┤   local WS/HTTP      │  (resident daemon, launchd)  │
│ web       │◄────────────────────►│  • permanent subscriber      │
├───────────┤   (mediator is       │  • sole submitter of input   │
│ phone     │◄──── mandatory ─────►│  • journal + runtime registry│
├───────────┤    for these)        │  • notification router       │
│ glasses   │◄────────────────────►│  • surface auth boundary     │
└───────────┘                      └──────────────┬───────────────┘
                                                  │
                                     ┌────────────▼────────────┐
                                     │ registry + journal store│
                                     │ (SQLite or Postgres)    │
                                     └─────────────────────────┘
```

Two resident processes, both supervised by launchd:

- **The App Server** — `letta server --backend local --listen ws://127.0.0.1:<port>`,
  loopback-only, no WS auth (the platform waives auth on loopback). It is the only writer of agent
  state and hosts the whole fleet of local agents in one process. Nothing else ever touches
  `~/.letta/lc-local-backend`.
- **The Continuity Controller** — a small daemon holding **one WebSocket** to the App Server, with
  a `runtime_start` subscription for every *active* `{agent_id, conversation_id}` pair. It is the
  durable half of every responsibility the platform punishes ephemeral clients for holding.

Surfaces — terminal, web, later phone and glasses — never connect to the App Server. They connect
to the controller, over an authenticated local API, and are free to be as ephemeral as they like.

## 3. Why a resident controller, specifically

Each of the three platform constraints is dissolved — not worked around — by the same move:

| Platform constraint | Under peer clients | Under a resident controller |
|---|---|---|
| Turn cancelled when last subscribed client goes | Needs a separate "keep-alive subscriber" bolted on, which then holds none of the context about *why* the turn matters | The controller **is** the permanent subscriber. There is always ≥1 active subscribed client, by construction, for every runtime it has started. |
| Queued input dies with the submitting connection | Every surface must implement resubmission/detection it cannot actually perform (the loss is invisible to it) | Surfaces never send `input`. They hand messages to the controller; the controller — which does not disconnect — is the submitting connection for everything. The failure mode ceases to exist. |
| Browser-class surfaces need a mediator anyway | The mediator exists *in addition to* the direct-WS path, so there are two client stacks to keep honest | The mediator **is** the controller. There is one client stack; the terminal uses the same door the browser does. |

Beyond the constraints, the controller is where the goals that are "not started" naturally live:

- **G3 (agent-initiated turns reach the operator).** A scheduled poke arrives at the controller
  (HTTP endpoint the scheduler calls), which ensures the runtime is started, submits the turn,
  journals every delta, and then executes the **R12–R15 routing model** the origin doc already
  resolved — which is controller-shaped through and through: *landing* by explicit
  conversation-tag → relevance-inferred thread → default thread (R13, with the relevance
  classifier being a controller concern); *focus never auto-moves* (R14); *awareness* as a
  per-item tiered directive — interrupt · badge · muted — urgency-inferred by default,
  deliberately overridable (R15), delivered to attached surfaces as a controller event and
  persisted as an unseen marker when none is attached. Specialist output is
  **mediated-by-default through Kinara, with a direct inline card as the time-critical
  fallback** (R12) — and both the mediation hand-off and the card-then-Kinara-catches-up
  bookkeeping are controller state, not agent memory. Because the controller is permanently
  subscribed, the turn runs to completion with nobody watching, and its output is in the
  journal when the next surface attaches. This is the motivating "10:55 reminder" problem,
  closed structurally.
- **G5 (nothing silently lost).** The controller maintains a per-conversation, append-only
  **journal** of every event, exactly the reducer-over-a-log pattern the docs recommend: track
  `event_seq` per connection, deduplicate on `idempotency_key`, call `sync` on sequence gaps.
  Every submitted turn carries a controller-issued `client_message_id` and moves through an
  explicit state machine — `accepted → submitted → streaming → terminal` — where terminal is one
  of `stop_reason | loop_error | error_message | aborted`. A turn that leaves the machine any
  other way (App Server restart, gap that `sync` cannot reconcile) is marked **visibly failed**
  in the journal and pushed to surfaces as a failure, never rendered as silence.
- **R18 (bounded hot/cold/archive lifecycle).** "Constant-on" is a *bounded hot set*, not
  every conversation forever. The controller's registry is where hot/cold status lives: HOT
  runtimes stay subscribed (instant attach, agent-initiated turns fire with no warm-up); COLD
  conversations are warmed — `runtime_start` issued — on surface attach *or* when an inbound
  agent-initiated turn targets them; stale threads prune to `~/.letta/history-archive`
  (qmd-recallable). A peer-client design has nowhere natural to put this policy; the controller
  *is* the hot-set manager. This is also a **latency lever**: the warm-up cost of a cold runtime
  is one of the few real latency items on the box, so hot-set membership should be tunable
  (e.g. Kinara's live threads plus any specialist with a predetermined direct route — §4).
- **G8 (safe reach).** The App Server stays loopback-only with no token to leak. The controller
  is the *single* authentication boundary for all surfaces — and because browsers can't send WS
  headers, it does browser-shaped auth (cookie session, or short-lived ticket minted over HTTPS
  and presented in the WS URL). Off-box reach = the existing Cloudflare-tunnel path terminating
  at the controller. One boundary, decided once, instead of per-surface.

**The cost, stated honestly:** the controller is a single point of failure and a second thing to
supervise, and it re-implements fan-out to surfaces that the App Server would have done for peer
clients. Mitigations: it is small and nearly stateless (its authority lives in the registry +
journal store, so a crash-restart rebuilds by re-reading the registry, re-issuing `runtime_start`
per active runtime, and letting the documented startup replay plus its own journal reconcile);
launchd restarts it; surfaces already handle reconnect-and-replay because that is their normal
attach path. A hanging-but-alive controller (the G7 concern) is detected the same way it detects
a hanging App Server: a periodic `sync` round-trip with a deadline, surfaced to launchd via a
liveness file or a watchdog exec.

## 4. The fleet: many local agents, one felt agent, latency-first routing

The App Server hosts multiple agents concurrently in a single process, and the 2026-08-12 spike
proved the substrate: injection is **scoped** to a specific `{agent_id, conversation_id}` (not a
broadcast), multiple agents and multiple conversations per agent run turns **concurrently**
(the one-active-turn constraint is per-runtime, not global), and an agent's sub-delegation
streams inline to subscribers via `update_subagent_state`. So "a series of local Letta agents"
costs nothing architecturally: the controller's registry holds rows for every
`{agent_id, conversation_id}` it cares about and subscribes to the hot ones.

The felt experience is **one agent (Kinara), with the fleet as specialists behind her** — but
the operator's guidance sharpens this: orchestration and parallel-agent patterns must be
**flexible and configurable**, with Kinara as key orchestrator *or reporter*, and **latency is
the top sensitivity**. The latency arithmetic is what shapes the design. On one box, transport
hops are noise: surface→controller→App Server is loopback IPC, well under a millisecond. The
hops that actually cost are **LLM turns** (a Kinara mediation pass is a full model inference —
seconds) and **cold-runtime warm-up** (R18). So the routing layer's job is to *skip model hops
when they add nothing*, while keeping the single-agent feel when they do.

That gives the controller a **configurable routing table** with three lanes, symmetric across
both directions:

1. **Kinara lane (default).** Operator messages go to Kinara's conversation; specialist output
   reaches the operator mediated through Kinara in her own voice (R12). This is the felt-single-
   agent path, and it pays one model hop for prioritization and voice — worth it by default.
2. **Direct lane (predetermined, latency-critical).** *Inbound:* when a message/command matches
   a predetermined route — an explicit address, a command prefix, a per-conversation binding,
   or a configured classifier rule — the controller submits it **directly to the specialist's
   runtime**, zero Kinara hops. The turn renders clearly attributed as that specialist, and
   Kinara is informed asynchronously (a catch-up digest into her context) rather than serially.
   *Outbound:* the same lane R12 already defines — the direct inline card, clearly marked as
   not-Kinara, with Kinara catching up on her next turn. The two directions should share one
   route-table representation and one attribution/catch-up mechanism; they are the same
   pattern mirrored. Specialists with standing direct routes belong in the hot set (R18) so
   the lane is *actually* fast end-to-end.
3. **Fan-out lane (parallel derivation).** For orchestration patterns — fan out a question to
   N specialists, synthesize — the stateless OpenAI shim (`--openai-api`,
   `POST /v1/responses`) is the right transport: fresh conversation per request, no
   subscription lifecycle, no observer problem, naturally parallel. The controller (or Kinara,
   via an external tool) fans out, and the synthesis lands wherever the pattern says: to
   **Kinara-as-orchestrator** (she dispatched and synthesizes) or to
   **Kinara-as-reporter** (the controller ran a configured pattern and hands her the results
   to present). Both are rows in the same pattern config, not separate mechanisms.

Where Kinara herself initiates, the controller registers **external tools** on her runtime —
`dispatch_task`, `notify_operator`, `fan_out`, `lookup_…` — the docs' "external tools as
commands" pattern, keeping task, routing, and notification state in the controller rather than
encoded in agent memory. `notify_operator` makes G3's signalling an *agent-callable* ability
whose implementation is the controller's routing policy; `fan_out` makes lane 3 available to
Kinara-as-orchestrator without her knowing the transport.

Two cautions. External tools bind to the registering connection and unregister when it
disconnects — fine for a resident controller, and one more reason surfaces should not register
anything. And the spike's gotcha stands: **conversations must pre-exist before WS inject**
(only `default` auto-creates) — conversation creation is a controller registry operation, which
fits, since the controller owns the rail anyway.

## 5. Surfaces as thin views

A surface's whole contract with the controller:

- **Attach**: authenticate; name a conversation (or ask for the rail — the controller's registry
  is what a conversation list *is*); receive journal tail + live events from a stated cursor.
- **Send**: hand over a message; receive the controller's `client_message_id` as the receipt.
  Delivery is now the controller's problem, and its state machine is inspectable.
- **Signal state**: tell the controller "I am focused / backgrounded / gone" so notification
  routing (interrupt vs badge vs muted) has something to route on.
- **Approvals**: `control_request` reaches the controller, which fans it to attached surfaces;
  first answer wins; the others see the resolution as an event. If nobody is attached, the
  approval is held pending (the platform treats `requires_approval` as a continuation boundary,
  not a terminal state, and `recover_approvals` exists for exactly this) and is surfaced as a
  badge-level notification.
- **Attribution**: the controller stamps every accepted message with its origin surface and
  operator identity in the registry, so "who said this, from where" is controller data — not
  something inferred from which WS happened to carry the frame.

Surfaces will span a **broad capability range** — a basic terminal at one end, rich web
interactions at the other, phone and glasses stranger still — so the controller protocol should
be **tiered, not uniform**: a small mandatory core (attach · replay-from-cursor · send · signal
presence) that a minimal surface can implement in an afternoon, plus optional capability sets a
surface declares at attach — rail CRUD (create/rename/fork/delete-with-undo), approvals,
notification rendering (interrupt/badge/muted), direct-lane addressing, subagent-state rendering
(`update_subagent_state` inline, for surfaces rich enough to show Kinara's delegation live).
The controller degrades per-surface: a capability a surface didn't declare routes elsewhere
(e.g. an approval falls to another attached surface, or holds pending) rather than being lost.

The terminal client under this design is small: readline/TUI + the core tier, opting into
approvals and direct-lane addressing. The web client is the same protocol from a browser with
the full set. Criterion 4 — "adding the next surface is additive" — falls out: a new surface
implements the core tier against the controller and inherits continuity, journal replay,
notifications, and auth without touching the App Server protocol at all. The App Server wire
protocol has exactly one consumer to keep correct.

## 6. What each goal gets

| Goal | How this design meets it |
|---|---|
| G1 one owner | Unchanged: the App Server is the sole writer. The controller adds a second resident process but owns no agent state — only product state (registry, journal, notification policy), which is the division the platform documents. |
| G2 continuously available | The controller's permanent subscription means a turn always has an active subscribed client. **Proof obligation P1** (§8) tests the platform actually honors this. |
| G3 initiated turns reach the operator | Controller endpoint for the scheduler + `notify_operator` external tool + routing policy + unseen markers. Survives zero-attached because of G2's mechanism. |
| G4 no privileged surface | Structurally true: every surface speaks the same controller protocol; the mandatory browser mediator is not a special case but the only case. |
| G5 nothing silently lost | Controller-owned submission kills the queued-input loss; journal + turn state machine + `sync`-on-gap makes every other loss visible by construction. |
| G6 stop choosing | Rail/create/rename/fork live in the controller registry, so *every* surface gets them; terminal ergonomics are the terminal's own. |
| G7 reversible consolidation | Incumbents keep running while the controller runs alongside; surfaces flip one at a time by changing what they connect to; rollback is flipping back. Supervision is two launchd services plus the watchdog `sync` probe. |
| G8 safe by default | App Server loopback-only/no-auth; controller is the one authenticated boundary; off-box via the tunnel. |
| G9 falsifiable | The controller's contract is testable against a real spawned `letta server` binary; §8 lists the named proofs, each with a mutation that must fail it. |

## 7. Deliberately *not* in this design

- **No direct-to-App-Server surface clients.** Even the terminal goes through the controller. The
  moment one surface is a peer of the controller on the same runtime, the queued-input and
  attribution holes reopen for that surface, and there are two client stacks again.
- **No out-of-band delivery as primary path** (per the goals' non-goals). Push/Slack, if ever,
  is a notification-routing *target* inside the controller, not a channel that carries turns.
- **No protocol extensions.** Everything app-specific is external tools or controller API,
  per the integration-patterns guidance.
- **No migration of the enrichment/task pipelines' interactive behaviour.** They may share the
  App Server (the `/v1/responses` lane), but they are not surfaces.

## 8. Proof obligations (the falsifiable core)

Named tests against a real `letta server` process, each with a reverting mutation:

- **P1 — the anchor holds.** With the controller subscribed and one surface attached, start a
  long tool turn, detach the surface: the turn must complete and its output be in the journal.
  This is *the* load-bearing assumption (the docs say cancellation happens when "no other
  subscribed client is active"; the live capture in the goals doc had zero clients, and the
  2026-08-12 spike — which proved subscribe/inject/broadcast — never tested detach-during-turn,
  so neither prior result answers this). If P1 fails — if a merely-subscribed-but-quiet
  controller doesn't count as "active" — the design degrades explicitly: the controller must
  additionally hold/refresh activity (and if *that* fails, G2/G3 are platform-blocked and the
  goals doc's open decision comes back to the operator.)
- **P2 — no orphaned queue.** Submit via controller, kill a surface mid-queue: the turn still
  runs. Then the adversarial half: a *direct* WS client submitting and dying loses its turn —
  demonstrating the loss mode exists and the controller is what removes it.
- **P3 — replay is complete and deduplicated.** Kill and restart the controller mid-stream:
  after `runtime_start` replay + journal reconciliation, the journal contains each event exactly
  once (`idempotency_key`), in order (`event_seq`), or a visible failure marker.
- **P4 — silence is impossible.** Kill the App Server mid-turn: the journal shows the turn
  leaving the state machine as a visible failure, and an attached surface renders it as one.
- **P5 — approval survives absence.** Trigger `control_request` with no surface attached;
  attach later: the pending approval is presented (via `sync`/`recover_approvals`) and answerable.

## 9. Cutover sketch (G7)

1. Stand up the supervised App Server + controller pair beside the incumbents (distinct port;
   the deliberate not-yet-loaded launchd situation ends here, because the controller pair is
   *new* services, not a takeover of an incumbent's port).
2. Run the proof suite P1–P5 against the pair.
3. Flip the terminal surface; live with it; flip the web surface; incumbents idle but intact.
4. Retire incumbents only after the soak; rollback at any step is re-pointing a surface.

## 10. Open questions for the comparison discussion

1. **Does "subscribed" mean "active"?** P1 is the whole ballgame. If the platform's cancellation
   trigger is stricter than subscription, the controller needs whatever "active" means — and the
   docs don't define it precisely.
2. **Fork/undo semantics.** The registry can *model* fork/rename, but whether conversation
   forking is a platform operation or a controller-level construct (new conversation + journal
   copy) needs a docs/capture answer.
3. ~~How thin is thin?~~ **Resolved by operator guidance (2026-08-15): a tiered surface API**
   (§5) — a small mandatory core plus declared capability sets — not a frame proxy. The range
   basic-terminal → rich-web is a requirement, so the protocol must degrade per surface.
4. ~~One controller or one per agent?~~ **Resolved by operator guidance (2026-08-15): one.**
   The routing table (Kinara lane / direct lane / fan-out lane, §4) is inherently cross-agent —
   a per-agent controller could not route around Kinara, and latency-first routing is the point.
5. ~~How are direct routes predetermined?~~ **Resolved (R25):** explicit address + per-thread
   binding + Kinara-managed routes (controller-owned table, auditable); static operator rule
   config rejected. Digest representation deferred to planning.
6. ~~Where do orchestration patterns live?~~ **Resolved (R27):** one controller pattern
   registry, invocable by Kinara (orchestrator), operator, or scheduler (Kinara as reporter);
   ad-hoc Kinara fan-outs use the same machinery.
7. ~~Direct-lane conversation model.~~ **Resolved (R24):** the specialist's own thread,
   rendered inline with clear attribution; never mirrored into Kinara's transcript; Kinara
   catches up via async digest.
8. ~~Multiple concurrent Kinara conversations.~~ **Resolved (R29): yes, from day one** —
   R13/R15 are load-bearing in the first milestone.
