import os, requests, sseclient

class LettaAPIStreaming:
    def __init__(self):
        self.base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
        self.agent = os.environ["LETTA_AGENT_ID"]
        self.headers = {"Content-Type": "application/json"}

    def chat_stream(self, system: str | None, user: str):
        url = f"{self.base}/v1/agents/{self.agent}/messages/stream"
        prompt = f"{system}\n\n{user}" if system else user
        body = {"messages": [{"role": "user", "content": prompt}]}

        with requests.post(url, json=body, headers=self.headers, stream=True) as r:
            r.raise_for_status()
            client = sseclient.SSEClient(r)
            for event in client.events():
                if event.event == "message":
                    try:
                        import json
                        data = json.loads(event.data)
                        if data.get("message_type") == "assistant_message" and "content" in data:
                            content = data["content"]
                            if isinstance(content, str):
                                yield content
                            elif isinstance(content, list):
                                # Handle segmented content
                                for segment in content:
                                    if isinstance(segment, str):
                                        yield segment
                                    elif isinstance(segment, dict) and "text" in segment:
                                        yield segment["text"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Skip malformed events
                        continue
                elif event.data == "[DONE]":
                    break
