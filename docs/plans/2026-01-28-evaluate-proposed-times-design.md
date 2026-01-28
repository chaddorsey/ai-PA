# Evaluate Proposed Times - Design Document

**Date:** 2026-01-28
**Status:** Draft
**Author:** Chad + Claude

## Overview

A new Letta tool to evaluate externally-proposed meeting time windows against internal participants' calendars. This is the **inverse** of the scheduling orchestrator:

| Tool | Input | Output |
|------|-------|--------|
| `Find_Shared_Meeting_Slots` | "Find me a time" | Searches calendars, proposes slots |
| `Evaluate_Proposed_Times` | "Do these times work?" | Evaluates given windows, returns viable slots |

**Use Case:** External party proposes available time windows → evaluate against internal participants' calendars → return viable specific slots ranked by preference.

---

## Architecture

### High-Level Flow

```
Input (natural language or structured)
    ↓
Parse proposed windows → List of (date, start_time, end_time, exclusions)
    ↓
Fetch calendars for all participants via MCP
    ↓
For each proposed window:
    - Normalize to 15-minute slot grid
    - Check availability using _find_free_slots()
    - Identify concrete available slots of requested duration
    ↓
Rank all found slots:
    1. Fewest conflicts (clean > solo-adjust > multi-adjust)
    2. Time-of-day preferences (if known)
    3. Sooner dates preferred
    ↓
Return categorized, ranked results
```

### Component Reuse from Orchestrator

| Component | Source | Usage |
|-----------|--------|-------|
| `_find_free_slots()` | `fact_generator.py` | Core availability checking |
| `normalizer.py` | Full module | Event → slot grid conversion |
| `mcp_client.py` | Full module | Calendar data fetching |
| DSPy extraction | Adapt from orchestrator | Parse natural language windows |

### New Components to Build

1. **Window Parser** - Parse "anytime but 3:30-4:30pm" into concrete ranges
2. **Slot Evaluator** - Apply duration requirement, find concrete slots
3. **Ranking Engine** - Score and sort by conflict/preference/date
4. **Result Formatter** - Output human-readable ranked list

### File Structure

```
letta/scheduling_orchestrator/
├── evaluate_proposed_times.py   # NEW: Main entry point
├── window_parser.py             # NEW: NL → ProposedWindow
├── slot_evaluator.py            # NEW: Window → EvaluatedSlots
├── ranking.py                   # NEW: Scoring and sorting
│
├── fact_generator.py            # REUSE: _find_free_slots()
├── normalizer.py                # REUSE: Calendar normalization
├── mcp_client.py                # REUSE: Calendar fetching
└── formatting.py                # REUSE: Display helpers (partial)
```

---

## Input/Output Specification

### Input Format (Natural Language - Primary)

```
"Which of these times works for a 30-minute meeting with Cynthia and Chad?
01/29 (Thu), anytime but 3:30-4:30pm
01/30 (Fri), anytime until 4pm
02/02 (Mon), after 1pm"
```

### Parsed Representation

```python
@dataclass
class ProposedWindow:
    date: date                    # 2026-01-29
    start_time: time              # 00:00 (or explicit start)
    end_time: time                # 23:59 (or explicit end)
    exclusions: List[TimeRange]   # [(15:30, 16:30)]
    raw_text: str                 # "anytime but 3:30-4:30pm"

@dataclass
class EvaluationRequest:
    windows: List[ProposedWindow]
    participants: List[str]       # ["cynthia@...", "chad@..."]
    duration_minutes: int         # 30
    requester_id: str             # Who's asking
```

### Output Structure

```python
@dataclass
class ConflictInfo:
    participant: str              # Who has the conflict
    event_title: str              # What event
    event_time: str               # When
    event_property: str           # locked/protected/flexible/transparent

@dataclass
class EvaluatedSlot:
    start: datetime
    end: datetime
    category: str                 # "clean" | "solo_adjust" | "multi_adjust"
    conflicts: List[ConflictInfo] # What needs moving (if any)
    score: float                  # For ranking

@dataclass
class EvaluationResult:
    clean_slots: List[EvaluatedSlot]        # No conflicts
    solo_adjust_slots: List[EvaluatedSlot]  # One person adjusts
    multi_adjust_slots: List[EvaluatedSlot] # Multiple adjustments
    no_availability_windows: List[str]      # Windows with zero options
```

### User-Facing Output Example

```
✅ Clean options (no conflicts):
  • Thu 1/29, 10:00-10:30am
  • Thu 1/29, 2:00-2:30pm
  • Fri 1/30, 9:00-9:30am

⚠️ Options requiring adjustment:
  • Mon 2/2, 2:00-2:30pm — overlaps Chad's "Team Sync" (protected)

❌ No availability:
  • Fri 1/30 after 2pm — both participants have locked events
```

---

## Window Parser (Natural Language)

### Supported Patterns

| Input Pattern | Parsed As |
|---------------|-----------|
| "anytime" | 08:00 - 18:00 (business hours default) |
| "anytime but 3:30-4:30pm" | 08:00-15:30, 16:30-18:00 |
| "until 4pm" | 08:00 - 16:00 |
| "after 1pm" | 13:00 - 18:00 |
| "morning only" | 08:00 - 12:00 |
| "afternoon" | 12:00 - 18:00 |
| "between 10am and 2pm" | 10:00 - 14:00 |
| "10am-2pm except noon-1pm" | 10:00-12:00, 13:00-14:00 |

### DSPy Signature

```python
class ExtractTimeWindows(dspy.Signature):
    """Extract proposed meeting time windows from natural language."""

    text: str = dspy.InputField(desc="User's proposed availability text")
    today_date: str = dspy.InputField(desc="Reference date for parsing (YYYY-MM-DD)")

    windows: List[dict] = dspy.OutputField(desc="""
        List of windows, each with:
        - date: "YYYY-MM-DD"
        - start_time: "HH:MM" (24h)
        - end_time: "HH:MM" (24h)
        - exclusions: [{"start": "HH:MM", "end": "HH:MM"}, ...]
        - raw_text: original phrase
    """)
```

### Fallback Behavior

If DSPy extraction fails or confidence is low:
1. Return structured error asking user to clarify
2. Never guess — ambiguity should be surfaced

---

## Slot Evaluator (Core Logic)

### Algorithm

```python
def evaluate_window(
    window: ProposedWindow,
    participants: List[str],
    duration_minutes: int,
    calendar_data: Dict[str, NormalizedCalendar]
) -> List[EvaluatedSlot]:
    """
    1. Convert window to 15-minute slot grid (reuse normalizer)
    2. Apply exclusions to create valid time ranges
    3. For each participant, get busy slots from calendar_data
    4. Slide a duration-sized window across the grid
    5. For each position, check: all participants free? some blocked?
    6. Categorize and return matching slots
    """
```

### Event Property Handling

The evaluator respects all event properties from the orchestrator:

| Property | Behavior | Category if Overlapped |
|----------|----------|------------------------|
| **Locked** | Hard blocker | Slot not viable |
| **Protected** | Soft blocker | `solo_adjust` |
| **Flexible** | Can be moved | `solo_adjust` or `multi_adjust` |
| **Transparent** | Treated as free | `clean` (noted in output) |

### Categorization Logic

| Scenario | Category | Score Boost |
|----------|----------|-------------|
| All participants free | `clean` | +100 |
| One person has flexible/protected event | `solo_adjust` | +50 |
| Multiple people have conflicts | `multi_adjust` | +0 |
| Any participant has locked event | Skip (not viable) | — |

---

## Ranking Engine

### Scoring Formula

```python
def score_slot(slot: EvaluatedSlot, preferences: Optional[UserPreferences]) -> float:
    score = 0.0

    # 1. Category (highest weight)
    CATEGORY_SCORES = {
        "clean": 100,
        "solo_adjust": 50,
        "multi_adjust": 0
    }
    score += CATEGORY_SCORES[slot.category]

    # 2. Time-of-day preference (if known)
    if preferences and preferences.preferred_hours:
        hour = slot.start.hour
        if preferences.preferred_hours[0] <= hour <= preferences.preferred_hours[1]:
            score += 20

    # 3. Sooner is better (decay over days)
    days_out = (slot.start.date() - date.today()).days
    score -= days_out * 2  # Slight penalty for later dates

    return score
```

### Sorting Order

1. **Category**: clean → solo_adjust → multi_adjust
2. **Within category**: By score (preferences, then date)
3. **Tie-breaker**: Earlier time on same day

---

## Error Handling

| Error Condition | Response |
|-----------------|----------|
| NL parsing fails | Return structured error, ask user to clarify format |
| Calendar fetch fails | Return error specifying which participant failed |
| No slots in any window | Return "None of these times work" with reason per window |
| Participant not found | Return error with unknown participant name |

---

## Letta Tool Registration

```python
# Tool name: Evaluate_Proposed_Times
# Registered alongside existing Find_Shared_Meeting_Slots
# Uses same agent, same MCP access, different entry point

def Evaluate_Proposed_Times(
    proposed_times: str,           # Natural language or structured
    participants: str,             # Comma-separated names/emails
    duration_minutes: Optional[int] = 30,
    timezone: Optional[str] = "America/New_York"
) -> Dict[str, Any]:
    """
    Evaluate externally-proposed meeting time windows against participants' calendars.

    Args:
        proposed_times: Time windows to evaluate (e.g., "01/29 anytime but 3-4pm, 01/30 until 4pm")
        participants: Meeting participants (e.g., "Chad, Cynthia")
        duration_minutes: Meeting length (default 30)
        timezone: Timezone for interpretation (default America/New_York)

    Returns:
        Dictionary with clean_slots, adjustment_slots, and no_availability sections
    """
```

---

## Success Criteria

1. **Correct parsing**: "anytime but 3:30-4:30pm" correctly excludes that window
2. **Accurate evaluation**: Slots marked `clean` have no actual conflicts
3. **Proper ranking**: Clean options appear before adjustment options
4. **Event property respect**: Locked events block, protected/flexible allow adjustment
5. **Clear output**: User can immediately identify best options

---

## Future Enhancements (Out of Scope)

- Interactive Slack buttons (like orchestrator proposals)
- Automatic response drafting to external party
- Learning user time-of-day preferences over time
- Integration with Calendly-style external availability

---

## Related Documents

- Scheduling Orchestrator: `letta/scheduling_orchestrator/orchestrate_scheduling.py`
- Fact Generator (free slots): `letta/scheduling_orchestrator/fact_generator.py`
- Normalizer: `letta/scheduling_orchestrator/normalizer.py`
