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
            self.stats = {"error": "clingo not available", "satisfiable": False}
            return None, self.stats, SolveResult.UNKNOWN
        
        self.models = []
        self.optimal_model = None
        self.stats = {}
        
        # Configure clingo to suppress messages and limit output
        # --opt-mode=optN: optimize with multiple models but limit to first optimal
        # --models=1: only return the first optimal model (reduces output)
        # --warn=none: suppress all warnings to reduce message volume
        ctl = Control([
            "--opt-mode=optN",
            "--models=1",  # Only return first optimal model
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
            
            return None, self.stats, SolveResult.UNKNOWN
        
        # Solve with timeout
        solve_start = time.time()
        
        def on_model(model: Model):
            """Callback for each model found."""
            # Limit number of models collected to avoid memory issues
            if len(self.models) < 10:  # Only keep first 10 models
                self.models.append(model)
            if on_model_callback:
                on_model_callback(model)
            # Track optimal model (first model when optimizing)
            if self.optimal_model is None:
                self.optimal_model = model
        
        try:
            with ctl.solve(on_model=on_model, async_=True) as handle:
                # Wait with timeout
                result = handle.get(timeout=self.timeout)
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
                        # Extract cost vector if available
                        if hasattr(self.optimal_model, 'cost'):
                            self.stats["cost"] = list(self.optimal_model.cost)
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
            return None, self.stats, SolveResult.UNKNOWN


def extract_model_predicates(model: Model) -> Dict[str, List[Tuple]]:
    """
    Extract predicates from a clingo model.
    
    Args:
        model: clingo Model object
        
    Returns:
        Dictionary mapping predicate names to lists of tuples (arguments)
    """
    predicates: Dict[str, List[Tuple]] = {}
    
    for atom in model.symbols(shown=True):
        if atom.type == atom.type.Function:
            name = atom.name
            args = tuple(arg.number if arg.type == arg.type.Number else str(arg) for arg in atom.arguments)
            
            if name not in predicates:
                predicates[name] = []
            predicates[name].append(args)
    
    return predicates


def extract_scheduling_solution(
    model: Model,
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
    
    # For each participant, check if new meeting overlaps with their events
    for participant_id in scheduling_problem.participants:
        participant_busy = busy_slots.get(participant_id, set())
        overlap_slots = occurs_slots & participant_busy
        
        if not overlap_slots:
            continue
        
        # Find which events are affected
        # This is simplified - in practice, we'd track which slots belong to which events
        # For now, we'll create a moved event for the overlap
        # A more sophisticated version would track event boundaries
        
        # Group consecutive overlapping slots (simplified)
        sorted_overlap = sorted(overlap_slots)
        if sorted_overlap:
            first_slot = sorted_overlap[0]
            last_slot = sorted_overlap[-1]
            
            # Calculate shift needed (simplified - shift by meeting duration)
            meeting_duration_slots = len(occurs_slots)
            shift_slots = meeting_duration_slots
            
            old_start_dt = slot_indexer.slot_to_datetime(first_slot)
            new_start_dt = slot_indexer.slot_to_datetime(first_slot + shift_slots)
            
            if old_start_dt and new_start_dt:
                shift_minutes = shift_slots * 15
                
                # Find event ID (simplified - use first overlapping event)
                event_id = None
                for (p_id, e_id), protection in event_protection.items():
                    if p_id == participant_id:
                        event_id = e_id
                        break
                
                if event_id:
                    moved_events.append({
                        "owner": participant_id,
                        "event_id": event_id,
                        "old_start": old_start_dt.isoformat(),
                        "new_start": new_start_dt.isoformat(),
                        "old_end": (old_start_dt + timedelta(minutes=15 * len(sorted_overlap))).isoformat(),
                        "new_end": (new_start_dt + timedelta(minutes=15 * len(sorted_overlap))).isoformat(),
                        "shift_minutes": shift_minutes
                    })
    
    return moved_events


def compute_objective_scores(
    model: Model,
    solution: Dict[str, Any],
    normalized_data: Dict[str, Any]
) -> Dict[str, int]:
    """
    Compute objective scores from model and solution.
    
    Args:
        model: clingo Model object
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
    if hasattr(model, 'cost') and model.cost:
        cost = list(model.cost)
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
    if solution:
        moved_events = compute_move_deltas(solution, normalized_data, None)  # TODO: pass scheduling_problem
        scores["moved_minutes"] = sum(me.get("shift_minutes", 0) for me in moved_events)
    
    return scores

