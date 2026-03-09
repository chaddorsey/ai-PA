from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://curator_radar:curator_radar_secret@supabase-db:5432/curator_radar",
        alias="DATABASE_URL",
    )
    github_token: str = Field(alias="GITHUB_TOKEN")
    github_username: str = Field(default="chaddorsey", alias="GITHUB_USERNAME")
    top_curators_k: int = Field(default=20, alias="TOP_CURATORS_K")
    rate_limit_guard: int = Field(default=200, alias="RATE_LIMIT_GUARD")
    slackbot_notify_url: str = Field(
        default="http://slackbot:8081/api/notify",
        alias="SLACKBOT_NOTIFY_URL",
    )
    slack_user_id: str = Field(default="", alias="SLACK_USER_ID")

    model_config = {"env_file": ".env", "extra": "ignore"}
