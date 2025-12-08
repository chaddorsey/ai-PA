"""
Validation functions for moved events.

This module provides functions to validate that moved events don't conflict
with any of their participants' calendars.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import pytz


def validate_move_for_all_participants(
    moved_event: Dict[str, Any],
    new_start_slot: int,
    new_end_slot: int,
    event_metadata: Dict[Tuple[str, str], Dict[str, Any]],
    event_participants: Dict[Tuple[str, str], List[str]],
    normalized_data: Dict[str, Any],
    slot_indexer: Any,
    exclude_event_keys: Optional[set] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a moved event doesn't conflict with any of its participants' calendars.
    
    NOTE: This function assumes all participant calendars are already in normalized_data.
    Calendar fetching for missing participants should be done proactively (Phase 5).
    
    Args:
        moved_event: Event being moved (with owner, event_id, new_start, new_end)
        new_start_slot: New start slot index
        new_end_slot: New end slot index
        event_metadata: Map of (participant_id, event_id) -> metadata
        event_participants: Map of (participant_id, event_id) -> list of participant emails
        normalized_data: Normalized data with busy_slots, work_hours_slots (must include all participants)
        slot_indexer: Slot indexer for time calculations
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if move is valid (no conflicts), False otherwise
        - error_message: None if valid, otherwise description of the conflict
    """
    # 1. Get all participants of the moved event
    event_key = (moved_event["owner"], moved_event["event_id"])
    participants = event_participants.get(event_key, [moved_event["owner"]])
    
    # 2. For each participant, check if new location conflicts
    new_event_slots = set(range(new_start_slot, new_end_slot))
    busy_slots = normalized_data.get("busy_slots", {})
    event_slots_map = normalized_data.get("event_slots_map", {})
    
    for participant_id in participants:
        # Check if we have calendar data for this participant
        if participant_id not in busy_slots:
            # Participant not available - should have been fetched proactively
            return False, f"Participant {participant_id} calendar not available (should have been fetched proactively)"
        
        # Check for conflicts (excluding the event being moved and other moved events)
        # Get all events for this participant except the one being moved and other moved events
        participant_other_events = set()
        exclude_keys = exclude_event_keys or set()
        exclude_keys.add(event_key)  # Always exclude the event being moved
        
        for (p_id, e_id), slots in event_slots_map.items():
            if p_id == participant_id and (p_id, e_id) not in exclude_keys:
                participant_other_events.update(slots)
        
        # Check if new location conflicts with other events
        conflicts = new_event_slots.intersection(participant_other_events)
        if conflicts:
            # Find which event(s) conflict
            conflicting_events = []
            for (p_id, e_id), slots in event_slots_map.items():
                if p_id == participant_id and (p_id, e_id) not in exclude_keys:
                    if new_event_slots.intersection(slots):
                        event_meta = event_metadata.get((p_id, e_id), {})
                        event_title = event_meta.get("title", e_id)
                        conflicting_events.append(event_title)
            
            conflict_list = ", ".join(conflicting_events[:3])  # Limit to first 3
            if len(conflicting_events) > 3:
                conflict_list += f" (and {len(conflicting_events) - 3} more)"
            
            return False, f"New location conflicts with existing events for {participant_id}: {conflict_list}"
    
    return True, None


def validate_moved_event_dict(
    moved_event_dict: Dict[str, Any],
    normalized_data: Dict[str, Any],
    slot_indexer: Any,
    exclude_event_keys: Optional[set] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate a moved event from a dictionary format.
    
    This is a convenience wrapper that extracts the necessary information
    from a moved_event dictionary and calls validate_move_for_all_participants.
    
    Args:
        moved_event_dict: Dictionary with keys: owner, event_id, new_start, new_end
        normalized_data: Normalized data with all necessary mappings
        slot_indexer: Slot indexer for time calculations
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Extract event key
    event_key = (moved_event_dict["owner"], moved_event_dict["event_id"])
    
    # Get event metadata and participants
    event_metadata = normalized_data.get("event_metadata", {})
    event_participants = normalized_data.get("event_participants", {})
    
    # Convert new_start and new_end to slots
    new_start_str = moved_event_dict.get("new_start", "")
    new_end_str = moved_event_dict.get("new_end", "")
    
    if not new_start_str or not new_end_str:
        return False, "Missing new_start or new_end in moved_event"
    
    try:
        # Parse datetime strings
        new_start_dt = datetime.fromisoformat(new_start_str.replace("Z", "+00:00"))
        new_end_dt = datetime.fromisoformat(new_end_str.replace("Z", "+00:00"))
        
        # Ensure UTC
        if new_start_dt.tzinfo is None:
            new_start_dt = pytz.UTC.localize(new_start_dt)
        else:
            new_start_dt = new_start_dt.astimezone(pytz.UTC)
        
        if new_end_dt.tzinfo is None:
            new_end_dt = pytz.UTC.localize(new_end_dt)
        else:
            new_end_dt = new_end_dt.astimezone(pytz.UTC)
        
        # Convert to slots
        new_start_slot = slot_indexer.datetime_to_slot(new_start_dt)
        new_end_slot = slot_indexer.datetime_to_slot(new_end_dt)
        
        if new_start_slot is None or new_end_slot is None:
            return False, f"Could not convert new_start or new_end to slots: start={new_start_slot}, end={new_end_slot}"
        
        # Call main validation function
        return validate_move_for_all_participants(
            moved_event_dict,
            new_start_slot,
            new_end_slot,
            event_metadata,
            event_participants,
            normalized_data,
            slot_indexer,
            exclude_event_keys=exclude_event_keys
        )
    except Exception as e:
        return False, f"Error validating moved event: {str(e)}"


def validate_proposal_meeting_time(
    proposal_start_utc: str,
    proposal_end_utc: str,
    participants: List[str],
    normalized_data: Dict[str, Any],
    slot_indexer: Any,
    is_solo_override: bool = False,
    moved_events: Optional[List[Dict[str, Any]]] = None,
    original_event_id: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a proposed meeting time doesn't conflict with any participant's calendar.
    
    This validates the meeting time itself (for zero-conflict proposals), not moved events.
    
    Args:
        proposal_start_utc: Proposed meeting start time (ISO 8601 UTC)
        proposal_end_utc: Proposed meeting end time (ISO 8601 UTC)
        participants: List of participant email addresses
        normalized_data: Normalized data with busy_slots, event_slots_map
        slot_indexer: Slot indexer for time calculations
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if meeting time is valid (no conflicts), False otherwise
        - error_message: None if valid, otherwise description of the conflict
    """
    try:
        # Parse datetime strings
        start_dt = datetime.fromisoformat(proposal_start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal_end_utc.replace("Z", "+00:00"))
        
        # Ensure UTC
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(pytz.UTC)
        
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(pytz.UTC)
        
        # Convert to slots
        start_slot = slot_indexer.datetime_to_slot(start_dt)
        end_slot = slot_indexer.datetime_to_slot(end_dt)
        
        if start_slot is None or end_slot is None:
            return False, f"Could not convert meeting time to slots: start={start_slot}, end={end_slot}"
        
        # Get meeting slots
        meeting_slots = set(range(start_slot, end_slot))
        busy_slots = normalized_data.get("busy_slots", {})
        event_slots_map = normalized_data.get("event_slots_map", {})
        event_metadata = normalized_data.get("event_metadata", {})
        
        # Build set of event keys that are being moved (to exclude from conflict check)
        # This must be done BEFORE checking for conflicts
        moved_event_keys = set()
        moved_event_slots = set()  # All slots occupied by moved events
        if moved_events:
            for moved_event in moved_events:
                owner = moved_event.get("owner")
                event_id = moved_event.get("event_id")
                if owner and event_id:
                    moved_event_keys.add((owner, event_id))
                    # Find all slots for this moved event
                    event_key = (owner, event_id)
                    if event_key in event_slots_map:
                        moved_event_slots.update(event_slots_map[event_key])
        
        # Also exclude the original event being rescheduled (if provided)
        # This prevents the original event from being counted as a conflict
        if original_event_id:
            # Try exact match first
            found_original = False
            for (p_id, e_id), slots in event_slots_map.items():
                if e_id == original_event_id and p_id in participants:
                    moved_event_keys.add((p_id, e_id))
                    moved_event_slots.update(slots)
                    found_original = True
            
            # If exact match failed, try partial match (event IDs might have date suffixes)
            # e.g., original_event_id might be "abc123_20251211T160000Z" but event_slots_map has "abc123"
            if not found_original:
                # Extract base event ID (before underscore if present)
                base_event_id = original_event_id.split('_')[0] if '_' in original_event_id else original_event_id
                for (p_id, e_id), slots in event_slots_map.items():
                    # Check if e_id matches base_event_id or if e_id starts with base_event_id
                    e_id_base = e_id.split('_')[0] if '_' in e_id else e_id
                    if (e_id_base == base_event_id or e_id == original_event_id or original_event_id in e_id or e_id in original_event_id) and p_id in participants:
                        moved_event_keys.add((p_id, e_id))
                        moved_event_slots.update(slots)
                        found_original = True
        
        # CRITICAL: For ASP multi-move solutions, also exclude flexible/protected events that overlap
        # with the meeting's occurs_slots. These events are implicitly "moved" by the ASP solver,
        # even if they're not explicitly in the moved_events list computed by compute_move_deltas.
        # This is necessary because ASP allows overlaps with flexible/protected events (penalized
        # in soft constraints), but compute_move_deltas only identifies events that directly overlap.
        event_protection = normalized_data.get("event_protection", {})
        for (p_id, e_id), slots in event_slots_map.items():
            if p_id in participants:
                # Check if this event overlaps with the meeting slots
                if meeting_slots.intersection(slots):
                    # Check if it's already excluded (moved or original)
                    if (p_id, e_id) in moved_event_keys:
                        continue
                    
                    # Check protection level
                    protection_level = event_protection.get((p_id, e_id), "flexible")
                    
                    # Check if it's internal-only (external events cannot be moved)
                    event_meta = event_metadata.get((p_id, e_id), {})
                    internal_only = event_meta.get("internal_only", True)  # Default to True for backwards compatibility
                    
                    # Exclude flexible/protected (not locked) internal-only events
                    # These are implicitly moved by ASP multi-move solutions
                    if protection_level in ("flexible", "protected") and internal_only:
                        moved_event_keys.add((p_id, e_id))
                        moved_event_slots.update(slots)
        
        # Check each participant's calendar
        for participant_id in participants:
            # Check if we have calendar data for this participant
            # Try exact match first, then try case-insensitive match
            participant_busy = busy_slots.get(participant_id)
            if participant_busy is None:
                # Try case-insensitive match
                participant_busy = next(
                    (busy_slots[key] for key in busy_slots.keys() if key.lower() == participant_id.lower()),
                    None
                )
            
            if participant_busy is None:
                # Participant not available - should have been fetched proactively
                available_keys = list(busy_slots.keys())[:5]  # Show first 5 for debugging
                return False, f"Participant {participant_id} calendar not available (available keys: {available_keys})"
            
            # Check for conflicts
            # If this is a solo_override proposal, we need to exclude solo events from the conflict check
            if is_solo_override:
                # Build a set of non-solo busy slots for this participant
                non_solo_busy_slots = set()
                for (p_id, e_id), slots in event_slots_map.items():
                    if p_id == participant_id:
                        event_meta = event_metadata.get((p_id, e_id), {})
                        num_attendees = event_meta.get("number_of_attendees", 0)
                        if num_attendees > 0:  # Only include non-solo events
                            non_solo_busy_slots.update(slots)
                
                # Exclude slots from moved events
                non_solo_busy_slots -= moved_event_slots
                
                # Check for conflicts with non-solo events only (excluding moved events)
                conflicts = meeting_slots.intersection(non_solo_busy_slots)
            else:
                # Normal validation: check all conflicts, but exclude moved event slots
                # Build participant's busy slots excluding moved events
                participant_busy_excluding_moved = participant_busy - moved_event_slots
                conflicts = meeting_slots.intersection(participant_busy_excluding_moved)
            
            if conflicts:
                # Find which event(s) conflict (excluding events that are being moved)
                conflicting_events = []
                for (p_id, e_id), slots in event_slots_map.items():
                    if p_id == participant_id:
                        if meeting_slots.intersection(slots):
                            # Skip events that are being moved
                            if (p_id, e_id) in moved_event_keys:
                                continue
                            
                            event_meta = event_metadata.get((p_id, e_id), {})
                            # If this is a solo_override proposal, skip solo events (num_attendees == 0)
                            if is_solo_override:
                                num_attendees = event_meta.get("number_of_attendees", 0)
                                if num_attendees == 0:
                                    # This is a solo event - skip it for solo_override proposals
                                    continue
                            event_title = event_meta.get("title", e_id)
                            conflicting_events.append(event_title)
                
                conflict_list = ", ".join(conflicting_events[:3])  # Limit to first 3
                if len(conflicting_events) > 3:
                    conflict_list += f" (and {len(conflicting_events) - 3} more)"
                
                return False, f"Meeting time conflicts with existing events for {participant_id}: {conflict_list}"
        
        return True, None
    except Exception as e:
        return False, f"Error validating meeting time: {str(e)}"

