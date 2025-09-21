# listeners/commands/ask_bolty_streaming.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time
import threading
import random
import re

from ai.providers.letta_stream import LettaAPIStreaming


def _handle_ask_bolty_streaming(ack, respond, command: dict, client: WebClient, logger: Logger):
    # 1) Acknowledge fast so Slack doesn't time out
    ack()

    user_id = command["user_id"]
    channel_id = command["channel_id"]
    prompt = (command.get("text") or "").strip()

    if not prompt:
        respond("Usage: /ask-bolty <question>")
        return

    # Let the user know we're processing
    respond("Got it — streaming a reply...")

    system = "You are a helpful Slack bot. Be concise and helpful."
    user_prompt = f"User <@{user_id}> says:\n{prompt}"

    # For now, use ephemeral response with streaming simulation until scopes are updated
    try:
        logger.info("Starting streaming simulation for slash command")
        streamer = LettaAPIStreaming()
        chunks = []
        
        # Get the full response first
        for chunk in streamer.chat_stream(system, user_prompt):
            chunks.append(chunk)
            logger.info(f"Received chunk: {repr(chunk[:50])}...")
        
        # Send the complete response as ephemeral
        final_text = "".join(chunks).strip()
        logger.info(f"Sending complete response: {len(final_text)} chars")
        respond(final_text)
        logger.info("Streaming simulation completed successfully")
        
    except Exception as e:
        logger.exception(f"Error in streaming simulation: {e}")
        respond(f"Sorry, I encountered an error: `{e}`")


def register(app: App):
    @app.command("/ask-bolty")
    def _on_cmd(ack, respond, command, client, logger):
        _handle_ask_bolty_streaming(ack, respond, command, client, logger)