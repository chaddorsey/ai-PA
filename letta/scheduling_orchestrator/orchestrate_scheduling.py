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
            
            # Save original normalized_data before any horizon reduction
            # ASP fallback needs the original data, not the reduced version used by Python solver
            original_normalized_data = normalized_data.copy()
            
            # Save original normalized_data before any horizon reduction
            # ASP fallback needs the original data, not the reduced version
            original_normalized_data = normalized_data.copy()
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
        
        # CRITICAL: Ensure all participants in scheduling_problem have work hours defined
        # Normalization might miss participants that are in the problem but not in events/context
        # Apply default 9-5 Eastern for any missing participants
        work_hours_slots = normalized_data.get("work_hours_slots", {})
        
        for participant_id in scheduling_problem.participants:
            if participant_id not in work_hours_slots or not work_hours_slots[participant_id]:
                # Participant missing work hours - apply default 9-5 Eastern
                try:
                    from .normalizer import parse_work_hours
                except (ImportError, ValueError):
                    try:
                        from normalizer import parse_work_hours
                    except ImportError:
                        from scheduling_orchestrator.normalizer import parse_work_hours
                
                import pytz
                from datetime import timedelta
                
                default_work_hours_tz = "America/New_York"
                default_work_hours_str = "M-F 09:00-17:00"
                participant_tz = pytz.timezone(default_work_hours_tz)
                work_hours = parse_work_hours(default_work_hours_str, default_work_hours_tz)
                
                work_slots = set()
                from_date_utc = slot_indexer.horizon_start
                to_date_utc = slot_indexer.horizon_end
                current_date = from_date_utc.replace(hour=0, minute=0, second=0, microsecond=0)
                while current_date < to_date_utc:
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
                            
                            # Get slots
                            work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                            work_slots.update(work_period_slots)
                    
                    current_date += timedelta(days=1)
                
                work_hours_slots[participant_id] = work_slots
                normalized_data["work_hours_slots"] = work_hours_slots
        
        # Log normalization results (before reduction)
        all_slots = slot_indexer.get_all_slots()
        num_slots = len(all_slots)
        busy_slots = normalized_data.get("busy_slots", {})
        total_busy_slots = sum(len(slots) for slots in busy_slots.values())
        
        # OPTIMIZATION: Reduce horizon if too large to avoid "too many messages" error
        # The "too many messages" error occurs when clingo grounds too many atoms,
        # even with optimized facts. For multi-move scenarios (allow_overlaps), we need
        # to be even more conservative because we generate facts for all work-hours slots.
        # Strategy:
        # 1. Try Python solver first (handles free slots + single-move efficiently)
        # 2. If Python fails, reduce horizon aggressively before ASP fallback
        # 3. For multi-move, use tighter limits (fewer candidate slots)
        
        # Check if we'll need ASP fallback (no free slots)
        duration_slots = max(1, scheduling_problem.duration_minutes // 15)
        try:
            from .fact_generator import _find_free_slots
        except (ImportError, ValueError):
            from fact_generator import _find_free_slots
        
        free_slots_check = _find_free_slots(
            all_slots,
            busy_slots,
            normalized_data.get("work_hours_slots", {}),
            scheduling_problem.participants,
            duration_slots,
            normalized_data.get("min_gap_slots", 0)
        )
        
        # Determine max slots based on whether ASP fallback will be needed
        if not free_slots_check:
            # No free slots - ASP fallback will be needed, use tighter limit
            # For multi-move, we generate facts for all work-hours slots, so need smaller horizon
            MAX_SLOTS_FOR_ASP = 96  # 1 day * 96 slots/day - very conservative for multi-move
        else:
            # Free slots exist - Python solver should handle it, but prepare for ASP just in case
            MAX_SLOTS_FOR_ASP = 192  # 2 days * 96 slots/day - normal limit
        
        if num_slots > MAX_SLOTS_FOR_ASP:
            try:
                original_slots = num_slots
                
                # Inline horizon reduction to avoid import issues
                # Strategy: Prioritize time window if specified (more aggressive reduction)
                min_slot = None
                max_slot = None
                
                # First, try to use time window if specified
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
                    
                    if window_start_slot is not None and window_end_slot is not None:
                        # Use time window as base
                        min_slot = window_start_slot
                        max_slot = window_end_slot
                        
                        # Add small padding (4 hours = 16 slots) to allow for moves
                        padding_slots = 16
                        min_slot = max(0, min_slot - padding_slots)
                        max_slot = min(num_slots - 1, max_slot + padding_slots)
                        
                        # If still too large, limit to max_slots centered on time window
                        if max_slot - min_slot + 1 > MAX_SLOTS_FOR_ASP:
                            center = (window_start_slot + window_end_slot) // 2
                            min_slot = max(0, center - MAX_SLOTS_FOR_ASP // 2)
                            max_slot = min(num_slots - 1, min_slot + MAX_SLOTS_FOR_ASP - 1)
                
                # Fallback to busy slots strategy if time window didn't work
                if min_slot is None or max_slot is None:
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
                        max_slot = min(num_slots - 1, max_busy + padding_slots)
                        
                        # Limit to max_slots
                        if max_slot - min_slot + 1 > MAX_SLOTS_FOR_ASP:
                            # Center the window around busy slots
                            center = (min_busy + max_busy) // 2
                            min_slot = max(0, center - MAX_SLOTS_FOR_ASP // 2)
                            max_slot = min(num_slots - 1, min_slot + MAX_SLOTS_FOR_ASP - 1)
                
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
                        # Parse context_json if it's a string
                        context_dict = context_json
                        if isinstance(context_json, str):
                            try:
                                context_dict = json.loads(context_json)
                            except:
                                context_dict = {}
                        
                        if context_dict and "participants" in context_dict:
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
                            
                            for participant in context_dict["participants"]:
                                participant_id = participant.get("id", "")
                                work_hours_str = participant.get("work_hours", "")
                                
                                # Determine timezone for work hours
                                if work_hours_str:
                                    # Participant has explicit work hours - use their timezone or timeframe timezone
                                    participant_timezone = participant.get("timezone")
                                    if not participant_timezone:
                                        participant_timezone = context_dict.get("timeframe", {}).get("tz", default_work_hours_tz)
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
                        
                        # CRITICAL: Ensure ALL participants in the scheduling problem have work hours
                        # If any participant is missing from new_work_hours_slots, recalculate using defaults
                        default_work_hours_tz = "America/New_York"
                        default_work_hours_str = "M-F 09:00-17:00"
                        
                        for participant_id in scheduling_problem.participants:
                            if participant_id not in new_work_hours_slots:
                                # Participant missing - recalculate using default 9-5 Eastern
                                try:
                                    from .normalizer import parse_work_hours
                                except (ImportError, ValueError):
                                    try:
                                        from normalizer import parse_work_hours
                                    except ImportError:
                                        from scheduling_orchestrator.normalizer import parse_work_hours
                                
                                import pytz
                                from datetime import timedelta
                                
                                participant_tz = pytz.timezone(default_work_hours_tz)
                                work_hours = parse_work_hours(default_work_hours_str, default_work_hours_tz)
                                
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
                        
                        # CRITICAL: Ensure ALL participants in scheduling_problem have work hours defined
                        # After horizon reduction, some participants might be missing work hours
                        # Apply default 9-5 Eastern for any missing participants
                        default_work_hours_tz = "America/New_York"
                        default_work_hours_str = "M-F 09:00-17:00"
                        
                        for participant_id in scheduling_problem.participants:
                            if participant_id not in new_work_hours_slots or not new_work_hours_slots[participant_id]:
                                # Participant missing work hours - apply default 9-5 Eastern
                                try:
                                    from .normalizer import parse_work_hours
                                except (ImportError, ValueError):
                                    try:
                                        from normalizer import parse_work_hours
                                    except ImportError:
                                        from scheduling_orchestrator.normalizer import parse_work_hours
                                
                                import pytz
                                from datetime import timedelta
                                
                                participant_tz = pytz.timezone(default_work_hours_tz)
                                work_hours = parse_work_hours(default_work_hours_str, default_work_hours_tz)
                                
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
            # CRITICAL: Use original_normalized_data for Python solver to ensure we don't lose solutions
            # due to horizon reduction. The Python solver can handle the full horizon efficiently.
            # Only use reduced horizon for ASP fallback (which has stricter memory/time constraints)
            python_normalized_data = original_normalized_data.copy()
            python_slot_indexer = original_normalized_data["slot_indexer"]
            
            solve_start_time = time.time()
            # Try to find multiple solutions for diversity
            try:
                from .python_solver import find_top_candidates
            except (ImportError, ValueError):
                try:
                    from python_solver import find_top_candidates
                except ImportError:
                    find_top_candidates = None
            
            solutions = []
            if find_top_candidates:
                # Find multiple top candidates
                # Use a high limit to get all 0-move and 1-move solutions
                # We'll filter by move count later when building proposals
                # Use original_normalized_data (full horizon) to find all solutions
                solutions = find_top_candidates(
                    python_normalized_data,
                    scheduling_problem,
                    python_slot_indexer,
                    context_json,
                    max_candidates=2000  # High limit to capture all feasible solutions
                )
                # If we found multiple solutions, use them; otherwise fall back to single solution
                if not solutions:
                    solution = find_optimal_slot(
                        normalized_data,
                        scheduling_problem,
                        slot_indexer,
                        context_json
                    )
                    if solution:
                        solutions = [solution]
                else:
                    solution = solutions[0]  # Keep for compatibility with existing code
            else:
                # Fallback to single solution
                solution = find_optimal_slot(
                    normalized_data,
                    scheduling_problem,
                    slot_indexer,  # Pass the current slot_indexer (might be reduced)
                    context_json
                )
                if solution:
                    solutions = [solution]
            
            solve_time_ms = int((time.time() - solve_start_time) * 1000)
            debug_info.solve_time_ms = solve_time_ms
            
            # Always run ASP sliding window to explore full date range for best solutions
            # Even if Python solver found solutions, ASP might find better options across more days
            asp_solution_found = False
            
            try:
                    # Import ASP solver components
                    try:
                        from .clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                        from .fact_generator import generate_asp_program
                        asp_available = True
                    except (ImportError, ValueError):
                        try:
                            from clingo_wrapper import ClingoSolver, extract_scheduling_solution, compute_move_deltas, compute_objective_scores
                            from fact_generator import generate_asp_program
                            asp_available = True
                        except ImportError:
                            # ASP not available - fall through to UNSAT
                            asp_available = False
                    
                    if asp_available:
                        # SLIDING WINDOW APPROACH: Explore full date range by solving overlapping windows
                        # This allows us to find solutions across the entire timeframe without
                        # overwhelming ASP with a huge horizon
                        
                        # Calculate window parameters
                        window_days = 3  # Each window covers 3 days
                        overlap_days = 1  # Windows overlap by 1 day to avoid missing solutions at boundaries
                        window_slots = window_days * 96  # 96 slots per day (24 hours * 4 slots/hour)
                        
                        # Get the full time window from scheduling problem
                        from datetime import datetime, timedelta
                        import pytz
                        
                        if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
                            full_start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
                            full_end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
                            
                            if full_start_dt.tzinfo is None:
                                full_start_dt = pytz.UTC.localize(full_start_dt)
                            else:
                                full_start_dt = full_start_dt.astimezone(pytz.UTC)
                            
                            if full_end_dt.tzinfo is None:
                                full_end_dt = pytz.UTC.localize(full_end_dt)
                            else:
                                full_end_dt = full_end_dt.astimezone(pytz.UTC)
                            
                            # Calculate number of windows needed
                            total_days = (full_end_dt.date() - full_start_dt.date()).days + 1
                            step_days = window_days - overlap_days  # How much to advance each window
                            num_windows = max(1, (total_days - window_days) // step_days + 1)
                            
                            # Collect solutions from all windows
                            all_asp_solutions = []
                            all_asp_stats = []
                            
                            try:
                                from .horizon_reducer import reduce_horizon_to_feasible_window
                            except (ImportError, ValueError):
                                from horizon_reducer import reduce_horizon_to_feasible_window
                            
                            for window_idx in range(num_windows):
                                # Calculate window boundaries
                                window_start_dt = full_start_dt + timedelta(days=window_idx * step_days)
                                window_end_dt = min(window_start_dt + timedelta(days=window_days), full_end_dt)
                                
                                # Create a modified scheduling problem for this window
                                from copy import deepcopy
                                window_problem = deepcopy(scheduling_problem)
                                window_problem.time_window_start = window_start_dt.isoformat()
                                window_problem.time_window_end = window_end_dt.isoformat()
                                
                                # Reduce horizon for this window
                                asp_normalized_data = reduce_horizon_to_feasible_window(
                                    original_normalized_data,
                                    window_problem,
                                    max_slots=window_slots,
                                    prefer_time_window=True
                                )
                                
                                # Generate ASP program for this window
                                asp_program = generate_asp_program(
                                    asp_normalized_data,
                                    window_problem,
                                    request_id="q1",
                                    include_soft_constraints=True,
                                    include_work_hours=True,
                                    include_min_gap=True,
                                    include_locked_events=True,
                                    phase=4,
                                    allow_multi_move=True
                                )
                                
                                # Solve this window
                                asp_solver = ClingoSolver(timeout=30)
                                asp_model, asp_stats, asp_result = asp_solver.solve(asp_program)
                                
                                # Collect models from this window
                                asp_models_list = asp_solver.models if hasattr(asp_solver, 'models') else []
                                if asp_model and asp_model not in asp_models_list:
                                    asp_models_list.insert(0, asp_model)
                                asp_models_list = asp_models_list[:10]  # Limit per window
                                
                                # Store solutions from this window
                                if asp_result.satisfiable and asp_models_list:
                                    all_asp_stats.append(asp_stats)
                                    window_solution_count = len(asp_models_list)
                                    # Debug: log window results
                                    try:
                                        import sys
                                        from datetime import datetime
                                        import pytz
                                        reduced_start = asp_normalized_data["slot_indexer"].horizon_start
                                        reduced_end = asp_normalized_data["slot_indexer"].horizon_end
                                        et_start = reduced_start.astimezone(pytz.timezone('America/New_York'))
                                        et_end = reduced_end.astimezone(pytz.timezone('America/New_York'))
                                        print(f"[SLIDING_WINDOW] Window {window_idx+1} ({window_start_dt.strftime('%b %d')}-{window_end_dt.strftime('%b %d')}): {window_solution_count} models found, horizon={et_start.strftime('%Y-%m-%d %H:%M')} to {et_end.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                    # CRITICAL: Make a deep copy of asp_normalized_data to avoid it being overwritten
                                    from copy import deepcopy
                                    for model_data in asp_models_list:
                                        all_asp_solutions.append((model_data, deepcopy(asp_normalized_data), window_problem))
                            
                            # Aggregate stats from all windows
                            total_models = sum(s.get("models_found", 0) for s in all_asp_stats)
                            total_solve_time = sum(s.get("solve_time_ms", 0) for s in all_asp_stats)
                            total_ground_time = sum(s.get("ground_time_ms", 0) for s in all_asp_stats)
                            
                            debug_info.asp_stats = {
                                "models": total_models,
                                "optimum": any(s.get("optimum", False) for s in all_asp_stats),
                                "solve_time_ms": total_solve_time,
                                "ground_time_ms": total_ground_time,
                                "windows_explored": num_windows,
                                "satisfiable": any(s.get("satisfiable", False) for s in all_asp_stats),
                                "asp_model_truthy": len(all_asp_solutions) > 0,
                                "asp_result_satisfiable": True
                            }
                            
                            # Process solutions from all windows
                            asp_solutions_list = []
                            original_slot_indexer = original_normalized_data["slot_indexer"]
                            
                            for model_idx, (model_data, window_normalized_data, window_problem) in enumerate(all_asp_solutions):
                                asp_solution = extract_scheduling_solution(model_data, "q1")
                                if not asp_solution:
                                    continue
                                
                                asp_slot_indexer = window_normalized_data.get("slot_indexer")
                                if not asp_slot_indexer:
                                    # Debug: log missing slot_indexer
                                    try:
                                        import sys
                                        print(f"[WINDOW_SOLUTION] Window {window_idx+1 if 'window_idx' in locals() else '?'}, model {model_idx}: Missing slot_indexer in window_normalized_data!", file=sys.stderr, flush=True)
                                    except:
                                        pass
                                    continue
                                
                                reduced_slot = asp_solution["start_slot"]
                                
                                # Convert to datetime
                                slot_datetime = asp_slot_indexer.slot_to_datetime(reduced_slot)
                                if not slot_datetime:
                                    continue
                                
                                # Convert to original horizon slot
                                original_slot = original_slot_indexer.datetime_to_slot(slot_datetime)
                                if original_slot is None:
                                    duration = slot_datetime - original_slot_indexer.horizon_start
                                    calculated_slot = int(duration.total_seconds() / 60 / 15)
                                    if 0 <= calculated_slot < original_slot_indexer.total_slots:
                                        original_slot = calculated_slot
                                    else:
                                        continue
                                
                                # Create solution dict
                                asp_solution_dict = {
                                    "start_slot": original_slot,
                                    "score": 500 - model_idx,  # Score based on order
                                    "moved_events": [],
                                    "method": "asp_multi_move",
                                    "_asp_model_data": model_data,
                                    "_asp_solution": asp_solution,
                                    "_asp_reduced_slot": reduced_slot,
                                    "_asp_normalized_data": window_normalized_data  # Store for move computation
                                }
                                asp_solutions_list.append(asp_solution_dict)
                            
                            if asp_solutions_list:
                                solution = asp_solutions_list[0]
                                solutions.extend(asp_solutions_list)
                                asp_solution_found = True
                                debug_info.horizon_reduced = True
                                debug_info.reduced_slots = window_slots
                                # Store windows_explored in asp_stats instead of debug_info directly
                                debug_info.asp_stats["windows_explored"] = num_windows
                        else:
                            # No time window specified - can't do sliding window
                            debug_info.asp_stats = {
                                "models": 0,
                                "optimum": False,
                                "solve_time_ms": 0,
                                "ground_time_ms": 0,
                                "error": "No time window specified for sliding window approach",
                                "error_type": None,
                                "satisfiable": False,
                                "asp_model_truthy": False,
                                "asp_result_satisfiable": False,
                                "windows_explored": 0
                            }
                    
                    # Only return UNSAT if we have no solutions at all (neither Python nor ASP)
                    if not solutions and not asp_solution_found:
                        # No solution found with either Python or ASP - return UNSAT
                        unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
                        return ResponseEnvelope(
                            status="unsat",
                            explanation=unsat_info["explanation"],
                            proposals=[],
                            relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                            debug=debug_info
                        ).model_dump()
            
            except Exception as e:
                    # ASP fallback failed - return UNSAT
                    import traceback
                    error_traceback = traceback.format_exc()
                    unsat_info = explain_unsat(normalized_data, scheduling_problem, slot_indexer, context_json)
                    return ResponseEnvelope(
                        status="unsat",
                        explanation=f"{unsat_info['explanation']} (ASP fallback error: {str(e)})",
                        proposals=[],
                        relaxations=[Relaxation(**r) for r in unsat_info["relaxations"]],
                        debug=debug_info
                    ).model_dump() | {"asp_fallback_error": str(e), "asp_fallback_traceback": error_traceback}
            
            # Process multiple solutions to build diverse proposals
            all_proposals = []
            # By default, return all proposals with 0 or 1 moves (zero or single-move solutions)
            # This ensures we return all feasible options without overwhelming the user
            max_moved_events = 1  # Return all proposals with 0 or 1 moves
            
            # Sort solutions by score (highest first), then by number of moved events (fewer is better)
            # Score already prioritizes free slots, then single moves, etc.
            # We also want to prioritize solutions with fewer moved events within same score tier
            def solution_sort_key(sol):
                score = sol.get("score", 0)
                # Estimate moved events count from method (for sorting before building proposals)
                # Lower moved events = better, so we negate for reverse=True sort
                method = sol.get("method", "")
                if method == "free_slot":
                    moved_estimate = 0
                elif method == "single_move":
                    moved_estimate = 1
                else:
                    moved_estimate = 10  # Multi-move, assume more
                # Return tuple: (score, -moved_estimate) so higher score and fewer moves come first
                return (score, -moved_estimate)
            
            solutions.sort(key=solution_sort_key, reverse=True)
            
            # Count solutions that pass validation after grouping by day
            validated_count = 0
            
            # Group solutions by day for diversity filtering
            from datetime import datetime
            import pytz
            solutions_by_day: Dict[str, List[Dict[str, Any]]] = {}
            
            for sol in solutions:
                # For ASP solutions, use original slot_indexer for validation and conversion
                # For Python solutions, also use original slot_indexer (they were computed with full horizon)
                validation_slot_indexer = python_slot_indexer  # Use original for Python solutions
                if sol.get("method") == "asp_multi_move":
                    validation_slot_indexer = original_normalized_data["slot_indexer"]
                
                start_slot = sol["start_slot"]
                
                # Validate slot
                if start_slot < 0 or start_slot >= validation_slot_indexer.total_slots:
                    continue
                
                start_dt = validation_slot_indexer.slot_to_datetime(start_slot)
                if not start_dt:
                    continue
                
                duration_slots = max(1, scheduling_problem.duration_minutes // 15)
                end_slot = start_slot + duration_slots
                
                if end_slot > validation_slot_indexer.total_slots:
                    continue
                
                if end_slot == validation_slot_indexer.total_slots:
                    end_dt = validation_slot_indexer.horizon_end
                else:
                    end_dt = validation_slot_indexer.slot_to_datetime(end_slot)
                
                if not end_dt:
                    continue
                
                # Group by day for diversity
                if start_dt.tzinfo is None:
                    start_dt = pytz.UTC.localize(start_dt)
                day_key = start_dt.date().isoformat()
                
                if day_key not in solutions_by_day:
                    solutions_by_day[day_key] = []
                sol["_start_dt"] = start_dt
                sol["_end_dt"] = end_dt
                sol["_validation_slot_indexer"] = validation_slot_indexer
                solutions_by_day[day_key].append(sol)
                validated_count += 1
            
            # Select diverse solutions across the full date range
            # Strategy: Ensure representation from different parts of the timeframe
            selected_solutions = []
            selected_days = set()
            
            # Group days by week/period for better distribution
            all_days = sorted(solutions_by_day.keys())
            # Process all solutions - we'll filter by move count when building proposals
            # Use a reasonable limit to prevent excessive processing
            MAX_SOLUTIONS_TO_PROCESS = 2000
            if not all_days:
                # No solutions grouped by day - use all solutions up to limit
                selected_solutions = solutions[:MAX_SOLUTIONS_TO_PROCESS]
            else:
                # First pass: best solution from each day (prioritize days with fewer moved events)
                # Sort days by the best solution's moved event estimate
                days_with_scores = []
                for day_key in all_days:
                    day_solutions = solutions_by_day[day_key]
                    if day_solutions:
                        # Find best solution for this day (by score, which correlates with moved events)
                        best_sol = max(day_solutions, key=lambda s: s.get("score", 0))
                        method = best_sol.get("method", "")
                        moved_estimate = 0 if method == "free_slot" else (1 if method == "single_move" else 10)
                        days_with_scores.append((day_key, moved_estimate, best_sol))
                
                # Sort by moved_estimate (fewer is better), then by day
                days_with_scores.sort(key=lambda x: (x[1], x[0]))
                
                # Take best solution from each day, prioritizing days with fewer moves
                for day_key, _, best_sol in days_with_scores:
                    if len(selected_solutions) >= MAX_SOLUTIONS_TO_PROCESS:
                        break
                    if best_sol not in selected_solutions:
                        selected_solutions.append(best_sol)
                        selected_days.add(day_key)
                
                # Second pass: add remaining solutions up to limit, ensuring we cover the full range
                if len(selected_solutions) < MAX_SOLUTIONS_TO_PROCESS:
                    # Sort all solutions by score (best first)
                    all_solutions_sorted = sorted(solutions, key=lambda s: s.get("score", 0), reverse=True)
                    
                    for sol in all_solutions_sorted:
                        if len(selected_solutions) >= MAX_SOLUTIONS_TO_PROCESS:
                            break
                        if "_start_dt" not in sol:
                            continue
                        day_key = sol["_start_dt"].date().isoformat()
                        
                        # Add solutions not yet selected
                        if sol not in selected_solutions:
                            selected_solutions.append(sol)
            
            # Build proposals from selected solutions
            for sol in selected_solutions:
                start_dt = sol["_start_dt"]
                end_dt = sol["_end_dt"]
                validation_slot_indexer = sol["_validation_slot_indexer"]
                
                # Compute moved events and objective scores
                solution_method = sol.get("method", "unknown")
                has_asp_model_data = "_asp_model_data" in sol
                
                try:
                    if solution_method == "asp_multi_move" and has_asp_model_data:
                        # ASP solution - use ASP move computation
                        asp_model_data_ref = sol.get("_asp_model_data")
                        asp_solution_ref = sol.get("_asp_solution")
                        if asp_model_data_ref and asp_solution_ref:
                            # CRITICAL: Convert occurs_slots from reduced horizon to original horizon
                            # The asp_solution_ref has occurs_slots relative to the reduced horizon,
                            # but we need to compute move deltas using the original horizon's event_slots_map
                            asp_solution_original = asp_solution_ref.copy()
                            if "_asp_reduced_slot" in sol and "start_slot" in sol:
                                # Convert occurs_slots from reduced horizon to original horizon
                                reduced_slot = sol.get("_asp_reduced_slot")
                                original_slot = sol.get("start_slot")
                                if reduced_slot is not None and original_slot is not None:
                                    slot_offset = original_slot - reduced_slot
                                    original_occurs_slots = [slot + slot_offset for slot in asp_solution_ref.get("occurs_slots", [])]
                                    asp_solution_original["occurs_slots"] = original_occurs_slots
                            
                            # Use original_normalized_data for move computation to match events correctly
                            moved_events_list = compute_move_deltas(asp_solution_original, original_normalized_data, scheduling_problem) or []
                            objective_scores_dict = compute_objective_scores(asp_model_data_ref, asp_solution_ref, asp_normalized_data, scheduling_problem) or {}
                        else:
                            moved_events_list = []
                            objective_scores_dict = {}
                    else:
                        # Python solution - use original_normalized_data for consistency
                        moved_events_list = compute_move_deltas_python(sol, python_normalized_data, scheduling_problem) or []
                        objective_scores_dict = compute_objective_scores_python(sol, python_normalized_data, scheduling_problem) or {}
                    
                    moved_events = [MovedEvent(**me) for me in moved_events_list]
                    scores_dict = {
                        "moved_minutes": objective_scores_dict.get("moved_minutes", 0),
                        "focus_block_bonus": objective_scores_dict.get("focus_block_bonus", 0),
                        "preference_penalty": objective_scores_dict.get("preference_penalty", 0),
                        "protected_events_moved": objective_scores_dict.get("protected_events_moved", 0)
                    }
                    scores = ObjectiveScores(**scores_dict)
                    
                    proposal = Proposal(
                        title=scheduling_problem.title or "Meeting",
                        participants=scheduling_problem.participants,
                        start_utc=start_dt.isoformat(),
                        end_utc=end_dt.isoformat(),
                        moved_events=moved_events,
                        objective_scores=scores,
                        location=scheduling_problem.location
                    )
                    all_proposals.append(proposal)
                except Exception as e:
                    # Skip this solution if proposal building fails
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    continue
            
            if not all_proposals:
                # No valid proposals built - return error
                return ResponseEnvelope(
                    status="bad_input",
                    explanation="Failed to build any valid proposals from solutions",
                    proposals=[],
                    error_message="Proposal building failed",
                    debug=debug_info
                ).model_dump()
            
            # Final sort: prioritize proposals with fewer moved events (more feasible)
            # Proposals with 0 moved events are best, then 1, then 2, etc.
            # Within same moved count, prefer earlier proposals (better scores/earlier times)
            def proposal_sort_key(prop):
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                start_utc = prop.start_utc
                return (moved_count, start_utc)
            
            all_proposals.sort(key=proposal_sort_key)
            
            # Filter to only include proposals with 0 or 1 moves (as specified by max_moved_events)
            filtered_proposals = []
            for prop in all_proposals:
                moved_count = len(prop.moved_events) if prop.moved_events else 0
                if moved_count <= max_moved_events:
                    filtered_proposals.append(prop)
            
            all_proposals = filtered_proposals
            
            # Generate explanation
            explanation_parts = [f"Found {len(all_proposals)} meeting option(s):"]
            for i, prop in enumerate(all_proposals[:5], 1):  # Show first 5 in explanation
                start_dt = datetime.fromisoformat(prop.start_utc.replace('Z', '+00:00'))
                explanation_parts.append(f"{i}. {start_dt.strftime('%Y-%m-%d %H:%M')} UTC")
                if prop.moved_events:
                    explanation_parts[-1] += f" (requires moving {len(prop.moved_events)} event(s))"
            if len(all_proposals) > 5:
                explanation_parts.append(f"... and {len(all_proposals) - 5} more option(s)")
            
            explanation = ". ".join(explanation_parts) + "."
            
            # Return response
            debug_info.total_time_ms = int((time.time() - start_time) * 1000)
            
            result = ResponseEnvelope(
                status="ok",
                proposals=all_proposals,
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

