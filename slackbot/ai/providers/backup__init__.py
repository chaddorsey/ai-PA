# ai/providers/__init__.py
import os

# Optional, but nice for linters/IDE
__all__ = ["available_providers", "get_available_providers", "get_provider", "get_provider_response"]

_AVAILABLE: dict[str, type] = {}

# OpenAI (optional)
try:
    from .openai import OpenAIAPI  # your provider class name
    if os.getenv("OPENAI_API_KEY"):
        _AVAILABLE["openai"] = OpenAIAPI
except Exception:
    pass

# Anthropic (optional)
try:
    from .anthropic import AnthropicAPI
    if os.getenv("ANTHROPIC_API_KEY"):
        _AVAILABLE["anthropic"] = AnthropicAPI
except Exception:
    pass

# Vertex/Gemini (optional)
try:
    from .vertex import VertexAPI
    if os.getenv("VERTEX_AI_PROJECT_ID"):
        _AVAILABLE["vertex"] = VertexAPI
except Exception:
    pass


def available_providers() -> list[str]:
    """Return provider keys available given installed SDKs + env vars."""
    return sorted(_AVAILABLE.keys())

def get_available_providers() -> list[str]:
    return available_providers()

def get_provider(name: str):
    """Instantiate the selected provider class."""
    if name not in _AVAILABLE:
        raise RuntimeError(
            f"Provider '{name}' is not available. "
            f"Available: {', '.join(available_providers()) or '(none)'}"
        )
    return _AVAILABLE[name]()


def get_provider_response(
    user_id: str,
    purpose: str,
    message: str,
    provider_name: str,
    model: str | None = None,
) -> str:
    """Uniform chat entry point used by listeners."""
    system = "You are a helpful Slack bot."
    if purpose == "summarize":
        system = (
            "Summarize the following Slack conversation for a newcomer. "
            "Be concise and neutral."
        )
    provider = get_provider(provider_name)
    return provider.chat(system, message, model=model)
