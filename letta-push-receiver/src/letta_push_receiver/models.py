"""Request/response models for the receiver's HTTP API.

Plain dataclasses + dict serialization — Flask handles JSON in/out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PushRequest:
    agent: Optional[str]        # owner agent slug (e.g. "email")
    prompt: str                 # what the agent should do
    source: Optional[str] = None        # source slug for auto-routing
    source_ref: Optional[str] = None    # for idempotency / dedup
    priority: str = "normal"            # normal | urgent

    @classmethod
    def from_json(cls, j: dict) -> "PushRequest":
        if not isinstance(j, dict):
            raise ValueError("push body must be a JSON object")
        prompt = j.get("prompt")
        if not prompt or not isinstance(prompt, str):
            raise ValueError("push.prompt is required (string)")
        return cls(
            agent=j.get("agent"),
            prompt=prompt,
            source=j.get("source"),
            source_ref=j.get("source_ref"),
            priority=j.get("priority", "normal"),
        )
