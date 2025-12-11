# Tasks for PBI 24: Daily Briefing Tool

This document lists all tasks associated with PBI 24.

**Parent PBI**: [PBI 24: Daily Briefing Tool](./prd.md)

## Task Summary

| Task ID | Name | Status | Description |
| :------ | :----------------------------------------------- | :------- | :----------------------------------------------- |
| 24-1 | [Define daily briefing tool interface & schemas](./24-1.md) | Done | Specify the Letta tool `generate_daily_briefing` with typed args/docstring or Pydantic models. Define input/output schemas. |
| 24-2 | [Set up MCP calendar client integration](./24-2.md) | Done | Reuse or extend MCPCalendarClient from scheduling orchestrator for calendar event retrieval. Configure MCP server connection. |
| 24-3 | [Implement calendar event retrieval](./24-3.md) | Done | Implement logic to retrieve events from cdorsey@concord.org for 3-day window (today-1 to today+1) via MCP Core_Event_Data. |
| 24-4 | [Implement event filtering and processing](./24-4.md) | Done | Filter events according to gold-standard rules: exclude "Email & Tasks" and "Hold" unless overlapped, include all Chad's events, handle overlaps. |
| 24-5 | [Implement available time calculation](./24-5.md) | Proposed | Calculate available time blocks from current Eastern time to 5:00 PM. Merge adjacent blocks, subtract elapsed time, include gaps. |
| 24-6 | [Implement Markdown formatting](./24-6.md) | Proposed | Generate Markdown-formatted briefing with proper header, schedule section, and available time section following gold-standard format. |
| 24-7 | [Implement timezone handling](./24-7.md) | Proposed | Handle Eastern timezone with DST adjustments. Convert all times to Eastern, format correctly, ensure current time calculation accounts for DST. |
| 24-8 | [Implement memory update mechanism](./24-8.md) | Proposed | Design and implement mechanism for updating Letta memory block `current_daily_schedule_and_available_time` with formatted briefing. |
| 24-9 | [Assemble generate_daily_briefing tool](./24-9.md) | Proposed | Combine tasks 24-2 through 24-8 into the single tool. Ensure error handling, logging, and proper response format. |
| 24-10 | [Register tool with Letta](./24-10.md) | Proposed | Register the tool in Letta, verify JSON schema, display names/docs, and run manual test call. |
| 24-11 | [E2E CoS Test](./24-11.md) | Proposed | End-to-end test verifying all Conditions of Satisfaction: calendar retrieval, filtering, time calculation, formatting, timezone handling, and memory update. |

