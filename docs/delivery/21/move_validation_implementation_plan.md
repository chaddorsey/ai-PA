# Move Validation Implementation Plan

## Problem Statement

Currently, the scheduling orchestrator suggests moving events without validating that the new location is conflict-free for all participants of the moved event. This can result in infeasible suggestions that cannot actually be enacted.

## Key Distinction: Phase 3 vs Phase 5

**Phase 3 (Validation Logic)**: 
- Creates the validation function that checks if a moved event conflicts with participants' calendars
- **Assumes all participant calendars are already available** in `normalized_data`
- Does NOT fetch calendars - it only validates using existing data
- Synchronous function (no async/await)

**Phase 5 (Proactive Calendar Fetching)**:
- Identifies participants from moved events who are NOT in the original request
- **Proactively fetches their calendars via MCP** before validation runs
- Updates `normalized_data` with the new participants' calendar data
- This is the "targeted search" mentioned in the requirements

**Why This Separation?**
- **Efficiency**: Fetch all missing calendars in one batch (Phase 5), then validate all moves using that data (Phase 3)
- **Simplicity**: Validation function doesn't need async/await or MCP client - it just checks existing data
- **Performance**: Avoids fetching the same participant's calendar multiple times if they appear in multiple moved events

## Current State Analysis

### What Currently Works
1. **Python Solver**: Checks if moved event conflicts with OTHER events for the SAME participant (owner) - `python_solver.py:756-759`
2. **Work Hours Validation**: Moved events are validated to stay within work hours (recently added)
3. **Internal-Only Preference**: Code prefers internal-only events but doesn't enforce it as a hard constraint

### What's Missing
1. **Multi-Participant Validation**: When an event has multiple participants (attendees), the code doesn't check if moving it conflicts with those other participants' calendars
2. **Internal-Only Enforcement**: No hard constraint that only internal-only meetings can be moved
3. **Attendee Calendar Fetching**: No mechanism to fetch calendar data for participants not in the original request
4. **Post-Solution Validation**: No validation step after solutions are generated to reject invalid moves

## Implementation Plan

### Phase 1: Data Structure Updates

#### 1.1 Store Attendee Information
**Location**: `normalizer.py`

Currently, events store:
- `number_of_attendees`: count only
- `attendees`: list (from MCP, but may not be stored in metadata)

**Action**: Ensure `attendees` list is stored in `event_metadata`:
```python
event_metadata[event_key] = {
    ...
    "attendees": event_dict.get("attendees", []),  # List of participant email addresses
    "number_of_attendees": len(event_dict.get("attendees", []))
}
```

**Note**: Events from MCP already have `attendees` field (normalized from `attendees_list` in `orchestrate_scheduling.py:452`), but this is not currently stored in `event_metadata` in `normalizer.py`.

#### 1.2 Track Event Participants
**Location**: `normalizer.py`

Add mapping: `event_participants: Dict[Tuple[str, str], List[str]]` to track all participants for each event:
```python
# Get attendees list from event
attendees = event_dict.get("attendees", [])
if not isinstance(attendees, list):
    attendees = []

# Store all participants (owner + attendees)
event_participants[event_key] = [participant_id] + attendees  # All participants of the event
```

**Note**: The owner (participant_id) is always a participant, plus any additional attendees from the `attendees` field.

### Phase 2: Internal-Only Enforcement

#### 2.1 Add Hard Constraint
**Location**: `python_solver.py` - `_find_slots_with_single_move()`

**Action**: Add check before considering an event for moving:
```python
# Only consider internal-only events for moving
internal_only = event_meta.get("internal_only", True)
if not internal_only:
    continue  # Skip external events
```

**Location**: `clingo_wrapper.py` - `compute_move_deltas()`

**Action**: Add validation when processing ASP solutions:
```python
# Only process internal-only events
internal_only = event_meta.get("internal_only", True)
if not internal_only:
    continue  # Skip external events
```

### Phase 3: Multi-Participant Conflict Validation

#### 3.1 Create Validation Function
**Location**: New function in `python_solver.py` or new module `move_validator.py`

```python
def validate_move_for_all_participants(
    moved_event: Dict[str, Any],
    new_start_slot: int,
    new_end_slot: int,
    event_metadata: Dict[Tuple[str, str], Dict[str, Any]],
    event_participants: Dict[Tuple[str, str], List[str]],
    normalized_data: Dict[str, Any],
    slot_indexer: SlotIndexer
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a moved event doesn't conflict with any of its participants' calendars.
    
    NOTE: This function assumes all participant calendars are already in normalized_data.
    Calendar fetching for missing participants should be done in Phase 5 (proactive fetching).
    
    Args:
        moved_event: Event being moved (with owner, event_id, new_start, new_end)
        new_start_slot: New start slot index
        new_end_slot: New end slot index
        event_metadata: Map of (participant_id, event_id) -> metadata
        event_participants: Map of (participant_id, event_id) -> list of participant emails
        normalized_data: Normalized data with busy_slots, work_hours_slots (must include all participants)
        slot_indexer: Slot indexer for time calculations
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # 1. Get all participants of the moved event
    event_key = (moved_event["owner"], moved_event["event_id"])
    participants = event_participants.get(event_key, [moved_event["owner"]])
    
    # 2. For each participant, check if new location conflicts
    new_event_slots = set(range(new_start_slot, new_end_slot))
    busy_slots = normalized_data.get("busy_slots", {})
    event_slots_map = normalized_data.get("event_slots_map", {})
    
    for participant_id in participants:
        # Check if we have calendar data for this participant
        if participant_id not in busy_slots:
            # Participant not available - should have been fetched in Phase 5
            return False, f"Participant {participant_id} calendar not available (should have been fetched proactively)"
        
        # Check for conflicts (excluding the event being moved)
        # Get all events for this participant except the one being moved
        participant_other_events = set()
        
        for (p_id, e_id), slots in event_slots_map.items():
            if p_id == participant_id and (p_id, e_id) != event_key:
                participant_other_events.update(slots)
        
        # Check if new location conflicts
        conflicts = new_event_slots.intersection(participant_other_events)
        if conflicts:
            return False, f"New location conflicts with existing events for {participant_id}"
    
    return True, None
```

#### 3.2 Integrate Validation in Python Solver
**Location**: `python_solver.py` - `_find_slots_with_single_move()`

**Action**: Add validation after calculating new location:
```python
# After calculating new_start_slot and new_end_slot (around line 753)
# Validate move for all participants
# NOTE: This assumes all participant calendars are already in normalized_data
# (fetched proactively in Phase 5)
is_valid, error_msg = validate_move_for_all_participants(
    moved_event_dict,
    new_start_slot,
    new_end_slot,
    event_metadata,
    event_participants,
    normalized_data,
    slot_indexer
)

if not is_valid:
    continue  # Skip this move - it's invalid
```

#### 3.3 Integrate Validation in ASP Move Calculation
**Location**: `clingo_wrapper.py` - `compute_move_deltas()`

**Action**: Add validation after calculating new location:
```python
# After calculating new_start_slot (around line 431)
# Validate move for all participants
# Note: This function needs to be async or we need a sync version
# For now, we'll add validation in the proposal building phase
```

### Phase 4: Post-Solution Validation

#### 4.1 Validate All Proposals
**Location**: `orchestrate_scheduling.py` - after building proposals

**Action**: Add validation step before returning proposals:
```python
# After building all_proposals (around line 1824)
# Validate all moved events
validated_proposals = []
for prop in all_proposals:
    if not prop.moved_events:
        # No moves - always valid
        validated_proposals.append(prop)
        continue
    
    # Validate each moved event
    all_moves_valid = True
    for moved_event in prop.moved_events:
        # Get event metadata
        event_key = (moved_event["owner"], moved_event["event_id"])
        event_meta = event_metadata.get(event_key, {})
        
        # Check internal-only constraint
        if not event_meta.get("internal_only", True):
            all_moves_valid = False
            break
        
        # Validate new location doesn't conflict with participants
        new_start_dt = datetime.fromisoformat(moved_event["new_start"].replace('Z', '+00:00'))
        new_end_dt = datetime.fromisoformat(moved_event["new_end"].replace('Z', '+00:00'))
        new_start_slot = slot_indexer.datetime_to_slot(new_start_dt)
        new_end_slot = slot_indexer.datetime_to_slot(new_end_dt)
        
        if new_start_slot is None or new_end_slot is None:
            all_moves_valid = False
            break
        
        # Get all participants
        participants = event_participants.get(event_key, [moved_event["owner"]])
        
        # Check each participant's calendar
        for participant_id in participants:
            if participant_id not in busy_slots:
                # Participant should have been fetched in Phase 5
                # If not available, reject the move
                all_moves_valid = False
                break
            
            # Check conflicts (excluding the moved event itself)
            participant_busy = busy_slots.get(participant_id, set())
            event_slots_map = normalized_data.get("event_slots_map", {})
            
            # Get other events for this participant
            other_event_slots = set()
            for (p_id, e_id), slots in event_slots_map.items():
                if p_id == participant_id and (p_id, e_id) != event_key:
                    other_event_slots.update(slots)
            
            new_event_slots = set(range(new_start_slot, new_end_slot))
            if new_event_slots.intersection(other_event_slots):
                all_moves_valid = False
                break
        
        if not all_moves_valid:
            break
    
    if all_moves_valid:
        validated_proposals.append(prop)

all_proposals = validated_proposals
```

### Phase 5: Targeted Calendar Fetching (Proactive)

**Key Difference from Phase 3**: 
- **Phase 3**: Validation logic that checks conflicts (assumes data is already available)
- **Phase 5**: Proactive fetching of missing participant calendars BEFORE validation
- This is the "targeted search" mentioned in the requirements - fetching calendars for moved-meeting participants not in the original consideration set

#### 5.1 Identify Missing Participants
**Location**: `orchestrate_scheduling.py` - BEFORE building proposals (after initial normalization)

**Action**: Collect all participants from events that might be moved:
```python
# After initial normalization, identify all potential participants
# This includes attendees from events that are candidates for moving
missing_participants = set()

# Check all events for participants not in original request
for (participant_id, event_id), event_meta in event_metadata.items():
    # Get all participants of this event
    participants = event_participants.get((participant_id, event_id), [participant_id])
    for p_id in participants:
        if p_id not in events_by_participant:
            missing_participants.add(p_id)

# OR: After building proposals, collect from moved events
# (if we want to be more targeted and only fetch for events that are actually moved)
missing_participants = set()
for prop in all_proposals:
    for moved_event in prop.moved_events:
        event_key = (moved_event["owner"], moved_event["event_id"])
        participants = event_participants.get(event_key, [moved_event["owner"]])
        for participant_id in participants:
            if participant_id not in events_by_participant:
                missing_participants.add(participant_id)
```

#### 5.2 Fetch Missing Calendars
**Location**: `orchestrate_scheduling.py` - after identifying missing participants

**Action**: Fetch calendars for missing participants:
```python
if missing_participants and mcp_client and context_json:
    # Fetch calendars for missing participants
    missing_list = list(missing_participants)
    fetched_events = await fetch_calendar_events(
        missing_list,
        user_id,
        context_json["timeframe"],
        mcp_client
    )
    
    # Merge into events_by_participant
    for pid, events in fetched_events.items():
        if pid not in events_by_participant:
            events_by_participant[pid] = events
    
    # Re-normalize with additional participants
    # This is complex - may need to re-run normalization
    # OR: Just add to busy_slots directly
```

#### 5.3 Update Normalized Data
**Location**: `orchestrate_scheduling.py` - after fetching

**Action**: Update `normalized_data` with new participants:
```python
# Add new participants to busy_slots
for pid, events in fetched_events.items():
    # Normalize events for this participant
    # Add to busy_slots, event_slots_map, event_metadata
    # This requires calling parts of normalize_events() for just these events
```

### Phase 6: Implementation Strategy

#### Option A: Pre-Validation (Preferred)
- Validate moves during solution generation
- Reject invalid moves before adding to candidates
- Pros: More efficient, fewer invalid solutions
- Cons: Requires async validation in solver

#### Option B: Post-Validation (Simpler)
- Generate all solutions first
- Validate after building proposals
- Reject invalid proposals
- Pros: Simpler, doesn't require async in solver
- Cons: May generate many invalid solutions

**Recommendation**: Start with Option B (post-validation) for simplicity, then optimize to Option A if needed.

### Phase 7: Edge Cases

1. **Participant Not Found**: If a participant email doesn't exist or calendar is inaccessible
   - **Action**: Reject the move, log warning

2. **Partial Calendar Data**: If we can only fetch some participants' calendars
   - **Action**: Reject moves involving participants we can't validate

3. **Recursive Moves**: If moving Event A requires moving Event B, and Event B has participants
   - **Action**: Validate all moves in the chain

4. **Timeframe Mismatch**: If new location is outside the original timeframe
   - **Action**: Extend timeframe or reject move

## Implementation Order

1. **Phase 1**: Store attendee information and track event participants
2. **Phase 2**: Enforce internal-only constraint
3. **Phase 5**: Add targeted calendar fetching for missing participants (PROACTIVE - fetch before validation)
4. **Phase 3**: Create validation function (assumes all data is already fetched)
5. **Phase 4**: Post-validation for all proposals (uses validation function from Phase 3)

**Note**: Phase 5 should come BEFORE Phase 3/4 because validation needs the calendar data to already be available. The validation function (Phase 3) should not do fetching - it should assume all data is already present (fetched proactively in Phase 5).

## Testing Strategy

1. **Unit Tests**: Test validation function with mock data
2. **Integration Tests**: Test with real calendar data
3. **Edge Cases**: Test with missing participants, fetch failures, etc.
4. **Performance**: Measure impact of additional validation and fetching

## Success Criteria

1. ✅ All suggested moves are validated for all participants
2. ✅ Only internal-only meetings are proposed for moving
3. ✅ Calendar data is fetched for missing participants when needed
4. ✅ Invalid moves are rejected from the solution set
5. ✅ Performance impact is acceptable (< 2x execution time)

