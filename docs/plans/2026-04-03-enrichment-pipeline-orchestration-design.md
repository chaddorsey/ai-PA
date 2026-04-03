# Enrichment Pipeline Orchestration Design

## Problem

The task extraction pipeline reliably captures sparks (Phase 0) via deterministic tooling, but Phases A (refinement) and B (backtracing) fail inconsistently because the tasks agent's LLM reasoning drifts between tool calls. The agent calls `backtrace_task` but doesn't follow through with `write_packet_info`, or skips Phase A entirely. The root cause is conversational context contamination — prior chat history, spark notifications, and summarization requests compete for the agent's attention between tool calls.

Additionally, tasks appear in the sidebar immediately after Phase 0 with raw, unrefined names (e.g., "Review: Status" instead of "Reply to Amy: confirm Thu 3:30pm Earth science status check-in"), before enrichment has a chance to improve them.

## Design Principles

1. **Fix the environment, not the tools.** The agent produces excellent synthesis when given a clean, focused instruction. The quality of PACKET INFO output (SciENcv mismatch warnings, nuanced knowns/unknowns, agent notes) should be preserved, not mechanized away.

2. **One message, one job.** Each enrichment task gets a single focused message in an isolated conversation. The agent makes exactly three tool calls: fetch, refine+backtrace, write.

3. **Tasks appear in sidebar only when cooked.** No half-baked entries. Sidebar visibility moves from Phase 0 to the end of Phase A.

4. **Origin gates depth.** User-indicated tasks get full backtrace. Agent-identified tasks get refinement only — backtrace deferred until user confirms.

5. **Scheduler as orchestrator.** The scheduler service replaces the cron script, scanning for tasks needing enrichment and dispatching focused messages. Self-healing on failure (next cycle retries).

## Architecture

```
Spark notification
  → process_spark_queue (Phase 0, deterministic)
    → writes archival passage with enrichment:none
    → does NOT write to extracted_tasks block
    → task is invisible in sidebar

Scheduler scanner (every 30s)
  → scans archival for enrichment:none tags
  → for each: sends focused message to enrichment conversation

Enrichment conversation (clean, isolated)
  → Agent turn:
    Tool call 1: fetch_source_content(ref_id) → full source content
    Tool call 2: refine_task_description(ref_id, new_description)
                 → writes refined name to archival
                 → writes task line to extracted_tasks block (sidebar visible)
                 → if user-indicated: runs backtrace internally, returns materials
    Tool call 3: write_packet_info(ref_id, ...) [user-indicated only]
                 → agent synthesizes from backtrace materials
                 → writes PACKET INFO to archival
                 → sidebar Details accordion shows Backtrace section

User confirmation
  → MC notified for deeper synthesis if warranted
  → work packet assembler produces OmniFocus rich-text note
```

### Agent-identified tasks (lighter path)

```
Same pipeline through tool call 2, but:
  → refine_task_description detects origin:agent-identified
  → skips internal backtrace, returns refinement only
  → no tool call 3
  → task appears in sidebar with "Suggested" badge, no PACKET INFO
  → if user confirms: MC does deep backtrace in its own conversation
```

## Component Changes

### A. `process_spark_queue` (modify)

Remove the `extracted_tasks` block write (currently lines ~242-290). The tool continues to write the archival passage with full metadata, source text, fetch hint, and enrichment tags. The only change is deferring sidebar visibility.

The `enrichment` section in the archival passage is written with `Status: none`.

### B. `refine_task_description` (extend)

Current behavior: updates the task name in the archival passage and sets enrichment to `phase-a-complete`.

New behavior additions:
1. After writing the refined name, write the task line to the `extracted_tasks` block. This is where sidebar visibility now lives. Format: `[extracted_time: ...; ref_id: ...; origin: ...; est: ...] Refined task description`
2. Check the passage's origin tag:
   - If `user-indicated`: internally call `backtrace_task(ref_id)` and include the structured materials (anchors, archival hits, artifact candidates, intent candidates, hop candidates, related tasks, mismatch warnings, node coverage) in the tool's return value.
   - If `agent-identified`: skip backtrace. Return only the refinement confirmation.

The return value shape for user-indicated tasks becomes:
```
{
  "status": "ok",
  "ref_id": "...",
  "refined_description": "...",
  "backtrace": {  // present only for user-indicated
    "source_content": "...",
    "anchors": {...},
    "direct_action": {...},
    "artifact_candidates": [...],
    "intent_candidates": [...],
    "related_tasks": [...],
    "hop_candidates": [...],
    "mismatch_warnings": [...],
    "node_coverage": {...},
    ...
  }
}
```

### C. `write_packet_info` (no change)

Stays as-is. Agent calls with its synthesis. Writes PACKET INFO section, updates enrichment tag to `packet-info`.

### D. `fetch_source_content` (no change)

Deterministic fetch. Returns full content from email/Slack/meeting/docs.

### E. Scheduler enrichment scanner job (new)

A new recurring job registered in the scheduler service.

**Configuration:**
- Interval: 30 seconds
- Action type: `agent_message` with conversation routing
- Target: tasks agent, enrichment-pipeline conversation

**Scanner logic:**
1. Query archival for passages tagged `enrichment:none` via tag-based query. Tags are structured metadata, unambiguous, and future-proof for alternative storage backends (e.g., raw file grep). All passages already carry enrichment tags (`enrichment:none`, `enrichment:phase-a-complete`, `enrichment:packet-info`).
2. For each passage found, extract the ref_id.
3. Send a focused message to the enrichment conversation:

```
Enrich task ref_id {X}.
Step 1: Call fetch_source_content(ref_id="{X}") to get the full source content.
Step 2: Read the content and formulate a clear, specific task name. Then call refine_task_description(ref_id="{X}", new_description="your refined name").
Step 3: If backtrace materials are returned in the response, read them and call write_packet_info(ref_id="{X}", ...) with your synthesis of the three-node model, context brief, resources, and knowns/unknowns.
If no backtrace materials are returned (agent-identified task), you are done after Step 2.
```

4. Process one task per scanner cycle to avoid overwhelming the agent. If multiple tasks are pending, process the oldest first; remaining tasks are picked up in subsequent cycles.

**Implementation:** This can be a scheduler job with action_type `http` that calls a new lightweight endpoint on the pa-web-ui or a small standalone service. The endpoint handles the archival query and message dispatch. Alternatively, it can be a `script` action running a Python script that does the query and dispatch.

### F. Dedicated enrichment conversation (one-time setup)

Create via Letta API:
```
POST /v1/conversations
{
  "agent_id": "{TASKS_AGENT_ID}",
  "label": "enrichment-pipeline"
}
```

The conversation ID is stored as a configuration value (environment variable or scheduler job metadata) for the scanner to reference.

### G. Retire spark-queue-drain cron

The existing cron job at `/Users/dorseyhomeserver/bin/spark-queue-drain.sh` (runs every 2 minutes) is replaced by the scheduler scanner job. The scanner can optionally also check the spark queue and nudge `process_spark_queue` if non-empty, folding both concerns into one job.

Remove from crontab:
```
*/2 * * * * /Users/dorseyhomeserver/bin/spark-queue-drain.sh >> /tmp/spark-drain.log 2>&1
```

## Error Handling

| Failure | Impact | Recovery |
|---------|--------|----------|
| Agent busy (400) on enrichment message | Task stays at `enrichment:none` | Scanner retries next cycle (30s). Self-healing. |
| `fetch_source_content` fails | Agent can't refine | Tool returns error. Agent responds without enrichment. Scanner sees `enrichment:none` next cycle, retries. |
| `refine_task_description` fails | Task not in sidebar, no refined name | Stays at `enrichment:none`. Scanner retries. |
| `write_packet_info` fails/skipped | Task in sidebar (refined name) but no PACKET INFO | Functional — user can review and confirm. Secondary scanner check could look for `phase-a-complete` + `user-indicated` without `enrichment:packet-info` and retry. |
| Enrichment conversation grows stale | Potential drift over months | Monthly reset: delete and recreate conversation. Low priority — repetitive pattern reinforces rather than drifts. |
| Scanner misses a task | Task stuck at `enrichment:none` | Interval polling is self-healing. If the archival query has issues, tasks accumulate and are processed on fix. |

## Sidebar Visibility Timeline

| Stage | Sidebar visible? | What user sees |
|-------|-----------------|----------------|
| Phase 0 complete (`enrichment:none`) | No | — |
| Phase A complete (`phase-a-complete`) | Yes | Refined task name, source details. For user-indicated: PACKET INFO appears seconds later after tool call 3. |
| Phase B complete (`packet-info`) | Yes | Full Backtrace section in Details accordion: three-node model, resources, context brief, knowns/unknowns, agent notes. |

## Confirmation Flow (unchanged)

When user confirms a task in the sidebar:
1. Task is transitioned to `confirmed` status.
2. MC is notified for optional deeper synthesis (may call `backtrace_task` → `write_packet_info` with fuller analysis in MC's own conversation).
3. Work packet assembler in `app.py` reads the final PACKET INFO and produces rich-text OmniFocus note with clickable resource links.

## What This Replaces

| Current | New |
|---------|-----|
| Cron script (`spark-queue-drain.sh`) every 2 min | Scheduler job every 30s |
| Phase A/B chaining via persona instructions in noisy conversation | Single-purpose messages in dedicated enrichment conversation |
| Sidebar visibility at Phase 0 (raw names) | Sidebar visibility at Phase A completion (refined names) |
| Agent expected to self-chain 4+ tool calls | Agent chains 3 tool calls in clean context (2 for agent-identified) |

## Future Considerations

- **MC deeper synthesis at confirmation:** Already designed. MC uses individual `backtrace_task` → `write_packet_info` tools in its own conversation for richer analysis when warranted.
- **`stage_resource` tool:** Future addition for MC to download PDFs/attachments to disk during work packet assembly. Not needed for this orchestration change.
- **Passive scan / agent-discovery sources:** New spark sources (e.g., @-mention monitoring) produce sparks with `origin: agent-identified`. They flow through the same pipeline with lighter enrichment. No architectural change needed.
- **Conversation rotation:** If the enrichment conversation accumulates too much history, implement periodic reset. Monitor for drift before building.
