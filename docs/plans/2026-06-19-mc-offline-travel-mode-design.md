---
date: 2026-06-19
status: DESIGN — architecture settled; sync details + inbox/outbox reactivity to be refined against a running version.
topic: "Laptop mode" — MC as a single continuous agent across intermittent connectivity (travel/offline + auto re-sync).
supersedes-and-extends: docs/plans/2026-06-08-distributed-ecosystem-offline-online-sync-sketch.md
related:
  - docs/plans/2026-06-08-distributed-ecosystem-offline-online-sync-sketch.md
  - feedback_cmux_continuum_blank_tabs.md (roaming substrate: server-side tmux sessions, mosh thin clients)
maintainers-note: |
  Architecture is decided (see §3 Decisions). The sync mechanics and the
  inbox/outbox→model reactivity are intentionally under-specified — we will
  stand up a minimal running version and refine those against real behavior.
  Update §10 (Open / refine-once-running) as we learn; don't rewrite §2–§3.
---

# Laptop mode: MC as one continuous agent across intermittent connectivity

## 1. Goal statement

**North star:** Mission Control remains a *single, continuous agent* — one identity, one memory lineage, one conversation lineage — that travels with Chad on the laptop and stays usable across **intermittent connectivity** (frequent short drops: tunnels, rural stretches, planes), **degrading gracefully when offline** and **reconciling automatically on reconnect**, *without* forking identity, running two live writers, or expanding the database.

This is a **general intermittent-connectivity mode**, not a one-off trip fork — equally applicable to commutes, flights, and dead zones. The upcoming long-range train trip is the forcing function, not the boundary.

**The goal decomposes into three testable commitments:**

1. **Continuity (no separation).** From the user's view there is one MC. Memory you shape offline and conversation you have offline are *the same* MC's memory and conversation — recallable later without asking "which agent / which trip was that?" Divergence between laptop and home is kept *small and constant* (synced every online window), never *large and occasional* (a trip-long fork).

2. **Graceful degradation (honest offline).** Offline, MC keeps thinking, planning, drafting, and shaping its own memory on a local model. It *knows* it is offline — it does not silently fail or hang on unreachable services; it queues fleet work and tells the user it is queued. The brain gets weaker offline (local model), but the identity and continuity do not break.

3. **Automatic reconcile (it just catches up).** On any online window — even a short one — memory, conversation, queued fleet commands, and their results sync without the user (or the agent) babysitting it. The fleet's deferred work runs and its results return. Re-entry is a non-event.

**Done looks like (success criteria):**
- You can pick up the same MC conversation on the laptop offline, mid-tunnel, on a local model, and on return that exchange is part of MC's one history at home — no manual merge, no duplicate agent.
- A memory/preference you teach MC offline is present in home MC after the next reconnect, having merged cleanly (no conflict for non-overlapping edits).
- A fleet command issued offline ("search my email for X", "draft a reply", "parse this transcript") is captured, survives an arbitrary number of drops, runs exactly once when back online, and its result reaches MC.
- Home automation (tasks, briefings, pulse) keeps running the whole time and never collides with offline shaping.
- No new database tables were added to support any of the above.

**Explicit non-goals (constrain, don't engineer):**
- No symmetric concurrent autonomy over external side-effects (two actors sending the same email) — solved by an **authority rule**, not a merge.
- No strong consistency during a partition — eventual + reconcile.
- No automatic semantic merge of *contradictory* decisions — arbitrated by rule or human.
- No goal of equal capability offline — the local brain is smaller; that is accepted.

---

## 2. Paradigm / mental model

One MC whose **live cursor follows the user**. When home and connected, the laptop is a thin client to the server's MC (the existing mosh/tmux roaming model). When traveling, the **laptop hosts the live conversational MC** and home runs **automation only**. Because the user converses from one place at a time and home automation is read-mostly/namespaced, there is — *in practice* — a single writer, so there is no real fork to reconcile, only a continuously-trailing mirror.

The fleet (tasks, pulse, email, docs, calendar) does **not** travel — its core work is online-bound (Gmail/Slack/Drive/Calendar). It stays server-side and keeps working; MC reaches it through a durable, async **seam** that tolerates drops.

---

## 3. Decisions (settled this session)

- **D1. Full offline agent.** A local model on the laptop is the offline brain (not "survive & reconnect", not "plan/draft only").
- **D2. MC is the one agent.** Unified identity, memory, and conversation. *Not* a separate travel agent (that would fragment recall).
- **D3. Topology = laptop-primary in travel mode; home = automation-only.** One live conversational MC at a time; home keeps automation running, writing into its **own namespace**.
- **D4. Memory = continuously-synced memfs, B′-style.** The laptop works on an *ephemeral branch* of MC's memfs folded back to `main` every online window. One shaping writer (laptop) + namespaced home-automation writes → trivial merges.
- **D5. Conversation = one thread, single live owner.** While traveling the laptop owns the live thread; its tail folds into MC's canonical thread on reconnect. (Consolidation here is *ownership discipline*, not a hard merge — which is why conversation is secondary to memory.)
- **D6. Brain = dynamic cloud↔local model swap on connectivity.** Same agent, same thread; the existing litellm `cross_provider_compat` scrub hook carries reasoning-field signatures across the swap. The swap is connectivity-automatic (extend `mc-model-manager` with an online/offline signal).
- **D7. Fleet stays server-only.** Online-bound; does not travel.
- **D8. MC↔fleet seam is durable + async.** MC never makes a synchronous fleet call. Commands are captured as durable intents; results return asynchronously. (See §5.)
- **D9. Outbox = generic git-synced envelope log, not DB expansion.** Heterogeneous commands are self-describing envelopes, not new tables/rows. (See §5.)
- **D10. One transport = git.** Memory, conversation, outbox, and inbox all ride the existing connectivity-aware git sync (memfs/Gitea pattern). The agent never drives transport.

---

## 4. Architecture — Layer 1: MC offline core

**Identity & memory.** The laptop runs MC (same agent) against a clone of its memfs, on an ephemeral branch. Home automation writes only into a reserved namespace (e.g. `automation/`), so the offline shaping (the rest of the tree) and the automation writes never overlap → merges are mechanical. Every online window: rebase/merge the branch back to `main`, push.

**Conversation.** One canonical MC thread. While traveling the laptop is its sole writer; the append-only tail folds into the canonical thread on reconnect (unique IDs make append idempotent). Home posts nothing to the live thread during travel.

**Brain / model swap.** A connectivity signal flips MC's model: cloud (full) when online, local (smaller) when offline, mid-conversation, with signature scrubbing. The *same* signal also drives capability-awareness (Layer 2).

**Travel-mode flip.** A lightweight, ideally presence/network-automatic toggle that means: laptop hosts live MC; home goes automation-only; sync runs aggressively. One action per trip, not per tunnel. (Refine the auto-trigger once running.)

## 4b. Architecture — Layer 2: MC↔fleet seam

**(a) Availability signaling.** One connectivity/capability signal (a lightweight probe to the server + a static map of which agent needs which service) that MC reads each turn — the same signal that drives the model swap. Offline, MC is in "local-only" mode: it will not *attempt* a live fleet call or fetch; it reasons "X unreachable → draft + queue", and says so.

**(b) Durable async delegation (the outbox).** Every MC→fleet action is an **envelope** appended to a git-synced outbox:
```
{ id, created_at, target: <agent|service>, verb, args, idempotency_key, reply_to }
```
On reconnect a **server-side drainer** reads newly-synced envelopes and routes each by `target`/`verb`:
- most → the **existing push-receiver** (which already routes an arbitrary prompt to any agent: "parse transcript" → docs-agent, "search email"/"draft" → email-agent);
- task-class → the **existing `pa_web.task_queue`** (existing path).
Idempotent by envelope `id`. **No new tables; no new fleet driver** (the fleet already drains `task_queue`; the drainer is a router, not a queue engine).

**(c) Results inbox.** `reply_to` closes the loop: the fleet agent writes its result into an **inbox** of result-envelopes, which git-syncs back; MC reads it on reconnect. Same transport, reversed.

---

## 5. The sync substrate (one pipe)

| Concern | Mechanism |
|---|---|
| Transport | **git** (existing memfs/Gitea sync) — memory + conversation + outbox + inbox all ride one pipe |
| Idempotency / atomicity / resume | **free from git** — commit/content hashes as dedup keys; atomic commits; resumable fetch/push |
| What kicks it | one **connectivity-aware sync runner** (launchd; fires on network-up + a debounced safety poll) — the same runner for all four data kinds |
| Agent's role | MC just **appends** intents/edits locally; it never drives transport or processing |
| Command representation | generic **envelopes** (one small versioned JSON contract — the only genuinely new data artifact) |
| Dispatch | one server-side **drainer** routing envelopes → push-receiver / `task_queue` |
| Database | **untouched** beyond existing `task_queue` |

Why git over Dropbox/rsync/Syncthing: an outbox needs exactly-once-ish + atomic + resumable + conflict-aware, which git gives for free; generic file-sync's "keep both copies" conflict model is wrong for a queue, and it adds a heavy dependency we don't need.

---

## 6. Authority & namespace rules (the un-mergeable parts)

- **External side-effects (send email, post, book): single owner.** While traveling, **home owns automated outward sends**; the offline laptop **drafts and queues** — outward execution happens once, by one actor, on reconnect. Never both.
- **Memory shaping: single shaper.** Traveling = laptop shapes; home automation writes only its namespace.
- **Live conversation: single owner.** Laptop owns the live thread while traveling.
- **Idempotency everywhere** so any replay after a flap is safe.

---

## 7. Offline-capable vs not

- **Capable offline (local model):** converse/plan/think, shape memory, draft, capture fleet commands + tasks to the outbox, read the last-synced snapshot of memory/conversation/fleet results.
- **Not offline (queued):** anything needing live external data or a fleet agent (email/Drive/Slack/Calendar reads, sends, transcript parsing) — captured as envelopes, run on reconnect, results returned to the inbox.

---

## 8. Components — new vs reused

**New (small):**
- `envelope` contract + the **outbox/inbox repos** (git-synced).
- **drainer** (server-side router: envelope → push-receiver / `task_queue`; idempotent).
- **connectivity-aware sync runner** (laptop launchd; network-up + debounced poll; syncs memory + conversation + outbox + inbox).
- **connectivity/capability signal** + MC's offline-awareness (and the model-swap trigger on it; extends `mc-model-manager`).
- **laptop local-model node** (model + serving + the MC runtime + memfs clone + offline-capable CLIs/creds/caches).
- **travel-mode flip** (lightweight; presence/network auto-trigger to refine).

**Reused (no change or minor extension):** memfs/Gitea git sync; push-receiver; `pa_web.task_queue` + its launchd poller; `cross_provider_compat` scrub hook; the mosh/tmux roaming model for the connected case.

---

## 9. Build cut: trip-ready MVP vs deferred

**MVP (stand up + test before the trip):**
1. Laptop **local-model node** + MC runtime running offline on a memfs clone.
2. **Memory + conversation git-sync** both directions, connectivity-runner-driven, idempotent.
3. **Outbox/inbox envelope log + drainer**, dispatching via push-receiver/`task_queue`.
4. **Connectivity-automatic model swap** + MC offline-awareness.
5. **Travel-mode flip** (even if manual at first) + authority rule (home owns sends).

**Deferred (phase 2+):**
- Mirroring fleet slices (esp. **tasks**) onto MC for richer offline task work (read/draft against a synced slice; writes via outbox).
- Fully-automatic presence-driven travel-mode.
- Tightening the connected-case toward continuous-peer if ever needed.

---

## 10. Open / refine-once-running (deliberately under-specified)

Per the steer, build a minimal running version, then refine these against real behavior:
- **Sync mechanics:** debounce/backoff tuning, branch rebase-vs-merge policy, ordering/causality under flapping, partial-window prioritization (what syncs first when the window is short).
- **Inbox/outbox → model reactivity:** how arriving results/notifications wake or notify MC; whether the drainer pushes to MC or MC pulls on its turn; latency expectations; surfacing "result ready" in the conversation.
- **Conflict edge cases:** the rare same-file memory overlap; whether any class needs semantic (vs git) consolidation.
- **Travel-mode auto-trigger:** presence/network heuristics and their failure modes.
- **Local model choice + parity:** which model, whether production adopts it.

---

## 11. Relationship to prior sketch

This supersedes the exploratory `2026-06-08` sketch's open questions #1–#7 (what travels, offline scope, authority, conversation mechanism) with decisions D1–D10. The sketch's feasibility taxonomy and "infeasible vs infrastructure-demanding" split remain the backing rationale; its §8 "authoritative-home + connected-peer" leaning is now sharpened into D3 (laptop-primary *while traveling*). Remaining sketch open items (#5 model choice, #8 secrets posture, #9 timezone) fold into §10.
