# ASP Complexity Analysis and Optimization Strategies

## Problem Statement

The scheduling orchestrator is hitting clingo's "too many messages" error even with optimized fact generation. This error occurs during **grounding** (not solving), when clingo generates internal atoms from ASP rules.

## Root Cause Analysis

### Current Issue
- **480 slots** (5 days) still triggers "too many messages"
- **171 facts** (relatively small)
- Error occurs at `ctl.add("base", [], program)` - during grounding

### Why This Happens

1. **Slot Generation Rule**: `slot(S) :- horizon_max(M), S = 0..M.`
   - Creates 480 `slot(S)` atoms during grounding
   - Each atom generates internal messages in clingo

2. **Choice Rule**: `{ start(Q, T) : slot(T), window(Q, T) } = 1`
   - Must ground over all 480 slots
   - Generates many candidate atoms during grounding

3. **Work Hours Rules**: 
   - `workhours(P, S) :- workhours_range(P, Start, End), slot(S), S >= Start, S <= End.`
   - For each participant and each range, generates atoms for all slots in range
   - Even with range encoding, this can generate many atoms

4. **Window Generation**: 
   - `window(Q, S) :- window_min(Q, Min), window_max(Q, Max), slot(S), S >= Min, S <= Max.`
   - Generates atoms for all slots in the window

### clingo's Internal Limits

- clingo has internal message limits to prevent excessive output
- These limits are hit during grounding, not solving
- The "too many messages" error is a safety mechanism
- Even with `--warn=none` and message suppression, internal grounding messages can exceed limits

## Expected Capacity of ASP for Scheduling

### Theoretical Capacity
- ASP can handle **thousands of facts** efficiently
- Can solve problems with **millions of ground atoms** (in theory)
- **BUT**: clingo's internal message handling can be a bottleneck

### Practical Limits (for this encoding)
- **Current safe limit**: ~288 slots (3 days) = ~27,000 potential atoms
- **With optimizations**: Could potentially handle ~500-700 slots
- **Without optimizations**: ~100-200 slots

### Why Our Encoding Hits Limits Early

1. **Dense slot generation**: Every slot becomes an atom
2. **Choice rules over all slots**: Must consider every slot as a candidate
3. **Multiple participants**: Multiplies the number of atoms
4. **Work hours constraints**: Generate atoms for every work hour slot

## Optimization Strategies

### 1. Further Horizon Reduction (Quick Fix) ✅ IMPLEMENTED
- **Current**: 480 slots (5 days) → **New**: 288 slots (3 days)
- **Trade-off**: Limits planning horizon but ensures solvability
- **When to use**: Always for large horizons

### 2. Two-Phase Coarse-to-Fine Approach (Recommended)

**Phase 1: Hourly Coarse Search**
- Use 1-hour slots instead of 15-minute slots
- Find candidate time windows (e.g., "Tuesday 2-4 PM")
- Reduces search space by 4x (96 slots → 24 slots)

**Phase 2: 15-Minute Refinement**
- Within each candidate window, use 15-minute slots
- Only consider slots within the candidate windows
- Reduces grounding complexity dramatically

**Implementation**:
```python
# Phase 1: Find candidate hourly windows
hourly_program = generate_hourly_asp_program(...)
hourly_solution = solve(hourly_program)
candidate_windows = extract_windows(hourly_solution)

# Phase 2: Refine within candidate windows
for window in candidate_windows:
    refined_program = generate_refined_asp_program(window, ...)
    refined_solution = solve(refined_program)
    if refined_solution:
        return refined_solution
```

**Benefits**:
- Reduces grounding atoms by ~75%
- Maintains 15-minute precision in final solution
- Can handle much larger horizons

### 3. Inverse Approach: Find Free Slots First

**Strategy**: Instead of generating all slots and filtering, generate only free slots.

**Current Approach**:
```
slot(S) for all S in [0..M]
window(Q, S) for all S in window
{ start(Q, T) : slot(T), window(Q, T) } = 1
```

**Inverse Approach**:
```
% Pre-compute free slots (where all participants are free)
free_slot(S) :- slot(S), not busy(P, S) : needs(Q, P), participant(P).

% Only consider free slots as candidates
{ start(Q, T) : free_slot(T), window(Q, T) } = 1
```

**Benefits**:
- Dramatically reduces choice rule candidates
- If 391/480 slots are busy, only 89 slots need consideration
- Reduces grounding atoms by ~80%

**Implementation**:
- Pre-filter in Python before ASP generation
- Generate `free_slot(S)` facts only for actually free slots
- Modify choice rule to use `free_slot(T)` instead of `slot(T)`

### 4. Pre-Filtering in Python (Hybrid Approach)

**Strategy**: Use Python to identify feasible slots, then only generate ASP for those.

```python
def find_feasible_slots(normalized_data, scheduling_problem):
    """Find slots where meeting could potentially start."""
    feasible = set()
    duration_slots = scheduling_problem.duration_minutes // 15
    
    for slot in range(max_slot - duration_slots + 1):
        # Check if all participants are free for duration
        if all_participants_free(slot, slot + duration_slots):
            # Check work hours
            if all_in_work_hours(slot, slot + duration_slots):
                feasible.add(slot)
    
    return feasible

# Then generate ASP with explicit window facts only for feasible slots
for slot in feasible_slots:
    facts.append(f"window({request_id}, {slot}).")
```

**Benefits**:
- Eliminates choice rule over all slots
- Only generates atoms for feasible slots
- Can handle much larger horizons

### 5. Chunked Solving

**Strategy**: Break horizon into overlapping chunks, solve each, merge results.

```python
chunk_size = 288  # 3 days
overlap = 96      # 1 day overlap

for chunk_start in range(0, total_slots, chunk_size - overlap):
    chunk_end = min(chunk_start + chunk_size, total_slots)
    chunk_solution = solve_chunk(chunk_start, chunk_end)
    if chunk_solution:
        return chunk_solution
```

**Benefits**:
- Each chunk is small enough to solve
- Overlap ensures no solutions are missed at boundaries
- Can handle arbitrarily large horizons

### 6. clingo Configuration Tuning

**Options to explore**:
- Increase clingo's internal message buffer (if configurable)
- Use `--opt-strategy=bb` for branch-and-bound (might reduce grounding)
- Use `--opt-mode=optN` with smaller N
- Disable certain clingo features that generate messages

**Limitations**:
- clingo's message limits are hardcoded
- May not be configurable via Python API

## Recommended Implementation Order

1. ✅ **Immediate**: Reduce MAX_SLOTS_FOR_ASP to 288 (3 days)
2. **Short-term**: Implement inverse approach (pre-filter free slots)
3. **Medium-term**: Implement two-phase coarse-to-fine
4. **Long-term**: Consider chunked solving for very large horizons

## Expected Improvements

| Strategy | Horizon Capacity | Complexity Reduction | Implementation Effort |
|----------|------------------|---------------------|----------------------|
| Current (480 slots) | 5 days | Baseline | Done |
| Reduce to 288 slots | 3 days | ~40% | ✅ Done |
| Inverse (free slots) | 7-10 days | ~80% | Medium |
| Two-phase | 14+ days | ~75% | High |
| Pre-filtering | 14+ days | ~90% | Medium |
| Chunked | Unlimited | Per chunk | High |

## Conclusion

ASP is well-suited for scheduling, but our current encoding generates too many atoms during grounding. The most effective immediate improvements are:

1. **Further reduce horizon** to 288 slots (quick fix)
2. **Implement inverse approach** - only consider free slots (high impact, medium effort)
3. **Consider two-phase** for very large horizons (high impact, higher effort)

The inverse approach is particularly promising because it directly addresses the root cause: we're generating choice rule candidates for slots that are impossible anyway.

