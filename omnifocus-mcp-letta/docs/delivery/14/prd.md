# PBI-14: Quick-Access Simplified Tools

## Overview
Introduce high-frequency OmniFocus MCP tools that expose core operations directly (complete task, list incomplete tasks, list projects, move task between projects) while coexisting with consolidated handlers. These tools target conversational agents and quick-command workflows that benefit from single-purpose entry points.

## Problem Statement
Although the simplified tool surface offers comprehensive consolidated operations, some clients and automations prefer dedicated commands for the most common flows. Allowing these shortcuts improves ergonomics and reduces prompt size without replacing the richer consolidated tools.

## User Stories
- As a quick command user, I want a `markTaskCompleted` tool so I can confirm completion of one task without constructing a multi-field payload.
- As an agent designer, I want a `listUncompletedTasks` tool that returns actionable metadata so I can quickly display pending work.
- As a project reviewer, I want a `listProjects` tool that can optionally group by folder or expand task names so I can scan project structures fast.
- As a workflow automator, I want a `moveTaskToProject` tool that validates both task and project IDs so I can remap work items safely.

## Technical Approach
- Extend simplified server registry to include four new tools driven by existing bridge utilities.
- Share serialization helpers with consolidated operations to ensure consistent metadata fields (task/project IDs, names, timestamps, flags).
- Reuse OmniFocus API adapters to access availability status, flagged state, inbox membership, and folder context.
- Guard operations with error handling that returns JSON-RPC errors when IDs are missing or invalid.
- Provide optional parameters for listing tools (project scope, flagged-only, availability, folder filters, grouping) while keeping defaults straightforward.

### Tool Specifications
1. `markTaskCompleted`
   - **Input**: `{ taskId: string }`
   - **Behavior**: Validate task existence, set completed state via bridge, return `{ taskId, completionStatus: 'completed' }`.
   - **Errors**: Task not found, task already completed (optional warning), underlying bridge failure.

2. `listUncompletedTasks`
   - **Input**: `{ projectId?: string, onlyFlagged?: boolean, onlyAvailable?: boolean }`
   - **Logic**: Query tasks excluding completed/dropped, apply project filter, flagged filter, and OmniFocus "available" predicate (not blocked/deferred future, not completed, etc.).
   - **Output items**: `{ taskId, name, projectId, inInbox, flagged, created, due, deferred }`.
   - **Notes**: Document availability detection (use `task.available` accessor or derive from status/ defer/due fields).

3. `listProjects`
   - **Input**: `{ folderId?: string, listProjectNames?: boolean, listByFolder?: boolean }`
   - **Logic**: Fetch active projects; if `folderId` present, filter; if `listProjectNames`, expand task details; if `listByFolder`, return array grouped by folder `{ folderId, folderName, projects: [...] }`.
   - **Output per project**: `{ projectId, name, description?, taskIds, tasks? }` depending on flags.
   - **Notes**: Ensure combination of `folderId` + `listByFolder` behaves (single folder grouping vs nested structure).

4. `moveTaskToProject`
   - **Input**: `{ taskId: string, projectId: string }`
   - **Behavior**: Validate both IDs, use bridge move helper, return `{ taskId, projectId, status: 'moved' }`.
   - **Errors**: Missing IDs, invalid project, invalid task, move failure (e.g., due to sequential constraints).

## UX/UI Considerations
- Reflect success vs error clearly with JSON fields so conversational agents can confirm outcomes.
- Keep tool descriptions concise and distinct from consolidated operations to avoid confusion.
- Maintain parity with consolidated schemas for field naming (e.g., `taskId`, `projectId`, `created`, `due`, `deferred`).

## Acceptance Criteria
1. Simplified server exposes four new tools with JSON schemas and descriptions documented.
2. Tools reuse bridge logic and return consistent metadata; no duplicated serialization code.
3. Errors for missing/invalid IDs produce clear JSON-RPC failures with actionable messages.
4. Documentation and smoke scripts updated with examples for each new tool.

## Dependencies
- Existing bridge functions for task completion, project listing, task movement, and task queries.
- Availability helper functions (from consolidated task operations) to assess OmniFocus status.

## Open Questions
- Should `listUncompletedTasks` expose additional fields (e.g., tag IDs) for future filtering? (Default: keep minimal fields.)
- Do we gate `moveTaskToProject` behind transaction support for rollback? (Initial implementation relies on existing move helper; evaluate need for transaction later.)

## Related Tasks
- [Tasks for PBI 14](./tasks.md)

[View in Backlog](../backlog.md#user-content-14)
