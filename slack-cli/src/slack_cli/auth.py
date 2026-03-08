"""Credential chain for Slack CLI."""
import json
import os
from pathlib import Path

TOKEN_TYPE_BOT = "bot"
TOKEN_TYPE_USER = "user"
TOKEN_TYPE_EITHER = "either"

CONFIG_PATH = os.path.expanduser("~/.config/slack-cli/credentials.json")


def _load_config() -> dict:
    """Load credentials from config file if it exists."""
    path = Path(CONFIG_PATH)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def resolve_token(token_type: str, force_user: bool = False, force_bot: bool = False) -> str | None:
    """Resolve a Slack token using the credential chain.

    Priority:
    1. SLACK_CLI_TOKEN / SLACK_CLI_USER_TOKEN env vars
    2. ~/.config/slack-cli/credentials.json
    3. SLACK_BOT_TOKEN / SLACK_MCP_XOXP_TOKEN env vars (fallback)
    """
    if force_user:
        token_type = TOKEN_TYPE_USER
    elif force_bot:
        token_type = TOKEN_TYPE_BOT

    if token_type == TOKEN_TYPE_EITHER:
        return resolve_token(TOKEN_TYPE_BOT) or resolve_token(TOKEN_TYPE_USER)

    if token_type == TOKEN_TYPE_BOT:
        sources = [
            ("env", "SLACK_CLI_TOKEN"),
            ("config", "bot_token"),
            ("env", "SLACK_BOT_TOKEN"),
        ]
    else:
        sources = [
            ("env", "SLACK_CLI_USER_TOKEN"),
            ("config", "user_token"),
            ("env", "SLACK_MCP_XOXP_TOKEN"),
        ]

    config = _load_config()

    for source_type, key in sources:
        if source_type == "env":
            val = os.environ.get(key)
        else:
            val = config.get(key)
        if val:
            return val

    return None


def save_credentials(bot_token: str | None = None, user_token: str | None = None) -> None:
    """Save tokens to config file."""
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_config()
    if bot_token:
        existing["bot_token"] = bot_token
    if user_token:
        existing["user_token"] = user_token

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    path.chmod(0o600)
