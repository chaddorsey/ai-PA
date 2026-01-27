# Scheduling Orchestrator Optimization Review

**Started:** 2026-01-26
**Status:** In Progress
**Tool:** `letta/scheduling_orchestrator/orchestrate_scheduling.py`

---

## Overview

This document tracks findings and recommendations from a comprehensive review of the `orchestrate_scheduling` tool for optimization and potential refactoring.

---

## Issue #1: Validation Calendar Data Leaking into User Output

### Problem Description

When the tool generates scheduling proposals, it performs "Proactive Calendar Fetching" to validate that moved events don't conflict with all their attendees. However, this validation data is incorrectly appearing in user-facing output.

**Example:** User requests a meeting with 4 participants (clore, cmcintyre, ddamelin, cdorsey). The output shows events from kbrown, dkehoe, and sbrau - people who were NOT in the participant list but are attendees of events that might be moved.

### Root Cause

**Data Flow:**
1. `original_normalized_data` is created with only the requested participants' calendars (line 2716-2720)
2. Proposals are generated suggesting event moves
3. **Proactive Calendar Fetching** (lines 4068-4253) identifies attendees of moved events who aren't in the original participant list
4. Their calendars are fetched and **merged INTO** `original_normalized_data`
5. Validation uses this merged data (legitimate)
6. **BUG:** Formatting also uses this merged data via `formatting_normalized_data = original_normalized_data` (line 4816)
7. `_find_all_overlapping_solo_events()` in formatting.py iterates over ALL events in `event_slots_map`, including validation-only calendars

**Key Files:**
- `orchestrate_scheduling.py:4068-4253` - Proactive fetching and merge
- `orchestrate_scheduling.py:4816` - `formatting_normalized_data = original_normalized_data`
- `formatting.py:803-900` - `_find_all_overlapping_solo_events()` iterates all events

### Chosen Fix: Keep Validation Data Completely Separate

**Approach:** Don't merge validation calendars into `original_normalized_data`. Keep them in a separate structure and pass explicitly only to functions that need them for validation.

**Rationale for this approach:**
1. **Multiple leak points exist** - We identified 2 confirmed leak points in user-facing output. A filtering approach would require changes in each location, whereas keeping data separate fixes all leak points automatically.
2. **Architectural clarity** - `original_normalized_data` becomes immutable after creation, making data flow easier to reason about and test.
3. **Future-proof** - Any new output code cannot accidentally leak validation data because it physically isn't present in the data structures passed to formatting.
4. **Validation is isolated** - Only `validate_moved_event_dict()` truly needs the validation calendars; it's appropriate for it to receive them explicitly rather than having them globally merged.

---

## Leak Point Analysis

**Purpose:** Identify all places where validation calendar data could leak into user-facing output.

### Confirmed Leak Points

| Location | Function | Status | Impact |
|----------|----------|--------|--------|
| `formatting.py:853` | `_find_all_overlapping_solo_events()` | **CONFIRMED** | Shows validation calendars' solo events as "potential overrides" in verbatim output |
| `agent_data_builder.py:107` | `build_event_registry()` | **CONFIRMED** | Iterates `event_slots_map` to find solo events for override proposals; could include events from validation calendars in `event_registry` |

### Not Affected

| Location | Function | Why Safe |
|----------|----------|----------|
| `formatting.py:687` | `_find_overridden_solo_event()` | **Dead code** - defined but never called |
| `formatting.py:615-617` | Move group formatting | Uses `event_metadata` but only for events from `prop.moved_events`, which are pre-filtered to internal events of original participants |
| `formatting.py:378-397` | Participant display | Uses `original_participants` from `context_json`, not from `normalized_data` |

### Analysis Summary

**Finding:** Two confirmed leak points, both involving iteration over `event_slots_map` to find solo events.

**Impact:** Multiple leak points strongly favor keeping validation data separate rather than filtering at each output location. The chosen fix (separate validation data) addresses both leak points automatically since validation calendars are never merged into the main data structure.

### Files That Use `event_slots_map`

| File | Purpose | User-Facing? |
|------|---------|--------------|
| `normalizer.py` | Creates the map | No - source |
| `formatting.py` | Solo event display | **Yes - 2 leak points** |
| `agent_data_builder.py` | Event registry | **Yes - 1 leak point** |
| `clingo_wrapper.py` | ASP solver | No - internal |
| `fact_generator.py` | ASP facts | No - internal |
| `free_block_scorer.py` | Scoring | No - internal |
| `horizon_reducer.py` | Optimization | No - internal |
| `move_validator.py` | Validation | No - internal (uses merged data legitimately) |
| `python_solver.py` | Python solver | No - internal |
| `orchestrate_scheduling.py` | Main orchestration | No - internal |

---

## Implementation Plan

### Overview

The fix involves isolating validation calendar data so it never contaminates the main `original_normalized_data` structure. This requires changes in 3 locations.

### Files to Modify

| File | Location | Change |
|------|----------|--------|
| `orchestrate_scheduling.py` | Lines 4068-4253 | Store proactively-fetched calendars separately instead of merging |
| `orchestrate_scheduling.py` | Lines ~4456 | Pass validation calendars explicitly to `validate_moved_event_dict()` |
| `move_validator.py` | `validate_moved_event_dict()` | Accept new `additional_calendars` parameter, merge internally for conflict checking |

### Detailed Changes

#### 1. Modify Proactive Calendar Fetching (orchestrate_scheduling.py:4068-4253)

**Current behavior:** Fetched calendars are merged into `original_normalized_data` via dictionary update operations.

**New behavior:** Create a separate `validation_normalized_data` dict to hold the additional calendars:

```python
# At the start of proactive fetching section (~line 4068)
validation_normalized_data = {
    "event_slots_map": {},
    "event_metadata": {},
    "participant_info": {},
    # ... other required keys
}

# When processing fetched calendars, add to validation_normalized_data instead of original_normalized_data
for participant_id, calendar_data in fetched_calendars.items():
    validation_normalized_data["event_slots_map"].update(...)
    validation_normalized_data["event_metadata"].update(...)
```

#### 2. Pass Validation Data Explicitly (orchestrate_scheduling.py:~4456)

**Current call:**
```python
is_valid, error_msg = validate_moved_event_dict(
    moved_event_dict,
    original_normalized_data,
    slot_indexer,
    exclude_event_keys=all_moved_event_keys
)
```

**New call:**
```python
is_valid, error_msg = validate_moved_event_dict(
    moved_event_dict,
    original_normalized_data,
    slot_indexer,
    exclude_event_keys=all_moved_event_keys,
    additional_calendars=validation_normalized_data  # NEW
)
```

#### 3. Update validate_moved_event_dict() (move_validator.py)

**Current signature:**
```python
def validate_moved_event_dict(
    moved_event_dict: dict,
    normalized_data: dict,
    slot_indexer: SlotIndexer,
    exclude_event_keys: set = None
) -> tuple[bool, str]:
```

**New signature:**
```python
def validate_moved_event_dict(
    moved_event_dict: dict,
    normalized_data: dict,
    slot_indexer: SlotIndexer,
    exclude_event_keys: set = None,
    additional_calendars: dict = None  # NEW
) -> tuple[bool, str]:
```

**Implementation change:** At the start of the function, merge `additional_calendars` into a local working copy for conflict checking:

```python
# Create working copy with additional calendars merged in
working_data = normalized_data.copy()
if additional_calendars:
    for key in ["event_slots_map", "event_metadata", "participant_info"]:
        if key in additional_calendars and key in working_data:
            working_data[key] = {**working_data[key], **additional_calendars[key]}
# Use working_data for all conflict checks within this function
```

### No Changes Required

- **formatting.py** - Will automatically receive clean data since `original_normalized_data` is never polluted
- **agent_data_builder.py** - Same as above; `event_slots_map` will only contain original participants' events

---

## Architecture Overview

### 6-Phase Pipeline

The tool follows a multi-stage pipeline pattern:

| Phase | Purpose | Key Operations |
|-------|---------|----------------|
| **Phase 0** | Input Processing | Parse JSON inputs, detect rescheduling mode |
| **Phase 1** | Calendar Retrieval | MCP fetch via `Core_Event_Data` or accept pre-fetched events |
| **Phase 2** | NLP Extraction | DSPy converts utterance → `SchedulingProblem` |
| **Phase 3** | Normalization | Events mapped to 15-minute slot grid |
| **Phase 4** | Constraint Solving | Python solver (fast) → ASP solver (fallback) |
| **Phase 5** | Post-Processing | Move validation, free-block scoring, preference scoring |
| **Phase 6** | Output Generation | Dual-format: `user_display` + `agent_data` |

### Key Data Structures

- **`normalized_data`**: Contains `slot_indexer`, `busy_slots`, `work_hours_slots`, `event_protection`, `event_slots_map`, `event_metadata`
- **`SchedulingProblem`**: Extracted scheduling request (participants, duration, preferences, time windows)
- **`Proposal`**: Meeting proposal with start/end times, moved events, scores
- **`ResponseEnvelope`**: Complete response with status, proposals, user_display, agent_data

### External Dependencies

| Dependency | Purpose | Location |
|------------|---------|----------|
| n8n MCP Server | Calendar event fetching | `mcp_client.py` |
| DSPy + LLM | Natural language extraction | `dspy_extraction.py` |
| clingo ASP solver | Complex constraint solving (fallback) | `clingo_wrapper.py` |

---

## Reliability Issues

### Issue #2: Over-Broad Exception Handling

**Severity:** Medium
**Files:** Multiple (52+ instances across codebase)

The code uses `except Exception` extensively, masking bugs and making debugging difficult:

```python
# Example at orchestrate_scheduling.py line 1130
except Exception:
    pass  # Silently swallows ALL errors
```

**Impact:**
- Silent failures make debugging impossible
- Critical errors (`MemoryError`, `KeyboardInterrupt`) caught inappropriately
- No logging or error reporting in many catch blocks

**Recommendation:** Replace with specific exception types; add logging for unexpected errors.

---

### Issue #3: Timezone Edge Cases

**Severity:** Medium
**File:** `normalizer.py` lines 300-320

Work hours are converted from local timezone to UTC slot-by-slot. Events spanning midnight in one timezone may not be handled correctly.

**Edge case:** Participant work hours "M-F 09:00-17:00" in America/Los_Angeles. UTC time Monday 16:00 = Sunday 08:00 PST. The slot might be excluded because it's "Sunday" in local time.

**Additional issue:** Default work hours assume Eastern timezone (hardcoded `America/New_York` at line 287).

**Recommendation:** Centralize timezone handling in `slot_indexer.py`; add explicit timezone validation.

---

### Issue #4: Empty Calendar Handling

**Severity:** Medium
**File:** `orchestrate_scheduling.py` lines 790-850

When fetching calendars, empty results are stored but not validated:
- Participant with genuinely empty calendar (new user, vacation period)
- Tool treats this identically to a fetch failure
- Validation logic returns `"Participant calendar not available"` even for legitimately empty calendars

**Impact:** False negatives - valid time slots rejected.

**Recommendation:** Distinguish between "empty calendar" and "fetch failure" with explicit status tracking.

---

### Issue #5: Participant ID Case Sensitivity

**Severity:** Low
**Files:** `move_validator.py` lines 296-310, `orchestrate_scheduling.py` lines 2700+

Inconsistent case handling:
- `move_validator.py` uses case-insensitive fallback for participant lookups
- Event fetching uses exact string matching (case-sensitive)

**Impact:** Events fetched for `john@example.com` may fail validation looking for `John@example.com`.

**Recommendation:** Normalize participant IDs to lowercase at entry point.

---

### Issue #6: DSPy Extraction Robustness

**Severity:** Medium
**File:** `dspy_extraction.py` lines 131-150

- Function named `extract_with_fallback` but fallback only provides minimal defaults
- No regex-based extraction fallback when DSPy fails
- API key missing returns `None` without clear error

**Recommendation:** Implement robust regex-based fallback for common patterns when DSPy fails.

---

### Issue #7: Event Matching Ambiguity

**Severity:** Medium
**File:** `event_matcher.py`, `dspy_extraction.py`

- Date reference parsing returns `None` on failures without validation by callers
- Title vs. participant name confusion (LLM guidance only, no validation logic)
- "Meeting with Concord Audit Team" might extract as participants instead of title

**Recommendation:** Add post-processing validation to catch title/participant confusion.

---

### Issue #8: Validation Logic Gaps

**Severity:** Medium
**File:** `move_validator.py` lines 268-294, 369-374

**Moved event exclusion:**
- Assumes ASP solver "implicitly moved" flexible/protected events
- No verification that the ASP solver actually moved them

**Solo event detection:**
- Default `number_of_attendees=0` if metadata missing
- Multi-person meeting with missing metadata treated as solo

**Recommendation:** Add explicit verification of solver output; don't default missing metadata.

---

### Issue #9: Missing Participant Calendar Pre-fetch

**Severity:** Low
**File:** `orchestrate_scheduling.py` lines 4068-4255

Phase 5 fetches missing participant calendars **after** proposals generated but **before** validation:
- If `event_participants_map` is incomplete, calendars won't be fetched
- No retry logic when calendar fetching fails (logs warning, continues)
- Validation will fail but proposals still presented

**Recommendation:** Fetch all potential participants upfront; add retry logic.

---

### Issue #10: Data Mutation Throughout Execution

**Severity:** High
**File:** `orchestrate_scheduling.py` lines 2716-2720, 4218-4247

`normalized_data.copy()` is **shallow** - nested dictionaries are shared references. Mutations to nested structures affect both copies.

**Impact:**
- Debugging is difficult
- Side effects between solver phases
- Data leakage (Issue #1)

**Recommendation:** Use `copy.deepcopy()` or implement immutable data structures.

---

## Efficiency Issues

### Issue #11: Redundant DSPy Extraction

**Severity:** High
**Files:** `orchestrate_scheduling.py` lines ~374 and ~1172

DSPy extraction is called twice in some code paths:
1. Preview extraction to check if rescheduling (line 374)
2. Full extraction with same inputs (line 1172)

**Impact:** 2x LLM API cost, 2x latency (~500-2000ms each)

**Recommendation:** Cache `scheduling_problem_preview` and reuse.

---

### Issue #12: No Caching

**Severity:** High
**Files:** Throughout codebase

No caching is implemented for:
- DSPy LLM responses (identical utterances = new API call)
- MCP calendar data (refetching for retries/refinements)
- Work hours calculations (recalculated 3+ times per request)
- Event matching scores
- Free slot sets

**Estimated savings with caching:**
- DSPy: 500-2000ms, 1 LLM API call (20-30% hit rate)
- MCP: 200-1000ms per participant (40-60% hit rate)
- Work hours: 50-200ms per recalculation

**Recommendation:** Implement in-memory request caching; consider TTL-based cache for MCP responses.

---

### Issue #13: O(n²) Loops

**Severity:** Medium
**Files:** `event_matcher.py`, `orchestrate_scheduling.py`, `fact_generator.py`

**Event Matching Loop (event_matcher.py:872-893):**
- O(P × E × (T+D+N)) where P=participants, E=events, T/D/N=comparison fields
- Worst case: 10 participants × 100 events × 15 comparisons = **15,000 operations**

**Free Slot Calculation (fact_generator.py:51-130):**
- O(S × D × P) where S=slots, D=duration slots, P=participants
- Worst case: 2000 × 12 × 10 = **240,000 operations**

**Recommendation:** Index events by metadata for O(1) lookup; early exit from free slot search.

---

### Issue #14: Sequential API Calls

**Severity:** Medium
**File:** `orchestrate_scheduling.py` lines 661-778

- Event fetch by ID for rescheduling done sequentially
- Then participant calendars fetched separately
- Could batch into single parallel operation

**Recommendation:** Batch event + calendar fetches using `asyncio.gather()`.

---

### Issue #15: Missing Early Exit Opportunities

**Severity:** Medium
**Files:** `python_solver.py`, `orchestrate_scheduling.py`

- Free slot search scans ALL slots even after finding 100+ candidates
- Event matching scores ALL events even after perfect match
- ASP solver runs even if Python solver found optimal 0-move solutions

**Recommendation:** Exit after finding N high-quality candidates; skip ASP when Python found free slots.

---

### Issue #16: Repeated Work Hours Calculation

**Severity:** Medium
**File:** `orchestrate_scheduling.py` lines 2764, 2954, 3020

Work hours calculation repeated 3+ times in horizon reduction section.

**Recommendation:** Calculate once and cache per participant.

---

## Performance Profile (Estimated)

| Phase | Time (ms) | % | Primary Bottleneck |
|-------|-----------|---|-------------------|
| DSPy Extraction | 1000-4000 | 30-40% | LLM API latency, redundant calls |
| MCP Calendar Fetches | 800-3000 | 25-35% | Network I/O, sequential fetches |
| Event Matching | 200-1000 | 10-15% | O(P×E) loop, fuzzy matching |
| Normalization | 100-500 | 5-10% | Slot conversions, work hours calc |
| Python Solver | 100-800 | 5-15% | Free slot search |
| ASP Solver (if triggered) | 500-5000 | 0-40% | Grounding, solving |
| Response Formatting | 50-200 | 2-5% | Display generation |

**Total:** ~2.5-15 seconds (varies by complexity)

---

## Quick Wins (High ROI, Low Effort)

| Issue | Fix | Estimated Savings | Effort |
|-------|-----|-------------------|--------|
| #11 | Cache DSPy extraction result | 500-2000ms | ~5 lines |
| #16 | Cache work hours calculation | 100-400ms | ~10 lines |
| #15 | Early exit from free slot search | 50-300ms | ~5 lines |
| #15 | Skip ASP when Python found 0-move solutions | 500-5000ms | ~10 lines |

---

## Dead Code

- `_find_overridden_solo_event()` at formatting.py:687 is defined but never called
- Should be removed in cleanup

---

## Key Files Reference

### Tier 1: Must Read

| File | Purpose | Lines of Concern |
|------|---------|------------------|
| `orchestrate_scheduling.py` | Main orchestration | 69-500 (entry), 4068-4253 (proactive fetch), 4816 (data leakage) |
| `schemas.py` | Data models | All (18 classes) |
| `python_solver.py` | Primary solver | 23-200 (main logic) |

### Tier 2: Important

| File | Purpose | Lines of Concern |
|------|---------|------------------|
| `normalizer.py` | Event normalization | 74-250 (normalize_events), 300-320 (timezone) |
| `dspy_extraction.py` | NLP extraction | 66-110 (init), 114-200 (extraction) |
| `move_validator.py` | Validation | 168-386 (validate_proposal_meeting_time) |
| `mcp_client.py` | Calendar API | 115-200 (call_tool) |

### Tier 3: Reference

| File | Purpose |
|------|---------|
| `event_matcher.py` | Event matching for rescheduling |
| `formatting.py` | User output generation |
| `agent_data_builder.py` | Agent metadata |
| `fact_generator.py` | ASP facts generation |
| `clingo_wrapper.py` | ASP solver interface |

---

## Action Items

### Reliability Fixes
- [x] Complete leak point analysis (Issue #1)
- [x] Decide on fix approach → **Separate validation data chosen**
- [x] Implement fix for Issue #1 (validation data leakage) → **Commit 73a4230**
- [x] Issue #10: Use deep copy for normalized_data → **Commit 73a4230**
- [ ] Add regression tests for Issues #1 and #10
- [ ] Issue #2: Replace over-broad exception handling
- [ ] Issue #3: Fix timezone edge cases
- [ ] Issue #4: Distinguish empty calendar from fetch failure
- [ ] Issue #5: Normalize participant ID casing

### Efficiency Optimizations
- [x] Issue #11: Cache DSPy extraction (quick win) → **Commit 10f1a42**
- [ ] Issue #12: Implement request-level caching
- [ ] Issue #13: Index events for O(1) lookup
- [ ] Issue #15: Add early exit from free slot search (quick win)
- [x] Issue #15: Skip ASP when Python found free slots (quick win) → **Commit a210bec**
- [ ] Issue #16: Cache work hours calculation (quick win)

### Code Quality
- [ ] Remove dead code (`_find_overridden_solo_event`)
- [ ] Issue #6: Improve DSPy fallback robustness
- [ ] Issue #7: Add title/participant validation
- [ ] Issue #8: Verify solver output explicitly

---

## Change Log

| Date | Change |
|------|--------|
| 2026-01-26 | Initial document created, Issue #1 documented |
| 2026-01-26 | Completed leak point analysis: 2 confirmed leak points |
| 2026-01-26 | Finalized fix approach: separate validation data; added detailed implementation plan |
| 2026-01-26 | **Comprehensive codebase exploration completed**: Added architecture overview, 9 additional reliability issues (#2-#10), 6 efficiency issues (#11-#16), performance profile, quick wins table, and key files reference |
| 2026-01-26 | **Implemented Issues #1 and #10**: Validation data isolation (separate `validation_normalized_data` structure) and deep copy fix (commit 73a4230) |
| 2026-01-26 | **Implemented Issue #11**: Reuse DSPy extraction result instead of redundant LLM call (commit 10f1a42) |
| 2026-01-26 | **Implemented Issue #15**: Skip ASP solver when Python solver found free slots (commit a210bec) |
| 2026-01-26 | **Code review fixes**: Fixed additional shallow copy (line 3230), misleading warning, and logging prefix (commit 0b73327) |

---

## Session Summary

### Accomplished

| Issue | Description | Impact | Commit |
|-------|-------------|--------|--------|
| **#1** | Validation data isolation | Fixes validation calendars leaking to user output | 73a4230 |
| **#10** | Deep copy for normalized_data | Prevents shared reference bugs | 73a4230 |
| **#11** | Cache DSPy extraction | **500-2000ms savings** per request | 10f1a42 |
| **#15** | Skip ASP when Python found free slots | **500-5000ms savings** when free slots exist | a210bec |
| - | Code review fixes | Consistency improvements | 0b73327 |

### Estimated Performance Impact

- **Best case**: ~7000ms savings (DSPy reuse + ASP skip)
- **Typical case**: ~1500ms savings (DSPy reuse)
- **Worst case**: ~0ms savings (no free slots, no preview)

### Files Modified

| File | Changes |
|------|---------|
| `orchestrate_scheduling.py` | Deep copy, validation data isolation, DSPy caching, ASP early exit |
| `move_validator.py` | Added `additional_calendars` parameter for validation data isolation |

### Remaining Work

**High Priority:**
- [ ] Add regression tests for Issues #1, #10, #11, #15
- [ ] Issue #2: Replace over-broad exception handling (52+ instances)

**Medium Priority:**
- [ ] Issue #3: Fix timezone edge cases
- [ ] Issue #4: Distinguish empty calendar from fetch failure
- [ ] Issue #12: Implement request-level caching
- [ ] Issue #16: Cache work hours calculation

**Low Priority:**
- [ ] Issue #5: Normalize participant ID casing
- [ ] Issue #6: Improve DSPy fallback robustness
- [ ] Issue #13: Index events for O(1) lookup
- [ ] Dead code removal (`_find_overridden_solo_event`)
