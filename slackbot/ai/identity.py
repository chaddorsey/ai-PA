"""
Letta Identity resolution for Slack users.

Maps Slack user IDs to Letta Identity IDs by looking up the slack_id
property on Letta identities. This enables cross-interface conversation
continuity — the same identity_id links Slack and pa-web conversations.

All 30 staff identities already have slack_id properties populated.
For unknown Slack users, creates a new external identity.

Architecture Note (2026-02):
- Letta Identities API has no search-by-property, so we list all and filter
- Identities are cached in memory (invalidated on create)
- pa-routing-handler uses the same pattern via IdentityService class
"""

import logging
import os
import threading
from typing import Dict, List, Optional

import requests

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")

# Cache: list of identity dicts, refreshed on miss or create
_identities_cache: Optional[List[Dict]] = None
_cache_lock = threading.Lock()

logger = logging.getLogger(__name__)


def _fetch_all_identities() -> List[Dict]:
    """Fetch all identities from Letta API."""
    try:
        resp = requests.get(
            f"{LETTA_BASE_URL}/v1/identities/",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("identity_fetch_failed: %s", e)
        return []


def _get_identities() -> List[Dict]:
    """Get all identities with caching."""
    global _identities_cache
    with _cache_lock:
        if _identities_cache is None:
            _identities_cache = _fetch_all_identities()
        return _identities_cache


def _invalidate_cache() -> None:
    """Clear identity cache."""
    global _identities_cache
    with _cache_lock:
        _identities_cache = None


def _find_property(identity: Dict, key: str) -> Optional[str]:
    """Extract a property value from an identity dict."""
    for prop in identity.get("properties", []) or []:
        if prop.get("key") == key:
            return prop.get("value")
    return None


def resolve_identity(slack_user_id: str) -> Optional[str]:
    """
    Resolve a Slack user ID to a Letta identity_id.

    Looks up identities by their slack_id property. Returns identity_id
    if found, None otherwise. Does NOT create identities for unknown users
    (caller decides whether to create).

    Args:
        slack_user_id: Slack user ID (e.g., "U02V91KU8")

    Returns:
        Letta identity_id string, or None if not found.
    """
    identities = _get_identities()

    for identity in identities:
        if _find_property(identity, "slack_id") == slack_user_id:
            return identity.get("id")

    # Cache miss — refetch once in case identities were added since cache load
    _invalidate_cache()
    identities = _get_identities()
    for identity in identities:
        if _find_property(identity, "slack_id") == slack_user_id:
            return identity.get("id")

    return None


def resolve_identity_full(slack_user_id: str) -> Optional[Dict]:
    """
    Resolve a Slack user ID to a full identity dict.

    Same as resolve_identity but returns the complete identity record
    including name, identifier_key, and all properties.

    Args:
        slack_user_id: Slack user ID (e.g., "U02V91KU8")

    Returns:
        Full identity dict, or None if not found.
    """
    identities = _get_identities()

    for identity in identities:
        if _find_property(identity, "slack_id") == slack_user_id:
            return identity

    # Cache miss — refetch once
    _invalidate_cache()
    identities = _get_identities()
    for identity in identities:
        if _find_property(identity, "slack_id") == slack_user_id:
            return identity

    return None


def create_external_identity(
    slack_user_id: str,
    display_name: Optional[str] = None,
) -> Optional[str]:
    """
    Create a Letta identity for an unknown Slack user.

    Args:
        slack_user_id: Slack user ID
        display_name: Optional display name

    Returns:
        Created identity_id, or None on failure.
    """
    try:
        resp = requests.post(
            f"{LETTA_BASE_URL}/v1/identities/",
            json={
                "identifier_key": f"slack:{slack_user_id}",
                "name": display_name or slack_user_id,
                "identity_type": "user",
                "properties": [
                    {"key": "slack_id", "value": slack_user_id, "type": "string"},
                    {"key": "source", "value": "slack", "type": "string"},
                ],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        identity = resp.json()
        identity_id = identity.get("id")

        _invalidate_cache()
        logger.info(
            "external_identity_created slack_user=%s identity=%s",
            slack_user_id,
            identity_id,
        )
        return identity_id

    except Exception as e:
        logger.warning(
            "external_identity_creation_failed slack_user=%s error=%s",
            slack_user_id,
            e,
        )
        return None
