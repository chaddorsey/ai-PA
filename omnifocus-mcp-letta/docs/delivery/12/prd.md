# PBI-12: Simplified Tool Surface with Freshness Awareness

## Overview
Deliver a streamlined OmniFocus MCP server that exposes the consolidated (simplify-tools) tool surface while retaining new metadata (timestamps, planned dates) and freshness-aware sorting options.

## Problem Statement
The current MCP server exposes a large number of granular tools. We now have a simplified tool design that reduces surface area, but it lacks the recently added timestamp/planned date functionality. Agents also frequently need to identify stale tasks quickly. We need to merge the simplified experience with the enhanced data while keeping the full tool server available for future use.

## User Stories
- As a Letta integrator, I want a compact tool list that still exposes freshness and planned-date information so that workflows remain efficient.
- As a power user, I want to optionally access the full tool surface, even if it is not exposed by default.
- As an automation developer, I want to request task/project lists sorted by freshness so I can surface stale items quickly.

## Technical Approach
- Analyse existing simplified server implementation (reference folder) to understand tool categories, helper functions, and schema structure.
- Extend consolidated tool schemas to incorporate detail levels, timestamp/planned-date fields, and optional freshness sorting (descending by modified/added as relevant).
- Implement a new simplified server entry point that calls shared bridge utilities; add configuration to keep the full server available but disabled by default.
- Update documentation, smoke tests, and release notes to cover new options.

### Schema Design Outline
- **Common additions**: every list/get response should expose `added`, `modified`, `plannedDate`, `effectivePlannedDate` (nullable ISO strings). All list-capable tools accept `detailLevel` (`minimal`/`standard`/`full`) and optional `sortOrder` (`default`, `freshness`).
- **taskOperations.list**: accepts existing filters plus `sortOrder`; default returns OmniFocus order, `freshness` sorts by descending `modified`/`added` fallback.
- **taskQuery**: inherits same response metadata; if `sortOrder` not provided, search result relevance preserved; `freshness` re-orders after query.
- **projectOperations.list**, **tagOperations.list**, **perspectiveOperations.list**: allow `sortOrder` where data volume manageable; default remains alphabetical/OmniFocus order.
- **inbox operations / validation / transaction / review**: no freshness parameter (not meaningful); still return new metadata when applicable.
- **Detail levels**: `minimal` includes identifiers, names, status/flag; `standard` adds key dates (defer/due/planned/timestamps); `full` includes notes, attachments, extended fields.
- **Shared types**: introduce `DetailLevel` and `SortOrder` enums, plus helper to apply default sorting.

## UX/UI Considerations
- Keep tool names/descriptions aligned with simplified design for clarity.
- Provide clear defaults (e.g., standard detail level, default sort by OmniFocus order) with optional parameters for freshness.
- Document how to enable the full tool server for specialized workflows, ensuring the default experience remains simple.

## Acceptance Criteria
1. Simplified tool server exposes the consolidated tool list with updated schemas, metadata, and freshness sorting options where applicable.
2. Freshness sorting (reverse chronological by modified/added) is available for task/project/tag list operations without significant performance degradation.
3. Original full tool server is preserved and runnable (e.g., via alternate npm script/flag) but not exposed by default.
4. Documentation and smoke tests updated to reflect simplified vs full modes and new parameters.

## Dependencies
- Existing timestamp/planned date serialization logic (PBI 10/11).
- Simplify-tools reference server implementation.

## Open Questions
- Should freshness sorting be available for all entities (e.g., perspectives) or only those where it provides clear value? (Default plan: tasks, projects, tags.)
- How should agents toggle between simplified and full tool sets (environment variable, CLI flag, config file)?

## Related Tasks
- [Tasks for PBI 12](./tasks.md)

## Initial Analysis Notes
- Simplified server (`server-mcp-simplified-8124.ts`) exposes 14 high-level tools covering task operations, queries, hierarchy, project/folder/tag operations, inbox processing, perspectives, validation, transactions, review, automation suggestions, analytics, and system health.
- Many actions map directly to existing bridge functions; need to adapt handlers to call shared serializers.
- Freshness-based sorting most valuable for task/project/tag lists; likely not necessary for validation, transaction, or automation tools.
- Reference implementation uses `detailLevel` parameter—extend to include new freshness toggle while preserving defaults.


[View in Backlog](../backlog.md#user-content-12)

