"""
View submission handler for proposal confirmation modal.

Extracts form values, combines with proposal data, and sends
synthetic message to agent for scheduling.
"""
from logging import Logger
from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.proposal_cache import proposal_cache
from services.agent_bridge import send_synthetic_message


def _handle_proposal_confirm(
    ack: Ack,
    body: dict,
    view: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle modal form submission - triggers agent scheduling."""
    ack()

    try:
        # Extract session_id and proposal_id from private_metadata
        metadata = view.get("private_metadata", "")
        if ":" not in metadata:
            logger.error(f"Invalid private_metadata format: {metadata}")
            return

        session_id, proposal_id = metadata.split(":", 1)

        # Look up proposal from cache
        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            logger.warning(f"Proposal set expired during modal: {session_id}")
            # Send ephemeral message to user
            user_id = body.get("user", {}).get("id")
            if user_id:
                client.chat_postMessage(
                    channel=user_id,  # DM the user
                    text="Those options expired while you were editing. Please ask me to find times again!",
                )
            return

        proposal = proposal_set.get_proposal_by_id(proposal_id)

        if not proposal:
            logger.error(f"Proposal {proposal_id} not found in session {session_id}")
            return

        # Extract form values
        values = view.get("state", {}).get("values", {})

        title = values.get("title_block", {}).get("meeting_title", {}).get("value", "")
        description = values.get("description_block", {}).get("meeting_description", {}).get("value", "")

        # Use extracted values or fall back to proposal defaults
        final_title = title or proposal.suggested_title or "Meeting"
        final_description = description or ""

        # Build scheduling data
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

        user_id = body.get("user", {}).get("id")

        # Send synthetic message to agent
        send_synthetic_message(
            user_id=user_id,
            proposal=proposal,
            scheduling_data=scheduling_data,
            meeting_context=proposal_set.meeting_context,
            client=client,
            logger=logger,
        )

        logger.info(f"Sent synthetic scheduling message for proposal {proposal_id}")

    except Exception as e:
        logger.error(f"Error handling proposal confirmation: {e}", exc_info=True)


def register(app: App) -> None:
    """Register view submission handler with the Slack app."""

    @app.view("schedule_proposal_confirm")
    def on_proposal_confirm(ack, body, view, client, logger):
        _handle_proposal_confirm(ack, body, view, client, logger)
