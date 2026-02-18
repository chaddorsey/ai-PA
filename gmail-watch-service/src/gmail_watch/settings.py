"""Service configuration settings."""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application settings
    app_name: str = Field(default="gmail-watch-service")
    log_level: str = Field(default="INFO")

    # Database settings
    database_url: Optional[str] = Field(
        default=None,
        alias="DATABASE_URL",
        description="PostgreSQL connection URL for storing watched thread state",
    )

    # GCP/Pub/Sub settings
    gcp_project_id: Optional[str] = Field(
        default=None,
        alias="GCP_PROJECT_ID",
        description="Google Cloud Project ID for Pub/Sub",
    )
    pubsub_subscription: str = Field(
        default="gmail-watch-pull",
        alias="PUBSUB_SUBSCRIPTION",
        description="Pub/Sub subscription name for Gmail push notifications",
    )

    # Gmail settings
    gmail_credentials_path: Optional[str] = Field(
        default=None,
        alias="GMAIL_CREDENTIALS_PATH",
        description="Path to Gmail OAuth credentials JSON file",
    )
    watching_label_name: str = Field(
        default="Watching",
        alias="WATCHING_LABEL_NAME",
        description="Gmail label name to filter watched threads",
    )

    # Letta integration settings
    letta_base_url: Optional[str] = Field(
        default=None,
        alias="LETTA_BASE_URL",
        description="Base URL for Letta API (e.g., http://letta:8283)",
    )
    letta_agent_id: Optional[str] = Field(
        default=None,
        alias="LETTA_AGENT_ID",
        description="Letta agent ID to notify on new replies",
    )

    # Polling settings
    pull_interval_seconds: int = Field(
        default=30,
        alias="PULL_INTERVAL_SECONDS",
        description="Interval in seconds between Pub/Sub pull operations",
    )

    # Follow-up scanner settings
    followup_check_interval: int = Field(
        default=300,
        alias="FOLLOWUP_CHECK_INTERVAL",
        description="Interval in seconds between follow-up deadline checks",
    )

    # BCC auto-watch settings
    bcc_watch_address: str = Field(
        default="cdorsey+watch",
        alias="BCC_WATCH_ADDRESS",
        description="Plus-address prefix for BCC-triggered watches (without domain)",
    )
    default_followup_seconds: int = Field(
        default=259200,
        alias="DEFAULT_FOLLOWUP_SECONDS",
        description="Default follow-up interval in seconds (3 days = 259200)",
    )

    # Task queue settings
    task_queue_enabled: bool = Field(
        default=False,
        alias="TASK_QUEUE_ENABLED",
        description="Enable automatic task queue processing",
    )
    task_queue_label_name: str = Field(
        default="TaskQueue",
        alias="TASK_QUEUE_LABEL_NAME",
        description="Gmail label name for task queue messages",
    )
    task_queue_block_id: Optional[str] = Field(
        default=None,
        alias="TASK_QUEUE_BLOCK_ID",
        description="Letta memory block ID for queued_tasks_from_email",
    )
    task_queue_bcc_address: str = Field(
        default="cdorsey+tasks",
        alias="TASK_QUEUE_BCC_ADDRESS",
        description="Plus-address prefix for task queue (without domain)",
    )


def get_settings() -> Settings:
    """Get the application settings instance."""
    return Settings()


settings = get_settings()
