# Orchestrator Output Analysis

## Current Behavior

### What Gets Returned
**The orchestrator currently returns ONLY 1 proposal** (the best/optimal slot).

```json
{
  "status": "ok",
  "proposals": [
    {
      "title": "Meeting",
      "participants": ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
      "start_utc": "2025-12-08T04:30:00+00:00",
      "end_utc": "2025-12-08T05:15:00+00:00",
      "moved_events": [],
      "objective_scores": {
        "moved_minutes": 0,
        "focus_block_bonus": 43,
        "preference_penalty": 0,
        "protected_events_moved": 0
      }
    }
  ],
  "explanation": "Found optimal meeting time: 2025-12-08 04:30 UTC. Creates 43 minutes of focus time."
}
```

### Available Options (Not Returned)

According to debug info for the test case:
- **140 free slots found** (meeting slots where all participants are free)
- **192 total slots considered** (after horizon reduction)
- **Free slots ratio: 72.9%** (good availability)

**The orchestrator ranks all 140 free slots but only returns the top 1.**

## Code Flow

### 1. Finding Free Slots
`python_solver.py` → `find_optimal_slot()`:
- Finds all free slots where all participants are available
- Filters by time window constraints
- Filters by locked events

### 2. Ranking All Slots
`python_solver.py` → `_rank_slots()`:
- **Ranks ALL free slots** by score
- Returns: `List[Tuple[int, float]]` sorted by score (highest first)
- Score components:
  - Disruption (minimize): `-disruption_score * 10.0`
  - Focus block bonus (maximize): `focus_bonus * 5.0`
  - Preference score: `preference_score * 2.0`

### 3. Selecting Only the Best
`python_solver.py` → `find_optimal_slot()` (line 111):
```python
if ranked:
    best_slot, best_score = ranked[0]  # ← Only takes the FIRST (best) slot
    return {
        "start_slot": best_slot,
        "score": best_score,
        ...
    }
```

### 4. Building Single Proposal
`orchestrate_scheduling.py` → (line 753):
```python
proposals=[proposal]  # ← Only one proposal in the list
```

## Why Only One?

The current design prioritizes:
1. **Simplicity**: Returns the best option immediately
2. **User Experience**: No decision paralysis from too many options
3. **Consistency**: Matches the "optimal" solver pattern

However, the **utterance says "options" (plural)**, suggesting users may want multiple choices.

## Potential Improvements

### Option 1: Return Top N Proposals
- Return the top 3-5 ranked slots
- Give users multiple options to choose from
- Useful when scheduling preferences are flexible

### Option 2: Return Diverse Options
- Not just top-scoring, but spread across:
  - Different days (early week vs late week)
  - Different times (morning vs afternoon)
  - Different strategies (free slot vs moved events)
- Ensures variety in the options presented

### Option 3: Make It Configurable
- Add a parameter: `max_proposals: int = 1`
- Allow context to specify desired number of options
- Default to 1 for backward compatibility

### Option 4: Return All Ranked Options
- Return all 140 slots ranked (could be too many)
- Require client to filter/paginate
- Best for advanced use cases

## Test Data Results

**Test Request**: "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 1 and 12."

**What's Available**:
- 140 free slots found
- Spread across 12 days (Dec 1-12)
- Multiple times per day
- Work hours: 9-5 Eastern (default)

**What's Returned**:
- 1 proposal: December 8, 2025 at 12:30 AM UTC (Nov 7 at 11:30 PM EST)
  - Wait, this looks wrong - it's outside work hours!
  - Actually, wait - let me check the conversion...

Actually, `2025-12-08T04:30:00+00:00` UTC = `2025-12-08T00:30:00-04:00` EDT = **12:30 AM Eastern** - this is outside 9-5 work hours!

**This suggests the work hours fix may not be working correctly in all cases, or there's a timezone conversion issue.**

## Recommendations

1. **Investigate the timezone issue** - why is a slot outside work hours being returned?
2. **Consider returning multiple proposals** (top 3-5) for better user experience
3. **Add diversity filtering** to ensure options span different days/times
4. **Make max_proposals configurable** via context parameter

