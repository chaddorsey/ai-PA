"""
Scheduling Orchestration Tool for Letta

This tool takes natural language scheduling requests plus calendar events and returns
ready-to-schedule meeting proposals that satisfy hard constraints and optimize soft preferences.

The tool uses:
- DSPy for robust natural language → structured JSON extraction
- clingo ASP for constraint-based optimization on a 15-minute grid
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time
from .schemas import (
    ResponseEnvelope,
    Proposal,
    Event,
    SchedulingProblem,
    Relaxation,
    DebugInfo,
    MovedEvent,
    ObjectiveScores,
)
from .dspy_extraction import extract_with_fallback
from .normalizer import normalize_events
from .fact_generator import generate_asp_program
from .clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
from .unsat_analyzer import explain_unsat


def orchestrate_scheduling(
    utterance: str,
    events_by_participant: dict,  # Dict[str, List[Dict[str, Any]]] - mapping participant IDs to lists of event dicts
    context_json: Optional[dict] = None  # Dict[str, Any] - optional scheduling context and preferences
) -> dict:
    """
    Orchestrate scheduling by finding optimal meeting times that satisfy constraints and preferences.
    
    This tool takes a natural language scheduling request, calendar events for all participants,
    and optional context (working hours, preferences, policies), then returns ready-to-schedule
    meeting proposals. The tool uses Answer Set Programming (ASP) to find optimal solutions that:
    - Satisfy hard constraints (no double bookings, work hours, minimum gaps)
    - Optimize soft preferences (minimize disruption, maximize focus blocks, respect timing preferences)
    
    Args:
        utterance: Natural language scheduling request (e.g., "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.")
        events_by_participant: Dictionary mapping participant IDs (strings) to lists of calendar events (list of dicts).
                              Each event should be a dict with keys: id, title, start, end, locked, protected, flexible.
                              Events should be expanded instances within the planning horizon.
                              Example: {"exec": [{"id": "evt1", "title": "Meeting", "start": "2025-11-25T10:00:00Z", "end": "2025-11-25T11:00:00Z", "locked": False}], "alex": [...]}
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
    start_time = time.time()
    debug_info = DebugInfo()
    
    # 1. Validate inputs
    if not events_by_participant:
        return ResponseEnvelope(
            status="bad_input",
            explanation="No events provided. Please call Get_Events for the desired horizon and all participants, then pass results as events_by_participant.",
            proposals=[],
            relaxations=[
                Relaxation(
                    description="Call Get_Events for [from,to] and all participants, pass results as events_by_participant",
                    expected_impact="high",
                    policy_change={},
                    rank=1
                )
            ],
            error_message="events_by_participant is empty",
            debug=debug_info
        ).model_dump()
    
    # Bounds checking
    MAX_PARTICIPANTS = 10
    MAX_EVENTS_PER_PARTICIPANT = 100
    MAX_HORIZON_DAYS = 28  # 4 weeks
    
    if context_json and "timeframe" in context_json:
        try:
            from_dt = datetime.fromisoformat(context_json["timeframe"]["from"])
            to_dt = datetime.fromisoformat(context_json["timeframe"]["to"])
            horizon_days = (to_dt - from_dt).days
            if horizon_days > MAX_HORIZON_DAYS:
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Planning horizon ({horizon_days} days) exceeds maximum ({MAX_HORIZON_DAYS} days).",
                    proposals=[],
                    error_message=f"Horizon too large: {horizon_days} days",
                    debug=debug_info
                ).model_dump()
        except Exception:
            pass
    
    if len(events_by_participant) > MAX_PARTICIPANTS:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Number of participants ({len(events_by_participant)}) exceeds maximum ({MAX_PARTICIPANTS}).",
            proposals=[],
            error_message=f"Too many participants: {len(events_by_participant)}",
            debug=debug_info
        ).model_dump()
    
    for participant_id, events in events_by_participant.items():
        if len(events) > MAX_EVENTS_PER_PARTICIPANT:
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Participant {participant_id} has {len(events)} events, exceeding maximum ({MAX_EVENTS_PER_PARTICIPANT}).",
                proposals=[],
                error_message=f"Too many events for {participant_id}: {len(events)}",
                debug=debug_info
            ).model_dump()
    
    # 2. Extract scheduling problem from utterance using DSPy
    try:
        scheduling_problem = extract_with_fallback(utterance, context_json)
        debug_info.extraction_time_ms = int((time.time() - start_time) * 1000)
    except Exception as e:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Failed to extract scheduling problem from utterance: {str(e)}",
            proposals=[],
            error_message=str(e),
            debug=debug_info
        ).model_dump()
    
    # 3. Normalize events to 15-minute grid
    try:
        normalized_data = normalize_events(events_by_participant, context_json or {})
        debug_info.normalization_time_ms = int((time.time() - start_time) * 1000) - debug_info.extraction_time_ms
    except Exception as e:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Failed to normalize events: {str(e)}",
            proposals=[],
            error_message=str(e),
            debug=debug_info
        ).model_dump()
    
    slot_indexer = normalized_data["slot_indexer"]
    
    # 4. Generate ASP program
    try:
        asp_program = generate_asp_program(
            normalized_data,
            scheduling_problem,
            request_id="q1",
            include_soft_constraints=True
        )
        debug_info.asp_generation_time_ms = int((time.time() - start_time) * 1000) - debug_info.normalization_time_ms
    except Exception as e:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Failed to generate ASP program: {str(e)}",
            proposals=[],
            error_message=str(e),
            debug=debug_info
        ).model_dump()
    
    # 5. Solve with clingo
    solver = ClingoSolver(timeout=30)
    try:
        model, stats, solve_result = solver.solve(asp_program)
        debug_info.asp_stats = stats
        debug_info.solve_time_ms = stats.get("solve_time_ms", 0)
    except Exception as e:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Failed to solve ASP program: {str(e)}",
            proposals=[],
            error_message=str(e),
            debug=debug_info
        ).model_dump()
    
    # 6. Handle UNSAT
    if not model or not stats.get("satisfiable", False):
        unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
        return ResponseEnvelope(
            status="unsat",
            explanation=unsat_info["explanation"],
            proposals=[],
            relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
            debug=debug_info
        ).model_dump()
    
    # 7. Extract solution
    try:
        solution = extract_scheduling_solution(model, request_id="q1")
        if not solution:
            # Fallback: try to extract from occurs predicates
            unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
            return ResponseEnvelope(
                status="unsat",
                explanation="No valid solution found in model. " + unsat_info["explanation"],
                proposals=[],
                relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                debug=debug_info
            ).model_dump()
    except Exception as e:
        return ResponseEnvelope(
            status="bad_input",
            explanation=f"Failed to extract solution from model: {str(e)}",
            proposals=[],
            error_message=str(e),
            debug=debug_info
        ).model_dump()
    
    # 8. Build proposal
    start_slot = solution["start_slot"]
    start_dt = slot_indexer.slot_to_datetime(start_slot)
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    end_dt = slot_indexer.slot_to_datetime(start_slot + duration_slots)
    
    if not start_dt or not end_dt:
        return ResponseEnvelope(
            status="bad_input",
            explanation="Failed to convert slot to datetime",
            proposals=[],
            error_message="Slot to datetime conversion failed",
            debug=debug_info
        ).model_dump()
    
    # Compute moved events
    moved_events_list = compute_move_deltas(solution, normalized_data, scheduling_problem)
    moved_events = [MovedEvent(**me) for me in moved_events_list]
    
    # Compute objective scores
    objective_scores = compute_objective_scores(model, solution, normalized_data)
    scores = ObjectiveScores(**objective_scores)
    
    # Build proposal
    proposal = Proposal(
        title=scheduling_problem.title or "Meeting",
        participants=scheduling_problem.participants,
        start_utc=start_dt.isoformat(),
        end_utc=end_dt.isoformat(),
        moved_events=moved_events,
        objective_scores=scores,
        location=scheduling_problem.location
    )
    
    # 9. Generate explanation
    explanation_parts = [
        f"Found optimal meeting time: {start_dt.strftime('%Y-%m-%d %H:%M')} UTC"
    ]
    
    if moved_events:
        explanation_parts.append(f"Requires moving {len(moved_events)} event(s):")
        for me in moved_events[:3]:  # Show first 3
            explanation_parts.append(f"  - {me.owner}: {me.shift_minutes} minutes")
    
    if scores.focus_block_bonus and scores.focus_block_bonus > 0:
        explanation_parts.append(f"Creates {scores.focus_block_bonus} minutes of focus time")
    
    explanation = ". ".join(explanation_parts) + "."
    
    # 10. Return response
    debug_info.total_time_ms = int((time.time() - start_time) * 1000)
    
    return ResponseEnvelope(
        status="ok",
        proposals=[proposal],
        explanation=explanation,
        debug=debug_info
    ).model_dump()

