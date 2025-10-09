# PBI-17: Surface Task Duration in Simplified OmniFocus Tools

## Overview
Expose OmniFocus task duration (estimated minutes) through the simplified MCP tool surface so LLMs can reason about effort and scheduling.

## Problem Statement
The current quick-access task summaries omit the OmniFocus `estimatedMinutes` property. Downstream automations and LLMs therefore lack visibility into task effort, limiting scheduling guidance and prioritisation.

## User Stories
- **As a productivity specialist**, I want quick task listings to include duration so I can assess workload at a glance.
- **As an LLM integrator**, I want duration exposed through MCP schemas so I can reason about effort when planning sequences of work.

## Technical Approach
- Update server-side summarizers (`toTaskSummary`, project task summaries) to include task duration sourced from `serializeTask` (`estimatedMinutes`).
- Ensure plugin serializers already emitting `duration` remain consistent (aligned with `estimatedMinutes`).
- Wire duration through relevant quick tools (`listUncompletedTasks`, `taskOperations.list`, project task summaries) and update TypeScript schemas as needed.
- Document the new field and provide sample responses for verification.

## UX/UI Considerations
- Duration will appear as a numeric field (`durationMinutes`) in JSON summaries alongside existing metadata.
- No UI changes required beyond API payloads and docs.

## Acceptance Criteria
1. `listUncompletedTasks` responses include `durationMinutes` (null when unavailable).
2. `taskOperations.list` (standard/full detail) surfaces `durationMinutes` in task objects.
3. Project task summaries returned via `listProjects` with task names include duration when available.
4. Documentation updated with examples showing the new field and its meaning.

## Dependencies
- Existing OmniFocus plugin already serialises `estimatedMinutes` into task objects.
- No additional service dependencies.

## Open Questions
- Should duration be exposed in minimal detail mode? (Proposal: yes, as it is small/low risk.)
- Do we need to map the value into hours for readability? (Proposal: keep raw minutes.)

## Related Tasks
- [Back to backlog](../backlog.md#user-content-17)

## Implementation Summary
- 2025-10-09 07:32:07: Duration surfaced across task quick tools; documentation and examples updated.
