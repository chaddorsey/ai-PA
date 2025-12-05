# Scheduling Orchestration Tool - Agent Instructions

## Overview

You have access to a powerful scheduling orchestration tool called `orchestrate_scheduling` that uses constraint-based optimization to find optimal meeting times. This tool can handle complex scheduling requests while minimizing disruption to everyone's calendars.

**IMPORTANT**: The tool now automatically fetches calendar events for you! You no longer need to call `Get_Events` or `Core_Event_Data` first.

## Tool Name

`orchestrate_scheduling`

## How to Use (Recommended Mode)

### Step 1: Extract Participant Information

From the user's request, identify:
- **Participant email addresses**: All people who need to attend the meeting
- **Date range**: The timeframe for scheduling (e.g., "next week", "December 8-14")
- **User's email**: The person making the request (optional but helpful)

### Step 2: Prepare the Inputs

1. **utterance** (string): The user's natural language scheduling request
   - Example: "Find 45 minutes with Alex and Priya next Tuesday morning. Minimize disruption."
   - Pass this exactly as the user said it - the tool extracts requirements automatically

2. **participant_ids** (list of strings): **REQUIRED** - List of participant email addresses
   - Include ALL participants who need to attend
   - Example: `["cdorsey@concord.org", "alex@example.com", "priya@example.com"]`
   - The tool will automatically fetch their calendar events via MCP
   - **No need to call Get_Events or Core_Event_Data first!**

3. **context_json** (JSON string): **REQUIRED when using participant_ids** - Must include timeframe
   - **Minimum required**:
     ```json
     {
       "timeframe": {
         "from": "2025-12-08",
         "to": "2025-12-14",
         "tz": "America/New_York"
       }
     }
     ```
   - **Optional but recommended**:
     ```json
     {
       "timeframe": {
         "from": "2025-12-08",
         "to": "2025-12-14",
         "tz": "America/New_York"
       },
       "participants": [
         {
           "id": "exec",
           "email": "cdorsey@concord.org",
           "work_hours": "M-F 09:00-17:30"
         }
       ],
       "policy": {
         "hard": {
           "min_gap_min": 15
         },
         "soft": {
           "maximize_focus_blocks": {"block_min": 90, "weight": 10},
           "minimize_moves_of_existing": {"weight_per_min_shift": 2, "tier": "protected"}
         }
       }
     }
     ```

4. **user_id** (string, optional): User's own email address
   - Example: `"cdorsey@concord.org"`
   - For reference only - the tool treats all calendars the same

### Step 3: Call orchestrate_scheduling

Simply call the tool with the inputs above. The tool will:
- **Automatically fetch** calendar events for all participants via MCP
- Extract the scheduling requirements from the natural language utterance
- Find optimal meeting times that satisfy all constraints
- Minimize disruption (avoid moving protected events, maximize focus blocks)
- Return ready-to-schedule proposals

**You do NOT need to:**
- ❌ Call `Get_Events` or `Core_Event_Data` first
- ❌ Format events into JSON
- ❌ Filter or process events
- ❌ Worry about message size limits

The tool handles all of this automatically!

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

## Example Workflow (Recommended Mode)

**User**: "Find 45 minutes with Alex and Priya next Tuesday morning"

**Agent actions**:
1. Extract participant emails: `["cdorsey@concord.org", "alex@example.com", "priya@example.com"]`
2. Determine date range: "next Tuesday morning" → December 9-13, 2025 (example)
3. Call `orchestrate_scheduling` with:
   ```python
   {
     "utterance": "Find 45 minutes with Alex and Priya next Tuesday morning",
     "participant_ids": ["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
     "context_json": "{\"timeframe\": {\"from\": \"2025-12-09\", \"to\": \"2025-12-13\", \"tz\": \"America/New_York\"}}"
   }
   ```
4. The tool automatically fetches all calendar events
5. Present the proposal to the user

**That's it!** No manual event fetching needed.

## Legacy Mode (Optional)

If you already have events fetched (e.g., from testing or custom sources), you can use the legacy `events_by_participant` parameter instead of `participant_ids`. However, the recommended approach is to use `participant_ids` and let the tool fetch events automatically.

## Key Points

- **Use participant_ids**: The tool automatically fetches calendar events - no need to call Get_Events or Core_Event_Data first
- **Always provide timeframe**: When using `participant_ids`, `context_json` must include a `timeframe` with `from`, `to`, and `tz` fields
- **Extract emails from names**: If the user mentions names like "Alex", map them to email addresses (e.g., "alex@example.com")
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

- **Missing timeframe**: If `participant_ids` is provided but `context_json` doesn't include `timeframe`, the tool returns `bad_input` with a clear error message. Always include timeframe when using participant_ids.
- **MCP fetch failures**: If the tool cannot fetch events from the MCP server, it returns `bad_input` with details. Check that participant email addresses are correct and the MCP server is accessible.
- **Invalid JSON**: If JSON parsing fails, check the format of `context_json` and retry
- **No solution found**: Present relaxations and work with the user to find an acceptable compromise
- **Tool dependencies missing**: If you get an error about missing dependencies, inform the user that the scheduling system needs to be configured

## Troubleshooting

**"Missing timeframe in context_json" error**:
- Ensure `context_json` includes a `timeframe` object with `from`, `to`, and `tz` fields
- Example: `{"timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"}}`

**"Failed to fetch calendar events from MCP server" error**:
- Verify participant email addresses are correct
- Check that the MCP calendar server is running and accessible
- Ensure participant emails match calendar identifiers

**"No events provided or fetched" error**:
- This usually means the MCP server returned no events for the given participants and date range
- Verify the date range is correct
- Check that participants have calendars accessible via the MCP server

