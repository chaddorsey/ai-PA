---
date: 2026-06-09
status: DESIGN (canonical) — unifies/supersedes prior scattered notes on memfs sync, conversation history, and the trip/multi-instance question
sources:
  - Letta support agent (2026-06-09) — three-plane state model, qmd layered archive, handoff exception
  - web research agent (letta-code 0.27.8 source) — local recall is keyword-only local scan; no server import
  - our investigation — DB is the only complete history source; conversation export 2026-06-09
supersedes_into_itself:
  - docs/plans/2026-06-08-distributed-ecosystem-offline-online-sync-sketch.md
  - docs/plans/2026-06-09-gitea-backed-local-memfs-design.md (becomes "Plane 1")
  - docs/followups/2026-06-08-slackbot-conversational-migration-thinking.md (the "brain" question)
---

# Memory & Recall Architecture — the three-plane model

## Purpose
Make our local-mode agents **continuous and recall-capable across multiple instances** (server runner, pa-web, future laptop) while **preserving full history** — *without* fighting letta-code local mode's grain. The core realization (Letta support + our investigation): **local mode is local state, not a distributed agent-state system.** So we don't replicate the live agent; we share the *durable* layers and let each instance keep its own *live* layer.

## The keystone: three planes of state, each with its own sync rule

| Plane | What it is | Where it lives | Sync rule | Status |
|---|---|---|---|---|
| **1. Durable memory** | memfs — the agent's curated "ground truth" (system/ instructions, learnings, digest) | per-agent git repo | **Gitea hub**, pull-on-start / push-on-write, **one-writer-at-a-time / explicit clean merge** | designed (canary paused at Task 4) |
| **2. Historical knowledge** | a **qmd-indexed, layered archive** (raw transcripts + curated knowledge) | git repo / shared folder | **git/shared, append-only; index rebuilt per machine** | raw layer exported; rest to build |
| **3. Live conversation state** | local backend `conversations/*/messages.jsonl`, compaction state, in-context IDs, system-prompt cache | `~/.letta/lc-local-backend/` | **PER-INSTANCE — do NOT sync** | as-is |

**The agent feels like one continuous agent across instances because it shares planes 1 & 2 — never because plane 3 is replicated.** This is the whole design.

## Plane 1 — Durable memory (memfs)
- Per-agent git repo, hosted on the **Gitea hub** (extend the existing Docker-agent pattern to `agent-local-*`). Each instance keeps a working clone; pull-on-start (`--memfs-startup blocking`) + push-on-write.
- Concurrency: one-writer-at-a-time / explicit commit-pull-merge. Conflict surface is narrow (different files auto-merge; rolling state isolated in `digest/`).
- **This is exactly the `gitea-backed-local-memfs` plan** (`docs/plans/2026-06-09-gitea-backed-local-memfs-{design,plan}.md`), now reframed as Plane 1. Canary (`docs` agent) is paused at Task 4 (seed done); resume on its own track. Letta support independently confirms git-sync of memfs with one-writer discipline is the right model.

## Plane 2 — Historical knowledge archive (the new core)
Conversation history is preserved and made recall-able as a **retrieval-optimized, layered corpus** — NOT a single markdown dump.

**Layout** (git repo / shared folder, e.g. `history/`):
- `raw/` — exact transcripts, one file per conversation/month, with stable anchors (`msg:<id>`, `conv:<id>`, timestamps, model, tool names, original ordering). **This is what we exported 2026-06-09** (`/Volumes/main-filestore/ai-PA-backups/conversation-archives/2026-06-09/` — per-agent JSONL/markdown for the working set + MC lineage, plus the 12.3 GB full `pg_dump` floor). Evidence layer.
- `episodes/` — curated event cards ("May 2026 local-mode migration," "approval-desync investigation"): summary, decisions, failed paths, key quotes, links back to raw anchors. High-signal.
- `entities/` — durable pages for agents, projects, people, servers, repos, tickets, long-running themes.
- `decisions/` — terse decision records (context, decision, why, date, consequences, links).
- `indexes/` — generated topic maps / `aliases.md` ("if searching X, also search Y") retrieval hints.

**Search = `qmd`** (or equivalent): local **keyword/BM25 + vector semantic + hybrid + reranking** over the files. This removes the keyword-only limitation of letta-code's built-in local recall, and indexes the *distilled* knowledge (episodes/decisions/entities) alongside raw — so "what did we learn over months?" becomes a strong query, not just "find the exact turn." **`qmd` is NOT installed yet — acquire it (or pick an equivalent local hybrid-search CLI over files); this is a dependency.**

**Retrieval UX (make it seamless — the failure mode is habit, not tech):**
- **Pinned policy** in `system/`: "For anything before the local-mode migration date, use the historical-archive skill. For recent local conversations, use native recall / `letta messages search`. If unsure, search both."
- **A `historical-recall` skill** (SKILL.md with exact commands): `qmd query "…" -c <collection> --files` → `qmd get <top-path>` → if it points to a raw anchor, open the raw transcript and expand around that `msg:<id>`/timestamp → answer with file-path/anchor citations.
- **Optional wrapper script** `historical-recall "<query>"` that hides qmd details and returns top paths + snippets (+ raw-context expansion). The skill just calls it.
- **Trigger rules** (in the policy): "before migration / old server / remember when / project & agent names / old tickets / we discussed" → archive; "earlier today / this local conversation / recent local-mode work" → native recall first.

**Distill pipeline (ongoing):** periodically export/summarize **new local conversations** into the same archive (raw + auto-drafted episode/decision cards), so old + new knowledge share one retrieval surface. Conceptually a recurring job (like the briefing crons).

This is genuinely usable by local agents: they have shell access (Bash/Read/Grep) and already run search tools — `qmd` over the archive is the same UX as the built-in recall subagent, just over a richer corpus. The one thing it is **not**: auto-blended into letta-code's built-in `letta messages search` (which only scans the local backend). That's acceptable — the pinned policy + skill make the agent reach for it.

## Plane 3 — Live conversation state (do NOT sync)
`~/.letta/lc-local-backend/conversations/<base64url(convId:agentId)>/{messages.jsonl, conversation.json, manifest.json, system-prompt.json}` is the **dangerous layer**: it is not a multi-writer replicated DB. Live-syncing it (Syncthing/git/Dropbox) across running instances invites message-ID collisions, concurrent writes, compaction divergence, tool-call/tool-result pairing breakage, and cache invalidation. **Each instance keeps its own live conversation state.** Continuity is provided by Planes 1 & 2, not by replicating this.
- Corollary: **drop the earlier "Path A" idea** of converting server history *into* the local backend for native recall — wrong layer to touch, per-backend only, and conflicts with this principle. History belongs in Plane 2.

## Multi-instance continuity model (the "trip" / pa-web / laptop question, resolved)
- **Best local-first path:** every instance has its own live conversations (Plane 3, local), and **all instances share** a synced **memfs** (Plane 1) + **qmd knowledge archive** (Plane 2). The agent is "continuous" because it searches the shared archive and updates shared durable memory.
- **Best product-native path** (if ever wanted): Letta Constellation/Cloud or a single remote environment — one agent across devices, natively. (Off-grain for us; noted.)
- **Do NOT** try to make multiple local backends literally be one agent — that's the distributed-systems hole above.

## Forward-looking: client topology (PWA, wearables) may moot the multi-instance machinery
The three-plane sync + handoff apparatus above only matters in a **thick-client** world — where multiple devices each run a *full local agent instance* (server runner, pa-web spawning local subprocesses, a laptop running its own offline agent). There is a second regime that largely **sidesteps it**:

- **Thin-client regime:** the PWA, phone, and **wearables** are *interfaces* to a **single always-on hosted brain** (the server agent, or Cloud/Constellation). They carry no live conversation state of their own; there's one agent, one Plane-3 — so multi-instance sync and handoff **don't arise.** Continuity is trivial because there's one brain.
- **If we finish the PWA as a thin client to one hosted agent, the multi-instance problem becomes moot** (the user's point). Note pa-web *today* is a thick-spawner (it spawns per-conversation local subprocesses); a thin-client PWA would change that — a real fork in the PWA design.

**Wearables (coming soon) raise new continuity implications and, importantly, push the SAME direction:**
- They're **offline/intermittent, voice/ambient, low-compute** — poor hosts for a full local agent. So they want to be **thin clients to one always-on brain**, not their own instance.
- Their offline-ness reintroduces the **capture-and-sync (outbox)** pattern from the trip sketch: capture intents/utterances locally when disconnected, replay to the hosted brain on reconnect — *not* a replicated live conversation.
- Ambient/always-on interaction raises **cross-surface continuity** (a wearable remark, a PWA chat, a Slack DM should land in one continuous experience) — which is delivered by **shared durable memory + the shared knowledge archive (Planes 1 & 2)**, exactly as for thick instances. So wearables **reinforce** the core conclusion: continuity comes from shared durable layers, never from replicating live state.

**The design-ahead question this forces:** decide the **client topology** before over-investing. If we go thin-client (one hosted brain + great PWA/wearable/phone clients + offline capture-sync), we may **not need** the multi-instance machinery (Plane-1 hub sync across instances, handoff) at all — we'd need *one* robust brain + clients. If we stay thick-instance (independent local agents per device, e.g. a fully-offline laptop agent), the three-plane model is required. Most likely: a **hybrid** — one always-on hosted brain for thin clients (phone/PWA/wearable), plus the option of a thick laptop instance for deep offline work — in which case we need the three planes *and* the thin-client path, with Planes 1 & 2 as the shared spine across both. **Don't build the full multi-instance sync until the PWA/wearable topology is decided**; the conversation-history *archive* (Plane 2) and *preservation* (done) are valuable under every topology, so they're safe to build now.

## Exception: occasional live-conversation handoff (documented, NOT built yet — too early)
*Captured per request; build only when a real use case appears.*

> **Q:** If I wanted to occasionally hand off live conversations, is there a workable mechanism that's an exception rather than the rule?
> **A (Letta support):** Yes — as a **handoff snapshot, not live sync.**
> **Recommended mechanism:**
> 1. Source instance reaches a stopping point.
> 2. Source agent writes a **handoff packet** into the shared archive, e.g. `handoffs/2026-06-09-mac-to-linux.md`: current goal, recent decisions, unresolved questions, files touched / commands run, key raw-transcript anchors, "next action."
> 3. Source copies the relevant raw transcript into `raw/`.
> 4. Destination starts a **new local conversation**, reads the handoff packet + qmd results around the anchors, and continues; later writes its own handoff/update back.
> Continuity = explicit state transfer + searchable archive, not pretending two backends share one live conversation.
>
> **Riskier "native" variant (takeover/import hack, NOT supported sync):** stop the source backend, copy the specific `conversations/<base64url(convId:agentId)>/` dir to the destination, ensure the destination has the **same local agent ID/agent record**, then start the destination. Works **only** if you preserve agent IDs and never have both sides writing.
>
> **Do NOT:** copy live while either instance is running, or merge two edited `messages.jsonl` histories — tool-call/tool-result pairing, compaction state, in-context IDs, and message IDs make that fragile.

Design stance: if/when handoff is needed, use the **handoff-snapshot** pattern (it's just Plane 2 + a packet convention). The takeover-import variant is an emergency-only escape hatch.

## How existing artifacts snap in
- `gitea-backed-local-memfs` design/plan → **Plane 1** (resume the canary on its track).
- Conversation export (2026-06-09) → **Plane 2 `raw/`** + the cold `pg_dump` floor.
- Distributed-ecosystem offline/online sketch → its "what syncs" question is **answered by the three planes** (memfs + archive sync; live state doesn't). The trip = the same model with intermittent connectivity (sync planes 1 & 2 on connectivity windows; live conversations are inherently local anyway).
- Slackbot "brain" question → orthogonal; whatever agent is the Slack brain still uses these three planes.

## Dependencies & open decisions
1. **`qmd` (or equivalent)** — not installed. Acquire it, or choose an equivalent local hybrid (BM25 + embeddings + rerank) over files. **Blocks Plane 2's search.**
2. **Archive location** — a git repo / Gitea repo (like canonical) so all instances reach it; raw + curated layers; index rebuilt per machine.
3. **Curation effort** — `episodes/entities/decisions` are an ongoing investment; first pass can be auto-drafted from raw. The **quick win is qmd over `raw/` + the skill** (semantic recall over full history now); curation accrues over time.
4. **Distill cadence** — how often new local conversations get exported/summarized into the archive.
5. **Which history in the archive** — full MC lineage (companion → kinara → MC) confirmed in scope.

## Sequencing
1. **Now (quick win):** acquire `qmd`; index the existing `raw/` export as one collection; add the `historical-recall` skill + pinned policy + `aliases.md` → MC gets semantic recall of its full lineage immediately.
2. **Soon:** auto-draft first-pass `episodes/entities/decisions` from the raw export.
3. **Ongoing:** the distill pipeline (new local convos → archive) + move the archive into the shared hub.
4. **Parallel track:** resume the Plane-1 memfs-hub canary.
Together, planes 1 + 2 deliver the "continuous agent across instances" goal; plane 3 stays local by design.
