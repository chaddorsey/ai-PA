# listeners/commands/ask_bolty.py
from logging import Logger
from slack_bolt import App
from slack_sdk import WebClient

from ai.providers import get_provider_response


def _handle_ask_bolty(ack, respond, command: dict, client: WebClient, logger: Logger):
    ack()
    user_id = command["user_id"]
    prompt = (command.get("text") or "").strip()

    if not prompt:
        respond("Usage: /ask-bolty <question>")
        return

    try:
        # For slash commands we don't fetch channel context; just answer the prompt
        answer = get_provider_response(
            user_id=user_id,
            purpose="chat",
            message=f"User <@{user_id}> says:\n{prompt}",
            provider_name="openai",
        )
        respond(answer)  # ephemeral to the caller
    except Exception as e:
        logger.exception(e)
        respond(f"Received an error from Bolty:\n{e}")


def register(app: App):
    @app.command("/ask-bolty")
    def _on_cmd(ack, respond, command, client, logger):
        _handle_ask_bolty(ack, respond, command, client, logger)
