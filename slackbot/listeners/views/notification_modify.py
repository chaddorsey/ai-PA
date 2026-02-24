"""
View submission handler for notification modify modal.

When the user clicks "Modify" on a notification and edits the reply text,
this handler receives the submission and routes the custom text to the
originating agent.
"""

import json
from logging import Logger

from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.pending_replies import (
    get_pending_reply_by_id,
    resolve_pending_reply,
)


def _handle_modify_submit(
    ack: Ack,
    body: dict,
    view: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle modify modal submission — send custom reply text to agent."""
    ack()

    try:
        pending_id = view.get("private_metadata", "")
        if not pending_id:
            logger.error("No pending_reply_id in modify modal metadata")
            return

        pending = get_pending_reply_by_id(pending_id)
        if not pending or pending.get("status") != "pending":
            logger.warning("Pending reply %s not found or already resolved", pending_id)
            user_id = body.get("user", {}).get("id")
            if user_id:
                client.chat_postMessage(
                    channel=user_id,
                    text="This notification has already been handled.",
                )
            return

        # Extract custom reply text from form
        values = view.get("state", {}).get("values", {})
        custom_text = (
            values.get("reply_text_block", {})
            .get("reply_text_input", {})
            .get("value", "")
        )

        if not custom_text.strip():
            logger.warning("Empty custom reply text submitted")
            return

        agent_id = pending["agent_id"]
        reply_context = pending.get("reply_context", {})
        channel_id = pending["channel_id"]
        thread_ts = pending["thread_ts"]
        user_id = body.get("user", {}).get("id", "")

        # Post confirmation in thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Sending modified reply: \"{custom_text}\"",
        )

        # Build synthetic message for the agent
        ref_id = reply_context.get("ref_id", "unknown")
        routing_tool = reply_context.get("routing_tool", "")
        routing_args = reply_context.get("routing_args", {})

        synthetic = (
            f"User MODIFIED the completion feedback for ref_id {ref_id}.\n"
            f"Custom reply text to use: \"{custom_text}\"\n\n"
        )

        if routing_tool and routing_args:
            args_str = json.dumps(routing_args)
            synthetic += (
                f"Call {routing_tool} with args {args_str} and reply_text=\"{custom_text}\".\n"
            )
            resolve_tool = reply_context.get("resolve_tool", "")
            resolve_args = reply_context.get("resolve_args", {})
            if resolve_tool and resolve_args:
                synthetic += f"Then call {resolve_tool} with args {json.dumps(resolve_args)} to resolve the comment.\n"

        # Resolve the pending reply
        resolve_pending_reply(pending_id)

        # Route to the originating agent
        from listeners.actions.notification_actions import _send_to_agent

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
        logger.error("Error handling notification modify submit: %s", e, exc_info=True)


def register(app: App) -> None:
    """Register view submission handler with the Slack app."""

    @app.view("notification_modify_submit")
    def on_modify_submit(ack, body, view, client, logger):
        _handle_modify_submit(ack, body, view, client, logger)
