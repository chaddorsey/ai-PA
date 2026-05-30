"""
Identity service for looking up and managing Letta Identities.

Enables staff recognition by platform ID (slack_id, email) and
colloquial name lookup ("Dan" -> Dan Damelin).

Architecture Note (2026-01-26):
- Letta API has no search-by-property, so we list all and filter client-side
- Simple caching reduces API calls for repeated lookups
- Properties format: [{"key": "...", "value": "...", "type": "string"}]
"""

import structlog
from typing import Any, List, Optional

logger = structlog.get_logger()


class IdentityService:
    """
    Wraps Letta Identities API for staff lookup and external user creation.

    Usage:
        service = IdentityService(letta_client)
        identity = service.find_by_property("slack_id", "U02V82YB9")
        if identity:
            calendar_id = service.get_property(identity, "calendar_id")
    """

    def __init__(self, letta_client: Any):
        self.letta = letta_client
        self._cache: Optional[List[Any]] = None

    def find_by_identifier_key(self, identifier_key: str) -> Optional[Any]:
        """
        Find identity by exact identifier_key (canonical identifier, usually email).

        Args:
            identifier_key: The canonical identifier (e.g., "ddamelin@concord.org")

        Returns:
            Identity object if found, None otherwise.
        """
        identities = self._get_all_identities()
        for identity in identities:
            if identity.identifier_key == identifier_key:
                return identity
        return None

    def find_by_property(self, property_key: str, property_value: str) -> Optional[Any]:
        """
        Find identity by property value (e.g., slack_id, calendar_id).

        Args:
            property_key: The property name (e.g., "slack_id")
            property_value: The value to match (e.g., "U02V82YB9")

        Returns:
            Identity object if found, None otherwise.
        """
        identities = self._get_all_identities()

        for identity in identities:
            properties = getattr(identity, 'properties', []) or []
            for prop in properties:
                # Handle both dict and object formats (defensive)
                key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
                value = prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
                if key == property_key and value == property_value:
                    return identity

        return None

    def find_by_colloquial_name(self, name: str) -> Optional[Any]:
        """
        Find identity by colloquial name (case-insensitive).

        Falls back to matching first name of full name if no colloquial_name match.

        Args:
            name: The colloquial name (e.g., "Dan", "Scott")

        Returns:
            Identity object if found, None otherwise.
        """
        identities = self._get_all_identities()
        name_lower = name.lower()

        # First pass: check colloquial_name property
        for identity in identities:
            properties = getattr(identity, 'properties', []) or []
            for prop in properties:
                # Handle both dict and object formats (defensive)
                key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
                value = prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
                if key == 'colloquial_name' and value and value.lower() == name_lower:
                    return identity

        # Second pass: check first name in identity.name
        for identity in identities:
            full_name = getattr(identity, 'name', '') or ''
            first_name = full_name.split()[0] if full_name else ''
            if first_name.lower() == name_lower:
                return identity

        return None

    def create_external_user(
        self,
        platform: str,
        platform_id: str,
        display_name: Optional[str] = None
    ) -> Any:
        """
        Create identity for unknown external user.

        Args:
            platform: Source platform (e.g., "slack", "email")
            platform_id: Platform-specific user ID
            display_name: Optional display name

        Returns:
            Created identity object.
        """
        identifier_key = f"{platform}:{platform_id}"
        properties = [
            {"key": f"{platform}_id", "value": platform_id, "type": "string"},
            {"key": "source", "value": platform, "type": "string"},
        ]

        identity = self.letta.identities.create(
            identifier_key=identifier_key,
            name=display_name or platform_id,
            identity_type="user",
            properties=properties
        )

        # Invalidate cache
        self._cache = None

        logger.info(
            "external_identity_created",
            identity_id=identity.id,
            platform=platform,
            platform_id=platform_id
        )

        return identity

    def list_all_staff(self) -> List[Any]:
        """
        List all identities (for administrative purposes).

        Returns:
            List of all identity objects.
        """
        return self._get_all_identities()

    def get_property(self, identity: Any, key: str) -> Optional[str]:
        """
        Extract property value from identity object.

        Args:
            identity: Identity object with properties list
            key: Property key to find

        Returns:
            Property value if found, None otherwise.
        """
        properties = getattr(identity, 'properties', []) or []
        for prop in properties:
            # Handle both dict and object formats (defensive)
            prop_key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
            if prop_key == key:
                return prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
        return None

    def _get_all_identities(self) -> List[Any]:
        """
        Get all identities with simple caching.

        Returns:
            List of identity objects.
        """
        if self._cache is None:
            try:
                self._cache = list(self.letta.identities.list())
            except Exception as e:
                logger.error("identity_list_failed", error=str(e))
                return []
        return self._cache

    def invalidate_cache(self) -> None:
        """Clear the identity cache (call after creating/modifying identities)."""
        self._cache = None
