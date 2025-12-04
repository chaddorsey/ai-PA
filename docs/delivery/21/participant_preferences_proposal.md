# Participant Preferences System - Design Proposal

## Current State

The system currently supports:
- **Request-level preferences**: `preferred_times` and `preferred_days` in `SchedulingProblem`
- **Preference scoring**: Basic scoring in `_compute_preference_score()` based on proximity to preferred times/days
- **DSPy extraction**: Can extract preferred times/days from utterance
- **ASP encoding**: Preference violations penalized in soft constraints

## Missing Capabilities

1. **Participant-specific preferences**: Preferences that apply to individual participants (not just the overall request)
2. **Avoid preferences**: Preferences to avoid certain days/times/categories
3. **Pre-recorded/standing preferences**: Preferences stored per participant in `context_json`
4. **Preference layering**: cdorsey schedule preferences should take precedence in ties
5. **Flexibility markers**: Extracting "flexible" or "should be avoided" language from utterance

## Proposed Design

### 1. Schema Extensions

#### Update `SchedulingProblem` schema:
```python
class ParticipantPreference(BaseModel):
    """Preferences specific to a participant."""
    participant_id: str
    preferred_times: Optional[List[str]] = None
    preferred_days: Optional[List[str]] = None
    avoid_times: Optional[List[str]] = None  # Times to avoid
    avoid_days: Optional[List[str]] = None  # Days to avoid
    avoid_categories: Optional[List[str]] = None  # Event categories to avoid (e.g., "lunch", "meetings")
    flexibility_notes: Optional[str] = None  # Notes about flexibility (e.g., "my meetings are flexible")

class SchedulingProblem(BaseModel):
    # ... existing fields ...
    participant_preferences: Optional[List[ParticipantPreference]] = None  # NEW
    avoid_times: Optional[List[str]] = None  # NEW: Request-level avoid preferences
    avoid_days: Optional[List[str]] = None  # NEW: Request-level avoid preferences
```

#### Update `ContextJSON` to support standing preferences:
```python
# In context_json, each participant can have:
{
    "participants": [
        {
            "id": "cdorsey@concord.org",
            "email": "cdorsey@concord.org",
            "work_hours": "M-F 09:00-17:00",
            "preferences": {  # NEW
                "preferred_times": ["09:00-11:00"],  # Morning preference
                "avoid_days": ["Friday"],  # Avoid Fridays
                "flexibility": "meetings marked flexible can be moved"
            }
        }
    ]
}
```

### 2. DSPy Extraction Enhancements

Update the `ExtractSchedulingRequest` signature to extract participant preferences:

```python
utterance: str = dspy.InputField(
    desc="Natural language scheduling request. Extract participant preferences: "
         "- If utterance mentions 'X prefers mornings' or 'X likes Tuesday', extract as participant preference. "
         "- If utterance mentions 'avoid Friday' or 'not on Monday', extract as avoid preference. "
         "- If utterance mentions 'flexible meetings' or 'moveable events', extract as flexibility notes. "
         "... (existing description) ..."
)

problem_json: str = dspy.OutputField(
    desc="Valid JSON object matching SchedulingProblem schema. NEW fields: "
         "- participant_preferences: Array of {participant_id, preferred_times, preferred_days, avoid_times, avoid_days, flexibility_notes} "
         "- avoid_times: Array of ISO 8601 UTC strings for times to avoid "
         "- avoid_days: Array of day names to avoid (e.g., ['Friday']) "
         "... (existing description) ..."
)
```

### 3. Enhanced Preference Scoring

Create a new module `preference_scorer.py`:

```python
def compute_participant_preference_score(
    slot: int,
    participant_id: str,
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]],
    slot_indexer: SlotIndexer
) -> float:
    """
    Compute preference score for a specific participant at a given slot.
    
    Returns:
        Score where:
        - Positive = preferred (higher is better)
        - Negative = avoided (more negative = worse)
        - 0 = neutral
    
    Layering:
        1. Request-level avoid preferences (highest penalty)
        2. Participant avoid preferences (medium penalty)
        3. Participant preferred preferences (medium bonus)
        4. Request-level preferred preferences (lower bonus)
    """
    score = 0.0
    slot_dt = slot_indexer.slot_to_datetime(slot)
    if not slot_dt:
        return 0.0
    
    # 1. Check request-level avoid preferences (highest penalty)
    if scheduling_problem.avoid_times:
        # Penalty for matching avoid times
        ...
    
    if scheduling_problem.avoid_days:
        # Penalty for matching avoid days
        ...
    
    # 2. Check participant avoid preferences
    if scheduling_problem.participant_preferences:
        for pref in scheduling_problem.participant_preferences:
            if pref.participant_id == participant_id:
                # Apply avoid preferences
                ...
    
    # 3. Check participant preferred preferences
    # 4. Check request-level preferred preferences
    
    return score


def compute_aggregate_preference_score(
    slot: int,
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]],
    slot_indexer: SlotIndexer,
    requester_id: Optional[str] = None
) -> float:
    """
    Compute aggregate preference score across all participants.
    
    Returns:
        Weighted score where:
        - cdorsey@concord.org preferences have 2x weight (if requester)
        - Other participant preferences have 1x weight
        - In ties, requester preferences break the tie
    """
    total_score = 0.0
    requester_weight = 2.0  # cdorsey preferences take precedence
    
    for participant_id in scheduling_problem.participants:
        participant_score = compute_participant_preference_score(
            slot, participant_id, scheduling_problem, context_json, slot_indexer
        )
        
        # Apply weight: requester gets 2x, others get 1x
        weight = requester_weight if participant_id == requester_id else 1.0
        total_score += participant_score * weight
    
    return total_score
```

### 4. Integration Points

#### Update `python_solver.py`:
```python
def _compute_preference_score(
    slot: int,
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None,  # ADD THIS
    requester_id: Optional[str] = None  # ADD THIS
) -> float:
    """Compute preference score with participant preferences."""
    from .preference_scorer import compute_aggregate_preference_score
    return compute_aggregate_preference_score(
        slot, scheduling_problem, context_json, slot_indexer, requester_id
    )
```

#### Update proposal sorting in `orchestrate_scheduling.py`:
After free-block scores are calculated, apply preference scores as a tie-breaker:
```python
# Sort proposals:
# 1. Category (zero-conflict > single-move > solo-override)
# 2. Free-block score (for cdorsey)
# 3. Aggregate preference score (as tie-breaker)
# 4. Priority score (fallback)
```

### 5. Standing Preferences from Context

When extracting from `context_json`, merge standing preferences:

```python
def merge_standing_preferences(
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]]
) -> SchedulingProblem:
    """
    Merge standing preferences from context_json into scheduling_problem.
    
    Standing preferences in context_json.participants[].preferences are merged
    with preferences extracted from utterance. Utterance preferences take precedence
    if there are conflicts.
    """
    if not context_json or "participants" not in context_json:
        return scheduling_problem
    
    # Initialize participant_preferences if needed
    if scheduling_problem.participant_preferences is None:
        scheduling_problem.participant_preferences = []
    
    for participant in context_json["participants"]:
        participant_id = participant.get("id")
        if not participant_id:
            continue
        
        prefs = participant.get("preferences", {})
        if not prefs:
            continue
        
        # Find or create participant preference
        existing_pref = next(
            (p for p in scheduling_problem.participant_preferences if p.participant_id == participant_id),
            None
        )
        
        if existing_pref is None:
            existing_pref = ParticipantPreference(participant_id=participant_id)
            scheduling_problem.participant_preferences.append(existing_pref)
        
        # Merge preferences (utterance takes precedence, so only fill if missing)
        if not existing_pref.preferred_times and prefs.get("preferred_times"):
            existing_pref.preferred_times = prefs["preferred_times"]
        
        # ... merge other preference fields ...
    
    return scheduling_problem
```

### 6. Preference Weighting Strategy

**Priority Order (applied as multipliers/penalties)**:
1. **cdorsey@concord.org preferences**: 2.0x weight (if requester)
2. **Other participant preferences**: 1.0x weight
3. **Request-level preferences**: 0.5x weight (less important than participant-specific)

**Scoring Range**:
- **Avoid preferences**: -10.0 to -1.0 (penalty)
- **Preferred preferences**: +0.5 to +2.0 (bonus)
- **cdorsey preferences**: Applied at 2x multiplier

**Tie-breaking**: When free-block scores are equal, preference scores break ties. cdorsey preferences still have 2x weight in ties.

## Implementation Checklist

- [ ] Update `schemas.py` with `ParticipantPreference` and new fields
- [ ] Create `preference_scorer.py` module
- [ ] Update `dspy_extraction.py` to extract participant preferences
- [ ] Update `python_solver.py` to use enhanced preference scoring
- [ ] Add preference merging from `context_json`
- [ ] Update proposal sorting to include preference scores
- [ ] Add tests for preference scoring
- [ ] Update documentation

## Example Usage

```python
context_json = {
    "participants": [
        {
            "id": "cdorsey@concord.org",
            "preferences": {
                "preferred_times": ["09:00-11:00"],
                "avoid_days": ["Friday"]
            }
        },
        {
            "id": "danielle@concord.org",
            "preferences": {
                "avoid_days": ["Monday"]
            }
        }
    ]
}

utterance = "Find 45 minutes with Danielle on Tuesday morning. Avoid Friday."
# DSPy extracts:
# - participant_preferences: [
#     {participant_id: "danielle@concord.org", preferred_days: ["Tuesday"], preferred_times: ["morning"]}
#   ]
# - avoid_days: ["Friday"] (request-level)
# - Merges with standing preferences from context_json
```

