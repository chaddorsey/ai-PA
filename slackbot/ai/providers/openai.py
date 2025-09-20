# ai/providers/openai.py
import os
from openai import OpenAI

class OpenAIAPI:
    """
    Minimal provider used by get_provider_response(...).
    Exposes chat(system, user, model=None) and defaults to Chat Completions.
    """

    DEFAULT_MODEL = "gpt-4o-mini"  # works with chat.completions

    def __init__(self):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=key)

    def chat(self, system: str | None, user: str, model: str | None = None) -> str:
        m = model or self.DEFAULT_MODEL
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        # Use Chat Completions; keep it simple and robust
        resp = self.client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
