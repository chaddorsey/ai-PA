# listeners/messages/message_im.py
from logging import Logger
from slack_bolt import App, Say
from slack_sdk import WebClient
import time

from ai.providers.letta_stream import LettaAPIStreaming
from listeners.listener_utils.listener_constants import DEFAULT_LOADING_TEXT
from listeners.listener_utils.parse_conversation import parse_conversation


def _handle_dm(event: dict, client: WebClient, logger: Logger, say: Say):
    if event.get("channel_type") != "im" or event.get("subtype"):
        return

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()

    try:
        history = client.conversations_history(channel=channel_id, limit=10)["messages"]
        conversation_context = parse_conversation(history[:-1])

        # Try to show typing indicator (may not work in all clients)
        try:
            waiting = client.chat_postMessage(channel=channel_id, text="", type="typing")
        except:
            # Fallback to dots if typing type not supported
            waiting = say(text="...")

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        # Use streaming instead of get_provider_response
        system = "You are a helpful Slack bot. Be concise and helpful."
        streamer = LettaAPIStreaming()
        chunks = []
        
        for i, chunk in enumerate(streamer.chat_stream(system, user_prompt)):
            chunks.append(chunk)
            
            # Update message more frequently for smoother appearance
            if (i + 1) % 2 == 0 or len(chunks) == 1:
                partial = "".join(chunks)
                client.chat_update(channel=channel_id, ts=waiting["ts"], text=partial)
                time.sleep(0.3)  # Shorter delay for more responsive feel
        
        # Final update
        final_text = "".join(chunks).strip()
        client.chat_update(channel=channel_id, ts=waiting["ts"], text=final_text)

    except Exception as e:
        logger.exception(e)
        try:
            client.chat_postMessage(channel=channel_id, text=f"Received an error from Bolty:\n{e}")
        except Exception:
            pass


def register(app: App):
    @app.event("message")
    def _on_dm(event, client, logger, say):
        _handle_dm(event, client, logger, say)
