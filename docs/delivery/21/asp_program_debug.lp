
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
% OPTIMIZATION: Use pre-generated occurs_if_start facts instead of range constraint
% This eliminates the range constraint T >= T0, T < T0 + D which generates many atoms
occurs(Q, T) :- start(Q, T0), occurs_if_start(Q, T0, T).

% Hard constraint: No double-booking
% A meeting cannot occur when any required participant is busy
:- occurs(Q, T), needs(Q, P), busy(P, T).

% Hard constraint: Must respect time window
% Meeting can only start within allowed window
:- start(Q, T), not window(Q, T).

% Hard constraint: Must respect work hours
% Meeting must occur during participant work hours
% OPTIMIZATION: Use explicit workhours facts when available, fallback to range rules
has_explicit_workhours :- workhours(_, _).
% If explicit workhours facts exist, use those
% If workhours_range exists, use range rule (but only for slots that exist)
workhours(P, S) :- workhours_range(P, Start, End), slot(S), S >= Start, S <= End, not has_explicit_workhours.
% Fallback: if no work hours specified, assume all slots are work hours
workhours(P, S) :- slot(S), participant(P), not workhours(P, _), not workhours_range(P, _, _).

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

% Facts:
request(q1).
horizon_max(47).
needs(q1, "cdorsey@concord.org").
needs(q1, "sbrau@concord.org").
needs(q1, "dkehoe@concord.org").
duration(q1, 3).
min_gap(q1, 1).
busy("cdorsey@concord.org", 0).
busy("cdorsey@concord.org", 1).
busy("cdorsey@concord.org", 2).
busy("cdorsey@concord.org", 3).
busy("cdorsey@concord.org", 4).
busy("cdorsey@concord.org", 5).
busy("cdorsey@concord.org", 6).
busy("cdorsey@concord.org", 7).
busy("cdorsey@concord.org", 8).
busy("cdorsey@concord.org", 9).
busy("cdorsey@concord.org", 10).
busy("cdorsey@concord.org", 11).
busy("cdorsey@concord.org", 12).
busy("cdorsey@concord.org", 13).
busy("cdorsey@concord.org", 14).
busy("cdorsey@concord.org", 15).
busy("cdorsey@concord.org", 16).
busy("cdorsey@concord.org", 17).
busy("cdorsey@concord.org", 18).
busy("cdorsey@concord.org", 19).
busy("cdorsey@concord.org", 20).
busy("cdorsey@concord.org", 21).
busy("cdorsey@concord.org", 22).
busy("cdorsey@concord.org", 23).
busy("cdorsey@concord.org", 24).
busy("cdorsey@concord.org", 25).
busy("cdorsey@concord.org", 26).
busy("cdorsey@concord.org", 27).
busy("cdorsey@concord.org", 28).
busy("cdorsey@concord.org", 29).
busy("cdorsey@concord.org", 30).
busy("cdorsey@concord.org", 31).
busy("sbrau@concord.org", 0).
busy("sbrau@concord.org", 1).
busy("sbrau@concord.org", 2).
busy("sbrau@concord.org", 3).
busy("sbrau@concord.org", 4).
busy("sbrau@concord.org", 5).
busy("sbrau@concord.org", 6).
busy("sbrau@concord.org", 7).
busy("sbrau@concord.org", 8).
busy("sbrau@concord.org", 9).
busy("sbrau@concord.org", 10).
busy("sbrau@concord.org", 11).
busy("sbrau@concord.org", 12).
busy("sbrau@concord.org", 13).
busy("sbrau@concord.org", 14).
busy("sbrau@concord.org", 15).
busy("sbrau@concord.org", 16).
busy("sbrau@concord.org", 17).
busy("sbrau@concord.org", 18).
busy("sbrau@concord.org", 19).
busy("sbrau@concord.org", 20).
busy("sbrau@concord.org", 21).
busy("sbrau@concord.org", 22).
busy("sbrau@concord.org", 23).
busy("sbrau@concord.org", 24).
busy("sbrau@concord.org", 25).
busy("sbrau@concord.org", 26).
busy("sbrau@concord.org", 28).
busy("sbrau@concord.org", 29).
busy("dkehoe@concord.org", 6).
busy("dkehoe@concord.org", 7).
busy("dkehoe@concord.org", 8).
busy("dkehoe@concord.org", 9).
busy("dkehoe@concord.org", 16).
busy("dkehoe@concord.org", 17).
busy("dkehoe@concord.org", 18).
busy("dkehoe@concord.org", 24).
busy("dkehoe@concord.org", 25).
busy("dkehoe@concord.org", 26).
busy("dkehoe@concord.org", 30).
busy("dkehoe@concord.org", 31).
occurs_if_start(q1, 0, 0).
occurs_if_start(q1, 0, 1).
occurs_if_start(q1, 0, 2).
occurs_if_start(q1, 1, 1).
occurs_if_start(q1, 1, 2).
occurs_if_start(q1, 1, 3).
occurs_if_start(q1, 2, 2).
occurs_if_start(q1, 2, 3).
occurs_if_start(q1, 2, 4).
occurs_if_start(q1, 3, 3).
occurs_if_start(q1, 3, 4).
occurs_if_start(q1, 3, 5).
occurs_if_start(q1, 4, 4).
occurs_if_start(q1, 4, 5).
occurs_if_start(q1, 4, 6).
occurs_if_start(q1, 5, 5).
occurs_if_start(q1, 5, 6).
occurs_if_start(q1, 5, 7).
occurs_if_start(q1, 6, 6).
occurs_if_start(q1, 6, 7).
occurs_if_start(q1, 6, 8).
occurs_if_start(q1, 7, 7).
occurs_if_start(q1, 7, 8).
occurs_if_start(q1, 7, 9).
occurs_if_start(q1, 8, 8).
occurs_if_start(q1, 8, 9).
occurs_if_start(q1, 8, 10).
occurs_if_start(q1, 9, 9).
occurs_if_start(q1, 9, 10).
occurs_if_start(q1, 9, 11).
occurs_if_start(q1, 10, 10).
occurs_if_start(q1, 10, 11).
occurs_if_start(q1, 10, 12).
occurs_if_start(q1, 11, 11).
occurs_if_start(q1, 11, 12).
occurs_if_start(q1, 11, 13).
occurs_if_start(q1, 12, 12).
occurs_if_start(q1, 12, 13).
occurs_if_start(q1, 12, 14).
occurs_if_start(q1, 13, 13).
occurs_if_start(q1, 13, 14).
occurs_if_start(q1, 13, 15).
occurs_if_start(q1, 14, 14).
occurs_if_start(q1, 14, 15).
occurs_if_start(q1, 14, 16).
occurs_if_start(q1, 15, 15).
occurs_if_start(q1, 15, 16).
occurs_if_start(q1, 15, 17).
occurs_if_start(q1, 16, 16).
occurs_if_start(q1, 16, 17).
occurs_if_start(q1, 16, 18).
occurs_if_start(q1, 17, 17).
occurs_if_start(q1, 17, 18).
occurs_if_start(q1, 17, 19).
occurs_if_start(q1, 18, 18).
occurs_if_start(q1, 18, 19).
occurs_if_start(q1, 18, 20).
occurs_if_start(q1, 19, 19).
occurs_if_start(q1, 19, 20).
occurs_if_start(q1, 19, 21).
occurs_if_start(q1, 20, 20).
occurs_if_start(q1, 20, 21).
occurs_if_start(q1, 20, 22).
occurs_if_start(q1, 21, 21).
occurs_if_start(q1, 21, 22).
occurs_if_start(q1, 21, 23).
occurs_if_start(q1, 22, 22).
occurs_if_start(q1, 22, 23).
occurs_if_start(q1, 22, 24).
occurs_if_start(q1, 23, 23).
occurs_if_start(q1, 23, 24).
occurs_if_start(q1, 23, 25).
occurs_if_start(q1, 24, 24).
occurs_if_start(q1, 24, 25).
occurs_if_start(q1, 24, 26).
occurs_if_start(q1, 25, 25).
occurs_if_start(q1, 25, 26).
occurs_if_start(q1, 25, 27).
occurs_if_start(q1, 26, 26).
occurs_if_start(q1, 26, 27).
occurs_if_start(q1, 26, 28).
occurs_if_start(q1, 27, 27).
occurs_if_start(q1, 27, 28).
occurs_if_start(q1, 27, 29).
occurs_if_start(q1, 28, 28).
occurs_if_start(q1, 28, 29).
occurs_if_start(q1, 28, 30).
occurs_if_start(q1, 29, 29).
occurs_if_start(q1, 29, 30).
occurs_if_start(q1, 29, 31).
occurs_if_start(q1, 30, 30).
occurs_if_start(q1, 30, 31).
occurs_if_start(q1, 30, 32).
occurs_if_start(q1, 31, 31).
occurs_if_start(q1, 31, 32).
occurs_if_start(q1, 31, 33).
slot(0).
slot(1).
slot(2).
slot(3).
slot(4).
slot(5).
slot(6).
slot(7).
slot(8).
slot(9).
slot(10).
slot(11).
slot(12).
slot(13).
slot(14).
slot(15).
slot(16).
slot(17).
slot(18).
slot(19).
slot(20).
slot(21).
slot(22).
slot(23).
slot(24).
slot(25).
slot(26).
slot(27).
slot(28).
slot(29).
slot(30).
slot(31).
slot(32).
slot(33).
slot(34).
slot(35).
slot(36).
slot(37).
slot(38).
slot(39).
slot(40).
slot(41).
slot(42).
slot(43).
slot(44).
slot(45).
workhours("cdorsey@concord.org", 0).
workhours("cdorsey@concord.org", 1).
workhours("cdorsey@concord.org", 2).
workhours("cdorsey@concord.org", 3).
workhours("cdorsey@concord.org", 4).
workhours("cdorsey@concord.org", 5).
workhours("cdorsey@concord.org", 6).
workhours("cdorsey@concord.org", 7).
workhours("cdorsey@concord.org", 8).
workhours("cdorsey@concord.org", 9).
workhours("cdorsey@concord.org", 10).
workhours("cdorsey@concord.org", 11).
workhours("cdorsey@concord.org", 12).
workhours("cdorsey@concord.org", 13).
workhours("cdorsey@concord.org", 14).
workhours("cdorsey@concord.org", 15).
workhours("cdorsey@concord.org", 16).
workhours("cdorsey@concord.org", 17).
workhours("cdorsey@concord.org", 18).
workhours("cdorsey@concord.org", 19).
workhours("cdorsey@concord.org", 20).
workhours("cdorsey@concord.org", 21).
workhours("cdorsey@concord.org", 22).
workhours("cdorsey@concord.org", 23).
workhours("cdorsey@concord.org", 24).
workhours("cdorsey@concord.org", 25).
workhours("cdorsey@concord.org", 26).
workhours("cdorsey@concord.org", 27).
workhours("cdorsey@concord.org", 28).
workhours("cdorsey@concord.org", 29).
workhours("cdorsey@concord.org", 30).
workhours("cdorsey@concord.org", 31).
workhours("sbrau@concord.org", 0).
workhours("sbrau@concord.org", 1).
workhours("sbrau@concord.org", 2).
workhours("sbrau@concord.org", 3).
workhours("sbrau@concord.org", 4).
workhours("sbrau@concord.org", 5).
workhours("sbrau@concord.org", 6).
workhours("sbrau@concord.org", 7).
workhours("sbrau@concord.org", 8).
workhours("sbrau@concord.org", 9).
workhours("sbrau@concord.org", 10).
workhours("sbrau@concord.org", 11).
workhours("sbrau@concord.org", 12).
workhours("sbrau@concord.org", 13).
workhours("sbrau@concord.org", 14).
workhours("sbrau@concord.org", 15).
workhours("sbrau@concord.org", 16).
workhours("sbrau@concord.org", 17).
workhours("sbrau@concord.org", 18).
workhours("sbrau@concord.org", 19).
workhours("sbrau@concord.org", 20).
workhours("sbrau@concord.org", 21).
workhours("sbrau@concord.org", 22).
workhours("sbrau@concord.org", 23).
workhours("sbrau@concord.org", 24).
workhours("sbrau@concord.org", 25).
workhours("sbrau@concord.org", 26).
workhours("sbrau@concord.org", 27).
workhours("sbrau@concord.org", 28).
workhours("sbrau@concord.org", 29).
workhours("sbrau@concord.org", 30).
workhours("sbrau@concord.org", 31).
workhours("dkehoe@concord.org", 0).
workhours("dkehoe@concord.org", 1).
workhours("dkehoe@concord.org", 2).
workhours("dkehoe@concord.org", 3).
workhours("dkehoe@concord.org", 4).
workhours("dkehoe@concord.org", 5).
workhours("dkehoe@concord.org", 6).
workhours("dkehoe@concord.org", 7).
workhours("dkehoe@concord.org", 8).
workhours("dkehoe@concord.org", 9).
workhours("dkehoe@concord.org", 10).
workhours("dkehoe@concord.org", 11).
workhours("dkehoe@concord.org", 12).
workhours("dkehoe@concord.org", 13).
workhours("dkehoe@concord.org", 14).
workhours("dkehoe@concord.org", 15).
workhours("dkehoe@concord.org", 16).
workhours("dkehoe@concord.org", 17).
workhours("dkehoe@concord.org", 18).
workhours("dkehoe@concord.org", 19).
workhours("dkehoe@concord.org", 20).
workhours("dkehoe@concord.org", 21).
workhours("dkehoe@concord.org", 22).
workhours("dkehoe@concord.org", 23).
workhours("dkehoe@concord.org", 24).
workhours("dkehoe@concord.org", 25).
workhours("dkehoe@concord.org", 26).
workhours("dkehoe@concord.org", 27).
workhours("dkehoe@concord.org", 28).
workhours("dkehoe@concord.org", 29).
workhours("dkehoe@concord.org", 30).
workhours("dkehoe@concord.org", 31).
window(q1, 0).
window(q1, 1).
window(q1, 2).
window(q1, 3).
window(q1, 4).
window(q1, 5).
window(q1, 6).
window(q1, 7).
window(q1, 8).
window(q1, 9).
window(q1, 10).
window(q1, 11).
window(q1, 12).
window(q1, 13).
window(q1, 14).
window(q1, 15).
window(q1, 16).
window(q1, 17).
window(q1, 18).
window(q1, 19).
window(q1, 20).
window(q1, 21).
window(q1, 22).
window(q1, 23).
window(q1, 24).
window(q1, 25).
window(q1, 26).
window(q1, 27).
window(q1, 28).
window(q1, 29).
window(q1, 30).
window(q1, 31).
