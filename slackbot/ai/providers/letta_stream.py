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
            full_content = ""
            
            for event in client.events():
                if event.event == "message":
                    try:
                        import json
                        data = json.loads(event.data)
                        if data.get("message_type") == "assistant_message" and "content" in data:
                            content = data["content"]
                            if isinstance(content, str):
                                full_content = content
                            elif isinstance(content, list):
                                # Handle segmented content
                                full_content = ""
                                for segment in content:
                                    if isinstance(segment, str):
                                        full_content += segment
                                    elif isinstance(segment, dict) and "text" in segment:
                                        full_content += segment["text"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Skip malformed events
                        continue
                elif event.data == "[DONE]":
                    break
            
            # Now artificially stream the content in chunks
            if full_content:
                import time
                words = full_content.split()
                chunk_size = 3  # Words per chunk
                
                for i in range(0, len(words), chunk_size):
                    chunk_words = words[i:i + chunk_size]
                    chunk = " ".join(chunk_words)
                    if i + chunk_size < len(words):
                        chunk += " "  # Add space if not the last chunk
                    yield chunk
                    time.sleep(0.1)  # Small delay between chunks
