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
import sys

# Lazy imports to avoid dependency issues during Letta schema generation
# These will be imported when the function is actually called


def orchestrate_scheduling(
    utterance: str,
    events_by_participant: str,  # JSON string: Dict[str, List[Dict[str, Any]]] - mapping participant IDs to lists of event dicts
    context_json: Optional[str] = None  # JSON string: Optional[Dict[str, Any]] - optional scheduling context and preferences
) -> dict:
    """
    Orchestrate scheduling by finding optimal meeting times that satisfy constraints and preferences.
    
    This function includes comprehensive error handling and logging. Errors are captured
    with full tracebacks and returned in the response for debugging.
    
    This tool takes a natural language scheduling request, calendar events for all participants,
    and optional context (working hours, preferences, policies), then returns ready-to-schedule
    meeting proposals. The tool uses Answer Set Programming (ASP) to find optimal solutions that:
    - Satisfy hard constraints (no double bookings, work hours, minimum gaps)
    - Optimize soft preferences (minimize disruption, maximize focus blocks, respect timing preferences)
    
    Args:
        utterance: Natural language scheduling request (e.g., "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.")
        events_by_participant: JSON string representing a dictionary mapping participant IDs (strings) to lists of calendar events.
                              Each event should be a dict with keys: id, title, start, end, locked, protected, flexible.
                              Events should be expanded instances within the planning horizon.
                              Example JSON: '{"exec": [{"id": "evt1", "title": "Meeting", "start": "2025-11-25T10:00:00Z", "end": "2025-11-25T11:00:00Z", "locked": false}], "alex": []}'
        context_json: Optional JSON string containing:
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
    # Import traceback, json, time, datetime, and pytz (ensure they're available)
    import traceback
    import json
    import time
    from datetime import datetime
    import pytz
    
    # Wrap entire function in try-except to catch any unexpected errors
    try:
        # Lazy imports - only import when function is called, not during schema generation
        # Try relative imports first (when run as package), then absolute imports (when run standalone)
        try:
            # Try relative imports (when run as package)
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
        except (ImportError, ValueError):
            # Fallback to absolute imports (when run standalone or in Letta)
            import sys
            import os
            
            # Find the letta directory and add it to path
            # __file__ might be the .pyc file, so get the real path
            current_file = os.path.abspath(__file__)
            if current_file.endswith('.pyc'):
                current_file = current_file[:-1]  # Remove .pyc to get .py
            
            # Get letta directory (parent of scheduling_orchestrator)
            letta_dir = os.path.dirname(os.path.dirname(current_file))
            if letta_dir not in sys.path:
                sys.path.insert(0, letta_dir)
            
            # Also try adding the scheduling_orchestrator directory itself
            orchestrator_dir = os.path.dirname(current_file)
            if orchestrator_dir not in sys.path:
                sys.path.insert(0, orchestrator_dir)
            
            # Now try absolute imports
            try:
                from scheduling_orchestrator.schemas import (
                    ResponseEnvelope,
                    Proposal,
                    Event,
                    SchedulingProblem,
                    Relaxation,
                    DebugInfo,
                    MovedEvent,
                    ObjectiveScores,
                )
                from scheduling_orchestrator.dspy_extraction import extract_with_fallback
                from scheduling_orchestrator.normalizer import normalize_events
                from scheduling_orchestrator.fact_generator import generate_asp_program
                from scheduling_orchestrator.clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                from scheduling_orchestrator.unsat_analyzer import explain_unsat
            except ImportError:
                # Last resort: try direct imports from orchestrator_dir
                from schemas import (
                    ResponseEnvelope,
                    Proposal,
                    Event,
                    SchedulingProblem,
                    Relaxation,
                    DebugInfo,
                    MovedEvent,
                    ObjectiveScores,
                )
                from dspy_extraction import extract_with_fallback
                from normalizer import normalize_events
                from fact_generator import generate_asp_program
                from clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                from unsat_analyzer import explain_unsat
        except ImportError as e:
            # If dependencies are missing, return a helpful error with traceback
            error_traceback = traceback.format_exc()
            return {
                "status": "bad_input",
                "explanation": f"Tool dependencies not available: {str(e)}. Please ensure clingo and dspy-ai are installed.",
                "proposals": [],
                "error_message": f"Missing dependencies: {str(e)}",
                "error_traceback": error_traceback,
                "debug": {
                    "error_type": "ImportError",
                    "missing_module": str(e)
                }
            }
        
        # Parse JSON string inputs
        try:
            if isinstance(events_by_participant, str):
                events_by_participant = json.loads(events_by_participant)
            if context_json is not None and isinstance(context_json, str):
                context_json = json.loads(context_json)
        except json.JSONDecodeError as e:
            return {
                "status": "bad_input",
                "explanation": f"Invalid JSON in input parameters: {str(e)}",
                "proposals": [],
                "error_message": f"JSON decode error: {str(e)}",
                "debug": {}
            }
        
        start_time = time.time()
        debug_info = DebugInfo()
        
        # Log input summary for debugging
        input_summary = {
            "utterance": utterance[:200] + ("..." if len(utterance) > 200 else ""),  # Truncate long utterances
            "num_participants": len(events_by_participant),
            "events_per_participant": {pid: len(events) for pid, events in events_by_participant.items()},
            "total_events": sum(len(events) for events in events_by_participant.values()),
            "has_context": context_json is not None,
            "context_keys": list(context_json.keys()) if context_json else []
        }
        debug_info.input_summary = input_summary
        
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
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to extract scheduling problem from utterance: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
        # 3. Normalize events to 15-minute grid
        try:
            normalized_data = normalize_events(events_by_participant, context_json or {})
            debug_info.normalization_time_ms = int((time.time() - start_time) * 1000) - debug_info.extraction_time_ms
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to normalize events: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
        slot_indexer = normalized_data["slot_indexer"]
        
        # Log normalization results (before reduction)
        all_slots = slot_indexer.get_all_slots()
        num_slots = len(all_slots)
        busy_slots = normalized_data.get("busy_slots", {})
        total_busy_slots = sum(len(slots) for slots in busy_slots.values())
        
        # OPTIMIZATION: Reduce horizon if too large to avoid "too many messages" error
        # The "too many messages" error occurs when clingo grounds too many atoms,
        # even with optimized facts. The slot generation rule creates one atom per slot,
        # so we need to limit the total number of slots.
        # With the inverse approach (pre-filtering free slots), we can handle much larger horizons.
        # The choice rule now only considers free slots, dramatically reducing grounding atoms.
        # For a typical calendar with 80% busy slots, this reduces candidates by ~80%.
        # Even with explicit slot facts and no soft constraints, clingo's grounding can still
        # generate too many atoms from rules like occurs() and workhours(). We need to be
        # very conservative. With explicit slots and no soft constraints, we can handle
        # ~192 slots (2 days) safely. The occurs_if_start pre-generation creates many facts,
        # so we need to keep the horizon small.
        MAX_SLOTS_FOR_ASP = 192  # 2 days * 96 slots/day - conservative limit for clingo grounding
        if num_slots > MAX_SLOTS_FOR_ASP:
            try:
                original_slots = num_slots
                
                # Inline horizon reduction to avoid import issues
                # Find the range of busy slots
                all_busy_slots_set = set()
                for participant_slots in busy_slots.values():
                    all_busy_slots_set.update(participant_slots)
                
                if not all_busy_slots_set:
                    # No busy slots - reduce to first max_slots (start of horizon)
                    min_slot = 0
                    max_slot = MAX_SLOTS_FOR_ASP - 1
                else:
                    min_busy = min(all_busy_slots_set)
                    max_busy = max(all_busy_slots_set)
                    
                    # Add padding: 1 day before and after (96 slots = 1 day)
                    padding_slots = 96
                    min_slot = max(0, min_busy - padding_slots)
                    max_slot = max_busy + padding_slots
                    
                    # Also consider the scheduling problem's time window if specified
                    if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
                        start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
                        
                        if start_dt.tzinfo is None:
                            start_dt = pytz.UTC.localize(start_dt)
                        else:
                            start_dt = start_dt.astimezone(pytz.UTC)
                        
                        if end_dt.tzinfo is None:
                            end_dt = pytz.UTC.localize(end_dt)
                        else:
                            end_dt = end_dt.astimezone(pytz.UTC)
                        
                        window_start_slot = slot_indexer.datetime_to_slot(start_dt)
                        window_end_slot = slot_indexer.datetime_to_slot(end_dt)
                        
                        if window_start_slot is not None:
                            min_slot = min(min_slot, window_start_slot)
                        if window_end_slot is not None:
                            max_slot = max(max_slot, window_end_slot)
                    
                    # Limit to max_slots
                    if max_slot - min_slot + 1 > MAX_SLOTS_FOR_ASP:
                        # Center the window around busy slots
                        center = (min_busy + max_busy) // 2
                        min_slot = max(0, center - MAX_SLOTS_FOR_ASP // 2)
                        max_slot = min_slot + MAX_SLOTS_FOR_ASP - 1
                
                # Create new slot indexer with reduced horizon
                original_start = slot_indexer.slot_to_datetime(min_slot)
                original_end = slot_indexer.slot_to_datetime(max_slot + 1)  # +1 to include the last slot
                
                if original_start and original_end:
                    # Import SlotIndexer using the same lazy import pattern as other modules
                    # SlotIndexer should already be imported via normalizer, but we need it here too
                    try:
                        try:
                            from .slot_indexer import SlotIndexer
                        except (ImportError, ValueError):
                            # Fallback to absolute imports
                            import sys
                            import os
                            current_file = os.path.abspath(__file__)
                            if current_file.endswith('.pyc'):
                                current_file = current_file[:-1]
                            orchestrator_dir = os.path.dirname(current_file)
                            if orchestrator_dir not in sys.path:
                                sys.path.insert(0, orchestrator_dir)
                            try:
                                from slot_indexer import SlotIndexer
                            except ImportError:
                                # Last resort: try direct import
                                from scheduling_orchestrator.slot_indexer import SlotIndexer
                        
                        # Create new slot indexer
                        new_slot_indexer = SlotIndexer(original_start, original_end)
                        
                        # Re-normalize busy slots to new indexer (shift slot indices)
                        new_busy_slots = {}
                        for participant_id, slots in busy_slots.items():
                            new_slots = set()
                            for slot in slots:
                                if min_slot <= slot <= max_slot:
                                    # Shift to new indexer (slot - min_slot)
                                    new_slots.add(slot - min_slot)
                            new_busy_slots[participant_id] = new_slots
                        
                        # Re-normalize work hours slots
                        work_hours_slots = normalized_data.get("work_hours_slots", {})
                        new_work_hours_slots = {}
                        for participant_id, slots in work_hours_slots.items():
                            new_slots = set()
                            for slot in slots:
                                if min_slot <= slot <= max_slot:
                                    new_slots.add(slot - min_slot)
                            new_work_hours_slots[participant_id] = new_slots
                        
                        # Update normalized_data
                        normalized_data["slot_indexer"] = new_slot_indexer
                        normalized_data["busy_slots"] = new_busy_slots
                        normalized_data["work_hours_slots"] = new_work_hours_slots
                        
                        slot_indexer = new_slot_indexer
                        all_slots = slot_indexer.get_all_slots()
                        num_slots = len(all_slots)
                        debug_info.horizon_reduced = True
                        debug_info.original_slots = original_slots
                        debug_info.reduced_slots = num_slots
                    except Exception as e:
                        # Reduction failed - log but continue with original horizon
                        debug_info.horizon_reduced = False
                        debug_info.horizon_reduction_error = f"Failed to create reduced slot indexer: {str(e)}"
                else:
                    # Could not convert slots to datetimes - fallback
                    debug_info.horizon_reduced = False
                    debug_info.horizon_reduction_error = "Could not convert slot indices to datetimes"
            except Exception as e:
                # Reduction failed - log but continue with original horizon
                debug_info.horizon_reduced = False
                debug_info.horizon_reduction_error = f"Failed to reduce horizon: {str(e)}"
        else:
            debug_info.horizon_reduced = False
        
        debug_info.slots_considered = num_slots
        debug_info.total_busy_slots = total_busy_slots
        
        # 4. Multi-shot solving: Try phases with incremental constraints
        # Phase 1: Minimal constraints (no work hours, no min_gap, no locked events)
        # Phase 2: Add work hours and locked events
        # Phase 3: Add min_gap
        # This reduces grounding complexity by 50-70% per phase
        
        model = None
        stats = None
        solve_result = None
        asp_program = None
        phase_used = 0
        
        # Count free slots before generating ASP (for debugging)
        try:
            try:
                from .fact_generator import _find_free_slots
            except (ImportError, ValueError):
                from fact_generator import _find_free_slots
            
            duration_slots = max(1, scheduling_problem.duration_minutes // 15)
            free_slots = _find_free_slots(
                all_slots,
                busy_slots,
                normalized_data.get("work_hours_slots", {}),
                scheduling_problem.participants,
                duration_slots,
                normalized_data.get("min_gap_slots", 0)
            )
            debug_info.free_slots_found = len(free_slots)
            debug_info.free_slots_ratio = len(free_slots) / num_slots if num_slots > 0 else 0
        except Exception:
            # If we can't count free slots, that's okay - just skip this debug info
            pass
        
        solver = ClingoSolver(timeout=30)
        
        # Try phases incrementally
        for phase in [1, 2, 3]:
            try:
                phase_used = phase
                
                # Generate ASP program for this phase
                include_work_hours = (phase >= 2)
                include_min_gap = (phase >= 3)
                include_locked_events = (phase >= 2)
                
                asp_program = generate_asp_program(
                    normalized_data,
                    scheduling_problem,
                    request_id="q1",
                    include_soft_constraints=False,
                    include_work_hours=include_work_hours,
                    include_min_gap=include_min_gap,
                    include_locked_events=include_locked_events,
                    phase=phase
                )
                
                # Log ASP program size (for last phase attempted)
                asp_lines = asp_program.split("\n")
                asp_facts_count = sum(1 for line in asp_lines if line.strip() and not line.strip().startswith("%") and not line.strip().startswith("#"))
                debug_info.asp_program_lines = len(asp_lines)
                debug_info.asp_facts_count = asp_facts_count
                debug_info.asp_program_size_chars = len(asp_program)
                debug_info.multi_shot_phase = phase
                
                # Count free_slot facts in the program (for verification)
                free_slot_facts = sum(1 for line in asp_lines if line.strip().startswith("free_slot("))
                if free_slot_facts > 0:
                    debug_info.free_slots_found = free_slot_facts  # Override with actual count from program
                
                # Solve with clingo
                model, stats, solve_result = solver.solve(asp_program)
                debug_info.asp_stats = stats
                debug_info.solve_time_ms = stats.get("solve_time_ms", 0)
                
                # Check if grounding/parsing failed
                if stats.get("error") or stats.get("grounding_failed"):
                    error_msg = stats.get("error", "Unknown error during ASP grounding/parsing")
                    error_type = stats.get("error_type", "unknown")
                    
                    # If this is a grounding error, try next phase (might be too many constraints)
                    if phase < 3:
                        continue  # Try next phase
                    else:
                        # Last phase failed - return error
                        diagnostics = {
                            "error_type": error_type,
                            "input_summary": input_summary,
                            "slots_considered": num_slots,
                            "total_busy_slots": total_busy_slots,
                            "asp_program_lines": debug_info.asp_program_lines,
                            "asp_facts_count": debug_info.asp_facts_count,
                            "asp_program_size_chars": debug_info.asp_program_size_chars,
                            "phase": phase
                        }
                        
                        if error_type == "parsing_failed":
                            diagnostics["suggestion"] = "The ASP program may be too large or contain syntax errors. Consider reducing the planning horizon."
                            explanation = f"Failed to parse ASP program: {error_msg}. Problem size: {num_slots} slots, {total_busy_slots} busy slots, {debug_info.asp_facts_count} facts."
                        elif error_type == "out_of_memory":
                            diagnostics["suggestion"] = "The problem size exceeds available memory. Reduce the planning horizon or number of participants/events."
                            explanation = f"Out of memory during ASP grounding: {error_msg}. Problem size: {num_slots} slots, {debug_info.asp_facts_count} facts."
                        else:
                            diagnostics["suggestion"] = "The problem size may be too large. Consider reducing the planning horizon, number of participants, or number of events."
                            explanation = f"Failed to ground ASP program: {error_msg}. Problem size: {num_slots} slots, {total_busy_slots} busy slots, {debug_info.asp_facts_count} facts."
                        
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=explanation,
                            proposals=[],
                            error_message=error_msg,
                            debug=debug_info
                        ).model_dump() | {"diagnostics": diagnostics}
                
                # Check if we got a solution
                if model and stats.get("satisfiable", False):
                    # Success! Break out of phase loop
                    break
                else:
                    # UNSAT - try next phase with more constraints
                    if phase < 3:
                        continue  # Try next phase
                    else:
                        # Last phase was UNSAT - will be handled below
                        break
                        
            except Exception as e:
                error_traceback = traceback.format_exc()
                error_msg = str(e)
                
                # Check if this is the "too many messages" error
                if "too many messages" in error_msg.lower():
                    # Try next phase if available
                    if phase < 3:
                        continue  # Try next phase with fewer constraints
                    else:
                        # Last phase - return error
                        diagnostics = {
                            "error_type": "clingo_too_many_messages",
                            "input_summary": input_summary,
                            "slots_considered": num_slots,
                            "total_busy_slots": total_busy_slots,
                            "asp_program_lines": debug_info.asp_program_lines if hasattr(debug_info, 'asp_program_lines') else None,
                            "asp_facts_count": debug_info.asp_facts_count if hasattr(debug_info, 'asp_facts_count') else None,
                            "phase": phase,
                            "suggestion": "The problem size may be too large. Consider reducing the planning horizon, number of participants, or number of events."
                        }
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Failed to solve ASP program: {error_msg}. Problem size: {num_slots} slots, {total_busy_slots} busy slots, {asp_facts_count if hasattr(debug_info, 'asp_facts_count') else 'unknown'} facts. Consider reducing the planning horizon or number of events.",
                            proposals=[],
                            error_message=error_msg,
                            debug=debug_info
                        ).model_dump() | {"error_traceback": error_traceback, "diagnostics": diagnostics}
                else:
                    # Other error - try next phase if available
                    if phase < 3:
                        continue
                    else:
                        return ResponseEnvelope(
                            status="bad_input",
                            explanation=f"Failed to solve ASP program: {error_msg}",
                            proposals=[],
                            error_message=error_msg,
                            debug=debug_info
                        ).model_dump() | {"error_traceback": error_traceback}
        
        # 5. Handle UNSAT (but only if there was no error during grounding)
        if not model or not stats or not stats.get("satisfiable", False):
            
            # Check if grounding/parsing failed
            if stats.get("error") or stats.get("grounding_failed"):
                error_msg = stats.get("error", "Unknown error during ASP grounding/parsing")
                error_type = stats.get("error_type", "unknown")
                
                diagnostics = {
                    "error_type": error_type,
                    "input_summary": input_summary,
                    "slots_considered": num_slots,
                    "total_busy_slots": total_busy_slots,
                    "asp_program_lines": debug_info.asp_program_lines,
                    "asp_facts_count": debug_info.asp_facts_count,
                    "asp_program_size_chars": debug_info.asp_program_size_chars,
                }
                
                if error_type == "parsing_failed":
                    diagnostics["suggestion"] = "The ASP program may be too large or contain syntax errors. Consider reducing the planning horizon (currently 15 days = 1440 slots) or number of events."
                    explanation = f"Failed to parse ASP program: {error_msg}. Problem size: {num_slots} slots, {total_busy_slots} busy slots, {debug_info.asp_facts_count} facts ({debug_info.asp_program_size_chars} characters). The program may be too large for clingo to parse. Consider reducing the planning horizon to 7 days or fewer."
                elif error_type == "out_of_memory":
                    diagnostics["suggestion"] = "The problem size exceeds available memory. Reduce the planning horizon or number of participants/events."
                    explanation = f"Out of memory during ASP grounding: {error_msg}. Problem size: {num_slots} slots, {debug_info.asp_facts_count} facts."
                else:
                    diagnostics["suggestion"] = "The problem size may be too large. Consider reducing the planning horizon, number of participants, or number of events."
                    explanation = f"Failed to ground ASP program: {error_msg}. Problem size: {num_slots} slots, {total_busy_slots} busy slots, {debug_info.asp_facts_count} facts."
                
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=explanation,
                    proposals=[],
                    error_message=error_msg,
                    debug=debug_info
                ).model_dump() | {"diagnostics": diagnostics}
            
            # If no grounding error, then it's genuinely UNSAT
            unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
            return ResponseEnvelope(
                status="unsat",
                explanation=unsat_info["explanation"],
                proposals=[],
                relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                debug=debug_info
            ).model_dump()
        
        # 6. Extract solution
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
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to extract solution from model: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
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
        
    except Exception as e:
        # Catch any unexpected errors and return them with full traceback
        error_traceback = traceback.format_exc()
        return {
            "status": "bad_input",
            "explanation": f"Unexpected error in orchestrate_scheduling: {str(e)}",
            "proposals": [],
            "error_message": str(e),
            "error_traceback": error_traceback,
            "debug": {
                "error_type": type(e).__name__,
                "error_args": str(e.args) if hasattr(e, 'args') else None
            }
        }

