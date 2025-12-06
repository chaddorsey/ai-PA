# Attendees Details Integration Plan

## Overview

The MCP server now returns `attendees_details` array in the format:
```json
[
  {"email": "cdorsey@concord.org", "name": "Chad Dorsey"},
  {"email": "jraiff@concord.org", "name": "Judi Raiff"}
]
```

This document outlines how to integrate this information into both standard scheduling and rescheduling modes.

## Use Cases

### Standard Mode (New Meeting Scheduling)

1. **Participant Name Matching**
   - User says: "Schedule a meeting with Judi Raiff"
   - DSPy can match "Judi Raiff" directly to participant names in context
   - Better extraction of participant list from utterance

2. **Context Enhancement**
   - Include participant names in `context_json.participants` for DSPy
   - DSPy can understand "meeting with Judi" better when names are available
   - Better handling of partial names (e.g., "Judi" → "Judi Raiff")

3. **Display/Formatting**
   - Show participant names in proposals (not just emails)
   - Better user-facing output with human-readable names

### Reschedule Mode

1. **Direct Name Matching in Event Identification**
   - User says: "Reschedule meeting with Judi Raiff on Dec. 10th"
   - Event has: `attendees_details = [{"email": "jraiff@concord.org", "name": "Judi Raiff"}]`
   - Can directly match "Judi Raiff" → event attendee name (no fuzzy matching needed)
   - Much more accurate event identification

2. **Title-Based Participant Extraction**
   - Event title: "Kate/Chad check in"
   - Event has: `attendees_details = [{"email": "kate@example.com", "name": "Kate Smith"}, {"email": "chad@example.com", "name": "Chad Dorsey"}]`
   - Can match "Kate" and "Chad" from title to attendee names
   - Better scoring for events with participant names in titles

3. **Improved Scoring**
   - Direct name matches get higher scores
   - Partial name matches (first name only) work better
   - Combination bonuses (participants + date) more accurate

## Integration Points

### 1. MCP Client (`mcp_client.py`)
- **Action**: Update docstring to document `attendees_details` field
- **Location**: `get_core_event_data` method docstring

### 2. Event Normalization (`orchestrate_scheduling.py`)
- **Action**: Extract and store `attendees_details` in normalized events
- **Location**: `fetch_participant_events` function (around line 519)
- **Storage**: Add `attendees_details` field to normalized event dict
- **Fallback**: If `attendees_details` not available, construct from `attendees_list` (backward compatibility)

### 3. Event Matching (`event_matcher.py`)
- **Action**: Use `attendees_details` for direct name matching
- **Location**: `score_event_match` function
- **Changes**:
  - Prefer `attendees_details` over `attendees_list` when available
  - Match participant names directly to attendee names
  - Use names for title-based participant extraction
  - Improve scoring with name-based matches

### 4. Context JSON Building (`orchestrate_scheduling.py`)
- **Action**: Include participant names in `context_json.participants`
- **Location**: Where `context_json` is built/enhanced
- **Changes**: Add `name` field to participant objects in context

### 5. DSPy Context (`dspy_extraction.py`)
- **Action**: DSPy can use participant names from context
- **Location**: `extract_scheduling_request` function
- **Note**: DSPy already receives `context_json` which will now include names

### 6. Event Extraction for Rescheduling (`event_extractor.py`)
- **Action**: Preserve `attendees_details` when extracting event details
- **Location**: `extract_event_details_for_rescheduling` function
- **Changes**: Include `attendees_details` in extracted event details

### 7. Display/Formatting (`formatting.py`)
- **Action**: Use names for display when available
- **Location**: User-facing output formatting
- **Changes**: Show names instead of (or alongside) emails in proposals

## Implementation Steps

### Step 1: Update Event Normalization
- Extract `attendees_details` from MCP response
- Store in normalized event structure
- Maintain backward compatibility with `attendees_list`

### Step 2: Update Event Matching
- Modify `score_event_match` to use `attendees_details`
- Add direct name matching logic
- Enhance title-based participant extraction

### Step 3: Update Context Building
- Include participant names in `context_json.participants`
- Build name-to-email mapping for DSPy

### Step 4: Update Event Extraction
- Preserve `attendees_details` in rescheduling flow
- Use names for better event identification

### Step 5: Update Display
- Show participant names in user-facing output
- Format proposals with names instead of emails

## Backward Compatibility

- Always check for `attendees_details` first, fallback to `attendees_list`
- If `attendees_details` not available, construct from `attendees_list` (use email prefix as name)
- Maintain existing code paths that use `attendees_list`

## Testing Considerations

1. **Standard Mode**: Test with utterances containing participant names
2. **Reschedule Mode**: Test event identification with name-based matching
3. **Backward Compatibility**: Test with events that only have `attendees_list`
4. **Title Extraction**: Test events with participant names in titles

