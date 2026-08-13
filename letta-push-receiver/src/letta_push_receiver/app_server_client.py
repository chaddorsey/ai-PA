"""Per-task enrichment dispatch against the warm App Server.

Each POST /v1/responses is a FRESH, isolated conversation (stateless —
confirmed in the Task 1 spike), so context never accumulates across tasks.
Non-streaming: the server returns one JSON object with output[] + usage.
"""
from __future__ import annotations
import json, urllib.request, urllib.error
from dataclasses import dataclass

# Task-1 spike: /v1/models exposes agents by FRIENDLY NAME, not agent-local-* id.
SLUG_TO_MODEL = {
    "tasks": "tasks-agent-local",
    "docs": "docs-and-transcripts-agent-local",
    "pulse": "pulse-monitor-agent-local",
    "email": "email-agent-local",
    "calendar": "calendar-agent_copy-local",
    "mc": "Mission Control (local)",
}

@dataclass
class DispatchResult:
    status: str          # "done" | "error"
    context_tokens: int | None
    detail: str

def parse_responses_json(obj: dict) -> "DispatchResult":
    usage = obj.get("usage") or {}
    # total_tokens is the real per-task context size; input_tokens is only
    # the last-turn delta (spike measured ~708 vs ~35167 total on the same
    # response), so the >200_000 WARN in enrich() below needs total_tokens
    # to ever fire. Fall back to input_tokens if total_tokens is absent.
    ctx = usage.get("total_tokens")
    if ctx is None:
        ctx = usage.get("input_tokens")
    if obj.get("status") != "completed":
        err = obj.get("error") or {}
        detail = err.get("message") if isinstance(err, dict) else str(err)
        return DispatchResult("error", ctx, detail or f"status={obj.get('status')}")
    text = ""
    for item in obj.get("output", []):
        if item.get("type") == "message":
            content = item.get("content") or []
            if content:
                text = content[0].get("text", "")
    return DispatchResult("done", ctx, text)

class AppServerClient:
    def __init__(self, base_url: str, log_fn):
        self.base_url = base_url.rstrip("/")
        self.log = log_fn

    def is_reachable(self, timeout: float = 2.0) -> bool:
        """Cheap liveness probe of the sole-owner App Server.

        Used by the receiver to return a synchronous 503 (retryable) when the
        server is down, instead of a false 202 followed by a silent async
        failure. Deliberately does NOT fall back to any local-subprocess path
        — the receiver never opens lc-local-backend itself (single-writer; the
        warm-pool fork fallback was removed in plan Unit 2).
        """
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def enrich(self, slug: str, prompt: str) -> DispatchResult:
        model = SLUG_TO_MODEL.get(slug, slug)
        body = json.dumps({"model": model, "input": prompt}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/responses", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                obj = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return DispatchResult("error", None, f"HTTP {e.code}: {e.read()[:200].decode('utf-8','replace')}")
        except Exception as e:
            return DispatchResult("error", None, f"unreachable: {e}")
        result = parse_responses_json(obj)
        # Observability sanity-check: a single fresh-conversation task should be
        # nowhere near the window. Flag pathological single-task growth.
        if result.context_tokens and result.context_tokens > 200_000:
            self.log(f"WARN pathological single-task context={result.context_tokens} slug={slug}")
        return result
