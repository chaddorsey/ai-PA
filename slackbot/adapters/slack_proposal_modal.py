"""
Slack modal for viewing all scheduling options and building share lists.

View stack design:
1. Schedule View (default) - All options with time buttons
2. Build List View - Checkboxes to select times (swapped via views.update)
3. Confirm Meeting View - Pre-filled meeting details (pushed via views.push)

Tab switching between Schedule/Build List uses views.update (same stack level).
Confirmation modal uses views.push (new stack level, returns on close).

Build List uses pagination by category:
- Page 1: ✨ Best Options (clean slots)
- Page 2: ⚡👥 Override/Move Options (conflicts)
"""
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
)


# View identifiers (stored in private_metadata)
VIEW_SCHEDULE = "schedule"
VIEW_BUILD_LIST = "build_list"

# Pagination constants
PAGE_BEST_OPTIONS = 1
PAGE_OVERRIDE_OPTIONS = 2
PAGE_LABELS = {
    PAGE_BEST_OPTIONS: "✨ Best Options",
    PAGE_OVERRIDE_OPTIONS: "⚡👥 Overrides & Moves",
}


def render_schedule_view(
    proposal_set: InteractiveProposalSet,
) -> Dict[str, Any]:
    """
    Render the Schedule view with all options and time buttons.

    This is the default/initial view when modal opens.
    """
    blocks: List[Dict[str, Any]] = []
    tz = pytz.timezone("America/New_York")

    # Tab buttons at top
    blocks.append({
        "type": "actions",
        "block_id": "view_tabs",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Schedule a Meeting", "emoji": True},
                "action_id": "modal_tab_schedule",
                "value": proposal_set.session_id,
                "style": "primary",  # Highlighted as active
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Build Shareable List", "emoji": True},
                "action_id": "modal_tab_build_list",
                "value": proposal_set.session_id,
            },
        ],
    })

    blocks.append({"type": "divider"})

    # Best Options section
    if proposal_set.clean_proposals:
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "✨ Best Options", "emoji": True},
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_Options currently open for all participants_"}],
        })
        blocks.extend(_render_proposals_with_buttons(
            proposal_set.clean_proposals,
            proposal_set.session_id,
            tz,
            include_annotation=False,
            primary_buttons=False,  # All buttons default style
        ))

    # Divider after Best Options
    has_conflict_sections = (
        proposal_set.get_single_solo_overlap_proposals() or
        proposal_set.get_multiple_solo_overlap_proposals() or
        proposal_set.get_multi_person_proposals()
    )
    if proposal_set.clean_proposals and has_conflict_sections:
        blocks.append({"type": "divider"})

    # Single Solo-Meeting Overrides section
    single_solo_proposals = proposal_set.get_single_solo_overlap_proposals()
    if single_solo_proposals:
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "⚡ Single Solo-Meeting Overrides", "emoji": True},
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_Options intersect with one single-person event_"}],
        })
        blocks.extend(_render_proposals_with_buttons(
            single_solo_proposals,
            proposal_set.session_id,
            tz,
            include_annotation=True,
        ))

    # Multiple Solo-Meeting Overrides section
    multiple_solo_proposals = proposal_set.get_multiple_solo_overlap_proposals()
    if multiple_solo_proposals:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "⚡⚡ Multiple Solo-Meeting Overrides", "emoji": True},
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_Options intersect with more than one single-person event_"}],
        })
        blocks.extend(_render_proposals_with_buttons(
            multiple_solo_proposals,
            proposal_set.session_id,
            tz,
            include_annotation=True,
        ))

    # Multi-Person Meeting Moves and Overrides section
    multi_proposals = proposal_set.get_multi_person_proposals()
    if multi_proposals:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "👥 Multi-Person Meeting Moves and Overrides", "emoji": True},
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_Options intersect with a moveable multi-person event or multiple single-person events_"}],
        })
        blocks.extend(_render_proposals_with_buttons(
            multi_proposals,
            proposal_set.session_id,
            tz,
            include_annotation=True,
        ))

    return {
        "type": "modal",
        "callback_id": "schedule_modal_view",
        "private_metadata": f"{VIEW_SCHEDULE}:{proposal_set.session_id}",
        "title": {"type": "plain_text", "text": "Schedule a Meeting"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


def render_build_list_view(
    proposal_set: InteractiveProposalSet,
    selected_ids: Optional[List[str]] = None,
    current_page: int = PAGE_BEST_OPTIONS,
    copy_feedback: bool = False,
    edit_mode: bool = False,
) -> Dict[str, Any]:
    """
    Render the Build List view with paginated checkboxes and preview at top.

    Layout:
    1. Tab buttons (Schedule / Build List)
    2. Preview section with Copy button (always visible at top)
    3. Pagination controls
    4. Checkboxes for current page's options

    Args:
        proposal_set: The proposals to display
        selected_ids: Currently selected proposal IDs (persisted across pages)
        current_page: Which page to show (PAGE_BEST_OPTIONS or PAGE_OVERRIDE_OPTIONS)
        copy_feedback: If True, show "Copied!" feedback on copy button
    """
    blocks: List[Dict[str, Any]] = []
    tz = pytz.timezone("America/New_York")
    selected_ids = selected_ids or []

    # Tab buttons at top
    blocks.append({
        "type": "actions",
        "block_id": "view_tabs",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Schedule a Meeting", "emoji": True},
                "action_id": "modal_tab_schedule",
                "value": proposal_set.session_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Build Shareable List", "emoji": True},
                "action_id": "modal_tab_build_list",
                "value": proposal_set.session_id,
                "style": "primary",
            },
        ],
    })

    blocks.append({"type": "divider"})

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 1: Preview at TOP (always visible)
    # ─────────────────────────────────────────────────────────────────────

    # Header row with copy button as accessory
    total_options = (
        len(proposal_set.clean_proposals) +
        len(proposal_set.get_solo_overlap_proposals()) +
        len(proposal_set.get_multi_person_proposals())
    )
    selection_count = len(selected_ids)

    # Header with Copy button as accessory
    copy_button_text = "Copied! ✓" if copy_feedback else "Copy"

    if edit_mode:
        # Edit mode: header with Done button
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Your List* ({selection_count} of {total_options} selected)",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Done", "emoji": True},
                "action_id": "build_list_edit_done",
                "value": proposal_set.session_id,
                "style": "primary",
            },
        })
    else:
        # Normal mode: header with Copy button
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Your List* ({selection_count} of {total_options} selected)",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": copy_button_text, "emoji": True},
                "action_id": "build_list_copy",
                "value": proposal_set.session_id,
                **({"style": "primary"} if copy_feedback else {}),
            },
        })

    # Show preview content
    if selected_ids:
        if edit_mode:
            # Edit mode: show checkboxes for removal
            preview_blocks = _render_preview_checkboxes(proposal_set, selected_ids, tz)
            blocks.extend(preview_blocks)
        else:
            # View mode: show compact text list with edit button on header line
            preview_text = _generate_share_list_text(proposal_set, selected_ids, tz)
            if preview_text:
                # Split to get header line and rest
                lines = preview_text.split("\n", 1)
                header_line = lines[0]  # "*Meeting Options (Eastern time)*"
                rest = lines[1] if len(lines) > 1 else ""

                # Header line with edit button as accessory
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": header_line},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✏️", "emoji": True},
                        "action_id": "build_list_edit_start",
                        "value": proposal_set.session_id,
                    },
                })
                # Rest of the list
                if rest.strip():
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": rest},
                    })
    else:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_Select options below to build your list_"}],
        })

    blocks.append({"type": "divider"})

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 2: Pagination controls
    # ─────────────────────────────────────────────────────────────────────

    # Count options per page for display
    best_count = len(proposal_set.clean_proposals)
    override_count = (
        len(proposal_set.get_solo_overlap_proposals()) +
        len(proposal_set.get_multi_person_proposals())
    )

    # Count selected per page
    best_ids = {p.id for p in proposal_set.clean_proposals}
    override_ids = {p.id for p in proposal_set.get_solo_overlap_proposals()} | \
                   {p.id for p in proposal_set.get_multi_person_proposals()}
    best_selected = len([sid for sid in selected_ids if sid in best_ids])
    override_selected = len([sid for sid in selected_ids if sid in override_ids])

    # Page buttons with selection indicators
    page_buttons = []

    # Best Options page button
    best_label = f"✨ Best Options"
    if best_selected > 0:
        best_label += f" ({best_selected})"
    page_buttons.append({
        "type": "button",
        "text": {"type": "plain_text", "text": best_label, "emoji": True},
        "action_id": "build_list_page_best",
        "value": proposal_set.session_id,
        **({"style": "primary"} if current_page == PAGE_BEST_OPTIONS else {}),
    })

    # Override Options page button (only if there are override options)
    if override_count > 0:
        override_label = f"⚡👥 Overrides"
        if override_selected > 0:
            override_label += f" ({override_selected})"
        page_buttons.append({
            "type": "button",
            "text": {"type": "plain_text", "text": override_label, "emoji": True},
            "action_id": "build_list_page_override",
            "value": proposal_set.session_id,
            **({"style": "primary"} if current_page == PAGE_OVERRIDE_OPTIONS else {}),
        })

    blocks.append({
        "type": "actions",
        "block_id": "page_selector",
        "elements": page_buttons,
    })

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 3: Section blocks with button accessories for current page
    # ─────────────────────────────────────────────────────────────────────

    # Get proposals for current page
    if current_page == PAGE_BEST_OPTIONS:
        page_proposals = proposal_set.clean_proposals
        page_header = "Open slots - no conflicts"
    else:
        page_proposals = (
            proposal_set.get_solo_overlap_proposals() +
            proposal_set.get_multi_person_proposals()
        )
        page_header = "Options that involve rescheduling"

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"_{page_header}_"}],
    })

    # Build section blocks with button accessories
    for prop in page_proposals:
        day_str = _format_day_short(prop, tz)
        time_str = _format_time_range(prop, tz)
        is_selected = prop.id in selected_ids

        # Build the section text with date (bold) and time (plain)
        title_line = f"*{day_str}* {time_str}"

        # Add context line based on conflict type (use normalized summary)
        normalized_summary = _normalize_conflict_summary(prop.conflict_summary) if prop.conflict_summary else None

        if prop.conflict_type in ("single_solo_overlap", "solo_overlap"):
            if normalized_summary:
                context_line = f"⚡ _{normalized_summary}_"
            else:
                context_line = "⚡ _Intersects with one solo-meeting_"
        elif prop.conflict_type == "multiple_solo_overlap":
            if normalized_summary:
                context_line = f"⚡⚡ _{normalized_summary}_"
            else:
                context_line = "⚡⚡ _Intersects with multiple solo-meetings_"
        elif prop.conflict_type == "multi_person":
            if normalized_summary:
                context_line = f"👥 _{normalized_summary}_"
            else:
                context_line = "👥 _Intersects with multi-person meeting_"
        else:
            # Clean/best option - no conflict context needed
            context_line = None

        # Combine into section text
        if context_line:
            section_text = f"{title_line}\n{context_line}"
        else:
            section_text = title_line

        # Button shows selection state (no primary style to avoid confusion with tabs)
        if is_selected:
            button_text = "Remove  ❌"
        else:
            button_text = "Add"

        button: Dict[str, Any] = {
            "type": "button",
            "text": {"type": "plain_text", "text": button_text, "emoji": True},
            "action_id": f"build_list_toggle_{prop.id}",
            "value": prop.id,
        }

        blocks.append({
            "type": "section",
            "block_id": f"option_{prop.id}",
            "text": {
                "type": "mrkdwn",
                "text": section_text,
            },
            "accessory": button,
        })

    # Handle empty page
    if not page_proposals:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "_No options available on this page_"}],
        })

    # Add All button at bottom of page, right-justified (if there are unselected items)
    page_ids = {p.id for p in page_proposals}
    unselected_on_page = page_ids - set(selected_ids)
    if unselected_on_page:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": " "},  # Minimal text for right-align
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Add All", "emoji": True},
                "action_id": "build_list_add_all",
                "value": proposal_set.session_id,
            },
        })

    # Encode state in private_metadata as JSON
    metadata = {
        "view": VIEW_BUILD_LIST,
        "session_id": proposal_set.session_id,
        "selected_ids": selected_ids,
        "current_page": current_page,
        "edit_mode": edit_mode,
    }

    return {
        "type": "modal",
        "callback_id": "build_list_modal_view",
        "private_metadata": json.dumps(metadata),
        "title": {"type": "plain_text", "text": "Build Shareable List"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


def _render_preview_checkboxes(
    proposal_set: InteractiveProposalSet,
    selected_ids: List[str],
    tz: "pytz.BaseTzInfo",
) -> List[Dict[str, Any]]:
    """
    Render selected items as checkboxes for removal.

    In edit mode, all selected items are shown as checked checkboxes.
    Unchecking removes them from the list.
    """
    blocks: List[Dict[str, Any]] = []

    # Collect selected proposals
    all_proposals = (
        proposal_set.clean_proposals +
        proposal_set.get_single_solo_overlap_proposals() +
        proposal_set.get_multiple_solo_overlap_proposals() +
        proposal_set.get_multi_person_proposals()
    )
    selected = [p for p in all_proposals if p.id in selected_ids]

    if not selected:
        return blocks

    # Sort by start time
    selected.sort(key=lambda p: p.start_utc)

    # Build checkbox options (max 10 per group)
    options = []
    for prop in selected:
        day_str = _format_day_short(prop, tz)
        time_str = _format_time_range(prop, tz)
        options.append({
            "text": {"type": "plain_text", "text": f"{day_str} {time_str}", "emoji": True},
            "value": prop.id,
        })

    # Split into groups of 10 (Slack limit)
    for i in range(0, len(options), 10):
        group_options = options[i:i+10]
        blocks.append({
            "type": "section",
            "block_id": f"preview_edit_{i}",
            "text": {"type": "mrkdwn", "text": "_Uncheck items to remove:_" if i == 0 else " "},
            "accessory": {
                "type": "checkboxes",
                "action_id": f"preview_edit_checkboxes_{i}",
                "options": group_options,
                "initial_options": group_options,  # All checked by default
            },
        })

    return blocks


def _generate_share_list_text(
    proposal_set: InteractiveProposalSet,
    selected_ids: List[str],
    tz: "pytz.BaseTzInfo",
) -> str:
    """
    Generate the shareable list text from selected proposals.

    Format:
    Meeting Options (Eastern time)

    Friday, February 27
    • 1:30-2:00
    • 2:00-2:30

    Monday, March 2
    • 10:00-10:30
    """
    if not selected_ids:
        return ""

    # Collect selected proposals from all categories
    all_proposals = (
        proposal_set.clean_proposals +
        proposal_set.get_solo_overlap_proposals() +
        proposal_set.get_multi_person_proposals()
    )
    selected_proposals = [p for p in all_proposals if p.id in selected_ids]

    if not selected_proposals:
        return ""

    # Sort by start time
    def sort_key(p: InteractiveProposal) -> str:
        return p.start_utc

    selected_proposals.sort(key=sort_key)

    # Group by day
    day_groups = _group_by_day(selected_proposals, tz)

    lines = ["*Meeting Options (Eastern time)*", ""]

    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        # Full day format: "Friday, February 27"
        day_str = _format_day_full(day_proposals[0], tz)
        lines.append(f"*{day_str}*")

        # Sort times within day
        day_proposals.sort(key=lambda p: p.start_utc)
        for prop in day_proposals:
            time_str = _format_time_range(prop, tz)
            lines.append(f"• {time_str}")

        lines.append("")  # Blank line between days

    return "\n".join(lines).strip()


def _format_day_full(prop: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format as 'Friday, February 27'."""
    try:
        start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
        local_dt = start_dt.astimezone(tz)
        return local_dt.strftime("%A, %B %d").replace(" 0", " ")
    except Exception:
        return "Unknown"


def render_share_list_result(
    selected_proposals: List[InteractiveProposal],
    session_id: str,
    tz_str: str = "America/New_York",
) -> Dict[str, Any]:
    """
    Render the generated shareable text list.

    Pushed via views.push after user submits Build List view.
    """
    tz = pytz.timezone(tz_str)

    if not selected_proposals:
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Share List"},
            "close": {"type": "plain_text", "text": "Back"},
            "private_metadata": f"result:{session_id}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No times selected. Go back and select some options.",
                },
            }],
        }

    # Group by day for nice formatting
    day_groups = _group_by_day(selected_proposals, tz)

    lines = ["*Available times:*", ""]
    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        day_str = _format_day(day_proposals[0], tz)
        times = [_format_time_range(p, tz) for p in day_proposals]
        lines.append(f"• *{day_str}:* {', '.join(times)}")

    # Note about conflicts if any
    has_conflicts = any(p.category != "clean" for p in selected_proposals)
    if has_conflicts:
        lines.append("")
        lines.append("_(Some options may require rescheduling)_")

    text_content = "\n".join(lines)

    # Plain text version for easy copying
    plain_lines = ["Available times:", ""]
    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        day_str = _format_day(day_proposals[0], tz)
        times = [_format_time_range(p, tz) for p in day_proposals]
        plain_lines.append(f"• {day_str}: {', '.join(times)}")
    if has_conflicts:
        plain_lines.append("")
        plain_lines.append("(Some options may require rescheduling)")
    plain_text = "\n".join(plain_lines)

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Share List"},
        "close": {"type": "plain_text", "text": "Done"},
        "private_metadata": f"result:{session_id}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Copy this text to share:\n\n" + text_content,
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": "💡 Select and copy the text above, or use the plain text below:",
                }],
            },
            {
                "type": "input",
                "block_id": "plain_text_copy",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "copy_text",
                    "multiline": True,
                    "initial_value": plain_text,
                },
                "label": {"type": "plain_text", "text": "Plain text (select all, copy)"},
            },
        ],
    }


def render_confirm_meeting_view(
    proposal: InteractiveProposal,
    context: MeetingContext,
    session_id: str,
) -> Dict[str, Any]:
    """
    Render confirmation modal for scheduling a meeting.

    Pushed via views.push when user clicks a time button.
    """
    tz = pytz.timezone("America/New_York")

    # Use actual email addresses for participants display (lowercase)
    participants_text = ", ".join([email.lower() for email in proposal.participants]) if proposal.participants else "No participants"

    # Keep participant names for title placeholder
    participant_names = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_names.append(name)
        else:
            participant_names.append(email.split("@")[0].capitalize())

    # Format time
    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)
        date_str = start_local.strftime("%A, %b %d")
        start_time = start_local.strftime("%I:%M").lstrip("0")
        end_time = end_local.strftime("%I:%M %p").lstrip("0")
        when_text = f"{date_str} · {start_time} - {end_time}"
    except Exception:
        when_text = f"{proposal.start_utc} - {proposal.end_utc}"

    title = proposal.suggested_title or context.inferred_title or ""
    title_placeholder = f"Meeting with {participant_names[0]}..." if participant_names else "Meeting title"

    blocks: List[Dict[str, Any]] = []

    # Conflict warning if applicable
    if proposal.conflict_summary:
        summary = proposal.conflict_summary

        # Check if this is a move scenario (starts with "If")
        if summary.lower().startswith("if "):
            # Clean up and convert names
            summary = summary.replace("*", "")
            summary = _convert_email_prefix_to_name(summary)
            # Move scenario: "If X can move" -> "is available if X can move"
            note_text = f"⚠️ *Note:* This option is available if {summary[3:]}"
        else:
            # Override scenario - use full normalization
            normalized = _normalize_conflict_summary(summary)
            if normalized and normalized.lower().startswith("intersects with"):
                note_text = f"⚠️ *Note:* This option {normalized.lower()}"
            else:
                note_text = f"⚠️ *Note:* This option intersects with {normalized or summary}"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": note_text,
            },
        })
        blocks.append({"type": "divider"})

    # Title input
    blocks.append({
        "type": "input",
        "block_id": "title_block",
        "label": {"type": "plain_text", "text": "Title"},
        "element": {
            "type": "plain_text_input",
            "action_id": "meeting_title",
            "initial_value": title,
            "placeholder": {"type": "plain_text", "text": title_placeholder},
        },
    })

    # When (display only)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*When:* {when_text}",
        },
    })

    # With (display only)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*With:* {participants_text}",
        },
    })

    # Description input
    blocks.append({
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
    })

    return {
        "type": "modal",
        "callback_id": "confirm_meeting_modal",
        "private_metadata": f"{session_id}:{proposal.id}",
        "title": {"type": "plain_text", "text": "Schedule a Meeting"},
        "submit": {"type": "plain_text", "text": "Schedule"},
        "close": {"type": "plain_text", "text": "Back"},
        "blocks": blocks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _render_proposals_with_buttons(
    proposals: List[InteractiveProposal],
    session_id: str,
    tz: "pytz.BaseTzInfo",
    include_annotation: bool = False,
    primary_buttons: bool = False,
) -> List[Dict[str, Any]]:
    """Render proposals grouped by day with time buttons."""
    blocks: List[Dict[str, Any]] = []
    day_groups = _group_by_day(proposals, tz)

    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        day_str = _format_day(day_proposals[0], tz)

        # Date as header block (prominent)
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": day_str, "emoji": False},
        })

        if include_annotation:
            # Group by normalized conflict summary (same event = same group)
            conflict_groups = _group_by_conflict(day_proposals)
            for conflict_summary, group in conflict_groups.items():
                # Annotation line (below date)
                if conflict_summary:
                    blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"_{conflict_summary}_"}],
                    })

                # Buttons for this conflict group
                buttons = _create_buttons(group, session_id, tz, primary=primary_buttons)
                for i in range(0, len(buttons), 5):
                    blocks.append({
                        "type": "actions",
                        "elements": buttons[i:i+5],
                    })
        else:
            # No annotations - just buttons under the date
            buttons = _create_buttons(day_proposals, session_id, tz, primary=primary_buttons)
            for i in range(0, len(buttons), 5):
                blocks.append({
                    "type": "actions",
                    "elements": buttons[i:i+5],
                })

    return blocks


def _group_by_day(
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


def _convert_email_prefix_to_name(text: str) -> str:
    """
    Convert email prefixes in text to proper first names.

    "cdorsey's 3:00 Hold event" -> "Chad's 3:00 Hold event"
    "rellis's Focus Time" -> "Ruth's Focus Time"

    Uses a known mapping for common users, falls back to capitalizing
    the first part of the email prefix for unknown users.
    """
    import re

    # Known email prefix to first name mappings
    # Format: email_prefix (lowercase) -> First Name
    name_map = {
        "cdorsey": "Chad",
        "rellis": "Ruth",
        "clore": "Cynthia",
        "pkremer": "Paul",
        "dbloom": "Dan",
        "sbannasch": "Scott",
        "nvaras": "Nathan",
        "jgibbons": "Judi",
        "akitson": "Andy",
        "alubin": "Andrew",
        "wmcchrystal": "Will",
    }

    # Pattern to find possessive email prefixes: "cdorsey's" or "cdorsey's"
    pattern = re.compile(r"\b([a-z][a-z0-9_.]+)'s\b", re.IGNORECASE)

    def replace_name(match):
        prefix = match.group(1).lower()
        if prefix in name_map:
            return f"{name_map[prefix]}'s"
        else:
            # Fallback: capitalize first letter of prefix
            # Handle formats like "first.last" -> "First"
            if "." in prefix:
                first_part = prefix.split(".")[0]
            else:
                first_part = prefix
            return f"{first_part.capitalize()}'s"

    return pattern.sub(replace_name, text)


def _group_by_conflict(
    proposals: List[InteractiveProposal],
) -> Dict[Optional[str], List[InteractiveProposal]]:
    """Group proposals by normalized conflict summary (event name only)."""
    groups: Dict[Optional[str], List[InteractiveProposal]] = defaultdict(list)
    for prop in proposals:
        normalized = _normalize_conflict_summary(prop.conflict_summary)
        groups[normalized].append(prop)
    return groups


def _normalize_conflict_summary(summary: Optional[str]) -> Optional[str]:
    """
    Normalize conflict summary to "Intersects with" format, grouping by person.

    "cdorsey's 11:00 – 12:00 Mapping Time event moves to 12:00 – 1:00"
    -> "Intersects with cdorsey's Mapping Time event"

    "cdorsey's 3:00 Hold event, cdorsey's 3:30 – 5:00 Weekly Review event"
    -> "Intersects with cdorsey's 3:00 Hold and 3:30 – 5:00 Weekly Review events"

    Multiple people:
    "cdorsey's Hold event, rellis's Focus Time event"
    -> "Intersects with cdorsey's Hold event and rellis's Focus Time event"
    """
    import re
    from collections import defaultdict

    if not summary:
        return None

    # Clean up: remove "Overrides" prefix and markdown formatting
    cleaned = summary.replace("Overrides ", "").replace("*", "")

    # Already in intersects format
    if cleaned.lower().startswith("intersects with"):
        return _convert_email_prefix_to_name(cleaned)

    # Parse out event patterns - handles both "person's" and "your"
    # Pattern 1: "person's [time] EventName event"
    # Pattern 2: "your [time] EventName event"
    # Time can be "3:00" or "3:00 – 4:00" or "3:00 - 4:00"
    event_pattern = re.compile(
        r"(your|\w+'s)\s+(?:(\d{1,2}:\d{2})(?:\s*[–-]\s*\d{1,2}:\d{2})?\s+)?(.+?)\s+event",
        re.IGNORECASE
    )

    matches = event_pattern.findall(cleaned)

    if matches:
        # Group events by person
        person_events: dict = defaultdict(list)
        for possessive, time_part, event_name in matches:
            # Clean up event name (remove "moves to..." suffix, "and" prefix)
            event_name = re.sub(r"\s+moves?\s+to.*$", "", event_name, flags=re.IGNORECASE)
            event_name = re.sub(r"^and\s+", "", event_name, flags=re.IGNORECASE)
            event_name = event_name.strip()
            if event_name:
                person_events[possessive].append(event_name)

        if person_events:
            parts = []
            for possessive, events in person_events.items():
                if len(events) == 1:
                    parts.append(f"{possessive} {events[0]} event")
                else:
                    # Join with "and" for last, comma for others
                    event_list = " and ".join(events) if len(events) == 2 else \
                                 ", ".join(events[:-1]) + " and " + events[-1]
                    parts.append(f"{possessive} {event_list} events")

            # Join multiple people with "and"
            if len(parts) == 1:
                result = f"Intersects with {parts[0]}"
            elif len(parts) == 2:
                result = f"Intersects with {parts[0]} and {parts[1]}"
            else:
                result = f"Intersects with {', '.join(parts[:-1])}, and {parts[-1]}"
            return _convert_email_prefix_to_name(result)

    # Fallback patterns
    # Pattern: "moves 'EventName' to..."
    match = re.search(r"moves?\s+['\"]([^'\"]+)['\"]", summary, re.IGNORECASE)
    if match:
        event_name = match.group(1).strip()
        result = f"Intersects with {event_name} event"
        return _convert_email_prefix_to_name(result)

    # Pattern: "overlaps with X"
    if "overlap" in summary.lower():
        match = re.search(r"overlaps?\s+with\s+(.+)", summary, re.IGNORECASE)
        if match:
            result = f"Intersects with {match.group(1).strip()}"
            return _convert_email_prefix_to_name(result)

    # If nothing matched, prefix with "Intersects with" if reasonable
    if len(summary) < 100:  # Only for short summaries
        result = f"Intersects with {summary}"
        return _convert_email_prefix_to_name(result)

    return _convert_email_prefix_to_name(summary)


def _format_day(prop: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format as 'Thursday, Jan. 29'."""
    try:
        start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
        local_dt = start_dt.astimezone(tz)
        return local_dt.strftime("%A, %b. %d").replace(" 0", " ")
    except Exception:
        return "Unknown"


def _format_day_short(prop: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format as 'Thu Jan 29'."""
    try:
        start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
        local_dt = start_dt.astimezone(tz)
        return local_dt.strftime("%a %b %d").replace(" 0", " ")
    except Exception:
        return "Unknown"


def _format_time_range(prop: InteractiveProposal, tz: "pytz.BaseTzInfo") -> str:
    """Format as '1:30-2:00'."""
    try:
        start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(prop.end_utc.replace("Z", "+00:00"))
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)
        start_str = start_local.strftime("%I:%M").lstrip("0")
        end_str = end_local.strftime("%I:%M").lstrip("0")
        return f"{start_str}-{end_str}"
    except Exception:
        return prop.label


def _create_buttons(
    proposals: List[InteractiveProposal],
    session_id: str,
    tz: "pytz.BaseTzInfo",
    primary: bool = False,
) -> List[Dict[str, Any]]:
    """Create button elements for time selection."""
    buttons = []
    for prop in proposals:
        time_label = _format_time_range(prop, tz)
        button: Dict[str, Any] = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": time_label,
                "emoji": False,
            },
            "action_id": f"modal_time_select_{prop.id}",
            "value": f"{session_id}:{prop.id}",
        }
        if primary:
            button["style"] = "primary"
        buttons.append(button)
    return buttons
