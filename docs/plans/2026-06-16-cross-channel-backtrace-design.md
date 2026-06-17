# Cross-Channel Backtrace & Work-Packet Enrichment — Design

**Date:** 2026-06-16
**Status:** Design (approved in brainstorm; pending spec review → implementation plan)
**Related:** [[project_work_packet_materials]], [[project_task_pipelines]], `letta/backtrace_task_tool.py`, `letta/fetch_source_content_tool.py`, `scripts/scan_meeting_markers.py`, `scripts/draft_meeting_followup.py`

## Problem

When a task is confirmed, its OmniFocus work-packet note should carry the *full* set of relevant materials — the artifact to act on plus the threads that give it context — drawn from across channels. Today it carries almost nothing beyond the originating source.

Concrete failure: the **Vernier SOW** task's note showed only the meeting note it came from. Yet asking the agent directly surfaced, in ~30 seconds, the **prior SOW Google Doc** and the **Slack status threads** with permalinks. The capability exists; the enrichment pipeline doesn't use it.

## Current state (what "backtrace" does today)

Per-task enrichment (enrichment-scanner → local tasks/docs agent):

1. `fetch_source_content(ref_id)` — loads the **one** source the task came from (email/Slack/meeting/docs-comment), as an ANCHOR block + that source's permalink.
2. `backtrace_task(ref_id)` — extracts anchors (URLs, doc-IDs, proper nouns, acronyms, distinctive phrases, participants) and builds a prioritized `search_terms[:20]` list — **then discards it**. The "hop search" (Step 4) is a **stub** wired to the retired Letta archival (`archival_hits = []`), so `artifact_candidates` / `intent_candidates` / `related_tasks` are **always empty**. The only `hop_candidates` are URLs **already present** in the source text (+ the source's own permalink).
3. Agent synthesizes the packet from that thin input and calls `write_packet_info`.

**Core gap:** "backtrace" is really *"extract anchors from one source + harvest links pasted in it."* It never searches another channel, so unlinked-but-relevant materials (the prior SOW, the Slack status thread) are never found. The code even builds the exact `search_terms` you'd feed to Drive/Slack search, then throws them away.

## Decisions (from brainstorm)

| Axis | Decision |
|---|---|
| **Trigger** | Cheap single-source enrichment stays for all extracted tasks (triage). The **cross-channel fan-out runs on CONFIRM** (task promoted to OmniFocus) — bounds cost to tasks that matter. |
| **Channels** | Google **Drive** (+ comments), **Slack**, **Gmail**, **internal history** (past tasks + past meetings), plus **memory** channels (see below). |
| **Curation** | **Tiered**: Primary (the artifact + top 1–2, staged as offline copies) / Supporting (status threads, decisions, prior tasks) / Related (long tail). Ranked within tiers. Reuses the existing `[primary]/[secondary]/[background]` resource markers → **no schema change**. |
| **Ranking/judgment** | **Agent-driven** (recipe) — the agent decides terms, searches adaptively (chasing threads), and judges relevance/tier. |
| **Reliability** | Read-only **searches** are agent-driven; **writes/staging** go through verified CLIs (`task stage`, `task packet-write`) so the agent can't fabricate resources; a **deterministic backstop** flags under-delivery. |
| **Memory** | **Both** a first-layer backbone *and* additional sources, run by the **running agent** (no MC routing; seam left for later). |
| **Scope** | **Tasks now.** Engine factored trigger-agnostic so **meeting prep** reuses it later (separate spec). |
| **Latency** | **Async** — confirm is never blocked; the note enriches tens of seconds later via the existing reassemble path. |

## Role of memory (explicit)

Memory is not just another channel — it has two roles:

1. **First-layer backbone (runs BEFORE the channel searches).** The running agent consults **canonical** (shared truth: people, projects, aliases, prior decisions, working facts) + its own **memfs** (already in-context) to *ground and expand the anchors* and form a *relevance frame*. E.g. "Vernier SOW" → the biology collaboration, people (Tom, Laurie), known aliases, "a prior SOW exists." This sharpens every downstream channel query and improves relevance judgment. Highest-leverage use.
2. **Additional sources (folded into the fan-out).** qmd-backed channels:
   - `canonical` → project facts/decisions (usually **Supporting**),
   - `history` → prior-conversation recall over the history archive ("have we discussed this?") (**Supporting/Related**),
   - `reference` → Evernote/NYT/Twitter background (**Related/background**).

Both roles **compound as memory grows** — same engine, better output over time — and pre-wire meeting prep, where grounding matters even more.

## Architecture / components

A **trigger-agnostic engine** + a **task consumer**.

### Engine

1. **Anchor provider** — `backtrace_task(ref_id)`, cleaned up: keep anchor extraction + the prioritized `search_terms` (expose them; stop discarding). **Delete the dead Step 4–7 archival classification.** Returns anchors + `search_terms` + the originating source's known URLs. (Meeting-prep later supplies anchors differently — attendees/title/agenda.)
2. **`task xsearch` — the one new primitive.** `task xsearch --terms "t1,t2,…" [--channels drive,slack,gmail,tasks,meetings,canonical,history,reference]` runs the selected channel searches **concurrently** and returns **normalized, deduped** candidates as JSON: `{channel, title, url, permalink, snippet, date}`. Per channel:
   - drive → `gws drive files list q=` (+ comments),
   - gmail → `gws gmail users messages list q=` → permalink,
   - slack → `slack` search → permalink,
   - tasks → `task search --text`,
   - meetings → Granola/`qmd` over meeting exports,
   - canonical / history / reference → `qmd` over the respective collections.
   Search **execution** is deterministic/reproducible/fast; the agent decides terms + judges. Each channel **degrades independently and loudly** (one channel down ≠ silent empty; the result notes which channels failed).
3. **Tiering** — reuse existing resource markers: `[primary]`=Primary (staged), `[secondary]`=Supporting, `[background]`=Related. No schema change.

### Task consumer

4. **Recipe** `cross_channel_backtrace.md` (agent memfs) — the format contract + procedure:
   `memory-ground (canonical + memfs) → xsearch (×N, refining terms as threads are chased) → judge & tier → stage Primary items (task stage) → task packet-write with tiered resources → report`.
   Carries the resource-line grammar (`[tier] label — url | offline: openfile://… (role)`).
5. **Trigger** — the confirm handler's existing work-packet gate dispatches this recipe (async; replaces/augments today's thin enrichment for confirmed tasks).
6. **Renderer** — `_build_work_packet_segments` groups the Resources block under **Primary / Supporting / Related** headers; reuses today's per-line link + dual-link/stage rendering.
7. **Backstop** — `scripts/check-packet-enrichment.py` (or folded into an existing cadence): for recently-confirmed tasks, verify the packet gained cross-channel resources (more than just the originating source / >1 channel); if thin, flag + retry. Loud — no silent under-delivery.

## Data flow

```
confirm
  → work-packet gate
  → push agent (cross_channel_backtrace recipe)
      → backtrace_task(ref_id): anchors + search_terms
      → memory-ground: canonical + agent memfs → enriched terms + relevance frame
      → task xsearch ×N (adaptive) across drive/slack/gmail/tasks/meetings/canonical/history/reference
      → agent judges + tiers (Primary/Supporting/Related)
      → task stage (Primary offline copies)  +  task packet-write (tiered resources)
  → enrichment.packet_info
  → reassemble OF note (tiered render)
  → backstop verifies cross-channel resources present
```

## Reliability / error handling

- **Searches** are read-only → low fabrication risk; agent-driven is acceptable here.
- **Writes/staging** go through `task stage` / `task packet-write`, which perform the real action and return real IDs/paths → the agent cannot report a staged file or resource that doesn't exist.
- **`xsearch`** handles per-channel CLI/MCP/Hub failures gracefully and reports gaps (never a silent empty); mirrors the marker-scanner's loud-degrade discipline.
- **Backstop** catches agent under-delivery (thin packet on a confirmed task) and flags/retries.
- **Estimate/actuals eval loop** is untouched (resources work is additive; no writes to `original_est_minutes`/`revised_est_minutes`/`actual_minutes` or the `Agent Estimate:` line).

## Testing

- **Unit:** `task xsearch` — mock channel CLIs → normalized/deduped output, per-channel failure handling, channel selection. Tiered renderer — Primary/Supporting/Related grouping + existing link/dual-link behavior preserved.
- **E2E:** re-confirm **Vernier SOW** → packet must contain the prior SOW Google Doc (Primary/Supporting) + a Slack status thread (Supporting), correctly tiered — the exact gap today. Backstop: a thin packet → flagged.
- **Memory:** a task whose canonical entry has aliases → grounding expands the search terms (verify the expanded terms reach `xsearch`).

## Meeting-prep seam (built-for, not built-now)

Shared engine = `xsearch` (incl. memory channels) + tiering + the recipe's search/judge loop + memory grounding. Task consumer = `backtrace_task` anchors + on-confirm trigger + `packet-write`. **Meeting-prep consumer (future spec)** = meeting anchors (attendees/title/agenda) + pre-meeting trigger + prep-brief framing, reusing the same three pieces. Document the seam so meeting prep is additive.

## Out of scope (this spec)

- Meeting-prep consumer itself (separate spec; engine designed for it).
- Routing backtrace through MC/Kinara for its richer memory (seam noted; deferred).
- Graphiti knowledge-graph channel (entity extraction is OFF for cost).
- Re-running fan-out on every extracted task (triage stays single-source).
