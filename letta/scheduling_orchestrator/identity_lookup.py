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

    # Get Letta URL - use localhost since orchestrator runs inside Letta container
    if letta_base_url is None:
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

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


def get_user_preferences_from_identity(
    identity_id: str,
    letta_base_url: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[Dict[str, List[str]]]:
    """
    Fetch scheduling preferences from a Letta identity.

    Looks up the identity by ID and extracts scheduling preference properties:
    - preferred_times (list of strings like "morning", "09:00-11:00")
    - preferred_days (list of strings like "Monday", "Tuesday")
    - avoid_times (list of strings)
    - avoid_days (list of strings)

    Args:
        identity_id: The Letta identity ID to look up
        letta_base_url: Base URL for Letta API (default: from env or http://localhost:8283)
        timeout: Request timeout in seconds

    Returns:
        Dict with preference lists, or None if identity not found
    """
    if not identity_id:
        return None

    # Get Letta URL
    if letta_base_url is None:
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available, cannot fetch identity preferences")
        return None

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{letta_base_url}/v1/identities/{identity_id}")
            if response.status_code == 404:
                logger.debug(f"Identity not found: {identity_id}")
                return None
            response.raise_for_status()
            identity = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch identity {identity_id} from Letta: {e}")
        return None

    return _extract_scheduling_preferences(identity)


def lookup_identity_by_property(
    property_key: str,
    property_value: str,
    letta_base_url: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[dict]:
    """
    Look up an identity by any property key/value pair.

    This enables lookup by slack_id, calendar_id, or any other property.

    Args:
        property_key: The property key to search for (e.g., "slack_id", "calendar_id")
        property_value: The value to match
        letta_base_url: Base URL for Letta API (default: from env or http://localhost:8283)
        timeout: Request timeout in seconds

    Returns:
        The matching identity dict, or None if not found
    """
    if not property_key or not property_value:
        return None

    if letta_base_url is None:
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available, cannot lookup identity by property")
        return None

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{letta_base_url}/v1/identities/")
            response.raise_for_status()
            identities = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch identities from Letta: {e}")
        return None

    # Search for matching property
    for identity in identities:
        # Check identifier_key first (for email lookups)
        if property_key == "email" or property_key == "identifier_key":
            if identity.get("identifier_key", "").lower() == property_value.lower():
                return identity

        # Check properties array
        for prop in identity.get("properties", []):
            if prop.get("key") == property_key and prop.get("value") == property_value:
                return identity

    return None


def resolve_participant_identifier(
    identifier: str,
    letta_base_url: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[str]:
    """
    Resolve any participant identifier (email, Slack ID, etc.) to an email address.

    This is a convenience function that tries multiple lookup strategies:
    1. If identifier looks like an email, return it directly
    2. If identifier looks like a Slack ID (starts with U), look up by slack_id
    3. Otherwise, try looking up by identifier_key

    Args:
        identifier: Email address, Slack ID (U...), or other identifier
        letta_base_url: Base URL for Letta API
        timeout: Request timeout in seconds

    Returns:
        Email address (identifier_key) if found, None otherwise
    """
    if not identifier:
        return None

    # If it looks like an email, return it directly
    if "@" in identifier:
        return identifier

    # If it looks like a Slack ID, look up by slack_id property
    if identifier.startswith("U") and len(identifier) >= 9:
        identity = lookup_identity_by_property("slack_id", identifier, letta_base_url, timeout)
        if identity:
            return identity.get("identifier_key")

    # Try direct identifier_key lookup as fallback
    identity = lookup_identity_by_property("identifier_key", identifier, letta_base_url, timeout)
    if identity:
        return identity.get("identifier_key")

    return None


def _extract_scheduling_preferences(identity: dict) -> Dict[str, List[str]]:
    """
    Extract scheduling preferences from an identity's properties.

    Expected property format:
        {"key": "preferred_times", "value": "morning,09:00-11:00"}
        {"key": "avoid_days", "value": "Friday,Saturday"}

    Args:
        identity: The identity record from Letta API

    Returns:
        Dict with preference lists (empty dict if no preferences found)
    """
    PREFERENCE_KEYS = ["preferred_times", "preferred_days", "avoid_times", "avoid_days"]

    properties = identity.get("properties", [])
    if not properties:
        return {}

    result: Dict[str, List[str]] = {}

    for prop in properties:
        key = prop.get("key", "")
        if key in PREFERENCE_KEYS:
            value = prop.get("value", "")
            if value:
                # Parse comma-separated values into list
                items = [item.strip() for item in value.split(",") if item.strip()]
                if items:
                    result[key] = items

    return result
