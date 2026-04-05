---
title: "refactor: Self-regulating backtrace_task with depth tiers and risk-aware heuristics"
type: refactor
status: active
date: 2026-04-05
---

# refactor: Self-regulating backtrace_task with depth tiers and risk-aware heuristics

## Overview

Refactor `backtrace_task` from a fixed-depth search tool into a self-regulating tool that internally selects how deep to search based on risk/impact signals, node coverage goals, and yield-based iteration. The worker agent's linear 4-call protocol is unchanged — all depth intelligence moves inside the tool. Also add `suggested_subtasks` field to `write_packet_info`.

## Problem Frame

`backtrace_task` currently uses a fixed `max_hops` parameter (default 3) regardless of task complexity. This produces:

- **Over-search for simple tasks:** "Read this article" or "Sign this form" runs 3 archival search iterations when zero would suffice.
- **Under-search for high-stakes tasks:** Short emails about licensing/contracts/board decisions get the same 3 hops as a lunch order.
- **No risk awareness:** A task containing "confidential", "licensing", or "board" gets the same depth as "check this spreadsheet."

MC's analysis (from this session) identified that ~80-90% of the depth decision can be made by heuristics if they include risk/impact triggers, not just source complexity. The key insight: **short but high-stakes tasks are the primary under-search failure mode.**

## Requirements Trace

- R1. `backtrace_task` internally selects a depth tier (0-3) based on risk tokens, node coverage, and task complexity
- R2. Yield-based iteration within the tool: stop when no new high-signal anchors emerge or nodes are filled
- R3. Hard budgets enforced: max queries per iteration, max iterations, max wall-clock time
- R4. Return value includes `depth_tier_selected`, `depth_reason`, `node_coverage`, `iterations_run`, `gaps_remaining`
- R5. Self-contained tasks (no fetch_hint, short source, no entities) exit at tier 0 with minimal work
- R6. Risk tokens force at least tier 2 even for short/simple sources
- R7. Worker agent protocol unchanged (still calls `backtrace_task` once, gets everything back)
- R8. `write_packet_info` gains `suggested_subtasks` field for discrete sub-work items surfaced during enrichment
- R9. Backward-compatible — tasks agent's enrichment pipeline and MC still call `backtrace_task` with existing interface

## Scope Boundaries

- Not changing the worker agent protocol (still 4 linear calls)
- Not adding per-hop agent decision points (this is the explicit alternative we rejected)
- Not changing `fetch_source_content` or `stage_resource`
- Not changing how the confirmation handler dispatches
- Not implementing cross-origin source-specific searches (email threads, Slack channel lookback, Drive sharing trails) — those are future enhancements to the search strategy within each tier
- Not changing the enrichment scanner or its gating

## Context & Research

### Relevant Code and Patterns

- `letta/backtrace_task_tool.py`: current tool — 5-tier anchor extraction, 3-iteration archival search loop, node classification, mismatch warnings. ~320 lines.
- `letta/write_packet_info_tool.py`: current tool — 11 string params, auto-populates from stored backtrace materials, auto-triggers reassemble endpoint. ~265 lines.
- `letta/refine_task_description_tool.py`: calls backtrace internally (compact version of same logic). Must stay in sync with backtrace changes or consume backtrace_task's output.
- `scheduler-service/scripts/enrichment-scanner.py`: dispatches enrichment messages that trigger backtrace via the tasks agent.

### MC's Analysis (session context, not a file)

MC identified three signal buckets for depth selection:
- **A) Risk/impact** (should dominate): legal, licensing, confidential, board, budget, partner, deadline, business development, contract, SOW, renewal, submission portal
- **B) Ambiguity/missing artifact**: "the doc" without URL, multiple candidate docs, partial artifact pointers
- **C) Coordination complexity**: multiple stakeholders, cross-references ("as we discussed"), many URLs/attachments, multiple systems implied

MC recommended internal iteration with yield-based stop + hard budgets, returning `depth_tier_selected`, `node_coverage`, `iterations_run`, `gaps_remaining`, and `suggested_subtasks`.

## Key Technical Decisions

- **Depth tiers as deterministic selection, not LLM judgment:** The tier is computed from heuristics (risk token count, source length, entity density, URL count) inside the tool. No agent decision point. The tool returns the tier selected and why, so the worker agent's synthesis can reference it.

- **Risk tokens force minimum depth:** If ANY risk token is found in source content, minimum tier is 2 regardless of source length or complexity. This directly addresses MC's "short but high-stakes" under-search failure mode. Risk tokens include: legal, licensing, confidential, board, budget, partner, deadline, business development, contract, SOW, renewal, submission, compliance, FERPA, COPPA, accessibility, privacy, security, audit, approval, trustees, IP, announcement, press.

- **Yield-based stop within each tier:** Each iteration checks whether new high-signal anchors emerged AND whether node coverage improved. If neither: stop. This prevents the over-search problem (verbose meeting transcripts generating many anchors that don't improve coverage).

- **Hard budgets per tier:** Prevent runaway regardless of yield signals.

  | Tier | Max iterations | Max queries | Max sources opened | Intended for |
  |------|---------------|-------------|-------------------|-------------|
  | 0 | 0 | 0 | 0 | Self-contained tasks (no backtrace needed) |
  | 1 | 1 | 10 | 5 | Simple tasks — fill direct-action + provenance |
  | 2 | 2 | 20 | 10 | Standard tasks — fill all three nodes if feasible |
  | 3 | 3 | 30 | 15 | High-stakes — full cross-origin backtrace |

- **Tier selection heuristic:** Computed as `max(complexity_tier, risk_tier)` where:
  - `complexity_tier`: based on source length, URL count, entity count, system references
  - `risk_tier`: 0 if no risk tokens, 2 if any risk token found, 3 if multiple risk categories
  - Result: simple + low-risk = tier 0-1; complex + low-risk = tier 1-2; any risk = tier 2-3

- **`suggested_subtasks` in write_packet_info:** A new optional string parameter (newline-separated). Renders in the OmniFocus note as a "Suggested Subtasks" section. The worker agent populates this from patterns in the backtrace materials (enumerated asks, multi-part requests, prerequisites discovered).

## Open Questions

### Resolved During Planning

- **Should tier 0 skip archival search entirely?** Yes. Self-contained tasks (e.g., "read this article") have their source content already; archival search adds noise. Tier 0 returns the passage metadata + source content as-is.
- **Should the enrichment pipeline (tasks agent) use the same self-regulating logic?** Yes. The `refine_task_description` tool calls backtrace inline — it will benefit from the same tier logic since it receives the same return structure.
- **How does this interact with the worker's backtrace call?** Worker calls `backtrace_task(ref_id)` exactly as before. The tool returns more metadata (tier, coverage, gaps) but the agent's next step (write_packet_info) is unchanged.

### Deferred to Implementation

- **Exact risk token list:** Start with MC's list + business development. Tune based on observed under-search patterns after deployment.
- **Tier boundary thresholds:** Source length cutoffs for tier selection (e.g., <200 chars + no entities → tier 0). Tune empirically.
- **Cross-origin bridge logic:** MC described per-origin search strategies (email→thread, Slack→channel lookback, Drive→sharing trail). These would enhance search within each tier but are separate from the tier selection itself. Defer to a future plan.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
backtrace_task(ref_id) entry:
  │
  ├── Step 1: Fetch passage (existing)
  ├── Step 2: Fetch full source content (existing)
  │
  ├── Step 2.5: SELECT DEPTH TIER (new)
  │   ├── Scan source for risk tokens → risk_tier
  │   ├── Count entities, URLs, source length → complexity_tier
  │   ├── tier = max(complexity_tier, risk_tier)
  │   └── If tier == 0: skip to Step 5 (return minimal result)
  │
  ├── Step 3: Extract anchors (existing, unchanged)
  │
  ├── Step 4: Iterative search (modified)
  │   ├── Budget: iterations ≤ tier budget, queries ≤ tier budget
  │   ├── Each iteration:
  │   │   ├── Search archival with current anchors
  │   │   ├── Classify hits (artifact, intent, related tasks)
  │   │   ├── Check node coverage
  │   │   ├── Extract new anchors from hits
  │   │   └── Yield check: new anchors found? coverage improved?
  │   │       ├── Yes: continue (if budget allows)
  │   │       └── No: stop (diminishing returns)
  │   └── Record iterations_run, queries_run
  │
  ├── Step 5: Build result (modified)
  │   ├── Include existing fields (anchors, candidates, coverage, etc.)
  │   ├── Add: depth_tier_selected, depth_reason (top 3 signals)
  │   ├── Add: iterations_run, queries_run
  │   ├── Add: gaps_remaining (unfilled nodes, unresolved artifacts)
  │   └── Add: suggested_next_hops (for future deeper passes)
  │
  └── Return
```

## Implementation Units

- [ ] **Unit 1: Add depth tier selection logic to backtrace_task**

**Goal:** Compute the depth tier from risk tokens + complexity signals before the search loop begins. Gate the search loop on the selected tier's budget.

**Requirements:** R1, R5, R6

**Dependencies:** None

**Files:**
- Modify: `letta/backtrace_task_tool.py`

**Approach:**
- After Step 2 (fetch source content), add Step 2.5: tier selection
- Define `RISK_TOKENS` set: legal, licensing, confidential, board, budget, partner, deadline, contract, SOW, renewal, submission, compliance, FERPA, COPPA, accessibility, privacy, security, audit, approval, trustees, IP, announcement, press, "business development"
- Scan `all_text` (task description + full content) for risk tokens. Count distinct risk categories hit.
- Compute `risk_tier`: 0 if no hits, 2 if 1-2 categories, 3 if 3+ categories
- Compute `complexity_tier`: 0 if source < 200 chars + no URLs + no proper nouns; 1 if source < 1000 chars or few entities; 2 otherwise; 3 if 5+ URLs or 10+ proper nouns or multiple system references
- Final tier = max(risk_tier, complexity_tier)
- If tier == 0: skip Steps 3-4 entirely, return minimal result with `depth_tier_selected: 0`
- Modify the existing iteration loop (Step 4) to respect tier budgets instead of fixed `max_hops`
- Record `depth_reason`: top 3 signals that drove the tier selection

**Patterns to follow:**
- Existing `STOP` words set pattern for token lists
- Existing `search_terms` construction for anchor density analysis

**Test scenarios:**
- Happy path: "Read this article" (no risk tokens, short source, no URLs) → tier 0, no search, returns in <1s
- Happy path: "Review the budget spreadsheet" (risk token "budget", short source) → tier 2 minimum
- Happy path: "This is confidential until the board meets" (risk "confidential" + "board") → tier 3
- Happy path: Long meeting transcript with many names (high complexity, no risk) → tier 2, stops early on diminishing returns
- Edge case: source has risk token in email signature ("Compliance Officer" in sender info) → still triggers tier 2 (acceptable false positive)
- Integration: worker calls backtrace_task on a simple task → gets tier 0 result → write_packet_info handles it correctly

**Verification:**
- Simple tasks complete in <2s with tier 0
- Risk-bearing tasks always get tier ≥ 2
- Returned `depth_tier_selected` and `depth_reason` are present and accurate

---

- [ ] **Unit 2: Implement yield-based iteration stop within search loop**

**Goal:** Replace the fixed "stop when no new anchors" logic with a richer yield check that considers node coverage improvement, not just anchor discovery.

**Requirements:** R2, R3

**Dependencies:** Unit 1 (tier budgets must be in place)

**Files:**
- Modify: `letta/backtrace_task_tool.py`

**Approach:**
- Before each iteration, record current `node_coverage` snapshot (artifact filled? intent filled?)
- After each iteration, compare: did artifact_candidates grow? did intent_candidates grow? did related_tasks find new relevant entries?
- Continue if: new nodes filled OR new high-signal anchors found (proper nouns not in existing set) AND budget allows
- Stop if: coverage unchanged AND no new high-signal anchors (existing "diminishing returns" check enhanced)
- Add `iterations_run` and `queries_run` counters to the return value
- Respect per-tier max_iterations and max_queries from Unit 1

**Patterns to follow:**
- Existing `new_anchors` list and `searched_terms` set for dedup
- Existing `seen_ids` set for passage dedup

**Test scenarios:**
- Happy path: first iteration fills all three nodes → stops at iteration 1 even if budget allows more
- Happy path: first iteration finds artifact but not intent → continues; second finds intent → stops
- Happy path: three iterations, each finding new anchors but no new node coverage → stops at iteration 3 (budget hit, not yield)
- Edge case: archival is empty (new system) → tier selection still works, iteration loop exits immediately

**Verification:**
- Tasks with rich archival context complete in fewer iterations than max budget
- `iterations_run` accurately reflects actual iterations (not always max)

---

- [ ] **Unit 3: Enhance return value with depth metadata and gaps**

**Goal:** Return value includes tier selection rationale, coverage gaps, and suggested next-hop candidates so the worker agent (and PACKET INFO) can report what the tool found and what it couldn't find.

**Requirements:** R4

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `letta/backtrace_task_tool.py`

**Approach:**
- Add to return dict:
  - `depth_tier_selected`: integer 0-3
  - `depth_reason`: list of top 3 signals (e.g., "risk:confidential", "complexity:5_urls", "coverage:intent_missing")
  - `iterations_run`: integer
  - `queries_run`: integer
  - `gaps_remaining`: list of strings describing what's unfilled (e.g., "intent_genesis not found", "artifact_provenance uncertain — multiple candidates")
  - `suggested_next_hops`: list of hop candidates the tool identified but didn't chase (beyond budget) — for future deeper passes or human follow-up
- Existing fields preserved (backward-compatible)
- `refine_task_description` (which calls backtrace inline) also gets these new fields in its compact return

**Patterns to follow:**
- Existing `node_coverage` dict structure
- Existing `hop_candidates` list structure

**Test scenarios:**
- Happy path: tier 0 task → `gaps_remaining` includes "no search performed (self-contained task)"
- Happy path: tier 2 task with missing intent → `gaps_remaining` includes "intent_genesis not found"
- Happy path: full coverage → `gaps_remaining` is empty list
- Integration: worker agent's write_packet_info receives these fields and can reference them in unknowns/agent_notes

**Verification:**
- Every backtrace_task call returns all new fields
- `gaps_remaining` accurately reflects unfilled nodes

---

- [ ] **Unit 4: Add `suggested_subtasks` field to write_packet_info**

**Goal:** `write_packet_info` accepts a new `suggested_subtasks` parameter for discrete sub-work items. Renders in the OmniFocus note.

**Requirements:** R8

**Dependencies:** None (independent of backtrace refactor)

**Files:**
- Modify: `letta/write_packet_info_tool.py`
- Modify: `pa-web-ui/app.py` (`parse_archival_passage` to extract subtasks; `_build_work_packet_segments` to render them)
- Modify: `pa-web-ui/static/js/sidebar.js` (render subtasks in Details accordion)

**Approach:**
- Add `suggested_subtasks: Optional[str] = None` parameter to `write_packet_info`. One subtask per line, agent writes free-form.
- Write as a "Suggested Subtasks" section in PACKET INFO (after knowns/unknowns, before agent notes)
- `parse_archival_passage` extracts the new section into `packet['suggested_subtasks']` list
- `_build_work_packet_segments` renders as a bulleted list with a "Suggested Subtasks" header in the OmniFocus note
- Sidebar accordion renders subtasks with checkbox-style markers (visual hint, not interactive)

**Patterns to follow:**
- Existing `resources` and `related_tasks` fields for the tool parameter pattern
- Existing `knowns`/`unknowns` rendering in `_build_work_packet_segments` and sidebar.js

**Test scenarios:**
- Happy path: write_packet_info with suggested_subtasks="Review budget section\nCheck deadline" → PACKET INFO includes "Suggested Subtasks" section, OmniFocus note shows 2 subtask bullets
- Happy path: write_packet_info without suggested_subtasks → no subtask section (backward compatible)
- Edge case: empty string → treated as no subtasks
- Integration: sidebar Details accordion shows subtasks for a task that has them

**Verification:**
- OmniFocus note includes "Suggested Subtasks" section with bullet items
- Sidebar shows subtasks in Backtrace section
- Existing tasks without subtasks continue to render correctly

---

- [ ] **Unit 5: Update refine_task_description's inline backtrace**

**Goal:** The inline backtrace logic in `refine_task_description` benefits from the same self-regulating depth. Ensure the compact backtrace in the enrichment pipeline also respects tiers.

**Requirements:** R9 (backward compatibility)

**Dependencies:** Units 1-3 (backtrace refactor must be complete)

**Files:**
- Modify: `letta/refine_task_description_tool.py`

**Approach:**
- `refine_task_description` currently has an inline copy of the backtrace search loop (from Unit 2b of enrichment pipeline plan). It needs to adopt the same tier selection and yield-based stop.
- Two options: (a) refactor the inline code to match backtrace_task's new structure, or (b) have refine_task_description call backtrace_task via HTTP instead of inlining.
- Preferred: option (a) — keep inline to preserve the single-tool-call pattern and compact return. Port the tier selection logic and budget constants.
- The compact summary return pattern ("Backtrace complete for ref_id: N artifacts, N intents...") remains unchanged — it already summarizes the materials regardless of depth.

**Patterns to follow:**
- Existing inline backtrace in refine_task_description (lines ~233-460)
- backtrace_task's new tier selection from Unit 1

**Test scenarios:**
- Happy path: enrichment scanner dispatches a simple task → refine_task_description selects tier 0-1, skips deep search
- Happy path: enrichment scanner dispatches a risk-bearing task → refine_task_description selects tier 2+
- Integration: enrichment pipeline end-to-end still works with the refactored inline backtrace

**Verification:**
- Enrichment pipeline produces the same quality output for existing task types
- Simple tasks enrich faster (fewer unnecessary searches)
- Risk-bearing tasks still get full PACKET INFO

---

- [ ] **Unit 6: Remove skip-dispatch gate from confirmation handler**

**Goal:** Always dispatch the worker agent on task confirmation, regardless of PACKET INFO completeness.

**Requirements:** R7 (protocol unchanged — worker always runs now)

**Dependencies:** Units 1-3 (worker needs the self-regulating backtrace so it doesn't over-search already-enriched tasks)

**Files:**
- Modify: `pa-web-ui/app.py` (remove `has_complete_enrichment` gate logic)

**Approach:**
- Remove the `should_dispatch_mc` / `has_complete_enrichment` gate that currently skips worker dispatch when PACKET INFO is already populated
- The worker always runs on confirm. If PACKET INFO is already complete, backtrace_task's tier selection will give it tier 0-1 (fast, minimal work) based on the already-enriched content
- The worker's write_packet_info call may add `suggested_subtasks` or `agent_notes` that the first-pass enrichment didn't produce — always a net positive
- Keep the rush flag plumbing (Add-and-Go still signals rush behavior)

**Patterns to follow:**
- Existing dispatch thread pattern

**Test scenarios:**
- Happy path: task with complete PACKET INFO confirmed → worker dispatched, runs tier 0-1, adds minimal content, reassemble runs
- Happy path: task with no PACKET INFO confirmed → worker dispatched, runs tier 2-3, produces full packet
- Happy path: rush confirmation → worker dispatched with rush flag, follows rush protocol

**Verification:**
- Every confirmation dispatches to the worker (no skip path)
- Worker on already-enriched tasks completes quickly without over-searching

## System-Wide Impact

- **Interaction graph:** backtrace_task is called by: (1) enrichment scanner → tasks agent → refine_task_description (inline), (2) worker agent → backtrace_task (direct tool call). Both paths benefit from self-regulation. No new callers.
- **Error propagation:** Tier selection errors (wrong tier) degrade quality, not functionality. The tool still returns materials — just more or fewer of them. No new failure modes.
- **State lifecycle risks:** None. The tool is stateless. Tier selection is computed fresh per invocation.
- **API surface parity:** Return value gains new fields (additive, backward-compatible). Existing consumers ignore unknown fields.
- **Integration coverage:** End-to-end test: enrichment pipeline processes a simple task (should be fast/shallow) and a risk-bearing task (should be deep). Worker processes both types. OmniFocus note reflects depth difference.

## Risks & Dependencies

- **Risk token false positives:** Email signatures containing "Compliance Officer" or "Legal Counsel" may trigger tier 2 for routine messages. Mitigation: acceptable — false positive (slightly deeper search) is better than false negative (missed risk).
- **Tier threshold tuning:** Initial thresholds are educated guesses from MC's analysis. May need adjustment after observing real task distribution. Mitigation: thresholds are constants at the top of the function, easy to tune.
- **refine_task_description sync burden:** Inline backtrace code in refine_task_description must stay in sync with backtrace_task changes. Mitigation: Unit 5 explicitly addresses this. Long-term, consider having refine_task_description call backtrace_task via HTTP to eliminate the sync issue.

## Documentation / Operational Notes

- Update worker agent persona to mention that backtrace_task now self-regulates depth (no max_hops parameter needed)
- Log tier selection for first 2 weeks to validate heuristics against real tasks

## Sources & References

- Related code: `letta/backtrace_task_tool.py`, `letta/write_packet_info_tool.py`, `letta/refine_task_description_tool.py`
- MC's analysis: depth tier signals, risk/impact tokens, yield-based stop conditions (session context, 2026-04-05)
- Related plans: `docs/plans/2026-04-03-001-feat-enrichment-pipeline-orchestration-plan.md`, `docs/plans/2026-04-04-001-feat-work-packet-assembly-plan.md`
