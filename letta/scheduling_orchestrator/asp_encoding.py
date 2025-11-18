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
%   slot(S)              - Slot S exists in the grid
%   busy(P, S)           - Participant P is busy at slot S
%   needs(Q, P)          - Request Q requires participant P
%   window(Q, S)         - Request Q is allowed to start at slot S
%   duration(Q, D)       - Request Q requires D slots
%   workhours(P, S)      - Participant P is available during work hours at slot S
%   min_gap(Q, G)        - Request Q requires minimum gap G slots after previous events
%   locked_event(P, S)   - Participant P has a locked event at slot S (cannot move)

% Choice rule: Select exactly one start slot for each request
{ start(Q, T) : slot(T), window(Q, T) } = 1 :- request(Q).

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

