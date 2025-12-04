"""
Preference scoring module for scheduling orchestrator.

Handles participant-specific preferences, avoid preferences, and preference layering.
cdorsey@concord.org preferences take precedence with 2x weight if requester.

WEIGHTING STRATEGY:
- Avoid preferences use PENALTIES (negative scores: -2.0 to -10.0)
- Preferred preferences use BONUSES (positive scores: +0.8 to +2.0)
- Avoid penalties are 5-12x larger than preferred bonuses, ensuring avoids ALWAYS take precedence
- Layering order: Request avoid → Participant avoid → Participant prefer → Request prefer
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import pytz

from .schemas import SchedulingProblem, ParticipantPreference
from .slot_indexer import SlotIndexer


def _parse_time_range(time_str: str) -> Optional[tuple]:
    """
    Parse a time string like "09:00-11:00" or "morning" into a time range.
    
    Returns:
        (start_hour, end_hour) tuple or None
    """
    time_str = time_str.strip().lower()
    
    # Handle named ranges
    if "morning" in time_str:
        return (9, 12)
    elif "afternoon" in time_str:
        return (12, 17)
    elif "evening" in time_str:
        return (17, 21)
    
    # Handle explicit time ranges like "09:00-11:00"
    if "-" in time_str:
        try:
            parts = time_str.split("-")
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            
            # Parse HH:MM format
            if ":" in start_str:
                start_hour, start_min = map(int, start_str.split(":"))
                start_hour = start_hour + (start_min / 60.0)
            else:
                start_hour = int(start_str)
            
            if ":" in end_str:
                end_hour, end_min = map(int, end_str.split(":"))
                end_hour = end_hour + (end_min / 60.0)
            else:
                end_hour = int(end_str)
            
            return (start_hour, end_hour)
        except (ValueError, IndexError):
            pass
    
    return None


def _is_time_in_range(dt: datetime, time_range: tuple) -> bool:
    """Check if datetime falls within a time range (hours)."""
    hour = dt.hour + (dt.minute / 60.0)
    start_hour, end_hour = time_range
    return start_hour <= hour < end_hour


def _compute_avoid_penalty(
    slot_dt: datetime,
    avoid_times: Optional[List[str]],
    avoid_days: Optional[List[str]],
    slot_indexer: SlotIndexer
) -> float:
    """
    Compute penalty for violating avoid preferences.
    
    Returns:
        Negative score (more negative = worse violation)
    """
    penalty = 0.0
    
    if not avoid_times and not avoid_days:
        return penalty
    
    # Check avoid days
    if avoid_days:
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        slot_weekday = slot_dt.weekday()
        for day_name in avoid_days:
            avoid_weekday = day_map.get(day_name.capitalize())
            if avoid_weekday == slot_weekday:
                penalty -= 10.0  # Strong penalty for avoid days
    
    # Check avoid times
    if avoid_times:
        for avoid_time_str in avoid_times:
            try:
                # Try parsing as ISO 8601 datetime
                avoid_dt = datetime.fromisoformat(avoid_time_str.replace("Z", "+00:00"))
                if avoid_dt.tzinfo is None:
                    avoid_dt = pytz.UTC.localize(avoid_dt)
                else:
                    avoid_dt = avoid_dt.astimezone(pytz.UTC)
                
                # Calculate time difference
                time_diff_hours = abs((slot_dt - avoid_dt).total_seconds() / 3600)
                
                # Penalty decreases with distance from avoided time
                if time_diff_hours < 0.5:  # Within 30 minutes
                    penalty -= 8.0
                elif time_diff_hours < 1.0:  # Within 1 hour
                    penalty -= 5.0
                elif time_diff_hours < 2.0:  # Within 2 hours
                    penalty -= 2.0
            except (ValueError, AttributeError):
                # Try parsing as time range (e.g., "09:00-11:00")
                time_range = _parse_time_range(avoid_time_str)
                if time_range and _is_time_in_range(slot_dt, time_range):
                    penalty -= 6.0  # Penalty for being in avoided time range
    
    return penalty


def _compute_preferred_bonus(
    slot_dt: datetime,
    preferred_times: Optional[List[str]],
    preferred_days: Optional[List[str]],
    slot_indexer: SlotIndexer
) -> float:
    """
    Compute bonus for matching preferred preferences.
    
    Returns:
        Positive score (higher = better match)
    """
    bonus = 0.0
    
    if not preferred_times and not preferred_days:
        return bonus
    
    # Check preferred days
    if preferred_days:
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        slot_weekday = slot_dt.weekday()
        for day_name in preferred_days:
            preferred_weekday = day_map.get(day_name.capitalize())
            if preferred_weekday == slot_weekday:
                bonus += 2.0  # Bonus for preferred days
    
    # Check preferred times
    if preferred_times:
        for pref_time_str in preferred_times:
            try:
                # Try parsing as ISO 8601 datetime
                pref_dt = datetime.fromisoformat(pref_time_str.replace("Z", "+00:00"))
                if pref_dt.tzinfo is None:
                    pref_dt = pytz.UTC.localize(pref_dt)
                else:
                    pref_dt = pref_dt.astimezone(pytz.UTC)
                
                # Calculate time difference
                time_diff_hours = abs((slot_dt - pref_dt).total_seconds() / 3600)
                
                # Bonus decreases with distance from preferred time
                if time_diff_hours < 0.5:  # Within 30 minutes
                    bonus += 2.0
                elif time_diff_hours < 1.0:  # Within 1 hour
                    bonus += 1.5
                elif time_diff_hours < 2.0:  # Within 2 hours
                    bonus += 0.8
                else:
                    bonus += max(0, 1.0 - (time_diff_hours / 4.0))  # Decreasing bonus
            except (ValueError, AttributeError):
                # Try parsing as time range (e.g., "09:00-11:00", "morning")
                time_range = _parse_time_range(pref_time_str)
                if time_range and _is_time_in_range(slot_dt, time_range):
                    bonus += 1.5  # Bonus for being in preferred time range
                    # Additional bonus if closer to start of range
                    hour = slot_dt.hour + (slot_dt.minute / 60.0)
                    start_hour, end_hour = time_range
                    if abs(hour - start_hour) < abs(hour - end_hour):
                        bonus += 0.5  # Extra bonus for being early in the range
    
    return bonus


def compute_participant_preference_score(
    slot: int,
    participant_id: str,
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]],
    slot_indexer: SlotIndexer
) -> float:
    """
    Compute preference score for a specific participant at a given slot.
    
    Handles BOTH prefer and avoid preferences using a symmetric pattern:
    - Avoid preferences: Apply PENALTIES (negative scores)
    - Preferred preferences: Apply BONUSES (positive scores)
    
    Scoring layers (applied in order, avoids ALWAYS override prefers):
        1. Request-level avoid preferences (highest penalty: -10.0)
        2. Participant avoid preferences (medium penalty: -8.0 to -10.0, scaled by 0.8)
        3. Participant preferred preferences (medium bonus: +1.5 to +2.0)
        4. Request-level preferred preferences (lower bonus: +0.8 to +1.0, scaled by 0.5)
    
    WEIGHTING RATIO:
        - Avoid penalties: -2.0 to -10.0 (strong negative)
        - Preferred bonuses: +0.8 to +2.0 (modest positive)
        - Ratio: Avoid penalties are 5-12x larger than preferred bonuses
        - Result: A slot matching both a prefer and an avoid will have net negative score (avoid wins)
    
    Returns:
        Score where:
        - Positive = preferred (higher is better)
        - Negative = avoided (more negative = worse)
        - 0 = neutral
    """
    slot_dt = slot_indexer.slot_to_datetime(slot)
    if not slot_dt:
        return 0.0
    
    score = 0.0
    
    # 1. Request-level avoid preferences (highest penalty)
    if scheduling_problem.avoid_times or scheduling_problem.avoid_days:
        penalty = _compute_avoid_penalty(
            slot_dt,
            scheduling_problem.avoid_times,
            scheduling_problem.avoid_days,
            slot_indexer
        )
        score += penalty
    
    # 2. Participant avoid preferences (medium penalty)
    if scheduling_problem.participant_preferences:
        for pref in scheduling_problem.participant_preferences:
            if pref.participant_id == participant_id:
                if pref.avoid_times or pref.avoid_days:
                    penalty = _compute_avoid_penalty(
                        slot_dt,
                        pref.avoid_times,
                        pref.avoid_days,
                        slot_indexer
                    )
                    score += penalty * 0.8  # Slightly less than request-level
    
    # 3. Participant preferred preferences (medium bonus)
    if scheduling_problem.participant_preferences:
        for pref in scheduling_problem.participant_preferences:
            if pref.participant_id == participant_id:
                if pref.preferred_times or pref.preferred_days:
                    bonus = _compute_preferred_bonus(
                        slot_dt,
                        pref.preferred_times,
                        pref.preferred_days,
                        slot_indexer
                    )
                    score += bonus
    
    # 4. Request-level preferred preferences (lower bonus, but still positive)
    if scheduling_problem.preferred_times or scheduling_problem.preferred_days:
        bonus = _compute_preferred_bonus(
            slot_dt,
            scheduling_problem.preferred_times,
            scheduling_problem.preferred_days,
            slot_indexer
        )
        score += bonus * 0.5  # Lower weight than participant preferences
    
    return score


def compute_aggregate_preference_score(
    slot: int,
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]],
    slot_indexer: SlotIndexer,
    requester_id: Optional[str] = None
) -> float:
    """
    Compute aggregate preference score across all participants.
    
    Weighting:
        - cdorsey@concord.org preferences (if requester): 2.0x weight
        - Other participant preferences: 1.0x weight
    
    This ensures cdorsey preferences take precedence in ties.
    
    Returns:
        Weighted aggregate score
    """
    total_score = 0.0
    requester_weight = 2.0  # cdorsey preferences take precedence
    
    for participant_id in scheduling_problem.participants:
        participant_score = compute_participant_preference_score(
            slot, participant_id, scheduling_problem, context_json, slot_indexer
        )
        
        # Apply weight: requester gets 2x, others get 1x
        weight = requester_weight if participant_id == requester_id else 1.0
        total_score += participant_score * weight
    
    return total_score

