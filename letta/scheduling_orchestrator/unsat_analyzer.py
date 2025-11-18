"""
UNSAT analysis and relaxation suggestion generator.

Analyzes unsatisfiable scheduling problems and generates ranked relaxation suggestions.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
import pytz
from .schemas import Relaxation
from .slot_indexer import SlotIndexer


def analyze_unsat_causes(
    normalized_data: Dict[str, Any],
    scheduling_problem,
    slot_indexer: SlotIndexer
) -> List[str]:
    """
    Analyze why a scheduling problem is unsatisfiable.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: SchedulingProblem object
        slot_indexer: SlotIndexer instance
        
    Returns:
        List of human-readable blocking causes
    """
    causes = []
    
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    work_hours_slots: Dict[str, Set[int]] = normalized_data["work_hours_slots"]
    
    # Check if all participants are busy during the entire window
    all_busy = True
    for participant_id in scheduling_problem.participants:
        participant_busy = busy_slots.get(participant_id, set())
        if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
            # Check if there are any free slots in the window
            try:
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
                
                window_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
                free_slots = set(window_slots) - participant_busy
                if free_slots:
                    all_busy = False
            except Exception:
                pass
        else:
            # No window specified - check if participant has any free slots
            all_slots = set(slot_indexer.get_all_slots())
            free_slots = all_slots - participant_busy
            if free_slots:
                all_busy = False
    
    if all_busy:
        causes.append("All participants are busy during the requested time window")
    
    # Check if window is too narrow
    if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
        try:
            start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = pytz.UTC.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = pytz.UTC.localize(end_dt)
            
            duration = (end_dt - start_dt).total_seconds() / 60
            if duration < scheduling_problem.duration_minutes:
                causes.append(f"Time window ({duration:.0f} minutes) is shorter than required duration ({scheduling_problem.duration_minutes} minutes)")
        except Exception:
            pass
    
    # Check if meeting would be outside work hours
    if not scheduling_problem.allow_off_hours:
        for participant_id in scheduling_problem.participants:
            work_slots = work_hours_slots.get(participant_id, set())
            if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
                try:
                    start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
                    if start_dt.tzinfo is None:
                        start_dt = pytz.UTC.localize(start_dt)
                    if end_dt.tzinfo is None:
                        end_dt = pytz.UTC.localize(end_dt)
                    
                    window_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
                    work_window_slots = set(window_slots) & work_slots
                    if not work_window_slots:
                        causes.append(f"Participant {participant_id} has no work hours available in the requested window")
                except Exception:
                    pass
    
    # Check if min_gap is too strict
    min_gap_slots = normalized_data.get("min_gap_slots", 1)
    if min_gap_slots > 0:
        # If min_gap is large relative to available slots, it might be blocking
        all_slots = set(slot_indexer.get_all_slots())
        if len(all_slots) < min_gap_slots * 2:
            causes.append(f"Minimum gap requirement ({min_gap_slots * 15} minutes) is too strict for the available time slots")
    
    if not causes:
        causes.append("Unable to find a meeting time that satisfies all constraints")
    
    return causes


def generate_relaxations(
    normalized_data: Dict[str, Any],
    scheduling_problem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None
) -> List[Relaxation]:
    """
    Generate ranked relaxation suggestions for an unsatisfiable problem.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: SchedulingProblem object
        slot_indexer: SlotIndexer instance
        context_json: Optional context dictionary
        
    Returns:
        List of Relaxation objects, ranked by expected impact
    """
    relaxations = []
    
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    work_hours_slots: Dict[str, Set[int]] = normalized_data["work_hours_slots"]
    
    # Relaxation 1: Widen time window
    if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
        try:
            start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = pytz.UTC.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = pytz.UTC.localize(end_dt)
            
            # Suggest extending window by 2 hours on each side
            new_start = (start_dt - timedelta(hours=2)).isoformat()
            new_end = (end_dt + timedelta(hours=2)).isoformat()
            
            relaxations.append(Relaxation(
                description=f"Widen time window to include more hours (extend to {new_start} - {new_end})",
                expected_impact="high",
                policy_change={
                    "time_window_start": new_start,
                    "time_window_end": new_end
                },
                rank=1
            ))
        except Exception:
            pass
    
    # Relaxation 2: Relax minimum gap
    min_gap_slots = normalized_data.get("min_gap_slots", 1)
    if min_gap_slots > 1:
        new_min_gap = max(1, min_gap_slots - 1)  # Reduce by 1 slot (15 minutes)
        relaxations.append(Relaxation(
            description=f"Relax minimum gap from {min_gap_slots * 15} to {new_min_gap * 15} minutes",
            expected_impact="medium",
            policy_change={
                "min_gap_minutes": new_min_gap * 15
            },
            rank=2
        ))
    
    # Relaxation 3: Allow off-hours
    if not scheduling_problem.allow_off_hours:
        relaxations.append(Relaxation(
            description="Allow scheduling outside work hours (before 9am or after 5:30pm)",
            expected_impact="low",
            policy_change={
                "allow_off_hours": True
            },
            rank=3
        ))
    
    # Relaxation 4: Extend horizon
    # Suggest looking further in the future
    horizon_end = slot_indexer.horizon_end
    new_horizon_end = (horizon_end + timedelta(days=7)).isoformat()
    relaxations.append(Relaxation(
        description=f"Extend planning horizon by 1 week (look until {new_horizon_end})",
        expected_impact="high",
        policy_change={
            "timeframe": {
                "to": new_horizon_end
            }
        },
        rank=4
    ))
    
    # Relaxation 5: Remove optional participants
    if len(scheduling_problem.participants) > 1:
        # Suggest making some participants optional
        relaxations.append(Relaxation(
            description=f"Make some participants optional (currently requires all {len(scheduling_problem.participants)} participants)",
            expected_impact="medium",
            policy_change={
                "optional_participants": scheduling_problem.participants[1:]  # All except first
            },
            rank=5
        ))
    
    # Sort by rank
    relaxations.sort(key=lambda r: r.rank)
    
    return relaxations


def explain_unsat(
    normalized_data: Dict[str, Any],
    scheduling_problem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate complete UNSAT explanation with causes and relaxations.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: SchedulingProblem object
        slot_indexer: SlotIndexer instance
        context_json: Optional context dictionary
        
    Returns:
        Dictionary with:
        - explanation: Human-readable explanation
        - causes: List of blocking causes
        - relaxations: List of Relaxation objects
    """
    causes = analyze_unsat_causes(normalized_data, scheduling_problem, slot_indexer)
    relaxations = generate_relaxations(normalized_data, scheduling_problem, slot_indexer, context_json)
    
    # Generate explanation
    explanation_parts = ["Unable to find a meeting time that satisfies all constraints."]
    if causes:
        explanation_parts.append("Blocking causes:")
        for i, cause in enumerate(causes, 1):
            explanation_parts.append(f"  {i}. {cause}")
    
    if relaxations:
        explanation_parts.append("\nSuggested relaxations (in order of recommendation):")
        for relaxation in relaxations[:3]:  # Show top 3
            explanation_parts.append(f"  {relaxation.rank}. {relaxation.description}")
    
    explanation = "\n".join(explanation_parts)
    
    return {
        "explanation": explanation,
        "causes": causes,
        "relaxations": [r.model_dump() for r in relaxations]
    }

