# PBI-22: Rescheduling Support for Scheduling Orchestrator

## Overview
Extend the scheduling orchestrator tool to support rescheduling existing meetings. The tool will accept requests to find new time options for an existing meeting, either via natural language ("Find me some new time options for the check-in with Judi on Dec. 10th") or via explicit event ID in agent-generated tool calls. The tool will extract the meeting's current details (participants, duration, title) and find optimal alternative time slots while treating the original event as movable.

[View in Backlog](../backlog.md#user-content-22)

## Problem Statement
Users frequently need to reschedule existing meetings due to conflicts, preference changes, or schedule adjustments. Currently, the scheduling orchestrator only supports finding new meeting slots. Users must manually identify the meeting to reschedule and provide all details again. The agent cannot efficiently handle rescheduling requests that reference existing meetings by natural language description or event ID.

## User Stories
- As a user, I want to ask "Find me a new time for my meeting with Judi on Dec. 10th" and have the orchestrator automatically identify the meeting and propose alternative times.
- As a Letta agent, I want to call the orchestrator with an event ID to find rescheduling options, so I can handle rescheduling requests programmatically.
- As a user, I want the orchestrator to preserve the original meeting details (participants, duration, title, location) when finding new times, so I don't have to re-specify them.
- As a user, I want the orchestrator to treat the original meeting as movable when finding alternatives, so it can propose times that require moving the existing meeting.

## Technical Approach

### Input Extensions
1. **New Optional Parameter**: `event_id` - Explicit event ID for rescheduling (when provided by agent)
2. **New Optional Parameter**: `event_owner_id` - Owner/calendar ID for the event (required when event_id is provided)
3. **Natural Language Detection**: Extend DSPy extraction to detect rescheduling intent and extract event identifiers from utterances

### Event Identification
1. **From Event ID**: When `event_id` and `event_owner_id` are provided, fetch the event via MCP Core_Event_Data
2. **From Natural Language**: Use DSPy to extract:
   - Event identifiers (participant names, dates, times, titles)
   - Rescheduling intent keywords ("reschedule", "find new time", "move", "change time")
3. **Event Lookup**: Search fetched calendar events to match extracted identifiers
4. **Recurring Events**: For recurring meeting instances, only the specific instance mentioned in the request is considered (not the entire series)

### Scheduling Problem Construction
1. **Extract Event Details**: From identified event, extract:
   - Participants (from attendees_list or owner)
   - Duration (from start/end times)
   - Title (from summary)
   - Location (if available)
   - Current start/end times
2. **Merge with Utterance**: Combine event details with any additional constraints/preferences from the utterance
3. **Mark Original Event**: Include the original event in the calendar data with appropriate flags (movable, internal-only check)

### Output Extensions
1. **Original Event Reference**: Include original event ID and details in proposals
2. **Rescheduling Context**: Indicate in proposals that this is a rescheduling operation
3. **Move Original Event**: If the best proposal requires moving the original event, include it in `moved_events`

### Integration Points
- **MCP Core_Event_Data**: Fetch specific event by ID when provided
- **DSPy Extraction**: Extend `ExtractSchedulingRequest` to detect rescheduling intent and extract event identifiers
- **Event Normalization**: Ensure original event is included in normalized calendar data
- **Constraint Solver**: Treat original event as movable (if internal-only) when finding alternatives

## UX Flow (Agent)

### Scenario 1: Natural Language Rescheduling Request
1. User: "Find me some new time options for the check-in with Judi on Dec. 10th"
2. Agent calls `orchestrate_scheduling` with:
   - `utterance`: The user's request
   - `participant_ids`: [user_email, judi_email] (extracted or inferred)
   - `context_json`: {timeframe, participants, policy}
3. Tool detects rescheduling intent, identifies the event, extracts its details
4. Tool finds alternative time slots treating original event as movable
5. Agent presents proposals to user

### Scenario 2: Agent-Generated Rescheduling Request
1. Agent has identified an event ID from previous context
2. Agent calls `orchestrate_scheduling` with:
   - `utterance`: "Find new time options" (or similar)
   - `event_id`: "evt_abc123"
   - `event_owner_id`: "user@example.com"
   - `participant_ids`: [user_email, ...] (from event or context)
   - `context_json`: {timeframe, participants, policy}
3. Tool fetches event by ID, extracts details, finds alternatives
4. Agent presents proposals to user

## Functional Requirements

### FR1: Event ID Parameter Support
- Tool accepts optional `event_id` and `event_owner_id` parameters
- When provided, tool fetches the specific event via MCP Core_Event_Data
- Tool validates that the event exists and is accessible

### FR2: Natural Language Rescheduling Detection
- DSPy extraction detects rescheduling intent from utterances
- Extracts event identifiers: participant names, dates, times, titles
- Maps extracted identifiers to calendar events in the fetched data

### FR3: Event Detail Extraction
- Extracts participants from event's attendees_list (or owner if solo)
- Calculates duration from event's start/end times
- Preserves title, location, and other metadata
- Validates that event is internal-only (if moving is required)

### FR4: Scheduling Problem Construction
- Constructs SchedulingProblem using extracted event details as base
- Merges additional constraints/preferences from utterance
- Includes original event in calendar data with appropriate flags
- Sets timeframe to search for alternatives (default: next 2 weeks from current date)
- Supports only one meeting per request (single event rescheduling only)

### FR5: Original Event Handling
- Original event is included in normalized calendar data
- Original event is marked as movable (if internal-only)
- Proposals that require moving original event include it in `moved_events`
- Original event details are preserved in proposal metadata

### FR6: Output Enhancements
- Proposals include `original_event_id` and `original_event_details` fields
- User display indicates this is a rescheduling operation and uses the same or very similar format to the current user report
- Agent data includes original event reference for follow-up actions
- Tool does not make any actual event changes or cancellations (proposals only)

## Goals & Non-Goals

### Goals
- Support both natural language and explicit event ID rescheduling requests
- Automatically extract meeting details from existing events
- Treat original events as movable when finding alternatives
- Preserve all original meeting metadata (title, location, participants)
- Maintain backward compatibility with existing scheduling functionality

### Non-Goals
- Automatic event deletion/cancellation (tool only proposes changes, agent handles actual modifications)
- Rescheduling multiple meetings in a single request (one meeting per request only)
- Recurring meeting series rescheduling (only the specific instance mentioned in the request)
- Cross-calendar event ownership changes
- Rescheduling external meetings (only internal-only events can be moved)

## Acceptance Criteria

1. **Natural Language Rescheduling**: User can request rescheduling via natural language, and tool correctly identifies the meeting and proposes alternatives.
2. **Event ID Rescheduling**: Agent can provide event_id and event_owner_id, and tool fetches the event and proposes alternatives.
3. **Event Detail Preservation**: All original meeting details (participants, duration, title, location) are preserved in proposals.
4. **Original Event Movement**: When best alternatives require moving the original event, it appears in `moved_events` with correct old/new times.
5. **Backward Compatibility**: Existing scheduling functionality (new meetings) continues to work without changes.
6. **Error Handling**: Tool gracefully handles cases where event cannot be found, is external-only, or is not accessible.

## Dependencies
- PBI 21 (Scheduling Orchestration Tool) - Must be completed
- MCP Core_Event_Data tool - Must support fetching events by ID
- DSPy extraction - Must be extended for rescheduling intent detection

## Design Decisions

### Single Meeting Per Request
The tool supports rescheduling only one meeting at a time. Multiple meeting rescheduling requests must be handled as separate tool calls.

### Default Search Timeframe
The default search timeframe for alternative slots is **the next 2 weeks** from the current date. This can be overridden via the `context_json` timeframe parameter if needed.

### Proposal-Only Mode
The tool **does not make any actual event changes or cancellations**. It only proposes alternative time slots in the same format as the current user report. The agent is responsible for executing any actual calendar modifications based on user approval.

### Recurring Event Handling
For recurring meeting instances, the tool only considers the specific instance mentioned in the request. It does not attempt to reschedule the entire recurring series, only the individual occurrence identified by the user.

## Related Tasks
- [Back to task list](./tasks.md)
- Tasks tracked in `docs/delivery/22/tasks.md`

