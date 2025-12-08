# Rescheduling Workflow Analysis: Expected vs Actual

## Expected Workflow (User's Specification)

1. **Title Extraction**: Extract "Kate / Chad meeting" as title search string/variants from utterance
2. **Date Extraction**: Extract "Monday" as date reference for event identification
3. **Calendar Selection**: Use `user_id` + possessive pronoun "my" to determine calendar to search (`cdorsey@concord.org`)
4. **Calendar Search**: Search that specific calendar for all events on Monday, Dec. 8
5. **Title Matching**: Search event summaries for "Kate / Chad" and close variants
6. **Event Identification**: Identify correct event (2:15 PM that day)
7. **Event Details Extraction**: Collect actual participants, start/end time, and duration from MCP response
8. **Scheduling**: Use actual event details (participants, duration) to find alternative slots

## Actual Workflow (From Logs)

1. **Title Extraction**: ❌ FAILED - `event_identifiers.titles` was empty `[]`
   - DSPy extracted: `{'participant_names': ['Kate', 'Chad'], 'dates': ['Monday'], 'times': [], 'titles': []}`
   - "Kate / Chad meeting" was NOT extracted as a title

2. **Date Extraction**: ✅ SUCCESS - "Monday" extracted to `event_identifiers.dates`

3. **Calendar Selection**: ⚠️ PARTIAL - Used `participant_ids` parameter instead of `user_id` + "my"
   - Used: `['cdorsey@concord.org', 'kmiller@concord.org']` (from `participant_ids`)
   - Should have used: `cdorsey@concord.org` (from `user_id` + "my" pronoun)

4. **Calendar Search**: ✅ SUCCESS - Searched both calendars for events

5. **Title Matching**: ❌ FAILED - Event had empty title in MCP response
   - Matched event: `o9jl388gbota6f74dvg1i0t0pj_20251208T140000Z` with score 1.00
   - Score based on: Date match (Monday) + Participant match (Kate, Chad)
   - Title was empty `''` in MCP response, so title matching couldn't work

6. **Event Identification**: ⚠️ UNCERTAIN - Found an event but may be wrong one
   - Event ID: `o9jl388gbota6f74dvg1i0t0pj_20251208T140000Z`
   - Time: 2:00 PM UTC (9:00 AM EST) - User says should be 2:15 PM
   - Title: "Untitled Meeting" (empty in MCP)

7. **Event Details Extraction**: ❌ FAILED - Wrong details extracted
   - Participants: Extracted `['cdorsey@concord.org']` (1 participant)
   - Duration: Extracted 120 minutes
   - Title: "Untitled Meeting" (empty in MCP response)

8. **Scheduling**: ❌ FAILED - Used wrong participants and duration
   - Used: `participant_ids` parameter `['cdorsey@concord.org', 'kmiller@concord.org']` instead of event participants
   - Used: 60 minutes (from DSPy default) instead of event duration (120 min) or actual (45 min?)

## Root Causes

### 1. DSPy Title Extraction Failure
**Problem**: DSPy prompt instructs to extract titles in `event_identifiers.titles`, but "Kate / Chad meeting" wasn't extracted.

**Why**: 
- The prompt says "event titles (e.g., 'check-in', 'standup', 'review meeting')" - these are generic examples
- "Kate / Chad meeting" contains participant names, which may have been extracted as `participant_names` instead
- DSPy may not recognize participant-name patterns as titles

**Fix Needed**: 
- Enhance DSPy prompt to explicitly extract participant-name patterns in titles (e.g., "X / Y", "X & Y", "X and Y")
- Add examples: "Kate / Chad meeting" → `titles: ['Kate / Chad']`
- Consider extracting both: participant names AND title patterns

### 2. Calendar Selection Logic
**Problem**: Used `participant_ids` parameter instead of `user_id` + possessive pronoun.

**Why**:
- Current priority: `participant_ids` → utterance extraction → event participants → `user_id`
- The "my" pronoun wasn't used to determine which calendar to search first

**Fix Needed**:
- Add logic to detect possessive pronouns ("my", "mine") in utterance
- When "my" is detected, prioritize `user_id` calendar for initial search
- Only search other calendars if event not found in `user_id` calendar

### 3. MCP Response Missing Title
**Problem**: Event's `summary` field was empty in MCP response.

**Why**:
- MCP server may not be returning the `summary` field correctly
- Or the event in Google Calendar has an empty title

**Fix Needed**:
- Verify MCP server returns `summary` field
- If empty, try alternative fields (`title`, `name`)
- Fall back to title extraction from utterance/event_identifiers

### 4. Event Matching Without Title
**Problem**: Event matcher scored event 1.00 based only on date + participants, not title.

**Why**:
- Title was empty, so title matching couldn't contribute to score
- Date match (Monday) + participant match (Kate, Chad) gave perfect score
- May have matched wrong event if multiple events on Monday with similar participants

**Fix Needed**:
- Require title match (or explicit confirmation) when title is available in utterance
- Lower score threshold when title is missing but expected
- Add logging to show why event was matched

### 5. Wrong Participants Used
**Problem**: Used `participant_ids` parameter instead of actual event participants.

**Why**:
- Merge logic prioritizes `participant_ids` parameter over event participants
- This is correct for NEW scheduling, but wrong for RESCHEDULING
- For rescheduling, should use event participants as base, allow additions/removals

**Fix Needed**:
- For rescheduling: Use event participants as base
- Only add/remove participants if utterance explicitly mentions changes
- `participant_ids` parameter should be used for NEW scheduling, not rescheduling

### 6. Wrong Duration Used
**Problem**: Used 60 minutes (DSPy default) instead of event duration (120 min) or actual (45 min?).

**Why**:
- Merge logic checks if utterance duration is >50% different from event duration
- 60 vs 120 is 50% difference, so it used utterance duration
- But utterance didn't specify duration - DSPy extracted default 60 min

**Fix Needed**:
- Only use utterance duration if utterance explicitly mentions duration
- Check utterance for duration keywords ("30 minutes", "1 hour", etc.)
- If no explicit duration in utterance, always use event duration for rescheduling

## Proposed Fixes

### Fix 1: Enhance DSPy Title Extraction
```python
# In dspy_extraction.py, update prompt:
"Extract event titles including participant-name patterns like 'Kate / Chad', 'X & Y', 'X and Y meeting'. 
These should be extracted to event_identifiers.titles even if they also contain participant names."
```

### Fix 2: Add Possessive Pronoun Detection
```python
# In orchestrate_scheduling.py, before calendar selection:
if user_id and ("my " in utterance.lower() or "mine " in utterance.lower()):
    # Prioritize user_id calendar for initial search
    calendars_to_search = [user_id]
    # Only search other calendars if event not found
```

### Fix 3: Require Title Match for Rescheduling
```python
# In event_matcher.py, score_event_match:
if event_identifiers.get("titles") and not event_title:
    # Title expected but missing - reduce score significantly
    score *= 0.5  # Penalty for missing expected title
```

### Fix 4: Use Event Participants for Rescheduling
```python
# In event_extractor.py, merge_event_details_with_utterance:
# For rescheduling, prioritize event participants
if extracted_event_details:
    event_participants = extracted_event_details.get("participants", [])
    # Only override if utterance explicitly adds/removes participants
    # Check utterance for explicit participant changes
    if not has_explicit_participant_changes(utterance):
        merged_participants = event_participants
```

### Fix 5: Only Use Utterance Duration If Explicit
```python
# In event_extractor.py, check utterance for explicit duration:
def has_explicit_duration(utterance: str) -> bool:
    """Check if utterance explicitly mentions a duration."""
    duration_keywords = ["minute", "hour", "hr", "min", "30", "45", "60", "90", "120"]
    return any(kw in utterance.lower() for kw in duration_keywords)

# In merge logic:
if not has_explicit_duration(utterance):
    # Always use event duration if utterance doesn't mention duration
    merged_duration = event_duration
```

## Implementation Priority

1. **High Priority**: Fix 4 (Use Event Participants) - Critical for correct rescheduling
2. **High Priority**: Fix 5 (Only Use Explicit Duration) - Prevents wrong duration
3. **Medium Priority**: Fix 1 (Enhance Title Extraction) - Improves event matching
4. **Medium Priority**: Fix 2 (Possessive Pronoun) - More accurate calendar selection
5. **Low Priority**: Fix 3 (Require Title Match) - Safety check, but may be too strict

