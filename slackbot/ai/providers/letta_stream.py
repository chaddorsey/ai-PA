import os, requests, sseclient

class LettaAPIStreaming:
    def __init__(self):
        self.base = os.getenv("LETTA_BASE_URL", "http://192.168.7.114:8283").rstrip("/")
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
                if event.event == "message_delta":
                    yield event.data  # partial text chunk
                elif event.event == "message_completed":
                    break
