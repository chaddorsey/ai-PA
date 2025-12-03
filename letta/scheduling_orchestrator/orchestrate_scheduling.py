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
        # Log function entry for debugging (stderr goes to Docker logs)
        import sys
        try:
            print(f"[orchestrate_scheduling] Function called", file=sys.stderr, flush=True)
        except:
            pass  # Don't fail if logging fails
        
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
        extraction_start = time.time()
        try:
            scheduling_problem = extract_with_fallback(utterance, context_json)
            extraction_time_ms = int((time.time() - extraction_start) * 1000)
            debug_info.extraction_time_ms = extraction_time_ms
            if extraction_time_ms == 0:
                print(f"[orchestrate_scheduling] WARNING: Extraction time is 0ms - DSPy may not have been used", file=sys.stderr, flush=True)
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to extract scheduling problem from utterance: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
        # Validate that all participants in scheduling problem have events (even if empty)
        missing_participants = [p for p in scheduling_problem.participants if p not in events_by_participant]
        if missing_participants:
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Missing events for participants: {', '.join(missing_participants)}. Please call Get_Events for all participants mentioned in the request.",
                proposals=[],
                error_message=f"Missing events for participants: {missing_participants}",
                debug=debug_info
            ).model_dump()
        
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
                        # IMPORTANT: Work hours must be RECALCULATED for the new horizon,
                        # not just shifted, because the new horizon starts at a different time.
                        # Shifting would preserve slot indices but not the actual time-of-day work hours.
                        work_hours_slots = normalized_data.get("work_hours_slots", {})
                        new_work_hours_slots = {}
                        
                        # Recalculate work hours for the new horizon using the context
                        if context_json_dict and "participants" in context_json_dict:
                            try:
                                from .normalizer import parse_work_hours
                            except (ImportError, ValueError):
                                try:
                                    from normalizer import parse_work_hours
                                except ImportError:
                                    from scheduling_orchestrator.normalizer import parse_work_hours
                            
                            import pytz
                            from datetime import timedelta
                            
                            # Default work hours are 9-5 Eastern time unless specified otherwise
                            default_work_hours_tz = "America/New_York"
                            
                            for participant in context_json_dict["participants"]:
                                participant_id = participant.get("id", "")
                                work_hours_str = participant.get("work_hours", "")
                                
                                # Determine timezone for work hours
                                if work_hours_str:
                                    # Participant has explicit work hours - use their timezone or timeframe timezone
                                    participant_timezone = participant.get("timezone")
                                    if not participant_timezone:
                                        participant_timezone = context_json_dict.get("timeframe", {}).get("tz", default_work_hours_tz)
                                    work_hours_tz = participant_timezone
                                else:
                                    # No explicit work hours - use default 9-5 Eastern
                                    work_hours_str = "M-F 09:00-17:00"
                                    work_hours_tz = default_work_hours_tz
                                
                                participant_tz = pytz.timezone(work_hours_tz)
                                
                                # Parse work hours
                                work_hours = parse_work_hours(work_hours_str, work_hours_tz)
                                
                                # Calculate work hours slots for the new horizon
                                work_slots = set()
                                current_date = original_start.replace(hour=0, minute=0, second=0, microsecond=0)
                                while current_date < original_end:
                                    current_date_local = current_date.astimezone(participant_tz)
                                    day_of_week = current_date_local.weekday()
                                    
                                    for day, start_hm, end_hm in work_hours:
                                        if day_of_week == day:
                                            start_hour = start_hm // 100
                                            start_min = start_hm % 100
                                            end_hour = end_hm // 100
                                            end_min = end_hm % 100
                                            
                                            work_start = current_date_local.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
                                            work_end = current_date_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
                                            
                                            # Convert to UTC
                                            work_start_utc = work_start.astimezone(pytz.UTC)
                                            work_end_utc = work_end.astimezone(pytz.UTC)
                                            
                                            # Get slots in new indexer
                                            work_period_slots = new_slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                                            work_slots.update(work_period_slots)
                                    
                                    current_date += timedelta(days=1)
                                
                                new_work_hours_slots[participant_id] = work_slots
                        else:
                            # Fallback: Recalculate using default 9-5 Eastern for participants not in context
                            # This ensures work hours are correctly aligned with the new horizon
                            try:
                                from .normalizer import parse_work_hours
                            except (ImportError, ValueError):
                                try:
                                    from normalizer import parse_work_hours
                                except ImportError:
                                    from scheduling_orchestrator.normalizer import parse_work_hours
                            
                            import pytz
                            from datetime import timedelta
                            
                            # For participants not in context_json, use default 9-5 Eastern
                            default_work_hours_tz = "America/New_York"
                            default_work_hours_str = "M-F 09:00-17:00"
                            
                            # First, shift existing work hours slots for participants we know about
                            for participant_id, slots in work_hours_slots.items():
                                new_slots = set()
                                for slot in slots:
                                    if min_slot <= slot <= max_slot:
                                        new_slots.add(slot - min_slot)
                                if new_slots:  # Only keep if there are slots in the new horizon
                                    new_work_hours_slots[participant_id] = new_slots
                            
                            # For any participants in the scheduling problem but not in work_hours_slots,
                            # recalculate using default 9-5 Eastern
                            # (This handles participants added dynamically)
                        
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
        
        # 4. Solve using pure Python constraint solver (replaces ASP/clingo)
        # This eliminates "too many messages" errors and handles common cases efficiently
        try:
            try:
                from .python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
            except (ImportError, ValueError):
                # Fallback to absolute imports (when run standalone or in Letta)
                import sys
                import os
                
                # Find the letta directory and add it to path
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
                    from scheduling_orchestrator.python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
                except ImportError:
                    # Last resort: try direct imports from orchestrator_dir
                    from python_solver import find_optimal_slot, compute_move_deltas_python, compute_objective_scores_python
            
            # Count free slots for debugging
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
            
            # Solve with Python solver
            # Ensure normalized_data uses the current slot_indexer (might have been reduced)
            normalized_data["slot_indexer"] = slot_indexer
            
            solve_start_time = time.time()
            solution = find_optimal_slot(
                normalized_data,
                scheduling_problem,
                slot_indexer,  # Pass the current slot_indexer (might be reduced)
                context_json
            )
            solve_time_ms = int((time.time() - solve_start_time) * 1000)
            debug_info.solve_time_ms = solve_time_ms
            
            if not solution:
                # No solution found - return UNSAT
                unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
                return ResponseEnvelope(
                    status="unsat",
                    explanation=unsat_info["explanation"],
                    proposals=[],
                    relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                    debug=debug_info
                ).model_dump()
            
            # Solution found - extract details
            start_slot = solution["start_slot"]
            
            # Validate slot is within bounds
            if start_slot < 0 or start_slot >= slot_indexer.total_slots:
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Invalid slot index {start_slot} (valid range: 0-{slot_indexer.total_slots-1})",
                    proposals=[],
                    error_message=f"Slot index out of bounds: {start_slot}",
                    debug=debug_info
                ).model_dump()
            
            # Validate slot_indexer is valid
            if not hasattr(slot_indexer, 'horizon_start') or not hasattr(slot_indexer, 'horizon_end'):
                return ResponseEnvelope(
                    status="bad_input",
                    explanation="Slot indexer is invalid (missing horizon_start or horizon_end)",
                    proposals=[],
                    error_message="Invalid slot_indexer",
                    debug=debug_info
                ).model_dump()
            
            start_dt = slot_indexer.slot_to_datetime(start_slot)
            duration_slots = max(1, scheduling_problem.duration_minutes // 15)
            end_slot = start_slot + duration_slots
            
            # Check if end_slot is within bounds
            # Note: end_slot can equal total_slots (meeting ends exactly at horizon boundary)
            if end_slot > slot_indexer.total_slots:
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Meeting end slot {end_slot} exceeds horizon (max: {slot_indexer.total_slots})",
                    proposals=[],
                    error_message=f"End slot out of bounds: {end_slot}",
                    debug=debug_info
                ).model_dump()
            
            # For end_slot == total_slots, calculate datetime manually (slot_indexer doesn't include it)
            if end_slot == slot_indexer.total_slots:
                # Meeting ends exactly at horizon boundary
                end_dt = slot_indexer.horizon_end
            else:
                end_dt = slot_indexer.slot_to_datetime(end_slot)
            
            if not start_dt or not end_dt:
                # Add more diagnostic info
                error_details = {
                    "start_slot": start_slot,
                    "end_slot": end_slot,
                    "total_slots": slot_indexer.total_slots,
                    "slot_indexer_horizon_start": str(slot_indexer.horizon_start) if hasattr(slot_indexer, 'horizon_start') else None,
                    "slot_indexer_horizon_end": str(slot_indexer.horizon_end) if hasattr(slot_indexer, 'horizon_end') else None,
                    "start_dt_result": str(start_dt) if start_dt else "None",
                    "end_dt_result": str(end_dt) if end_dt else "None"
                }
                # Add to debug_info if possible (might not have error_details field)
                try:
                    debug_info.error_details = error_details
                except:
                    pass
                return ResponseEnvelope(
                    status="bad_input",
                    explanation=f"Failed to convert slot to datetime. Start slot: {start_slot}, End slot: {end_slot}, Total slots: {slot_indexer.total_slots}. Start DT: {start_dt}, End DT: {end_dt}",
                    proposals=[],
                    error_message="Slot to datetime conversion failed",
                    debug=debug_info
                ).model_dump() | {"error_details": error_details}
            
            # Compute moved events and objective scores
            moved_events_list = compute_move_deltas_python(solution, normalized_data, scheduling_problem)
            moved_events = [MovedEvent(**me) for me in moved_events_list]
            
            objective_scores_dict = compute_objective_scores_python(solution, normalized_data, scheduling_problem)
            scores = ObjectiveScores(**objective_scores_dict)
            
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
            
            # Generate explanation
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
            
            # Return response
            debug_info.total_time_ms = int((time.time() - start_time) * 1000)
            
            result = ResponseEnvelope(
                status="ok",
                proposals=[proposal],
                explanation=explanation,
                debug=debug_info
            ).model_dump()
            
            # Ensure result is JSON-serializable before returning
            try:
                json.dumps(result)
            except (TypeError, ValueError) as ser_err:
                try:
                    import sys
                    print(f"[orchestrate_scheduling] JSON serialization error in success path: {ser_err}", file=sys.stderr, flush=True)
                except:
                    pass
                # Return a safe fallback
                return {
                    "status": "bad_input",
                    "explanation": f"Response serialization failed: {str(ser_err)}",
                    "proposals": [],
                    "error_message": "Internal error: response could not be serialized",
                    "debug": {"error_type": "SerializationError", "original_error": str(ser_err)}
                }
            
            return result
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to solve scheduling problem: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=debug_info
            ).model_dump() | {"error_traceback": error_traceback}
        
    except Exception as e:
        # Catch any unexpected errors and return them with full traceback
        # This should never happen if all code paths are properly handled, but it's a safety net
        error_traceback = traceback.format_exc()
        
        # Log to stderr (visible in Docker logs)
        try:
            import sys
            print(f"[orchestrate_scheduling] UNEXPECTED ERROR: {type(e).__name__}: {str(e)}", file=sys.stderr, flush=True)
            print(f"[orchestrate_scheduling] Traceback:\n{error_traceback}", file=sys.stderr, flush=True)
        except:
            pass  # Don't fail if logging fails
        
        # Try to use ResponseEnvelope if available, otherwise fall back to dict
        try:
            # ResponseEnvelope should be available from imports above
            result = ResponseEnvelope(
                status="bad_input",
                explanation=f"Unexpected error in orchestrate_scheduling: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=DebugInfo(
                    error_type=type(e).__name__,
                    error_traceback=error_traceback
                )
            ).model_dump() | {"error_traceback": error_traceback}
            
            # Ensure result is JSON-serializable
            try:
                json.dumps(result)
            except (TypeError, ValueError) as ser_err:
                try:
                    import sys
                    print(f"[orchestrate_scheduling] JSON serialization error in error path: {ser_err}", file=sys.stderr, flush=True)
                except:
                    pass
                # Return a safe fallback without traceback (which might not be serializable)
                return {
                    "status": "bad_input",
                    "explanation": f"Unexpected error: {str(e)}",
                    "proposals": [],
                    "error_message": str(e),
                    "debug": {"error_type": type(e).__name__}
                }
            
            return result
        except (NameError, Exception) as inner_e:
            # If ResponseEnvelope isn't available or fails, use dict
            try:
                import sys
                print(f"[orchestrate_scheduling] Failed to create ResponseEnvelope: {inner_e}", file=sys.stderr, flush=True)
            except:
                pass
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

