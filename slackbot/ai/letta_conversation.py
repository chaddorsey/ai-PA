"""
Direct Letta Conversations API helper for Slack users.

Creates and caches one Letta conversation per Slack user per agent,
giving each user an isolated message history instead of sharing
the agent's entire accumulated message buffer.

Identity-aware: resolves Slack user IDs to Letta identity IDs via the
identity module, then stores the mapping in Supabase user_conversations
table — the same table pa-web uses. This enables cross-interface
conversation continuity when shared routing is added later.

Falls back gracefully: if identity resolution or Supabase fails,
uses the original Letta-labels-only approach.
"""

import logging
import os
import threading
from typing import Optional, Tuple

import requests

from ai.identity import resolve_identity, create_external_identity

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Default scheduler agent — same as letta_stream.py
DEFAULT_AGENT_ID = os.getenv(
    "LETTA_SCHEDULER_AGENT_ID",
    os.getenv("LETTA_AGENT_ID", "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"),
)

# In-memory cache: {(user_id, agent_id): (conversation_id, identity_id)}
_cache: dict = {}
_cache_lock = threading.Lock()

# Label prefix for Slack conversations
_LABEL_PREFIX = "slack-"


def _supabase_headers() -> dict:
    """PostgREST headers for Supabase access."""
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_lookup(
    user_id: str, agent_id: str, log: logging.Logger
) -> Optional[Tuple[str, Optional[str]]]:
    """Look up existing conversation in Supabase user_conversations table.

    Returns (conversation_id, identity_id) or None.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/user_conversations",
            params={
                "select": "conversation_id,identity_id",
                "user_id": f"eq.{user_id}",
                "user_source": "eq.slack",
                "agent_id": f"eq.{agent_id}",
            },
            headers=_supabase_headers(),
            timeout=5.0,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return (rows[0]["conversation_id"], rows[0].get("identity_id"))
    except Exception as e:
        log.debug("supabase_conversation_lookup_failed: %s", e)

    return None


def _supabase_store(
    user_id: str,
    agent_id: str,
    conversation_id: str,
    identity_id: Optional[str],
    log: logging.Logger,
) -> None:
    """Store conversation mapping in Supabase (fire-and-forget)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/user_conversations",
            json={
                "user_id": user_id,
                "user_source": "slack",
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "identity_id": identity_id,
            },
            headers=_supabase_headers(),
            timeout=5.0,
        )
        if resp.status_code == 409:
            # Already exists (UNIQUE constraint) — update identity_id if we have one
            if identity_id:
                requests.patch(
                    f"{SUPABASE_URL}/user_conversations",
                    params={
                        "user_id": f"eq.{user_id}",
                        "user_source": "eq.slack",
                        "agent_id": f"eq.{agent_id}",
                    },
                    json={"identity_id": identity_id},
                    headers=_supabase_headers(),
                    timeout=5.0,
                )
            return
        resp.raise_for_status()
        log.info(
            "supabase_conversation_stored user=%s conv=%s identity=%s",
            user_id,
            conversation_id,
            identity_id,
        )
    except Exception as e:
        log.debug("supabase_conversation_store_failed: %s", e)


def get_or_create_letta_conversation(
    user_id: str,
    agent_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Get or create a Letta conversation for a Slack user.

    Resolution order:
    1. In-memory cache
    2. Supabase user_conversations table (shared with pa-web)
    3. Letta Conversations API label lookup (legacy)
    4. Create new conversation + store in Supabase

    Also resolves Slack user_id to Letta identity_id and stores
    the mapping for cross-interface continuity.

    Returns conversation_id, or None on failure (falls back to legacy messaging).
    """
    log = logger or logging.getLogger(__name__)
    agent_id = agent_id or DEFAULT_AGENT_ID
    cache_key = (user_id, agent_id)

    # 1. Check in-memory cache
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached:
        return cached[0]  # conversation_id

    # Resolve identity (non-blocking, cached)
    identity_id = None
    try:
        identity_id = resolve_identity(user_id)
        if identity_id:
            log.info("identity_resolved slack_user=%s identity=%s", user_id, identity_id)
        else:
            # Unknown user — create external identity
            identity_id = create_external_identity(user_id)
            if identity_id:
                log.info("identity_created slack_user=%s identity=%s", user_id, identity_id)
    except Exception as e:
        log.debug("identity_resolution_failed: %s", e)

    # 2. Check Supabase
    supabase_result = _supabase_lookup(user_id, agent_id, log)
    if supabase_result:
        conv_id, existing_identity = supabase_result
        # Backfill identity_id if we resolved one and Supabase doesn't have it
        if identity_id and not existing_identity:
            _supabase_store(user_id, agent_id, conv_id, identity_id, log)
        with _cache_lock:
            _cache[cache_key] = (conv_id, identity_id or existing_identity)
        log.info("conversation_from_supabase user=%s conv=%s", user_id, conv_id)
        return conv_id

    label = f"{_LABEL_PREFIX}{user_id}"

    try:
        # 3. Check Letta API labels (legacy path)
        resp = requests.get(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": agent_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        conversations = resp.json()

        for conv in conversations:
            if conv.get("label") == label:
                conv_id = conv["id"]
                log.info(
                    "conversation_from_letta_label user=%s conv=%s",
                    user_id,
                    conv_id,
                )
                # Backfill to Supabase for future lookups
                _supabase_store(user_id, agent_id, conv_id, identity_id, log)
                with _cache_lock:
                    _cache[cache_key] = (conv_id, identity_id)
                return conv_id

        # 4. Create new conversation
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

        log.info("conversation_created user=%s conv=%s", user_id, conv_id)

        # Store in Supabase
        _supabase_store(user_id, agent_id, conv_id, identity_id, log)

        with _cache_lock:
            _cache[cache_key] = (conv_id, identity_id)
        return conv_id

    except Exception as e:
        log.warning("letta_conversation_lookup_failed: %s", e)
        return None


def clear_letta_conversation(
    user_id: str,
    agent_id: Optional[str] = None,
    log: Optional[logging.Logger] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Implement `/clear` semantics per Letta Code: move the user to a fresh
    Letta conversation on the SAME agent, keeping memory blocks intact.

    Returns (old_conv_id, new_conv_id). Either may be None if a step
    failed; the caller decides how to surface that.

    Steps:
      1. Look up the user's current conversation (cache + Supabase + label).
      2. Evict the in-memory cache entry so subsequent lookups create
         (or pick up) a different conversation.
      3. Best-effort: cancel any in-flight run on the old conversation.
      4. Create a new Letta conversation with the same agent + label.
      5. Persist the new mapping (Supabase + cache).

    Does NOT touch agent memory blocks. Does NOT delete the old conv —
    its history remains accessible, just unreferenced by this user's
    cache. Future messages route to the new conv.
    """
    log = log or logging.getLogger(__name__)
    agent_id = agent_id or DEFAULT_AGENT_ID
    cache_key = (user_id, agent_id)

    # 1. Resolve current conv
    with _cache_lock:
        cached = _cache.get(cache_key)
    old_conv_id: Optional[str] = cached[0] if cached else None
    identity_id: Optional[str] = cached[1] if cached else None

    if not old_conv_id:
        sb_hit = _supabase_lookup(user_id, agent_id, log)
        if sb_hit:
            old_conv_id, identity_id = sb_hit
            if not identity_id:
                identity_id = resolve_identity(user_id) or create_external_identity(user_id)

    # 2. Evict from in-memory cache. (Supabase row is overwritten in step 5.)
    with _cache_lock:
        _cache.pop(cache_key, None)

    # 3. Best-effort: cancel any active run on the old conversation.
    if old_conv_id:
        try:
            requests.post(
                f"{LETTA_BASE_URL}/v1/conversations/{old_conv_id}/cancel",
                timeout=5.0,
            )
        except Exception as exc:
            log.debug("clear_cancel_old_conv_failed: %s", exc)

    # 4. Create a new conversation on the same agent.
    label = f"{_LABEL_PREFIX}{user_id}"
    try:
        create_resp = requests.post(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": agent_id},
            json={"label": label},
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        create_resp.raise_for_status()
        new_conv_id = create_resp.json().get("id")
    except Exception as exc:
        log.warning("clear_create_new_conv_failed: %s", exc)
        return old_conv_id, None

    if not new_conv_id:
        return old_conv_id, None

    # 5. Persist mapping (Supabase upsert + warm cache).
    if not identity_id:
        try:
            identity_id = resolve_identity(user_id) or create_external_identity(user_id)
        except Exception:
            identity_id = None
    _supabase_store(user_id, agent_id, new_conv_id, identity_id, log)
    with _cache_lock:
        _cache[cache_key] = (new_conv_id, identity_id)

    log.info(
        "clear_letta_conversation user=%s agent=%s old=%s new=%s",
        user_id, agent_id, old_conv_id, new_conv_id,
    )
    return old_conv_id, new_conv_id


def get_cached_identity(user_id: str, agent_id: Optional[str] = None) -> Optional[str]:
    """
    Get the cached identity_id for a Slack user (if resolved).

    Lightweight accessor for use in archival writes and other
    places that need the identity_id without triggering a new lookup.

    Returns identity_id or None.
    """
    agent_id = agent_id or DEFAULT_AGENT_ID
    with _cache_lock:
        cached = _cache.get((user_id, agent_id))
    if cached:
        return cached[1]  # identity_id
    return None
