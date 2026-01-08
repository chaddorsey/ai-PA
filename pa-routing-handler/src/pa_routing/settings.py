"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """PA Routing Handler configuration."""

    # Letta connection
    letta_base_url: str = "http://letta:8283"

    # Default agent for fallback routing
    default_agent_id: str = ""

    # Database connection
    postgres_url: str = ""

    # Feature flags
    enable_dspy_routing: bool = False
    enable_semantic_routing: bool = False

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "PA_ROUTING_"


settings = Settings()
