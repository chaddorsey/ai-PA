"""
Identity lookup utilities for participant name resolution.

Uses the Letta identity service to resolve email addresses to display names
(colloquial names like "Dan" instead of email prefixes like "ddamelin").
"""

import os
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def lookup_participant_names(
    participant_emails: List[str],
    letta_base_url: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, str]:
    """
    Look up display names for participant emails from Letta identity service.

    Args:
        participant_emails: List of email addresses to look up
        letta_base_url: Base URL for Letta API (default: from env or http://letta:8283)
        timeout: Request timeout in seconds

    Returns:
        Dict mapping email -> display name (colloquial name or fallback to email prefix)
    """
    if not participant_emails:
        return {}

    # Get Letta URL
    if letta_base_url is None:
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://letta:8283")

    result: Dict[str, str] = {}

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available, falling back to email prefixes")
        return {email: _email_to_fallback_name(email) for email in participant_emails}

    # Fetch all identities once (more efficient than individual lookups)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{letta_base_url}/v1/identities/")
            response.raise_for_status()
            identities = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch identities from Letta: {e}")
        return {email: _email_to_fallback_name(email) for email in participant_emails}

    # Build lookup index by identifier_key (email)
    identity_by_email: Dict[str, dict] = {}
    for identity in identities:
        identifier_key = identity.get("identifier_key", "").lower()
        if identifier_key:
            identity_by_email[identifier_key] = identity

    # Resolve each participant
    for email in participant_emails:
        email_lower = email.lower()
        identity = identity_by_email.get(email_lower)

        if identity:
            display_name = _extract_display_name(identity)
            result[email] = display_name
        else:
            # Fallback to email prefix
            result[email] = _email_to_fallback_name(email)

    return result


def _extract_display_name(identity: dict) -> str:
    """
    Extract the best display name from an identity record.

    Priority:
    1. colloquial_name property (first name like "Dan")
    2. Full name split to first name
    3. Email prefix from identifier_key
    """
    # Check for colloquial_name in properties
    properties = identity.get("properties", [])
    for prop in properties:
        if prop.get("key") == "colloquial_name":
            value = prop.get("value", "").strip()
            if value:
                return value

    # Fall back to first name from full name
    full_name = identity.get("name", "").strip()
    if full_name:
        # Take first word as first name
        first_name = full_name.split()[0]
        if first_name:
            return first_name

    # Final fallback: email prefix
    identifier_key = identity.get("identifier_key", "")
    return _email_to_fallback_name(identifier_key)


def _email_to_fallback_name(email: str) -> str:
    """
    Convert email to a fallback display name.

    Examples:
        "ddamelin@concord.org" -> "ddamelin"
        "dan.damelin@example.com" -> "dan"
    """
    if not email or "@" not in email:
        return email or "unknown"

    prefix = email.split("@")[0]

    # If prefix contains dots, take first part (likely first name)
    if "." in prefix:
        return prefix.split(".")[0]

    return prefix
