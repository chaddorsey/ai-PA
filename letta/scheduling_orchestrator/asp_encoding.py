"""
ASP (Answer Set Programming) encoding for scheduling optimization.

Defines the clingo logic program for constraint-based scheduling on a 15-minute grid.
"""

# Base ASP program with hard constraints
BASE_ASP_PROGRAM = """
% ============================================
% Scheduling ASP Encoding - Hard Constraints
% ============================================

% Predicates:
%   slot(S)              - Slot S exists in the grid (generated from range or explicit facts)
%   busy(P, S)           - Participant P is busy at slot S
%   needs(Q, P)          - Request Q requires participant P
%   window(Q, S)         - Request Q is allowed to start at slot S (explicit or from range)
%   window_min(Q, M)     - Request Q minimum allowed start slot (for range)
%   window_max(Q, M)     - Request Q maximum allowed start slot (for range)
%   horizon_max(M)       - Maximum slot index in the horizon
%   duration(Q, D)       - Request Q requires D slots
%   workhours(P, S)      - Participant P is available during work hours at slot S
%   min_gap(Q, G)        - Request Q requires minimum gap G slots after previous events
%   locked_event(P, S)   - Participant P has a locked event at slot S (cannot move)

% Generate slot range from horizon_max (optimization: avoid generating thousands of slot facts)
% NOTE: If explicit slot(S) facts are provided, use those instead of the range rule.
% This dramatically reduces grounding atoms by only generating slots that are actually used.
% Fallback to range rule only if no explicit slot facts are provided.
has_explicit_slots :- slot(_).
slot(S) :- horizon_max(M), S = 0..M, not has_explicit_slots.

% Generate window from range if window_min/window_max are provided (optimization)
% This is more efficient than generating explicit window facts for every slot
% OPTIMIZATION: If explicit window facts are provided, use those; otherwise use range rule
has_explicit_windows :- window(Q, _).
window(Q, S) :- window_min(Q, Min), window_max(Q, Max), slot(S), S >= Min, S <= Max, not has_explicit_windows.

% Choice rule: Select exactly one start slot for each request
% OPTIMIZATION: Use free_slot(T) instead of slot(T) to dramatically reduce candidates
% If free_slot facts are provided, use them; otherwise fall back to slot(T)
% Check if any free_slot facts exist
has_free_slots :- free_slot(_).
% Use free_slot if available, otherwise use all slots
{ start(Q, T) : free_slot(T), window(Q, T) } = 1 :- request(Q), has_free_slots.
{ start(Q, T) : slot(T), window(Q, T) } = 1 :- request(Q), not has_free_slots.

% Meeting occurs at all slots from start to start+duration-1
occurs(Q, T) :- start(Q, T0), duration(Q, D), slot(T), T >= T0, T < T0 + D.

% Hard constraint: No double-booking
% A meeting cannot occur when any required participant is busy
:- occurs(Q, T), needs(Q, P), busy(P, T).

% Hard constraint: Must respect time window
% Meeting can only start within allowed window
:- start(Q, T), not window(Q, T).

% Hard constraint: Must respect work hours
% Meeting must occur during participant work hours
% Support both range encoding (workhours_range) and inverse encoding (non_workhours)

% Range encoding: workhours_range(P, Start, End) means P works from Start to End (inclusive)
workhours(P, S) :- workhours_range(P, Start, End), slot(S), S >= Start, S <= End.

% Inverse encoding: non_workhours(P, Start, End) means P does NOT work from Start to End
% Helper: check if slot S is in a non-workhours range
in_non_workhours(P, S) :- non_workhours(P, Start, End), slot(S), S >= Start, S <= End.
% If non_workhours is defined, workhours = all slots NOT in non_workhours ranges
workhours(P, S) :- slot(S), participant(P), not in_non_workhours(P, S), not workhours_range(P, _, _).

% Fallback: if no work hours specified, assume all slots are work hours
workhours(P, S) :- slot(S), participant(P), not workhours_range(P, _, _), not non_workhours(P, _, _).

% Hard constraint: Meeting must occur during work hours
:- occurs(Q, T), needs(Q, P), not workhours(P, T).

% Hard constraint: Cannot overlap with locked events
% Meeting cannot occur when any required participant has a locked event
:- occurs(Q, T), needs(Q, P), locked_event(P, T).

% Hard constraint: Minimum gap after previous events
% Ensure no meeting starts within min_gap slots after any busy slot ends
% We need to track when busy slots end - for simplicity, assume each busy slot
% blocks the next min_gap slots. A more sophisticated version would track
% consecutive busy slots as events.
% For now: if a participant is busy at slot T, no meeting can start at T+1 to T+G
:- start(Q, T), needs(Q, P), busy(P, T2), min_gap(Q, G), T > T2, T <= T2 + G.

% Show the selected start slots and occupied slots
#show start/2.
#show occurs/2.
"""

# Soft constraints with lexicographic optimization
SOFT_CONSTRAINTS_PROGRAM = """
% ============================================
% Scheduling ASP Encoding - Soft Constraints
% ============================================

% Additional predicates for optimization:
%   protected_event(P, S)    - Participant P has a protected event at slot S
%   event_start(P, E, S)    - Event E for participant P starts at slot S
%   event_end(P, E, S)      - Event E for participant P ends at slot S
%   moved_event(P, E, M)     - Event E for participant P moved by M minutes
%   focus_block(P, B, L)     - Participant P has focus block B of length L slots
%   preferred_time(Q, T)     - Request Q prefers time slot T
%   preferred_day(Q, D)      - Request Q prefers day D

% L1: Minimize violations of protected event boundaries
% Penalize moving protected events (events that should not be moved if possible)
% For each protected event slot that the new meeting overlaps with, add penalty
protected_overlap(Q, P, S) :- occurs(Q, S), needs(Q, P), protected_event(P, S).
#minimize { 1@1 : protected_overlap(Q, P, S) }.

% L2: Minimize total moved minutes
% Calculate how much existing events need to shift to accommodate the new meeting
% This is simplified - in a full implementation, we'd track event boundaries
% and calculate actual shift amounts. For now, we penalize overlaps with flexible events.
flexible_overlap(Q, P, S) :- occurs(Q, S), needs(Q, P), busy(P, S), not protected_event(P, S), not locked_event(P, S).
% Weight by duration - longer overlaps cost more
overlap_cost(Q, P, S, C) :- flexible_overlap(Q, P, S), occurs(Q, S), duration(Q, D), C = D * 15.
#minimize { C@2 : overlap_cost(Q, P, S, C) }.

% L3: Maximize focus blocks (consecutive free slots)
% Identify consecutive free slots after scheduling the meeting
% A focus block is a sequence of free slots of minimum length
% We reward longer focus blocks
free_slot(P, S) :- slot(S), participant(P), not busy(P, S), not occurs(Q, S) : needs(Q, P).
% Focus block starts when we transition from busy to free or at slot 0
focus_block_start(P, 0) :- free_slot(P, 0), participant(P).
focus_block_start(P, S) :- free_slot(P, S), (busy(P, S-1) ; occurs(Q, S-1) : needs(Q, P)), S > 0.
% Focus block continues while slots are free (simplified - track length)
% For optimization, we'll use a simpler approach: count consecutive free slots
% This is a simplified version - full implementation would track block boundaries
% For now, we'll optimize based on total free slots (proxy for focus blocks)
% More sophisticated: track actual block lengths
free_slot_count(P, C) :- participant(P), C = #count { S : free_slot(P, S) }.
% Maximize free slots (minimize negative count)
#minimize { -C@3 : free_slot_count(P, C) }.

% L3: Minimize preference violations
% Penalize deviations from preferred times
% If preferred times are specified and we don't use one, add penalty
has_preferred_time(Q) :- preferred_time(Q, T).
preference_violation(Q, T, 1) :- start(Q, T), has_preferred_time(Q), not preferred_time(Q, T).
% Penalize deviations from preferred days
% Calculate day from slot (assuming 96 slots per day = 24 hours * 4 slots/hour)
% This is approximate - actual calculation depends on horizon start
% For simplicity, we'll use a helper fact that will be generated if preferred_days are specified
has_preferred_day(Q) :- preferred_day(Q, D).
preference_day_violation(Q, T, 1) :- start(Q, T), has_preferred_day(Q), not preferred_day(Q, D) : day_of_slot(T, D).
#minimize { P@3 : preference_violation(Q, T, P) }.
#minimize { P@3 : preference_day_violation(Q, T, P) }.
"""

# Complete ASP program (hard + soft constraints)
COMPLETE_ASP_PROGRAM = BASE_ASP_PROGRAM + SOFT_CONSTRAINTS_PROGRAM

