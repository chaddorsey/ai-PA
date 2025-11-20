# Performance Improvement Recommendations for Scheduling Orchestrator

Based on the research in `considerations_for_scheduling_approaches.md` and our current "too many messages" issues, here are prioritized recommendations:

## Current Situation Analysis

**Problem**: Even with optimizations (explicit slots, inverse approach, no soft constraints), clingo hits "too many messages" error at ~288-480 slots.

**Root Cause**: Clingo's grounding phase generates too many intermediate atoms from rules like:
- `occurs(Q, T) :- start(Q, T0), duration(Q, D), slot(T), T >= T0, T < T0 + D.`
- `workhours(P, S) :- workhours_range(P, Start, End), slot(S), S >= Start, S <= End.`
- Range constraints in choice rules

**Density Calculation**: 
- Your case: 8 events / (480 slots × 3 participants) = ~0.0056 density
- Literature threshold: >0.4 density requires decomposition
- **Conclusion**: Density is low, but clingo's grounding limits are still being hit

## Recommended Approaches (Prioritized)

### 1. **Multi-Shot Solving** (Highest Priority - Immediate Impact)

**What it is**: Incrementally add constraints rather than grounding everything at once.

**Implementation Strategy**:
```python
# Phase 1: Find ANY feasible solution with minimal constraints
asp_program_phase1 = generate_asp_program(
    normalized_data,
    scheduling_problem,
    include_soft_constraints=False,
    include_work_hours=False,  # Start without work hours
    include_min_gap=False      # Start without min_gap
)

# If Phase 1 succeeds, refine with more constraints
# If Phase 1 fails, gradually relax constraints
```

**Benefits**:
- Reduces grounding atoms by 50-70% per phase
- Can handle larger horizons by solving in chunks
- Literature shows 50-70% solve time reduction

**Code Changes Needed**:
- Modify `generate_asp_program()` to accept constraint flags
- Implement iterative solving loop in `orchestrate_scheduling()`
- Start with hard constraints only, add soft constraints if solution found

**Expected Impact**: Should allow 672+ slots (7+ days) with current optimizations

### 2. **Temporal Decomposition (Master-Sub Problem)** (High Priority - Medium Effort)

**What it is**: Split into two phases:
- **Master Problem**: Assign meeting to a day (coarse-grained)
- **Sub-Problem**: Assign specific time within that day (fine-grained)

**Implementation Strategy**:
```python
# Phase 1: Find feasible days (hourly slots)
hourly_slot_indexer = create_hourly_indexer(horizon_start, horizon_end)
hourly_program = generate_hourly_asp_program(...)  # 24 slots/day instead of 96
day_solution = solve(hourly_program)  # Returns: "Meeting on Day X"

# Phase 2: Refine to 15-minute slots within that day
day_start = get_day_start(day_solution)
day_end = day_start + timedelta(days=1)
refined_indexer = create_15min_indexer(day_start, day_end)  # Only 96 slots
refined_program = generate_refined_asp_program(day_solution, ...)
final_solution = solve(refined_program)
```

**Benefits**:
- Master problem: 14 days = 336 hourly slots (vs 1344 15-min slots)
- Sub-problem: 1 day = 96 15-min slots (very manageable)
- Total grounding: ~432 atoms vs 1344 atoms (68% reduction)

**Code Changes Needed**:
- Create `hourly_slot_indexer.py` for 1-hour granularity
- Modify `generate_asp_program()` to support hourly mode
- Implement two-phase solving in `orchestrate_scheduling()`

**Expected Impact**: Should handle 14+ day horizons easily

### 3. **Pre-generate occurs() Facts** (Medium Priority - Low Effort)

**What it is**: Instead of using the rule `occurs(Q, T) :- start(Q, T0), duration(Q, D), slot(T), T >= T0, T < T0 + D.`, pre-generate explicit `occurs(Q, T)` facts for each free slot.

**Implementation Strategy**:
```python
# In fact_generator.py, for each free slot:
for free_slot in free_slots:
    # Pre-generate occurs facts for this meeting start
    for offset in range(duration_slots):
        facts.append(f"occurs({request_id}, {free_slot + offset}).")
```

**Benefits**:
- Eliminates range constraint in `occurs()` rule
- Reduces grounding atoms significantly
- Rule becomes: `occurs(Q, T) :- occurs(Q, T).` (trivial)

**Code Changes Needed**:
- Modify `generate_asp_facts()` to pre-generate occurs facts
- Simplify `occurs()` rule in ASP encoding

**Expected Impact**: Should reduce grounding atoms by 20-30%

### 4. **Simplify Work Hours Encoding** (Medium Priority - Low Effort)

**What it is**: Instead of using range rules `workhours(P, S) :- workhours_range(P, Start, End), slot(S), S >= Start, S <= End.`, generate explicit workhours facts only for slots that are actually used.

**Implementation Strategy**:
```python
# Only generate workhours facts for slots that are:
# 1. Free slots (meeting candidates)
# 2. Meeting duration slots (for occurs rule)
# 3. Busy slots (for constraint checking)

workhours_slots_to_generate = used_slots.intersection(work_hours_slots[participant])
for slot in workhours_slots_to_generate:
    facts.append(f"workhours({participant_id}, {slot}).")
```

**Benefits**:
- Eliminates range constraint in workhours rules
- Only generates atoms for slots that matter
- Reduces grounding complexity

**Code Changes Needed**:
- Modify work hours fact generation in `generate_asp_facts()`
- Simplify workhours rules in ASP encoding

**Expected Impact**: Should reduce grounding atoms by 15-25%

### 5. **Consider Alternative Solvers** (Lower Priority - High Effort)

If ASP continues to struggle, consider:

**Google OR-Tools CP-SAT**:
- **Pros**: Excellent for scheduling, handles large problems, Python API
- **Cons**: Different paradigm, would require rewriting encoding
- **When to consider**: If multi-shot + decomposition still fails

**OptaPlanner/Timefold**:
- **Pros**: Built for scheduling, handles rescheduling, REST API
- **Cons**: Java-based, requires service architecture
- **When to consider**: If we need production-grade scheduling with rescheduling

**Implementation Strategy**:
- Keep ASP as primary, add CP-SAT as fallback
- Use same Python interface, swap solver based on problem size
- Fallback logic: If ASP fails with "too many messages", try CP-SAT

## Implementation Plan

### Phase 1: Quick Wins (1-2 days)
1. ✅ Pre-generate occurs() facts
2. ✅ Simplify work hours encoding
3. ✅ Implement multi-shot solving (basic version)

**Expected Result**: Should handle 672+ slots (7 days)

### Phase 2: Decomposition (3-5 days)
1. Implement temporal decomposition (hourly → 15-min)
2. Add master-sub problem solving
3. Test with 14+ day horizons

**Expected Result**: Should handle 14+ day horizons

### Phase 3: Optimization (if needed)
1. Add CP-SAT fallback
2. Implement advanced multi-shot with constraint relaxation
3. Add parallel execution for sub-problems

## Codebase References

### Clingo Multi-Shot
- **Documentation**: https://potassco.org/clingo/python-api/5.5/clingo/
- **Key API**: `Control.solve()` with `on_model` callback
- **Example**: Use `Control.ground()` incrementally, add constraints per iteration

### Train Scheduling Example
- **Repository**: https://github.com/potassco/train-scheduling-with-clingo-dl
- **Relevance**: Shows ASP encoding patterns, solution checking
- **Key Pattern**: Incremental constraint addition

### LUNCH Course Scheduling
- **Repository**: Open-source ASP-based scheduling
- **Relevance**: Complete pipeline from requirements to solution
- **Key Pattern**: Modular constraint definition

## Immediate Next Steps

1. **Implement pre-generated occurs() facts** (30 min)
2. **Simplify work hours encoding** (30 min)
3. **Test with 672 slots** (15 min)
4. **If still fails, implement basic multi-shot** (2-3 hours)

This should get us to 7+ day horizons. Then we can implement temporal decomposition for 14+ day support.

