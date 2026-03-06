"""
Solo Availability Tool for Letta

This tool provides a simple interface for finding a user's own available time slots.
It wraps the full scheduling orchestrator for the single-participant case.

Use cases:
- "When am I available for a 45-minute meeting this week?"
- "What 30-minute slots do I have open next Monday?"
- "Find me some free time for a call this afternoon"
"""

from typing import Dict, Any, Optional


def find_my_availability(
    user_id: str,
    duration_minutes: int,
    date_range: Optional[str] = None,
    time_preference: Optional[str] = None,
    max_results: int = 10
) -> Dict[str, Any]:
    """
    Find available time slots in the user's calendar.

    Use this tool when the user asks about their own availability without
    specifying other participants. Examples:
    - "When am I free this week?"
    - "Find me a 30-minute slot tomorrow"
    - "What times work for a call next Tuesday afternoon?"

    This tool checks the user's calendar and returns open slots that fit
    the requested duration, respecting work hours and existing commitments.

    Args:
        user_id: The user's email address (e.g., "cdorsey@concord.org").
                 This is used to fetch their calendar events.
        duration_minutes: Length of the meeting slot needed (e.g., 30, 45, 60).
                         Common values: 15, 30, 45, 60, 90.
        date_range: Time period to search. Supports natural language:
                    - "today", "tomorrow", "this week", "next week"
                    - "Monday", "Tuesday afternoon", "Friday morning"
                    - "2026-02-05" (specific date)
                    - "2026-02-03 to 2026-02-07" (date range)
                    If not provided, defaults to the next 5 business days.
        time_preference: Optional preference for time of day:
                        - "morning" (before noon)
                        - "afternoon" (noon to 5pm)
                        - "evening" (after 5pm)
                        - None (any time within work hours)
        max_results: Maximum number of slots to return (default 10, max 20).

    Returns:
        Dictionary with:
        - status: "ok" | "no_availability" | "error"
        - available_slots: List of available time slots, each with:
            - start: Start time (ISO format)
            - end: End time (ISO format)
            - day: Day of week (e.g., "Monday")
            - date: Date (e.g., "Feb 5")
            - time: Time range (e.g., "2:00 PM - 2:45 PM")
            - conflicts_with: Any blocking events that could be moved (empty for clean slots)
        - summary: Human-readable summary
        - search_range: The date range that was searched
    """
    # Import all dependencies inside function for Letta tool extraction
    import os
    import json
    import traceback
    from datetime import datetime, timedelta
    import pytz
    import requests

    try:
        # Validate inputs
        if not user_id or "@" not in user_id:
            return {
                "status": "error",
                "error_message": "Invalid user_id. Please provide a valid email address.",
                "available_slots": []
            }

        if duration_minutes is None:
            duration_minutes = 30
        duration_minutes = max(15, min(180, duration_minutes))  # Clamp to 15-180 min

        max_results = max(1, min(20, max_results or 10))

        # Parse date_range to get from/to dates
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Default: next 5 business days
        from_date = today
        to_date = today + timedelta(days=7)

        if date_range:
            date_range_lower = date_range.lower().strip()

            if date_range_lower == "today":
                from_date = today
                to_date = today + timedelta(days=1)
            elif date_range_lower == "tomorrow":
                from_date = today + timedelta(days=1)
                to_date = today + timedelta(days=2)
            elif date_range_lower in ["this week", "this-week"]:
                # Rest of this week (through Sunday)
                days_until_sunday = 6 - today.weekday()
                from_date = today
                to_date = today + timedelta(days=days_until_sunday + 1)
            elif date_range_lower in ["next week", "next-week"]:
                # Next Monday through Friday
                days_until_monday = (7 - today.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                from_date = today + timedelta(days=days_until_monday)
                to_date = from_date + timedelta(days=5)
            elif " to " in date_range_lower:
                # Date range: "2026-02-03 to 2026-02-07"
                parts = date_range_lower.split(" to ")
                try:
                    from_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").replace(tzinfo=tz)
                    to_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)
                except ValueError:
                    pass  # Use defaults
            else:
                # Try parsing as single date
                try:
                    from_date = datetime.strptime(date_range_lower, "%Y-%m-%d").replace(tzinfo=tz)
                    to_date = from_date + timedelta(days=1)
                except ValueError:
                    # Try day names
                    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    for i, day in enumerate(day_names):
                        if day in date_range_lower:
                            days_ahead = (i - today.weekday()) % 7
                            if days_ahead == 0 and now.hour >= 17:
                                days_ahead = 7  # If it's late, go to next week
                            from_date = today + timedelta(days=days_ahead)
                            to_date = from_date + timedelta(days=1)
                            break

        # Build context for orchestrate_scheduling
        context = {
            "timeframe": {
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
                "tz": "America/New_York"
            },
            "participants": [
                {
                    "id": user_id.split("@")[0],
                    "email": user_id,
                    "work_hours": "M-F 08:00-18:00"  # Default work hours
                }
            ]
        }

        # Build utterance for the orchestrator
        utterance = f"Find {duration_minutes}-minute available slots"
        if time_preference:
            utterance += f" in the {time_preference}"

        # Call scheduling-orchestrator-api via HTTP
        orchestrator_url = os.environ.get(
            "SCHEDULING_ORCHESTRATOR_URL",
            "http://scheduling-orchestrator-api:8095"
        ).rstrip("/")

        try:
            resp = requests.post(
                f"{orchestrator_url}/schedule",
                json={
                    "utterance": utterance,
                    "participant_ids": [user_id],
                    "user_id": user_id,
                    "context_json": json.dumps(context),
                },
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as api_err:
            return {
                "status": "error",
                "error_message": f"Scheduling orchestrator unavailable: {str(api_err)}",
                "available_slots": [],
                "debug": {"orchestrator_url": orchestrator_url},
            }

        # Debug: log raw result from orchestrate_scheduling
        debug_info = {
            "orchestrator_status": result.get("status"),
            "orchestrator_proposals_count": len(result.get("proposals", [])),
            "orchestrator_error": result.get("error_message"),
        }

        # Extract verbatim_user_output from orchestrator for interactive UI
        verbatim = result.get("verbatim_user_output") or ""
        if not verbatim:
            user_display = result.get("user_display")
            if isinstance(user_display, dict):
                verbatim = user_display.get("verbatim_user_output", "")

        # Process results into simpler format
        if result.get("status") == "ok":
            proposals = result.get("proposals", [])

            available_slots = []
            for prop in proposals[:max_results]:
                # Parse proposal time - orchestrator uses start_utc/end_utc
                start_str = prop.get("start_utc") or prop.get("start_time") or prop.get("start")
                end_str = prop.get("end_utc") or prop.get("end_time") or prop.get("end")

                if not start_str:
                    continue

                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    if end_str:
                        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    else:
                        end_dt = start_dt + timedelta(minutes=duration_minutes)

                    # Convert to local timezone
                    start_local = start_dt.astimezone(tz)
                    end_local = end_dt.astimezone(tz)

                    # Apply time preference filter
                    if time_preference:
                        hour = start_local.hour
                        if time_preference.lower() == "morning" and hour >= 12:
                            continue
                        elif time_preference.lower() == "afternoon" and (hour < 12 or hour >= 17):
                            continue
                        elif time_preference.lower() == "evening" and hour < 17:
                            continue

                    slot = {
                        "start": start_local.isoformat(),
                        "end": end_local.isoformat(),
                        "day": start_local.strftime("%A"),
                        "date": start_local.strftime("%b %d"),
                        "time": f"{start_local.strftime('%I:%M %p').lstrip('0')} - {end_local.strftime('%I:%M %p').lstrip('0')}",
                        "conflicts_with": prop.get("conflicts", []) or prop.get("moves_required", [])
                    }
                    available_slots.append(slot)
                except (ValueError, TypeError):
                    continue

            if available_slots:
                # Generate summary
                clean_count = sum(1 for s in available_slots if not s["conflicts_with"])
                conflict_count = len(available_slots) - clean_count

                summary_parts = [f"Found {len(available_slots)} available {duration_minutes}-minute slots"]
                if clean_count > 0:
                    summary_parts.append(f"{clean_count} with no conflicts")
                if conflict_count > 0:
                    summary_parts.append(f"{conflict_count} requiring override of blocking time")

                ret = {
                    "status": "ok",
                    "available_slots": available_slots,
                    "summary": ". ".join(summary_parts) + ".",
                    "search_range": {
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d")
                    },
                    "debug": debug_info
                }
                if verbatim:
                    ret["verbatim_user_output"] = verbatim
                return ret
            else:
                # Add first few proposals for debugging - capture ALL fields
                raw_proposals = result.get("proposals", [])[:2]
                debug_info["raw_proposals_sample"] = [
                    {k: str(v)[:100] for k, v in p.items()} if isinstance(p, dict) else str(p)[:200]
                    for p in raw_proposals
                ] if raw_proposals else []
                debug_info["proposal_keys"] = list(raw_proposals[0].keys()) if raw_proposals and isinstance(raw_proposals[0], dict) else []

                ret = {
                    "status": "no_availability",
                    "available_slots": [],
                    "summary": f"No {duration_minutes}-minute slots found in the requested time period.",
                    "search_range": {
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d")
                    },
                    "debug": debug_info
                }
                if verbatim:
                    ret["verbatim_user_output"] = verbatim
                return ret

        elif result.get("status") == "unsat":
            ret = {
                "status": "no_availability",
                "available_slots": [],
                "summary": "Your calendar is fully booked during the requested time period.",
                "search_range": {
                    "from": from_date.strftime("%Y-%m-%d"),
                    "to": to_date.strftime("%Y-%m-%d")
                },
                "suggestions": result.get("relaxations", []),
                "debug": debug_info
            }
            if verbatim:
                ret["verbatim_user_output"] = verbatim
            return ret
        else:
            return {
                "status": "error",
                "error_message": result.get("error_message", "Scheduling check failed"),
                "available_slots": [],
                "debug": debug_info
            }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to check availability: {str(e)}\n{traceback.format_exc()}",
            "available_slots": []
        }
