---
date: 2026-08-12
topic: agent-multi-surface-continuity
---

# One Agent, Everywhere — Multi-Surface Continuity

## Problem Frame

The Letta personal-assistant agent is reachable today only through fragmented, **independent runtimes** that don't share state: the stock terminal TUI (`letta --backend local`), the `pa-web-ui` chat (a *subprocess-per-conversation* pool), and the Letta Desktop app (which also holds the cron scheduler lease). Because each is its own runtime writing its own session, nothing composes:

- Working in the TUI means losing the conversation features `pa-web-ui` already has (create/rename/fork/rail); the operator has drifted between surfaces and can't have both.
- Scheduled/agent-initiated turns fire in whichever runtime owns the lease (the Desktop app), not where the operator is looking — the "10:55 reminder that never appeared."
- Concurrent runtimes on the same conversation cause a **multi-writer race** (a turn lands in the append-only transcript but drops out of the active projection), so messages silently vanish from a given surface.
- Acute reach gaps remain: no good phone access, no agent-initiated native notifications, no agent-maintained ambient surfaces (dashboard / standing daily-schedule card), and a coming hardware surface (Brilliant Labs **Halo** glasses via the **Noa** platform) with nowhere to plug in.

The operator wants **their live agents to follow them across surfaces** — pick up the same conversation on terminal, web, phone, or glasses — with everything else (notifications, dashboards, glasses) hanging off that continuity.

**Multi-agent reality (added 2026-08-12):** this is not one agent but a **fleet** (Mission Control, tasks, docs, pulse, email, calendar, …). Continuity therefore spans **two axes — which agent × which conversation** — surfaced as a rail the operator navigates, on every surface. "Constant-on" and the peer-client model must account for a fleet of agents each with conversations, not a single conversation.

Per Letta's own guidance, the supported substrate for this is **one App Server as the runtime/store owner, with many clients subscribed to a given `{agent_id, conversation_id}`**: one client injects a turn, all subscribed clients render it live. That reframes the effort from "which platform?" to **"one runtime, many client surfaces, across a fleet of agents."**

> **STATUS (2026-08-12): FOUNDATION VALIDATED — spike PASSED.** A 7-persona review flagged the core premise as unproven (and seemingly contradicted by our stateless `letta-push-receiver` dispatch usage). The feasibility spike then **proved it on our actual Letta App Server (0.30.19):** two WebSocket clients subscribed (`runtime_start`) to the *same* `{agent_id, conversation_id}`; one injected a turn (`input`/`create_message`); **both clients received the identical live-streamed response** (`stream_delta` "P"→"ONG", `usage_statistics`, `turn_finished`). Multi-client subscribe + inject-from-one + real-time broadcast-to-all-observers all work — the continuity primitive is real here. **The remaining blockers (Outstanding Questions) are now the gate to `/ce:plan`, not the feasibility unknown.** (Operational note: the conversation must pre-exist before WS inject — a client responsibility, not a blocker.)

## Requirements

**Foundation — single runtime, peer clients (the durable capability)**
- R1. A single **App Server** is the sole owner of the agent runtime and conversation store; no other process concurrently owns or writes the same live conversation (retires the competing runtimes: the `pa-web-ui` subprocess pool and the Desktop app's scheduler/session lease).
- R2. The runtime keeps the **fleet's agents and their conversations continuously available ("constant-on")**, independent of whether any client is attached; agent presence and context persist across attachments. Clients are **ephemeral attach points / views** that navigate a **rail of `{agent, conversation}`** and attach to a given one. *(Open — see Outstanding Questions: whether "constant-on" applies to one designated live conversation per agent, to every conversation, and how agent-initiated turns route when the operator is viewing a different agent/conversation in the rail. This two-axis routing is the top review finding and must be resolved before planning.)*
- R2b. Surfaces are **peer clients** that subscribe to a live `{agent_id, conversation_id}`; a turn entered on one client renders on all clients subscribed to that same agent+conversation in near-real-time.
- R3. Agent-initiated turns (scheduled pokes, event reactions) inject into the shared runtime and render on all subscribed clients — the "reminder/reaction appears where I am" behavior, generalized.
- R4. The multi-writer race is eliminated as a consequence of R1 (single writer/owner).

**First milestone — web + terminal continuity (the proof)**
- R5. A **web client** and a **terminal client** both subscribe to the *same* live conversation on the App Server: typing in one appears in the other; both see agent turns live.
- R6. The web client recovers the conversation features `pa-web-ui` already has (conversation rail, create/rename/delete-with-undo/fork), now backed by the shared App-Server runtime rather than per-conversation subprocesses.
- R7. The terminal client is a **text-first, lightweight attach point** onto the constant-on conversation (the stock TUI cannot subscribe, so the terminal surface is re-platformed onto the client protocol). With a constant-on conversation, no single client — terminal included — is special or load-bearing; the specific terminal-multiplexer/server workflow is at most a nice-to-have.

**Vision surfaces — ride on the foundation (phased after the first milestone)**
- R8. A **phone client** for on-the-go access to the same live agent/conversation.
- R9. Agent-initiated **native notifications** (esp. iOS) so time-sensitive things reach the operator without being in a chat.
- R10. An agent-maintained **ambient surface** — a standing daily-schedule card / dashboard the agent keeps current and can push live updates to.
- R11. **Halo glasses (Noa)** as a hands-free client/integration surface on the same runtime.

## Success Criteria
- The same live conversation is usable interchangeably from the web and terminal clients — a turn in one appears in the other within seconds — with no lost/vanishing messages.
- Scheduled or agent-initiated turns render on the surface the operator is attached to (not silently in a detached runtime).
- The foundation is proven such that adding the next client (phone) is additive, not a re-architecture.
- The operator no longer has to choose between "TUI ergonomics" and "web-UI conversation features."

## Scope Boundaries
- First milestone is **web + terminal only.** Phone (R8), notifications (R9), dashboard (R10), and glasses/Noa (R11) are in the vision but explicitly **out of the first milestone.**
- Not building an out-of-band "delivery channel" (Slack/notification bridge) as the primary path; continuity is delivered by the shared runtime, not a side channel. (Out-of-band delivery may still be an *optional* client-side capability later.)
- **Do not depend on Letta Chat's roadmap.** It may be adoptable as a client base, but its (uncertain) desktop timeline is not a gating dependency.
- Not migrating the enrichment/task pipelines' use of the App Server; this effort is about *interactive* client surfaces, though it shares the same App Server runtime concept.

## Key Decisions
- **Continuity = one App-Server runtime + peer clients** (not per-surface runtimes). Chosen because it's the only model that makes "same live agent everywhere" real, and it's Letta's supported multi-client pattern.
- **No single primary surface** — terminal, web, phone are co-equal clients from the architecture's standpoint; the first *milestone* proves it with web + terminal.
- **The stock TUI is a dead end for continuity** (it cannot be an App-Server client and causes multi-writer races); the terminal experience must be rebuilt as a client.
- **The Desktop app and the pa-web-ui subprocess pool are the incumbent competing runtimes** that must be consolidated/retired onto the single App Server for continuity to hold.
- **Terminal client is text-first sharing the runtime; mux integration is nice-to-have** (not load-bearing for the client design).
- **The conversation is "constant-on"** (always-live runtime; clients are ephemeral views). This is what makes continuity, agent-initiated reactions between attachments, and client-agnosticism all fall out of the same property — and it further reduces how much any single client (incl. terminal) matters.

## Dependencies / Assumptions
- **All agents run on one box** (the home server), so a single Local App Server on that box can own the whole fleet's runtimes/conversations locally — no cross-box coordination needed. This meaningfully simplifies the multi-agent picture (the App Server already enumerates every local agent).
- A Local App Server process is **proven runnable** here — but its only in-repo use (`letta-push-receiver`, stateless one-shot `POST /v1/responses` dispatch; WS-subscribe **explicitly rejected** in `docs/plans/2026-08-12-dispatch-surface-spike.md`) does **not** validate the constant-on, multi-client-subscribe pattern this vision needs. That pattern is **unproven in this deployment and is the primary technical risk** (→ the feasibility spike).
- `pa-web-ui`'s **conversation-rail UX/CRUD** (rename/fork/delete-with-undo, `pa_web.conversation_meta`) is a reusable asset — but its **chat transport is not**: it is Popen-per-conversation with stdout stream-json parsing, with zero App-Server client code. "Re-pointing" undersells a ground-up transport rebuild against the client protocol.
- Letta docs describe multi-client subscribe + inject/render — but this environment has a **documented history of Letta behavior diverging from its docs** (PATCH semantics, 307s, silent stalls), so treat this as an assumption to **prove in the spike**, not a validated dependency.
- Runtime landscape is larger than two incumbents: besides the `pa-web-ui` subprocess pool and the Desktop app (which holds the **letta-code cron lease** — verified live, PID 1002; distinct from the custom `scheduler-service`), a **legacy Docker Letta** (`letta:8283`) is still live serving slackbot/gmail-watch/granola (decommission blocked). R1's "sole owner" scope must account for all three.

## Feasibility Spike (gating — do this before anything else)

Time-boxed spike to prove or kill the foundation premise on our actual Letta App Server. It must answer:
- Can **two clients subscribe to one live `{agent_id, conversation_id}`** and see each other's turns in near-real-time (bidirectional), and can an **externally-injected turn render** on subscribed clients?
- Does it hold **across the fleet on one box** — one App Server serving multiple agents, a client navigating a **rail of `{agent, conversation}`** and (re)subscribing?
- Does a **constant-on** conversation survive/behave over time (no silent-stall / projection loss under multi-attach)?
Outcome decides everything: **validates** → proceed to resolve the blockers below then `/ce:plan`; **falsifies** → pivot to a lighter path (below) before any consolidation.

**RESULT — PASSED (2026-08-12).** On Letta 0.30.19, verified via two spikes:
- **Spike 1 (continuity):** two clients subscribed to one `{agent, conversation}` (`runtime_start`); one injected (`input`/`create_message`); **both received the identical live-streamed turn** (`stream_delta` "P"→"ONG", `turn_finished`). Subscribe + inject + broadcast-to-all-observers work.
- **Spike 2 (multi-agent / multi-conversation), answering the design questions:**
  - **Targeted send (one agent → just one other): YES.** Injection is scoped to a specific `{agent_id, conversation_id}` in the `input` message; injecting into agent A produced a turn ONLY on A — agent B and other conversations were untouched. Not a broadcast to all agents.
  - **Concurrent multi-agent (operator↔agentA while agentA↔agentB): YES.** Injected into `{A}` and `{B}` simultaneously → both ran concurrently, events correctly scoped. The docs' "one active turn per `{agent,conversation}`" constraint is *per-runtime*, not global; spike 1 also showed `update_subagent_state` streams, so an agent's sub-delegation (e.g. MC → tasks-agent) is both possible and visible to subscribers.
  - **Multiple live conversations per agent (switch "primary" on the rail): YES (substrate).** Two conversations on one agent (`default` + a `--new` conv) both ran concurrently, correctly scoped. "Primary" and "keep-primary-across-devices" are **app-level coordination** (a synced current-`{agent,conversation}` pointer) layered on this substrate.
- **Protocol:** `/ws` (loopback=no auth; else `--ws-auth`), `runtime_start {agent_id, conversation_id}` → `runtime_start_response`, `input {runtime, payload.kind:"create_message"}`, receive `stream_delta`/`update_loop_status`/`update_queue`/`update_subagent_state`/`turn_finished`. **Gotcha:** the conversation must pre-exist — `default` auto-creates on first inject, but arbitrary conversation names do NOT (create via `--new` or the pa-web-ui create path). *Still to probe (non-gating):* sustained constant-on behavior over days/weeks.

## Outstanding Questions

### Resolve Before Planning
- ✅ **[Affects R1–R5][Spike] DONE — Feasibility Spike PASSED (2026-08-12).** Multi-client subscribe + inject + real-time broadcast validated on Letta 0.30.19 (see above). The foundation is feasible; the items below are now the gate.
- [Affects R2,R3][User decision] **Two-axis routing** (top review finding, 3-persona consensus): when an agent-initiated turn fires while the operator is viewing a *different* agent/conversation in the rail, where does it go? (pinned-primary-per-agent vs. follows-focus vs. notify-and-hold) — get this wrong and it reproduces the 10:55-never-appeared bug one layer up.
- [Affects R1,R2][User decision + Technical] **Client auth/authz** as a foundation property (security P0): what authenticates a subscribe/inject to `{agent_id, conversation_id}`, especially once off-loopback (phone/glasses); and the **Noa/Halo cloud trust boundary** (what conversation data crosses to a third party).
- [Affects R1,R2][Technical] **Reliability model**: one sole-owner App Server is a new single point of failure (this env has a documented Letta silent-stall) — needs supervision/auto-restart, a client-visible "disconnected" state, and a **conversation lifecycle/pruning** policy (constant-on threads will bloat, as memfs already did here).
- [Affects R1][Technical] **Same instance or separate?** Is the interactive App Server the *same* process as the enrichment `letta-push-receiver` (regression risk to the system we just stabilized) or a distinct instance — and how does R1's single-writer guarantee coexist with the enrichment dispatch pattern.
- [Affects Key Decisions][User decision] **Retirement is a hypothesis, not settled**: don't retire the incumbents (pa-web-ui pool, Desktop cron lease, legacy Docker Letta) until a validated, non-disruptive consolidation + rollback exists. And weigh — *after* the spike — whether full consolidation is the right scope vs. a **lighter path** (e.g., pa-web-ui as daily driver + a persistence write-lock for the race + a notification stopgap for the acute reminder pain).

### Deferred to Planning
- [Affects R5,R6][Technical] **Interaction model** (design cluster): cross-client sync granularity (turn vs character-level), how an agent-initiated turn presents (auto-scroll/interrupt vs unread badge), reconnect/catch-up after a gap, and cross-client rail-action (delete/fork/rename) conflicts.
- [Affects R6][Technical] Migration path for `pa-web-ui`'s live conversation data onto an App-Server-backed store (no described path today).
- [Affects R5,R6][Needs research] Client base. **Strong lead: the Letta Agent SDK (`@letta-ai/letta-agent-sdk`)** — the high-level TS harness interface that natively supports the **self-hosted App Server** backend with `createSession`/`createRuntime`, streaming, subagents, MemFS sync, permissions/approvals, local tools. It's the sanctioned way to build our peer clients (abstracts the raw WS subscribe/inject/render we hand-rolled in the spike) and materially de-risks the client work. (NOT the low-level `@letta-ai/letta-client`/`letta-client` REST-CRUD SDK — Letta says don't build directly on that.) Open: build web+terminal clients on the Agent SDK directly, reuse `pa-web-ui`'s rail UX on top of it (transport rebuilt against the SDK), and/or evaluate **Letta Chat** (OSS UI) as a starting shell — one base for both surfaces? Docs: docs.letta.com/agent-sdk, github.com/letta-ai/letta-agent-sdk.
- [Affects R8,R9][Needs research] Phone: **PWA vs native Swift** + iOS push/native-notification mechanism — when phone becomes active.
- [Affects R11][Needs research] Halo/Noa integration surface + constraints (Noa API, on-device vs cloud, what "client" means for glasses).

## Next Steps
→ Spike **PASSED** — foundation is feasible. Resolve the remaining Resolve-Before-Planning blockers (two-axis rail routing, client auth + Noa trust boundary, reliability/SPOF + conversation lifecycle, same-vs-separate App Server instance, retirement-vs-lighter-path), then `/ce:plan`.
