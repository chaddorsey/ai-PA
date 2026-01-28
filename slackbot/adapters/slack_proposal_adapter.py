"""
Slack Block Kit adapter for interactive proposals.

Converts platform-agnostic InteractiveProposalSet to Slack Block Kit JSON.

Layout:
- Image blocks for section headers (Best Options, Solo Overrides, Multi-Person)
- Header blocks for dates (largest text)
- Context blocks for annotations (below date, above buttons)
- Actions blocks for buttons
- Dividers before conflict subsections
"""
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
)

# Intro text shown before all options
INTRO_TEXT = (
    "Click options to schedule directly or use the button at bottom "
    "to make a shareable list."
)

# Button text
SHOW_BUTTON_TEXT = "See more / Make shareable list"
HIDE_BUTTON_TEXT = "Hide extra options"
MODAL_BUTTON_TEXT = "See more / Make shareable list"

# Context text for best options
BEST_OPTIONS_CONTEXT = "Currently open for all participants"

# Section header images (Slack workspace URLs)
IMAGE_BEST_OPTIONS = "https://concord-consortium.slack.com/files/U02V91KU8/F0AB6RSHYFM/best-options.png"
IMAGE_SOLO_OVERRIDES = "https://concord-consortium.slack.com/files/U02V91KU8/F0ABGR8L36Y/solo-overrides.png"
IMAGE_MULTI_PERSON = "https://concord-consortium.slack.com/files/U02V91KU8/F0AAXPUM1JT/multi-person-overrides.png"


def render_proposal_blocks(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """Render an InteractiveProposalSet as Slack Block Kit blocks."""
    blocks: List[Dict[str, Any]] = []
    tz = pytz.timezone("America/New_York")

    # Section 1: Clean proposals ("Best Options")
    if proposal_set.clean_proposals:
        # Divider before section
        blocks.append({"type": "divider"})

        # Header for Best Options
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "Best Options - Click to Schedule", "emoji": True},
        })

        # Context explaining these are open slots
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "_Options currently open for all participants_",
            }],
        })

        # Divider after context
        blocks.append({"type": "divider"})

        blocks.extend(_render_clean_proposals(
            proposal_set.clean_proposals,
            proposal_set.session_id,
            tz,
        ))

    # Section 2: Button to open modal with all options (overrides, moves, share list)
    if proposal_set.conflict_proposals:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": SHOW_BUTTON_TEXT,
                    "emoji": False,
                },
                "action_id": "open_options_modal",
                "value": proposal_set.session_id,
            }],
        })

    return blocks


def _render_clean_proposals(
    proposals: List[InteractiveProposal],
    session_id: str,
    tz: "pytz.BaseTzInfo",
) -> List[Dict[str, Any]]:
    """Render clean proposals with header dates and buttons."""
    blocks: List[Dict[str, Any]] = []
    day_groups = _group_proposals_by_day(proposals, tz)

    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        day_header = _format_day_header(day_proposals[0], tz)

        # Date as header block (largest text)
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": day_header,
                "emoji": False,
            },
        })

        # Buttons
        buttons = _create_time_buttons(day_proposals, session_id, style="primary")
        for i in range(0, len(buttons), 5):
            blocks.append({
                "type": "actions",
                "elements": buttons[i:i+5],
            })

    return blocks


def _render_expanded_conflict_section(
    proposal_set: InteractiveProposalSet,
    tz: "pytz.BaseTzInfo",
) -> List[Dict[str, Any]]:
    """Render expanded conflict proposals with image headers and annotations."""
    blocks: List[Dict[str, Any]] = []

    solo_proposals = proposal_set.get_solo_overlap_proposals()
    multi_proposals = proposal_set.get_multi_person_proposals()

    # Hide button first (above dividers)
    if proposal_set.clean_proposals:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": HIDE_BUTTON_TEXT,
                    "emoji": False,
                },
                "action_id": "schedule_proposal_collapse",
                "value": proposal_set.session_id,
            }],
        })

    # Solo-Meeting Override Options
    if solo_proposals:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "image",
            "slack_file": {"url": IMAGE_SOLO_OVERRIDES},
            "alt_text": "Solo-Meeting Override Options",
        })
        blocks.extend(_render_conflict_proposals(
            solo_proposals,
            proposal_set.session_id,
            tz,
        ))

    # Multi-Person Moves and Overrides
    if multi_proposals:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "image",
            "slack_file": {"url": IMAGE_MULTI_PERSON},
            "alt_text": "Multi-Person Moves and Overrides",
        })
        blocks.extend(_render_conflict_proposals(
            multi_proposals,
            proposal_set.session_id,
            tz,
        ))

    return blocks


def _render_conflict_proposals(
    proposals: List[InteractiveProposal],
    session_id: str,
    tz: "pytz.BaseTzInfo",
) -> List[Dict[str, Any]]:
    """
    Render conflict proposals with header dates, annotations, and buttons.

    Layout:
    Thursday, Jan. 29                    [header]
    If _Event Title_ can move            [context - ABOVE buttons]
    [buttons]                            [actions]
    """
    blocks: List[Dict[str, Any]] = []
    day_groups = _group_proposals_by_day(proposals, tz)

    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        day_header = _format_day_header(day_proposals[0], tz)

        # Group by conflict summary
        conflict_groups: Dict[Optional[str], List[InteractiveProposal]] = defaultdict(list)
        for prop in day_proposals:
            normalized = _normalize_conflict_summary(prop.conflict_summary)
            conflict_groups[normalized].append(prop)

        # Date header (largest text)
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": day_header,
                "emoji": False,
            },
        })

        # Each conflict group: annotation then buttons
        for conflict_summary, group_proposals in conflict_groups.items():
            # Annotation as context ABOVE buttons
            if conflict_summary:
                annotation_text = _format_annotation(conflict_summary)
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": annotation_text,
                    }],
                })

            # Buttons
            buttons = _create_time_buttons(group_proposals, session_id)
            for i in range(0, len(buttons), 5):
                blocks.append({
                    "type": "actions",
                    "elements": buttons[i:i+5],
                })

    return blocks


def _format_annotation(conflict_summary: str) -> str:
    """
    Format annotation with event title in italics.

    "If Event Title can move" -> "If _Event Title_ can move"
    """
    # Pattern: "If [event info] can move"
    match = re.match(r"^If\s+(.+?)\s+can move$", conflict_summary, re.IGNORECASE)
    if match:
        event_info = match.group(1)
        return f"If _{event_info}_ can move"

    # Fallback: italicize any quoted content
    result = re.sub(r"'([^']+)'", r"_\1_", conflict_summary)
    result = re.sub(r'"([^"]+)"', r"_\1_", result)
    return result


def _normalize_conflict_summary(summary: Optional[str]) -> Optional[str]:
    """
    Normalize conflict summary to consistent format.

    "moves 'Standup' to 3pm" -> "If Standup can move"
    """
    if not summary:
        return None

    # Remove "moves to [time]" patterns
    normalized = re.sub(
        r'\s+moves?\s+to\s+[\d:]+\s*[–-]?\s*[\d:]*\s*(am|pm|AM|PM)?',
        '',
        summary,
        flags=re.IGNORECASE
    )

    # Convert "moves 'Event'" to "If Event can move"
    if normalized.lower().startswith('move'):
        match = re.match(r"moves?\s+['\"]?([^'\"]+)['\"]?", normalized, re.IGNORECASE)
        if match:
            event_name = match.group(1).strip()
            return f"If {event_name} can move"

    # Ensure "If ..." ends with "can move"
    if normalized.lower().startswith('if '):
        normalized = re.sub(r'\s+moves?\s*$', '', normalized, flags=re.IGNORECASE)
        if not normalized.lower().endswith('can move'):
            normalized = normalized + " can move"
        return normalized

    return f"If {normalized} can move"


def _group_proposals_by_day(
    proposals: List[InteractiveProposal],
    tz: "pytz.BaseTzInfo",
) -> Dict[str, List[InteractiveProposal]]:
    """Group proposals by date (YYYY-MM-DD)."""
    groups: Dict[str, List[InteractiveProposal]] = defaultdict(list)

    for prop in proposals:
        try:
            start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
            local_dt = start_dt.astimezone(tz)
            day_key = local_dt.strftime("%Y-%m-%d")
            groups[day_key].append(prop)
        except Exception:
            groups["unknown"].append(prop)

    return groups


def _format_day_header(proposal: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format day header like 'Thursday, Jan. 29'."""
    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        local_dt = start_dt.astimezone(tz)
        return local_dt.strftime("%A, %b. %d").replace(" 0", " ")
    except Exception:
        return "Available times"


def _format_time_range(proposal: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format time range like '3:00-3:45'."""
    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))

        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)

        start_str = start_local.strftime("%I:%M").lstrip("0")
        end_str = end_local.strftime("%I:%M").lstrip("0")

        return f"{start_str}-{end_str}"
    except Exception:
        return proposal.label


def _create_time_buttons(
    proposals: List[InteractiveProposal],
    session_id: str,
    style: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Create button elements with time-only labels."""
    buttons = []
    tz = pytz.timezone("America/New_York")

    for prop in proposals:
        time_label = _format_time_range(prop, tz)

        button: Dict[str, Any] = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": time_label,
                "emoji": False,
            },
            "action_id": f"schedule_proposal_select_{prop.id}",
            "value": f"{session_id}:{prop.id}",
        }

        if style:
            button["style"] = style

        buttons.append(button)

    return buttons


def render_confirmation_modal(
    proposal: InteractiveProposal,
    context: MeetingContext,
    session_id: str,
) -> Dict[str, Any]:
    """Render confirmation modal with pre-filled meeting details."""
    participant_names = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_names.append(name)
        else:
            participant_names.append(email.split("@")[0].capitalize())

    participants_text = ", ".join(participant_names) if participant_names else "No participants"

    tz = pytz.timezone("America/New_York")

    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))

        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)

        date_str = start_local.strftime("%A, %b %d")
        start_time = start_local.strftime("%I:%M").lstrip("0")
        end_time = end_local.strftime("%I:%M %p %Z").lstrip("0")
        when_text = f"{date_str} · {start_time} - {end_time}"
    except Exception:
        when_text = f"{proposal.start_utc} - {proposal.end_utc}"

    title = proposal.suggested_title or context.inferred_title or ""
    title_placeholder = f"Meeting with {participant_names[0]}..." if participant_names else "Meeting title"

    blocks: List[Dict[str, Any]] = [
        {
            "type": "input",
            "block_id": "title_block",
            "label": {"type": "plain_text", "text": "Title"},
            "element": {
                "type": "plain_text_input",
                "action_id": "meeting_title",
                "initial_value": title,
                "placeholder": {"type": "plain_text", "text": title_placeholder},
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*When:* {when_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*With:* {participants_text}",
            },
        },
        {
            "type": "input",
            "block_id": "description_block",
            "optional": True,
            "label": {"type": "plain_text", "text": "Description"},
            "element": {
                "type": "plain_text_input",
                "action_id": "meeting_description",
                "multiline": True,
                "initial_value": context.inferred_description or "",
            },
        },
    ]

    if proposal.conflict_summary:
        blocks.insert(0, {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Note:* This option {proposal.conflict_summary}",
            },
        })

    return {
        "type": "modal",
        "callback_id": "schedule_proposal_confirm",
        "private_metadata": f"{session_id}:{proposal.id}",
        "title": {"type": "plain_text", "text": "Schedule Meeting"},
        "submit": {"type": "plain_text", "text": "Schedule"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def render_expanded_conflicts(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """Render conflict proposals section after user clicks expand."""
    if not proposal_set.conflict_proposals:
        return []

    tz = pytz.timezone("America/New_York")
    return _render_expanded_conflict_section(proposal_set, tz)
