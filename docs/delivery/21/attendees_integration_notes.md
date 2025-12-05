# Attendees List Integration Notes

## Overview

The `Core_Event_Data` tool now includes an `attendees_list` field containing email addresses of event attendees. This document describes how this information can be used in the scheduling orchestrator.

## Current Status

**Workflow Issue**: The n8n workflow is currently returning `attendees_list` as a string representation of an array instead of an actual array. This needs to be fixed in the workflow configuration.

**Error Message**: `"'attendees_list' expects a array but we got '[nwarner@hewlett.org, dkehoe@concord.org, cdorsey@concord.org]' [item 3]"`

## Expected Data Structure

Once the workflow is fixed, events should have:

```json
{
  "summary": "Event title",
  "id": "event_id",
  "start": {"dateTime": "2025-12-09T11:00:00-05:00"},
  "end": {"dateTime": "2025-12-09T15:00:00-05:00"},
  "locked": false,
  "protected": false,
  "flexible": true,
  "number_of_attendees": 3,
  "internal_only": false,
  "attendees_list": [
    "attendee1@example.com",
    "attendee2@example.com",
    "attendee3@example.com"
  ]
}
```

## Integration Options

### Option 1: Pass Through (Minimal Change)

Include `attendees` in normalized events but don't use it in orchestrator logic:

**Pros:**
- Minimal code changes
- Data available for future use
- No impact on current scheduling logic

**Cons:**
- Doesn't leverage the information

### Option 2: Use for Conflict Detection

Use attendees to identify conflicts with other participants in the scheduling request:

**Use Cases:**
- If an event has attendees that overlap with participants in the scheduling request, it may be more important to avoid moving
- Can help identify which events are "group meetings" vs "individual meetings"
- Can inform prioritization of which events to move

**Implementation:**
```python
def has_attendee_overlap(event_attendees: List[str], scheduling_participants: List[str]) -> bool:
    """Check if event attendees overlap with scheduling participants."""
    return bool(set(event_attendees) & set(scheduling_participants))
```

### Option 3: Enhance Event Metadata

Include attendees in `EventMetadata` for agent reasoning:

**Current EventMetadata:**
```python
class EventMetadata(BaseModel):
    title: str
    owner: str
    start_utc: str
    end_utc: str
    locked: bool
    protected: bool
    flexible: bool
    number_of_attendees: int
    internal_only: bool
    human_readable: str
```

**Enhanced EventMetadata:**
```python
class EventMetadata(BaseModel):
    # ... existing fields ...
    attendees: List[str] = Field(default_factory=list, description="List of attendee email addresses")
```

## Recommended Approach

**Phase 1 (Immediate)**: 
- Fix n8n workflow to return `attendees_list` as an array
- Include `attendees` in normalized event data (pass through)
- Update normalization code to handle both array and string formats (defensive)

**Phase 2 (Future Enhancement)**:
- Add `attendees` field to `Event` schema (optional)
- Include in `EventMetadata` for agent reasoning
- Consider using for conflict detection and prioritization

## Normalization Code Update

The normalization code should handle the attendees_list field:

```python
# Extract attendees_list (handle both array and potential string representation)
attendees_list = evt.get("attendees_list", [])
if isinstance(attendees_list, str):
    # If it's a string representation, try to parse it
    # This handles workflow errors where it's returned as a string
    try:
        import ast
        attendees_list = ast.literal_eval(attendees_list)
    except:
        # If parsing fails, treat as empty
        attendees_list = []
elif not isinstance(attendees_list, list):
    attendees_list = []

# Include in normalized event
normalized_event = {
    # ... other fields ...
    "attendees": attendees_list  # Renamed from attendees_list for consistency
}
```

## Workflow Fix Required

The n8n workflow needs to ensure `attendees_list` is returned as a proper JSON array, not a string representation. This is likely a data transformation issue in the workflow where the array is being converted to a string.

## Testing

Once the workflow is fixed:
1. Test that `attendees_list` is returned as an array
2. Verify normalization handles it correctly
3. Confirm events include attendees in the expected format
4. Test with events that have multiple attendees
5. Test with events that have no attendees (empty array)

