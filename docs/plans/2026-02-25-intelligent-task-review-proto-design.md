# Intelligent Task Review — Proto-Design

**Date:** 2026-02-25
**Status:** Proto-design (directional, not implementation-ready)
**Depends on:** [Task Extraction Pipeline](2026-02-25-task-extraction-pipeline-design.md) (origin field, extraction infrastructure)
**Related:** [WIP System Updates](2026-02-23-wip-system-updates.md)

---

## Motivation

The current task pipeline is mechanical: markers are extracted, archived, and queued for OmniFocus confirmation. No step exists where an agent brings contextual intelligence to bear — cross-referencing linked documents, spotting duplicates across sources, discovering deadlines from transcript analysis, or recognizing that a task is stale or already completed.

This proto-design outlines the architecture for an intelligent review layer that operates on extracted tasks *after* initial extraction, enriching them with cross-cutting context before they reach the user for OmniFocus confirmation.

## Design principles

1. **User intent is a first-class signal.** The `origin` field (`user-indicated` vs `agent-identified`) must be preserved and surfaced at every review point. As agents become better at identifying tasks independently, the user needs to know which tasks they explicitly marked and which the agent inferred. This distinction affects trust calibration and review priority.

2. **Extraction should flow readily.** Tasks should not be held back from the `extracted_tasks` pool for lack of enrichment. The extracted pool is the consideration set; OmniFocus confirmation is the human gate. Light extraction now, intelligent enrichment asynchronously.

3. **Agent consideration is a feature, not a side effect.** The architecture must create deliberate space for agent reasoning about tasks — not as a byproduct of a tool chain, but as an explicit step with its own triggers, context, and outputs. Steps that route around agent consideration attenuate our ability to tune task framing as agents improve.

4. **Cross-source awareness requires cross-agent visibility.** A meeting task may duplicate a Slack-queued task. A Google Doc comment may provide context for a meeting action item. The review step must span sources, which means spanning agents.

## Architecture sketch

### Task Review Agent

A dedicated agent (or the sleeptime companion of the tasks agent) that periodically reviews the `extracted_tasks` block with full cross-cutting context.

**Inputs:**
- `extracted_tasks` block (shared, all agents' sections visible)
- `extracted_tasks_archive` (archival passages with full source metadata)
- Access to meeting archival (Granola agent's archive)
- Access to Drive RAG (linked documents)
- Access to Slack archive (conversation context)

**Capabilities:**
- **Enrich:** Add context discovered after extraction — a linked Google Doc reveals the real scope, a transcript excerpt clarifies the deadline, a follow-up email changes the ask
- **Merge:** Two tasks from different sources are the same work. Combine them, preserving both source references. (`merge_extracted_tasks` tool already exists)
- **Reclassify:** Mark a task as stale, completed, or superseded with high confidence. Remove from active consideration set without deleting the archive record
- **Augment metadata:** Add due dates, project tags, priority based on cross-source analysis
- **Flag for user attention:** Surface tasks that need human judgment — ambiguous scope, conflicting information, unusually high stakes

**Trigger:** Periodic (scheduler cron) or event-driven (new extraction triggers review of related tasks).

### Shared block access

Current constraint: agents can only modify their own section of shared blocks. Options for cross-section operations:

1. **Privileged review agent:** A single agent authorized to modify any section. Requires a new Letta capability or a tool that bypasses section enforcement.
2. **Tool-mediated cross-section ops:** `merge_extracted_tasks` and `update_extracted_task` operate via direct API calls (not through agent memory), so they can modify any section. The review agent calls these tools rather than editing the block directly.
3. **Archive-first approach:** Instead of modifying the block, the review agent writes enrichment to the archival passage (which has no section restriction). The block entry stays minimal; the archive passage becomes the rich record. At confirmation time, the user sees the enriched archive, not just the block line.

**Recommendation:** Option 3 (archive-first) is the cleanest. The block is a summary view; the archive is the source of truth. Enrichment updates the archive passage. The `update_extracted_task` tool already supports this pattern.

### Origin-aware presentation

When the user reviews tasks for OmniFocus confirmation, the presentation should distinguish:

- **User-indicated tasks:** High confidence. User explicitly marked these. Show with minimal friction — "confirm" is the default action.
- **Agent-identified tasks:** Variable confidence. Agent inferred these from context. Show with more detail — source reasoning, confidence signal, option to dismiss without penalty.
- **Agent-enriched tasks:** Originally user-indicated, but the agent added context (deadline, project, related URLs). Show the enrichment clearly so the user can validate.

### Consideration at extraction vs. after extraction

| Aspect | At extraction | After extraction |
|--------|--------------|-----------------|
| **Context available** | Single meeting/source | All sources, cross-meeting |
| **Latency impact** | Adds to real-time processing chain | Asynchronous, no user-facing delay |
| **Compaction risk** | High (already a fragile chain) | None (separate agent session) |
| **Duplicate detection** | Only within current meeting | Across all sources and time |
| **Linked doc analysis** | Possible but adds 10-30s per doc | Can be thorough, no time pressure |

**Conclusion:** Light mechanical extraction at scan time. Deep intelligent review as a separate asynchronous process. The queue exists as the durable handoff between these two phases.

## Implementation phases

### Phase 0 (current work)
Close the extraction gap. `[c]` markers reach `extracted_tasks` automatically. `origin` field added. Queue cleanup works. No intelligence yet — pure plumbing.

### Phase 1: Post-extraction enrichment
Task Review Agent runs periodically. For each recently-extracted task:
- Fetch the archival passage
- Check for linked documents (fetch via Drive RAG if URLs present)
- Search for related tasks (semantic search on archive)
- Update the passage with any discovered context
- Flag duplicates or merge candidates

### Phase 2: Cross-source awareness
Review agent gains access to Slack archives, email context, and meeting transcripts beyond the originating meeting. Can spot patterns like "this was discussed in three meetings" or "the email thread resolved this."

### Phase 3: Agent-identified tasks
Agents begin identifying tasks from transcript analysis, email scanning, and document review. These enter the extracted_tasks pool with `origin: agent-identified`. The review agent applies higher scrutiny to agent-identified tasks. User review presentation adapts based on origin.

### Phase 4: Proactive task management
Review agent notices approaching deadlines, stalled tasks, or tasks that should be escalated. Sends notifications via the outbound notification system (item 6 in WIP). Begins to close the loop between task identification and task completion.

## Open questions

1. **Should the review agent be a new agent or the sleeptime companion of the tasks agent?** Sleeptime is natural (runs during off-hours, has review-oriented persona) but may not have the right tool set. A dedicated agent is cleaner but adds to the agent count.

2. **How should enrichment be surfaced at confirmation time?** Currently confirmation happens via a manual agent interaction. If the archive passage is the enriched record, the confirmation tool needs to present it clearly. May need a "task review" view that shows origin, enrichment history, and related tasks.

3. **What triggers review?** Pure periodic (every N hours) vs. event-driven (new extraction triggers review of related tasks) vs. hybrid. Event-driven is more responsive but harder to implement reliably.

4. **How do we handle the transition period?** The ~20K chars of stale queue entries represent tasks that were never extracted. Should they be bulk-extracted (with `origin: user-indicated, stale: true`) or simply cleared? The meetings are old enough that the tasks are likely already handled or irrelevant.
