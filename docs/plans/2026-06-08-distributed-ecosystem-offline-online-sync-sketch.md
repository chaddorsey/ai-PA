---
date: 2026-06-08
status: WORKING SKETCH — exploratory; to be honed over several sessions. NOT a spec or implementation plan yet.
topic: Running the agent ecosystem across devices (server + laptop + phone) over Tailscale, with an intermittent-connectivity trip as the forcing function.
related:
  - docs/followups/2026-06-08-slackbot-conversational-migration-thinking.md
  - docs/plans/2026-06-07-current-briefing-materialized-view-plan.md
maintainers-note: |
  This is a thinking document. Capture > polish. Mark DECISIONS vs LEANINGS vs
  OPEN. When we revisit, update the "Open questions" + "Next-session agenda"
  rather than rewriting wholesale.
---

# Distributed ecosystem: intermittent offline/online sync — working sketch

## 1. The use case (forcing function)
Upcoming trip: **laptop travels with Chad; server stays home (always on); phone in the mix.** All three are on a Tailscale net "essentially at all times" but the trip has **intermittent internet** (bursty connectivity, not fully offline). Chad wants to keep **working with the same live concerns his regular agents handle** (tasks, planning, etc.) AND **"shape the agent"** — deepen its understanding of him, plan together, hone processes. So this is **continuity of the live ecosystem across a partition-prone link**, NOT a separated trip fork. "Offline mode" (graceful behavior across gaps) is wanted; "separate for the whole trip" is not.

Souped-up laptop → **running local models on the laptop is on the table** (and doubles as a local-model-fleet pilot + resilience story).

## 2. Verified substrate (what we're actually working with)
- **Memory (memfs):** per-agent **git repo** at `~/.letta/lc-local-backend/memfs/<agent>/memory/.git` (branch `main`), mirrored to **Gitea** (`agents/{agentId}.git`). MC's history reads as a literal shaping log ("Record preference for durable process learning", "Refine working loops…"). → multi-master / partition-tolerant by nature.
- **Conversations:** plain file dirs `~/.letta/lc-local-backend/conversations/<b64-id>/` (`messages.jsonl` append-only + `conversation.json` + `manifest.json` + `system-prompt.json`); ~270 of them. **Per-device today; not synced anywhere.** Unique IDs; append-only.
- **Canonical signals:** `agents-canonical` Gitea repo (git; mostly per-date append).
- **Tasks / queues / conversation-meta / analytics:** **Postgres** (`pa_web.tasks`, `pa_web.task_queue`, `pa_web.conversation_meta`, `analytics.*`) on the home server. Single-master.
- **Existing outbox-ish primitive:** `pa_web.task_queue` + launchd backup poller (`scan_task_queue.sh`) + the push-receiver. (Shape we'd extend for offline capture.)
- **Brain:** **cloud** — MC on `gpt-5.4` (ChatGPT OAuth) with LiteLLM fallback (`gpt-5-mini` via `litellm:4000`, also upstream-cloud); `mc-model-manager` handles rate-limit failover. **No server-hosted local model currently running.**
- **Invocation routing:** scheduler reaches local agents at a **single fixed runner URL** (`host.docker.internal:8920` = server's runner). Runner is launchd, per-device (`LETTA_LOCAL_BACKEND_DIR=~/.letta/lc-local-backend`).
- **Prior art for cross-device:** `letta/mc-tools/execute_on_laptop.py`, `com.ai-pa.laptop-presence.plist` (stale), `mc-cli` references — an old "server-MC delegates to laptop" pattern (Rover-era), now decommissioned.
- **Model-swap edge:** litellm `cross_provider_compat` hook scrubs reasoning-field signatures when swapping to Fireworks-strict models (kimi/deepseek/glm) — relevant if conversations move between local and cloud models.
- **Server is itself a Mac** (OmniFocus/AppleScript live here) → tool *parity* between server and laptop is achievable; OmniFocus + attached hardware are device-bound.

## 3. Core tension
Two active writers (laptop + always-on home) on shared mutable state, sometimes partitioned. **CAP**: during a partition you can't have both consistency and availability → accept **eventual consistency + reconciliation**. Feasibility then depends entirely on **data type + conflict semantics + whether an operation has external side-effects.**

## 4. State-layer feasibility taxonomy
| Layer | Store | Conflict profile | Verdict |
|---|---|---|---|
| Memory (memfs) | git/Gitea | semantic conflicts if same file edited both ends; text-merge otherwise | **Infra-demanding, not infeasible** (git does heavy lifting; needs namespace hygiene + conflict policy) |
| Conversations | local jsonl files | rare (unique IDs, append-only; only same-thread-both-ends) | **Infra-demanding-but-easy** (file sync + "one device owns an open thread") |
| Canonical signals | git/Gitea | low (per-date append) | **Tractable** |
| Tasks/queues/meta/analytics | Postgres | high (row edits, IDs, deletes) | **Multi-master Postgres = ~infeasible**; **outbox/command-replay or git-backed task state = infra-demanding** |
| Home automation during partition | crons on server | acts on stale view → dup/contradictory work | coordination problem (authority) |
| External side-effects (send email/post/book) | outside world | **un-mergeable** (two actors = double-send) | **Infeasible to merge → partition AUTHORITY** |
| Inbound external world (new mail/cal/slack) | cloud | inherent latency, not a merge | refresh each window; agent reasons "view may be stale" |
| Brain | cloud today | n/a | needs **laptop-local model** offline; model-swap continuity edge |

## 5. Infeasible vs infrastructure-demanding (the crisp split)
**Simply infeasible (constrain the problem; don't engineer a merge):**
- Symmetric concurrent autonomy over **external side-effects** (double-action) → one owner per action class.
- **Strong consistency** during partitions → accept eventual + reconcile.
- **Automatic semantic merge** of contradictory decisions/state → human/rule arbitration.
- **Generic multi-master Postgres** reconciliation → use outbox or git-backed state.

**Infrastructure-demanding (feasible; real machinery to build + operate):**
- Connectivity-aware **sync orchestrator**: online-window detection, priority sync, **resumable + idempotent + atomic** (interrupted transfers), debounced (flapping).
- Bidirectional **memfs / conversation / signal** sync + conflict policy + memory-namespace hygiene.
- **Laptop-local outbox** for task/queue intents that drains to home (extends existing queue+poller).
- **Authority/ownership model**: which side owns side-effecting actions when (home owns automated sends; laptop-offline = read/plan/draft/queue; sends executed by one actor).
- **Local-model node** on laptop (inference + runner + venv + CLIs + creds + caches) + model-swap continuity handling.
- **Staleness awareness** in agent reasoning + external-state refresh on reconnect.
- **Idempotency everywhere** for replay.

## 6. Intermittent-specific stings (vs fully offline)
- Partial/interrupted syncs → resumable + idempotent + atomic-ish.
- Flapping connectivity → debounce; don't thrash.
- Causality races → may sync *into* state home just changed; ordering matters.
- **Online ≠ safe-to-double:** even connected, two live instances of the same agent need an explicit "who's the live actor" lock, or they collide. Intermittency makes that coordination *continuous*.

## 7. Paradigms considered
- **Relocate the agent (MC moves device-to-device).** Rejected: single-writer-on-one-memfs + availability (laptop sleeps) + routing-follows-the-agent (presence registry). Heavy.
- **Branch/lab fork for the whole trip.** Rejected by Chad: he wants *continuity* with live concerns (tasks etc.), not separation.
- **"Offline-mode conversation group" + memfs git branch.** Elegant for *bounded shaping* (branch isolation dissolves single-writer even for MC; curated merge = good memory hygiene). But it's separation-flavored → only a *partial* fit given the continuity requirement. Keep as a tool for focused shaping sub-threads, not the whole model.
- **Bidirectional continuous sync (the live direction).** What the continuity requirement actually points to — see §8.

## 8. Current leaning (tractable reframe)
**One authoritative home + a mostly-connected laptop peer** (NOT two symmetric masters):
1. **Memory / conversations / signals sync bidirectionally** (git-native) — carries "shaping + continuity"; the cheap robust win.
2. **Reads** served from **local caches**, refreshed opportunistically each online window.
3. **Writes with side-effects** captured as **intents**, executed by a **single authority** (home by default; laptop only when explicitly the live actor) — never both.
4. **Tasks** flow through the **existing outbox** (`task_queue` + poller), extended with **laptop-local capture** that drains on reconnect.
5. **Local model on the laptop** as the offline brain; ideally **same model family** used when resuming at home for clean continuity (avoids the cross-provider reasoning-field edge). Cloud stays for other agents/automation.

This gets ~80% (continuous shaping + task capture + offline planning + clean reconcile) while quarantining the infeasible ~20% (double side-effects, strong consistency) behind an **authority rule** rather than a doomed merge.

## 9. Candidate MVP (to stand up before the trip) — DRAFT, not committed
- **Git-sync for memory + conversations + signals** (a small connectivity-aware sync command; conversations get versioned). Bidirectional, idempotent, resumable.
- **Laptop-local task outbox** that replays into `pa_web.task_queue` on reconnect (reads from a local snapshot offline).
- **Authority rule**: while traveling, **home owns automated outward actions**; laptop is plan/draft/queue; outward sends reconciled by one actor. Make "who is the live actor" explicit.
- **Local-model node** on the laptop (model + runner + venv + extensions + CLIs + creds + caches).
- **Sync ritual**: one command on each online window (push/pull memory+conversations+signals, drain outbox, refresh external snapshots).

## 10. Decisions vs leanings vs open
**DECISIONS (Chad):**
- Continuity over separation (work the same live concerns; not a trip fork).
- Willing to run **local models on the laptop**.
- Wants to **hold + sync conversations**, not just config/memory.

**LEANINGS (mine, unconfirmed):**
- Authoritative-home + connected-peer (not symmetric multi-master).
- Same model family across devices for the shaping agent.
- Reuse/extend the existing task_queue+poller as the outbox.
- Treat external side-effects via authority partition.

**OPEN QUESTIONS (resolve in coming sessions):**
1. What does "honing/shaping" concretely include offline — instructions/memory/process docs (transfers cleanly) vs live-data-dependent behavior (needs connectivity)?
2. Which agents need to travel "live" (MC? a personal/planning agent? tasks-agent?) vs stay home-only?
3. Exactly which task operations must work **offline** (capture-only? claim/extract/complete?) — sizes the outbox vs a fuller local task store.
4. Authority rules: enumerate side-effecting action classes and assign an owner-per-state.
5. Model choice for the laptop brain + whether production also adopts it (parity).
6. Acceptable reconciliation effort: auto-merge where safe vs human-curated merge for memory.
7. Conversation sync mechanism: git over the conversation dirs vs a Gitea "conversations" repo vs rsync; and "one device owns an open thread" enforcement.
8. Secrets posture on a traveling laptop (disk encryption, scoped tokens, key handling).
9. Timezone handling vs ET-anchored time logic while traveling.
10. Phone's role (client/interface only — confirm).

## 11. Dependencies / relationships
- **Brain-local** depends on standing up a laptop model node (and possibly a server-side local model for parity).
- Interacts with the **slackbot conversational migration** (parked) — both touch "where the brain runs" and the local-agent model; the unified-brain question recurs. Keep the two docs cross-referenced.
- **pa-web-ui's `LETTA_BASE_URL=letta:8283`** still unverified (likely vestigial) — orthogonal but part of the broader Docker-Letta wind-down.

## 12. Next-session agenda
1. Pin down OPEN #1–#3 (what "honing" means; which agents travel; offline task scope) — these size everything.
2. Draft the **authority model** (OPEN #4) — the part that can't be merged, so it must be designed.
3. Decide the **laptop model** + parity stance (OPEN #5).
4. Convert the §9 MVP into a real spec (brainstorming → writing-plans) once the above are settled — likely decomposed (sync layer; task outbox; local-model node; authority rules) like the slackbot work.
