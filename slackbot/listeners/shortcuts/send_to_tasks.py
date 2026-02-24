"""
Message shortcut handlers for queuing Slack messages as tasks.

Two shortcuts:
  - send_to_tasks: Silent queue, ephemeral confirmation
  - send_to_tasks_modal: Opens modal for optional notes before queuing

Messages are appended as JSON entries (separated by ---) to the
queued_tasks_from_slack memory block in Letta, for processing by the
Pulse agent.
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
PULSE_AGENT_ID = os.getenv(
    "LETTA_PULSE_AGENT_ID",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
)


def _append_to_queue(entry: dict, logger: Logger) -> bool:
    """Append a JSON entry to the queued_tasks_from_slack memory block.

    Uses --- separators between entries (consistent with other queue blocks,
    required for atomic cleanup by add_extracted_tasks).

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

        # Build new entry with --- separator
        new_entry = json.dumps(entry, ensure_ascii=False)

        # Append with --- separator
        if current_value:
            if current_value.endswith("---"):
                updated = f"{current_value}\n{new_entry}\n---"
            else:
                updated = f"{current_value}\n---\n{new_entry}\n---"
        else:
            updated = f"{new_entry}\n---"

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
    thread_ts = message.get("thread_ts", "")

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
        "thread_ts": thread_ts,
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
        "source_ref_id": f"{info['channel_id']}:{info['message_ts']}",
        "message_ts": info["message_ts"],
    }
    if info.get("thread_ts"):
        entry["thread_ts"] = info["thread_ts"]
    if info.get("files"):
        entry["files"] = info["files"]
    if notes:
        entry["notes"] = notes
    return entry


def _queue_and_trigger(entry: dict, logger: Logger) -> None:
    """Write to queue block, then trigger the Pulse agent.

    Runs in a background thread. Sequenced so the queue entry exists
    before the agent receives the extraction trigger.
    """
    if not _append_to_queue(entry, logger):
        return  # Queue write failed — don't trigger without durable record

    _trigger_extraction(entry, logger)


def _trigger_extraction(entry: dict, logger: Logger) -> None:
    """Send a message to the Pulse agent to extract the queued task.

    Best-effort. If it fails, the entry stays in the queue for manual
    or scheduled processing.
    """
    try:
        text_preview = entry.get("text", "")[:200]
        channel = entry.get("channel", "")
        from_id = entry.get("from_id", "")
        link = entry.get("link", "")
        source_ref = entry.get("source_ref_id", "")
        notes = entry.get("notes", "")

        parts = [
            "New task queued from Slack. Process this item from "
            "queued_tasks_from_slack using add_extracted_tasks.",
            f"Channel: {channel}",
            f"From: {from_id}",
            f"Text: {text_preview}",
            f"Link: {link}",
            f"source_ref_id (for cleanup_entry_identifier): {source_ref}",
        ]
        thread_ts = entry.get("thread_ts", "")
        if thread_ts:
            parts.append(
                f"Thread TS (for reference_id, use format "
                f"slack-{{channel}}-{{ts}}-t{{thread_ts}}): {thread_ts}"
            )
        if notes:
            parts.append(f"User notes: {notes}")
        parts.append(
            "Follow the task_extraction_process_slack guidelines "
            "including the Context Enrichment Protocol. "
            "Use cleanup_block_id=block-033a720d-1f13-44a2-a5cb-b5edde418ea1."
        )
        message = "\n".join(parts)

        payload = json.dumps({
            "messages": [{"role": "user", "content": message}]
        })
        resp = requests.post(
            f"{LETTA_BASE_URL}/v1/agents/{PULSE_AGENT_ID}/messages/",
            json=json.loads(payload),
            timeout=120,
        )
        resp.raise_for_status()
        logger.info(f"Triggered extraction for {source_ref}")

    except Exception as e:
        logger.error(f"Failed to trigger extraction: {e}", exc_info=True)


def send_to_tasks_callback(body: dict, ack: Ack, client: WebClient, logger: Logger):
    """Silent send — queue message as task, show ephemeral confirmation."""
    ack()

    try:
        info = _extract_message_info(body, logger)
        logger.info(f"send_to_tasks triggered: channel={info['channel_id']}, text={info['text'][:50]}")

        # Queue the task and trigger extraction (sequenced in background)
        entry = _build_queue_entry(info)
        threading.Thread(
            target=_queue_and_trigger,
            args=(entry, logger),
            daemon=True,
        ).start()

        # Try ephemeral confirmation (may fail in DMs/private channels)
        preview = info["text"][:100] + ("..." if len(info["text"]) > 100 else "")
        try:
            client.chat_postEphemeral(
                channel=info["channel_id"],
                user=info["triggering_user_id"],
                text=f"Queued for tasks: _{preview}_",
            )
        except Exception:
            # Ephemeral failed (channel_not_found in DMs) — not critical
            logger.info(f"Ephemeral confirmation skipped for channel {info['channel_id']}")

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
            "message_ts": info["message_ts"],
            "thread_ts": info["thread_ts"],
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
            "message_ts": metadata.get("message_ts", ""),
            "thread_ts": metadata.get("thread_ts", ""),
            "files": metadata.get("files", []),
        }

        entry = _build_queue_entry(info, notes=notes)

        # Queue the task and trigger extraction (sequenced in background)
        threading.Thread(
            target=_queue_and_trigger,
            args=(entry, logger),
            daemon=True,
        ).start()

    except Exception as e:
        logger.error(f"send_to_tasks_view submission failed: {e}", exc_info=True)
