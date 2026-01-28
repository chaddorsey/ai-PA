"""
Ranking engine for evaluated meeting slots.

Scores and sorts slots by:
1. Category (clean > solo_adjust > multi_adjust)
2. Time-of-day preferences (optional)
3. Sooner dates preferred
"""
from datetime import date
from typing import List, Optional

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

# Date penalty per day in the future
DATE_PENALTY_PER_DAY = 2


def score_slot(
    slot: EvaluatedSlot,
    reference_date: date,
    preferred_hours: Optional[tuple] = None
) -> float:
    """
    Calculate score for a slot.

    Args:
        slot: The slot to score
        reference_date: Today's date for calculating days out
        preferred_hours: Optional (start_hour, end_hour) for time preference bonus

    Returns:
        Numeric score (higher is better)
    """
    score = 0.0

    # Category score
    score += CATEGORY_SCORES.get(slot.category, 0)

    # Time preference bonus
    if preferred_hours:
        start_hour, end_hour = preferred_hours
        slot_hour = slot.start.hour
        if start_hour <= slot_hour <= end_hour:
            score += 20

    # Date penalty (sooner is better)
    days_out = (slot.start.date() - reference_date).days
    score -= days_out * DATE_PENALTY_PER_DAY

    return score


def rank_slots(
    slots: List[EvaluatedSlot],
    reference_date: date,
    preferred_hours: Optional[tuple] = None
) -> List[EvaluatedSlot]:
    """
    Score and sort slots by preference.

    Args:
        slots: List of slots to rank
        reference_date: Today's date
        preferred_hours: Optional time preference

    Returns:
        Sorted list of slots (best first), with scores assigned
    """
    # Score each slot
    for slot in slots:
        slot.score = score_slot(slot, reference_date, preferred_hours)

    # Sort by score descending
    return sorted(slots, key=lambda s: s.score, reverse=True)
