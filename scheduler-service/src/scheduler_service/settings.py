"""Service configuration settings."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = Field(default="scheduler-service")
    log_level: str = Field(default="INFO")
    api_key: Optional[str] = Field(default=None, alias="SCHEDULER_API_KEY")

    database_url: str = Field(
        default="postgresql+asyncpg://scheduler_service:scheduler_secret@localhost:5432/scheduler_service",
        alias="SCHEDULER_DB_URL",
    )

    alembic_config_path: str = Field(default="migrations/alembic.ini")

    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL_NAME",
    )
    embedding_cache_dir: str = Field(
        default="/app/.cache/embeddings", alias="EMBEDDING_CACHE_DIR"
    )

    allowlist_script_dir: str = Field(
        default="/app/scripts", alias="ALLOWLIST_SCRIPT_DIR"
    )
    letta_callback_url: Optional[AnyHttpUrl] = Field(
        default=None, alias="LETTA_CALLBACK_URL"
    )
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")

    scheduler_timezone: str = Field(default="UTC", alias="SCHEDULER_TIMEZONE")
    scheduler_instance_id: Optional[str] = Field(
        default=None, alias="SCHEDULER_INSTANCE_ID"
    )

    http_timeout_seconds: float = Field(default=15.0, alias="HTTP_TIMEOUT_SECONDS")
    http_retries: int = Field(default=2, alias="HTTP_RETRIES")
    http_retry_backoff: float = Field(default=1.0, alias="HTTP_RETRY_BACKOFF")

    agent_message_timeout_seconds: float = Field(
        default=300.0, alias="AGENT_MESSAGE_TIMEOUT_SECONDS"
    )

    script_env_defaults: Dict[str, str] = Field(default_factory=dict)

    scheduler_db_password: SecretStr = Field(
        default=SecretStr("scheduler_secret"), alias="SCHEDULER_DB_PASSWORD"
    )


def get_settings() -> Settings:
    return Settings()


settings = get_settings()


