"""Envelope — the one new data contract for the offline command bus.

An Envelope is a self-describing, durable agent invocation captured by MC while
offline (or anytime) and replayed against the fleet on reconnect. Envelopes are
files in a git-synced outbox/inbox; the database is never extended to hold them.

Identity (`id`) is a content hash over the *semantic* fields (target/verb/args/
reply_to/idempotency_key/version) and deliberately EXCLUDES `created_at`, so two
identical commands dedup naturally. To issue the same command twice on purpose,
vary `idempotency_key`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

ENVELOPE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Envelope:
    target: str                                   # agent/service, e.g. "email", "docs", "tasks"
    verb: str                                     # e.g. "email.search", "email.draft", "task.extract"
    args: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None                # inbox key for the result
    idempotency_key: Optional[str] = None         # vary to allow intentional duplicates
    created_at: Optional[str] = None              # metadata only; NOT part of id
    version: int = ENVELOPE_VERSION
    id: Optional[str] = None                      # content hash; auto-computed

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = _now_iso()
        if self.id is None:
            self.id = self.content_hash()

    def content_hash(self) -> str:
        basis = {
            "version": self.version,
            "target": self.target,
            "verb": self.verb,
            "args": self.args,
            "reply_to": self.reply_to,
            "idempotency_key": self.idempotency_key,
        }
        blob = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "target": self.target,
            "verb": self.verb,
            "args": self.args,
            "reply_to": self.reply_to,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Envelope":
        d = json.loads(s)
        return cls(
            target=d["target"],
            verb=d["verb"],
            args=d.get("args") or {},
            reply_to=d.get("reply_to"),
            idempotency_key=d.get("idempotency_key"),
            created_at=d.get("created_at"),
            version=d.get("version", ENVELOPE_VERSION),
            id=d.get("id"),
        )
