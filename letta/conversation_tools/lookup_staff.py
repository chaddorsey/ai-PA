"""
Look up staff member by colloquial name or email.

This tool enables agents to resolve queries like "What's Dan's schedule?"
by looking up the identity and returning relevant properties.

Usage by agent:
    lookup_staff("Dan") -> {"name": "Dan Damelin", "calendar_id": "...", ...}
    lookup_staff("ddamelin@concord.org") -> same result
"""

from typing import Dict, Any, Optional


def lookup_staff(name_or_email: str) -> Dict[str, Any]:
    """
    Look up staff member by colloquial name or email address.

    This tool resolves staff queries like "What's Dan's schedule?" by
    finding the identity and returning all known properties.

    Args:
        name_or_email: Colloquial name (e.g., "Dan") or email address

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - name: Full name of staff member (if found)
        - identity_id: Letta identity ID (if found)
        - email: Email address / identifier_key (if found)
        - slack_id: Slack user ID (if available)
        - calendar_id: Google calendar ID (if available)
        - colloquial_name: Short name (if available)
        - working_hours: Working hours (if available)
        - working_week: Working days (if available)
        - error_message: Error message if status is "error"

    Example:
        >>> lookup_staff("Dan")
        {
            "status": "ok",
            "name": "Dan Damelin",
            "identity_id": "identity-123",
            "email": "ddamelin@concord.org",
            "slack_id": "U0303SG91",
            "calendar_id": "ddamelin@concord.org",
            "colloquial_name": "Dan"
        }
    """
    # IMPORTS FIRST - inside function for Letta tool extraction
    import os
    import traceback

    try:
        from letta_client import Letta
    except ImportError:
        try:
            from letta import Letta
        except ImportError:
            Letta = None

    # TRY-EXCEPT WRAPPER
    try:
        # CONFIGURATION - inside function for Letta tool extraction
        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

        # CHECK LETTA AVAILABILITY
        if Letta is None:
            return {
                "status": "error",
                "error_message": "Letta client not available"
            }

        # GET LETTA CLIENT AND ALL IDENTITIES (inline, no helper function)
        client = Letta(base_url=letta_base_url)
        all_identities = list(client.identities.list())

        # SEARCH PARAMETER
        search_lower = name_or_email.lower()
        found_identity = None

        # FIRST PASS: FIND BY COLLOQUIAL NAME (inline logic, no nested def)
        for identity in all_identities:
            # Get colloquial_name from properties (inline _get_prop logic)
            colloquial = None
            for prop in (getattr(identity, 'properties', None) or []):
                if isinstance(prop, dict) and prop.get("key") == "colloquial_name":
                    colloquial = prop.get("value")
                    break

            # Check if colloquial name matches
            if colloquial and colloquial.lower() == search_lower:
                found_identity = identity
                break

            # Check if first name of full name matches
            full_name = getattr(identity, 'name', '') or ''
            if full_name:
                first_name = full_name.split()[0] if full_name.split() else ''
                if first_name.lower() == search_lower:
                    found_identity = identity
                    break

        # SECOND PASS: FIND BY EMAIL/IDENTIFIER_KEY (if not found and contains @)
        if found_identity is None and "@" in name_or_email:
            for identity in all_identities:
                if getattr(identity, 'identifier_key', '') == name_or_email:
                    found_identity = identity
                    break

        # NOT FOUND
        if found_identity is None:
            return {
                "status": "error",
                "error_message": f"Staff member '{name_or_email}' not found"
            }

        # EXTRACT PROPERTIES (inline _extract_properties logic)
        result = {
            "status": "ok",
            "name": getattr(found_identity, 'name', None),
            "identity_id": getattr(found_identity, 'id', None),
            "email": getattr(found_identity, 'identifier_key', None),
        }

        # Extract all properties into flat dict
        for prop in (getattr(found_identity, 'properties', None) or []):
            if isinstance(prop, dict):
                key = prop.get("key")
                value = prop.get("value")
                if key and value:
                    result[key] = value

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to lookup staff: {str(e)}\n{traceback.format_exc()}"
        }
