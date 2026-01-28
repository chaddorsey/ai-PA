"""
Unified slot ranking for scheduling tools.

Provides a single ranking entry point that can be used by both:
- evaluate_proposed_times (new tool)
- orchestrate_scheduling (existing orchestrator)

Combines:
- Category scoring (clean > solo_adjust > multi_adjust)
- Date proximity scoring (sooner is better)
- Preference scoring (via preference_scorer when context available)
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

try:
    from .evaluation_models import EvaluatedSlot
except ImportError:
    from evaluation_models import EvaluatedSlot

try:
    from .schemas import SchedulingProblem
    from .slot_indexer import SlotIndexer
    from .preference_merger import merge_standing_preferences
    from .preference_scorer import compute_aggregate_preference_score
except ImportError:
    from schemas import SchedulingProblem
    from slot_indexer import SlotIndexer
    from preference_merger import merge_standing_preferences
    from preference_scorer import compute_aggregate_preference_score

# Category scores (higher = better)
CATEGORY_SCORES = {
    "clean": 100,
    "solo_adjust": 50,
    "multi_adjust": 0,
}

# Penalty per day in the future
DATE_PENALTY_PER_DAY = 2.0

# Weight for preference score in the total
PREFERENCE_SCORE_WEIGHT = 2.0

# Default planning horizon for preference scoring (days)
DEFAULT_HORIZON_DAYS = 14


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

    # Build preference scoring context if context_json is provided
    preference_context = None
    if context_json and participants:
        preference_context = _build_preference_context(
            slots=slots,
            participants=participants,
            context_json=context_json,
            identity_id=identity_id,
        )

    # Score each slot
    for slot in slots:
        score = _compute_slot_score(
            slot=slot,
            reference_date=reference_date,
            preference_context=preference_context,
        )
        slot.score = score

    # Sort by score descending (higher = better)
    return sorted(slots, key=lambda s: s.score, reverse=True)


def _compute_slot_score(
    slot: EvaluatedSlot,
    reference_date: date,
    preference_context: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Compute composite score for a single slot.

    Args:
        slot: The slot to score
        reference_date: Today's date for calculating days out
        preference_context: Optional preference scoring context from _build_preference_context

    Returns:
        Numeric score (higher is better)
    """
    score = 0.0

    # 1. Category score
    score += CATEGORY_SCORES.get(slot.category, 0)

    # 2. Date proximity penalty
    days_out = (slot.start.date() - reference_date).days
    score -= days_out * DATE_PENALTY_PER_DAY

    # 3. Preference score (if context available)
    if preference_context is not None:
        preference_score = _compute_preference_score(
            slot_datetime=slot.start,
            preference_context=preference_context,
        )
        score += preference_score * PREFERENCE_SCORE_WEIGHT

    return score


def _build_preference_context(
    slots: List[EvaluatedSlot],
    participants: List[str],
    context_json: Dict[str, Any],
    identity_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build preference scoring context for a set of slots.

    Creates a minimal SchedulingProblem and SlotIndexer that can be reused
    across all slots for efficient preference scoring.

    Args:
        slots: List of slots to compute horizon from
        participants: List of participant email addresses
        context_json: Context with participant preferences
        identity_id: Optional requester identity for 2x weighting

    Returns:
        Dictionary with scheduling_problem, slot_indexer, context_json, and requester_id
    """
    import pytz

    # Compute horizon from slots (min start to max end + buffer)
    if not slots:
        # No slots - return empty context that will be skipped
        return {}

    # Find the range of times covered by slots
    min_start = min(s.start for s in slots)
    max_end = max(s.end for s in slots)

    # Ensure timezone awareness
    if min_start.tzinfo is None:
        min_start = pytz.UTC.localize(min_start)
    if max_end.tzinfo is None:
        max_end = pytz.UTC.localize(max_end)

    # Extend horizon by 1 day on each end for safety
    horizon_start = min_start - timedelta(days=1)
    horizon_end = max_end + timedelta(days=1)

    # Create SlotIndexer
    slot_indexer = SlotIndexer(horizon_start, horizon_end)

    # Create minimal SchedulingProblem
    scheduling_problem = SchedulingProblem(
        participants=participants,
        duration_minutes=60,  # Placeholder, not used for preference scoring
    )

    # Merge standing preferences from context_json
    scheduling_problem = merge_standing_preferences(scheduling_problem, context_json)

    # Determine requester_id for 2x weighting
    # Use identity_id if provided, otherwise use first participant from context
    requester_id = identity_id
    if not requester_id and context_json.get("participants"):
        first_participant = context_json["participants"][0]
        requester_id = first_participant.get("id")

    return {
        "scheduling_problem": scheduling_problem,
        "slot_indexer": slot_indexer,
        "context_json": context_json,
        "requester_id": requester_id,
    }


def _compute_preference_score(
    slot_datetime: datetime,
    preference_context: Dict[str, Any],
) -> float:
    """
    Compute preference score for a single slot datetime.

    Uses the preference_scorer module to compute aggregate preference score
    across all participants.

    Args:
        slot_datetime: The datetime to score
        preference_context: Context from _build_preference_context

    Returns:
        Preference score (positive=preferred, negative=avoided, 0=neutral)
    """
    import pytz

    if not preference_context:
        return 0.0

    scheduling_problem = preference_context.get("scheduling_problem")
    slot_indexer = preference_context.get("slot_indexer")
    context_json = preference_context.get("context_json")
    requester_id = preference_context.get("requester_id")

    if not scheduling_problem or not slot_indexer:
        return 0.0

    # Ensure slot_datetime is timezone-aware
    if slot_datetime.tzinfo is None:
        slot_datetime = pytz.UTC.localize(slot_datetime)

    # Convert datetime to slot index
    slot_index = slot_indexer.datetime_to_slot(slot_datetime)
    if slot_index is None:
        return 0.0

    # Compute aggregate preference score
    return compute_aggregate_preference_score(
        slot=slot_index,
        scheduling_problem=scheduling_problem,
        context_json=context_json,
        slot_indexer=slot_indexer,
        requester_id=requester_id,
    )
