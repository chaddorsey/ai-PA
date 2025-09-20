# ai/providers/__init__.py
from .letta import LettaAPI

def available_providers():
    return ["letta"]

def get_provider(_name: str):
    return LettaAPI()

def get_provider_response(user_id: str, purpose: str, message: str, provider_name: str = "letta", model: str | None = None) -> str:
    system = "You are a helpful Slack bot."
    if purpose == "summarize":
        system = "Summarize the following Slack conversation for a newcomer. Be concise and neutral."
    return LettaAPI().chat(system, message, model=model)
