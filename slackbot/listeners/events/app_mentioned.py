# listeners/events/app_mentioned.py
from logging import Logger
from slack_bolt import App, Say
from slack_sdk import WebClient

from ai.providers import get_provider_response
from ..listener_utils.listener_constants import (
    DEFAULT_LOADING_TEXT,
    MENTION_WITHOUT_TEXT,
)
from ..listener_utils.parse_conversation import parse_conversation


def _handle_app_mention(event: dict, client: WebClient, logger: Logger, say: Say):
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts")
    user_id = event.get("user")
    text = (event.get("text") or "").strip()

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
            say(text=MENTION_WITHOUT_TEXT, thread_ts=thread_ts)
            return

        # Post a loading message we can later update
        waiting = say(text=DEFAULT_LOADING_TEXT, thread_ts=thread_ts)

        # Build a single prompt that includes the short context (we’re OpenAI-only now)
        user_prompt = (
            (f"Conversation so far:\n{conversation_context}\n\n") if conversation_context else ""
        ) + f"User <@{user_id}> says:\n{text}"

        answer = get_provider_response(
            user_id=user_id,
            purpose="chat",
            message=user_prompt,
            provider_name="openai",
        )

        client.chat_update(channel=channel_id, ts=waiting["ts"], text=answer)

    except Exception as e:
        logger.exception(e)
        # If waiting wasn't created for some reason, just post a fresh error message
        try:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts or event.get("ts"),
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
