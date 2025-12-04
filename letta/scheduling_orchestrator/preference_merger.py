"""
Preference merging module for scheduling orchestrator.

Merges standing preferences from context_json with preferences extracted from utterance.
Utterance preferences take precedence if there are conflicts.
"""

from typing import Dict, List, Optional, Any
from .schemas import SchedulingProblem, ParticipantPreference


def merge_standing_preferences(
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]]
) -> SchedulingProblem:
    """
    Merge standing preferences from context_json into scheduling_problem.
    
    Standing preferences in context_json.participants[].preferences are merged
    with preferences extracted from utterance. Utterance preferences take precedence
    if there are conflicts.
    
    Args:
        scheduling_problem: The scheduling problem with preferences extracted from utterance
        context_json: Optional context dictionary with standing preferences
        
    Returns:
        Updated SchedulingProblem with merged preferences
    """
    if not context_json or "participants" not in context_json:
        return scheduling_problem
    
    # Initialize participant_preferences if needed
    if scheduling_problem.participant_preferences is None:
        scheduling_problem.participant_preferences = []
    
    for participant in context_json["participants"]:
        participant_id = participant.get("id")
        if not participant_id:
            continue
        
        prefs = participant.get("preferences", {})
        if not prefs:
            continue
        
        # Find or create participant preference
        existing_pref = next(
            (p for p in scheduling_problem.participant_preferences if p.participant_id == participant_id),
            None
        )
        
        if existing_pref is None:
            existing_pref = ParticipantPreference(participant_id=participant_id)
            scheduling_problem.participant_preferences.append(existing_pref)
        
        # Merge preferences (utterance takes precedence, so only fill if missing)
        if not existing_pref.preferred_times and prefs.get("preferred_times"):
            existing_pref.preferred_times = prefs["preferred_times"]
        
        if not existing_pref.preferred_days and prefs.get("preferred_days"):
            existing_pref.preferred_days = prefs["preferred_days"]
        
        if not existing_pref.avoid_times and prefs.get("avoid_times"):
            existing_pref.avoid_times = prefs["avoid_times"]
        
        if not existing_pref.avoid_days and prefs.get("avoid_days"):
            existing_pref.avoid_days = prefs["avoid_days"]
        
        if not existing_pref.avoid_categories and prefs.get("avoid_categories"):
            existing_pref.avoid_categories = prefs["avoid_categories"]
        
        if not existing_pref.flexibility_notes and prefs.get("flexibility"):
            existing_pref.flexibility_notes = prefs["flexibility"]
        
        # Also merge request-level avoid preferences if not set from utterance
        if not scheduling_problem.avoid_days and prefs.get("avoid_days"):
            # Only apply if this is the requester (first participant)
            if participant == context_json["participants"][0]:
                scheduling_problem.avoid_days = prefs["avoid_days"]
        
        if not scheduling_problem.avoid_times and prefs.get("avoid_times"):
            # Only apply if this is the requester (first participant)
            if participant == context_json["participants"][0]:
                scheduling_problem.avoid_times = prefs["avoid_times"]
    
    return scheduling_problem

