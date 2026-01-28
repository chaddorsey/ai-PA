"""
Action handlers for scheduling options modal.

Handles:
- Tab switching (Schedule ↔ Build List) via views.update
- Time button clicks → push confirmation modal
- Build list checkbox changes → update preview dynamically
- Page switching for paginated checkbox view
- Copy button → post ephemeral message with text (clipboard workaround)
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from slack_bolt import App

from adapters.slack_proposal_modal import (
    PAGE_BEST_OPTIONS,
    PAGE_OVERRIDE_OPTIONS,
    VIEW_BUILD_LIST,
    VIEW_SCHEDULE,
    render_build_list_view,
    render_confirm_meeting_view,
    render_schedule_view,
)
from services.agent_bridge import send_synthetic_message
from services.interactive_proposals import MeetingContext
from services.proposal_cache import proposal_cache

logger = logging.getLogger(__name__)

# Regex pattern for matching time select buttons
TIME_SELECT_PATTERN = re.compile(r"^modal_time_select_.+$")
# Regex pattern for matching checkbox actions (legacy)
CHECKBOX_PATTERN = re.compile(r"^build_list_selections_\d+$")
# Regex pattern for matching toggle buttons (section+button pattern)
TOGGLE_PATTERN = re.compile(r"^build_list_toggle_.+$")
# Regex pattern for preview edit checkboxes
PREVIEW_EDIT_PATTERN = re.compile(r"^preview_edit_checkboxes_\d+$")


def register_modal_actions(app: App) -> None:
    """Register all modal-related action handlers."""

    # ─────────────────────────────────────────────────────────────────────
    # Tab switching
    # ─────────────────────────────────────────────────────────────────────

    @app.action("modal_tab_schedule")
    def handle_tab_schedule(ack, body, client):
        """Switch to Schedule tab via views.update."""
        ack()
        try:
            session_id = body["actions"][0]["value"]
            view_id = body["view"]["id"]

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            new_view = render_schedule_view(proposal_set)
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error switching to schedule tab: {e}", exc_info=True)

    @app.action("modal_tab_build_list")
    def handle_tab_build_list(ack, body, client):
        """Switch to Build List tab via views.update."""
        ack()
        try:
            session_id = body["actions"][0]["value"]
            view_id = body["view"]["id"]

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            new_view = render_build_list_view(
                proposal_set,
                selected_ids=[],
                current_page=PAGE_BEST_OPTIONS,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error switching to build list tab: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Page switching within Build List
    # ─────────────────────────────────────────────────────────────────────

    @app.action("build_list_page_best")
    def handle_page_best(ack, body, client):
        """Switch to Best Options page."""
        ack()
        _handle_page_switch(body, client, PAGE_BEST_OPTIONS)

    @app.action("build_list_page_override")
    def handle_page_override(ack, body, client):
        """Switch to Override Options page."""
        ack()
        _handle_page_switch(body, client, PAGE_OVERRIDE_OPTIONS)

    # ─────────────────────────────────────────────────────────────────────
    # Build list checkbox changes (dynamic update)
    # ─────────────────────────────────────────────────────────────────────

    @app.action(CHECKBOX_PATTERN)
    def handle_build_list_selections(ack, body, client):
        """Update preview when checkbox selections change."""
        ack()
        try:
            view_id = body["view"]["id"]
            private_metadata = body["view"].get("private_metadata", "")

            # Parse JSON metadata
            try:
                metadata = json.loads(private_metadata)
                session_id = metadata.get("session_id")
                previous_selected = set(metadata.get("selected_ids", []))
                current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid JSON metadata: {private_metadata}")
                return

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Get IDs for current page's proposals
            if current_page == PAGE_BEST_OPTIONS:
                current_page_ids = {p.id for p in proposal_set.clean_proposals}
            else:
                current_page_ids = (
                    {p.id for p in proposal_set.get_solo_overlap_proposals()} |
                    {p.id for p in proposal_set.get_multi_person_proposals()}
                )

            # Extract current page selections from view state
            current_page_selected = set()
            view_state = body["view"].get("state", {}).get("values", {})
            for block_id, block_values in view_state.items():
                if block_id.startswith("time_selections_"):
                    for action_id, action_data in block_values.items():
                        selected_options = action_data.get("selected_options", [])
                        current_page_selected.update([opt["value"] for opt in selected_options])

            # Merge: keep other page selections, update current page selections
            other_page_selected = previous_selected - current_page_ids
            all_selected = list(other_page_selected | current_page_selected)

            logger.info(f"Build list selections: {len(all_selected)} total ({len(current_page_selected)} on current page)")

            # Update view with merged selections
            new_view = render_build_list_view(
                proposal_set,
                selected_ids=all_selected,
                current_page=current_page,
                copy_feedback=False,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error handling build list selections: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Build list toggle buttons (section+button pattern)
    # ─────────────────────────────────────────────────────────────────────

    @app.action(TOGGLE_PATTERN)
    def handle_build_list_toggle(ack, body, client):
        """Toggle selection when Add/Added button is clicked."""
        ack()
        try:
            view_id = body["view"]["id"]
            private_metadata = body["view"].get("private_metadata", "")

            # Get the proposal ID being toggled
            toggled_id = body["actions"][0]["value"]

            # Parse JSON metadata
            try:
                metadata = json.loads(private_metadata)
                session_id = metadata.get("session_id")
                selected_ids = set(metadata.get("selected_ids", []))
                current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid JSON metadata: {private_metadata}")
                return

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Toggle the selection
            if toggled_id in selected_ids:
                selected_ids.remove(toggled_id)
                logger.info(f"Removed {toggled_id} from selection")
            else:
                selected_ids.add(toggled_id)
                logger.info(f"Added {toggled_id} to selection")

            # Update view with new selection state
            new_view = render_build_list_view(
                proposal_set,
                selected_ids=list(selected_ids),
                current_page=current_page,
                copy_feedback=False,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error handling build list toggle: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Preview edit mode
    # ─────────────────────────────────────────────────────────────────────

    @app.action("build_list_edit_start")
    def handle_edit_start(ack, body, client):
        """Enter edit mode for the preview list."""
        ack()
        try:
            view_id = body["view"]["id"]
            private_metadata = body["view"].get("private_metadata", "")

            try:
                metadata = json.loads(private_metadata)
                session_id = metadata.get("session_id")
                selected_ids = metadata.get("selected_ids", [])
                current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid JSON metadata: {private_metadata}")
                return

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Re-render with edit mode enabled
            new_view = render_build_list_view(
                proposal_set,
                selected_ids=selected_ids,
                current_page=current_page,
                edit_mode=True,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error entering edit mode: {e}", exc_info=True)

    @app.action("build_list_edit_done")
    def handle_edit_done(ack, body, client):
        """Exit edit mode, applying checkbox changes."""
        ack()
        try:
            view_id = body["view"]["id"]
            private_metadata = body["view"].get("private_metadata", "")

            try:
                metadata = json.loads(private_metadata)
                session_id = metadata.get("session_id")
                current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid JSON metadata: {private_metadata}")
                return

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Extract remaining selections from checkbox state
            remaining_ids = set()
            view_state = body["view"].get("state", {}).get("values", {})
            for block_id, block_values in view_state.items():
                if block_id.startswith("preview_edit_"):
                    for action_id, action_data in block_values.items():
                        selected_options = action_data.get("selected_options", [])
                        remaining_ids.update([opt["value"] for opt in selected_options])

            logger.info(f"Edit done: {len(remaining_ids)} items remaining")

            # Re-render with edit mode disabled
            new_view = render_build_list_view(
                proposal_set,
                selected_ids=list(remaining_ids),
                current_page=current_page,
                edit_mode=False,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error exiting edit mode: {e}", exc_info=True)

    @app.action(PREVIEW_EDIT_PATTERN)
    def handle_preview_edit_checkboxes(ack, body, client):
        """Handle checkbox changes in preview edit mode (no-op, changes applied on Done)."""
        ack()
        # Changes are applied when user clicks Done
        # This handler just acknowledges the action

    # ─────────────────────────────────────────────────────────────────────
    # Add All button
    # ─────────────────────────────────────────────────────────────────────

    @app.action("build_list_add_all")
    def handle_add_all(ack, body, client):
        """Add all items from current page to selection."""
        ack()
        try:
            view_id = body["view"]["id"]
            private_metadata = body["view"].get("private_metadata", "")

            try:
                metadata = json.loads(private_metadata)
                session_id = metadata.get("session_id")
                selected_ids = set(metadata.get("selected_ids", []))
                current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid JSON metadata: {private_metadata}")
                return

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Get all IDs from current page
            if current_page == PAGE_BEST_OPTIONS:
                page_ids = {p.id for p in proposal_set.clean_proposals}
            else:
                page_ids = (
                    {p.id for p in proposal_set.get_solo_overlap_proposals()} |
                    {p.id for p in proposal_set.get_multi_person_proposals()}
                )

            # Add all page items to selection
            selected_ids.update(page_ids)

            logger.info(f"Add All: now {len(selected_ids)} items selected")

            # Update view
            new_view = render_build_list_view(
                proposal_set,
                selected_ids=list(selected_ids),
                current_page=current_page,
                edit_mode=False,
            )
            client.views_update(view_id=view_id, view=new_view)

        except Exception as e:
            logger.error(f"Error handling Add All: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Overflow menu (Copy/Edit)
    # ─────────────────────────────────────────────────────────────────────

    @app.action("build_list_overflow")
    def handle_overflow(ack, body, client):
        """Handle overflow menu selection (Copy or Edit)."""
        ack()
        try:
            selected_value = body["actions"][0]["selected_option"]["value"]

            if selected_value == "copy":
                # Delegate to copy handler logic
                _handle_copy_action(body, client)
            elif selected_value == "edit":
                # Delegate to edit handler logic
                _handle_edit_start_action(body, client)

        except Exception as e:
            logger.error(f"Error handling overflow: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Copy button
    # ─────────────────────────────────────────────────────────────────────

    @app.action("build_list_copy")
    def handle_build_list_copy(ack, body, client):
        """Handle copy button click."""
        ack()
        _handle_copy_action(body, client)


    # ─────────────────────────────────────────────────────────────────────
    # Time button clicks (from Schedule tab)
    # ─────────────────────────────────────────────────────────────────────

    @app.action(TIME_SELECT_PATTERN)
    def handle_modal_time_select(ack, body, client):
        """Handle time button click - push confirmation modal."""
        ack()
        try:
            trigger_id = body["trigger_id"]
            action_value = body["actions"][0]["value"]

            logger.info(f"Time select clicked: {action_value}")

            # Parse session_id:proposal_id
            parts = action_value.split(":")
            if len(parts) != 2:
                logger.error(f"Invalid action value: {action_value}")
                return

            session_id, proposal_id = parts

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                return

            # Find the specific proposal
            proposal = proposal_set.get_proposal_by_id(proposal_id)
            if not proposal:
                logger.error(f"No proposal found with id {proposal_id}")
                return

            # Use stored meeting context from proposal set
            context = proposal_set.meeting_context
            if not context:
                context = MeetingContext(
                    inferred_title=proposal.suggested_title,
                )

            logger.info(f"Showing confirm modal for proposal {proposal_id} with {len(proposal.participants)} participants")

            # Push confirmation modal
            confirm_view = render_confirm_meeting_view(proposal, context, session_id)
            client.views_push(trigger_id=trigger_id, view=confirm_view)

        except Exception as e:
            logger.error(f"Error handling time selection: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Open modal button (from message)
    # ─────────────────────────────────────────────────────────────────────

    @app.action("open_options_modal")
    def handle_open_options_modal(ack, body, client):
        """Open the scheduling options modal."""
        ack()
        try:
            trigger_id = body["trigger_id"]
            session_id = body["actions"][0]["value"]

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                # Show error modal
                client.views_open(
                    trigger_id=trigger_id,
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Error"},
                        "close": {"type": "plain_text", "text": "Close"},
                        "blocks": [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Sorry, this scheduling session has expired. Please start a new request.",
                            },
                        }],
                    },
                )
                return

            # Open with Schedule view as default
            schedule_view = render_schedule_view(proposal_set)
            client.views_open(trigger_id=trigger_id, view=schedule_view)

        except Exception as e:
            logger.error(f"Error opening options modal: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Modal submissions
    # ─────────────────────────────────────────────────────────────────────

    @app.view("confirm_meeting_modal")
    def handle_confirm_meeting_submit(ack, body, client, view):
        """Handle meeting confirmation submission - triggers agent scheduling."""
        ack()
        try:
            private_metadata = view.get("private_metadata", "")
            parts = private_metadata.split(":")
            if len(parts) != 2:
                logger.error(f"Invalid private_metadata: {private_metadata}")
                return

            session_id, proposal_id = parts
            user_id = body["user"]["id"]

            # Extract form values
            values = view.get("state", {}).get("values", {})
            title = values.get("title_block", {}).get("meeting_title", {}).get("value", "")
            description = values.get("description_block", {}).get("meeting_description", {}).get("value", "")

            proposal_set = proposal_cache.get(session_id)
            if not proposal_set:
                logger.error(f"No proposal set found for session {session_id}")
                # Notify user
                channel_id = _get_user_dm_channel(client, user_id)
                if channel_id:
                    client.chat_postMessage(
                        channel=channel_id,
                        text="Those options expired while you were editing. Please ask me to find times again!",
                    )
                return

            proposal = proposal_set.get_proposal_by_id(proposal_id)
            if not proposal:
                logger.error(f"No proposal found with id {proposal_id}")
                return

            # Use extracted values or fall back to proposal defaults
            final_title = title or proposal.suggested_title or "Meeting"
            final_description = description or ""

            # Build scheduling data for agent
            scheduling_data = {
                "title": final_title,
                "description": final_description,
                "start": proposal.start_utc,
                "end": proposal.end_utc,
                "participants": proposal.participants,
                "proposal_id": proposal.id,
                "proposal_index": proposal.index,
                "category": proposal.category,
            }

            # Add conflict info if present
            if proposal.moved_events:
                scheduling_data["moved_events"] = [
                    {
                        "event_id": me.event_id,
                        "event_title": me.event_title,
                        "old_start": me.old_start,
                        "new_start": me.new_start,
                        "owner": me.owner,
                    }
                    for me in proposal.moved_events
                ]

            # Send synthetic message to agent to actually create the calendar event
            send_synthetic_message(
                user_id=user_id,
                proposal=proposal,
                scheduling_data=scheduling_data,
                meeting_context=proposal_set.meeting_context,
                client=client,
                logger=logger,
            )

            logger.info(f"Sent synthetic scheduling message for proposal {proposal_id}: {final_title}")

        except Exception as e:
            logger.error(f"Error handling meeting confirmation: {e}", exc_info=True)


def _handle_copy_action(body: Dict, client) -> None:
    """
    Handle copy action (from button or overflow).

    Since Slack has no clipboard API, we post the text as an ephemeral message.
    """
    try:
        view_id = body["view"]["id"]
        user_id = body["user"]["id"]
        private_metadata = body["view"].get("private_metadata", "")

        try:
            metadata = json.loads(private_metadata)
            session_id = metadata.get("session_id")
            selected_ids = metadata.get("selected_ids", [])
            current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Invalid JSON metadata: {private_metadata}")
            return

        proposal_set = proposal_cache.get(session_id)
        if not proposal_set:
            logger.error(f"No proposal set found for session {session_id}")
            return

        plain_text = _generate_plain_text_list(proposal_set, selected_ids)

        channel_id = _get_user_dm_channel(client, user_id)
        if plain_text and channel_id:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"📋 *Copy this text:*\n\n```\n{plain_text}\n```",
            )
        elif channel_id:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="No times selected yet. Select some options first!",
            )

        # Update modal to show feedback
        new_view = render_build_list_view(
            proposal_set,
            selected_ids=selected_ids,
            current_page=current_page,
            copy_feedback=True,
        )
        client.views_update(view_id=view_id, view=new_view)

    except Exception as e:
        logger.error(f"Error handling copy: {e}", exc_info=True)


def _handle_edit_start_action(body: Dict, client) -> None:
    """Handle edit start action (from overflow menu)."""
    try:
        view_id = body["view"]["id"]
        private_metadata = body["view"].get("private_metadata", "")

        try:
            metadata = json.loads(private_metadata)
            session_id = metadata.get("session_id")
            selected_ids = metadata.get("selected_ids", [])
            current_page = metadata.get("current_page", PAGE_BEST_OPTIONS)
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Invalid JSON metadata: {private_metadata}")
            return

        proposal_set = proposal_cache.get(session_id)
        if not proposal_set:
            logger.error(f"No proposal set found for session {session_id}")
            return

        new_view = render_build_list_view(
            proposal_set,
            selected_ids=selected_ids,
            current_page=current_page,
            edit_mode=True,
        )
        client.views_update(view_id=view_id, view=new_view)

    except Exception as e:
        logger.error(f"Error entering edit mode: {e}", exc_info=True)


def _handle_page_switch(body: Dict, client, new_page: int) -> None:
    """Handle page switch in Build List view, preserving selections."""
    try:
        view_id = body["view"]["id"]
        private_metadata = body["view"].get("private_metadata", "")

        # Parse JSON metadata - selections are stored here (not in view state)
        try:
            metadata = json.loads(private_metadata)
            session_id = metadata.get("session_id")
            selected_ids = metadata.get("selected_ids", [])
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Invalid JSON metadata in page switch: {private_metadata}")
            return

        proposal_set = proposal_cache.get(session_id)
        if not proposal_set:
            logger.error(f"No proposal set found for session {session_id}")
            return

        logger.info(f"Page switch to {new_page}: {len(selected_ids)} selections preserved")

        # Update view with new page, keeping all selections
        new_view = render_build_list_view(
            proposal_set,
            selected_ids=selected_ids,
            current_page=new_page,
            copy_feedback=False,
        )
        client.views_update(view_id=view_id, view=new_view)

    except Exception as e:
        logger.error(f"Error handling page switch: {e}", exc_info=True)


def _generate_plain_text_list(
    proposal_set: "InteractiveProposalSet",
    selected_ids: List[str],
) -> str:
    """Generate plain text version of the share list."""
    import pytz
    from datetime import datetime
    from collections import defaultdict

    if not selected_ids:
        return ""

    tz = pytz.timezone("America/New_York")

    # Collect selected proposals
    all_proposals = (
        proposal_set.clean_proposals +
        proposal_set.get_solo_overlap_proposals() +
        proposal_set.get_multi_person_proposals()
    )
    selected = [p for p in all_proposals if p.id in selected_ids]

    if not selected:
        return ""

    # Sort by start time
    selected.sort(key=lambda p: p.start_utc)

    # Group by day
    day_groups: Dict[str, List] = defaultdict(list)
    for prop in selected:
        try:
            start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
            local_dt = start_dt.astimezone(tz)
            day_key = local_dt.strftime("%Y-%m-%d")
            day_groups[day_key].append(prop)
        except Exception:
            pass

    lines = ["Meeting Options (Eastern time)", ""]

    for day_key in sorted(day_groups.keys()):
        day_proposals = day_groups[day_key]
        # Full day format
        try:
            start_dt = datetime.fromisoformat(day_proposals[0].start_utc.replace("Z", "+00:00"))
            local_dt = start_dt.astimezone(tz)
            day_str = local_dt.strftime("%A, %B %d").replace(" 0", " ")
        except Exception:
            day_str = "Unknown"

        lines.append(day_str)

        for prop in day_proposals:
            try:
                start_dt = datetime.fromisoformat(prop.start_utc.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(prop.end_utc.replace("Z", "+00:00"))
                start_local = start_dt.astimezone(tz)
                end_local = end_dt.astimezone(tz)
                start_str = start_local.strftime("%I:%M").lstrip("0")
                end_str = end_local.strftime("%I:%M").lstrip("0")
                time_str = f"{start_str}-{end_str}"
            except Exception:
                time_str = prop.label
            lines.append(f"• {time_str}")

        lines.append("")

    return "\n".join(lines).strip()


def _get_user_dm_channel(client, user_id: str) -> Optional[str]:
    """Get or open DM channel with user."""
    try:
        response = client.conversations_open(users=[user_id])
        return response["channel"]["id"]
    except Exception as e:
        logger.error(f"Error opening DM channel: {e}")
        return None
