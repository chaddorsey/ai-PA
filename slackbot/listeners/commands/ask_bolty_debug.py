# listeners/commands/ask_bolty_debug.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

from ai.providers.letta_stream import LettaAPIStreaming

def _handle_ask_bolty_debug(ack, respond, command: dict, client: WebClient, logger: Logger):
    # 1) Acknowledge fast so Slack doesn't time out
    ack()

    user_id = command["user_id"]
    channel_id = command["channel_id"]
    prompt = (command.get("text") or "").strip()

    if not prompt:
        respond("Usage: /ask-bolty <question>")
        return

    logger.info(f"DEBUG: Starting streaming for user {user_id} in channel {channel_id}")
    
    system = "You are a helpful Slack bot. Be concise and helpful."
    user_prompt = f"User <@{user_id}> says:\n{prompt}"

    # For slash commands, use ephemeral responses with streaming simulation
    try:
        logger.info("DEBUG: Starting streaming...")
        streamer = LettaAPIStreaming()
        chunks = []
        
        # Get the full response first
        for chunk in streamer.chat_stream(system, user_prompt):
            chunks.append(chunk)
            logger.info(f"DEBUG: Received chunk: {repr(chunk[:50])}...")
        
        # Send the complete response as ephemeral
        final_text = "".join(chunks).strip()
        logger.info(f"DEBUG: Sending complete response: {len(final_text)} chars")
        respond(final_text)
        logger.info("DEBUG: Streaming completed successfully")
        
    except Exception as e:
        logger.error(f"DEBUG: Error in streaming: {e}")
        respond(f"Sorry, an unexpected error occurred: `{e}`")

def register(app: App):
    @app.command("/ask-bolty")
    def _on_cmd(ack, respond, command, client, logger):
        _handle_ask_bolty_debug(ack, respond, command, client, logger)
