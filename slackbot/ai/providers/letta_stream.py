import json
import logging
import os
import re
from typing import Dict, Generator, Iterable, List, Optional, Tuple, Union

import requests
import sseclient


RequestTimeout = Tuple[float, float]
StreamEvent = Dict[str, Union[str, Dict]]


class LettaAPIStreaming:
    """Stream responses from Letta's SSE endpoint and yield text deltas and events.

    Supports both agent-level messaging (legacy) and conversation-level messaging
    (multi-user isolation). When conversation_id is provided, uses the Conversations
    API which provides per-user context isolation.
    """

    _DEFAULT_TIMEOUT: RequestTimeout = (5.0, 120.0)

    # Default scheduler agent ID - can be overridden via LETTA_SCHEDULER_AGENT_ID env var
    _DEFAULT_SCHEDULER_AGENT_ID = "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"

    def __init__(
        self,
        *,
        timeout: Optional[RequestTimeout] = None,
        logger: Optional[logging.Logger] = None,
        conversation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        self.base = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
        # Use provided agent_id, or env var, or default scheduler agent
        self.agent = agent_id or os.getenv(
            "LETTA_SCHEDULER_AGENT_ID",
            os.getenv("LETTA_AGENT_ID", self._DEFAULT_SCHEDULER_AGENT_ID)
        )
        self.conversation_id = conversation_id
        self.headers = {"Content-Type": "application/json"}
        self.timeout = timeout or self._DEFAULT_TIMEOUT
        self.logger = logger or logging.getLogger(__name__)
        self.last_message: str = ""

    def chat_stream(self, system: Optional[str], user: str) -> Generator[str, None, None]:
        """Yield response deltas from Letta as they arrive."""

        prompt = f"{system}\n\n{user}" if system else user

        # Use conversation endpoint if conversation_id is provided
        if self.conversation_id:
            url = f"{self.base}/v1/conversations/{self.conversation_id}/messages"
            body = {"input": prompt}
            self.logger.info(f"Using Conversations API: {self.conversation_id}")
        else:
            url = f"{self.base}/v1/agents/{self.agent}/messages/stream"
            body = {"messages": [{"role": "user", "content": prompt}]}
            self.logger.info(f"Using Agent API (legacy): {self.agent}")

        assembled: str = ""
        last_segment: Optional[str] = None

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

    def chat_stream_with_events(self, system: Optional[str], user: str) -> Generator[StreamEvent, None, None]:
        """Yield events from Letta stream, including text deltas and tool calls."""

        prompt = f"{system}\n\n{user}" if system else user

        # Use conversation endpoint if conversation_id is provided
        if self.conversation_id:
            url = f"{self.base}/v1/conversations/{self.conversation_id}/messages"
            body = {"input": prompt}
            self.logger.info(f"Using Conversations API: {self.conversation_id}")
        else:
            url = f"{self.base}/v1/agents/{self.agent}/messages/stream"
            body = {"messages": [{"role": "user", "content": prompt}]}
            self.logger.info(f"Using Agent API (legacy): {self.agent}")

        assembled: str = ""
        last_segment: Optional[str] = None

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

                # Log full payload for debugging (using ERROR to ensure it's visible)
                self.logger.error(f"🔍 SSE PAYLOAD:\n{json.dumps(payload, indent=2)[:800]}")

                # Check for tool calls first
                tool_event = self._extract_tool_call(payload)
                if tool_event:
                    yield tool_event
                    continue

                # Check for tool returns (contains verbatim output for proposals)
                tool_return_event = self._extract_tool_return(payload)
                if tool_return_event:
                    yield tool_return_event
                    continue

                # Extract text segments (already clean from assistant_message)
                segments = self._extract_segments(payload)
                if not segments:
                    continue

                for segment in segments:
                    # Segments from assistant_message are already clean - no sanitization needed
                    cleaned = segment.strip()
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
                    yield {"type": "text", "content": delta}

            self.last_message = assembled.strip()

    # ------------------------------------------------------------------
    def _extract_tool_call(self, payload: object) -> Optional[StreamEvent]:
        """Extract tool call information from SSE payload."""
        if not isinstance(payload, dict):
            return None

        # Check for tool_call_message type (Letta's current format)
        if payload.get("message_type") == "tool_call_message":
            tool_call = payload.get("tool_call")
            if isinstance(tool_call, dict):
                tool_name = tool_call.get("name", "")
                self.logger.info(f"🔧 Tool call detected: {tool_name}")
                return {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": tool_call.get("arguments", {}),
                }

        # Check for tool_calls array pattern
        if "tool_calls" in payload:
            tool_calls = payload["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                tool_call = tool_calls[0]
                if isinstance(tool_call, dict):
                    return {
                        "type": "tool_call",
                        "tool_name": tool_call.get("name", ""),
                        "arguments": tool_call.get("arguments", {}),
                    }
        
        # Check for function_call pattern
        if "function_call" in payload:
            func_call = payload["function_call"]
            if isinstance(func_call, dict):
                return {
                    "type": "tool_call",
                    "tool_name": func_call.get("name", ""),
                    "arguments": func_call.get("arguments", {}),
                }
        
        # Check message_type for function_call indicators
        if payload.get("message_type") == "function_call":
            return {
                "type": "tool_call",
                "tool_name": payload.get("function_name", payload.get("name", "")),
                "arguments": payload.get("function_args", {}),
            }

        return None

    def _extract_tool_return(self, payload: object) -> Optional[StreamEvent]:
        """Extract tool return information from SSE payload.

        Tool returns contain verbatim output for scheduling proposals that
        needs to be captured for proposal detection.
        """
        if not isinstance(payload, dict):
            return None

        # Check for tool_return_message type (Letta's format)
        if payload.get("message_type") == "tool_return_message":
            tool_return = payload.get("tool_return", "")
            tool_name = payload.get("name", "")
            if tool_return:
                self.logger.info(f"🔧 Tool return detected: {tool_name} ({len(tool_return)} chars)")
                return {
                    "type": "tool_return",
                    "tool_name": tool_name,
                    "content": tool_return,
                }

        return None

    def _extract_segments(self, payload: object) -> List[str]:
        """Extract text segments ONLY from assistant_message type."""

        if not isinstance(payload, dict):
            return []

        # ONLY process messages with message_type == "assistant_message"
        message_type = payload.get("message_type", "")
        
        if message_type != "assistant_message":
            # Skip everything that's not an assistant message
            if message_type:
                self.logger.debug(f"Skipping message_type: {message_type}")
            return []
        
        # Extract ONLY the content field from assistant messages
        content = payload.get("content")
        if content and isinstance(content, str):
            self.logger.info(f"✅ Extracted assistant_message content: {content[:100]}...")
            return [content]
        
        return []

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
    _TIMESTAMP_PREFIX = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9T:+-]+")
    _UUID_PATTERN = re.compile(r"-?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
    
    # Patterns to completely filter out tool call metadata and returns
    _TOOL_CALL_PATTERNS = (
        # Tool call/return with or without brackets
        re.compile(r"^[A-Z][a-z_]+tool_return_message", re.IGNORECASE),  # Find_Shared_Meeting_Slotstool_return_message
        re.compile(r"^[A-Z][a-z_]+tool_call", re.IGNORECASE),  # Any tool_call prefix
        re.compile(r"^[A-Z][a-z_]+_message", re.IGNORECASE),  # Find_Shared_Meeting_Slots_message
        # Tool name pattern (PascalCase or Snake_Case followed by successcall)
        re.compile(r"^[A-Z][A-Za-z_]+(?=successcall_)"),  # Find_Shared_Meeting_Slots before successcall_
        # Success/failure call IDs with or without brackets
        re.compile(r"successcall_[a-zA-Z0-9]+"),  # successcall_d3KpxXx5rwIejZcKoYUlNC2c
        re.compile(r"failedcall_[a-zA-Z0-9]+"),  # failedcall_xxx
        re.compile(r"^function_return", re.IGNORECASE),  # function_return messages
        re.compile(r"^\s*\{[\s\S]*\"response\"[\s\S]*\}"),  # Large JSON objects with "response" key
    )

    def _sanitize_segment(self, text: str) -> str:
        if not text:
            return ""

        # Skip if it looks like a large JSON object (starts with { or [, has lots of structure)
        stripped = text.strip()
        if (stripped.startswith('{') or stripped.startswith('[')) and len(stripped) > 200:
            # Check if it looks like a tool response (has common keys)
            if any(key in stripped for key in ['"slots":', '"response":', '"groupsText":', '"arguments":']):
                self.logger.debug(f"Filtering out large JSON payload: {stripped[:100]}...")
                return ""

        # Check if this entire segment is ONLY tool call metadata
        for pattern in self._TOOL_CALL_PATTERNS:
            if pattern.match(text.strip()):
                self.logger.debug(f"Filtering out tool call metadata: {text[:100]}...")
                return ""

        cleaned = text

        # Strip garbage from the beginning: timestamps, UUIDs, hex, etc.
        # Pattern: anything that's not normal text before a capital letter
        garbage_prefix = re.compile(
            r"^[T0-9a-f:\+\-d]+(?=[A-Z])",  # Timestamps, UUIDs, hex, dates before capital
            re.IGNORECASE
        )
        cleaned = garbage_prefix.sub("", cleaned)
        
        # Strip garbage from the end: partial keywords like "nd_turn", "istics", etc.
        garbage_suffix = re.compile(
            r"(nd_turn|d_turn|_turn|istics|tistics|mitted|itted)$",
            re.IGNORECASE
        )
        cleaned = garbage_suffix.sub("", cleaned)

        # Remove any remaining tool call patterns from anywhere in the text
        for pattern in self._TOOL_CALL_PATTERNS:
            cleaned = pattern.sub("", cleaned)

        # Remove control message prefixes
        for pattern in self._CONTROL_PREFIXES:
            cleaned = pattern.sub("", cleaned)

        # Remove timestamps and UUIDs from anywhere in text
        cleaned = self._TIMESTAMP_PREFIX.sub("", cleaned)
        cleaned = self._UUID_PATTERN.sub("", cleaned)

        # Remove specific keywords and their fragments
        keywords_to_remove = [
            "omitted", "itted",  # Handle partial matches
            "stop_reason", "end_turn",
            "usage_statistics", "istics",  # Handle partial matches
            "tool_return", "function_return",
            "tool_call", "function_call",
        ]
        for keyword in keywords_to_remove:
            cleaned = cleaned.replace(keyword, "")

        return cleaned.strip()

    @staticmethod
    def _normalize_for_compare(text: str) -> str:
        if not text:
            return ""
        return " ".join(text.split()).lower()
