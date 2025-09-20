# ai/providers/__init__.py  — OpenAI-only, explicit
import os
from .openai import OpenAIAPI  # make sure this class exists in ai/providers/openai.py

def available_providers():
    return ["openai"] if os.getenv("OPENAI_API_KEY") else []

def get_provider(_name: str):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAIAPI()

def get_provider_response(user_id: str, purpose: str, message: str, provider_name: str = "openai", model: str | None = None) -> str:
    system = "You are a helpful Slack bot."
    if purpose == "summarize":
        system = "Summarize the following Slack conversation for a newcomer. Be concise and neutral."
    return OpenAIAPI().chat(system, message, model=model)
