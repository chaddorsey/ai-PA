# listeners/messages/message_im.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient
import time

from ai.providers.letta_stream import LettaAPIStreaming

MAX_SLACK_MESSAGE_LENGTH = 3500  # Slack hard limit is 4000 characters; keep buffer for formatting
MAX_STREAM_PREVIEW_LENGTH = 1200
def _force_open_dm_channel(client: WebClient, user_id: str, logger: Logger) -> tuple[str | None, dict[str, object]]:
    debug: dict[str, object] = {}
    try:
        response = client.conversations_open(users=[user_id])
        data = getattr(response, "data", response)
        debug["force_open"] = data
        logger.error("force conversations.open response: %s", data)
        if response.get("ok"):
            channel_id = response.get("channel", {}).get("id")
            if channel_id:
                return channel_id, debug
    except Exception as exc:  # pragma: no cover - network failure
        logger.error("force conversations.open failed: %s", exc)
    return None, debug



def _resolve_dm_channel(
    client: WebClient,
    user_id: str | None,
    fallback_channel: str | None,
    logger: Logger,
):
    """Try to obtain the bot-writable DM channel for the given user."""

    channel_debug: dict[str, object] = {}

    if not user_id:
        logger.error("❌ Cannot resolve DM channel: missing user_id")
        return fallback_channel, channel_debug

    try:
        open_response = client.conversations_open(users=[user_id])
        open_data = getattr(open_response, "data", open_response)
        channel_debug["conversations_open"] = open_data
        ok = open_response.get("ok")
        channel_id = open_response.get("channel", {}).get("id") if ok else None
        logger.info("conversations.open response: %s", open_data)
        if not ok:
            logger.warning("conversations.open error response: %s", open_data)
        if channel_id:
            return channel_id, channel_debug
    except Exception as open_error:  # pragma: no cover - network failure
        logger.error(f"conversations.open failed: {open_error}")

    try:
        users_conversations = client.users_conversations(types="im", limit=100)
        conv_data = getattr(users_conversations, "data", users_conversations)
        channel_debug["users_conversations"] = conv_data
        logger.info("users.conversations response: %s", conv_data)
        channels = conv_data.get("channels") or []
        if not channels:
            logger.warning("users.conversations returned no channels for user %s", user_id)
        for channel in channels:
            if channel.get("user") == user_id:
                resolved = channel.get("id")
                logger.info(
                    "users.conversations matched user %s → channel %s",
                    user_id,
                    resolved,
                )
                if resolved:
                    return resolved, channel_debug
        else:
            logger.warning(
                "users.conversations could not resolve channel for user %s; channels=%s",
                user_id,
                channels,
            )
        logger.warning(
            "users.conversations did not contain DM channel for user %s", user_id
        )
    except Exception as conv_error:  # pragma: no cover - network failure
        logger.error(f"users.conversations failed: {conv_error}")

    if fallback_channel:
        logger.warning(
            "⚠️ Falling back to event channel '%s' due to channel resolution failure",
            fallback_channel,
        )
    else:
        logger.error("❌ No DM channel available after resolution attempts")
    return fallback_channel, channel_debug


def _handle_dm(event: dict, client: WebClient, logger: Logger):
    if event.get("channel_type") != "im" or event.get("subtype"):
        return

    # FORCE LOGGING AT START
    logger.error("=== DM HANDLER CALLED - ENHANCED VERSION ===")
    
    try:
        channel_id = event.get("channel")
        user_id = event.get("user")
        text = (event.get("text") or "").strip()
        
        # Enhanced debugging for channel issues
        logger.error(f"🔍 DM Event Debug - SHOULD BE VISIBLE:")
        logger.error(f"  Channel ID: '{channel_id}' (type: {type(channel_id)})")
        logger.error(f"  User ID: '{user_id}' (type: {type(user_id)})")
        logger.error(f"  Text: '{text}' (length: {len(text)})")
        logger.error(f"  Event keys: {list(event.keys())}")
        logger.error(f"  Full event: {event}")
    except Exception as debug_error:
        logger.error(f"❌ DEBUG ERROR: {debug_error}")
        logger.error(f"❌ Event type: {type(event)}")
        logger.error(f"❌ Event: {event}")
        return
    
    # Validate channel_id
    if not channel_id:
        logger.error(f"❌ No channel_id found in DM event!")
        return

    # Debug: Log the actual channel and user IDs received
    logger.info(
        "DM Event - Channel ID: '%s', User ID: '%s', Channel Type: '%s'",
        channel_id,
        user_id,
        event.get("channel_type"),
    )
    logger.info(f"Full DM event keys: {list(event.keys())}")

    working_channel, channel_debug = _resolve_dm_channel(
        client,
        user_id,
        channel_id,
        logger,
    )

    if working_channel == channel_id:
        forced_channel, forced_debug = _force_open_dm_channel(client, user_id, logger)
        channel_debug["forced_channel"] = forced_debug
        if forced_channel:
            logger.error("🔁 Forced channel replacement: %s -> %s", channel_id, forced_channel)
            working_channel = forced_channel
        else:
            logger.error("❌ Forced channel lookup failed; original channel remains %s", channel_id)

    if working_channel and working_channel != channel_id:
        logger.info("Using resolved DM channel %s instead of event channel %s", working_channel, channel_id)
        channel_id = working_channel

    logger.info("DM channel resolution debug: %s", channel_debug)

    if not working_channel:
        logger.error("❌ Unable to send DM reply because no channel could be resolved")
        return

    try:
        # Skip conversation history due to permissions issues - mirror slash command behaviour
        conversation_context = ""

        # Start with simple loading message - use client.chat_postMessage instead of say()
        try:
            waiting = client.chat_postMessage(channel=working_channel, text="...")
            logger.info(f"✅ Successfully posted loading message to channel {working_channel}")
        except Exception as loading_error:
            logger.error(f"❌ Failed to post loading message to {working_channel}: {loading_error}")
            return

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        # Use streaming instead of get_provider_response
        system = "You are a helpful Slack bot. Be concise and helpful."
        streamer = LettaAPIStreaming()
        chunks = []
        
        for i, chunk in enumerate(streamer.chat_stream(system, user_prompt)):
            if sum(len(part) for part in chunks) > MAX_STREAM_PREVIEW_LENGTH:
                logger.info("Stream preview exceeded limit; skipping further updates")
                break

            chunks.append(chunk)

            # Update message more frequently for smoother appearance
            if (i + 1) % 2 == 0 or len(chunks) == 1:
                partial = _truncate("".join(chunks))
                client.chat_update(channel=working_channel, ts=waiting["ts"], text=partial)
                time.sleep(0.3)  # Shorter delay for more responsive feel

        # Final update with chunking to satisfy Slack max length
        final_text = "".join(chunks).strip()
        final_chunks = list(_chunk_text(final_text)) or [""]

        client.chat_update(channel=working_channel, ts=waiting["ts"], text=final_chunks[0])

        for extra_chunk in final_chunks[1:]:
            client.chat_postMessage(channel=working_channel, text=extra_chunk)

    except Exception as e:
        logger.exception(e)
        try:
            # Use the working channel for error messages too
            error_channel = working_channel if 'working_channel' in locals() else channel_id
            client.chat_postMessage(channel=error_channel, text=f"Received an error from Bolty:\n{e}")
        except Exception:
            pass


def _truncate(message: str) -> str:
    if len(message) <= MAX_SLACK_MESSAGE_LENGTH:
        return message
    truncated = message[: MAX_SLACK_MESSAGE_LENGTH - 1].rstrip()
    return f"{truncated}…"


def _chunk_text(message: str):
    if not message:
        yield ""
        return
    for start in range(0, len(message), MAX_SLACK_MESSAGE_LENGTH):
        yield message[start : start + MAX_SLACK_MESSAGE_LENGTH]


def register(app: App):
    @app.event("message")
    def _on_dm(event, client, logger, say):
        _handle_dm(event, client, logger)
