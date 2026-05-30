"""
Cross-provider message-format compatibility hook for LiteLLM.

When an agent's conversation history accumulates provider-specific fields
(e.g. OpenAI's encrypted `reasoning_content_signature` from gpt-5.x reasoning
models, or Anthropic-style `thinking` blocks), swapping the agent to a
provider that rejects those fields produces 400 errors that effectively
freeze the conversation.

This hook intercepts outbound chat-completion requests and strips fields
the *target* provider doesn't accept, leaving Letta's stored message
history untouched. The net effect: arbitrary back-and-forth swapping
between reasoning-capable providers (OpenAI, Anthropic) and strict
providers (Fireworks: Kimi/DeepSeek/GLM/MiniMax/gpt-oss) works without
manual surgery.

To extend: add the target model name to the appropriate set below, or add
a new field name to REASONING_FIELDS.
"""

from __future__ import annotations

import logging
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

log = logging.getLogger("litellm.cross_provider_compat")

# Models that reject OpenAI / Anthropic provider-specific reasoning fields.
# Membership is matched against the final segment of the model name
# (after the last '/'), so "fireworks_ai/accounts/fireworks/models/kimi-k2p6"
# and a bare "kimi-k2p6" both match.
STRICT_MODELS: frozenset[str] = frozenset({
    # Fireworks open-weights — reject any unknown message-level fields
    "kimi-k2p6",
    "kimi-k2p5",
    "glm-5p1",
    "minimax-m2p7",
    "gpt-oss-120b",
    # Fireworks reasoning-capable but uses its OWN reasoning format,
    # so OpenAI/Anthropic-emitted reasoning fields still need stripping.
    "deepseek-v4-pro",
})

# Fields known to break strict providers when present on assistant messages.
REASONING_FIELDS: tuple[str, ...] = (
    "reasoning_content_signature",   # OpenAI o-series / gpt-5.x encrypted reasoning
    "reasoning_content",              # OpenAI visible reasoning
    "encrypted_content",              # Variant naming
    "thinking",                       # Anthropic extended-thinking blocks
    "redacted_thinking",              # Anthropic redacted-thinking
)


def _last_segment(model: str) -> str:
    """fireworks_ai/accounts/.../kimi-k2p6 → kimi-k2p6"""
    return model.rsplit("/", 1)[-1]


def _strip_message(msg: dict[str, Any]) -> int:
    """Remove reasoning fields from a single message. Returns count removed."""
    stripped = 0
    for field in REASONING_FIELDS:
        if field in msg:
            del msg[field]
            stripped += 1
    # Some providers nest reasoning inside content blocks.
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                for field in REASONING_FIELDS:
                    if field in block:
                        del block[field]
                        stripped += 1
    return stripped


class CrossProviderCompat(CustomLogger):
    """Pre-call hook that scrubs incompatible message fields per target model."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        if call_type not in ("completion", "acompletion", "text_completion"):
            return data

        model = data.get("model", "")
        if _last_segment(model) not in STRICT_MODELS:
            return data

        messages = data.get("messages") or []
        total_stripped = 0
        for msg in messages:
            if isinstance(msg, dict):
                total_stripped += _strip_message(msg)

        if total_stripped:
            log.info(
                "cross_provider_compat: stripped %d reasoning field(s) "
                "from %d message(s) for model=%s",
                total_stripped,
                len(messages),
                model,
            )

        return data


# LiteLLM proxy loads `<module>.<instance_name>` — this name must match
# the `callbacks:` reference in litellm/config.yaml.
proxy_handler_instance = CrossProviderCompat()
