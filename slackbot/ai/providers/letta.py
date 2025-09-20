# ai/providers/letta.py
import os, requests
from typing import Optional

class LettaAPI:
    def __init__(self):
        base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
        agent = os.getenv("LETTA_AGENT_ID", "").strip()
        if not agent:
            raise RuntimeError("LETTA_AGENT_ID is not set")
        self.base = base
        self.agent = agent
        # no auth per your setup; add a token header here later if needed
        self.headers = {"Content-Type": "application/json"}

    def chat(self, system: Optional[str], user: str, model: Optional[str] = None) -> str:
        """
        Non-streaming message → reply.
        Endpoint per docs: POST /v1/agents/:agent_id/messages
        Body uses 'messages' list with role/content pairs.
        """
        # Optional: prepend system text to steer the agent for this call
        prompt = f"{system}\n\n{user}" if system else user

        url = f"{self.base}/v1/agents/{self.agent}/messages"
        body = {
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        r = requests.post(url, json=body, headers=self.headers, timeout=60)
        r.raise_for_status()
        data = r.json()

        # The response is a list of messages (reasoning, tool calls, assistant, etc.)
        # Return the last assistant text we can find.
        msgs = data.get("messages", [])
        # prefer message_type == "assistant_message", then fall back to role == "assistant"
        text = None
        for m in reversed(msgs):
            if m.get("message_type") == "assistant_message" or m.get("role") == "assistant":
                text = m.get("content")
                if isinstance(text, list):
                    # some responses may be segmented; join plain text parts if needed
                    text = "".join([t if isinstance(t, str) else t.get("text", "") for t in text])
                break

        return text or "(no content)"
