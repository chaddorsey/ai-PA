# Preference Handling: Avoid vs. Prefer

## Current Implementation

The system handles both **prefer** and **avoid** preferences using a consistent, symmetric pattern with proper weighting to ensure avoids take precedence over prefers.

## Preference Types Supported

### Request-Level Preferences (in `SchedulingProblem`)
- **`preferred_times`**: List of ISO 8601 UTC strings for preferred time slots
- **`preferred_days`**: List of day names (e.g., `['Monday', 'Tuesday']`)
- **`avoid_times`**: List of ISO 8601 UTC strings for times to avoid
- **`avoid_days`**: List of day names to avoid (e.g., `['Friday']`)

### Participant-Specific Preferences (in `ParticipantPreference`)
- **`preferred_times`**: Preferred time slots for this specific participant
- **`preferred_days`**: Preferred days for this specific participant
- **`avoid_times`**: Times to avoid for this specific participant
- **`avoid_days`**: Days to avoid for this specific participant

## Weighting Strategy

The system uses a **penalty/bonus model** where:

1. **Avoid preferences** apply **negative scores (penalties)**
2. **Preferred preferences** apply **positive scores (bonuses)**
3. **Avoid penalties are significantly larger** in magnitude than preferred bonuses, ensuring avoids always override prefers

### Scoring Magnitudes

**Avoid Penalties:**
- Request-level avoid: **-10.0** (highest penalty)
- Participant avoid: **-8.0 to -10.0** (scaled by 0.8, so -10.0 * 0.8 = -8.0)
- Time proximity: Penalty decreases with distance from avoided time (e.g., -8.0 within 30 min, -5.0 within 1 hour, -2.0 within 2 hours)
- Day matches: **-10.0** for exact day match

**Preferred Bonuses:**
- Participant preferred: **+1.5 to +2.0** (medium bonus)
  - Days: **+2.0** for exact day match
  - Times: **+2.0** within 30 min, **+1.5** within 1 hour, **+0.8** within 2 hours
- Request-level preferred: **+0.8 to +1.0** (lower bonus, scaled by 0.5)

### Weighting Ratio

The avoid penalties are **5-12x larger** than preferred bonuses:
- Avoid penalty range: **-2.0 to -10.0**
- Preferred bonus range: **+0.8 to +2.0**
- Ratio: **Avoid penalties are 5-12x stronger**

This ensures that:
- A slot matching both a prefer and an avoid will have a **net negative score** (avoid wins)
- Avoid preferences can never be outweighed by preferred preferences
- The system will prefer slots that don't violate avoids, even if they don't match prefers

## Scoring Layer Order

The `compute_participant_preference_score()` function applies preferences in this order:

1. **Request-level avoid preferences** (highest penalty: -10.0)
   - Applied first, so they have the strongest effect
   
2. **Participant avoid preferences** (medium penalty: -8.0 to -10.0)
   - Slightly less than request-level (scaled by 0.8)
   
3. **Participant preferred preferences** (medium bonus: +1.5 to +2.0)
   - Applied after avoids, so they can't override avoid penalties
   
4. **Request-level preferred preferences** (lower bonus: +0.8 to +1.0)
   - Lowest weight (scaled by 0.5), applied last

## Example Scoring Scenarios

### Scenario 1: Slot matches both prefer and avoid
- Slot: Tuesday at 10:00 AM
- Request-level avoid: `['Tuesday']` → **-10.0 penalty**
- Request-level prefer: `['Tuesday']` → **+1.0 bonus** (scaled by 0.5)
- **Net score: -9.0** → Avoid wins, slot is penalized

### Scenario 2: Slot matches prefer but not avoid
- Slot: Monday at 9:00 AM
- Request-level avoid: `['Friday']` → **0.0** (no match)
- Request-level prefer: `['Monday']` → **+1.0 bonus**
- **Net score: +1.0** → Slot is preferred

### Scenario 3: Slot matches avoid but not prefer
- Slot: Friday at 2:00 PM
- Request-level avoid: `['Friday']` → **-10.0 penalty**
- Request-level prefer: `['Monday']` → **0.0** (no match)
- **Net score: -10.0** → Slot is strongly penalized

### Scenario 4: Slot matches neither
- Slot: Wednesday at 3:00 PM
- Request-level avoid: `['Friday']` → **0.0**
- Request-level prefer: `['Monday']` → **0.0**
- **Net score: 0.0** → Neutral

### Scenario 5: Participant-specific preferences
- Slot: Tuesday at 10:00 AM
- Participant (cdorsey) prefer: `['Tuesday']` → **+2.0 bonus**
- Participant (danielle) avoid: `['Tuesday']` → **-8.0 penalty** (scaled by 0.8)
- Request-level prefer: `['Monday']` → **0.0**
- **Aggregate score (cdorsey 2x weight)**: `(+2.0 * 2.0) + (-8.0 * 1.0) = -4.0` → Overall negative, avoid wins

## Integration in Proposal Sorting

Preference scores are integrated into proposal sorting as a **tie-breaker** after free-block scores:

```
Sorting priority (for zero-conflict proposals):
1. Category (zero-conflict always first)
2. Free-block score (higher is better) - cdorsey calendar optimization
3. Preference score (higher is better) - breaks ties when free-block scores are equal
4. Priority score (fallback)
5. Time (earlier preferred)
```

For proposals with moves/overrides:
```
Sorting priority:
1. Free-block score (primary)
2. Preference score (tie-breaker)
3. Category (single-move vs solo-override)
4. Priority score
5. Time
```

## Extracting Preferences from Utterance

DSPy extraction handles both prefer and avoid patterns:

**Prefer patterns:**
- "Find a meeting on Tuesday morning"
- "I prefer mornings"
- "Danielle likes afternoons"
- "Schedule it for Monday or Wednesday"

**Avoid patterns:**
- "Avoid Friday"
- "Not on Monday"
- "Don't schedule on weekends"
- "Chad wants to avoid afternoons"

## Standing Preferences from Context

Standing preferences in `context_json` follow the same pattern:

```json
{
  "participants": [
    {
      "id": "cdorsey@concord.org",
      "preferences": {
        "preferred_times": ["09:00-11:00"],  // Morning preference
        "preferred_days": ["Monday", "Tuesday"],
        "avoid_times": ["12:00-13:00"],      // Lunch hour
        "avoid_days": ["Friday"]              // Avoid Fridays
      }
    }
  ]
}
```

These are merged with utterance-extracted preferences, with utterance preferences taking precedence if there are conflicts.

## Summary

**Preferred preferences are fully implemented** using the same symmetric pattern as avoid preferences:
- Same structure (times and days at request and participant levels)
- Same extraction mechanism (DSPy)
- Same integration points (preference scorer, proposal sorting)
- Proper weighting (avoid penalties 5-12x stronger than preferred bonuses)

The system ensures that **avoids always take precedence over prefers** through the magnitude difference in penalties vs. bonuses, and the layering order in the scoring function.

