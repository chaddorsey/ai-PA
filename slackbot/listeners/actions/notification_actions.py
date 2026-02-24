"""
Action handlers for agent outbound notification buttons.

Handles Approve, Modify, and Skip button clicks on notification messages.
Routes user decisions back to the originating Letta agent via
send_synthetic_message pattern.
"""

import json
import logging
from logging import Logger

from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.pending_replies import (
    get_pending_reply_by_id,
    resolve_pending_reply,
)
from adapters.notification_blocks import render_modify_modal


logger = logging.getLogger(__name__)


def _send_to_agent(
    agent_id: str,
    message: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
    client: WebClient,
    logger: Logger,
) -> None:
    """
    Send a synthetic message to the originating agent and stream response to thread.

    Uses LettaAPIStreaming with explicit agent_id to route to the correct agent.
    """
    try:
        from ai.conversation_helper import get_conversation_for_user
        from ai.providers.letta_stream import LettaAPIStreaming

        conversation_id = None
        try:
            conversation_id = get_conversation_for_user(
                user_id, agent_id=agent_id, logger=logger
            )
        except Exception as e:
            logger.warning("Could not get conversation for notification reply: %s", e)

        streamer = LettaAPIStreaming(
            logger=logger,
            conversation_id=conversation_id,
            agent_id=agent_id,
        )

        # Collect response
        text_chunks = []
        for event in streamer.chat_stream_with_events(None, message):
            event_type = event.get("type")
            if event_type == "text":
                text_chunks.append(event.get("content", ""))
            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "")
                logger.info("Agent called tool during notification response: %s", tool_name)

        final_text = (streamer.last_message or "".join(text_chunks)).strip()

        if final_text:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=final_text,
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="Done.",
            )

    except Exception as e:
        logger.error("Error sending notification response to agent: %s", e, exc_info=True)
        try:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="Sorry, I had trouble processing that response. Please try again.",
            )
        except Exception:
            pass


def _handle_notification_approve(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle 'Send Reply' button click — approve the suggested feedback."""
    ack()

    try:
        pending_id = body["actions"][0]["value"]
        pending = get_pending_reply_by_id(pending_id)

        if not pending or pending.get("status") != "pending":
            _send_expired_message(body, client)
            return

        agent_id = pending["agent_id"]
        reply_context = pending.get("reply_context", {})
        notification_data = pending.get("notification_data", {})
        channel_id = pending["channel_id"]
        thread_ts = pending["thread_ts"]
        user_id = body.get("user", {}).get("id", "")
        suggested_reply = notification_data.get("suggested_reply", "")

        # Post confirmation in thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Sending the suggested reply...",
        )

        # Build synthetic message for the agent
        ref_id = reply_context.get("ref_id", "unknown")
        routing_tool = reply_context.get("routing_tool", "")
        routing_args = reply_context.get("routing_args", {})

        synthetic = (
            f"User APPROVED the completion feedback for ref_id {ref_id}.\n"
            f"Reply text to use: \"{suggested_reply}\"\n\n"
        )

        if routing_tool and routing_args:
            args_str = json.dumps(routing_args)
            synthetic += (
                f"Call {routing_tool} with args {args_str} and reply_text=\"{suggested_reply}\".\n"
            )
            # Check if we should also resolve
            resolve_tool = reply_context.get("resolve_tool", "")
            resolve_args = reply_context.get("resolve_args", {})
            if resolve_tool and resolve_args:
                synthetic += f"Then call {resolve_tool} with args {json.dumps(resolve_args)} to resolve the comment.\n"

        # Resolve the pending reply
        resolve_pending_reply(pending_id)

        # Route to the originating agent
        _send_to_agent(
            agent_id=agent_id,
            message=synthetic,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            client=client,
            logger=logger,
        )

    except Exception as e:
        logger.error("Error handling notification approve: %s", e, exc_info=True)


def _handle_notification_modify(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle 'Modify' button click — open modal with pre-filled reply text."""
    ack()

    try:
        pending_id = body["actions"][0]["value"]
        pending = get_pending_reply_by_id(pending_id)

        if not pending or pending.get("status") != "pending":
            _send_expired_message(body, client)
            return

        notification_data = pending.get("notification_data", {})
        suggested_reply = notification_data.get("suggested_reply", "")

        modal = render_modify_modal(pending_id, suggested_reply)
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

    except Exception as e:
        logger.error("Error handling notification modify: %s", e, exc_info=True)


def _handle_notification_skip(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle 'Skip' button click — no feedback sent."""
    ack()

    try:
        pending_id = body["actions"][0]["value"]
        pending = get_pending_reply_by_id(pending_id)

        if not pending or pending.get("status") != "pending":
            _send_expired_message(body, client)
            return

        channel_id = pending["channel_id"]
        thread_ts = pending["thread_ts"]

        resolve_pending_reply(pending_id)

        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Skipped \u2014 no feedback sent.",
        )

    except Exception as e:
        logger.error("Error handling notification skip: %s", e, exc_info=True)


def _send_expired_message(body: dict, client: WebClient) -> None:
    """Send ephemeral message when a notification has already been resolved."""
    channel_id = body.get("channel", {}).get("id")
    user_id = body.get("user", {}).get("id")
    if channel_id and user_id:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="This notification has already been handled.",
        )


def register(app: App) -> None:
    """Register notification action handlers with the Slack app."""

    @app.action("notification_approve")
    def on_approve(ack, body, client, logger):
        _handle_notification_approve(ack, body, client, logger)

    @app.action("notification_modify")
    def on_modify(ack, body, client, logger):
        _handle_notification_modify(ack, body, client, logger)

    @app.action("notification_skip")
    def on_skip(ack, body, client, logger):
        _handle_notification_skip(ack, body, client, logger)
