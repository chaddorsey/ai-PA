# PBI-15: Repair OmniFocus Project Metadata Exposure

## Overview
PBI 15 standardizes OmniFocus project metadata surfaced through the simplified MCP interface so downstream automations receive accurate timestamps, folder context, and detail-level specific payloads.

## Problem Statement
Current project-focused tools (`projectOperations`, `listProjects`) omit creation/modification timestamps, lack folder context, and ignore detail-level options. Consumers cannot rely on these tools for accurate reporting or routing.

## User Stories
- As a productivity specialist, I need projectOperations list results to include accurate project timestamps so I can audit recency.
- As an automation developer, I need detail level flags to control payload weight so that lightweight integrations avoid unnecessary data.
- As a workspace curator, I need project listings grouped by folder so I can confirm organisational hygiene quickly.
- As a review coordinator, I need both projectOperations and listProjects to filter by completion state so I can focus on active or completed initiatives on demand.

## Technical Approach
- Extend the OmniFocus plugin serializer to emit rich project metadata (timestamps, status, folder hierarchy, task references).
- Allow `projectOperations` and quick tools to forward detail-level requests and prune payloads consistently.
- Populate folder metadata and optional task summaries so grouping and name hydration work without per-project round trips.
- Introduce shared completion-state filters used by both projectOperations and quick tools.
- Update tests and documentation to cover new fields and behaviour.

## UX/UI Considerations
- CLI and MCP responses must remain readable at minimal detail levels.
- Ensure field naming stays consistent with existing task schemas (e.g., `added`, `modified`).
- Provide deterministic ordering when grouping by folder.

## Acceptance Criteria
- projectOperations list returns non-null `added` and `modified` for active projects when data exists.
- projectOperations detail levels map to distinct payload sizes: minimal suppresses folder/task info, standard strips notes/attachments, full returns complete project snapshots.
- listProjects emits valid `folderId`/`folderName` values and groups projects correctly when `listByFolder` is true.
- Both projectOperations and listProjects support filtering by completion status (`active`, `completed`, `all`) while maintaining consistent counts.
- Documentation and smoke tests demonstrate the updated fields and grouping behaviour.

## Dependencies
- Requires access to OmniFocus JXA plugin to extend serializers.
- Depends on existing timestamp utilities (`serializeTimestamped`).
- Must coordinate with any consumers caching project payloads.

## Open Questions
- Do we need to surface folder path arrays in minimal/standard detail levels?

## Related Tasks
- [Tasks for PBI 15](./tasks.md)
