# Current Pipeline Analysis and Fundamental Issue

## Current Pipeline Overview

### 1. **Input Processing**
- **DSPy Extraction**: Natural language → `SchedulingProblem` (participants, duration, preferences)
- **Event Normalization**: Google Calendar events → 15-minute grid slots
  - Converts event times to slot indices
  - Creates `busy_slots[participant_id] = {slot1, slot2, ...}`
  - Extracts work hours, locked/protected/flexible flags

### 2. **Horizon Reduction**
- Reduces planning horizon from original (e.g., 1440 slots = 15 days) to 192 slots (2 days)
- Focuses on busy slot ranges with padding

### 3. **Free Slot Pre-filtering** (Inverse Approach)
- Python function `_find_free_slots()` finds slots where:
  - All participants are free for entire meeting duration
  - All slots are within work hours
  - Respects min_gap after busy slots
- **Intended benefit**: Reduce choice rule candidates from all slots to only feasible ones

### 4. **ASP Fact Generation**
- Generates explicit `slot(S)` facts for "used" slots only
- Generates `free_slot(S)` facts (limited to 50 for phase 1)
- Generates `occurs_if_start(Q, T0, T)` facts for each free slot × duration
- Generates `busy(P, S)` facts
- Generates `workhours(P, S)` facts (if enabled)

### 5. **Multi-Shot Solving**
- **Phase 1**: Minimal constraints (no work hours, no min_gap, no locked events)
- **Phase 2**: Add work hours + locked events
- **Phase 3**: Add min_gap

### 6. **Clingo Grounding & Solving**
- Clingo grounds the ASP program (converts rules to atoms)
- **THIS IS WHERE IT FAILS**: "too many messages" during grounding

## The Fundamental Problem

### What's Happening in Clingo Grounding

Even with only **192 slots** and **188 facts**, clingo is generating **too many intermediate atoms** during grounding. The issue is in the **ASP rules themselves**, not just the facts.

#### Problematic Rules:

1. **Window Generation Rule**:
   ```asp
   window(Q, S) :- window_min(Q, Min), window_max(Q, Max), slot(S), S >= Min, S <= Max, not has_explicit_windows.
   ```
   - Even with explicit window facts, this rule must be evaluated
   - For each slot S in range, generates atoms

2. **Occurs Rule**:
   ```asp
   occurs(Q, T) :- start(Q, T0), occurs_if_start(Q, T0, T).
   ```
   - For each `start(Q, T0)` candidate, generates `occurs(Q, T)` for all T in meeting duration
   - Even with pre-generated `occurs_if_start` facts, clingo must ground this rule

3. **Double-Booking Constraint**:
   ```asp
   :- occurs(Q, T), needs(Q, P), busy(P, T).
   ```
   - For each `occurs(Q, T)`, checks against all participants and all busy slots
   - Generates many constraint atoms during grounding

4. **Work Hours Constraint** (Phase 2+):
   ```asp
   :- occurs(Q, T), needs(Q, P), not workhours(P, T).
   ```
   - Similar explosion of constraint atoms

### Why "Too Many Messages" Happens

Clingo's grounding phase:
1. Takes ASP rules and facts
2. **Instantiates rules** to create ground atoms
3. Each rule instantiation can create many atoms
4. Clingo has internal message limits to prevent excessive output
5. Even with message suppression, **internal grounding messages** exceed limits

**Key Insight**: The problem isn't the number of facts (188 is small), it's the **combinatorial explosion of rule instantiations** during grounding.

## Why Our Optimizations Haven't Worked

1. ✅ **Explicit slot facts**: Reduced slot atoms, but rules still generate many atoms
2. ✅ **Free slot pre-filtering**: Reduced choice candidates, but `occurs` rule still explodes
3. ✅ **Occurs pre-generation**: Reduced some atoms, but constraint rules still explode
4. ✅ **Multi-shot solving**: Helps, but even phase 1 (minimal) fails
5. ✅ **Horizon reduction**: Helps, but 192 slots is still too many

## The Real Issue: ASP Encoding Mismatch

**ASP is designed for**:
- Problems with many facts but relatively simple rules
- Constraint satisfaction where rules don't generate exponential atoms
- Problems where grounding is fast relative to solving

**Our problem has**:
- Relatively few facts (188)
- Rules that generate many atoms during grounding
- Constraint rules that check every combination

## Alternative Approaches

### Option 1: Pure Python Greedy Search (Recommended)

**Approach**: Solve entirely in Python without ASP

**Algorithm**:
1. Pre-filter free slots (already done)
2. For each free slot, check constraints:
   - All participants free? ✅
   - Within work hours? ✅
   - Respects min_gap? ✅
   - Within time window? ✅
3. Rank remaining slots by preferences
4. Return best slot(s)

**Benefits**:
- No grounding overhead
- Can handle arbitrarily large horizons
- Fast for typical calendar densities
- Easy to add heuristics

**Trade-offs**:
- No lexicographic optimization (but can use heuristics)
- No soft constraint optimization (but can rank)

### Option 2: Simplified ASP Encoding

**Approach**: Drastically simplify ASP rules to reduce grounding atoms

**Changes**:
- Remove `occurs` rule entirely - use direct `start` + duration checks
- Pre-compute all constraints in Python, pass as facts
- Use only choice rule + hard constraints (no intermediate predicates)

**Benefits**:
- Much fewer atoms during grounding
- Still uses ASP for constraint satisfaction

**Trade-offs**:
- Less elegant encoding
- Still may hit limits for very large horizons

### Option 3: Hybrid: Python Pre-solve + ASP Refinement

**Approach**: 
1. Python finds top N candidate slots (e.g., 10-20)
2. ASP only considers these candidates
3. ASP optimizes among candidates

**Benefits**:
- Best of both worlds
- ASP only grounds small problem
- Python handles large search space

**Trade-offs**:
- More complex
- May miss optimal solution if Python pre-filtering is imperfect

## Recommendation

**Switch to Option 1 (Pure Python)** for now because:

1. **Immediate solution**: No more "too many messages" errors
2. **Handles real-world scale**: Can process 2+ weeks, multiple participants
3. **Fast enough**: For typical calendar densities, greedy search is very fast
4. **Maintainable**: Easier to debug and extend
5. **Can add ASP later**: If we need complex optimization, we can add it incrementally

The current ASP approach is fighting against clingo's architecture. A pure Python solution will be more reliable and scalable for this use case.

