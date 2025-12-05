# Tasks for PBI 22: Rescheduling Support for Scheduling Orchestrator

This document lists all tasks associated with PBI 22.

**Parent PBI**: [PBI 22: Rescheduling Support for Scheduling Orchestrator](./prd.md)

## Task Summary

| Task ID | Name | Status | Description |
| :------ | :----------------------------------------------- | :------- | :----------------------------------------------- |
| 22-1 | [Extend tool signature for event ID parameters](./22-1.md) | InProgress | Add optional `event_id` and `event_owner_id` parameters to `orchestrate_scheduling` function signature. Update docstring and type hints. |
| 22-2 | [Implement event fetching by ID via MCP](./22-2.md) | Review | Add function to fetch specific event by ID using MCP Core_Event_Data. Handle errors for missing/inaccessible events. |
| 22-3 | [Extend DSPy extraction for rescheduling intent](./22-3.md) | Review | Update `ExtractSchedulingRequest` signature and extraction logic to detect rescheduling intent and extract event identifiers (participant names, dates, times, titles) from natural language. |
| 22-4 | [Implement event identification from natural language](./22-4.md) | Review | Build function to match extracted event identifiers against fetched calendar events. Handle fuzzy matching for participant names, date/time ranges, and titles. For recurring events, identify only the specific instance mentioned in the request. |
| 22-5 | [Extract event details for scheduling problem](./22-5.md) | Review | Create function to extract participants, duration, title, location, and other metadata from identified event. Validate event is internal-only if moving is required. |
| 22-6 | [Merge event details with utterance constraints](./22-6.md) | Review | Combine extracted event details with additional constraints/preferences from utterance to construct complete SchedulingProblem. Handle conflicts and overrides. Set default search timeframe to next 28 days (current and future) if not specified. Ensure only one meeting per request is supported. |
| 22-7 | [Include original event in normalized data](./22-7.md) | Proposed | Ensure original event is included in normalized calendar data with appropriate flags (movable, internal-only). Update normalizer to handle rescheduling context. |
| 22-8 | [Update proposal output with original event reference](./22-8.md) | Proposed | Add `original_event_id` and `original_event_details` fields to Proposal schema. Populate these fields in proposals for rescheduling operations. |
| 22-9 | [Update user display for rescheduling context](./22-9.md) | Proposed | Modify formatting functions to indicate rescheduling context in user-facing output. Show original meeting details and highlight that this is a rescheduling operation. Use the same or very similar format to the current user report for consistency. |
| 22-10 | [Update agent data with original event metadata](./22-10.md) | Proposed | Include original event reference in agent_data.event_registry and proposal metadata. Enable agent to perform follow-up actions on original event. |
| 22-11 | [Integration testing for rescheduling scenarios](./22-11.md) | Proposed | Create test scenarios for: (a) natural language rescheduling with event identification, (b) explicit event ID rescheduling, (c) rescheduling with original event movement, (d) recurring event instance rescheduling (single instance only), (e) error cases (missing event, external event, inaccessible event, multiple meeting request rejection). |
| 22-12 | [Documentation and examples](./22-12.md) | Proposed | Update tool documentation with rescheduling examples. Document new parameters, natural language patterns, and agent usage patterns. Add examples to technical documentation. |

