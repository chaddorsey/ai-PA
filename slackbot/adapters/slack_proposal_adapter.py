"""
Slack Block Kit adapter for interactive proposals.

Converts platform-agnostic InteractiveProposalSet to Slack Block Kit JSON.
"""
from typing import Any, Dict, List

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
)


def render_proposal_blocks(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """
    Render an InteractiveProposalSet as Slack Block Kit blocks.

    Returns a list of blocks suitable for chat.postMessage or views.publish.
    """
    blocks: List[Dict[str, Any]] = []

    # Section 1: Clean proposals (Best Options)
    if proposal_set.clean_proposals:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📅 *Best Options*",
            },
        })

        # Create buttons for clean proposals (max 5 per actions block)
        clean_buttons = _create_proposal_buttons(
            proposal_set.clean_proposals,
            proposal_set.session_id,
        )

        # Slack limits actions blocks to 25 elements, but 5 buttons per row is cleaner
        for i in range(0, len(clean_buttons), 5):
            blocks.append({
                "type": "actions",
                "elements": clean_buttons[i:i+5],
            })

    # Section 2: Conflict proposals
    if proposal_set.conflict_proposals:
        # If we have clean options, add expand button first
        if proposal_set.clean_proposals and not proposal_set.show_conflicts_expanded:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "▸ Show more options (requires changes)...",
                    },
                    "action_id": "schedule_proposal_expand",
                    "value": proposal_set.session_id,
                }],
            })
        else:
            # Show conflict section directly
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Options that require changes*",
                },
            })

            conflict_buttons = _create_proposal_buttons(
                proposal_set.conflict_proposals,
                proposal_set.session_id,
                include_conflict_indicator=True,
            )

            for i in range(0, len(conflict_buttons), 5):
                blocks.append({
                    "type": "actions",
                    "elements": conflict_buttons[i:i+5],
                })

    return blocks


def _create_proposal_buttons(
    proposals: List[InteractiveProposal],
    session_id: str,
    include_conflict_indicator: bool = False,
) -> List[Dict[str, Any]]:
    """Create button elements for proposals."""
    buttons = []

    for prop in proposals:
        label = prop.label
        if include_conflict_indicator and prop.conflict_summary:
            label = f"{label} ⚡"

        buttons.append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": f"{prop.index} {label}",
                "emoji": True,
            },
            "action_id": "schedule_proposal_select",
            "value": f"{session_id}:{prop.id}",
        })

    return buttons


def render_confirmation_modal(
    proposal: InteractiveProposal,
    context: MeetingContext,
    session_id: str,
) -> Dict[str, Any]:
    """
    Render confirmation modal with pre-filled meeting details.

    Returns Slack modal view object.
    """
    # Format participants list
    participant_names = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_names.append(name)
        else:
            # Extract name from email
            participant_names.append(email.split("@")[0].capitalize())

    participants_text = ", ".join(participant_names) if participant_names else "No participants"

    # Format date/time for display
    from datetime import datetime
    import pytz

    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))

        tz = pytz.timezone("America/New_York")
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)

        # Format: "Tuesday, Jan 28 · 2:00 - 3:00 PM EST"
        date_str = start_local.strftime("%A, %b %d")
        start_time = start_local.strftime("%I:%M").lstrip("0")
        end_time = end_local.strftime("%I:%M %p %Z").lstrip("0")
        when_text = f"{date_str} · {start_time} - {end_time}"
    except Exception:
        when_text = f"{proposal.start_utc} - {proposal.end_utc}"

    # Determine title (from proposal or context)
    title = proposal.suggested_title or context.inferred_title or ""
    title_placeholder = f"Meeting with {participant_names[0]}..." if participant_names else "Meeting title"

    # Build modal blocks
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

    # Add conflict warning if applicable
    if proposal.conflict_summary:
        blocks.insert(0, {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Note:* This option {proposal.conflict_summary}",
            },
        })

    return {
        "type": "modal",
        "callback_id": "schedule_proposal_confirm",
        "private_metadata": f"{session_id}:{proposal.id}",
        "title": {"type": "plain_text", "text": "Schedule Meeting"},
        "submit": {"type": "plain_text", "text": "Yes — schedule it!"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def render_expanded_conflicts(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """
    Render conflict proposals section after user clicks expand.

    Returns blocks to append to existing message.
    """
    if not proposal_set.conflict_proposals:
        return []

    blocks: List[Dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚠️ *Options that require changes*",
            },
        },
    ]

    conflict_buttons = _create_proposal_buttons(
        proposal_set.conflict_proposals,
        proposal_set.session_id,
        include_conflict_indicator=True,
    )

    for i in range(0, len(conflict_buttons), 5):
        blocks.append({
            "type": "actions",
            "elements": conflict_buttons[i:i+5],
        })

    return blocks
