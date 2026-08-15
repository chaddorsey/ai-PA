# Multi-Surface Agent Continuity — Goals

**Living document.** This is the current statement of *what we are trying to achieve* and *where it
stands*. It deliberately contains no design or implementation detail — those live in the M1 plan,
the design brief, and the review/findings documents linked at the end.

**Relationship to the origin doc.** The goals were first set out in
`docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md` (R1–R20). That remains
the record of how we got here and is not edited. This document supersedes its *Requirements* and
*Success Criteria* sections as the thing to read for current intent; original R-numbers are kept
against each goal so the trace holds.

**Last reality check:** 2026-08-15, after reading the App Server documentation and protocol
declarations for the first time, and after live captures against the running server.

---

## The outcome we want

The operator's agent should **follow them across surfaces**. The same live conversation, picked up
on a terminal, in a browser, later on a phone or glasses — with the agent present and working
whether or not anyone is currently looking at it, and with nothing said or scheduled getting lost
in a runtime nobody is attached to.

Everything else — notifications, ambient dashboards, hands-free surfaces — hangs off that one
property. The felt experience is **one agent (Kinara)**, with the rest of the fleet as specialists
behind her, not as separate destinations.

## Why this doesn't exist today

The agent is reachable only through **independent runtimes that don't share state** — the stock
terminal TUI, the `pa-web-ui` subprocess pool, the Desktop app. Nothing composes: choosing the
terminal means losing the web's conversation features; scheduled turns fire wherever the lease
lives rather than where the operator is looking (*"the 10:55 reminder that never appeared"*); and
concurrent runtimes on one conversation race each other so messages silently vanish from a surface.

---

## Goals

Each goal is an outcome, with an honest status. **Status vocabulary:** `met` · `partial` ·
`not started` · `at risk` · `blocked`.

### G1 — One runtime owns the agent state (R1, R4) — **met**

Exactly one process owns the live conversation store; every surface is a client of it. This is what
removes the multi-writer race rather than working around it.

*Status:* the sole-owner App Server runs and is the only writer. Consolidating the remaining
incumbents onto it (G7) is what is left.

### G2 — The agent is continuously available, not summoned (R2, R2b) — **partial, and qualified since 2026-08-15**

Agents and conversations stay live independently of whether a client is attached; surfaces are
ephemeral views that attach and detach freely.

*Status:* the runtime persists and multiple clients can attach to the same conversation and see
each other's turns — verified live and repeatedly.

> **Qualification we did not know when this goal was written.** A conversation persists, but a
> **turn in progress does not survive the last client detaching**: the platform cancels the active
> turn when no subscribed client can take it over. Verified — a turn running a 25-second tool was
> dead within 6 seconds of the only client disconnecting.
>
> So "the agent keeps working while nobody is watching" is **not currently true**, and it is the
> assumption several later goals rest on. This is a platform behaviour, not a bug in our clients.
> Whether we accept it, hold a keep-alive subscription, or something else, is an open decision —
> see Open Risks.

### G3 — Anything the agent initiates reaches the operator (R3, R9, R12–R15) — **not started**

Scheduled pokes and event reactions land in the right conversation and are *signalled* to the
operator wherever they are, without hijacking their focus. Routing is three separable decisions —
which conversation it lands in, whether focus moves (it never does), and how the operator is made
aware (interrupt · badge · muted).

*Status:* not built. **This is the motivating problem and it is still unfixed.** It is also the
goal most exposed to G2's qualification: an agent-initiated turn with no client attached may not
survive to be delivered.

### G4 — No surface is privileged, and adding one is additive (R5, R7, R8, R11) — **partial**

Terminal, web, phone and glasses are co-equal clients. Adding the next surface should not be a
re-architecture.

*Status:* the terminal client is **built but not signed off** (its review is open — see the design
brief). The web client is **not started**. Phone and glasses remain vision.

> **Constraint discovered 2026-08-15:** a browser **cannot connect to the runtime directly** —
> the platform rejects browser-origin connections unless authenticated, and a browser cannot send
> the required credential on a WebSocket. Every browser-based surface therefore needs an on-box
> mediator. This was already our M1 approach, but as a *choice*; it is in fact **mandatory**, and it
> applies to phone and glasses too.

### G5 — Nothing is silently lost (R17, and the "no vanishing messages" criterion) — **at risk**

A turn typed, scheduled, or streamed is either delivered or visibly failed. Degradation is visible;
silence is never the failure mode.

*Status:* substantially improved — errored turns are now shown rather than rendering as empty
success, connection state is visible, and failures reach the exit code. But **two known silent-loss
paths remain**: a queued turn whose submitting client disconnects is cancelled without the
reconnecting client being told, and (G2) a running turn can be cancelled by detachment. Both are
platform behaviours we must design around rather than defects we can fix locally.

### G6 — The operator stops choosing between surfaces (R6) — **not started**

Terminal ergonomics and the web's conversation features (rail, create/rename/fork/undo) stop being
an either/or.

*Status:* not started; depends on the web client (G4).

### G7 — Consolidation is non-disruptive and reversible (R19, R16) — **partial**

Existing runtimes become clients or retire, without losing conversation history and with an instant
rollback if it goes wrong. The single owner is supervised, including against hanging-but-alive
failure.

*Status:* the cutover is designed but not executed; incumbents still run. Supervision is
**currently a stopgap** — the tracked launchd service is deliberately not loaded, because loading it
*is* the cutover. Discovered 2026-08-15: the runtime had been running unsupervised as an orphan of
an older process, so a restart would have left it down.

### G8 — Reach is safe by default (R20) — **met for now, revisit per surface**

The runtime is not exposed beyond the machine without authentication. Remote reach is delegated to
an already-authenticated path.

*Status:* loopback-only, enforced in the client core. The platform does support authenticated remote
access, which is a better-founded position than we previously documented — but every off-box surface
still needs a deliberate decision, not an inherited default.

### G9 — Changes to this system are falsifiable — **met, and worth keeping**

Not in the original list, but it has become a real goal. Three review rounds shipped comparable
defects with a green test suite. A change is not done because it passes; it is done when reverting
it *provably* fails a named test.

*Status:* met for the client packages — every landed fix carries a mutation that reverts only that
component and must fail a named test, and process-level behaviour is tested by running the binary.

---

## What changed our understanding (2026-08-15)

Recorded because these were **goal-affecting**, not merely technical:

1. **A turn does not outlive its last observer** (G2, G3, G5). The most significant finding: it
   undercuts "constant-on" as originally stated and puts G3 at risk before G3 is even built.
2. **Browsers cannot reach the runtime directly** (G4). A mediator is mandatory for every
   browser-class surface, including phone and glasses.
3. **A queued turn can be cancelled unobserved** (G5). The affected client is not told and cannot
   discover it by inspection.
4. **The platform is specified, and we had not read the specification.** Much of what four review
   rounds derived from packet captures was written down. This is a working-practice failure more
   than a technical one, and it is why this document now carries a "last reality check" date.

## Non-goals

- **Not** an out-of-band delivery channel (a Slack or notification bridge) as the primary path.
  Continuity is delivered by the shared runtime; side channels are at most an optional extra.
- **Not** dependent on any vendor UI's roadmap.
- **Not** migrating the enrichment/task pipelines' interactive behaviour — they share the runtime
  but this effort is about *interactive* surfaces.
- **Not** in scope: the legacy Docker Letta instance, which is a separate store on its own
  decommission track.
- **Not** a rebuild of anything that already works. Where an existing surface's UX is good, the
  intent is to keep the ideas and change what it talks to.

## Success criteria

Outcome-level, and testable:

1. The same live conversation is usable interchangeably from two different surfaces — a turn in one
   appears in the other within seconds — with no lost messages. *(G1, G2, G4)*
2. A scheduled or agent-initiated turn reaches the operator on the surface they are attached to,
   and is not lost when they are attached to none. *(G3 — and see Open Risks: the second clause may
   not be achievable as stated.)*
3. The operator does not have to choose between terminal ergonomics and web conversation features.
   *(G6)*
4. Adding the next surface is additive rather than a re-architecture. *(G4)*
5. Every failure is visible: no silent drops, no hangs presented as success. *(G5)*
6. Consolidation can be rolled back instantly at any point. *(G7)*

## Open risks

| Risk | Bears on | Status |
|---|---|---|
| A running turn is cancelled when the last client detaches, so "the agent works while you're away" may not be achievable without a permanent subscriber. | G2, G3, G5 | **Open — needs a decision, not a fix.** |
| An agent-initiated turn arriving with nobody attached may not survive to be seen. | G3 | Open; follows from the above and is untested. |
| A queued turn cancelled during a disconnect is not discoverable by the affected client. | G5 | Open; design brief question. |
| The terminal client is built but unsigned-off; its ownership/attribution model is under review. | G4 | Open — design brief. |
| Supervision of the sole owner is a stopgap; the real service is not deployed because deploying it is the cutover. | G7 | Open — operational decision. |
| The motivating problem (the detached scheduled turn) remains unfixed and is gated on work not yet started. | G3 | Open. |

## Where the detail lives

- **Origin and full R1–R20 rationale:** `docs/brainstorms/2026-08-12-agent-multi-surface-continuity-requirements.md`
- **Milestone 1 plan (design + implementation units):** `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md`
- **Open design conversation (attribution + turn completion):** `docs/plans/2026-08-15-005-continuity-ownership-design-brief.md`
- **What the platform actually specifies, versus what we built:** `docs/followups/2026-08-15-app-server-docs-vs-implementation.md`
- **Live protocol captures:** `docs/followups/2026-08-15-continuity-ownership-live-captures.md` and `docs/followups/captures/`
- **Most recent client work and its verification standard:** `docs/plans/2026-08-15-004-continuity-fix-forward-closeout.md`
