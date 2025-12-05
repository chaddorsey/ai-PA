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

