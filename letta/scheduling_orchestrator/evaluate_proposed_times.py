"""
Main entry point for evaluating proposed meeting times.

This module provides the Evaluate_Proposed_Times tool for Letta agents.
"""
import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Any, Optional, Set, Tuple
import pytz

try:
    from .window_parser import parse_proposed_windows
    from .slot_evaluator import find_available_slots
    from .unified_slot_ranker import rank_evaluated_slots
    from .evaluation_models import (
        ProposedWindow, EvaluatedSlot, EvaluationResult, ConflictInfo
    )
    from .normalizer import normalize_events
    from .identity_working_hours import get_all_participants_working_hours
    from .identity_lookup import lookup_participant_names, resolve_participant_identifier
except ImportError:
    from window_parser import parse_proposed_windows
    from slot_evaluator import find_available_slots
    from unified_slot_ranker import rank_evaluated_slots
    from evaluation_models import (
        ProposedWindow, EvaluatedSlot, EvaluationResult, ConflictInfo
    )
    from normalizer import normalize_events
    from identity_working_hours import get_all_participants_working_hours
    from identity_lookup import lookup_participant_names, resolve_participant_identifier


logger = logging.getLogger(__name__)


# Month abbreviation map for Slack-compatible format
MONTH_ABBREV = {
    1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.",
    5: "May", 6: "Jun.", 7: "Jul.", 8: "Aug.",
    9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dec."
}


def format_evaluation_output(
    ranked_slots: List[EvaluatedSlot],
    participants: List[str],
    participant_names: List[str],
    timezone: str
) -> Dict[str, Any]:
    """
    Format ranked slots for both LLM display and Slack interaction.

    Output format is designed to be parseable by slackbot's parse_orchestrator_proposals():
    - Day headers: "Wednesday, Jan. 29" (no ### prefix, abbreviated month)
    - Time slots: "* 10:00 – 11:00" (bullet, 24-hour time, en-dash separator)
    - Conflict info on day header: "Thursday, Jan. 30  — Conflicts with \"Event\" (Name)"

    Args:
        ranked_slots: List of EvaluatedSlot objects, already ranked
        participants: List of participant email addresses
        participant_names: List of participant display names (same order as participants)
        timezone: Timezone for display (e.g., "America/Los_Angeles")

    Returns:
        Dictionary with:
        - markdown_display: VERBATIM-wrapped text for LLM response
        - interactive_data: Structured data for Slack adapter
    """
    tz = pytz.timezone(timezone)

    # Build participant lookup for names
    name_lookup = dict(zip(participants, participant_names))

    # Group slots by day (in user's timezone)
    # Use tuple key (weekday, month_abbrev, day_num) for proper formatting
    slots_by_day = defaultdict(list)
    day_keys_ordered = []
    for slot in ranked_slots:
        local_start = slot.start.astimezone(tz)
        weekday = local_start.strftime("%A")
        month_abbrev = MONTH_ABBREV[local_start.month]
        day_num = local_start.day
        day_key = (weekday, month_abbrev, day_num)
        if day_key not in slots_by_day:
            day_keys_ordered.append(day_key)
        slots_by_day[day_key].append(slot)

    # Build markdown output
    lines = [
        "[VERBATIM_USER_OUTPUT]",
        f"[PARTICIPANTS:{','.join(participants)}]",
        f"[PARTICIPANT_NAMES:{','.join(participant_names)}]",
        "",
        "## Available Times",
        ""
    ]

    # Add slots grouped by day
    for day_key in day_keys_ordered:
        weekday, month_abbrev, day_num = day_key
        day_slots = slots_by_day[day_key]

        # Build day header with optional conflict annotation
        day_header = f"{weekday}, {month_abbrev} {day_num}"

        # Check if any slot in this day has conflicts - add to day header
        conflicted_slots = [s for s in day_slots if s.conflicts]
        if conflicted_slots:
            # Use first conflict for the day header annotation
            first_conflict = conflicted_slots[0].conflicts[0]
            participant_name = name_lookup.get(first_conflict.participant, first_conflict.participant)
            day_header += f"  — Conflicts with \"{first_conflict.event_title}\" ({participant_name})"

        lines.append(day_header)

        for slot in day_slots:
            local_start = slot.start.astimezone(tz)
            local_end = slot.end.astimezone(tz)

            # Format time in 24-hour format with en-dash separator
            time_str = f"* {local_start.strftime('%H:%M')} – {local_end.strftime('%H:%M')}"
            lines.append(time_str)

        lines.append("")

    # Summary line
    clean_count = sum(1 for s in ranked_slots if s.category == "clean")
    conflict_count = len(ranked_slots) - clean_count

    lines.append("---")
    summary_parts = [f"{len(ranked_slots)} times evaluated"]
    if clean_count > 0:
        summary_parts.append(f"{clean_count} clean")
    if conflict_count > 0:
        summary_parts.append(f"{conflict_count} with conflicts")
    lines.append(", ".join(summary_parts))

    lines.append("[/VERBATIM_USER_OUTPUT]")

    # Build interactive data for Slack
    interactive_data = {
        "participants": participants,
        "participant_names": participant_names,
        "proposals": [
            _slot_to_proposal_dict(slot, tz) for slot in ranked_slots
        ]
    }

    return {
        "markdown_display": "\n".join(lines),
        "interactive_data": interactive_data
    }


def _slot_to_proposal_dict(slot: EvaluatedSlot, tz: pytz.BaseTzInfo) -> Dict[str, Any]:
    """
    Convert EvaluatedSlot to proposal dictionary for Slack rendering.

    Args:
        slot: The EvaluatedSlot to convert
        tz: Timezone for local time display

    Returns:
        Dictionary with slot data in a format suitable for Slack Block Kit rendering
    """
    local_start = slot.start.astimezone(tz)
    local_end = slot.end.astimezone(tz)

    return {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "start_local": local_start.isoformat(),
        "end_local": local_end.isoformat(),
        "category": slot.category,
        "conflicts": [
            {
                "participant": c.participant,
                "event_title": c.event_title,
                "event_time": c.event_time,
                "event_property": c.event_property
            }
            for c in slot.conflicts
        ],
        "score": slot.score
    }


def _slot_to_dict(slot: EvaluatedSlot) -> Dict[str, Any]:
    """
    Convert EvaluatedSlot to dictionary for backward-compatible API response.

    Args:
        slot: The EvaluatedSlot to convert

    Returns:
        Dictionary with slot data in backward-compatible format
    """
    return {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "category": slot.category,
        "conflicts": [
            {
                "participant": c.participant,
                "event": c.event_title,
                "property": c.event_property
            }
            for c in slot.conflicts
        ],
        "score": slot.score
    }


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
    timezone: str = "America/New_York",
    identity_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate externally-proposed meeting time windows.

    Args:
        proposed_times: Natural language time windows, one per line
        participants: Comma-separated list of participant identifiers (emails or Slack IDs).
            Slack IDs (starting with U) are auto-resolved to email addresses.
        duration_minutes: Meeting duration in minutes (default 30)
        timezone: Timezone for interpretation (default America/New_York)
        identity_id: Optional Letta identity ID for preference lookup

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - slots: List of ranked slot dictionaries (backward compatible)
        - markdown_display: VERBATIM-wrapped text for LLM response
        - interactive_data: Structured data for Slack adapter
        - summary: Counts of evaluated slots by category
        - clean_slots, solo_adjust_slots, multi_adjust_slots: Legacy format (backward compatible)
        - no_availability_windows: Windows with no availability
    """
    try:
        # Parse and resolve participant identifiers (email, Slack ID, etc.)
        raw_participants = [p.strip() for p in participants.split(",") if p.strip()]

        if not raw_participants:
            return {"status": "error", "error_message": "No participants provided"}

        # Resolve each identifier to an email address
        participant_list = []
        unresolved = []
        for identifier in raw_participants:
            resolved = resolve_participant_identifier(identifier)
            if resolved:
                participant_list.append(resolved)
            else:
                unresolved.append(identifier)
                logger.warning(f"Could not resolve participant identifier: {identifier}")

        if not participant_list:
            return {
                "status": "error",
                "error_message": f"Could not resolve any participants. Unresolved: {', '.join(unresolved)}"
            }

        if unresolved:
            logger.info(f"Proceeding with {len(participant_list)} resolved participants, {len(unresolved)} unresolved")

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

        # Fetch working hours from Letta identities
        # Convert dates to UTC datetimes for slot calculation
        from_dt_utc = tz.localize(datetime.combine(min_date, datetime.min.time())).astimezone(pytz.UTC)
        to_dt_utc = tz.localize(datetime.combine(max_date, datetime.max.time())).astimezone(pytz.UTC)

        work_hours_slots = get_all_participants_working_hours(
            participant_emails=participant_list,
            from_date_utc=from_dt_utc,
            to_date_utc=to_dt_utc,
            default_hours="M-F 09:00-17:00",
            default_timezone=timezone
        )

        logger.info(
            "Loaded working hours for participants",
            participants=participant_list,
            work_hours_loaded=len(work_hours_slots)
        )

        all_slots = []
        no_availability = []

        for window in windows:
            window_slots = find_available_slots(
                window=window,
                participants=participant_list,
                duration_minutes=duration_minutes,
                busy_slots=busy_slots,
                event_details=event_details,
                work_hours_slots=work_hours_slots
            )

            if not window_slots:
                no_availability.append(window.raw_text)
            else:
                all_slots.extend(window_slots)

        # Use unified slot ranker with preference scoring
        ranked_slots = rank_evaluated_slots(
            slots=all_slots,
            identity_id=identity_id,
            participants=participant_list,
            context_json=context_json,
            reference_date=today
        )

        # Look up participant display names for formatted output
        participant_names_map = lookup_participant_names(participant_list)
        participant_names = [participant_names_map.get(p, p) for p in participant_list]

        # Generate formatted output for display and interaction
        formatted = format_evaluation_output(
            ranked_slots=ranked_slots,
            participants=participant_list,
            participant_names=participant_names,
            timezone=timezone
        )

        # Build backward-compatible result structure (EvaluationResult)
        legacy_result = EvaluationResult(
            clean_slots=[s for s in ranked_slots if s.category == "clean"],
            solo_adjust_slots=[s for s in ranked_slots if s.category == "solo_adjust"],
            multi_adjust_slots=[s for s in ranked_slots if s.category == "multi_adjust"],
            no_availability_windows=no_availability
        )
        legacy_output = _format_output(legacy_result)

        # Combine new and legacy formats
        return {
            "status": "ok",
            # New format fields
            "slots": [_slot_to_dict(s) for s in ranked_slots],
            "markdown_display": formatted["markdown_display"],
            "interactive_data": formatted["interactive_data"],
            "summary": {
                "total_proposed": len(windows),
                "total_evaluated": len(ranked_slots),
                "clean_count": sum(1 for s in ranked_slots if s.category == "clean"),
                "conflict_count": sum(1 for s in ranked_slots if s.category != "clean")
            },
            # Backward compatible fields (from legacy format)
            "clean_slots": legacy_output["clean_slots"],
            "solo_adjust_slots": legacy_output["solo_adjust_slots"],
            "multi_adjust_slots": legacy_output["multi_adjust_slots"],
            "no_availability_windows": no_availability
        }

    except Exception as e:
        logger.exception("Error evaluating proposed times")
        return {"status": "error", "error_message": str(e)}
