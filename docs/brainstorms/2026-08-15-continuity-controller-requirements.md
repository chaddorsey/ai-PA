---
date: 2026-08-15
topic: continuity-controller
---

# Continuity Controller — Requirements (extends R1–R20)

**Lineage.** This extends the origin brainstorm
(`docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md`, R1–R20) and adopts
the code-blind design sketch (`docs/plans/2026-08-15-continuity-fresh-design-sketch.md`) as the
target architecture. R-numbers continue the origin series. The goals document
(`docs/architecture/multi-surface-continuity-goals.md`) remains the statement of intent; this doc
records the 2026-08-15 architecture and routing decisions that get us there.

## Problem Frame

The three platform constraints discovered 2026-08-15 (a turn is cancelled when its last observer
detaches; queued input dies with its submitting connection; browsers cannot authenticate a WS
upgrade) all punish **ephemeral connections holding durable responsibilities** — which is exactly
what the peer-client architecture asks surfaces to do. The App Server's own integration guidance
prescribes the alternative: a resident *controller* owning product state. Separately, the operator
has sharpened the fleet requirements: surfaces from basic terminal to rich web; orchestration and
parallel-agent patterns that are flexible and configurable with Kinara as key orchestrator or
reporter; and **latency as the top sensitivity**, meaning predetermined routes may bypass Kinara
entirely.

## Requirements

**Architecture adoption**
- R21. A resident **Continuity Controller** (launchd-supervised, beside the sole-owner App Server)
  is the App Server's only real client: permanent subscriber for every hot runtime, sole submitter
  of all `input`, keeper of the per-conversation journal (reducer over `event_seq` /
  `idempotency_key`, `sync` on gaps), executor of the R12–R15 routing model, registrar of all
  external tools, and the single authenticated boundary every surface connects through — terminal
  included. No surface connects to the App Server directly.
- R22. **Salvage-only reconciliation.** The controller architecture is decided; the built
  peer-client packages (`letta-continuity-core`, `letta-terminal`) are assessed strictly as a
  parts inventory — candidate reuse: the wire-protocol layer as the controller's App-Server-side
  client; the terminal UX as a surface on the new controller protocol. No keep-vs-pivot
  comparison of architectures is owed. Attribution and turn-completion ownership (the open design
  brief) are resolved by architecture: they are controller data.

**Routing — extends R12–R15**
- R23. The controller holds a **configurable routing table with three lanes**: the **Kinara lane**
  (default; mediated, her voice), the **direct lane** (predetermined operator↔specialist routes,
  zero model hops), and the **fan-out lane** (parallel derivation via the stateless
  `/v1/responses` shim). Outbound R12 (mediated-by-default, direct-card fallback) and the inbound
  direct lane share one route representation and one attribution/catch-up mechanism.
- R24. A **direct-lane exchange lives in the specialist's own `{agent, conversation}` thread**,
  rendered inline in the operator's current surface with unmistakable specialist attribution;
  it is never mirrored into Kinara's transcript. Kinara receives an **asynchronous catch-up
  digest** so directness never becomes divergence.
- R25. Supported **route forms**: (a) **explicit address** (e.g. `@calendar …`), deterministic on
  every surface; (b) **per-thread binding** (a conversation bound to a specialist until unbound);
  (c) **Kinara-managed routes** — Kinara authors/updates routes via an external tool; the table
  remains controller-owned and every change is visible and auditable. Deliberately excluded:
  hand-maintained static rule config.
- R26. Specialists holding standing direct routes are members of the **hot set** (R18), so the
  direct lane is fast end-to-end — no cold warm-up on a latency-motivated route.

**Orchestration — fan-out lane**
- R27. One **pattern registry** in the controller: named patterns declaring participants, fan-out
  shape, and synthesis target. Invocable three ways — by Kinara (via her `fan_out` /
  pattern-invocation external tool: **Kinara-as-orchestrator**), by the operator, and by the
  scheduler (results delivered to Kinara for presentation: **Kinara-as-reporter**). Ad-hoc
  fan-outs Kinara composes use the same machinery as named patterns.

**Surfaces**
- R28. The controller↔surface protocol is **tiered**: a small mandatory core (attach ·
  replay-from-cursor · send · presence signal) plus declared capability sets (rail CRUD,
  approvals, notification rendering, direct-lane addressing, subagent-state rendering). The
  controller degrades per surface: a capability a surface didn't declare routes to another
  attached surface or holds pending — it is never silently lost.

**Kinara conversations**
- R29. **Multiple Kinara conversations may be live concurrently** (hot, receiving
  agent-initiated turns). R13 landing precedence and the R15 tiered awareness signal are
  therefore load-bearing from the first milestone, not later hardening.

## Success Criteria

- All six goals-doc criteria stand; additionally:
- A direct-lane message reaches its specialist with **no LLM hop before the specialist's own
  turn** — controller overhead is negligible against model latency — and the exchange appears
  inline, correctly attributed, with Kinara's digest arriving asynchronously.
- A named pattern produces the same result whether invoked by Kinara, the operator, or the
  scheduler, differing only in who presents it.
- A minimal surface implementing only the core tier achieves full conversation continuity
  (attach → replay → send → live) with nothing lost.
- The proof obligations **P1–P5** in the design sketch pass against a real spawned
  `letta server`, each with its reverting mutation (G9 standard).

## Scope Boundaries

- Unchanged from origin: first interactive milestone is web + terminal; phone/glasses/ambient
  ride later on the same controller protocol; no out-of-band delivery as primary path; legacy
  Docker Letta out of scope; enrichment pipelines share the App Server but are not surfaces.
- No hand-edited routing-rule config (R25 exclusion) — route adaptivity comes from Kinara, not
  from an operator-maintained pattern file.
- No architecture-comparison retrospective of the peer-client approach (R22) beyond the salvage
  map.

## Key Decisions

- **Resident controller over peer clients**: every discovered platform constraint punishes
  ephemeral connections holding durable responsibilities; the controller dissolves all three
  structurally and is the pattern the platform documentation itself prescribes.
- **Direct-lane exchanges live in specialist threads, inline** (over cards-in-Kinara or
  per-route choice): cleanest transcripts, no double-write, matches the spike-proven substrate,
  keeps the agent axis "secondary/inspection" as originally decided.
- **Route forms = address + binding + Kinara-managed** (static operator rule config rejected):
  determinism where the operator wants it, adaptivity delegated to Kinara rather than to a
  config file that goes stale.
- **One orchestration registry serving both Kinara-as-orchestrator and Kinara-as-reporter**
  (over Kinara-only or controller-only): one representation, three invokers.
- **Multiple live Kinara threads from day one**: the routing/awareness model was designed for
  it; running with one would leave R13/R15 untested exactly where they matter.
- **Salvage-only reconciliation**: the comparison exercise ends with the sketch's adoption;
  built code is inventory, and the open attribution/turn-completion design fault is mooted by
  the architecture rather than adjudicated.

## Dependencies / Assumptions

- **P1 is the load-bearing platform assumption**: a resident subscribed controller prevents
  turn cancellation on surface detach. Unproven — neither the 2026-08-12 spike (never tested
  detach-during-turn) nor the 2026-08-15 capture (zero clients) answers it. If false, the
  controller must hold whatever "active" means; if that fails, G2/G3 are platform-blocked and
  the decision returns to the operator.
- The sole-owner App Server continues to run supervised on loopback with no WS auth; the
  controller becomes the second supervised service and the only network-facing one.

## Outstanding Questions

### Resolve Before Planning
- (none — product decisions above are complete)

### Deferred to Planning
- [Affects R21][Needs research] **P1/P2 spike first**: prove the resident subscriber holds a
  detached turn alive, and that controller-submitted turns survive surface death, before any
  cutover work builds on them. Gating inside the plan, not before it.
- [Affects R22][Technical] The **salvage map**: read the built packages and assign each part
  (protocol layer, reconnect/replay, TUI, deploy wrapper) to controller-side, surface-side, or
  retire.
- [Affects R24][Technical] The **catch-up digest** representation: how a direct-lane exchange is
  summarized into Kinara's context (per-exchange vs batched, and how dedupe with R12 cards works).
- [Affects R24][Technical] How inline rendering of a specialist thread composes with the rail on
  each surface tier (terminal vs web), including R13 interplay when a direct thread also receives
  agent-initiated turns.
- [Affects R25][Technical] Route-table schema and the audit/visibility surface for
  Kinara-authored route changes.
- [Affects R26, R29][Technical] Hot-set budget and prune thresholds (R18) now that hot must
  cover multiple Kinara threads plus direct-route specialists.
- [Affects R27][Technical] Pattern-registry schema; whether `/v1/responses` fan-out preserves
  enough context for synthesis or some patterns need short-lived conversations.
- [Affects R28][Technical] Exact capability-set taxonomy and the degradation matrix (esp.
  approvals fan-out: first-answer-wins semantics across surfaces).
- [Affects R21][Technical] Fork/rename/delete-undo semantics: platform operation vs
  controller-level construct (new conversation + journal copy).

## Next Steps
→ `/ce:plan` for structured implementation planning (spike P1/P2 first inside the plan; then
salvage map; then controller core; then surfaces).
