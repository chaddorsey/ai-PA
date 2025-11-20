# Scheduling Orchestration Tool - Agent Instructions

## Overview

You have access to a powerful scheduling orchestration tool called `orchestrate_scheduling` that uses constraint-based optimization to find optimal meeting times. This tool can handle complex scheduling requests while minimizing disruption to everyone's calendars.

## Tool Name

`orchestrate_scheduling`

## How to Use

### Step 1: Gather Calendar Events

Before calling `orchestrate_scheduling`, you must first retrieve calendar events for all participants:

- **For the user's calendar**: Use `Get_Events` tool
  - This tool queries the user's own calendar
  - Example: Call `Get_Events` with the desired date range and participant list

- **For other staff calendars**: Use `Get-Events_From_Arbitrary_Calendar` tool
  - This tool queries calendars of other team members/staff
  - Use this for participants other than the user
  - Example: Call `Get-Events_From_Arbitrary_Calendar` for each participant (Alex, Priya, etc.)

**Important**: 
- You need to call these tools for ALL participants in the scheduling request
- **Filter events by time horizon**: Only fetch events within the planning window (e.g., if scheduling for "next 2 weeks", only get events in that range)
- **Filter all-day events**: Exclude events that span 24+ hours (they don't block specific time slots)
- **Use minimal event format**: When preparing events for `orchestrate_scheduling`, only include: `id`, `start`, `end`, `locked`, `protected`, `flexible` (omit `title`, `description`, `location`, etc.)
- This reduces payload size by 60-70% and prevents message size limit errors

### Step 2: Prepare the Inputs

Once you have all the calendar events, prepare the inputs for `orchestrate_scheduling`:

1. **utterance** (string): The user's natural language scheduling request
   - Example: "Find 45 minutes with Alex and Priya next Tuesday morning. Minimize disruption."

2. **events_by_participant** (JSON string): A JSON object mapping participant IDs to their calendar events
   - Format: `{"participant_id": [list of events], ...}`
   - **IMPORTANT**: Use minimal event format to reduce payload size (see below)
   - Each event must have: `id`, `start`, `end`, `locked`, `protected`, `flexible`
   - **Omit unused fields**: `title`, `description`, `location`, `owner` are NOT needed
   - **Pre-filter events**: Only include events within the planning horizon (timeframe)
   - **Filter all-day events**: Exclude events that span 24+ hours (they don't block time slots)
   - Convert the events from Get_Events/Get-Events_From_Arbitrary_Calendar into this minimal format
   - Example JSON (minimal format):
     ```json
     {
       "exec": [
         {
           "id": "evt1",
           "start": "2025-11-25T14:00:00Z",
           "end": "2025-11-25T14:15:00Z",
           "locked": false,
           "protected": false,
           "flexible": true
         }
       ],
       "alex": [
         {
           "id": "evt2",
           "start": "2025-11-25T10:00:00Z",
           "end": "2025-11-25T11:00:00Z",
           "locked": false,
           "protected": true,
           "flexible": false
         }
       ],
       "priya": []
     }
     ```
   - **Payload size optimization**: This minimal format reduces payload by 60-70% compared to full event objects

3. **context_json** (optional JSON string): Scheduling preferences and rules
   - Can include: `timeframe`, `participants` (with work hours), `policy` (min gaps, preferences)
   - Example JSON:
     ```json
     {
       "timeframe": {
         "from": "2025-11-24",
         "to": "2025-12-08",
         "tz": "America/New_York"
       },
       "participants": [
         {
           "id": "exec",
           "email": "user@example.com",
           "work_hours": "M-F 09:00-17:30"
         }
       ],
       "policy": {
         "hard": {
           "min_gap_min": 15
         }
       }
     }
     ```

### Step 3: Call orchestrate_scheduling

Call the tool with the prepared inputs. The tool will:
- Extract the scheduling requirements from the natural language utterance
- Find optimal meeting times that satisfy all constraints
- Minimize disruption (avoid moving protected events, maximize focus blocks)
- Return ready-to-schedule proposals

### Step 4: Handle the Response

The tool returns a response with:

- **status**: `"ok"`, `"unsat"`, or `"bad_input"`
- **proposals**: List of optimal meeting proposals (typically one best proposal)
- **explanation**: Human-readable explanation of why this time was chosen
- **relaxations**: If `status` is `"unsat"`, suggestions for relaxing constraints

**If status is "ok"**:
- Present the proposed meeting time to the user
- Explain why this time was chosen (from the `explanation` field)
- Mention any events that need to be moved (from `moved_events` in the proposal)
- Ask the user if they want to schedule it

**If status is "unsat"**:
- Explain that no meeting time was found that satisfies all constraints
- Present the relaxation suggestions from the `relaxations` field
- Ask the user which constraints they'd like to relax
- You can then re-call the tool with updated context_json if the user agrees to relaxations

**If status is "bad_input"**:
- Check the `error_message` field
- Fix the issue (e.g., ensure events were retrieved, check JSON format)
- Retry the call

## Example Workflow

**User**: "Find 45 minutes with Alex and Priya next Tuesday morning"

**Agent actions**:
1. Call `Get_Events` for the user's calendar (next week)
2. Call `Get-Events_From_Arbitrary_Calendar` for Alex (next week)
3. Call `Get-Events_From_Arbitrary_Calendar` for Priya (next week)
4. Combine all events into `events_by_participant` JSON format
5. Call `orchestrate_scheduling` with:
   - utterance: "Find 45 minutes with Alex and Priya next Tuesday morning"
   - events_by_participant: (the combined JSON)
   - context_json: (optional, with work hours if available)
6. Present the proposal to the user

## Key Points

- **Always gather events first**: You cannot call `orchestrate_scheduling` without calendar events
- **Use the right tool for each calendar**: `Get_Events` for user, `Get-Events_From_Arbitrary_Calendar` for others
- **Convert to JSON strings**: The tool expects `events_by_participant` and `context_json` as JSON strings
- **Handle UNSAT gracefully**: When no solution is found, present relaxations and negotiate with the user
- **Explain the reasoning**: Use the `explanation` field to help the user understand why a time was chosen

## Common Patterns

**Simple meeting request**:
- User asks for a meeting with specific people
- Gather events, call tool, present proposal

**Meeting with preferences**:
- User specifies time preferences (morning, specific days, etc.)
- Include preferences in `context_json` or the utterance
- Tool will optimize for these preferences

**Complex scheduling**:
- Multiple participants, specific constraints
- Tool handles the complexity automatically
- May return UNSAT if constraints are too strict

**Recurring meetings**:
- For recurring meetings, you may need to call the tool multiple times
- Or handle recurrence logic separately after getting the first instance

## Error Handling

- **Missing events**: If `events_by_participant` is empty, the tool returns `bad_input` with a helpful message
- **Invalid JSON**: If JSON parsing fails, check the format and retry
- **No solution found**: Present relaxations and work with the user to find an acceptable compromise
- **Tool dependencies missing**: If you get an error about missing dependencies, inform the user that the scheduling system needs to be configured

