"""
Action handlers for interactive scheduling proposals.

Handles button clicks, modal confirmations, and expand actions.
"""
from logging import Logger
from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.proposal_cache import proposal_cache
from adapters.slack_proposal_adapter import (
    render_confirmation_modal,
    render_expanded_conflicts,
)


def _handle_proposal_select(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle proposal button click - opens confirmation modal."""
    ack()

    try:
        # Extract session_id and proposal_id from button value
        action_value = body["actions"][0]["value"]
        session_id, proposal_id = action_value.split(":", 1)

        # Look up proposal from cache
        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            # Proposals expired or not found
            channel_id = body.get("channel", {}).get("id")
            user_id = body.get("user", {}).get("id")

            if channel_id and user_id:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Those options have expired. Ask me to find times again! 🔄",
                )
            logger.warning(f"Proposal set not found for session: {session_id}")
            return

        # Find the specific proposal
        proposal = proposal_set.get_proposal_by_id(proposal_id)

        if not proposal:
            logger.error(f"Proposal {proposal_id} not found in session {session_id}")
            return

        # Render and open confirmation modal
        modal = render_confirmation_modal(
            proposal=proposal,
            context=proposal_set.meeting_context,
            session_id=session_id,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

        logger.info(f"Opened confirmation modal for proposal {proposal_id}")

    except Exception as e:
        logger.error(f"Error handling proposal select: {e}", exc_info=True)


def _handle_proposal_expand(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle expand button click - shows conflict proposals."""
    ack()

    try:
        session_id = body["actions"][0]["value"]

        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            channel_id = body.get("channel", {}).get("id")
            user_id = body.get("user", {}).get("id")

            if channel_id and user_id:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Those options have expired. Ask me to find times again! 🔄",
                )
            return

        # Mark as expanded and get new blocks
        proposal_set.show_conflicts_expanded = True

        # Get the expanded conflict blocks
        expanded_blocks = render_expanded_conflicts(proposal_set)

        if expanded_blocks:
            # Update the message to include expanded conflicts
            # We need to reconstruct the full block list
            from adapters.slack_proposal_adapter import render_proposal_blocks
            full_blocks = render_proposal_blocks(proposal_set)

            # Update the message
            channel_id = body.get("channel", {}).get("id")
            message_ts = body.get("message", {}).get("ts")

            if channel_id and message_ts:
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=full_blocks,
                )

        logger.info(f"Expanded conflict proposals for session {session_id}")

    except Exception as e:
        logger.error(f"Error handling proposal expand: {e}", exc_info=True)


def register(app: App) -> None:
    """Register action handlers with the Slack app."""

    @app.action("schedule_proposal_select")
    def on_proposal_select(ack, body, client, logger):
        _handle_proposal_select(ack, body, client, logger)

    @app.action("schedule_proposal_expand")
    def on_proposal_expand(ack, body, client, logger):
        _handle_proposal_expand(ack, body, client, logger)
