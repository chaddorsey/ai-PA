# Newsletter / Info-Scanning Loop — planning seed (2026-06-11)

**Status:** idea / not yet scoped. Captured for later planning at Chad's request.

**Goal (Chad's words):** "We ultimately/soon want to build a newsletter and other-info
scanning loop. When we do, we should consider the patterns here."

**Reference:** *AI Newsletter Research Agent* — https://aimaker.substack.com/p/ai-newsletter-research-agent
(fetched 2026-06-11). The author wires it with Make.com + Tavily + Claude Code.

---

## What the reference agent does (its pipeline)

1. **Ingestion** — RSS feeds, Substack subscriptions, public URLs / product blogs,
   optional email newsletters; Tavily API for supplementary research fetches.
2. **Signal extraction** — pull recurring themes / titles / claims / reader-problems /
   formats across sources.
3. **Contextual filtering** — compare extracted signals against *your archive,
   current projects, and decision criteria* (grounds external noise in internal knowledge).
4. **Ranking & scoring** — return 5–7 prioritized signals with a relevance assessment.
5. **Action labeling** — tag each item: write / build / research / discuss / save / skip.
6. **Delivery** — weekly digest (daily monitoring optional).

Reusable patterns it names: distributed-source consolidation (one monitoring point for
heterogeneous feeds); signal→decision mapping; context-aware filtering; "permission to
ignore" (dedup separates noise from patterns); role-agnostic framework.

---

## Why this maps almost 1:1 onto infra we ALREADY have

When we plan this, **don't build a new stack** — it's the analytics/task pipeline shape
again. The parallels:

| Reference stage | Our existing equivalent (reuse this) |
|---|---|
| Ingestion (RSS/Substack/URL/email + Tavily) | Source **detectors** → `pa_web.task_queue` pattern ([[project_task_pipelines]]). Add a feed/RSS detector + a fetch step (WebFetch/WebSearch, or Tavily). Dedup with sha256 like the analytics **bronze** layer. |
| Signal extraction | The pulse **snapshot/compose** stages + per-source extraction recipes ([[project_analytics_pipeline]]). |
| Contextual filtering vs. archive/projects | **qmd Plane-2 history archive** + `agents-canonical` (projects/working-context) + memfs ([[project_plane2_history_archive]]). This is the differentiator — we already have the "internal knowledge" substrate to ground relevance. |
| Ranking → 5–7 signals | A **local curator/research agent** invoked via the runner (`:8920`) — same pattern as the analytics **vibe** stage (`run-analytics-stage.sh vibe`). |
| Action labeling (write/build/research/discuss/save/skip) | Mirrors our `task_queue` source taxonomy + enrichment; "save/research/build" items could even spawn real `pa_web.tasks`. |
| Weekly delivery | **launchd-scheduled stage** (like `com.ai-pa.analytics-*`) → write `signals/<date>/newsletter-digest.md` → **materialize `signals/current/newsletter.md`** ([[project_analytics_pipeline]] current-cells) → surface in MC's **daily/weekly kickoff** recipe (`mc_cli_recipes.md`). |

**Make.com → our equivalent:** launchd plists + `scheduler-service` crons + a
`scripts/run-newsletter-stage.sh` dispatcher (clone of `run-analytics-stage.sh`:
PATH/PYTHONPATH/pa-tools.env setup, stage dispatch, HOME logs).
**Tavily → our equivalent:** WebFetch/WebSearch first; evaluate Tavily only if we need
better full-text feed fetching.
**Claude Code → our equivalent:** local letta-code agent(s) via the push-receiver/runner.

## Open questions for the eventual brainstorm
- Source list + how Chad curates feeds (canonical `feeds.yml`? OPML?).
- Cadence: weekly digest vs. daily monitoring vs. both (analytics pipeline already proves both).
- Does it emit **tasks** (write/build/research) into `pa_web.tasks`, or stay a read-only digest?
- Owner agent: extend pulse (already the "monitoring/search specialist") or a new curator agent?
- Relevance grounding: how much to lean on qmd archive vs. canonical projects vs. explicit rules.

**Next step when prioritized:** run the `brainstorming` skill against this seed, then a plan.
