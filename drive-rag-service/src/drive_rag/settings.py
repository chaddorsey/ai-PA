"""Settings and configuration for Drive RAG service."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str = "http://localhost:8000"
    supabase_service_key: str = ""

    # OpenAI
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimensions: int = 1536

    # Google OAuth
    google_credentials_path: str = "/app/credentials"
    google_token_path: Optional[str] = None

    # Chunking configuration
    max_chunk_chars: int = 6000
    min_chunk_chars: int = 1200

    # Service configuration
    service_name: str = "drive-rag-service"
    log_level: str = "INFO"

    # Rate limiting
    embedding_batch_size: int = 20
    embedding_requests_per_minute: int = 3000


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
