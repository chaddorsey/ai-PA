"""
Formatting utilities for generating user-facing display content.

This module provides functions to convert structured proposal data into
human-readable formatted strings for display to end users.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import pytz
import uuid

from .schemas import Proposal, MovedEvent, EventMetadata, FormattedProposal


def format_datetime_for_display(dt_str: str, timezone_str: str = "America/New_York") -> str:
    """
    Format an ISO 8601 UTC datetime string for user display.
    
    Args:
        dt_str: ISO 8601 UTC datetime string
        timezone_str: Target timezone (default: Eastern Time)
    
    Returns:
        Formatted string like "Monday, December 15, 2025 at 2:00 PM EST"
    """
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        dt_local = dt.astimezone(tz)
        
        # Format: "Monday, December 15, 2025 at 2:00 PM EST"
        weekday = dt_local.strftime("%A")
        month = dt_local.strftime("%B")
        day = dt_local.day
        year = dt_local.year
        time_str = dt_local.strftime("%I:%M %p").lstrip("0")
        tz_abbr = dt_local.strftime("%Z")
        
        return f"{weekday}, {month} {day}, {year} at {time_str} {tz_abbr}"
    except Exception:
        # Fallback to original string if parsing fails
        return dt_str


def format_time_only(dt_str: str, timezone_str: str = "America/New_York") -> str:
    """Format just the time portion for display."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%I:%M %p %Z").lstrip("0")
    except Exception:
        return dt_str


def format_short_date(dt_str: str, timezone_str: str = "America/New_York") -> str:
    """Format a short date/time for quick scanning."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        dt_local = dt.astimezone(tz)
        
        weekday_short = dt_local.strftime("%a")
        month_short = dt_local.strftime("%b")
        day = dt_local.day
        time_str = dt_local.strftime("%I:%M %p").lstrip("0")
        
        return f"{weekday_short}, {month_short} {day} at {time_str}"
    except Exception:
        return dt_str


def format_day_header(dt_str: str, timezone_str: str = "America/New_York") -> str:
    """Format a day header like 'Wednesday, Dec. 10'."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        dt_local = dt.astimezone(tz)
        
        weekday = dt_local.strftime("%A")
        month_short = dt_local.strftime("%b")
        day = dt_local.day
        
        return f"{weekday}, {month_short}. {day}"
    except Exception:
        return dt_str


def format_time_range(start_dt_str: str, end_dt_str: str, timezone_str: str = "America/New_York") -> str:
    """Format a time range like '4:15 – 5:00'."""
    try:
        start_dt = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))
        
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(pytz.UTC)
        
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)
        
        # Format time in 12-hour format, removing leading zero from hour
        start_time_str = start_local.strftime("%I:%M").lstrip("0")
        end_time_str = end_local.strftime("%I:%M").lstrip("0")
        
        return f"{start_time_str} – {end_time_str}"
    except Exception:
        return f"{start_dt_str} – {end_dt_str}"


def format_move_description(moved_events: List[MovedEvent], event_registry: Dict[str, EventMetadata]) -> Optional[str]:
    """
    Format a human-readable description of moved events.
    
    Args:
        moved_events: List of moved events
        event_registry: Map of event_id -> EventMetadata
    
    Returns:
        Formatted string like "Move 'Chad/Paul' meeting 75 minutes later (12:00 PM → 1:15 PM)"
        or None if no moves
    """
    if not moved_events:
        return None
    
    descriptions = []
    for moved in moved_events:
        event_meta = event_registry.get(moved.event_id, None)
        event_title = event_meta.human_readable if event_meta else moved.event_id[:40]
        
        # Format time change
        old_time = format_time_only(moved.old_start)
        new_time = format_time_only(moved.new_start)
        
        # Determine direction
        shift_minutes = moved.shift_minutes
        if shift_minutes > 0:
            direction = "later"
        elif shift_minutes < 0:
            direction = "earlier"
        else:
            direction = "same time"
        
        # Format shift amount
        abs_minutes = abs(shift_minutes)
        if abs_minutes < 60:
            shift_str = f"{abs_minutes} minutes"
        else:
            hours = abs_minutes // 60
            minutes = abs_minutes % 60
            if minutes == 0:
                shift_str = f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                shift_str = f"{hours}h {minutes}m"
        
        descriptions.append(
            f"Move '{event_title}' {shift_str} {direction} ({old_time} → {new_time})"
        )
    
    return "; ".join(descriptions)


def format_override_description(proposal: Proposal, event_registry: Dict[str, EventMetadata]) -> Optional[str]:
    """
    Format a human-readable description of overridden events.
    
    Args:
        proposal: The proposal
        event_registry: Map of event_id -> EventMetadata
    
    Returns:
        Formatted string like "Override 'Hold' solo event"
        or None if no overrides
    """
    notes = proposal.notes_for_invite or ""
    if "solo/blocking events" not in notes.lower():
        return None
    
    # Extract event titles from notes if available, otherwise generic message
    if "override" in notes.lower():
        return "Override solo/blocking events"
    
    return "Override solo/blocking events"


def format_detailed_proposal(proposal: Proposal, rank: int, event_registry: Dict[str, EventMetadata], timezone_str: str = "America/New_York") -> str:
    """
    Generate detailed formatted text for a proposal.
    
    Args:
        proposal: The proposal to format
        rank: Rank of the proposal
        event_registry: Map of event_id -> EventMetadata
        timezone_str: Target timezone
    
    Returns:
        Multi-line formatted string
    """
    lines = []
    
    # Start time and end time
    start_display = format_datetime_for_display(proposal.start_utc, timezone_str)
    end_display = format_time_only(proposal.end_utc, timezone_str)
    
    lines.append(f"Start: {start_display}")
    lines.append(f"End: {end_display}")
    
    # Type/category
    category = proposal.category or "unknown"
    if category == "zero_conflict":
        type_str = "Free slot (zero-conflict)"
    elif category == "single_move":
        type_str = "Requires moving 1 meeting"
    elif category == "solo_override":
        type_str = "Solo-override slot"
    elif category == "multi_move":
        type_str = f"Requires moving {len(proposal.moved_events)} meetings"
    else:
        type_str = "Meeting slot"
    
    lines.append(f"Type: {type_str}")
    
    # Move description if applicable
    if proposal.moved_events:
        move_desc = format_move_description(proposal.moved_events, event_registry)
        if move_desc:
            lines.append(f"Move: {move_desc}")
    
    # Override description if applicable
    override_desc = format_override_description(proposal, event_registry)
    if override_desc:
        lines.append(f"Override: {override_desc}")
    
    return "\n".join(lines)


def format_short_summary(proposal: Proposal, rank: int, timezone_str: str = "America/New_York") -> str:
    """
    Generate a short one-line summary.
    
    Args:
        proposal: The proposal
        rank: Rank of the proposal
        timezone_str: Target timezone
    
    Returns:
        One-line summary like "Monday, Dec 15 at 1:15 PM (Free slot)"
    """
    date_time = format_short_date(proposal.start_utc, timezone_str)
    
    category = proposal.category or "unknown"
    if category == "zero_conflict":
        type_str = "Free slot"
    elif category == "single_move":
        type_str = "1 move required"
    elif category == "solo_override":
        type_str = "Override"
    else:
        type_str = "Meeting"
    
    return f"{date_time} ({type_str})"


def format_proposal_for_display(
    proposal: Proposal,
    rank: int,
    category: str,
    event_registry: Dict[str, EventMetadata],
    timezone_str: str = "America/New_York"
) -> FormattedProposal:
    """
    Generate user-facing formatted content for a proposal.
    
    Args:
        proposal: The proposal to format
        rank: Rank of the proposal
        category: Display category ('best_options', 'with_moves', 'with_overrides')
        event_registry: Map of event_id -> EventMetadata
        timezone_str: Target timezone
    
    Returns:
        FormattedProposal object
    """
    display_text = format_detailed_proposal(proposal, rank, event_registry, timezone_str)
    short_summary = format_short_summary(proposal, rank, timezone_str)
    move_summary = format_move_description(proposal.moved_events, event_registry) if proposal.moved_events else None
    override_summary = format_override_description(proposal, event_registry)
    
    return FormattedProposal(
        rank=rank,
        category=category,
        display_text=display_text,
        short_summary=short_summary,
        move_summary=move_summary,
        override_summary=override_summary
    )


def generate_proposal_id() -> str:
    """Generate a unique proposal ID."""
    return f"prop_{uuid.uuid4().hex[:12]}"


def format_refined_user_display(
    free_proposals: List[Proposal],
    move_proposals: List[Proposal],
    override_proposals: List[Proposal],
    event_registry: Dict[str, EventMetadata],
    normalized_data: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    timezone_str: str = "America/New_York",
    context_json: Optional[Dict[str, Any]] = None,
    external_participants: Optional[List[str]] = None
) -> str:
    """
    Generate refined user-facing display with grouped, prioritized formatting.
    
    Format:
    - Rescheduling header (if rescheduling): Shows original meeting details
    - "Best options" section: Zero-conflict proposals grouped by day
    - "If We Can Move or Override" section: Move and override proposals
    
    Args:
        free_proposals: Zero-conflict proposals (already sorted by priority)
        move_proposals: Proposals requiring event moves (already sorted by priority)
        override_proposals: Solo-override proposals (already sorted by priority)
        event_registry: Map of event_id -> EventMetadata
        user_id: User's email address for identifying override events
        timezone_str: Target timezone
    
    Returns:
        Multi-line formatted string ready for display
    """
    lines = []
    
    # Check if this is a rescheduling operation by looking for original_event_id in any proposal
    all_proposals = free_proposals + move_proposals + override_proposals
    rescheduling_proposal = None
    for prop in all_proposals:
        if prop.original_event_id or prop.original_event_details:
            rescheduling_proposal = prop
            break
    
    # Add rescheduling header if applicable
    if rescheduling_proposal and rescheduling_proposal.original_event_details:
        original_details = rescheduling_proposal.original_event_details
        original_title = original_details.get("title", "Meeting")
        original_start = original_details.get("start_utc")
        original_end = original_details.get("end_utc")
        original_participants = original_details.get("participants", [])
        
        lines.append("## Rescheduling Options")
        lines.append("")
        lines.append(f"**Original Meeting:** {original_title}")
        
        if original_start and original_end:
            original_day = format_day_header(original_start, timezone_str)
            original_time = format_time_range(original_start, original_end, timezone_str)
            lines.append(f"**Current Time:** {original_day} at {original_time}")
        
        if original_participants:
            # Format participant list (show names if available, otherwise emails)
            participant_display = []
            for p in original_participants[:3]:  # Show first 3
                if "@" in p:
                    name = p.split("@")[0].capitalize()
                    participant_display.append(name)
            if len(original_participants) > 3:
                participant_display.append(f"and {len(original_participants) - 3} more")
            if participant_display:
                lines.append(f"**Participants:** {', '.join(participant_display)}")
        
        # Add note about external participants if present
        if external_participants:
            external_names = []
            for ext_p in external_participants:
                if "@" in ext_p:
                    name = ext_p.split("@")[0].capitalize()
                    external_names.append(name)
            if external_names:
                if len(external_names) == 1:
                    lines.append(f"*Note: This meeting includes external participant {external_names[0]}. The suggested times below are when all internal participants could attend an alternate meeting.*")
                else:
                    names_str = ", ".join(external_names[:-1]) + f" and {external_names[-1]}"
                    lines.append(f"*Note: This meeting includes external participants ({names_str}). The suggested times below are when all internal participants could attend an alternate meeting.*")
        
        lines.append("")
        lines.append("Here are alternative time options:")
        lines.append("")
    
    # Section 1: Best Options (zero-conflict)
    if free_proposals:
        lines.append("## Best Options")
        lines.append("")
        
        # Group by day
        proposals_by_day: Dict[str, List[Proposal]] = {}
        for prop in free_proposals:
            day_key = format_day_header(prop.start_utc, timezone_str)
            if day_key not in proposals_by_day:
                proposals_by_day[day_key] = []
            proposals_by_day[day_key].append(prop)
        
        # Sort days chronologically
        sorted_days = sorted(proposals_by_day.keys(), key=lambda d: _get_day_sort_key(d, proposals_by_day[d][0].start_utc))
        
        for day_key in sorted_days:
            day_proposals = proposals_by_day[day_key]
            lines.append(day_key)
            for prop in day_proposals:
                time_range = format_time_range(prop.start_utc, prop.end_utc, timezone_str)
                lines.append(f"* {time_range}")
            lines.append("")
    
    # Section 2: If We Can Move or Override Current Meetings
    if move_proposals or override_proposals:
        lines.append("## If We Can Move or Override Current Meetings")
        lines.append("")
        
        # Subsection 2a: Override Options
        if override_proposals:
            # Group override proposals by the requester's (user_id's) overridden event, then by proposal day
            # Structure: (requester_event_key) -> {proposal_day: [proposals]}
            # If no requester event, use a fallback key
            override_groups: Dict[Optional[Tuple[str, str]], Dict[str, List[Proposal]]] = {}
            
            for prop in override_proposals:
                # Find all overlapping solo events for this proposal
                overlapping_events = _find_all_overlapping_solo_events(prop, normalized_data, event_registry, timezone_str)
                
                # Find the requester's (user_id's) event if it exists
                requester_event_key = None
                if user_id:
                    for owner, event_id, event_title, event_time_range in overlapping_events:
                        if owner == user_id:
                            requester_event_key = (owner, event_id)
                            break
                
                # If no requester event found, use None as the key (will be grouped separately)
                if requester_event_key not in override_groups:
                    override_groups[requester_event_key] = {}
                
                # Group by proposal day
                proposal_day = format_day_header(prop.start_utc, timezone_str)
                if proposal_day not in override_groups[requester_event_key]:
                    override_groups[requester_event_key][proposal_day] = []
                override_groups[requester_event_key][proposal_day].append(prop)
            
            # Format override section - group by requester's event
            # Sort groups: requester events first (by event), then fallback groups
            sorted_group_keys = sorted(
                override_groups.keys(),
                key=lambda k: (
                    k is None,  # None (no requester event) goes last
                    k[0] if k else "",  # Then by owner
                    k[1] if k else ""   # Then by event_id
                )
            )
            
            for requester_event_key in sorted_group_keys:
                day_groups = override_groups[requester_event_key]
                sorted_days = sorted(day_groups.keys(), key=lambda d: _get_day_sort_key(d, day_groups[d][0].start_utc))
                
                for proposal_day in sorted_days:
                    day_props = day_groups[proposal_day]
                    
                    # Collect all unique solo events that are overridden by any proposal in this group
                    all_overridden_events: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {}
                    
                    for prop in day_props:
                        overlapping_events = _find_all_overlapping_solo_events(prop, normalized_data, event_registry, timezone_str)
                        for owner, event_id, event_title, event_time_range in overlapping_events:
                            key = (owner, event_id)
                            if key not in all_overridden_events:
                                all_overridden_events[key] = (owner, event_id, event_title, event_time_range)
                    
                    # Format the header
                    if all_overridden_events:
                        # Separate requester's events from other participants' events
                        requester_events = []
                        other_events = []
                        
                        for owner, event_id, event_title, event_time_range in all_overridden_events.values():
                            if user_id and owner == user_id:
                                requester_events.append((owner, event_id, event_title, event_time_range))
                            else:
                                other_events.append((owner, event_id, event_title, event_time_range))
                        
                        # Build the override description
                        if requester_events:
                            # Primary: requester's event(s)
                            requester_descriptions = []
                            for owner, event_id, event_title, event_time_range in requester_events:
                                if event_title and event_title != "solo/blocking events" and len(event_title) > 0:
                                    requester_descriptions.append(f"{event_time_range} \"{event_title}\" event")
                                else:
                                    requester_descriptions.append(f"{event_time_range} solo/blocking event")
                            
                            primary_text = "your " + requester_descriptions[0]  # Use first requester event
                            
                            # Secondary: other participants' events as annotation
                            if other_events:
                                other_descriptions = []
                                for owner, event_id, event_title, event_time_range in other_events:
                                    owner_name = owner.split("@")[0]
                                    if event_title and event_title != "solo/blocking events" and len(event_title) > 0:
                                        other_descriptions.append(f"{owner_name}'s {event_time_range} \"{event_title}\" event")
                                    else:
                                        other_descriptions.append(f"{owner_name}'s {event_time_range} solo/blocking event")
                                
                                # Join other events with ", " and "and" for the last one
                                if len(other_descriptions) == 1:
                                    annotation_text = other_descriptions[0]
                                elif len(other_descriptions) == 2:
                                    annotation_text = f"{other_descriptions[0]} and {other_descriptions[1]}"
                                else:
                                    annotation_text = ", ".join(other_descriptions[:-1]) + f", and {other_descriptions[-1]}"
                                
                                lines.append(f"{proposal_day}  — Overrides {primary_text} (and {annotation_text})")
                            else:
                                lines.append(f"{proposal_day}  — Overrides {primary_text}")
                        else:
                            # No requester event, fall back to listing all events
                            override_descriptions = []
                            for owner, event_id, event_title, event_time_range in sorted(all_overridden_events.values(), key=lambda x: x[0].lower()):
                                owner_name = owner.split("@")[0] if owner != user_id else "your"
                                if event_title and event_title != "solo/blocking events" and len(event_title) > 0:
                                    override_descriptions.append(f"{owner_name}'s {event_time_range} \"{event_title}\" event")
                                else:
                                    override_descriptions.append(f"{owner_name}'s {event_time_range} solo/blocking event")
                            
                            if len(override_descriptions) == 1:
                                override_text = override_descriptions[0]
                            elif len(override_descriptions) == 2:
                                override_text = f"{override_descriptions[0]} and {override_descriptions[1]}"
                            else:
                                override_text = ", ".join(override_descriptions[:-1]) + f", and {override_descriptions[-1]}"
                            
                            lines.append(f"{proposal_day}  — Overrides {override_text}")
                    else:
                        # Fallback: no solo events found, use generic description
                        lines.append(f"{proposal_day}  — Overrides solo/blocking events")
                    
                    # List proposal times
                    for prop in day_props:
                        time_range = format_time_range(prop.start_utc, prop.end_utc, timezone_str)
                        lines.append(f"* {time_range}")
                    lines.append("")
        
        # Subsection 2b: Move Options
        if move_proposals:
            # Group move proposals by the moved event, then by new location, then by proposal day
            # Structure: (owner, event_id) -> {new_location: {proposal_day: [proposals]}}
            move_groups: Dict[Tuple[str, str], Dict[Tuple[str, str], Dict[str, List[Proposal]]]] = {}
            
            for prop in move_proposals:
                if prop.moved_events:
                    moved = prop.moved_events[0]
                    key = (moved.owner, moved.event_id)
                    
                    if key not in move_groups:
                        move_groups[key] = {}
                    
                    # Group by new location
                    new_date = format_day_header(moved.new_start, timezone_str)
                    new_time = format_time_range(moved.new_start, moved.new_end, timezone_str)
                    location_key = (new_date, new_time)
                    
                    if location_key not in move_groups[key]:
                        move_groups[key][location_key] = {}
                    
                    # Group by proposal day
                    proposal_day = format_day_header(prop.start_utc, timezone_str)
                    if proposal_day not in move_groups[key][location_key]:
                        move_groups[key][location_key][proposal_day] = []
                    move_groups[key][location_key][proposal_day].append(prop)
            
            # Format each move group
            for (owner, event_id), location_groups in move_groups.items():
                # Get event metadata
                event_meta = event_registry.get(event_id, None)
                if event_meta:
                    event_title = event_meta.title
                else:
                    # Fallback: try to get from normalized_data
                    if normalized_data:
                        event_metadata = normalized_data.get("event_metadata", {})
                        event_key = (owner, event_id)
                        meta = event_metadata.get(event_key, {})
                        event_title = meta.get("title", event_id[:40])
                    else:
                        event_title = event_id[:40]
                
                # Get the original event time from the first proposal
                first_prop = None
                for location_props in location_groups.values():
                    for day_props in location_props.values():
                        if day_props:
                            first_prop = day_props[0]
                            break
                    if first_prop:
                        break
                
                if first_prop and first_prop.moved_events:
                    moved_event = first_prop.moved_events[0]
                    old_time_range = format_time_range(moved_event.old_start, moved_event.old_end, timezone_str)
                    
                    # Get owner's name (trim domain)
                    if owner == user_id:
                        owner_display = "your"
                    else:
                        # Remove @domain.com from email
                        owner_name = owner.split("@")[0]
                        owner_display = f"{owner_name}'s"
                    
                    # Format each location
                    sorted_locations = sorted(location_groups.items(), key=lambda x: _get_day_sort_key(x[0][0], first_prop.moved_events[0].new_start if first_prop.moved_events else ""))
                    
                    for (new_date, new_time), day_groups in sorted_locations:
                        # Format each proposal day
                        sorted_days = sorted(day_groups.keys(), key=lambda d: _get_day_sort_key(d, day_groups[d][0].start_utc))
                        
                        for proposal_day in sorted_days:
                            day_props = day_groups[proposal_day]
                            
                            # Format: "Day – If owner's time_range "title" event moves to new_time"
                            # Check if new location is on a different day
                            if new_date != proposal_day:
                                # Show full date for new location
                                lines.append(f"{proposal_day} – If {owner_display} {old_time_range} \"{event_title}\" event moves to {new_date} at {new_time}")
                            else:
                                # Same day, just show time
                                lines.append(f"{proposal_day} – If {owner_display} {old_time_range} \"{event_title}\" event moves to {new_time}")
                            
                            # List proposal times
                            for prop in day_props:
                                time_range = format_time_range(prop.start_utc, prop.end_utc, timezone_str)
                                lines.append(f"* {time_range}")
                            lines.append("")
    
    return "\n".join(lines)


def _get_day_sort_key(day_str: str, fallback_dt_str: str) -> float:
    """Get a sort key for a day string (for chronological sorting)."""
    try:
        dt = datetime.fromisoformat(fallback_dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.timestamp()
    except Exception:
        # Fallback: use string comparison
        return hash(day_str)


def _find_overridden_solo_event(
    proposal: Proposal,
    normalized_data: Optional[Dict[str, Any]],
    event_registry: Dict[str, EventMetadata],
    timezone_str: str = "America/New_York"
) -> Optional[Tuple[str, str, str, str]]:
    """
    Find the solo event being overridden by this proposal.
    
    Returns:
        Tuple of (owner, event_id, event_title, event_time_range) or None
    """
    if not normalized_data:
        return None
    
    try:
        # Convert proposal time to slots
        try:
            from .slot_indexer import SlotIndexer
        except (ImportError, ValueError):
            try:
                from scheduling_orchestrator.slot_indexer import SlotIndexer
            except ImportError:
                from slot_indexer import SlotIndexer
        
        slot_indexer = normalized_data.get("slot_indexer")
        if not slot_indexer:
            return None
        
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        
        start_slot = slot_indexer.datetime_to_slot(start_dt)
        end_slot = slot_indexer.datetime_to_slot(end_dt)
        
        if start_slot is None or end_slot is None:
            return None
        
        proposal_slots = set(range(start_slot, end_slot))
        
        # Check event_slots_map for overlapping solo events
        event_slots_map = normalized_data.get("event_slots_map", {})
        event_metadata = normalized_data.get("event_metadata", {})
        
        # Collect all overlapping solo events and pick the one with most overlap
        overlapping_solo_events = []
        
        for (owner, event_id), event_slots in event_slots_map.items():
            overlap = proposal_slots.intersection(event_slots)
            if overlap:
                # Check if this is a solo event (num_attendees == 0)
                event_meta = event_metadata.get((owner, event_id), {})
                num_attendees = event_meta.get("number_of_attendees", -1)
                
                if num_attendees == 0:
                    overlapping_solo_events.append((owner, event_id, event_meta, len(overlap)))
        
        # If we found solo events, pick the one with the most overlap
        if overlapping_solo_events:
            # Sort by overlap size (descending) and take the first
            overlapping_solo_events.sort(key=lambda x: x[3], reverse=True)
            owner, event_id, event_meta, _ = overlapping_solo_events[0]
            
            # Get event title
            event_title = event_meta.get("title") or event_meta.get("summary") or ""
            if not event_title:
                event_title = event_id[:40]
            
            # Get event start/end from metadata (use start_str and end_str)
            event_start = event_meta.get("start_str")
            event_end = event_meta.get("end_str")
            
            # If start_str/end_str not available, try start_dt/end_dt and convert
            if not event_start or not event_end:
                start_dt = event_meta.get("start_dt")
                end_dt = event_meta.get("end_dt")
                if start_dt and end_dt:
                    # Convert datetime objects to ISO strings
                    if isinstance(start_dt, datetime):
                        event_start = start_dt.isoformat()
                    else:
                        event_start = str(start_dt)
                    if isinstance(end_dt, datetime):
                        event_end = end_dt.isoformat()
                    else:
                        event_end = str(end_dt)
            
            if event_start and event_end:
                # event_start and event_end are ISO strings
                event_time_range = format_time_range(event_start, event_end, timezone_str)
            else:
                # Fallback: try to get from event_registry
                event_reg_meta = event_registry.get(event_id)
                if event_reg_meta and event_reg_meta.start_utc and event_reg_meta.end_utc:
                    event_time_range = format_time_range(event_reg_meta.start_utc, event_reg_meta.end_utc, timezone_str)
                else:
                    # Last resort: use proposal time as approximation (but this shouldn't happen)
                    import sys
                    print(f"[formatting] WARNING: Could not find event time for {event_id}, using proposal time", file=sys.stderr, flush=True)
                    print(f"[formatting] DEBUG: event_meta keys: {list(event_meta.keys())}", file=sys.stderr, flush=True)
                    print(f"[formatting] DEBUG: event_meta: {event_meta}", file=sys.stderr, flush=True)
                    event_time_range = format_time_range(proposal.start_utc, proposal.end_utc, timezone_str)
            
            return (owner, event_id, event_title, event_time_range)
        
        return None
    except Exception as e:
        import sys
        print(f"[formatting] Error finding overridden solo event: {e}", file=sys.stderr, flush=True)
        return None


def _find_all_overlapping_solo_events(
    proposal: Proposal,
    normalized_data: Optional[Dict[str, Any]],
    event_registry: Dict[str, EventMetadata],
    timezone_str: str = "America/New_York"
) -> List[Tuple[str, str, str, str]]:
    """
    Find ALL solo events being overridden by this proposal.
    
    Returns:
        List of tuples: [(owner, event_id, event_title, event_time_range), ...]
    """
    results = []
    if not normalized_data:
        return results
    
    try:
        # Convert proposal time to slots
        try:
            from .slot_indexer import SlotIndexer
        except (ImportError, ValueError):
            try:
                from scheduling_orchestrator.slot_indexer import SlotIndexer
            except ImportError:
                from slot_indexer import SlotIndexer
        
        slot_indexer = normalized_data.get("slot_indexer")
        if not slot_indexer:
            return results
        
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        
        start_slot = slot_indexer.datetime_to_slot(start_dt)
        end_slot = slot_indexer.datetime_to_slot(end_dt)
        
        if start_slot is None or end_slot is None:
            return results
        
        proposal_slots = set(range(start_slot, end_slot))
        
        # Check event_slots_map for overlapping solo events
        event_slots_map = normalized_data.get("event_slots_map", {})
        event_metadata = normalized_data.get("event_metadata", {})
        
        # Collect all overlapping solo events
        for (owner, event_id), event_slots in event_slots_map.items():
            overlap = proposal_slots.intersection(event_slots)
            if overlap:
                # Check if this is a solo event (num_attendees == 0)
                event_meta = event_metadata.get((owner, event_id), {})
                num_attendees = event_meta.get("number_of_attendees", -1)
                
                if num_attendees == 0:
                    # Get event title
                    event_title = event_meta.get("title") or event_meta.get("summary") or ""
                    if not event_title:
                        event_title = event_id[:40]
                    
                    # Get event start/end from metadata
                    event_start = event_meta.get("start_str")
                    event_end = event_meta.get("end_str")
                    
                    # If start_str/end_str not available, try start_dt/end_dt
                    if not event_start or not event_end:
                        start_dt_meta = event_meta.get("start_dt")
                        end_dt_meta = event_meta.get("end_dt")
                        if start_dt_meta and end_dt_meta:
                            if isinstance(start_dt_meta, datetime):
                                event_start = start_dt_meta.isoformat()
                            else:
                                event_start = str(start_dt_meta)
                            if isinstance(end_dt_meta, datetime):
                                event_end = end_dt_meta.isoformat()
                            else:
                                event_end = str(end_dt_meta)
                    
                    if event_start and event_end:
                        event_time_range = format_time_range(event_start, event_end, timezone_str)
                    else:
                        # Fallback: try to get from event_registry
                        event_reg_meta = event_registry.get(event_id)
                        if event_reg_meta and event_reg_meta.start_utc and event_reg_meta.end_utc:
                            event_time_range = format_time_range(event_reg_meta.start_utc, event_reg_meta.end_utc, timezone_str)
                        else:
                            # Last resort: use proposal time
                            event_time_range = format_time_range(proposal.start_utc, proposal.end_utc, timezone_str)
                    
                    results.append((owner, event_id, event_title, event_time_range))
        
        return results
    except Exception as e:
        import sys
        print(f"[formatting] Error finding all overlapping solo events: {e}", file=sys.stderr, flush=True)
        return results

