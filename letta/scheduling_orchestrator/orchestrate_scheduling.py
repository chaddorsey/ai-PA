"""
Scheduling Orchestration Tool for Letta

This tool takes natural language scheduling requests plus calendar events and returns
ready-to-schedule meeting proposals that satisfy hard constraints and optimize soft preferences.

The tool uses:
- DSPy for robust natural language → structured JSON extraction
- clingo ASP for constraint-based optimization on a 15-minute grid
"""

from typing import Dict, List, Optional, Any
from .schemas import (
    ResponseEnvelope,
    Proposal,
    Event,
    SchedulingProblem,
    Relaxation,
    DebugInfo,
)


def orchestrate_scheduling(
    utterance: str,
    events_by_participant: Dict[str, List[Dict[str, Any]]],
    context_json: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Orchestrate scheduling by finding optimal meeting times that satisfy constraints and preferences.
    
    This tool takes a natural language scheduling request, calendar events for all participants,
    and optional context (working hours, preferences, policies), then returns ready-to-schedule
    meeting proposals. The tool uses Answer Set Programming (ASP) to find optimal solutions that:
    - Satisfy hard constraints (no double bookings, work hours, minimum gaps)
    - Optimize soft preferences (minimize disruption, maximize focus blocks, respect timing preferences)
    
    Args:
        utterance: Natural language scheduling request (e.g., "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.")
        events_by_participant: Dictionary mapping participant IDs to lists of calendar events.
                              Each event should be a dict with keys: id, title, start, end, locked, protected, flexible.
                              Events should be expanded instances within the planning horizon.
        context_json: Optional dictionary containing:
                      - timeframe: {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"}
                      - participants: [{"id": "exec", "email": "me@acme.com", "work_hours": "M-F 09:00-17:30"}, ...]
                      - policy: {
                          "hard": {"min_gap_min": 10},
                          "soft": {
                            "maximize_focus_blocks": {"block_min": 90, "weight": 10},
                            "minimize_moves_of_existing": {"weight_per_min_shift": 2, "tier": "protected"},
                            "respect_others_prefs_weight": 3
                          },
                          "lexicographic_levels": ["feasibility", "protected_events", "move_costs", "focus_blocks"]
                        }
                      - slot_size_minutes: 15 (fixed for now)
    
    Returns:
        Dictionary with keys:
        - status: "ok" | "unsat" | "bad_input"
        - proposals: List of Proposal objects (typically one best proposal)
        - explanation: Human-readable explanation of the result
        - relaxations: List of Relaxation suggestions (if status is "unsat")
        - debug: DebugInfo with timing and statistics
        - error_message: Error message (if status is "bad_input")
    
    Example:
        >>> result = orchestrate_scheduling(
        ...     utterance="Find 45 minutes with Alex & Priya Tue–Thu mornings",
        ...     events_by_participant={
        ...         "exec": [{"id": "evt1", "title": "Standup", "start": "2025-11-25T14:00:00Z", "end": "2025-11-25T14:15:00Z", "locked": False}],
        ...         "alex": [...],
        ...         "priya": [...]
        ...     },
        ...     context_json={
        ...         "timeframe": {"from": "2025-11-24", "to": "2025-11-28", "tz": "America/New_York"},
        ...         "participants": [
        ...             {"id": "exec", "email": "me@acme.com", "work_hours": "M-F 09:00-17:30"}
        ...         ],
        ...         "policy": {"hard": {"min_gap_min": 15}}
        ...     }
        ... )
        >>> print(result["status"])
        'ok'
        >>> print(result["proposals"][0]["start_utc"])
        '2025-11-26T15:15:00Z'
    """
    # TODO: Implement in subsequent tasks
    # This is a stub that will be implemented by combining:
    # - Task 21-2: Event normalization
    # - Task 21-3: ASP encoding
    # - Task 21-4: ASP optimization
    # - Task 21-5: clingo wrapper
    # - Task 21-6: DSPy extraction
    # - Task 21-7: UNSAT handling
    # - Task 21-8: Assembly
    
    # For now, return a placeholder response
    if not events_by_participant:
        return ResponseEnvelope(
            status="bad_input",
            explanation="No events provided. Please call Get_Events for the desired horizon and all participants, then pass results as events_by_participant.",
            relaxations=[
                Relaxation(
                    description="Call Get_Events for [from,to] and all participants, pass results as events_by_participant",
                    expected_impact="high",
                    policy_change={},
                    rank=1
                )
            ],
            error_message="events_by_participant is empty"
        ).model_dump()
    
    # Placeholder response structure
    return ResponseEnvelope(
        status="ok",
        proposals=[],
        explanation="Tool implementation in progress. This is a placeholder response.",
        debug=DebugInfo()
    ).model_dump()

