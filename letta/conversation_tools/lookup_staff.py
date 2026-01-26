"""
Look up staff member by colloquial name or email.

This tool enables agents to resolve queries like "What's Dan's schedule?"
by looking up the identity and returning relevant properties.

Usage by agent:
    lookup_staff("Dan") -> {"name": "Dan Damelin", "calendar_id": "...", ...}
    lookup_staff("ddamelin@concord.org") -> same result
"""

import os
from typing import Dict, Any, Optional

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        Letta = None


LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Cache for identity service (module-level singleton)
_identity_service_cache: Optional[Any] = None


def _get_identity_service():
    """Get or create IdentityService singleton."""
    global _identity_service_cache

    if _identity_service_cache is None:
        if Letta is None:
            return None

        # Import here to handle both standalone and integrated usage
        try:
            from pa_routing.services.identity_service import IdentityService
            client = Letta(base_url=LETTA_BASE_URL)
            _identity_service_cache = IdentityService(letta_client=client)
        except ImportError:
            # Fallback: create minimal inline implementation
            return _create_minimal_identity_service()

    return _identity_service_cache


def _create_minimal_identity_service():
    """Create minimal identity service when pa_routing not available."""
    if Letta is None:
        return None

    client = Letta(base_url=LETTA_BASE_URL)

    class MinimalIdentityService:
        def __init__(self):
            self._cache = None

        def find_by_colloquial_name(self, name: str):
            name_lower = name.lower()
            for identity in self._get_all():
                colloquial = self._get_prop(identity, "colloquial_name")
                if colloquial and colloquial.lower() == name_lower:
                    return identity
                if identity.name and identity.name.split()[0].lower() == name_lower:
                    return identity
            return None

        def find_by_identifier_key(self, key: str):
            for identity in self._get_all():
                if identity.identifier_key == key:
                    return identity
            return None

        def _get_all(self):
            if self._cache is None:
                self._cache = list(client.identities.list())
            return self._cache

        def _get_prop(self, identity, key):
            for prop in (identity.properties or []):
                if isinstance(prop, dict) and prop.get("key") == key:
                    return prop.get("value")
            return None

    return MinimalIdentityService()


def _extract_properties(identity: Any) -> Dict[str, Any]:
    """Extract all properties from identity into flat dict."""
    result = {
        "name": identity.name,
        "identity_id": identity.id,
        "email": identity.identifier_key,
    }

    for prop in (identity.properties or []):
        if isinstance(prop, dict):
            key = prop.get("key")
            value = prop.get("value")
            if key and value:
                result[key] = value

    return result


def lookup_staff(name_or_email: str) -> Dict[str, Any]:
    """
    Look up staff member by colloquial name or email address.

    This tool resolves staff queries like "What's Dan's schedule?" by
    finding the identity and returning all known properties.

    Args:
        name_or_email: Colloquial name (e.g., "Dan") or email address

    Returns:
        Dict with staff properties: name, email, identity_id, slack_id,
        calendar_id, colloquial_name, working_hours, working_week.
        Or dict with "error" key if not found.

    Example:
        >>> lookup_staff("Dan")
        {
            "name": "Dan Damelin",
            "identity_id": "identity-123",
            "email": "ddamelin@concord.org",
            "slack_id": "U0303SG91",
            "calendar_id": "ddamelin@concord.org",
            "colloquial_name": "Dan"
        }
    """
    service = _get_identity_service()
    if service is None:
        return {"error": "Identity service not available"}

    # Try colloquial name first
    identity = service.find_by_colloquial_name(name_or_email)

    # Fall back to email lookup
    if identity is None and "@" in name_or_email:
        identity = service.find_by_identifier_key(name_or_email)

    if identity is None:
        return {"error": f"Staff member '{name_or_email}' not found"}

    return _extract_properties(identity)
