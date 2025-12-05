"""
clingo wrapper for solving ASP programs and extracting models.

Handles grounding, solving, model extraction, and statistics collection.
"""

from typing import Dict, List, Optional, Any, Tuple, Set
import time
from datetime import timedelta

try:
    from clingo import Control, Model
    from clingo.solving import SolveResult
    CLINGO_AVAILABLE = True
except ImportError:
    CLINGO_AVAILABLE = False
    # Placeholder classes for when clingo is not installed
    class Control:
        pass
    class Model:
        pass
    class SolveResult:
        SAT = "SAT"
        UNSAT = "UNSAT"
        UNKNOWN = "UNKNOWN"


class ClingoSolver:
    """Wrapper for clingo Control API."""
    
    def __init__(self, timeout: int = 30):
        """
        Initialize clingo solver.
        
        Args:
            timeout: Maximum solve time in seconds (default: 30)
        """
        self.timeout = timeout
        self.stats: Dict[str, Any] = {}
        self.models: List[Model] = []
        self.optimal_model: Optional[Model] = None
        self.solve_result: Optional[SolveResult] = None
    
    def solve(
        self,
        program: str,
        on_model_callback=None
    ) -> Tuple[Optional[Model], Dict[str, Any], SolveResult]:
        """
        Ground and solve an ASP program.
        
        Args:
            program: ASP program as string
            on_model_callback: Optional callback function(model) called for each model
            
        Returns:
            Tuple of (optimal_model, stats, solve_result)
        """
        if not CLINGO_AVAILABLE:
            # Use placeholder SolveResult for when clingo not available
            class MockSolveResult:
                satisfiable = False
                unknown = True
            self.stats = {"error": "clingo not available", "satisfiable": False}
            return None, self.stats, MockSolveResult()
        
        self.models = []
        self.optimal_model = None
        self.stats = {}
        
        # Configure clingo to suppress messages and limit output
        # --opt-mode=optN: optimize with multiple models but limit to first optimal
        # --models=1: only return the first optimal model (reduces output)
        # Note: --models=1 with optimization can sometimes fail to return models
        # if optimization is not proven, so we may need to relax this
        # --warn=none: suppress all warnings to reduce message volume
        ctl = Control([
            "--opt-mode=optN",
            "--models=10",  # Return up to 10 optimal models for diversity
            "--warn=none"  # Suppress all warnings
        ])
        
        # Suppress clingo's message handler to avoid "too many messages" error
        # The callback takes a single Message object parameter
        message_count = [0]  # Use list to allow modification in nested function
        MAX_MESSAGES = 10000  # Increase limit to handle larger problems
        
        def on_message(msg):
            """Suppress clingo messages to avoid 'too many messages' error."""
            message_count[0] += 1
            # Suppress all messages to avoid "too many messages" error
            # Return True to suppress the message, False to show it
            # We suppress everything to prevent clingo from hitting its internal message limit
            return True
        
        # Set the message handler BEFORE adding program to catch all messages
        ctl.on_message = on_message
        
        # Add program
        ctl.add("base", [], program)
        
        # Ground
        start_time = time.time()
        try:
            ctl.ground([("base", [])])
            ground_time = time.time() - start_time
            self.stats["ground_time_ms"] = int(ground_time * 1000)
        except Exception as e:
            ground_time = time.time() - start_time
            error_msg = str(e)
            self.stats["error"] = error_msg
            self.stats["ground_time_ms"] = int(ground_time * 1000)
            self.stats["grounding_failed"] = True
            
            # Check for specific error types
            if "parsing" in error_msg.lower() or "parse" in error_msg.lower():
                self.stats["error_type"] = "parsing_failed"
            elif "memory" in error_msg.lower() or "out of memory" in error_msg.lower():
                self.stats["error_type"] = "out_of_memory"
            else:
                self.stats["error_type"] = "grounding_failed"
            
            # Create a mock result for grounding failure
            class MockSolveResult:
                def __init__(self):
                    self.satisfiable = False
                    self.unknown = True
                    self.unsatisfiable = False
                    self.exhausted = False
                    self.interrupted = False
            return None, self.stats, MockSolveResult()
        
        # Solve with timeout
        solve_start = time.time()
        
        def on_model(model: Model):
            """Callback for each model found."""
            # Extract all needed data from model while it's still valid
            # Clingo models are only valid within the solve context
            model_data = {
                'symbols': list(model.symbols(shown=True)),  # Extract symbols immediately
                'cost': list(model.cost) if hasattr(model, 'cost') and model.cost else []
            }
            
            # Collect multiple optimal models for diversity (all models at same cost level are optimal)
            # Limit to reasonable number to avoid memory issues
            MAX_MODELS = 15  # Collect up to 15 models to have variety
            if len(self.models) < MAX_MODELS:
                self.models.append(model_data)
            if on_model_callback:
                # Still call callback with original model (valid during solve)
                on_model_callback(model)
            # Track optimal model data (first model when optimizing)
            if self.optimal_model is None:
                self.optimal_model = model_data
        
        try:
            with ctl.solve(on_model=on_model, async_=True) as handle:
                # Wait with timeout - clingo's handle.get() doesn't accept timeout
                # Instead, we poll with a timeout loop
                import time as time_module
                start_wait = time_module.time()
                result = None
                while time_module.time() - start_wait < self.timeout:
                    if handle.wait(0.1):  # Check if result is ready (wait up to 0.1 seconds)
                        result = handle.get()
                        break
                if result is None:
                    # Timeout - cancel solving
                    handle.cancel()
                    result = handle.get()  # Get partial result
                self.solve_result = result
                
                solve_time = time.time() - solve_start
                self.stats["solve_time_ms"] = int(solve_time * 1000)
                self.stats["total_time_ms"] = int((time.time() - start_time) * 1000)
                
                # Collect statistics
                self.stats["models_found"] = len(self.models)
                self.stats["optimum"] = result.optimality_proven if hasattr(result, 'optimality_proven') else False
                
                if result.satisfiable:
                    self.stats["satisfiable"] = True
                    if self.optimal_model:
                        # Cost vector was already extracted in on_model callback
                        if 'cost' in self.optimal_model:
                            self.stats["cost"] = self.optimal_model['cost']
                else:
                    self.stats["satisfiable"] = False
                    self.stats["unsat"] = True
                
                # Get clingo statistics
                try:
                    clingo_stats = ctl.statistics
                    self.stats["clingo_stats"] = {
                        "problem": {
                            "generators": clingo_stats.get("problem", {}).get("generators", 0),
                            "atoms": clingo_stats.get("problem", {}).get("atoms", 0),
                            "rules": clingo_stats.get("problem", {}).get("rules", 0),
                        },
                        "solving": {
                            "models": clingo_stats.get("solving", {}).get("models", {}).get("enumerated", 0),
                            "time": clingo_stats.get("solving", {}).get("time", {}).get("total", 0),
                        }
                    }
                except Exception:
                    pass
                
                return self.optimal_model, self.stats, result
        
        except Exception as e:
            solve_time = time.time() - solve_start
            self.stats["solve_time_ms"] = int(solve_time * 1000)
            self.stats["error"] = str(e)
            self.stats["timeout"] = solve_time >= self.timeout
            # Create a mock result for error case (SolveResult doesn't have UNKNOWN constant)
            class MockSolveResult:
                def __init__(self):
                    self.satisfiable = False
                    self.unknown = True
                    self.unsatisfiable = False
                    self.exhausted = False
                    self.interrupted = False
            return None, self.stats, MockSolveResult()


def extract_model_predicates(model) -> Dict[str, List[Tuple]]:
    """
    Extract predicates from a clingo model or model data.
    
    Args:
        model: clingo Model object (valid during solve) or dict with 'symbols' key
        
    Returns:
        Dictionary mapping predicate names to lists of tuples (arguments)
    """
    predicates: Dict[str, List[Tuple]] = {}
    
    # Handle both live Model objects and extracted model data dicts
    if isinstance(model, dict) and 'symbols' in model:
        # Model data dict: symbols are already extracted as a list
        symbols = model['symbols']
    elif hasattr(model, 'symbols'):
        # Live Model object: call symbols() method
        symbols = model.symbols(shown=True)
    else:
        return predicates
    
    for atom in symbols:
        # Symbols from dict are already Symbol objects (from clingo)
        if hasattr(atom, 'type') and atom.type == atom.type.Function:
            name = atom.name
            args = tuple(arg.number if arg.type == arg.type.Number else str(arg) for arg in atom.arguments)
            
            if name not in predicates:
                predicates[name] = []
            predicates[name].append(args)
    
    return predicates


def extract_scheduling_solution(
    model,
    request_id: str = "q1"
) -> Optional[Dict[str, Any]]:
    """
    Extract scheduling solution from model.
    
    Args:
        model: clingo Model object
        request_id: Request identifier
        
    Returns:
        Dictionary with:
        - start_slot: int (slot where meeting starts)
        - occurs_slots: List[int] (all slots the meeting occupies)
        - or None if no solution found
    """
    predicates = extract_model_predicates(model)
    
    # Extract start(Q, T)
    start_predicates = predicates.get("start", [])
    start_slot = None
    for args in start_predicates:
        if len(args) == 2 and args[0] == request_id:
            start_slot = args[1]
            break
    
    if start_slot is None:
        return None
    
    # Extract occurs(Q, T)
    occurs_predicates = predicates.get("occurs", [])
    occurs_slots = []
    for args in occurs_predicates:
        if len(args) == 2 and args[0] == request_id:
            occurs_slots.append(args[1])
    
    occurs_slots.sort()
    
    return {
        "start_slot": start_slot,
        "occurs_slots": occurs_slots,
        "request_id": request_id
    }


def compute_move_deltas(
    solution: Dict[str, Any],
    normalized_data: Dict[str, Any],
    scheduling_problem
) -> List[Dict[str, Any]]:
    """
    Compute which events need to be moved and by how much.
    
    Args:
        solution: Output from extract_scheduling_solution()
        normalized_data: Output from normalize_events()
        scheduling_problem: SchedulingProblem object
        
    Returns:
        List of MovedEvent dictionaries
    """
    moved_events = []
    
    if not solution:
        return moved_events
    
    occurs_slots: Set[int] = set(solution["occurs_slots"])
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    event_protection: Dict[Tuple[str, str], str] = normalized_data["event_protection"]
    slot_indexer = normalized_data["slot_indexer"]
    
    # Use event_slots_map to find which events overlap with the solution
    event_slots_map = normalized_data.get("event_slots_map", {})
    event_metadata = normalized_data.get("event_metadata", {})
    
    # Track which events have been processed to avoid duplicates
    processed_events = set()
    
    # For each participant, find events that overlap with the solution
    for participant_id in scheduling_problem.participants:
        participant_busy = busy_slots.get(participant_id, set())
        overlap_slots = occurs_slots & participant_busy
        
        if not overlap_slots:
            continue
        
        # Find which specific events overlap with the solution slots
        for (p_id, event_id), event_slots_set in event_slots_map.items():
            if p_id != participant_id:
                continue
            
            # Check if this event overlaps with the solution
            event_overlap = event_slots_set & occurs_slots
            if not event_overlap:
                continue
            
            # Avoid processing the same event twice
            event_key = (p_id, event_id)
            if event_key in processed_events:
                continue
            processed_events.add(event_key)
            
            # Get event metadata for old start/end times
            event_meta = event_metadata.get(event_key, {})
            
            # HARD CONSTRAINT: Only internal-only meetings can be moved
            internal_only = event_meta.get("internal_only", True)  # Default to True for backwards compatibility
            if not internal_only:
                continue  # Skip external events - they cannot be moved
            
            old_start_dt = event_meta.get("start_dt")
            old_end_dt = event_meta.get("end_dt")
            
            if not old_start_dt or not old_end_dt:
                # Fallback: calculate from slots
                if event_slots_set:
                    first_slot = min(event_slots_set)
                    last_slot = max(event_slots_set)
                    old_start_dt = slot_indexer.slot_to_datetime(first_slot)
                    old_end_dt = slot_indexer.slot_to_datetime(last_slot + 1)  # +1 because end is exclusive
            
            if old_start_dt:
                # For ASP solutions, we need to calculate where the event should be moved.
                # Since ASP doesn't explicitly tell us where events were moved, we use a heuristic:
                # Find the earliest slot after the meeting that would fit the event.
                # But a simpler approach: shift the event by the meeting duration plus a small buffer.
                # This is a conservative estimate - in practice, ASP may have moved it less.
                meeting_duration_slots = len(occurs_slots)
                meeting_start_slot = min(occurs_slots) if occurs_slots else 0
                meeting_end_slot = max(occurs_slots) + 1 if occurs_slots else 0
                
                # Calculate the event's current start slot in the current slot_indexer's frame
                event_start_slot = min(event_slots_set) if event_slots_set else None
                
                if event_start_slot is not None:
                    # Calculate minimum shift: move event to start after meeting ends
                    # Add 1 slot (15 min) buffer to avoid back-to-back meetings
                    min_new_start_slot = meeting_end_slot + 1
                    slot_shift = min_new_start_slot - event_start_slot
                    
                    # Calculate event duration in slots
                    event_duration_slots = len(event_slots_set) if event_slots_set else 1
                    
                    # Get work hours for this participant to ensure moved event stays within work hours
                    work_hours_slots = normalized_data.get("work_hours_slots", {})
                    participant_work_hours = work_hours_slots.get(participant_id, set())
                    
                    # Find a valid slot within work hours
                    new_start_slot = None
                    if participant_work_hours:
                        # Try to find a slot after the meeting that keeps the entire event within work hours
                        # Start from the minimum required slot and search forward
                        search_start_slot = min_new_start_slot
                        # Search up to 7 days forward (7 * 96 slots = 672 slots) to find a valid work hours slot
                        max_search_slots = 672  # 7 days worth of slots
                        
                        for candidate_slot in range(search_start_slot, search_start_slot + max_search_slots):
                            candidate_event_slots = set(range(candidate_slot, candidate_slot + event_duration_slots))
                            
                            # Check if all slots are within work hours
                            if all(slot in participant_work_hours for slot in candidate_event_slots):
                                new_start_slot = candidate_slot
                                break
                        
                        # If no valid slot found within work hours, this is a problem
                        # We should reject solutions that can't keep moved events within work hours
                        # For now, we'll use the original shift but this indicates a constraint violation
                        if new_start_slot is None:
                            # No valid work hours slot found - this solution violates work hours constraint
                            # Use original shift as fallback, but this should ideally cause the solution to be rejected
                            # TODO: Consider rejecting solutions that can't keep moved events within work hours
                            new_start_slot = event_start_slot + slot_shift
                    else:
                        # No work hours defined - use original shift
                    new_start_slot = event_start_slot + slot_shift
                    
                    # Calculate new start/end times based on slot
                    new_start_dt = slot_indexer.slot_to_datetime(new_start_slot)
                    if not new_start_dt:
                        # Fallback to simple duration shift
                        meeting_duration = timedelta(minutes=meeting_duration_slots * 15)
                        new_start_dt = old_start_dt + meeting_duration
                        shift_minutes = int(meeting_duration.total_seconds() / 60)
                    else:
                        # Calculate actual shift from datetime difference
                        actual_shift = (new_start_dt - old_start_dt).total_seconds() / 60
                        shift_minutes = int(actual_shift)
                    
                    # Calculate new end time
                    event_duration = (old_end_dt - old_start_dt) if old_end_dt else timedelta(minutes=event_duration_slots * 15)
                    new_end_dt = new_start_dt + event_duration if new_start_dt else None
                else:
                    # Fallback: shift by meeting duration
                    meeting_duration = timedelta(minutes=meeting_duration_slots * 15)
                    new_start_dt = old_start_dt + meeting_duration
                    new_end_dt = old_end_dt + meeting_duration if old_end_dt else None
                    shift_minutes = int(meeting_duration.total_seconds() / 60)
                
                if not new_end_dt and new_start_dt:
                    event_duration = (old_end_dt - old_start_dt) if old_end_dt else timedelta(minutes=len(event_slots_set) * 15)
                    new_end_dt = new_start_dt + event_duration
                
                moved_event_dict = {
                    "owner": participant_id,
                    "event_id": event_id,
                    "old_start": old_start_dt.isoformat(),
                    "new_start": new_start_dt.isoformat(),
                    "old_end": old_end_dt.isoformat() if old_end_dt else new_end_dt.isoformat(),
                    "new_end": new_end_dt.isoformat(),
                    "shift_minutes": shift_minutes
                }
                
                moved_events.append(moved_event_dict)
    
    return moved_events


def compute_objective_scores(
    model,
    solution: Dict[str, Any],
    normalized_data: Dict[str, Any],
    scheduling_problem=None
) -> Dict[str, int]:
    """
    Compute objective scores from model and solution.
    
    Args:
        model: clingo Model object (valid during solve) or dict with 'cost' key
        solution: Output from extract_scheduling_solution()
        normalized_data: Output from normalize_events()
        
    Returns:
        Dictionary with objective scores
    """
    scores = {
        "moved_minutes": 0,
        "focus_block_bonus": 0,
        "preference_penalty": 0,
        "protected_events_moved": 0
    }
    
    # Extract cost vector if available
    # Handle both live Model objects and extracted model data dicts
    cost = None
    if isinstance(model, dict) and 'cost' in model:
        cost = model['cost']
    elif hasattr(model, 'cost') and model.cost:
        # Only safe to access if model is still in solve context
        try:
            cost = list(model.cost)
        except (AttributeError, RuntimeError):
            # Model may be invalid - skip cost extraction
            cost = None
    
    if cost:
        # Cost vector format: [L1_cost, L2_cost, L3_cost]
        if len(cost) >= 1:
            scores["protected_events_moved"] = cost[0] if cost[0] else 0
        if len(cost) >= 2:
            scores["moved_minutes"] = cost[1] if cost[1] else 0
        if len(cost) >= 3:
            # L3 is negative for focus blocks (we minimize negative)
            scores["focus_block_bonus"] = abs(cost[2]) if cost[2] and cost[2] < 0 else 0
            scores["preference_penalty"] = cost[2] if cost[2] and cost[2] > 0 else 0
    
    # Calculate moved minutes from solution
    if solution and scheduling_problem:
        moved_events = compute_move_deltas(solution, normalized_data, scheduling_problem)
        scores["moved_minutes"] = sum(me.get("shift_minutes", 0) for me in moved_events)
    
    # Calculate priority score from cost vector (lower cost = higher priority score)
    # ASP uses lexicographic optimization, so we convert cost to a priority score
    # Cost vector format: [L1_cost, L2_cost, L3_cost, ...] where lower is better
    if cost:
        # Invert costs to get priority score (lower cost = higher score)
        # Use negative sum of costs as priority score (lower total cost = higher score)
        total_cost = sum(c if c else 0 for c in cost)
        scores["priority_score"] = max(0.0, 1000.0 - total_cost)  # Higher score = better
    
    return scores

