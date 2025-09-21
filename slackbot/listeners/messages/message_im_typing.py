# listeners/messages/message_im_typing.py
from logging import Logger
from slack_bolt import App, Say
from slack_sdk import WebClient
import time
import random

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.listener_utils.listener_constants import DEFAULT_LOADING_TEXT
from listeners.listener_utils.parse_conversation import parse_conversation


def _handle_dm_typing(event: dict, client: WebClient, logger: Logger, say: Say):
    if event.get("channel_type") != "im" or event.get("subtype"):
        return

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()

    try:
        history = client.conversations_history(channel=channel_id, limit=10)["messages"]
        conversation_context = parse_conversation(history[:-1])

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        # Get the full response first
        system = "You are a helpful Slack bot. Be concise and helpful."
        streamer = LettaAPIStreaming()
        full_response = "".join(streamer.chat_stream(system, user_prompt)).strip()
        
        # Simulate typing by showing dots that grow and shrink
        typing_phases = ["...", "....", ".....", "......", "....."]
        waiting = None
        
        # Show typing animation for a few seconds
        for i, phase in enumerate(typing_phases * 3):  # Repeat 3 times
            if waiting:
                client.chat_update(channel=channel_id, ts=waiting["ts"], text=phase)
            else:
                waiting = client.chat_postMessage(channel=channel_id, text=phase)
            time.sleep(0.4)
        
        # Now reveal the actual response word by word
        words = full_response.split()
        current_text = ""
        
        for i, word in enumerate(words):
            current_text += word + " "
            client.chat_update(channel=channel_id, ts=waiting["ts"], text=current_text.strip())
            
            # Variable delay based on word length (more natural)
            delay = 0.1 + (len(word) * 0.02) + random.uniform(0, 0.1)
            time.sleep(delay)

    except Exception as e:
        logger.exception(e)
        try:
            client.chat_postMessage(channel=channel_id, text=f"Received an error from Bolty:\n{e}")
        except Exception:
            pass


def register(app: App):
    @app.event("message")
    def _on_dm(event, client, logger, say):
        _handle_dm_typing(event, client, logger, say)
