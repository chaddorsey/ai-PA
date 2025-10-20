# listeners/commands/ask_bolty_streaming.py
import os
from logging import Logger
from typing import List

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.messages.message_im_hybrid import (
    _is_streaming_enabled,
    _stream_dm_reply,
    _set_assistant_status,
)


def _handle_ask_bolty_streaming(ack, respond, command: dict, client: WebClient, logger: Logger):
    # 1) Acknowledge fast so Slack doesn't time out
    ack()

    user_id = command["user_id"]
    channel_id = command["channel_id"]
    prompt = (command.get("text") or "").strip()

    if not prompt:
        respond("Usage: /ask-bolty <question>")
        return

    system = "You are a helpful Slack bot. Be concise and helpful."
    user_prompt = f"User <@{user_id}> says:\n{prompt}"

    streaming_enabled = _is_streaming_enabled()

    if streaming_enabled:
        logger.info("Streaming flag enabled for /ask-bolty; using chat.stream path")
        try:
            posted = client.chat_postMessage(channel=channel_id, text="…")
        except SlackApiError as post_error:
            logger.exception("Unable to post initial message for streaming: %s", post_error)
            respond(f"Sorry, I couldn't start streaming: `{post_error.response['error']}`")
            return

        thread_ts = posted["ts"]
        _set_assistant_status(
            client,
            logger,
            channel_id,
            thread_ts,
            status="thinking…",
            loading_messages=[
                "Gathering context…",
                "Checking notes…",
                "Consulting sources…",
            ],
        )

        success, response_text = _stream_dm_reply(
            client,
            logger,
            channel_id,
            thread_ts,
            system,
            user_prompt,
        )

        if success:
            logger.info("Streaming response completed for /ask-bolty")
            _set_assistant_status(
                client,
                logger,
                channel_id,
                thread_ts,
                status="",
            )
            return

        logger.warning("Streaming failed for /ask-bolty; falling back to non-streaming response")
        final_text = response_text
    else:
        respond("Got it — generating a reply…")
        logger.info("Streaming disabled; collecting full response for /ask-bolty")

        streamer = LettaAPIStreaming(logger=logger)
        chunks: List[str] = []
        try:
            for chunk in streamer.chat_stream(system, user_prompt):
                chunks.append(chunk)
            final_text = (streamer.last_message or "".join(chunks)).strip()
        except Exception as exc:
            logger.exception("Slash command streaming simulation failed: %s", exc)
            respond(f"Sorry, I encountered an error: `{exc}`")
            return

    respond(final_text or "(No response received)")


def register(app: App):
    @app.command("/ask-bolty")
    def _on_cmd(ack, respond, command, client, logger):
        _handle_ask_bolty_streaming(ack, respond, command, client, logger)