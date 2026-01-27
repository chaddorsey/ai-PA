"""
Proposal formatter for converting orchestrator output to interactive proposals.

Parses the markdown-formatted scheduling orchestrator output and creates
InteractiveProposalSet for rendering in Slack.
"""
import re
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytz

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
    MovedEventInfo,
)


def parse_orchestrator_proposals(
    output: str,
    session_id: str,
    user_id: str,
    participants: List[str],
    meeting_context: Optional[MeetingContext] = None,
    timezone_str: str = "America/New_York",
) -> InteractiveProposalSet:
    """
    Parse orchestrator markdown output into InteractiveProposalSet.

    Args:
        output: Markdown output from scheduling orchestrator
        session_id: Session ID for tracking
        user_id: Slack user ID
        participants: List of participant email addresses
        meeting_context: Optional meeting context (title, description hints)
        timezone_str: Timezone for date parsing

    Returns:
        InteractiveProposalSet ready for rendering
    """
    clean_proposals: List[InteractiveProposal] = []
    conflict_proposals: List[InteractiveProposal] = []

    # Split into sections
    sections = re.split(r'^##\s+', output, flags=re.MULTILINE)

    proposal_index = 1
    current_year = datetime.now().year
    tz = pytz.timezone(timezone_str)

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split('\n')
        header = lines[0].strip()
        content = '\n'.join(lines[1:])

        is_conflict_section = "move" in header.lower() or "override" in header.lower()

        # Parse proposals from content
        current_day: Optional[Tuple[str, str, int]] = None
        current_conflict_info: Optional[str] = None

        for line in content.split('\n'):
            line = line.strip()

            if not line:
                continue

            # Check for day header (e.g., "Wednesday, Jan. 29")
            day_match = re.match(
                r'^(\w+),?\s+(\w+\.?)\s+(\d+)',
                line
            )
            if day_match:
                weekday, month, day = day_match.groups()
                current_day = (weekday, month, int(day))

                # Check for conflict info in the same line
                if '–' in line and is_conflict_section:
                    # Extract text after the date
                    parts = line.split('–', 1)
                    if len(parts) > 1:
                        current_conflict_info = parts[1].strip()
                else:
                    current_conflict_info = None
                continue

            # Check for time slot (e.g., "* 2:00 – 3:00")
            time_match = re.match(
                r'^\*?\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})',
                line
            )
            if time_match and current_day:
                start_time, end_time = time_match.groups()

                # Parse times
                weekday, month, day = current_day
                start_utc, end_utc = _parse_times_to_utc(
                    month, day, start_time, end_time,
                    current_year, tz
                )

                if start_utc and end_utc:
                    # Generate label
                    label = _format_short_label(weekday, start_time, end_time)

                    # Create proposal
                    proposal = InteractiveProposal(
                        id=f"prop_{uuid.uuid4().hex[:8]}",
                        index=proposal_index,
                        label=label,
                        start_utc=start_utc,
                        end_utc=end_utc,
                        participants=participants,
                        category="move" if is_conflict_section else "clean",
                        conflict_summary=current_conflict_info if is_conflict_section else None,
                    )

                    if is_conflict_section:
                        conflict_proposals.append(proposal)
                    else:
                        clean_proposals.append(proposal)

                    proposal_index += 1

    return InteractiveProposalSet(
        session_id=session_id,
        user_id=user_id,
        clean_proposals=clean_proposals,
        conflict_proposals=conflict_proposals,
        meeting_context=meeting_context or MeetingContext(),
        show_conflicts_expanded=len(clean_proposals) == 0,
    )


def _parse_times_to_utc(
    month: str,
    day: int,
    start_time: str,
    end_time: str,
    year: int,
    tz: "pytz.tzinfo.BaseTzInfo",
) -> Tuple[Optional[str], Optional[str]]:
    """Parse time strings to UTC ISO format."""
    try:
        # Map month abbreviations
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
            'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
            'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        }

        month_lower = month.lower().replace('.', '')
        month_num = month_map.get(month_lower[:3], 1)

        # Parse start time
        start_parts = start_time.split(':')
        start_hour = int(start_parts[0])
        start_minute = int(start_parts[1]) if len(start_parts) > 1 else 0

        # Parse end time
        end_parts = end_time.split(':')
        end_hour = int(end_parts[0])
        end_minute = int(end_parts[1]) if len(end_parts) > 1 else 0

        # Assume business hours (adjust PM if hour < 8)
        if start_hour < 8:
            start_hour += 12
        if end_hour < 8:
            end_hour += 12
        if end_hour < start_hour:
            end_hour += 12

        # Create datetime objects
        start_dt = tz.localize(datetime(year, month_num, day, start_hour, start_minute))
        end_dt = tz.localize(datetime(year, month_num, day, end_hour, end_minute))

        # Handle year rollover
        now = datetime.now(tz)
        if start_dt < now - timedelta(days=30):
            start_dt = start_dt.replace(year=year + 1)
            end_dt = end_dt.replace(year=year + 1)

        # Convert to UTC
        start_utc = start_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        return start_utc, end_utc

    except Exception:
        return None, None


def _format_short_label(weekday: str, start_time: str, end_time: str) -> str:
    """Format a short label like 'Wed 2-3pm'."""
    # Get abbreviated weekday
    weekday_abbrev = weekday[:3]

    # Format times
    start_hour = int(start_time.split(':')[0])
    end_hour = int(end_time.split(':')[0])

    # Assume business hours for AM/PM detection
    if start_hour < 8:
        start_hour += 12
    if end_hour < 8:
        end_hour += 12

    # Determine AM/PM
    start_period = "am" if start_hour < 12 else "pm"
    end_period = "am" if end_hour < 12 else "pm"

    # Convert to 12-hour
    display_start = start_hour if start_hour <= 12 else start_hour - 12
    display_end = end_hour if end_hour <= 12 else end_hour - 12

    # Omit period on start if same as end
    if start_period == end_period:
        return f"{weekday_abbrev} {display_start}-{display_end}{end_period}"
    else:
        return f"{weekday_abbrev} {display_start}{start_period}-{display_end}{end_period}"
