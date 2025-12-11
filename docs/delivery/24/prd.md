# PBI-24: Daily Briefing Tool

## Overview
Deliver a custom Letta tool, `generate_daily_briefing`, that retrieves calendar events from cdorsey@concord.org via MCP, formats them according to gold-standard rules, calculates available time from the current moment to 5:00 PM Eastern, and generates a Markdown-formatted daily briefing report. The tool updates a memory block with the formatted briefing and handles Eastern time with daylight savings adjustments correctly.

[View in Backlog](../backlog.md#user-content-24)

## Problem Statement
Users need an up-to-date view of their daily schedule with accurate available time calculations at any point during the day. Currently, there is no automated way to generate a formatted daily briefing that:
- Retrieves calendar data directly from the calendar system
- Filters events according to specific business rules (e.g., excluding "Email & Tasks" and "Hold" events unless overlapped)
- Calculates available time blocks from the current time forward
- Formats the output in a consistent, readable Markdown format
- Updates persistent memory for reference

## User Stories
- As a user, I want to ask Letta to "update the daily briefing" and receive a formatted schedule report with available time calculations, so I can quickly see what's on my calendar and when I have free time.
- As a Letta agent, I want a single tool that retrieves calendar data, applies filtering rules, calculates available time, and formats the output, so I can provide accurate daily briefings without complex multi-step workflows.
- As a user, I want the briefing to show the exact time it was generated and calculate available time from that moment forward, so the information is always current and actionable.
- As a user, I want the briefing to properly handle Eastern time with daylight savings adjustments, so all times are displayed correctly regardless of when the tool is called.

## Technical Approach

### Architecture
- **Letta Integration**: One tool with typed signature/docstring (or Pydantic schema) so Letta generates a tool schema automatically. Tool code lives in `letta/daily_briefing/` directory.
- **MCP Calendar Integration**: Reuse the MCP client architecture from `orchestrate_scheduling` tool to retrieve calendar events via `Core_Event_Data` from the n8n MCP server.
- **Event Processing**: Filter and categorize events according to gold-standard rules:
  - Include ALL events where Chad is a participant
  - Exclude "Email & Tasks" (9:00-11:00 AM) and "Hold" events from meeting list unless overlapped by real meetings
  - Treat "Chad out" as busy time
  - Handle overlapping events correctly
- **Time Calculations**: 
  - Get current time in Eastern timezone (with DST handling)
  - Calculate available time from current time to 5:00 PM Eastern
  - Merge adjacent available blocks
  - Subtract elapsed minutes from partially elapsed blocks
  - Include gap from last busy item to 5:00 PM if any
- **Formatting**: Generate Markdown-formatted output with:
  - Header with timestamp (Eastern time, properly formatted day name)
  - Schedule section with chronological event listing
  - Available time section with total and individual blocks
  - Proper Markdown formatting (bold, italic, bullets)
- **Memory Management**: Update Letta memory block `current_daily_schedule_and_available_time` with the formatted briefing

### Dependencies
- MCP Calendar Client: Reuse `MCPCalendarClient` from `letta/scheduling_orchestrator/mcp_client.py` or create a shared module
- Timezone Handling: Use `pytz` or `zoneinfo` for Eastern timezone with DST support
- Letta SDK: For memory block updates (if available via SDK) or via tool response that agent can use to update memory

## UX Flow (Agent)

1. User requests: "Update the daily briefing" or "Generate today's schedule"
2. Agent calls `generate_daily_briefing()` tool
3. Tool:
   - Gets current Eastern time
   - Retrieves calendar events for cdorsey@concord.org (dayBefore = today-1, dayAfter = today+1)
   - Filters and processes events according to rules
   - Calculates available time blocks
   - Formats Markdown briefing
   - Returns formatted briefing and memory update instruction
4. Agent:
   - Displays formatted briefing to user
   - Updates memory block `current_daily_schedule_and_available_time` with briefing content
   - Confirms memory update

## Functional Requirements

### FR1: Calendar Event Retrieval
- Tool retrieves calendar events from cdorsey@concord.org via MCP `Core_Event_Data`
- Date range: dayBefore = today-1, dayAfter = today+1 (3-day window centered on today)
- Includes ALL events where Chad is a participant
- Handles MCP errors gracefully with clear error messages

### FR2: Event Filtering and Processing
- Excludes "Email & Tasks" (9:00-11:00 AM) from meeting list unless overlapped by real meeting
- Excludes "Hold" events from meeting list unless overlapped by real meeting
- Treats "Chad out" events as busy time (included in schedule)
- Lists overlapping events separately (no deduplication)
- Sorts events chronologically by start time

### FR3: Available Time Calculation
- Gets current time in Eastern timezone (with DST adjustment)
- Calculates available time from current time to 5:00 PM Eastern
- Merges adjacent available blocks
- Subtracts elapsed minutes from first partially elapsed block
- Includes gap from last busy item to 5:00 PM if any
- Only counts time up to 5:00 PM (does not include evening time)

### FR4: Markdown Formatting
- Header: `# Today's Schedule (updated [Day] [Month] [DD] at [H:MM AM/PM])`
  - Day name abbreviated (Mon., Tue., Wed., etc.)
  - Date and time in Eastern timezone
  - Properly formatted with daylight savings adjustment
- Schedule section:
  - Bold section title: `**Today's Schedule**`
  - Bullet format: `• **start–end** — **Bold meeting title** (*attendee names italicized in parentheses*)`
  - Solo blocks italicized: `• **Email & Tasks** (*Chad Dorsey*) — *9:00–11:00 AM*`
  - Events listed in chronological order
- Available Time section:
  - Header: `### Available Time Remaining — **<total>**`
  - Total formatted as "Xh, Y min" (e.g., "3h, 15 min")
  - Individual blocks: `- start – end (X min left)` for first block, `- start – end (X min)` for subsequent blocks
  - All parenthetical times italicized
  - Blocks listed on separate lines

### FR5: Memory Update
- Tool returns formatted briefing in response
- Tool includes instruction or structured data for agent to update memory block `current_daily_schedule_and_available_time`
- Memory content matches briefing format exactly
- Agent confirms memory update to user

### FR6: Timezone Handling
- All times displayed in Eastern timezone
- Properly handles daylight savings time transitions
- Current time calculation accounts for DST
- Event times converted to Eastern if needed

## Goals & Non-Goals

### Goals
- Single tool interface for daily briefing generation
- Accurate available time calculation from current moment
- Consistent Markdown formatting following gold-standard rules
- Proper Eastern timezone handling with DST
- Memory block update capability
- Reuse of existing MCP calendar infrastructure

### Non-Goals
- Multi-day briefings (focus on today only, though retrieves 3-day window for context)
- Historical briefings (always generates current state)
- Customizable formatting rules (follows fixed gold-standard format)
- Integration with other calendar systems (cdorsey@concord.org only)
- Real-time calendar synchronization (uses snapshot from MCP call)

## Acceptance Criteria

1. **Calendar Retrieval**: Tool successfully retrieves events from cdorsey@concord.org for 3-day window via MCP
2. **Event Filtering**: "Email & Tasks" and "Hold" events excluded unless overlapped by real meetings
3. **Time Calculation**: Available time correctly calculated from current Eastern time to 5:00 PM
4. **Formatting**: Markdown output matches gold-standard format exactly
5. **Timezone**: All times displayed correctly in Eastern timezone with DST handling
6. **Memory Update**: Memory block updated with formatted briefing content
7. **Error Handling**: Graceful handling of MCP errors, missing events, and edge cases
8. **Tool Registration**: Tool registered with Letta and schema verified
9. **Manual Testing**: Tool can be called manually and produces correct output

## Dependencies
- Letta agent with MCP calendar access (assumed to exist via n8n MCP server)
- MCP Calendar Client infrastructure (can reuse from scheduling orchestrator)
- `pytz` or `zoneinfo` for timezone handling
- Letta SDK for tool registration and memory management

## Open Questions
- Should the tool support custom date ranges, or always use today ±1 day?
- Should the tool cache calendar data, or always fetch fresh data?
- How should the tool handle events that span multiple days?
- Should the tool support multiple calendar sources in the future?
- What is the preferred method for memory block updates (SDK call, tool response instruction, etc.)?

## Related Tasks
- [Back to task list](./tasks.md)
- Tasks tracked in `docs/delivery/24/tasks.md` with detailed files

