from logging import Logger
from slack_bolt import App
from slack_bolt import Ack, Complete, Fail
from slack_sdk import WebClient
from ai.providers import get_provider_response

SUMMARIZE_PURPOSE = "summarize"

def register(app: App):
    @app.event("function_executed")
    def handle(ev, logger: Logger, client: WebClient, ack: Ack, complete: Complete, fail: Fail):
        # function_executed delivers multiple function events; check the function id or callback_id if you set one
        ack()
        try:
            inputs = ev.get("inputs") or {}
            user_ctx = inputs.get("user_context")
            channel_id = inputs.get("channel_id")
            history = client.conversations_history(channel=channel_id, limit=10)["messages"]
            # flatten history into a plain text transcript
            lines = []
            for m in reversed(history):
                if "text" in m:
                    lines.append(m["text"])
            transcript = "\n".join(lines)
            provider = "openai"  # or load a default / admin choice; could also read user_ctx.id from your state store
            summary = get_provider_response(user_ctx["id"], SUMMARIZE_PURPOSE, transcript, provider)
            complete({"user_context": user_ctx, "response": summary})
        except Exception as e:
            logger.exception(e)
            fail(str(e))
