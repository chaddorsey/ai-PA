"""
JSON schema validator for DSPy extraction output.

Validates that extracted JSON matches SchedulingProblem schema.
"""

import json
from typing import Dict, Any, List, Optional, Tuple


def validate_scheduling_problem(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a dictionary matches SchedulingProblem schema.
    
    Args:
        data: Dictionary to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Required fields
    if "participants" not in data:
        errors.append("Missing required field: participants")
    elif not isinstance(data["participants"], list):
        errors.append("participants must be a list")
    elif len(data["participants"]) == 0:
        errors.append("participants list cannot be empty")
    else:
        # Validate each participant is a string
        for i, p in enumerate(data["participants"]):
            if not isinstance(p, str):
                errors.append(f"participants[{i}] must be a string")
    
    if "duration_minutes" not in data:
        errors.append("Missing required field: duration_minutes")
    elif not isinstance(data["duration_minutes"], int):
        errors.append("duration_minutes must be an integer")
    elif data["duration_minutes"] <= 0:
        errors.append("duration_minutes must be positive")
    
    # Optional fields - validate types if present
    optional_fields = {
        "time_window_start": (str, type(None)),
        "time_window_end": (str, type(None)),
        "preferred_times": (list, type(None)),
        "preferred_days": (list, type(None)),
        "participant_preferences": (list, type(None)),
        "avoid_times": (list, type(None)),
        "avoid_days": (list, type(None)),
        "title": (str, type(None)),
        "location": (str, type(None)),
        "min_gap_minutes": (int, type(None)),
        "allow_off_hours": bool,
    }
    
    for field, expected_type in optional_fields.items():
        if field in data:
            if isinstance(expected_type, tuple):
                if not isinstance(data[field], expected_type):
                    errors.append(f"{field} must be one of {expected_type}")
            else:
                if not isinstance(data[field], expected_type):
                    errors.append(f"{field} must be {expected_type}")
    
    # Validate preferred_times if present
    if "preferred_times" in data and data["preferred_times"] is not None:
        if not isinstance(data["preferred_times"], list):
            errors.append("preferred_times must be a list")
        else:
            for i, time_str in enumerate(data["preferred_times"]):
                if not isinstance(time_str, str):
                    errors.append(f"preferred_times[{i}] must be a string")
    
    # Validate preferred_days if present
    if "preferred_days" in data and data["preferred_days"] is not None:
        if not isinstance(data["preferred_days"], list):
            errors.append("preferred_days must be a list")
        else:
            valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for i, day in enumerate(data["preferred_days"]):
                if not isinstance(day, str):
                    errors.append(f"preferred_days[{i}] must be a string")
                elif day not in valid_days:
                    errors.append(f"preferred_days[{i}] must be a valid day name")
    
    # Validate participant_preferences if present
    if "participant_preferences" in data and data["participant_preferences"] is not None:
        if not isinstance(data["participant_preferences"], list):
            errors.append("participant_preferences must be a list")
        else:
            for i, pref in enumerate(data["participant_preferences"]):
                if not isinstance(pref, dict):
                    errors.append(f"participant_preferences[{i}] must be a dictionary")
                else:
                    if "participant_id" not in pref:
                        errors.append(f"participant_preferences[{i}] must have 'participant_id' field")
                    # Optional fields are validated only if present
    
    # Validate avoid_times if present
    if "avoid_times" in data and data["avoid_times"] is not None:
        if not isinstance(data["avoid_times"], list):
            errors.append("avoid_times must be a list")
        else:
            for i, time_str in enumerate(data["avoid_times"]):
                if not isinstance(time_str, str):
                    errors.append(f"avoid_times[{i}] must be a string")
    
    # Validate avoid_days if present
    if "avoid_days" in data and data["avoid_days"] is not None:
        if not isinstance(data["avoid_days"], list):
            errors.append("avoid_days must be a list")
        else:
            valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for i, day in enumerate(data["avoid_days"]):
                if not isinstance(day, str):
                    errors.append(f"avoid_days[{i}] must be a string")
                elif day not in valid_days:
                    errors.append(f"avoid_days[{i}] must be a valid day name")
    
    return len(errors) == 0, errors

