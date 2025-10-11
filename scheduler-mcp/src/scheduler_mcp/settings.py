"""Configuration settings for scheduler MCP server."""

from typing import Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="scheduler-mcp")
    scheduler_base_url: AnyHttpUrl = Field(
        default="http://scheduler-service:8087/v1",
        description="Base URL for the scheduler REST API",
    )
    api_key: Optional[str] = Field(default=None, env="SCHEDULER_API_KEY")
    timeout_seconds: float = Field(default=10.0)
    request_retries: int = Field(default=3)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


