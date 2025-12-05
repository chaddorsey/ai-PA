# Core_Event_Data Response Structure

## Confirmed Data Structure

The `Core_Event_Data` tool returns a JSON array of event objects. Each event has the following structure:

```json
[
  {
    "summary": "Event title/name",
    "id": "unique_event_id",
    "start": {
      "dateTime": "2025-12-09T11:00:00-05:00"
    },
    "end": {
      "dateTime": "2025-12-09T15:00:00-05:00"
    },
    "locked": false,
    "protected": false,
    "flexible": true,
    "number_of_attendees": 0,
    "internal_only": true,
    "attendees_list": [
      "attendee1@example.com",
      "attendee2@example.com",
      "attendee3@example.com"
    ]
  }
]
```

**Note**: The `attendees_list` field is a new addition. It should be an array of email addresses (strings). The n8n workflow may need to ensure this is properly formatted as an array, not a string representation.

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Event title/name |
| `id` | string | Unique event identifier |
| `start.dateTime` | string | ISO 8601 datetime with timezone offset (e.g., "2025-12-09T11:00:00-05:00") |
| `end.dateTime` | string | ISO 8601 datetime with timezone offset |
| `locked` | boolean | Whether event is locked (cannot be moved) |
| `protected` | boolean | Whether event is protected (should not be moved if possible) |
| `flexible` | boolean | Whether event can be moved |
| `number_of_attendees` | number | Number of attendees |
| `internal_only` | boolean | Whether event is internal-only |
| `attendees_list` | array[string] | List of attendee email addresses |

## Normalization for Orchestrator

The orchestrator expects events in this format:

```json
{
  "id": "event_id",
  "title": "Event title",
  "start": "2025-12-09T11:00:00-05:00",
  "end": "2025-12-09T15:00:00-05:00",
  "locked": false,
  "protected": false,
  "flexible": true,
  "attendees": ["attendee1@example.com", "attendee2@example.com"]
}
```

**Transformation needed:**
- `summary` → `title`
- `start.dateTime` → `start` (extract from nested object)
- `end.dateTime` → `end` (extract from nested object)
- `attendees_list` → `attendees` (rename for consistency)
- Keep `id`, `locked`, `protected`, `flexible` as-is
- Drop `number_of_attendees` and `internal_only` (not needed by orchestrator, though `number_of_attendees` can be derived from `attendees_list.length`)

**Note**: The `attendees` field is useful for:
- Identifying conflicts with other participants in the scheduling request
- Understanding meeting context (who else is involved)
- Potentially filtering or prioritizing events based on attendee overlap

## Important Notes

1. **Parameter Names are Reversed**: 
   - `Before` parameter = END date
   - `After` parameter = START date

2. **Date Format**: 
   - Accepts both `YYYY-MM-DD` and ISO datetime strings
   - Returns ISO datetime strings with timezone offset

3. **All-Day Events**: 
   - Should be filtered out (they would have `start.date` instead of `start.dateTime`)
   - Core_Event_Data may already filter these

4. **Response Format**: 
   - Data comes in `result.content[0].text` as a JSON string
   - Must parse JSON to get the array

## Example Normalization Code

```python
def normalize_core_event_data(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize Core_Event_Data response to orchestrator format."""
    normalized = []
    for evt in events:
        # Skip all-day events
        if evt.get("start", {}).get("date"):
            continue
        
        # Extract start/end from nested structure
        start_dt = evt.get("start", {}).get("dateTime")
        end_dt = evt.get("end", {}).get("dateTime")
        
        if not start_dt or not end_dt:
            continue
        
        # Extract attendees_list (handle both array and potential string representation)
        attendees_list = evt.get("attendees_list", [])
        if isinstance(attendees_list, str):
            # If it's a string representation, try to parse it
            # This handles the workflow error case where it's a string
            try:
                import ast
                attendees_list = ast.literal_eval(attendees_list)
            except:
                # If parsing fails, treat as empty
                attendees_list = []
        elif not isinstance(attendees_list, list):
            attendees_list = []
        
        normalized.append({
            "id": evt.get("id", ""),
            "title": evt.get("summary", ""),
            "start": start_dt,
            "end": end_dt,
            "locked": evt.get("locked", False),
            "protected": evt.get("protected", False),
            "flexible": evt.get("flexible", True),
            "attendees": attendees_list  # Include attendees list
        })
    
    return normalized
```

