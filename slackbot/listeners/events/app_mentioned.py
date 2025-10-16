# listeners/events/app_mentioned.py
import time
import random
import threading
from logging import Logger
from typing import List

from slack_bolt import App, Say
from slack_sdk import WebClient

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.messages.message_im_hybrid import (
    _is_streaming_enabled,
    _set_assistant_status,
    _stream_dm_reply,
)
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

        if streaming_enabled:
            logger.info("Streaming enabled for app_mention; attempting Slack chat.stream")
            placeholder = client.chat_postMessage(
                channel=channel_id,
                text="…",
                thread_ts=thread_ts,
            )

            _set_assistant_status(
                client,
                logger,
                channel_id,
                placeholder["ts"],
                status="thinking…",
                loading_messages=[
                    "Gathering channel history…",
                    "Assembling a helpful reply…",
                    "Checking references…",
                ],
            )

            success, streamed_text = _stream_dm_reply(
                client,
                logger,
                channel_id,
                placeholder["ts"],
                system,
                user_prompt,
            )

            if success:
                _set_assistant_status(
                    client,
                    logger,
                    channel_id,
                    placeholder["ts"],
                    status="done",
                )
                return

            logger.warning(
                "Streaming mention response failed; falling back to legacy animation"
            )
            waiting = placeholder
            fallback_text = streamed_text
        else:
            fallback_text = None

        if "waiting" not in locals():
            waiting = client.chat_postMessage(channel=channel_id, text="...", thread_ts=thread_ts)

        streamer = LettaAPIStreaming(logger=logger)
        response_ready = threading.Event()
        collected_chunks: List[str] = []

        def get_response():
            try:
                for chunk in streamer.chat_stream(system, user_prompt):
                    collected_chunks.append(chunk)
            finally:
                response_ready.set()

        response_thread = threading.Thread(target=get_response)
        response_thread.start()

        dot_count = 3

        while not response_ready.is_set() and dot_count < 7:
            time.sleep(1.0)
            if not response_ready.is_set():
                dot_count += 1
                client.chat_update(channel=channel_id, ts=waiting["ts"], text="." * dot_count)

        while not response_ready.is_set():
            dot_count = 1
            client.chat_update(channel=channel_id, ts=waiting["ts"], text=".")
            time.sleep(1.0)

            if response_ready.is_set():
                break

            while not response_ready.is_set() and dot_count < 7:
                time.sleep(1.0)
                if not response_ready.is_set():
                    dot_count += 1
                    client.chat_update(channel=channel_id, ts=waiting["ts"], text="." * dot_count)

        response_thread.join()

        full_response = fallback_text or streamer.last_message or "".join(collected_chunks).strip()
        client.chat_update(channel=channel_id, ts=waiting["ts"], text=full_response)

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
