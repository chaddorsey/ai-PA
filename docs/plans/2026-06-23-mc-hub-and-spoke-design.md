# MC Hub-and-Spoke — Design Spec

> **Status:** design, approved through brainstorming 2026-06-23. Supersedes the single-roaming-writer model of `2026-06-19-mc-offline-travel-mode-design.md` (D1–D10). The substrate it built (memfs/git, outbox/inbox + drainer, conn-probe/sync-runner, oMLX+GLM, mc-quiesce/resume) is **reused**; the *single live writer that follows the user* framing is **replaced** by hub-and-spoke.

**Goal:** Let Mission Control ("Kinara") be reachable as one coherent assistant across a fleet of intermittent devices (laptop now; AR glasses, phone later), each degrading gracefully to a local brain when disconnected, reconciling automatically on reconnect — without pretending the devices share one live runtime or one live conversation.

**North-star rule (from the user):** *architect for the practicalities, design for the feel.* The implementation is a fleet of distinct agents sharing one canonical memory; the experience is "one Kinara."

---

## Why the model changed
The D1–D10 north star — "a single live writer that follows the user" — works for one roaming device but dies with **multiple intermittent devices**: "which device hosts the one live MC right now?" is a question you'd have to answer during exactly the partitions where devices can't coordinate (partition-time consensus, which is impossible). Adding the glasses forces the issue. Hub-and-spoke scales because each spoke fails over and reconciles **independently** against an always-on anchor, with no cross-device contention.

A second forcing function: a **mod** (Letta Code's local extension mechanism) runs *inside one runtime* and can swap that runtime's **model**, but cannot move a session *between* runtimes. So a single mod can't transparently flip you from a server runtime to a laptop runtime — that would require an external router. Hub-and-spoke sidesteps this entirely: each device **always runs its own runtime**, so failover is a per-device *model* swap (a mod's job), never a *runtime* swap.

---

## Global constraints (every task inherits these)
- **Transport:** everything rides the existing git-over-SSH-tunnel substrate (Gitea repos: the canonical memfs lineage + the bus repos). **No new database, no new transport.**
- **Identity:** hub Kinara is the canonical agent. Each spoke is a **distinct agent ID** with its own brain that **shares the hub's canonical memory lineage**.
- **Authority (Invariant 1):** every irreversible/external action (send, post, book) has **exactly one executor, chosen at action time by connectivity × capability** — online-and-capable facets act **directly** via the shared fleet services; otherwise **draft-and-queue** for the hub to drain **exactly-once**. Idempotency keys (content-hash envelope IDs) prevent double-execution across transitions.
- **Ownership (Invariant 2):** a spoke owns its **lease + its queued work (outbox)** — *not* a memory namespace. There is no global "who is the one live writer" lock; the lease + per-item action ownership make split-brain structurally impossible rather than something to arbitrate during a partition.
- **Conversations are per-device** (backend-scoped), reconciled via shared memory + summary/recall, **never synced**.
- **Memory is one shared bank**; agents own their own memory organization; infrastructure only guarantees frequent reliable sync.
- **Single-writer for any fold** is enforced by the hub-side `mc-quiesce.sh`/`mc-resume.sh` when needed.

---

## 1. Architecture & Identity

```
                 ┌─────────────────────────────┐
                 │   HUB · server "Kinara"     │  always-on · cloud brain
                 │   canonical identity        │  authoritative memory merge
                 │   automation + fleet        │  reachable from anywhere
                 └──────────────┬──────────────┘
                                │  reconciliation contract
                                │  (presence · memory · queue · results · handoff · recall)
              ┌─────────────────┼─────────────────┐
        ┌─────┴─────┐     ┌─────┴─────┐     ┌─────┴─────┐
        │  laptop   │     │  glasses  │     │   phone   │
        │  mini-me  │     │  mini-me  │     │  (thin)   │
        │ local GLM │     │  Noa SDK  │     │           │
        └───────────┘     └───────────┘     └───────────┘
         spoke #1 (now)    spoke #2 (later)   (later)
```

**Hub (server Kinara):** the canonical agent. Always-on; cloud brain; runs automation, the specialized fleet, and inbound channels; the merge point / source-of-truth for the shared memory lineage; the endpoint other devices reach. Its load-bearing roles are the ones only an always-on node can fill: (1) **drain executor** for offline-queued actions; (2) **automation** (crons, schedulers, background fleet orchestration); (3) **inbound endpoint** (email/Slack/phone arrive at a persistent receiver); (4) **canonical-memory merge**; (5) **long-running work** that must outlive a device session.

**Spokes (mini-mes):** each a distinct agent ID with its own persona (a Kinara facet) and its own brain (local model offline, cloud online), sharing the hub's canonical memory lineage. Spokes vary in capability (laptop = heavy local brain + full memfs; glasses = thin, hub-leaning); the contract absorbs the asymmetry via the **capability profile**.

**The fleet are shared, domain-owned services** (tasks, calendar, email, …) — *not* the hub's private agents. Each fleet agent is the single owner/executor of its domain, so it is irrelevant whether hub-Kinara or a spoke-Kinara invoked it. Any facet is a *client* of these services when it can reach them.

**"One Kinara" (the feel)** is delivered by three things, none requiring a single live runtime: (1) **shared canonical memory** — every facet knows what Kinara knows; (2) a **consistent persona/identity** across facets, seeded from shared memory; (3) **reconcile-on-reconnect** (memory fold now; rejoin-summary next). What is explicitly **not** built here: a unified *live* cross-device transcript (that is the deferred web-router). Continuity is "Kinara remembers everything everywhere," not "one literal chat spanning devices."

---

## 2. The Reconciliation Contract
The one interface every spoke speaks to the hub — the existing command bus generalized, plus a presence layer. Heterogeneous spokes speak the *same* contract and implement the subset their capability profile declares.

| Channel | Direction | Carries | Transport | Status |
|---|---|---|---|---|
| **Presence / lease** | spoke ↔ hub | heartbeat + TTL; spoke owns its own queued work while present | lease file in a bus repo | **new** |
| **Memory** | spoke ↔ hub | frequent bidirectional sync of the **shared canonical**; organization is agent-owned; git-native merge | memfs git | exists (generalize) |
| **Action queue** | spoke → hub | drafted irreversible actions, exactly-once | outbox repo → drainer | exists |
| **Results** | hub → spoke | execution outcomes keyed by request id | inbox repo | exists |
| **Handoff / rejoin** | spoke → hub *(later: hub → spoke)* | **leveled**: L0 memory-only · L1 rejoin-summary · L2+ deliberate thread handoff / conscious sync | envelope + memory | **L0 now, extensible** |
| **Recall** | any → any | on-demand lookup over another facet's history ("what did we cover on the laptop?") | shared memory + exported logs | new-ish |
| **Capability profile** | spoke → hub | what this spoke can do (memory full/partial, execute-locally vs draft-only) | registration | **new** |

**Capability × connectivity decides routing.** A capable spoke online (laptop) calls the fleet/world **directly** (low latency). A thin spoke (glasses, lacking tools/creds) may **route through the hub even when online**. Any spoke offline **queues**. The contract supports all three; the spoke chooses.

**Memory model (deliberately minimal):** one canonical memfs lineage, cloned by every facet. Agents read/write it however they see fit — file organization and what-to-remember are the **agent's** domain, not ours to schematize. Infrastructure's only job: **pull-current-before-interaction, push-after-writes** on a frequent cadence while online, plus the fold on reconnect, keeping memory current at interaction time. Merges are git-native (existing commit → rebase → push; auto-merge the common case, flag the rare true conflict; contended-push already graceful). We do **not** prevent conflicts with imposed structure; we keep the divergence window small with frequent sync, and the agents — owning their memory — re-read and recover. (Known property: two facets writing the *same file* in the *same instant* can produce a flagged conflict rather than an auto-merge; the small window makes this rare and recoverable.)

---

## 3. Laptop Failover Spine (spoke #1 — the first implemented increment)

Scope = **Approach 1 "failover spine."** Rejoin-summary (L1 handoff) is specified in the contract but built as the **fast-follow**, not in the spine.

### Gating prerequisite (Phase 0)
The existing memfs divergence — hub-local `560f81d` unpushed vs Gitea `248ba04`, laptop diverged — must be reconciled first: **quiesce hub Kinara (`mc-quiesce.sh`), align hub state to Gitea, rebase the laptop, resume.** Nothing builds against shared memory until this is clean.

### New components (everything else is reused)
**Reused as-is:** conn-probe, sync-runner, outbox/inbox + server drainer, the memfs/git substrate, oMLX + GLM-4.5-Air, mc-quiesce/resume.

1. **The laptop mini-me agent** — a *distinct* agent ID with its own persona (a local-aware Kinara facet) and model config (local GLM offline / cloud online), that **reads and writes the shared canonical memfs** (not a per-agent memory). *Highest-uncertainty implementation item:* letta-code keys memfs by agent ID, so "distinct agent + shared memory lineage" needs a mount/config mechanism (symlink, path override, or shared-repo configuration) the plan must resolve; this is the one piece that changes today's same-ID setup.
2. **The connectivity mod** (loaded in the laptop's letta-code) — watches hub reachability via the conn-probe signal; **auto-swaps the model** cloud↔local on transitions; publishes the online/offline link state that action-routing reads; surfaces state + lease in the statusline. (Built using the in-harness `creating-mods` skill.)
3. **The presence-lease** — the laptop renews a heartbeat in a bus repo while present; TTL distinguishes blip from departure; on expiry the hub knows the laptop is gone and holds its own posture (no handoff fight). Heartbeat frequency ≪ TTL.
4. **Action routing** — at action time, read link state: **online + capable → call the fleet/world directly**; **offline → draft + queue to the outbox** with an idempotency key. Mutually exclusive. *Integration item:* verify the fleet agents accept **spoke callers over Tailscale** (auth/routing), not only hub-local invocation.

### Data flow (three phases)
- **Online steady-state:** mini-me calls the fleet directly; reads/writes shared memfs; frequent sync (pull-before / push-after); lease renewed.
- **Drop:** mod detects hub-unreachable → swaps to GLM → action routing flips to queue → lease still valid (within TTL) so the hub stays automation-only.
- **Reconnect:** fold memory (sync-runner: commit → rebase onto canonical → push), drain outbox (server drainer executes queued actions exactly-once → inbox), swap brain back to cloud.

### Failure modes the plan must handle
- **False handoff** → lease TTL tuning; heartbeat frequency ≪ TTL.
- **Partition mid-fold** → rebase-abort + retry (already in sync-runner).
- **Contended push** (multiple facets online) → graceful (exists), exercised more often.
- **Drain failure** → idempotent retry; results keyed by request id.
- **Model-swap failure** → defined fallback (stay on last-good model; surface state).
- **Double-execution across offline→online** → mutual exclusivity (queue vs direct) + idempotency key backstop.

### Acceptance (the spine is done when)
1. An **offline exchange** runs on the local brain (GLM) with shared memory loaded.
2. **Memory folds** automatically on reconnect (laptop writes reach canonical; canonical updates reach the laptop).
3. A **queued action drains exactly-once** on reconnect (replay-safe; dispatched-marker present).
4. The **lease behaves** correctly for blip (< TTL, no handoff) vs departure (> TTL, hub holds posture).
5. **Hub automation is unaffected** throughout (fleet, crons, inbound keep running).
6. **No double-execution** across an offline→online transition.

---

## 4. Decomposition & Deferred (own specs later)
- **Rejoin-summary (L1 handoff)** — auto-summarize the offline delta and inject into the hub thread on reconnect. *Fast-follow* after the spine.
- **Glasses spoke #2 (Noa SDK)** — thin, hub-leaning capability profile; voice-first persona; plugs into the *same* contract. Validates the contract's heterogeneity.
- **Leveled conversation handoff / conscious sync (L2+)** — deliberate thread handoff and opt-in sync as use cases evolve; the contract reserves the slot.
- **External router / continuous-transcript web UI (Pathway 2)** — the only path to a unified *live* cross-device transcript; pursue only if/when the TUI ceiling is hit.

---

## Open implementation questions (for the plan, not blockers)
- The exact letta-code mechanism for **distinct agent ID + shared canonical memfs** (§3.1).
- Fleet **auth/routing for spoke callers** over Tailscale (§3.4).
- Concrete **lease TTL + heartbeat cadence** values (tune during acceptance).
