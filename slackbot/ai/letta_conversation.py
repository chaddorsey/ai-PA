"""
Direct Letta Conversations API helper for Slack users.

Creates and caches one Letta conversation per Slack user per agent,
giving each user an isolated message history instead of sharing
the agent's entire accumulated message buffer.

No Supabase dependency — talks to Letta API directly.
"""

import logging
import os
import threading
from typing import Optional

import requests

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")

# Default scheduler agent — same as letta_stream.py
DEFAULT_AGENT_ID = os.getenv(
    "LETTA_SCHEDULER_AGENT_ID",
    os.getenv("LETTA_AGENT_ID", "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"),
)

# In-memory cache: {(user_id, agent_id): conversation_id}
_cache: dict = {}
_cache_lock = threading.Lock()

# Label prefix for Slack conversations
_LABEL_PREFIX = "slack-"


def get_or_create_letta_conversation(
    user_id: str,
    agent_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Get or create a Letta conversation for a Slack user.

    Looks up existing conversations labeled 'slack-{user_id}' on the agent.
    Creates one if none exists. Caches the result in memory.

    Returns conversation_id, or None on failure (falls back to legacy messaging).
    """
    log = logger or logging.getLogger(__name__)
    agent_id = agent_id or DEFAULT_AGENT_ID
    cache_key = (user_id, agent_id)

    # Check in-memory cache first
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached:
        return cached

    label = f"{_LABEL_PREFIX}{user_id}"

    try:
        # List conversations for this agent
        resp = requests.get(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": agent_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        conversations = resp.json()

        # Find one with matching label
        for conv in conversations:
            if conv.get("label") == label:
                conv_id = conv["id"]
                log.info(
                    "Found existing Letta conversation %s for Slack user %s",
                    conv_id,
                    user_id,
                )
                with _cache_lock:
                    _cache[cache_key] = conv_id
                return conv_id

        # None found — create a new one
        create_resp = requests.post(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": agent_id},
            json={"label": label},
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        create_resp.raise_for_status()
        conv_data = create_resp.json()
        conv_id = conv_data["id"]

        log.info(
            "Created new Letta conversation %s for Slack user %s",
            conv_id,
            user_id,
        )
        with _cache_lock:
            _cache[cache_key] = conv_id
        return conv_id

    except Exception as e:
        log.warning("Letta conversation lookup/creation failed: %s", e)
        return None
