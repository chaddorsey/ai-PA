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
                    text="Those options have expired. Ask me to find times again!",
                )
            return

        # Mark as expanded and get new blocks
        proposal_set.show_conflicts_expanded = True

        # Reconstruct the full block list with intro
        from adapters.slack_proposal_adapter import render_proposal_blocks, INTRO_TEXT
        full_blocks = _build_full_blocks(proposal_set, INTRO_TEXT)

        # Update the message
        channel_id = body.get("channel", {}).get("id")
        message_ts = body.get("message", {}).get("ts")

        if channel_id and message_ts:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=INTRO_TEXT,
                blocks=full_blocks,
            )

        logger.info(f"Expanded conflict proposals for session {session_id}")

    except Exception as e:
        logger.error(f"Error handling proposal expand: {e}", exc_info=True)


def _handle_proposal_collapse(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle collapse button click - hides conflict proposals."""
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
                    text="Those options have expired. Ask me to find times again!",
                )
            return

        # Mark as collapsed
        proposal_set.show_conflicts_expanded = False

        # Reconstruct the full block list with intro
        from adapters.slack_proposal_adapter import render_proposal_blocks, INTRO_TEXT
        full_blocks = _build_full_blocks(proposal_set, INTRO_TEXT)

        # Update the message
        channel_id = body.get("channel", {}).get("id")
        message_ts = body.get("message", {}).get("ts")

        if channel_id and message_ts:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=INTRO_TEXT,
                blocks=full_blocks,
            )

        logger.info(f"Collapsed conflict proposals for session {session_id}")

    except Exception as e:
        logger.error(f"Error handling proposal collapse: {e}", exc_info=True)


def _build_full_blocks(proposal_set, intro_text: str) -> list:
    """Build full block list with intro section."""
    from adapters.slack_proposal_adapter import render_proposal_blocks

    intro_block = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": intro_text,
        },
    }
    proposal_blocks = render_proposal_blocks(proposal_set)
    return [intro_block] + proposal_blocks


def register(app: App) -> None:
    """Register action handlers with the Slack app."""
    import re

    # Use regex to match schedule_proposal_select_* action IDs
    @app.action(re.compile(r"^schedule_proposal_select_"))
    def on_proposal_select(ack, body, client, logger):
        _handle_proposal_select(ack, body, client, logger)

    @app.action("schedule_proposal_expand")
    def on_proposal_expand(ack, body, client, logger):
        _handle_proposal_expand(ack, body, client, logger)

    @app.action("schedule_proposal_collapse")
    def on_proposal_collapse(ack, body, client, logger):
        _handle_proposal_collapse(ack, body, client, logger)
