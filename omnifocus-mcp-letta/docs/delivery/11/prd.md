# PBI-11: Planned Date Exposure

## Overview
Expose newly introduced planned date fields from OmniFocus tasks (`plannedDate`, `effectivePlannedDate`) through the plugin and MCP server so agents can reason about planned scheduling.

## Problem Statement
OmniFocus 4.7.1 adds `plannedDate` metadata to tasks, but the current MCP integration neither captures nor exposes these values. Agents lack visibility into when tasks are planned, limiting proactive scheduling and planning features.

## User Stories
- As an OmniFocus planner, I want MCP responses to contain planned dates so I can coordinate task execution windows.
- As an automation developer, I need schemas and typings that reflect planned date fields so downstream clients remain type-safe.

## Technical Approach
- Update plugin serializers to include `plannedDate` and `effectivePlannedDate` using Omni Automation APIs.
- Extend TypeScript interfaces, Zod schemas, and bridge logic to surface planned date fields.
- Provide documentation describing planned date semantics and format.

## UX/UI Considerations
No UI changes; ensure API consumers receive ISO-8601 strings for planned dates and understand nullable semantics.

## Acceptance Criteria
1. Tasks returned by MCP list/get commands include `plannedDate` and `effectivePlannedDate` when available.
2. TypeScript typings and generated schemas reflect optional planned date fields.
3. Documentation and release notes describe planned date support and examples.
4. Smoke tests confirm planned date propagation for dated tasks.

## Dependencies
- Requires OmniFocus 4.7.1+ where `plannedDate` is available (`effectivePlannedDate` is read-only).
- Coordination with timestamp exposure (PBI 10) for consistent serialization helpers.

## Open Questions
- Should planned dates be included for projects and folders if available in future versions?
- How should agents prioritize planned versus due dates when both are present?

## Related Tasks
_To be defined in `tasks.md`._

[View in Backlog](../backlog.md#user-content-11)
