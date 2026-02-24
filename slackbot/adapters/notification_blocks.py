"""
Block Kit renderer for agent outbound notifications.

Composes Slack Block Kit JSON for notification messages with
interactive action buttons (approve, modify, skip).
"""

from typing import Any, Dict, List


def render_notification_blocks(
    notification_data: Dict[str, Any],
    pending_reply_id: str,
) -> List[Dict[str, Any]]:
    """
    Render Block Kit blocks for an agent notification message.

    Args:
        notification_data: Structured notification from the agent tool.
            Expected keys: text, detail (optional), suggested_reply (optional),
            footer (optional).
        pending_reply_id: UUID of the pending_agent_replies row,
            encoded in button values for action handler lookup.

    Returns:
        List of Slack Block Kit block dicts.
    """
    blocks: List[Dict[str, Any]] = []

    # Main notification text
    text = notification_data.get("text", "")
    if text:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

    # Detail / context line
    detail = notification_data.get("detail", "")
    if detail:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": detail}],
        })

    # Suggested reply as a quote
    suggested_reply = notification_data.get("suggested_reply", "")
    if suggested_reply:
        # Indent each line with > for block quote effect
        quoted = "\n".join(f"> {line}" for line in suggested_reply.split("\n"))
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Suggested reply:*\n{quoted}"},
        })

    # Footer / additional context
    footer = notification_data.get("footer", "")
    if footer:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"_{footer}_"}],
        })

    # Divider before actions
    blocks.append({"type": "divider"})

    # Action buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Send Reply"},
                "action_id": "notification_approve",
                "value": pending_reply_id,
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Modify"},
                "action_id": "notification_modify",
                "value": pending_reply_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Skip"},
                "action_id": "notification_skip",
                "value": pending_reply_id,
                "style": "danger",
            },
        ],
    })

    return blocks


def render_notification_fallback_text(notification_data: Dict[str, Any]) -> str:
    """
    Render plain-text fallback for notifications (shown in push notifications
    and accessibility contexts where blocks aren't rendered).
    """
    text = notification_data.get("text", "Agent notification")
    suggested = notification_data.get("suggested_reply", "")
    if suggested:
        return f"{text} | Suggested reply: {suggested}"
    return text


def render_modify_modal(
    pending_reply_id: str,
    suggested_reply: str,
) -> Dict[str, Any]:
    """
    Render a modal for modifying the suggested reply text.

    Args:
        pending_reply_id: UUID of the pending reply (stored in private_metadata).
        suggested_reply: Pre-filled text for the user to edit.

    Returns:
        Slack view dict for views.open.
    """
    return {
        "type": "modal",
        "callback_id": "notification_modify_submit",
        "private_metadata": pending_reply_id,
        "title": {"type": "plain_text", "text": "Modify Reply"},
        "submit": {"type": "plain_text", "text": "Send Modified Reply"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "reply_text_block",
                "label": {"type": "plain_text", "text": "Reply text"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reply_text_input",
                    "multiline": True,
                    "initial_value": suggested_reply,
                },
            },
        ],
    }
