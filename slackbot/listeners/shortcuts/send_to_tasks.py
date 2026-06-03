"""
Message shortcut handlers for sending Slack messages to the Tasks agent.

Two shortcuts:
  - send_to_tasks: Silent send, ephemeral confirmation
  - send_to_tasks_modal: Opens modal for optional notes before sending

Messages are written as Spark Records to the tasks agent's spark_queue block,
then the tasks agent is notified to process them.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from logging import Logger

import requests
from slack_bolt import Ack
from slack_sdk import WebClient

# Local-mode notification target. The receiver is a host-side daemon
# that dispatches to per-agent warm letta-code subprocesses via
# stdin-stream-json. The slackbot runs inside Docker, so it reaches
# the host via host.docker.internal.
PUSH_RECEIVER_URL = os.getenv(
    "LETTA_PUSH_RECEIVER_URL",
    "http://host.docker.internal:8099/push",
)
# Source slug used in receiver's DEFAULT_SOURCE_ROUTING; "slack" → pulse agent.
PUSH_SOURCE = "slack"


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

    import re

    # Build permalink
    permalink = ""
    if channel_id and message_ts:
        ts_clean = message_ts.replace(".", "")
        permalink = f"https://slack.com/archives/{channel_id}/p{ts_clean}"

    # Extract full URLs from blocks (Slack's text field truncates URLs in <url|label> format)
    urls = []
    for block in message.get("blocks", []):
        for element in block.get("elements", []):
            for item in element.get("elements", []):
                if item.get("type") == "link":
                    url = item.get("url", "")
                    if url:
                        urls.append(url)

    # Also extract URLs from Slack mrkdwn <url|label> patterns in text as fallback
    import re
    for match in re.finditer(r'<(https?://[^|>]+)', text):
        url = match.group(1)
        if url not in urls:
            urls.append(url)

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
        "urls": urls,
        "message_user_id": message_user_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "triggering_user_id": triggering_user_id,
        "message_ts": message_ts,
        "thread_ts": thread_ts,
        "permalink": permalink,
        "files": files,
    }


def _build_entry(info: dict, notes: str = "") -> dict:
    """Build an entry dict from extracted message info."""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "from_id": info["message_user_id"],
        "channel": info["channel_name"],
        "channel_id": info["channel_id"],
        "text": info["text"],
        "link": info["permalink"],
        "message_ts": info["message_ts"],
        "triggering_user_id": info["triggering_user_id"],
    }
    if info.get("thread_ts"):
        entry["thread_ts"] = info["thread_ts"]
    if info.get("files"):
        entry["files"] = info["files"]
    if info.get("urls"):
        entry["urls"] = info["urls"]
    if notes:
        entry["notes"] = notes
    return entry


def _send_confirmation(client: WebClient, channel_id: str, user_id: str,
                       preview: str, logger: Logger) -> None:
    """Send confirmation: ephemeral in channel, fall back to DM."""
    text = f"Queued for tasks: _{preview}_"
    try:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
    except Exception:
        # Ephemeral failed (bot not in channel, DM, etc.) — try DM
        try:
            dm = client.conversations_open(users=[user_id])
            dm_channel = dm["channel"]["id"]
            client.chat_postMessage(channel=dm_channel, text=text)
        except Exception:
            logger.info(f"Confirmation skipped for user {user_id}")


def _resolve_mentions(text: str, client) -> str:
    """Resolve Slack channel and user mentions in message text.

    <#C0AA0HMDW3W> → #channel-name (https://slack.com/archives/C0AA0HMDW3W)
    <@U02V91KU8> → @Real Name
    """
    import re

    def resolve_channel(match):
        cid = match.group(1)
        label = match.group(2)  # may be None
        if label:
            return f"#{label} (https://slack.com/archives/{cid})"
        try:
            resp = client.conversations_info(channel=cid)
            if resp.get("ok"):
                name = resp["channel"].get("name", cid)
                return f"#{name} (https://slack.com/archives/{cid})"
        except Exception:
            pass
        return f"#{cid} (https://slack.com/archives/{cid})"

    def resolve_user(match):
        uid = match.group(1)
        label = match.group(2)
        if label:
            return f"@{label}"
        try:
            resp = client.users_info(user=uid)
            if resp.get("ok"):
                name = resp["user"].get("real_name") or resp["user"].get("name", uid)
                return f"@{name}"
        except Exception:
            pass
        return f"@{uid}"

    text = re.sub(r'<#([A-Z0-9]+)(?:\|([^>]*))?>', resolve_channel, text)
    text = re.sub(r'<@([A-Z0-9]+)(?:\|([^>]*))?>', resolve_user, text)
    return text


def _resolve_slack_user(user_id: str, client) -> str:
    """Resolve a Slack user ID to 'Real Name (USERID)' format."""
    try:
        resp = client.users_info(user=user_id)
        if resp.get("ok"):
            user = resp["user"]
            name = user.get("real_name") or user.get("profile", {}).get("display_name") or user_id
            return f"{name} ({user_id})"
    except Exception:
        pass
    return user_id


def _trigger_extraction(entry: dict, logger: Logger,
                        slack_client: WebClient = None) -> None:
    """Write Spark Record to spark_queue and notify tasks agent.

    Runs in a background thread.
    """
    try:
        channel = entry.get("channel", "")
        channel_id = entry.get("channel_id", "")
        from_id = entry.get("from_id", "")
        # Resolve user ID to name
        if slack_client and from_id.startswith("U"):
            from_id = _resolve_slack_user(from_id, slack_client)
        text = entry.get("text", "")

        # Resolve channel mentions and user mentions
        if slack_client and text:
            text = _resolve_mentions(text, slack_client)
        link = entry.get("link", "")
        message_ts = entry.get("message_ts", "")
        notes = entry.get("notes", "")
        thread_ts = entry.get("thread_ts", "")

        urls = entry.get("urls", [])
        files = entry.get("files", [])

        # Build reference_id
        ref_id = f"slack-{channel_id}-{message_ts}"
        if thread_ts:
            ref_id += f"-t{thread_ts}"

        # Build Spark Record (Slack messages are short — inline full text, no fetch_hint)
        # Parse markers from user notes if present
        import re as _re
        marker_type = None
        task_hint = None
        if notes:
            # Check for [c] or [] marker
            m = _re.match(r'^\s*(?:[-*]\s*)?(\[\s*c?\s*[\]\[])\s+(.+)$', notes.strip(), _re.IGNORECASE)
            if m:
                marker_type = "explicit"
                task_hint = m.group(2).strip()
            # Check for > pointer
            elif _re.match(r'^\s*>\s+(.+)$', notes.strip()):
                marker_type = "pointer"
                task_hint = _re.match(r'^\s*>\s+(.+)$', notes.strip()).group(1).strip()
            else:
                # No marker — notes are implicit task intent
                marker_type = "implicit"
                task_hint = notes.strip()

        spark = {
            "spark_id": uuid.uuid4().hex[:8],
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_type": "slack",
            "origin": "user-indicated",
            "reference_id": ref_id,
            "source_text": text,
            "from_person": from_id,
            "location": f"#{channel}",
            "location_id": channel_id,
            "permalink": link,
            "related_urls": urls,
            "marker_type": marker_type,
            "task_hint": task_hint,
            "user_notes": notes if notes else None,
            "surrounding_context": None,
            "fetch_hint": None,
        }
        if thread_ts:
            spark["thread_ts"] = thread_ts
        if files:
            spark["files"] = [{"name": f["name"], "type": f["type"]} for f in files]

        # Cycle-1 Pattern 2 cutover (2026-04-26): write to pa_web.task_queue
        # instead of PATCHing the spark_queue Letta block. ref_id becomes
        # source_ref (UNIQUE), spark dict becomes payload JSONB.
        import psycopg
        from psycopg.types.json import Jsonb
        pg_password = os.getenv("POSTGRES_PASSWORD", "")
        pg_url = os.getenv(
            "PA_WEB_POSTGRES_URL",
            f"postgresql://postgres:{pg_password}@supabase-db:5432/postgres",
        )
        try:
            with psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO pa_web.task_queue (source, source_ref, payload)
                        VALUES ('slack', %s, %s)
                        ON CONFLICT (source, source_ref) DO NOTHING
                        RETURNING id
                        """,
                        (ref_id, Jsonb(spark)),
                    )
                    row = cur.fetchone()
            if row:
                logger.info(f"Task queue row written for {ref_id} (id={row[0]})")
            else:
                logger.info(f"Task queue dedup skip for {ref_id}")
        except Exception as e:
            logger.error(f"Task queue write failed for {ref_id}: {e}", exc_info=True)
            raise

        # Local-mode: notify the push receiver, which routes 'slack' →
        # pulse agent's warm subprocess. The agent applies its per-source
        # extraction recipe (task_extraction_process_slack.md) and writes
        # to pa_web.tasks via the `task` CLI. If the receiver is down,
        # the 15-min launchd backup poller (`scan_task_queue.sh`) will
        # eventually pick up the row.
        notify_prompt = (
            f"[Task Queue] New user-indicated slack spark, source_ref={ref_id}. "
            "Apply your per-source extraction recipe: claim from pa_web.task_queue "
            "(`task queue-claim --source slack --limit 5`), extract task(s), "
            "`task write` to pa_web.tasks, and `task queue-mark --status processed`. "
            "Origin should be 'user-indicated' since this came from the Slack shortcut."
        )
        push_body = {
            "source": PUSH_SOURCE,
            "source_ref": ref_id,
            "prompt": notify_prompt,
            "priority": "normal",
        }
        try:
            resp = requests.post(PUSH_RECEIVER_URL, json=push_body, timeout=10)
            if resp.status_code >= 400:
                logger.warning(
                    f"Push receiver returned {resp.status_code} for {ref_id} "
                    f"(row in task_queue; poller will retry): {resp.text[:200]}"
                )
            else:
                logger.info(f"Pulse agent notified via receiver for {ref_id}")
        except Exception as e:
            # Non-fatal — the row is in pa_web.task_queue, and the
            # launchd backup poller will sweep it within 15 min.
            logger.warning(
                f"Push receiver unreachable for {ref_id} "
                f"(falling back to poller): {e}"
            )

    except Exception as e:
        logger.error(f"Failed to trigger extraction: {e}", exc_info=True)


def send_to_tasks_callback(body: dict, ack: Ack, client: WebClient, logger: Logger):
    """Silent send — immediate confirmation, extraction in background."""
    ack()

    try:
        info = _extract_message_info(body, logger)
        logger.info(f"send_to_tasks triggered: channel={info['channel_id']}, text={info['text'][:50]}")

        # Immediate confirmation (before extraction)
        preview = info["text"][:100] + ("..." if len(info["text"]) > 100 else "")
        _send_confirmation(client, info["channel_id"], info["triggering_user_id"],
                           preview, logger)

        entry = _build_entry(info)
        threading.Thread(
            target=_trigger_extraction,
            args=(entry, logger, client),
            daemon=True,
        ).start()

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
            "urls": info.get("urls", []),
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
            "triggering_user_id": metadata.get("triggering_user_id", ""),
            "message_ts": metadata.get("message_ts", ""),
            "thread_ts": metadata.get("thread_ts", ""),
            "files": metadata.get("files", []),
            "urls": metadata.get("urls", []),
        }

        entry = _build_entry(info, notes=notes)

        triggering_user_id = body.get("user", {}).get("id", "")
        entry["triggering_user_id"] = triggering_user_id

        # Immediate confirmation
        preview = info["text"][:100] + ("..." if len(info["text"]) > 100 else "")
        _send_confirmation(client, info["channel_id"], triggering_user_id,
                           preview, logger)

        threading.Thread(
            target=_trigger_extraction,
            args=(entry, logger, client),
            daemon=True,
        ).start()

    except Exception as e:
        logger.error(f"send_to_tasks_view submission failed: {e}", exc_info=True)
