# Event Protection Levels: locked, protected, and flexible

## Overview

The scheduling orchestrator uses three protection levels to control how existing calendar events interact with new meeting requests. These levels determine whether events can be moved or overlapped, and with what priority.

## Protection Level Hierarchy

The system evaluates events in this priority order:
1. **`locked`** (highest priority - hard constraint)
2. **`protected`** (soft constraint, priority level 1)
3. **`flexible`** (soft constraint, priority level 2)

**Note**: If multiple flags are set, `locked` takes precedence over `protected`, which takes precedence over `flexible`.

## 1. `locked` (Hard Constraint)

**Meaning**: Event cannot be moved or overlapped - absolute blocker

**Behavior**:
- **Hard constraint**: The new meeting **cannot** overlap with locked events
- If a locked event exists, the optimizer will find a different time slot
- Locked events are treated as immovable barriers
- If no solution exists without overlapping locked events, the system returns `UNSAT`

**Use cases**:
- Critical meetings (board meetings, client presentations)
- External commitments (doctor appointments, flights)
- Recurring events that must stay fixed (weekly team standup at specific time)
- Events explicitly marked as "do not move" by the user

**Example**:
```json
{
  "id": "board-meeting",
  "start": "2025-01-15T14:00:00Z",
  "end": "2025-01-15T16:00:00Z",
  "locked": true,
  "protected": false,
  "flexible": false
}
```

**ASP Encoding**:
```asp
% Hard constraint: Cannot overlap with locked events
:- occurs(Q, T), needs(Q, P), locked_event(P, T).
```

## 2. `protected` (Soft Constraint - Priority 1)

**Meaning**: Event should not be moved if possible - strong preference

**Behavior**:
- **Soft constraint**: The optimizer will **strongly prefer** not to overlap with protected events
- Protected events can be moved, but it's heavily penalized
- In lexicographic optimization, avoiding protected event overlaps is **priority level 1** (highest soft constraint priority)
- The system will only move protected events if absolutely necessary to find a solution

**Use cases**:
- Important client meetings
- Focus time blocks
- Recurring meetings that are preferred at specific times
- Events the user wants to preserve but could move if needed

**Example**:
```json
{
  "id": "client-review",
  "start": "2025-01-15T10:00:00Z",
  "end": "2025-01-15T11:00:00Z",
  "locked": false,
  "protected": true,
  "flexible": false
}
```

**ASP Encoding**:
```asp
% L1: Minimize violations of protected event boundaries
protected_overlap(Q, P, S) :- occurs(Q, S), needs(Q, P), protected_event(P, S).
#minimize { 1@1 : protected_overlap(Q, P, S) }.
```

## 3. `flexible` (Soft Constraint - Priority 2)

**Meaning**: Event can be moved to accommodate new meetings - default behavior

**Behavior**:
- **Soft constraint**: The optimizer can move flexible events, but with a cost
- Moving flexible events is penalized, but less than protected events
- In lexicographic optimization, flexible event movement is **priority level 2** (lower than protected)
- The system will move flexible events to find optimal solutions

**Use cases**:
- Internal team meetings
- Standup meetings
- Working sessions
- Any event that can be rescheduled without major impact

**Example**:
```json
{
  "id": "team-standup",
  "start": "2025-01-15T09:00:00Z",
  "end": "2025-01-15T09:15:00Z",
  "locked": false,
  "protected": false,
  "flexible": true
}
```

**ASP Encoding**:
```asp
% L2: Minimize total moved minutes
flexible_overlap(Q, P, S) :- occurs(Q, S), needs(Q, P), busy(P, S), 
                              not protected_event(P, S), not locked_event(P, S).
overlap_cost(Q, P, S, C) :- flexible_overlap(Q, P, S), occurs(Q, S), 
                             duration(Q, D), C = D * 15.
#minimize { C@2 : overlap_cost(Q, P, S, C) }.
```

## Default Behavior

If no flags are explicitly set:
- `locked`: `false` (default)
- `protected`: `false` (default)
- `flexible`: `true` (default)

**Result**: Events default to `flexible` protection level.

## Protection Level Determination Logic

The normalizer determines protection level using this priority:

```python
if locked:
    protection_level = "locked"
elif protected:
    protection_level = "protected"
elif flexible:
    protection_level = "flexible"
else:
    protection_level = "flexible"  # default
```

**Important**: Only one protection level is assigned per event, based on the priority above.

## Lexicographic Optimization Priority

The optimizer uses lexicographic optimization with these priority levels:

1. **Level 0**: Feasibility (hard constraints - must be satisfied)
   - No double bookings
   - Work hours respected
   - **Locked events cannot be overlapped** ← `locked` events enforced here

2. **Level 1**: Minimize protected event overlaps ← `protected` events optimized here
   - Strongly prefer not to move protected events

3. **Level 2**: Minimize flexible event movement costs ← `flexible` events optimized here
   - Minimize disruption to flexible events

4. **Level 3**: Maximize focus blocks and respect preferences
   - Create long focus blocks
   - Respect time/day preferences

## Practical Examples

### Example 1: Board Meeting (Locked)
```json
{
  "id": "board-q1",
  "start": "2025-01-20T14:00:00Z",
  "end": "2025-01-20T17:00:00Z",
  "locked": true,
  "protected": false,
  "flexible": false
}
```
**Result**: New meeting will be scheduled around this time - cannot overlap.

### Example 2: Client Review (Protected)
```json
{
  "id": "client-acme-review",
  "start": "2025-01-20T10:00:00Z",
  "end": "2025-01-20T11:00:00Z",
  "locked": false,
  "protected": true,
  "flexible": false
}
```
**Result**: New meeting will avoid this time if possible, but could move it if necessary.

### Example 3: Team Standup (Flexible)
```json
{
  "id": "daily-standup",
  "start": "2025-01-20T09:00:00Z",
  "end": "2025-01-20T09:15:00Z",
  "locked": false,
  "protected": false,
  "flexible": true
}
```
**Result**: New meeting can overlap this time, and the standup can be moved to accommodate.

## Summary Table

| Flag | Constraint Type | Can Overlap? | Can Move? | Optimization Priority | Use Case |
|------|----------------|--------------|-----------|----------------------|----------|
| `locked: true` | **Hard** | ❌ No | ❌ No | Level 0 (feasibility) | Critical, immovable events |
| `protected: true` | **Soft** | ⚠️ Avoid if possible | ⚠️ Strongly prefer not to | Level 1 (highest soft) | Important but movable events |
| `flexible: true` | **Soft** | ✅ Yes | ✅ Yes (with cost) | Level 2 (lower soft) | Movable internal meetings |

## Best Practices

1. **Use `locked` sparingly**: Only for truly immovable events
2. **Use `protected` for important events**: Client meetings, focus time, important reviews
3. **Default to `flexible`**: Most internal meetings should be flexible
4. **Don't set conflicting flags**: The system uses priority (locked > protected > flexible)
5. **Consider user preferences**: Let users mark their own events with appropriate protection levels

