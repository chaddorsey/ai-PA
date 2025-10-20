# listeners/events/app_mentioned.py
from logging import Logger

from slack_bolt import App, Say
from slack_sdk import WebClient

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.messages.message_im_hybrid import (
    _is_streaming_enabled,
    _set_assistant_status,
)
from listeners.messages.status_messages import get_status_for_tool, get_default_status
from listeners.listener_utils.listener_constants import MENTION_WITHOUT_TEXT
from listeners.listener_utils.parse_conversation import parse_conversation


def _handle_app_mention(event: dict, client: WebClient, logger: Logger, say: Say):
    logger.info(f"DEBUG: @-mention handler called with event: {event}")
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()
    logger.info(f"DEBUG: Processing @-mention from user {user_id} in channel {channel_id}: '{text[:50]}...'")

    try:
        # Collect recent context
        if thread_ts:
            history = client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=10
            )["messages"]
        else:
            history = client.conversations_history(channel=channel_id, limit=10)["messages"]
            thread_ts = event["ts"]

        conversation_context = parse_conversation(history[:-1])  # exclude current mention

        if not text:
            # No prompt provided — just reply with a helpful hint
            say(text=MENTION_WITHOUT_TEXT)
            return

        # Build a single prompt that includes the short context
        user_prompt = (
            (f"Conversation so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text}"

        system = "You are a helpful Slack bot. Be concise and helpful."
        streaming_enabled = _is_streaming_enabled()
        event_ts = event.get("ts")

        # Determine the thread_ts to use for assistant status
        # If already in a thread, use that thread_ts; otherwise use the mention event's ts
        status_thread_ts = thread_ts if thread_ts else event_ts

        # Set initial default status
        if streaming_enabled and status_thread_ts:
            default_status = get_default_status()
            _set_assistant_status(
                client,
                logger,
                channel_id,
                status_thread_ts,
                status=default_status["status"],
                loading_messages=default_status["loading_messages"],
            )

        # Get full response from Letta with event detection
        streamer = LettaAPIStreaming(logger=logger)
        text_chunks = []
        
        for event in streamer.chat_stream_with_events(system, user_prompt):
            event_type = event.get("type")
            logger.error(f"📨 Mention Event: type={event_type}, keys={list(event.keys())}")
            
            if event_type == "tool_call":
                # Update status based on tool call
                tool_name = event.get("tool_name", "")
                logger.error(f"🔧 MENTION TOOL CALL: {tool_name}")
                if streaming_enabled and status_thread_ts and tool_name:
                    logger.error(f"🔄 Updating mention status for: {tool_name}")
                    tool_status = get_status_for_tool(tool_name)
                    _set_assistant_status(
                        client,
                        logger,
                        channel_id,
                        status_thread_ts,
                        status=tool_status["status"],
                        loading_messages=tool_status["loading_messages"],
                    )
            elif event_type == "text":
                # Accumulate text
                text_chunks.append(event.get("content", ""))

        full_response = (streamer.last_message or "".join(text_chunks)).strip()
        
        # Post reply - threaded if in a thread, inline otherwise
        reply_kwargs = {"channel": channel_id, "text": full_response}
        if thread_ts and thread_ts != event_ts:
            reply_kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**reply_kwargs)
        
        # Clear assistant status if it was set
        if streaming_enabled and status_thread_ts:
            _set_assistant_status(
                client,
                logger,
                channel_id,
                status_thread_ts,
                status="",
            )

    except Exception as e:
        logger.exception(e)
        # If waiting wasn't created for some reason, just post a fresh error message
        try:
            client.chat_postMessage(
                channel=channel_id,
                text=f"Received an error from Bolty:\n{e}",
            )
        except Exception:
            pass

def app_mentioned_callback(client: WebClient, event: dict, logger: Logger, say: Say):
    _handle_app_mention(event, client, logger, say)

def register(app: App):
    @app.event("app_mention")
    def _on_mention(event, client, logger, say):
        _handle_app_mention(event, client, logger, say)
