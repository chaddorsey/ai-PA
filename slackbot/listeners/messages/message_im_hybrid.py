# listeners/messages/message_im.py
import os
import threading
import time
from logging import Logger
from typing import List, Optional, Tuple

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai.providers.letta_stream import LettaAPIStreaming
from ai.conversation_helper import get_conversation_for_user
from listeners.messages.status_messages import get_status_for_tool, get_default_status

MAX_SLACK_MESSAGE_LENGTH = 3500  # Slack hard limit is 4000 characters; keep buffer for formatting
MAX_STREAM_PREVIEW_LENGTH = 1200

_STREAM_FLAG_VALUES = {"1", "true", "yes", "on"}


def _is_streaming_enabled() -> bool:
    return os.getenv("ENABLE_SLACK_STREAMING", "false").strip().lower() in _STREAM_FLAG_VALUES


def _set_assistant_status(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    thread_ts: str,
    status: str,
    loading_messages: Optional[List[str]] = None,
) -> None:
    try:
        logger.error(f"🚀 CALLING assistant_threads_setStatus: status={status}, channel={channel_id}, thread={thread_ts}, messages={loading_messages}")
        result = client.assistant_threads_setStatus(
            channel_id=channel_id,
            thread_ts=thread_ts,
            status=status,
            loading_messages=loading_messages,
        )
        logger.error(f"✅ assistant_threads_setStatus SUCCESS: {result}")
    except Exception as error:  # pragma: no cover - non-critical feedback
        logger.error(
            f"❌ assistant_threads_setStatus FAILED (status={status}, channel={channel_id}, ts={thread_ts}): {error}",
            exc_info=True,
        )


def _show_typing_indicator(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    stop_event: threading.Event,
) -> None:
    """Show native typing indicator, refreshing every 2 seconds until stopped."""
    while not stop_event.is_set():
        try:
            client.chat_typingIndicator(channel=channel_id)
            logger.debug("Typing indicator sent for channel %s", channel_id)
        except Exception as error:
            logger.debug("typing indicator failed: %s", error)
        
        # Wait 2 seconds or until stopped
        stop_event.wait(timeout=2.0)


def _should_use_streaming(logger: Logger) -> bool:
    flag = _is_streaming_enabled()
    if not flag:
        return False
    if os.getenv("DISABLE_ASSISTANT_STREAMING", "false").strip().lower() in _STREAM_FLAG_VALUES:
        logger.info("Streaming disabled via DISABLE_ASSISTANT_STREAMING flag")
        return False
    return True


def _stream_dm_reply(
    client: WebClient,
    logger: Logger,
    channel_id: str,
    thread_ts: str,
    system_prompt: str,
    user_prompt: str,
    *,
    recipient_user_id: Optional[str] = None,
    recipient_team_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """Attempt to stream a Letta response using Slack's chat.stream helpers."""

    streamer = LettaAPIStreaming(logger=logger)
    slack_stream = None
    collected: List[str] = []

    try:
        stream_kwargs = {
            "channel": channel_id,
            "thread_ts": thread_ts,
            "buffer_size": 80,
        }
        if recipient_user_id:
            stream_kwargs["recipient_user_id"] = recipient_user_id
        if recipient_team_id:
            stream_kwargs["recipient_team_id"] = recipient_team_id
        
        logger.error(f"🚀 chat.stream kwargs: {stream_kwargs}")
        slack_stream = client.chat_stream(**stream_kwargs)

        for chunk in streamer.chat_stream(system_prompt, user_prompt):
            if not chunk:
                continue
            collected.append(chunk)
            try:
                slack_stream.append(markdown_text=chunk)
            except SlackApiError as append_error:  # pragma: no cover - Slack API failure
                logger.error(
                    "Slack append stream failed for channel=%s ts=%s: %s",
                    channel_id,
                    thread_ts,
                    append_error,
                    exc_info=True,
                )
                raise

        final_text = (streamer.last_message or "".join(collected)).strip()
        slack_stream.stop(markdown_text=final_text or " ")
        return True, final_text

    except Exception as exc:  # pragma: no cover - network/runtime issues
        logger.error("Streaming DM response failed", exc_info=True)
        fallback_text = (streamer.last_message or "".join(collected)).strip()

        if slack_stream is not None:
            try:
                slack_stream.stop(markdown_text=fallback_text or " ")
                return True, fallback_text
            except Exception:  # pragma: no cover - Slack closure failure
                logger.debug("Unable to close Slack stream cleanly", exc_info=True)

        return False, fallback_text
def _force_open_dm_channel(client: WebClient, user_id: str, logger: Logger) -> tuple[str | None, dict[str, object]]:
    debug: dict[str, object] = {}
    try:
        response = client.conversations_open(users=[user_id])
        data = getattr(response, "data", response)
        debug["force_open"] = data
        logger.debug("force conversations.open response: %s", data)
        if response.get("ok"):
            channel_id = response.get("channel", {}).get("id")
            if channel_id:
                return channel_id, debug
    except Exception as exc:  # pragma: no cover - network failure
        logger.debug("force conversations.open failed: %s", exc)
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
    
    # Ignore messages sent BY the bot itself (to prevent echo loops)
    sender_user_id = event.get("user")
    if sender_user_id:
        try:
            bot_user_id = client.auth_test().get("user_id")
            if sender_user_id == bot_user_id:
                logger.info("Ignoring DM sent by bot itself (user=%s)", sender_user_id)
                return
        except Exception as auth_err:
            logger.warning("Unable to check bot user ID: %s", auth_err)

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()
    
    logger.debug("DM received from user %s in channel %s", user_id, channel_id)
    
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
            logger.debug("Forced channel replacement: %s -> %s", channel_id, forced_channel)
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

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        system_prompt = "You are a helpful Slack bot. Be concise and helpful."
        streaming_enabled = _should_use_streaming(logger)
        
        # Use the user's message timestamp as the thread_ts for assistant status
        user_message_ts = event.get("ts")
        
        # Set initial default status
        if streaming_enabled and user_message_ts:
            default_status = get_default_status()
            _set_assistant_status(
                client,
                logger,
                working_channel,
                user_message_ts,
                status=default_status["status"],
                loading_messages=default_status["loading_messages"],
            )

        # Get or create conversation for this user (enables per-user context isolation)
        # Falls back to None (legacy agent-level messaging) if lookup/creation fails
        conversation_id = None
        try:
            conversation_id = get_conversation_for_user(user_id, logger=logger)
            if conversation_id:
                logger.info(f"Using Letta conversation: {conversation_id} for user {user_id}")
            else:
                logger.info(f"Using legacy agent messaging for user {user_id} (no conversation)")
        except Exception as conv_err:
            logger.warning(f"Conversation lookup failed, using legacy messaging: {conv_err}")

        # Get full response from Letta with event detection
        streamer = LettaAPIStreaming(logger=logger, conversation_id=conversation_id)
        text_chunks = []
        
        for event in streamer.chat_stream_with_events(system_prompt, user_prompt):
            event_type = event.get("type")
            logger.error(f"📨 Event received: type={event_type}, keys={list(event.keys())}")
            
            if event_type == "tool_call":
                # Update status based on tool call
                tool_name = event.get("tool_name", "")
                logger.error(f"🔧 TOOL CALL EVENT: {tool_name}")
                if streaming_enabled and user_message_ts and tool_name:
                    logger.error(f"🔄 Updating status for tool: {tool_name}")
                    tool_status = get_status_for_tool(tool_name)
                    logger.error(f"📝 Status config: {tool_status}")
                    _set_assistant_status(
                        client,
                        logger,
                        working_channel,
                        user_message_ts,
                        status=tool_status["status"],
                        loading_messages=tool_status["loading_messages"],
                    )
            elif event_type == "text":
                # Accumulate text
                text_chunks.append(event.get("content", ""))

        final_text = (streamer.last_message or "".join(text_chunks)).strip()
        final_chunks = list(_chunk_text(final_text)) or [""]

        # Post the response in the same channel (not threaded)
        post_response = client.chat_postMessage(
            channel=working_channel, 
            text=final_chunks[0]
        )
        reply_ts = post_response.get("ts")

        # Post any overflow chunks in the same channel
        for extra_chunk in final_chunks[1:]:
            client.chat_postMessage(
                channel=working_channel, 
                text=extra_chunk
            )
        
        # Set thread title if enabled
        if streaming_enabled and user_message_ts:
            try:
                thread_title = (text or "Conversation")[:50]
                client.assistant_threads_setTitle(
                    channel_id=working_channel,
                    thread_ts=user_message_ts,
                    title=thread_title,
                )
            except Exception as title_err:
                logger.debug("Could not set thread title: %s", title_err)

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
