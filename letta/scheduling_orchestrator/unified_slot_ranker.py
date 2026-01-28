"""
Unified slot ranking for scheduling tools.

Provides a single ranking entry point that can be used by both:
- evaluate_proposed_times (new tool)
- orchestrate_scheduling (existing orchestrator)

Combines:
- Category scoring (clean > solo_adjust > multi_adjust)
- Date proximity scoring (sooner is better)
- Preference scoring (via preference_scorer when context available - Task 1.2)
"""

from datetime import date
from typing import List, Optional, Dict, Any

try:
    from .evaluation_models import EvaluatedSlot
except ImportError:
    from evaluation_models import EvaluatedSlot

# Category scores (higher = better)
CATEGORY_SCORES = {
    "clean": 100,
    "solo_adjust": 50,
    "multi_adjust": 0,
}

# Penalty per day in the future
DATE_PENALTY_PER_DAY = 2.0


def rank_evaluated_slots(
    slots: List[EvaluatedSlot],
    identity_id: Optional[str],
    participants: List[str],
    context_json: Optional[Dict[str, Any]] = None,
    reference_date: Optional[date] = None
) -> List[EvaluatedSlot]:
    """
    Rank evaluated slots by preference and feasibility.

    Scoring layers:
    1. Category score (clean=100, solo_adjust=50, multi_adjust=0)
    2. Date proximity (sooner dates preferred, -2 points per day)
    3. Preference score (if identity/context provides preferences - Task 1.2)

    Args:
        slots: List of EvaluatedSlot objects to rank
        identity_id: Optional Letta identity ID for preference lookup (Task 1.3)
        participants: List of participant email addresses
        context_json: Optional context with participant preferences (Task 1.2)
        reference_date: Date to calculate "days out" from (defaults to today)

    Returns:
        Sorted list of EvaluatedSlot objects (best first), with scores assigned
    """
    if not slots:
        return []

    if reference_date is None:
        reference_date = date.today()

    # Score each slot
    # Note: identity_id, participants, and context_json are reserved for
    # preference scoring in Task 1.2 (preference_scorer integration)
    for slot in slots:
        score = _compute_slot_score(
            slot=slot,
            reference_date=reference_date,
        )
        slot.score = score

    # Sort by score descending (higher = better)
    return sorted(slots, key=lambda s: s.score, reverse=True)


def _compute_slot_score(
    slot: EvaluatedSlot,
    reference_date: date,
) -> float:
    """
    Compute composite score for a single slot.

    Args:
        slot: The slot to score
        reference_date: Today's date for calculating days out

    Returns:
        Numeric score (higher is better)
    """
    score = 0.0

    # 1. Category score
    score += CATEGORY_SCORES.get(slot.category, 0)

    # 2. Date proximity penalty
    days_out = (slot.start.date() - reference_date).days
    score -= days_out * DATE_PENALTY_PER_DAY

    # 3. Preference score (Task 1.2 will add this)
    # For now, skip if no context

    return score
