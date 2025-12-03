# Work Hours Default and Individual Settings Fix

## Summary

Updated the orchestrator to:
1. **Default to 9-5 Eastern time** for all participants unless explicitly specified
2. **Respect individual work hours** when specified for specific participants
3. **Properly enforce work hours** after horizon reduction

## Changes Made

### 1. Default Work Hours to Eastern Time

**File**: `letta/scheduling_orchestrator/normalizer.py`

- Changed default work hours from timezone-dependent to always **9-5 Eastern (America/New_York)**
- When a participant doesn't specify `work_hours`, defaults to `"M-F 09:00-17:00"` in Eastern time
- When a participant is not in `context_json["participants"]`, applies default 9-5 Eastern

**Before**: Default used timeframe timezone or UTC
**After**: Default always uses Eastern timezone (`America/New_York`)

### 2. Individual Work Hours Support

- If a participant specifies `work_hours` in their participant object, that is used
- Uses the participant's `timezone` field if specified, otherwise falls back to timeframe timezone
- Work hours are properly calculated per participant and enforced individually

### 3. Horizon Reduction Work Hours Recalculation

**File**: `letta/scheduling_orchestrator/orchestrate_scheduling.py`

- When horizon is reduced, work hours are **recalculated** (not just shifted)
- Recalculation uses:
  - Individual work hours if specified for each participant
  - Default 9-5 Eastern if not specified
- Ensures work hours align correctly with the new horizon timeframe

### 4. Work Hours Enforcement

**File**: `letta/scheduling_orchestrator/fact_generator.py`

- Enhanced work hours checking to ensure slots are within all participants' work hours
- Intersection logic: meeting must be within ALL participants' work hours
- Proper handling of edge cases (empty sets, missing participants)

## Test Results

### Test 1: Default 9-5 Eastern ✓
- Participants with no `work_hours` specified
- Result: Meeting scheduled at 2:30 PM ET (Monday) - within 9-5 Eastern ✓

### Test 2: Individual Work Hours ✓
- Chad: Default 9-5 Eastern
- Sue: 10 AM - 6 PM Eastern
- Result: Meeting scheduled at 2:30 PM ET - within intersection (10 AM - 5 PM) ✓

### Test 3: Work Hours Enforcement ✓
- Previously returned slot at 11:30 PM ET (outside work hours)
- Now correctly enforces work hours and finds slots within 9-5 Eastern ✓

## Behavior

### Default Behavior
- **No work_hours specified**: Uses 9-5 Eastern (`M-F 09:00-17:00` in `America/New_York` timezone)
- **Participant not in context**: Uses 9-5 Eastern
- **No context provided**: Uses 9-5 Eastern

### Individual Work Hours
- **work_hours specified**: Uses that participant's work hours
- **timezone specified**: Uses that timezone for work hours calculation
- **No timezone**: Uses timeframe timezone (or Eastern as fallback)

### Work Hours Intersection
- Meeting must be within **ALL** participants' work hours
- If Chad: 9-5, Sue: 10-6, meeting must be 10-5 (intersection)
- If no intersection exists, returns UNSAT with relaxation suggestions

## Example Usage

```json
{
  "participants": [
    {
      "id": "user1@example.com",
      "email": "user1@example.com",
      "name": "User 1"
      // No work_hours - defaults to 9-5 Eastern
    },
    {
      "id": "user2@example.com",
      "email": "user2@example.com",
      "name": "User 2",
      "work_hours": "M-F 10:00-18:00",
      "timezone": "America/New_York"
      // Individual work hours: 10 AM - 6 PM Eastern
    }
  ]
}
```

Result: Meeting will be scheduled within 10 AM - 5 PM (intersection of both work hours).

