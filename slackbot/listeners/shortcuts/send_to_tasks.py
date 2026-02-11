"""
Message shortcut handlers for queuing Slack messages as tasks.

Two shortcuts:
  - send_to_tasks: Silent queue, ephemeral confirmation
  - send_to_tasks_modal: Opens modal for optional notes before queuing

Messages are appended as JSON lines to the queued_tasks_from_slack
memory block in Letta, for later processing by the Pulse agent.
"""
import json
import os
import threading
from datetime import datetime, timezone
from logging import Logger

import requests
from slack_bolt import Ack
from slack_sdk import WebClient

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
QUEUE_BLOCK_ID = os.getenv(
    "LETTA_TASK_QUEUE_BLOCK_ID",
    "block-033a720d-1f13-44a2-a5cb-b5edde418ea1",
)


def _append_to_queue(entry: dict, logger: Logger) -> bool:
    """Append a JSON-line entry to the queued_tasks_from_slack memory block.

    Returns True on success, False on failure.
    """
    try:
        # Read current block value
        resp = requests.get(
            f"{LETTA_BASE_URL}/v1/blocks/{QUEUE_BLOCK_ID}",
            timeout=10,
        )
        resp.raise_for_status()
        block = resp.json()
        current_value = block.get("value", "").strip()

        # Build new JSON line
        new_line = json.dumps(entry, ensure_ascii=False)

        # Append
        if current_value:
            updated = f"{current_value}\n{new_line}"
        else:
            updated = new_line

        # Write back
        resp = requests.patch(
            f"{LETTA_BASE_URL}/v1/blocks/{QUEUE_BLOCK_ID}",
            json={"value": updated},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"Queued task to memory block: {entry.get('link', '?')}")
        return True

    except Exception as e:
        logger.error(f"Failed to append to task queue block: {e}", exc_info=True)
        return False


def _extract_message_info(body: dict, logger: Logger) -> dict:
    """Extract message details from a message shortcut body."""
    message = body.get("message", {})
    channel = body.get("channel", {})
    user = body.get("user", {})

    text = message.get("text", "")
    message_user_id = message.get("user", "unknown")
    channel_id = channel.get("id", "")
    channel_name = channel.get("name", channel_id)
    triggering_user_id = user.get("id", "")
    message_ts = message.get("ts", "")

    # Build permalink
    permalink = ""
    if channel_id and message_ts:
        ts_clean = message_ts.replace(".", "")
        permalink = f"https://slack.com/archives/{channel_id}/p{ts_clean}"

    # Extract file names and URLs from message attachments
    files = []
    for f in message.get("files", []):
        files.append({
            "name": f.get("name", ""),
            "url": f.get("url_private", ""),
            "type": f.get("filetype", ""),
        })

    return {
        "text": text,
        "message_user_id": message_user_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "triggering_user_id": triggering_user_id,
        "message_ts": message_ts,
        "permalink": permalink,
        "files": files,
    }


def _build_queue_entry(info: dict, notes: str = "") -> dict:
    """Build a queue entry dict from extracted message info."""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "from_id": info["message_user_id"],
        "channel": info["channel_name"],
        "channel_id": info["channel_id"],
        "text": info["text"],
        "link": info["permalink"],
    }
    if info.get("files"):
        entry["files"] = info["files"]
    if notes:
        entry["notes"] = notes
    return entry


def send_to_tasks_callback(body: dict, ack: Ack, client: WebClient, logger: Logger):
    """Silent send — queue message as task, show ephemeral confirmation."""
    ack()

    try:
        info = _extract_message_info(body, logger)
        preview = info["text"][:100] + ("..." if len(info["text"]) > 100 else "")

        # Immediate ephemeral confirmation
        client.chat_postEphemeral(
            channel=info["channel_id"],
            user=info["triggering_user_id"],
            text=f"Queued for tasks: _{preview}_",
        )

        # Append to memory block in background thread
        entry = _build_queue_entry(info)
        thread = threading.Thread(
            target=_append_to_queue,
            args=(entry, logger),
            daemon=True,
        )
        thread.start()

    except Exception as e:
        logger.error(f"send_to_tasks shortcut failed: {e}", exc_info=True)


def send_to_tasks_modal_callback(body: dict, ack: Ack, client: WebClient, logger: Logger):
    """Open modal for notes before queuing as task."""
    ack()

    try:
        info = _extract_message_info(body, logger)
        preview = info["text"][:300] + ("..." if len(info["text"]) > 300 else "")

        # Store message info in private_metadata for the view submission
        metadata = json.dumps({
            "text": info["text"],
            "message_user_id": info["message_user_id"],
            "channel_id": info["channel_id"],
            "channel_name": info["channel_name"],
            "permalink": info["permalink"],
            "triggering_user_id": info["triggering_user_id"],
            "files": info["files"],
        })

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "send_to_tasks_view",
                "title": {"type": "plain_text", "text": "Send to Tasks"},
                "submit": {"type": "plain_text", "text": "Send"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": metadata,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Message:*\n>{preview}",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "notes_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Notes"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "notes_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Add context, priority, due date...",
                            },
                            "multiline": False,
                        },
                    },
                ],
            },
        )
    except Exception as e:
        logger.error(f"send_to_tasks_modal shortcut failed: {e}", exc_info=True)


def send_to_tasks_view_callback(ack: Ack, body: dict, view: dict, client: WebClient, logger: Logger):
    """Handle modal submission — queue message + notes."""
    ack()

    try:
        metadata = json.loads(view.get("private_metadata", "{}"))

        # Extract notes from form
        values = view.get("state", {}).get("values", {})
        notes = values.get("notes_block", {}).get("notes_input", {}).get("value", "") or ""

        info = {
            "text": metadata.get("text", ""),
            "message_user_id": metadata.get("message_user_id", ""),
            "channel_id": metadata.get("channel_id", ""),
            "channel_name": metadata.get("channel_name", ""),
            "permalink": metadata.get("permalink", ""),
            "files": metadata.get("files", []),
        }

        entry = _build_queue_entry(info, notes=notes)

        # Append to memory block in background thread
        thread = threading.Thread(
            target=_append_to_queue,
            args=(entry, logger),
            daemon=True,
        )
        thread.start()

    except Exception as e:
        logger.error(f"send_to_tasks_view submission failed: {e}", exc_info=True)
