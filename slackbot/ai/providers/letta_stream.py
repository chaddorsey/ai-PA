import json
import logging
import os
import re
from typing import Generator, Iterable, List

import requests
import sseclient


RequestTimeout = tuple[float, float]


class LettaAPIStreaming:
    """Stream responses from Letta's SSE endpoint and yield text deltas."""

    _DEFAULT_TIMEOUT: RequestTimeout = (5.0, 120.0)

    def __init__(self, *, timeout: RequestTimeout | None = None, logger: logging.Logger | None = None) -> None:
        self.base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
        self.agent = os.environ["LETTA_AGENT_ID"]
        self.headers = {"Content-Type": "application/json"}
        self.timeout = timeout or self._DEFAULT_TIMEOUT
        self.logger = logger or logging.getLogger(__name__)
        self.last_message: str = ""

    def chat_stream(self, system: str | None, user: str) -> Generator[str, None, None]:
        """Yield response deltas from Letta as they arrive."""

        url = f"{self.base}/v1/agents/{self.agent}/messages/stream"
        prompt = f"{system}\n\n{user}" if system else user
        body = {"messages": [{"role": "user", "content": prompt}]}

        assembled: str = ""
        last_segment: str | None = None

        with requests.post(
            url,
            json=body,
            headers=self.headers,
            stream=True,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()

            client = sseclient.SSEClient(response)

            for event in client.events():
                if event.event != "message":
                    if event.data == "[DONE]":
                        break
                    continue

                try:
                    payload = json.loads(event.data)
                except json.JSONDecodeError:  # pragma: no cover - network anomaly
                    self.logger.debug("Skipping malformed SSE payload: %s", event.data)
                    continue

                segments = self._extract_segments(payload)
                if not segments:
                    continue

                for segment in segments:
                    cleaned = self._sanitize_segment(segment)
                    if not cleaned:
                        continue
                    normalized_current = self._normalize_for_compare(cleaned)
                    if normalized_current == self._normalize_for_compare(last_segment or ""):
                        continue
                    if assembled:
                        prefix = os.path.commonprefix([assembled, cleaned])
                        delta = cleaned[len(prefix) :]
                    else:
                        delta = cleaned

                    if not delta:
                        continue

                    assembled += delta
                    last_segment = cleaned
                    yield delta

            self.last_message = assembled.strip()

    # ------------------------------------------------------------------
    def _extract_segments(self, payload: object) -> List[str]:
        """Normalise any text found in an SSE payload into a list of segments."""

        if not isinstance(payload, dict):
            return []

        segments: List[str] = []

        # Common Letta keys we have observed: message_type, content, delta
        candidates: Iterable[object] = []

        if "content" in payload:
            candidates = (*candidates, payload["content"])
        if "delta" in payload:
            candidates = (*candidates, payload["delta"])
        if "text" in payload:
            candidates = (*candidates, payload["text"])

        # Fallback: iterate over dict values for any nested text containers
        if not candidates:
            candidates = payload.values()

        for value in candidates:
            segments.extend(self._normalise_text(value))

        return segments

    def _normalise_text(self, value: object) -> List[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            collected: List[str] = []
            for item in value:
                collected.extend(self._normalise_text(item))
            return collected
        if isinstance(value, dict):
            # Prefer explicit text keys but fall back to concatenating values
            if "text" in value:
                return self._normalise_text(value["text"])
            if "content" in value:
                return self._normalise_text(value["content"])
            if "value" in value:
                return self._normalise_text(value["value"])
            collected: List[str] = []
            for item in value.values():
                collected.extend(self._normalise_text(item))
            return collected
        return []

    _CONTROL_PREFIXES = (
        re.compile(r"^message-[^\s]+", re.IGNORECASE),
        re.compile(r"^hidden_reasoning_message", re.IGNORECASE),
        re.compile(r"^reasoning_message", re.IGNORECASE),
        re.compile(r"^step-[^\s]+", re.IGNORECASE),
        re.compile(r"^run-[^\s]+", re.IGNORECASE),
    )
    _TIMESTAMP_PREFIX = re.compile(r"^[0-9]{4}-[0-9T:+-]+")
    _UUID_PREFIX = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)

    def _sanitize_segment(self, text: str) -> str:
        if not text:
            return ""

        cleaned = text

        for pattern in self._CONTROL_PREFIXES:
            cleaned = pattern.sub("", cleaned)

        cleaned = self._TIMESTAMP_PREFIX.sub("", cleaned)
        cleaned = self._UUID_PREFIX.sub("", cleaned)

        cleaned = cleaned.replace("omitted", "")
        cleaned = cleaned.replace("stop_reason", "")
        cleaned = cleaned.replace("end_turn", "")
        cleaned = cleaned.replace("usage_statistics", "")

        return cleaned.strip()

    @staticmethod
    def _normalize_for_compare(text: str) -> str:
        if not text:
            return ""
        return " ".join(text.split()).lower()
