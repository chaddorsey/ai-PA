"""
Main entry point for evaluating proposed meeting times.

This module provides the Evaluate_Proposed_Times tool for Letta agents.
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional, Set, Tuple
import pytz

try:
    from .window_parser import parse_proposed_windows
    from .slot_evaluator import find_available_slots
    from .ranking import rank_slots
    from .evaluation_models import (
        ProposedWindow, EvaluatedSlot, EvaluationResult, ConflictInfo
    )
    from .normalizer import normalize_events
except ImportError:
    from window_parser import parse_proposed_windows
    from slot_evaluator import find_available_slots
    from ranking import rank_slots
    from evaluation_models import (
        ProposedWindow, EvaluatedSlot, EvaluationResult, ConflictInfo
    )
    from normalizer import normalize_events


logger = logging.getLogger(__name__)


async def fetch_calendar_data(
    participants: List[str],
    start_date: date,
    end_date: date,
    timezone_str: str
) -> Dict[str, List[Dict]]:
    """
    Fetch calendar events for participants.

    This is a placeholder that should be replaced with actual MCP client call.
    """
    try:
        from .mcp_client import MCPCalendarClient
    except ImportError:
        from mcp_client import MCPCalendarClient

    import os
    mcp_url = os.getenv("N8N_MCP_URL", "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb")

    client = MCPCalendarClient(base_url=mcp_url)
    await client.initialize()

    tz = pytz.timezone(timezone_str)
    start_dt = tz.localize(datetime.combine(start_date, datetime.min.time()))
    end_dt = tz.localize(datetime.combine(end_date, datetime.max.time()))

    events_by_participant = {}
    for participant in participants:
        try:
            events = await client.get_core_event_data(
                calendar_id=participant,
                before=end_dt.isoformat(),
                after=start_dt.isoformat()
            )
            # Normalize event format for compatibility with normalizer
            normalized_events = []
            for event in events:
                normalized_event = {
                    "id": event.get("id", ""),
                    "summary": event.get("summary", ""),
                    "locked": event.get("locked", False),
                    "protected": event.get("protected", False),
                    "flexible": event.get("flexible", True),
                    "transparent": event.get("transparent", False),
                }
                # Handle start/end which may be nested dicts or strings
                start_val = event.get("start", "")
                end_val = event.get("end", "")
                if isinstance(start_val, dict):
                    normalized_event["start"] = start_val.get("dateTime", start_val.get("date", ""))
                else:
                    normalized_event["start"] = start_val
                if isinstance(end_val, dict):
                    normalized_event["end"] = end_val.get("dateTime", end_val.get("date", ""))
                else:
                    normalized_event["end"] = end_val
                normalized_events.append(normalized_event)
            events_by_participant[participant] = normalized_events
        except Exception as e:
            logger.warning(f"Could not fetch calendar for {participant}: {e}")
            events_by_participant[participant] = []

    return events_by_participant


def _convert_to_busy_slots(
    normalized_data: Dict[str, Any],
    participants: List[str]
) -> Tuple[Dict[str, Set[int]], Dict[Tuple[str, str], Dict]]:
    """Convert normalized event data to busy slots and event details."""
    busy_slots = normalized_data.get("busy_slots", {})

    event_details = {}
    event_slots_map = normalized_data.get("event_slots_map", {})
    event_protection = normalized_data.get("event_protection", {})
    event_metadata = normalized_data.get("event_metadata", {})

    for (participant, event_id), slots in event_slots_map.items():
        protection = event_protection.get((participant, event_id), "busy")
        metadata = event_metadata.get((participant, event_id), {})

        event_details[(participant, event_id)] = {
            "property": protection,
            "title": metadata.get("summary", "Event"),
            "slots": slots
        }

    return busy_slots, event_details


def _format_output(result: EvaluationResult) -> Dict[str, Any]:
    """Format EvaluationResult as dict for Letta tool output."""
    return {
        "status": "ok",
        "clean_slots": [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "display": f"{slot.start.strftime('%a %m/%d %I:%M%p')}-{slot.end.strftime('%I:%M%p')}"
            }
            for slot in result.clean_slots
        ],
        "solo_adjust_slots": [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "display": f"{slot.start.strftime('%a %m/%d %I:%M%p')}-{slot.end.strftime('%I:%M%p')}",
                "conflicts": [
                    {"participant": c.participant, "event": c.event_title, "property": c.event_property}
                    for c in slot.conflicts
                ]
            }
            for slot in result.solo_adjust_slots
        ],
        "multi_adjust_slots": [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "display": f"{slot.start.strftime('%a %m/%d %I:%M%p')}-{slot.end.strftime('%I:%M%p')}",
                "conflicts": [
                    {"participant": c.participant, "event": c.event_title, "property": c.event_property}
                    for c in slot.conflicts
                ]
            }
            for slot in result.multi_adjust_slots
        ],
        "no_availability_windows": result.no_availability_windows
    }


async def evaluate_proposed_times(
    proposed_times: str,
    participants: str,
    duration_minutes: int = 30,
    timezone: str = "America/New_York"
) -> Dict[str, Any]:
    """
    Evaluate externally-proposed meeting time windows.

    Args:
        proposed_times: Natural language time windows, one per line
        participants: Comma-separated list of participant emails
        duration_minutes: Meeting duration in minutes (default 30)
        timezone: Timezone for interpretation (default America/New_York)

    Returns:
        Dictionary with clean_slots, solo_adjust_slots, multi_adjust_slots,
        and no_availability_windows
    """
    try:
        participant_list = [p.strip() for p in participants.split(",") if p.strip()]

        if not participant_list:
            return {"status": "error", "error_message": "No participants provided"}

        tz = pytz.timezone(timezone)
        today = datetime.now(tz).date()

        windows = parse_proposed_windows(proposed_times, reference_date=today)

        if not windows:
            return {"status": "error", "error_message": "Could not parse any time windows from input"}

        min_date = min(w.date for w in windows)
        max_date = max(w.date for w in windows)

        calendar_data = await fetch_calendar_data(
            participants=participant_list,
            start_date=min_date,
            end_date=max_date,
            timezone_str=timezone
        )

        context_json = {
            "timeframe": {"from": min_date.isoformat(), "to": max_date.isoformat(), "tz": timezone},
            "participants": [{"id": p} for p in participant_list]
        }

        normalized = normalize_events(calendar_data, context_json)
        busy_slots, event_details = _convert_to_busy_slots(normalized, participant_list)

        all_slots = []
        no_availability = []

        for window in windows:
            window_slots = find_available_slots(
                window=window,
                participants=participant_list,
                duration_minutes=duration_minutes,
                busy_slots=busy_slots,
                event_details=event_details
            )

            if not window_slots:
                no_availability.append(window.raw_text)
            else:
                all_slots.extend(window_slots)

        ranked_slots = rank_slots(all_slots, reference_date=today)

        result = EvaluationResult(
            clean_slots=[s for s in ranked_slots if s.category == "clean"],
            solo_adjust_slots=[s for s in ranked_slots if s.category == "solo_adjust"],
            multi_adjust_slots=[s for s in ranked_slots if s.category == "multi_adjust"],
            no_availability_windows=no_availability
        )

        return _format_output(result)

    except Exception as e:
        logger.exception("Error evaluating proposed times")
        return {"status": "error", "error_message": str(e)}
