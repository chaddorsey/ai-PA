# Participant Names Structure Recommendation

## Current State

**MCP Core_Event_Data currently returns:**
```json
{
  "summary": "Meeting Title",
  "id": "event_id",
  "attendees_list": ["email1@example.com", "email2@example.com"],
  ...
}
```

**Current limitations:**
- Only email addresses, no names
- Matching relies on fuzzy matching email prefixes (e.g., "Judi Raiff" → "jraiff@concord.org")
- Cannot directly match names from user utterances to event attendees
- Title extraction for participant names (e.g., "Kate/Chad check in") is less reliable

## Recommended Structure

### Option 1: Add `attendees` field (Recommended)

**Add a new `attendees` field alongside existing `attendees_list` for backward compatibility:**

```json
{
  "summary": "Meeting Title",
  "id": "event_id",
  "attendees_list": ["jraiff@concord.org", "cdorsey@concord.org"],  // Keep for backward compatibility
  "attendees": [
    {
      "email": "jraiff@concord.org",
      "name": "Judi Raiff",
      "displayName": "Judi Raiff"  // Optional: formatted display name
    },
    {
      "email": "cdorsey@concord.org",
      "name": "Chad Dorsey",
      "displayName": "Chad Dorsey"
    }
  ],
  ...
}
```

**Benefits:**
- ✅ Backward compatible: Existing code using `attendees_list` continues to work
- ✅ Rich data: Provides both email and name for each attendee
- ✅ Direct matching: Can match "Judi Raiff" directly to event attendees
- ✅ Better fuzzy matching: Can match name parts (e.g., "Judi" or "Raiff") to names
- ✅ Title extraction: Can match names from titles (e.g., "Kate/Chad check in") to attendee names
- ✅ Gradual migration: Can update orchestrator to use `attendees` while keeping `attendees_list`

**Structure details:**
- `email` (required): Email address (same as in `attendees_list`)
- `name` (required): Full name (e.g., "Judi Raiff", "Chad Dorsey")
- `displayName` (optional): Formatted display name if different from `name`

### Option 2: Replace `attendees_list` with `attendees` (Breaking Change)

**Replace `attendees_list` entirely:**

```json
{
  "summary": "Meeting Title",
  "id": "event_id",
  "attendees": [
    {
      "email": "jraiff@concord.org",
      "name": "Judi Raiff"
    },
    ...
  ],
  ...
}
```

**Benefits:**
- ✅ Cleaner structure
- ✅ Single source of truth
- ❌ Breaking change: Requires updating all code that uses `attendees_list`

## Recommended Approach: Option 1

**Implementation plan:**

1. **MCP Server Changes:**
   - Add `attendees` field to Core_Event_Data response
   - Keep `attendees_list` for backward compatibility
   - Populate `attendees` with email and name for each attendee

2. **Orchestrator Updates:**
   - Update `event_matcher.py` to prefer `attendees` over `attendees_list`
   - Enhance `map_participant_names_to_emails` to use attendee names
   - Improve `score_event_match` to match names directly
   - Update title extraction to match names from titles

3. **Migration Path:**
   - Phase 1: Add `attendees` field, keep `attendees_list` (backward compatible)
   - Phase 2: Update orchestrator to use `attendees` when available, fallback to `attendees_list`
   - Phase 3: (Future) Remove `attendees_list` once all consumers updated

## Usage in Orchestrator

### Current Flow (with `attendees_list` only):
```python
event_attendees = event.get("attendees_list", [])  # ["jraiff@concord.org", ...]
# Must use fuzzy matching to map "Judi Raiff" → "jraiff@concord.org"
```

### Enhanced Flow (with `attendees`):
```python
# Prefer attendees if available, fallback to attendees_list
attendees_data = event.get("attendees", [])
if attendees_data:
    # Direct name matching
    attendee_emails = [a["email"] for a in attendees_data]
    attendee_names = [a["name"].lower() for a in attendees_data]
    
    # Match "Judi Raiff" directly to attendee names
    if "judi raiff" in attendee_names:
        matching_email = attendees_data[attendee_names.index("judi raiff")]["email"]
else:
    # Fallback to attendees_list (backward compatibility)
    attendee_emails = event.get("attendees_list", [])
```

## Matching Improvements

### Direct Name Matching
```python
# User says: "Find new time for meeting with Judi Raiff"
# Event has: attendees = [{"email": "jraiff@concord.org", "name": "Judi Raiff"}]
# Can directly match "Judi Raiff" → "Judi Raiff" (exact match)
```

### Partial Name Matching
```python
# User says: "Reschedule meeting with Judi"
# Event has: attendees = [{"email": "jraiff@concord.org", "name": "Judi Raiff"}]
# Can match "Judi" → "Judi Raiff" (partial match on first name)
```

### Title-Based Matching
```python
# User says: "Reschedule Kate/Chad check in"
# Event has: 
#   summary = "Kate/Chad check in"
#   attendees = [
#     {"email": "kate@example.com", "name": "Kate Smith"},
#     {"email": "chad@example.com", "name": "Chad Dorsey"}
#   ]
# Can match "Kate" and "Chad" from title to attendee names
```

## Example MCP Response

```json
{
  "summary": "Chad & Leslie",
  "id": "5o5poen7um7fgn5od9bvfhn5ak_20251215T171500Z",
  "start": {
    "dateTime": "2025-12-15T11:15:00-05:00"
  },
  "end": {
    "dateTime": "2025-12-15T12:00:00-05:00"
  },
  "locked": false,
  "protected": false,
  "flexible": true,
  "number_of_attendees": 2,
  "internal_only": true,
  "attendees_list": ["cdorsey@concord.org", "lbondaryk@concord.org"],
  "attendees": [
    {
      "email": "cdorsey@concord.org",
      "name": "Chad Dorsey",
      "displayName": "Chad Dorsey"
    },
    {
      "email": "lbondaryk@concord.org",
      "name": "Leslie Bondaryk",
      "displayName": "Leslie Bondaryk"
    }
  ]
}
```

## Implementation Notes

1. **Name Format:**
   - Use full name (e.g., "Judi Raiff", "Chad Dorsey")
   - Normalize to lowercase for matching
   - Preserve original case for display

2. **Missing Names:**
   - If name is not available, use email prefix as fallback (e.g., "jraiff" from "jraiff@concord.org")
   - Or use `displayName` from calendar if available

3. **Name Variations:**
   - Handle common variations (e.g., "Judi" vs "Judith", "Chad" vs "Chadwick")
   - Use fuzzy matching for partial matches

4. **Backward Compatibility:**
   - Always check for `attendees` first, fallback to `attendees_list`
   - Maintain existing code paths that use `attendees_list`

## Conclusion

**Recommended structure: Add `attendees` field with email and name, keep `attendees_list` for backward compatibility.**

This provides:
- ✅ Rich participant data for better matching
- ✅ Backward compatibility with existing code
- ✅ Direct name matching capabilities
- ✅ Better title-based participant extraction
- ✅ Gradual migration path

