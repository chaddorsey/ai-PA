# listeners/messages/message_im.py
from logging import Logger
from slack_bolt import App, Say
from slack_sdk import WebClient

from ai.providers import get_provider_response
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

        waiting = say(text=DEFAULT_LOADING_TEXT)

        user_prompt = (
            (f"DM so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text or 'Hello'}"

        answer = get_provider_response(
            user_id=user_id,
            purpose="chat",
            message=user_prompt,
            provider_name="openai",
        )

        client.chat_update(channel=channel_id, ts=waiting["ts"], text=answer)

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
