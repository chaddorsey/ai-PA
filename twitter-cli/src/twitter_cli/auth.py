"""Cookie-based authentication for Twitter API.

Priority: environment variables > Smaug config file.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_cookies(config_path: str) -> dict[str, str]:
    """Load Twitter auth cookies.

    Args:
        config_path: Path to Smaug's smaug.config.json.

    Returns:
        Dict with 'auth_token' and 'ct0' keys.
    """
    # Environment variables take precedence
    env_auth = os.environ.get("TWITTER_AUTH_TOKEN", "")
    env_ct0 = os.environ.get("TWITTER_CT0", "")
    if env_auth and env_ct0:
        return {"auth_token": env_auth, "ct0": env_ct0}

    # Fall back to Smaug config file
    path = Path(config_path)
    if not path.exists():
        logger.warning("Smaug config not found: %s", config_path)
        return {"auth_token": "", "ct0": ""}

    try:
        config = json.loads(path.read_text())
        twitter = config.get("twitter", {})
        return {
            "auth_token": twitter.get("authToken", ""),
            "ct0": twitter.get("ct0", ""),
        }
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read Smaug config: %s", e)
        return {"auth_token": "", "ct0": ""}
