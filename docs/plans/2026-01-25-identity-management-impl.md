# Identity Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement unified identity management using Letta Identities for staff recognition, colloquial lookup, and cross-platform memory coherence.

**Architecture:** Staff identities are pre-populated via migration script. ConversationService looks up identities by platform ID (slack_id, email) before creating conversations. An IdentityService wraps the Letta API for identity operations. A lookup_staff tool enables agents to resolve colloquial references.

**Tech Stack:** Python 3.9+, Letta API (identities endpoint), Supabase (user_conversations table), pytest

**Design Reference:** `docs/plans/2026-01-25-identity-management-design.md`

---

## API Discovery Notes

The Letta Identities API (v0.16.3) works as follows:
- **Create:** `POST /v1/identities/` with `identifier_key`, `name`, `identity_type`, `properties`
- **Properties format:** List of `{"key": "...", "value": "...", "type": "string"}`
- **List:** `GET /v1/identities/` returns all identities
- **Search:** `GET /v1/identities/?identifier_key=xxx` filters by identifier_key
- **Delete:** `DELETE /v1/identities/{id}`

No direct search by property value - must list all and filter client-side.

---

## Task 1: Create IdentityService

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/identity_service.py`
- Modify: `pa-routing-handler/src/pa_routing/services/__init__.py`
- Test: `pa-routing-handler/tests/services/test_identity_service.py`

### Step 1: Write the failing test

```python
# pa-routing-handler/tests/services/test_identity_service.py
"""Tests for identity service."""

import pytest
from unittest.mock import MagicMock, patch


class TestIdentityService:
    """Tests for Letta identity management."""

    @pytest.fixture
    def mock_letta_client(self):
        """Create mock Letta client."""
        client = MagicMock()
        client.identities = MagicMock()
        return client

    def test_find_by_identifier_key_returns_identity(self, mock_letta_client):
        """Returns identity when identifier_key matches."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-123"
        mock_identity.identifier_key = "scytacki@concord.org"
        mock_identity.name = "Scott Cytacki"
        mock_identity.properties = [
            {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
            {"key": "colloquial_name", "value": "Scott", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [mock_identity]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("scytacki@concord.org")

        assert result is not None
        assert result.id == "identity-123"
        assert result.name == "Scott Cytacki"

    def test_find_by_identifier_key_returns_none_when_not_found(self, mock_letta_client):
        """Returns None when no identity matches."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = []

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("unknown@example.com")

        assert result is None

    def test_find_by_property_returns_identity(self, mock_letta_client):
        """Returns identity when property matches."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-123"
        mock_identity.identifier_key = "scytacki@concord.org"
        mock_identity.name = "Scott Cytacki"
        mock_identity.properties = [
            {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [mock_identity]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_property("slack_id", "U02V82YB9")

        assert result is not None
        assert result.id == "identity-123"

    def test_find_by_property_returns_none_when_not_found(self, mock_letta_client):
        """Returns None when no property matches."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.properties = [
            {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [mock_identity]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_property("slack_id", "UXXXXXXXX")

        assert result is None

    def test_find_by_colloquial_name_returns_identity(self, mock_letta_client):
        """Returns identity when colloquial_name matches (case-insensitive)."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-123"
        mock_identity.name = "Dan Damelin"
        mock_identity.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [mock_identity]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("dan")  # lowercase

        assert result is not None
        assert result.name == "Dan Damelin"

    def test_find_by_colloquial_name_falls_back_to_first_name(self, mock_letta_client):
        """Falls back to matching first name if no colloquial_name property."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-123"
        mock_identity.name = "Scott Cytacki"
        mock_identity.properties = []  # No colloquial_name
        mock_letta_client.identities.list.return_value = [mock_identity]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("Scott")

        assert result is not None
        assert result.name == "Scott Cytacki"

    def test_create_external_user_creates_identity(self, mock_letta_client):
        """Creates minimal identity for unknown external user."""
        from pa_routing.services.identity_service import IdentityService

        mock_created = MagicMock()
        mock_created.id = "identity-new-123"
        mock_letta_client.identities.create.return_value = mock_created

        service = IdentityService(letta_client=mock_letta_client)
        result = service.create_external_user(
            platform="slack",
            platform_id="UNEWUSER1"
        )

        assert result.id == "identity-new-123"
        mock_letta_client.identities.create.assert_called_once()
        call_kwargs = mock_letta_client.identities.create.call_args[1]
        assert call_kwargs["identifier_key"] == "slack:UNEWUSER1"
        assert call_kwargs["identity_type"] == "user"

    def test_list_all_staff_returns_user_identities(self, mock_letta_client):
        """Returns all identities with identity_type=user."""
        from pa_routing.services.identity_service import IdentityService

        mock_staff1 = MagicMock()
        mock_staff1.identity_type = "user"
        mock_staff2 = MagicMock()
        mock_staff2.identity_type = "user"
        mock_agent = MagicMock()
        mock_agent.identity_type = "agent"

        mock_letta_client.identities.list.return_value = [mock_staff1, mock_staff2, mock_agent]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.list_all_staff()

        assert len(result) == 2
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_identity_service.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pa_routing.services.identity_service'`

### Step 3: Write minimal implementation

```python
# pa-routing-handler/src/pa_routing/services/identity_service.py
"""
Identity service for Letta identity management.

Provides lookup and creation of Letta identities for:
- Staff recognition by platform ID (slack_id, email)
- Colloquial name resolution ("Dan" -> Dan Damelin)
- External user identity creation
"""

import structlog
from typing import Any, List, Optional

logger = structlog.get_logger()


class IdentityService:
    """
    Manages Letta Identities for user recognition and lookup.

    Identities store stable user data (email, slack_id, calendar_id, colloquial_name)
    that is shared across all agents and used for:
    - Recognizing who is messaging the bot
    - Resolving colloquial references ("What's Dan's schedule?")
    - Cross-platform user linking
    """

    def __init__(self, letta_client: Any):
        """
        Initialize identity service.

        Args:
            letta_client: Letta client instance with identities API
        """
        self.letta = letta_client
        self._cache: Optional[List[Any]] = None
        self._cache_valid = False

    def _get_all_identities(self) -> List[Any]:
        """Fetch all identities, with simple caching."""
        if self._cache_valid and self._cache is not None:
            return self._cache
        try:
            self._cache = list(self.letta.identities.list())
            self._cache_valid = True
            return self._cache
        except Exception as e:
            logger.error("identity_list_failed", error=str(e))
            return []

    def invalidate_cache(self) -> None:
        """Invalidate the identity cache after mutations."""
        self._cache_valid = False
        self._cache = None

    def find_by_identifier_key(self, identifier_key: str) -> Optional[Any]:
        """
        Find identity by its canonical identifier_key (usually email).

        Args:
            identifier_key: The canonical identifier (e.g., "scytacki@concord.org")

        Returns:
            Identity object if found, None otherwise
        """
        try:
            # Use API filter if available
            results = self.letta.identities.list(identifier_key=identifier_key)
            results_list = list(results)
            if results_list:
                return results_list[0]
            return None
        except Exception as e:
            logger.warning("identity_lookup_by_key_failed", error=str(e), key=identifier_key)
            return None

    def find_by_property(self, property_key: str, property_value: str) -> Optional[Any]:
        """
        Find identity by a property value (e.g., slack_id).

        Args:
            property_key: The property key to search (e.g., "slack_id")
            property_value: The value to match (e.g., "U02V82YB9")

        Returns:
            Identity object if found, None otherwise
        """
        identities = self._get_all_identities()

        for identity in identities:
            properties = getattr(identity, 'properties', []) or []
            for prop in properties:
                # Handle both dict and object formats
                key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
                value = prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
                if key == property_key and value == property_value:
                    return identity

        return None

    def find_by_colloquial_name(self, name: str) -> Optional[Any]:
        """
        Find identity by colloquial name (case-insensitive).

        First checks the 'colloquial_name' property, then falls back to
        matching the first part of the identity's full name.

        Args:
            name: Colloquial name to search (e.g., "Dan", "Scott")

        Returns:
            Identity object if found, None otherwise
        """
        identities = self._get_all_identities()
        name_lower = name.lower()

        # First pass: check colloquial_name property
        for identity in identities:
            properties = getattr(identity, 'properties', []) or []
            for prop in properties:
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
        Create a minimal identity for an unknown external user.

        Args:
            platform: Source platform ("slack", "email", "web")
            platform_id: Platform-specific user ID
            display_name: Optional display name

        Returns:
            Created identity object
        """
        identifier_key = f"{platform}:{platform_id}"
        name = display_name or f"User {platform_id[:8]}"

        properties = [
            {"key": f"{platform}_id", "value": platform_id, "type": "string"},
            {"key": "source", "value": platform, "type": "string"},
        ]

        try:
            identity = self.letta.identities.create(
                identifier_key=identifier_key,
                name=name,
                identity_type="user",
                properties=properties
            )
            self.invalidate_cache()
            logger.info("external_identity_created", identity_id=identity.id, platform=platform)
            return identity
        except Exception as e:
            logger.error("external_identity_creation_failed", error=str(e))
            raise

    def list_all_staff(self) -> List[Any]:
        """
        List all staff identities (identity_type=user).

        Returns:
            List of identity objects
        """
        identities = self._get_all_identities()
        return [i for i in identities if getattr(i, 'identity_type', '') == 'user']

    def get_property(self, identity: Any, key: str) -> Optional[str]:
        """
        Helper to extract a property value from an identity.

        Args:
            identity: Identity object
            key: Property key to extract

        Returns:
            Property value if found, None otherwise
        """
        properties = getattr(identity, 'properties', []) or []
        for prop in properties:
            prop_key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
            if prop_key == key:
                return prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
        return None
```

### Step 4: Update services __init__.py

```python
# pa-routing-handler/src/pa_routing/services/__init__.py
"""Business logic services."""

from .conversation_service import ConversationService
from .identity_service import IdentityService

__all__ = ["ConversationService", "IdentityService"]
```

### Step 5: Run test to verify it passes

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_identity_service.py -v
```
Expected: PASS (8 tests)

### Step 6: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/identity_service.py
git add pa-routing-handler/src/pa_routing/services/__init__.py
git add pa-routing-handler/tests/services/test_identity_service.py
git commit -m "feat: add IdentityService for Letta identity management"
```

---

## Task 2: Staff Directory Migration Script

**Files:**
- Create: `scripts/migrate_staff_to_identities.py`

### Step 1: Create the migration script

```python
#!/usr/bin/env python3
"""
Migrate staff directory from memory block to Letta Identities.

This script reads the staff data (hardcoded from the memory block export)
and creates Letta Identities for each staff member with their platform IDs.

Usage:
    python scripts/migrate_staff_to_identities.py [--dry-run]
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client or letta package not found")
        print("Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Staff directory data (from memory block export)
STAFF_DIRECTORY: List[Dict[str, Any]] = [
    {
        "name": "Ethan McElroy",
        "email": "emcelroy@concord.org",
        "slack_id": "U02V96MQC",
        "calendar_id": "emcelroy@concord.org",
        "colloquial_name": "Ethan",
    },
    {
        "name": "Kirk Swenson",
        "email": "kswenson@concord.org",
        "slack_id": "U0GQHHS1W",
        "calendar_id": "kswenson@concord.org",
        "colloquial_name": "Kirk",
        "working_hours": "11:30AM-7:30PM",
    },
    {
        "name": "Scott Cytacki",
        "email": "scytacki@concord.org",
        "slack_id": "U02V82YB9",
        "calendar_id": "scytacki@concord.org",
        "colloquial_name": "Scott",
    },
    {
        "name": "Paul Horwitz",
        "email": "phorwitz@concord.org",
        "slack_id": "U031V0J1M",
        "calendar_id": "phorwitz@concord.org",
        "colloquial_name": "Paul",
    },
    {
        "name": "Hee-Sun Lee",
        "email": "hlee@concord.org",
        "slack_id": "U09M9UU3A",
        "calendar_id": "hlee@concord.org",
        "colloquial_name": "Hee-Sun",
        "working_hours": "12:00PM-5:00PM",
    },
    {
        "name": "Trudi Lord",
        "email": "tlord@concord.org",
        "slack_id": "U02V941L0",
        "calendar_id": "tlord@concord.org",
        "colloquial_name": "Trudi",
    },
    {
        "name": "Dan Damelin",
        "email": "ddamelin@concord.org",
        "slack_id": "U0303SG91",
        "calendar_id": "ddamelin@concord.org",
        "colloquial_name": "Dan",
    },
    {
        "name": "Judi Raiff",
        "email": "jraiff@concord.org",
        "slack_id": "U48DTGUGJ",
        "calendar_id": "jraiff@concord.org",
        "colloquial_name": "Judi",
    },
    {
        "name": "Cynthia McIntyre",
        "email": "cmcintyre@concord.org",
        "slack_id": "U09DXRLAH",
        "calendar_id": "cmcintyre@concord.org",
        "colloquial_name": "Cynthia",
    },
    {
        "name": "Bill Finzer",
        "email": "wfinzer@concord.org",
        "slack_id": "U02VCM7TL",
        "calendar_id": "wfinzer@concord.org",
        "colloquial_name": "Bill",
        "working_hours": "11:00AM-7:00PM",
    },
    {
        "name": "Kiley Brown",
        "email": "kbrown@concord.org",
        "slack_id": None,  # Missing
        "calendar_id": "kbrown@concord.org",
        "colloquial_name": "Kiley",
    },
    {
        "name": "Leslie Bondaryk",
        "email": "lbondaryk@concord.org",
        "slack_id": "UACG5LG3Y",
        "calendar_id": "lbondaryk@concord.org",
        "colloquial_name": "Leslie",
        "working_week": "Monday-Thursday",
    },
    {
        "name": "Jie Chao",
        "email": "jchao@concord.org",
        "slack_id": "U0AEJSLQJ",
        "calendar_id": "jchao@concord.org",
        "colloquial_name": "Jie",
    },
    {
        "name": "Amy Pallant",
        "email": "apallant@concord.org",
        "slack_id": "U09LTDGKX",
        "calendar_id": "apallant@concord.org",
        "colloquial_name": "Amy",
        "working_week": "Monday-Thursday",
    },
    {
        "name": "Chris Lore",
        "email": "clore@concord.org",
        "slack_id": "UG8PJCU1L",
        "calendar_id": "clore@concord.org",
        "colloquial_name": "Chris",
        "working_week": "Monday-Thursday",
    },
    {
        "name": "Kate Miller",
        "email": "kmiller@concord.org",
        "slack_id": "U04DMBL0YAU",
        "calendar_id": "kmiller@concord.org",
        "colloquial_name": "Kate",
    },
    {
        "name": "Kathy Jessen Eller",
        "email": "kjesseneller@concord.org",
        "slack_id": "U0836P6REKF",
        "calendar_id": "kjesseneller@concord.org",
        "colloquial_name": "Kathy",
    },
    {
        "name": "Rebecca Ellis",
        "email": "rellis@concord.org",
        "slack_id": "UK486BUSX",
        "calendar_id": "rellis@concord.org",
        "colloquial_name": "Rebecca",
    },
    {
        "name": "Teale Fristoe",
        "email": "tfristoe@concord.org",
        "slack_id": "U03HRBXLJ12",
        "calendar_id": "tfristoe@concord.org",
        "colloquial_name": "Teale",
    },
    {
        "name": "Lisa Buoncuore",
        "email": "lbuoncuore@concord.org",
        "slack_id": "U09DZHHPT",
        "calendar_id": "lbuoncuore@concord.org",
        "colloquial_name": "Lisa",
    },
    {
        "name": "Danielle Kehoe",
        "email": "dkehoe@concord.org",
        "slack_id": "U09B5JUK2TY",
        "calendar_id": "dkehoe@concord.org",
        "colloquial_name": "Danielle",
    },
    {
        "name": "Sue Brau",
        "email": "sbrau@concord.org",
        "slack_id": "U09C3N5LZ",
        "calendar_id": "sbrau@concord.org",
        "colloquial_name": "Sue",
    },
    {
        "name": "Doug Martin",
        "email": "dmartin@concord.org",
        "slack_id": "U048JG9CU",
        "calendar_id": "dmartin@concord.org",
        "colloquial_name": "Doug",
    },
    {
        "name": "Lynn Stephens",
        "email": "lstephens@concord.org",
        "slack_id": "U7DMA61BN",
        "calendar_id": "lstephens@concord.org",
        "colloquial_name": "Lynn",
    },
    {
        "name": "Michael Tirenin",
        "email": "mtirenin@concord.org",
        "slack_id": "UBRAAE2FM",
        "calendar_id": "mtirenin@concord.org",
        "colloquial_name": "Michael",
    },
    {
        "name": "Aditi Wagh",
        "email": "awagh@concord.org",
        "slack_id": "U096MABDPNF",
        "calendar_id": "awagh@concord.org",
        "colloquial_name": "Aditi",
    },
]

# Family directory data
FAMILY_DIRECTORY: List[Dict[str, Any]] = [
    {
        "name": "Sophia Dorsey",
        "email": "sophiadorsey@gmail.com",
        "calendar_id": "sb06g6b1g2jlkplc1bcd7k4ofk@group.calendar.google.com",
        "colloquial_name": "Sophia",
        "imessage": "sophiadorsey@gmail.com",
    },
    {
        "name": "Liam Dorsey",
        "email": "liamdorsey00@gmail.com",
        "calendar_id": "cr89gktnjrcrtm9j9a48j060hc@group.calendar.google.com",
        "colloquial_name": "Liam",
        "imessage": "liamdorsey00@gmail.com",
    },
    {
        "name": "Liz Dorsey",
        "email": "lizdorsey@gmail.com",
        "calendar_id": "lizdorsey@gmail.com",
        "colloquial_name": "Liz",
        "imessage": "lizdorsey@gmail.com",
    },
    {
        "name": "Chad Dorsey",
        "email": "cdorsey@concord.org",
        "calendar_id": "concord.org_ouqdctthtvfm6bklntoq2rbg9s@group.calendar.google.com",
        "colloquial_name": "Chad",
        "imessage": "chaddorsey@gmail.com",
        "personal_email": "chaddorsey@gmail.com",
    },
]


def build_properties(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build properties list from staff/family data."""
    properties = []

    # Always include colloquial_name
    if data.get("colloquial_name"):
        properties.append({
            "key": "colloquial_name",
            "value": data["colloquial_name"],
            "type": "string"
        })

    # Platform IDs
    if data.get("slack_id"):
        properties.append({
            "key": "slack_id",
            "value": data["slack_id"],
            "type": "string"
        })

    if data.get("calendar_id"):
        properties.append({
            "key": "calendar_id",
            "value": data["calendar_id"],
            "type": "string"
        })

    # Optional fields
    if data.get("working_hours"):
        properties.append({
            "key": "working_hours",
            "value": data["working_hours"],
            "type": "string"
        })

    if data.get("working_week"):
        properties.append({
            "key": "working_week",
            "value": data["working_week"],
            "type": "string"
        })

    if data.get("imessage"):
        properties.append({
            "key": "imessage",
            "value": data["imessage"],
            "type": "string"
        })

    if data.get("personal_email"):
        properties.append({
            "key": "personal_email",
            "value": data["personal_email"],
            "type": "string"
        })

    return properties


def create_identity(client, data: Dict[str, Any], category: str, dry_run: bool = False) -> bool:
    """Create a single identity."""
    email = data["email"]
    name = data["name"]
    properties = build_properties(data)

    print(f"  {name} ({email})")
    for prop in properties:
        print(f"    - {prop['key']}: {prop['value']}")

    if dry_run:
        print("    [DRY RUN - not created]")
        return True

    try:
        identity = client.identities.create(
            identifier_key=email,
            name=name,
            identity_type="user",
            properties=properties
        )
        print(f"    Created: {identity.id}")
        return True
    except Exception as e:
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            print(f"    Already exists, skipping")
            return True
        else:
            print(f"    ERROR: {e}")
            return False


def main():
    """Run the migration."""
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("Staff Directory Migration to Letta Identities")
    print("=" * 60)
    print(f"\nLetta Base URL: {LETTA_BASE_URL}")
    print(f"Dry Run: {dry_run}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")
    except Exception as e:
        print(f"Failed to connect to Letta: {e}")
        return 1

    created = 0
    failed = 0

    # Migrate staff
    print(f"Migrating {len(STAFF_DIRECTORY)} staff members...")
    print("-" * 40)
    for staff in STAFF_DIRECTORY:
        if create_identity(client, staff, "staff", dry_run):
            created += 1
        else:
            failed += 1

    print()

    # Migrate family
    print(f"Migrating {len(FAMILY_DIRECTORY)} family members...")
    print("-" * 40)
    for family in FAMILY_DIRECTORY:
        if create_identity(client, family, "family", dry_run):
            created += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print(f"Migration Complete: {created} created, {failed} failed")
    print("=" * 60)

    if dry_run:
        print("\nThis was a dry run. Run without --dry-run to create identities.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

### Step 2: Run dry-run to verify

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python scripts/migrate_staff_to_identities.py --dry-run
```
Expected: Lists all 30 people (26 staff + 4 family) with their properties, marked as `[DRY RUN]`

### Step 3: Run actual migration

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python scripts/migrate_staff_to_identities.py
```
Expected: `Migration Complete: 30 created, 0 failed`

### Step 4: Verify identities were created

Run:
```bash
curl -s http://localhost:8283/v1/identities/ | python3 -m json.tool | head -100
```
Expected: List of identities with properties including slack_id, calendar_id, colloquial_name

### Step 5: Commit

```bash
git add scripts/migrate_staff_to_identities.py
git commit -m "feat: add staff directory migration script for Letta Identities"
```

---

## Task 3: Update ConversationService to Use Identity Lookup

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/conversation_service.py`
- Modify: `pa-routing-handler/tests/services/test_conversation_service.py`

### Step 1: Write failing tests for identity integration

Add these tests to `test_conversation_service.py`:

```python
# Add to existing test file

    @pytest.fixture
    def mock_identity_service(self):
        """Create mock IdentityService."""
        from unittest.mock import MagicMock
        service = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_uses_existing_identity_for_known_staff(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Uses existing staff identity when slack_id matches."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Staff identity exists
        mock_staff_identity = MagicMock()
        mock_staff_identity.id = "identity-staff-scott"
        mock_staff_identity.name = "Scott Cytacki"
        mock_identity_service.find_by_property.return_value = mock_staff_identity

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-123"
        mock_letta_client.conversations.create.return_value = mock_conversation

        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="U02V82YB9",  # Scott's Slack ID
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should have looked up by slack_id
        mock_identity_service.find_by_property.assert_called_with("slack_id", "U02V82YB9")

        # Should use existing identity, not create new one
        mock_letta_client.identities.create.assert_not_called()

        # Result should include the staff identity
        assert result["identity_id"] == "identity-staff-scott"

    @pytest.mark.asyncio
    async def test_creates_external_identity_for_unknown_user(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Creates external identity when no staff match found."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # No staff identity match
        mock_identity_service.find_by_property.return_value = None

        # External identity will be created
        mock_external_identity = MagicMock()
        mock_external_identity.id = "identity-external-123"
        mock_identity_service.create_external_user.return_value = mock_external_identity

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-456"
        mock_letta_client.conversations.create.return_value = mock_conversation

        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="UNEWUSER99",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should have created external identity
        mock_identity_service.create_external_user.assert_called_with(
            platform="slack",
            platform_id="UNEWUSER99",
            display_name=None
        )

        assert result["identity_id"] == "identity-external-123"
```

### Step 2: Run tests to verify they fail

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py::TestConversationService::test_uses_existing_identity_for_known_staff -v
```
Expected: FAIL (TypeError or identity_service not accepted)

### Step 3: Update ConversationService implementation

```python
# pa-routing-handler/src/pa_routing/services/conversation_service.py
"""
Conversation service for managing user→conversation mappings.

Handles:
- Looking up existing conversations for user+agent pairs
- Creating new conversations with Letta Conversations API
- Resolving user identity via IdentityService before conversation creation
- Creating initial user blocks on onboarding (with naming conventions)
- Tracking conversation activity via last_active_at

Architecture Note (2026-01-26):
- Uses IdentityService to recognize known staff by platform ID
- Falls back to creating external identity for unknown users
- Block naming uses identity_id for cross-platform coherence
"""

import structlog
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = structlog.get_logger()

# Default scheduler agent ID
SCHEDULER_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
AGENT_NAME = "meeting_scheduler"


class ConversationService:
    """
    Manages Letta Conversations for multi-user agent access.

    Each user gets a unique conversation with the agent, enabling:
    - Isolated message history (context) per user
    - Per-user memory blocks via identity-based naming
    - Activity tracking for potential TTL/cleanup
    """

    def __init__(
        self,
        letta_client: Any,
        supabase_client: Any,
        identity_service: Optional[Any] = None
    ):
        """
        Initialize the conversation service.

        Args:
            letta_client: Letta client instance
            supabase_client: Supabase client instance
            identity_service: Optional IdentityService for staff lookup
        """
        self.letta = letta_client
        self.supabase = supabase_client
        self.identity_service = identity_service

    async def get_or_create_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get existing conversation or create new one for user+agent pair.

        This is the main entry point for conversation resolution. If a mapping
        exists in Supabase, returns the existing conversation_id. Otherwise,
        resolves the user's identity and creates a new conversation.

        Args:
            user_id: External user identifier (e.g., Slack user ID "U12345678")
            user_source: Source platform ("slack", "email", "web")
            agent_id: Letta agent ID to converse with
            display_name: Optional user display name for identity
            email: Optional user email for identity

        Returns:
            dict with keys:
            - conversation_id: The Letta conversation ID
            - identity_id: The Letta identity ID
            - created: bool indicating if this is a new conversation
            - error: Only present if there was an error
        """
        # Try to find existing conversation
        existing = await self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            logger.info(
                "conversation_found",
                user_id=user_id,
                conversation_id=existing["conversation_id"]
            )
            return {
                "conversation_id": existing["conversation_id"],
                "identity_id": existing.get("identity_id"),
                "created": False
            }

        # Resolve identity before creating conversation
        identity = await self._resolve_identity(
            user_id=user_id,
            user_source=user_source,
            display_name=display_name,
            email=email
        )

        # Create new conversation
        logger.info(
            "conversation_creating",
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            identity_id=identity.id if identity else None
        )
        return await self._onboard_user(
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            identity=identity,
            display_name=display_name or user_id,
            email=email
        )

    async def _resolve_identity(
        self,
        user_id: str,
        user_source: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[Any]:
        """
        Resolve user identity from platform ID.

        First checks if user matches a known staff identity by platform ID.
        If not found, creates a minimal external identity.

        Args:
            user_id: Platform-specific user ID
            user_source: Source platform
            display_name: Optional display name
            email: Optional email

        Returns:
            Identity object (existing staff or newly created external)
        """
        if not self.identity_service:
            return None

        # Map platform to property key
        property_key = f"{user_source}_id"  # e.g., "slack_id"

        # Try to find existing identity by platform ID
        identity = self.identity_service.find_by_property(property_key, user_id)
        if identity:
            logger.info(
                "staff_identity_found",
                user_id=user_id,
                identity_id=identity.id,
                identity_name=getattr(identity, 'name', 'Unknown')
            )
            return identity

        # Try by email if provided
        if email:
            identity = self.identity_service.find_by_identifier_key(email)
            if identity:
                logger.info(
                    "staff_identity_found_by_email",
                    user_id=user_id,
                    email=email,
                    identity_id=identity.id
                )
                return identity

        # Create external identity for unknown user
        try:
            identity = self.identity_service.create_external_user(
                platform=user_source,
                platform_id=user_id,
                display_name=display_name
            )
            logger.info(
                "external_identity_created",
                user_id=user_id,
                identity_id=identity.id
            )
            return identity
        except Exception as e:
            logger.warning("identity_resolution_failed", error=str(e), user_id=user_id)
            return None

    async def _lookup_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Look up existing conversation in Supabase.

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID

        Returns:
            dict with conversation_id and identity_id if found, None otherwise
        """
        try:
            result = (
                self.supabase.table("user_conversations")
                .select("conversation_id, identity_id")
                .eq("user_id", user_id)
                .eq("user_source", user_source)
                .eq("agent_id", agent_id)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("conversation_lookup_failed", error=str(e), user_id=user_id)
            return None

    async def _onboard_user(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        identity: Optional[Any],
        display_name: str,
        email: Optional[str]
    ) -> Dict[str, Any]:
        """
        Create conversation and initial resources for new user.

        This creates:
        1. Initial preference block with identity-based naming
        2. Initial calendar block with identity-based naming
        3. Letta conversation
        4. Supabase mapping record

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID
            identity: Resolved identity object (or None)
            display_name: User display name
            email: Optional user email

        Returns:
            dict with conversation_id, identity_id, and created=True
        """
        identity_id = identity.id if identity else None

        # Use identity_id for block naming if available, otherwise fall back to user_id
        block_user_key = identity_id if identity_id else user_id
        block_ids = []

        # Create initial preference block with naming convention
        try:
            pref_block = self.letta.blocks.create(
                label=f"preferences_{block_user_key}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {display_name}",
                limit=2000
            )
            block_ids.append(pref_block.id)

            # Attach to agent
            self.letta.agents.blocks.attach(
                agent_id=agent_id,
                block_id=pref_block.id
            )
            logger.info("preference_block_created", user_id=user_id, block_id=pref_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="preferences")

        # Create initial calendar block with naming convention
        try:
            cal_block = self.letta.blocks.create(
                label=f"calendar_{block_user_key}",
                value="Calendar integration pending configuration. This block stores calendar context for this user.",
                description=f"Calendar integration for {display_name}",
                limit=2000
            )
            block_ids.append(cal_block.id)

            # Attach to agent
            self.letta.agents.blocks.attach(
                agent_id=agent_id,
                block_id=cal_block.id
            )
            logger.info("calendar_block_created", user_id=user_id, block_id=cal_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="calendar")

        # Create conversation
        try:
            conversation = self.letta.conversations.create(
                agent_id=agent_id,
                label=f"{display_name} - {user_source.capitalize()}"
            )
            conversation_id = conversation.id
            logger.info("conversation_created", user_id=user_id, conversation_id=conversation_id)
        except Exception as e:
            logger.error("conversation_creation_failed", error=str(e), user_id=user_id)
            return {
                "error": f"Failed to create conversation: {str(e)}",
                "created": False
            }

        # Store mapping in Supabase
        try:
            self.supabase.table("user_conversations").insert({
                "user_id": user_id,
                "user_source": user_source,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "identity_id": identity_id
            }).execute()
            logger.info("mapping_stored", user_id=user_id, conversation_id=conversation_id)
        except Exception as e:
            logger.error(
                "conversation_mapping_insert_failed",
                error=str(e),
                user_id=user_id,
                conversation_id=conversation_id
            )
            # Don't fail the whole operation - conversation was created successfully

        logger.info(
            "user_onboarded",
            user_id=user_id,
            conversation_id=conversation_id,
            identity_id=identity_id,
            block_count=len(block_ids)
        )

        return {
            "conversation_id": conversation_id,
            "identity_id": identity_id,
            "created": True
        }

    async def update_last_active(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> None:
        """
        Update last_active_at timestamp for a conversation.

        This is called after each message to track activity for potential
        TTL/cleanup operations.

        Args:
            user_id: External user identifier
            user_source: Source platform
            agent_id: Letta agent ID
        """
        try:
            self.supabase.table("user_conversations").update({
                "last_active_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("user_source", user_source).eq("agent_id", agent_id).execute()
            logger.debug("last_active_updated", user_id=user_id)
        except Exception as e:
            logger.warning("last_active_update_failed", error=str(e), user_id=user_id)
```

### Step 4: Run tests to verify they pass

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v
```
Expected: PASS (all tests including new identity integration tests)

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/conversation_service.py
git add pa-routing-handler/tests/services/test_conversation_service.py
git commit -m "feat: integrate IdentityService into ConversationService for staff recognition"
```

---

## Task 4: Create lookup_staff Agent Tool

**Files:**
- Create: `letta/conversation_tools/lookup_staff.py`
- Create: `letta/conversation_tools/tests/test_lookup_staff.py`
- Modify: `letta/conversation_tools/__init__.py`

### Step 1: Write failing test

```python
# letta/conversation_tools/tests/test_lookup_staff.py
"""Tests for lookup_staff tool."""

import pytest
from unittest.mock import MagicMock, patch


class TestLookupStaff:
    """Tests for staff lookup by colloquial name."""

    def test_returns_staff_info_by_colloquial_name(self):
        """Returns staff info when colloquial name matches."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_identity = MagicMock()
        mock_identity.id = "identity-123"
        mock_identity.identifier_key = "ddamelin@concord.org"
        mock_identity.name = "Dan Damelin"
        mock_identity.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
            {"key": "slack_id", "value": "U0303SG91", "type": "string"},
            {"key": "calendar_id", "value": "ddamelin@concord.org", "type": "string"},
        ]

        with patch("letta.conversation_tools.lookup_staff._get_identity_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.find_by_colloquial_name.return_value = mock_identity
            mock_get_svc.return_value = mock_svc

            result = lookup_staff("Dan")

        assert result["name"] == "Dan Damelin"
        assert result["email"] == "ddamelin@concord.org"
        assert result["slack_id"] == "U0303SG91"
        assert result["calendar_id"] == "ddamelin@concord.org"

    def test_returns_error_when_not_found(self):
        """Returns error dict when no match found."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        with patch("letta.conversation_tools.lookup_staff._get_identity_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.find_by_colloquial_name.return_value = None
            mock_get_svc.return_value = mock_svc

            result = lookup_staff("UnknownPerson")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_handles_email_lookup(self):
        """Can also look up by email address."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_identity = MagicMock()
        mock_identity.id = "identity-456"
        mock_identity.identifier_key = "scytacki@concord.org"
        mock_identity.name = "Scott Cytacki"
        mock_identity.properties = [
            {"key": "colloquial_name", "value": "Scott", "type": "string"},
        ]

        with patch("letta.conversation_tools.lookup_staff._get_identity_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.find_by_colloquial_name.return_value = None
            mock_svc.find_by_identifier_key.return_value = mock_identity
            mock_get_svc.return_value = mock_svc

            result = lookup_staff("scytacki@concord.org")

        assert result["name"] == "Scott Cytacki"
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_lookup_staff.py -v
```
Expected: FAIL with `ModuleNotFoundError`

### Step 3: Write implementation

```python
# letta/conversation_tools/lookup_staff.py
"""
Look up staff member by colloquial name or email.

This tool enables agents to resolve colloquial references like
"What's Dan's schedule?" to actual staff identity data including
email, slack_id, and calendar_id.
"""

import os
import sys
from typing import Dict, Any, Optional

# Add pa-routing-handler to path for IdentityService import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'pa-routing-handler', 'src'))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        Letta = None

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Cached service instance
_identity_service = None


def _get_identity_service():
    """Get or create IdentityService instance."""
    global _identity_service
    if _identity_service is None:
        if Letta is None:
            return None
        try:
            from pa_routing.services.identity_service import IdentityService
            client = Letta(base_url=LETTA_BASE_URL)
            _identity_service = IdentityService(letta_client=client)
        except ImportError:
            # Fallback: create minimal inline service
            _identity_service = _MinimalIdentityService()
    return _identity_service


class _MinimalIdentityService:
    """Minimal identity service when pa_routing not available."""

    def __init__(self):
        self.client = Letta(base_url=LETTA_BASE_URL) if Letta else None

    def find_by_colloquial_name(self, name: str):
        """Find identity by colloquial name."""
        if not self.client:
            return None
        try:
            identities = list(self.client.identities.list())
            name_lower = name.lower()

            # Check colloquial_name property
            for identity in identities:
                for prop in getattr(identity, 'properties', []) or []:
                    key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
                    value = prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
                    if key == 'colloquial_name' and value and value.lower() == name_lower:
                        return identity

            # Check first name
            for identity in identities:
                full_name = getattr(identity, 'name', '') or ''
                first_name = full_name.split()[0] if full_name else ''
                if first_name.lower() == name_lower:
                    return identity

            return None
        except Exception:
            return None

    def find_by_identifier_key(self, key: str):
        """Find identity by identifier_key (email)."""
        if not self.client:
            return None
        try:
            results = list(self.client.identities.list(identifier_key=key))
            return results[0] if results else None
        except Exception:
            return None


def _extract_property(identity, key: str) -> Optional[str]:
    """Extract property value from identity."""
    for prop in getattr(identity, 'properties', []) or []:
        prop_key = prop.get('key') if isinstance(prop, dict) else getattr(prop, 'key', None)
        if prop_key == key:
            return prop.get('value') if isinstance(prop, dict) else getattr(prop, 'value', None)
    return None


def lookup_staff(name_or_email: str) -> Dict[str, Any]:
    """
    Look up staff member by colloquial name or email address.

    Use this tool when you need to find information about a person mentioned
    in conversation, such as their email, Slack ID, or calendar ID.

    Args:
        name_or_email: Colloquial name (e.g., "Dan", "Scott") or email address

    Returns:
        dict with staff info:
        - name: Full name
        - email: Email address (identifier_key)
        - slack_id: Slack user ID (if available)
        - calendar_id: Calendar ID for scheduling (if available)
        - colloquial_name: Short name used for reference
        - working_hours: Working hours constraint (if set)
        - working_week: Working days constraint (if set)

        Or dict with "error" key if not found.

    Example:
        >>> lookup_staff("Dan")
        {
            "name": "Dan Damelin",
            "email": "ddamelin@concord.org",
            "slack_id": "U0303SG91",
            "calendar_id": "ddamelin@concord.org",
            "colloquial_name": "Dan"
        }
    """
    service = _get_identity_service()
    if service is None:
        return {"error": "Identity service not available"}

    identity = None

    # Try colloquial name first
    identity = service.find_by_colloquial_name(name_or_email)

    # Try email if not found
    if identity is None and "@" in name_or_email:
        identity = service.find_by_identifier_key(name_or_email)

    if identity is None:
        return {"error": f"Staff member '{name_or_email}' not found in directory"}

    # Build response
    result = {
        "name": getattr(identity, 'name', 'Unknown'),
        "email": getattr(identity, 'identifier_key', None),
        "identity_id": getattr(identity, 'id', None),
    }

    # Add properties
    for key in ["slack_id", "calendar_id", "colloquial_name", "working_hours", "working_week", "imessage"]:
        value = _extract_property(identity, key)
        if value:
            result[key] = value

    return result
```

### Step 4: Update __init__.py

```python
# letta/conversation_tools/__init__.py
"""
Letta Conversation Tools for multi-user agent access.

These tools enable:
- User block discovery via find_user_blocks
- User block creation via create_user_memory_block
- Staff lookup via lookup_staff
"""

from .find_user_blocks import find_user_blocks
from .create_user_memory_block import create_user_memory_block
from .lookup_staff import lookup_staff

__all__ = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
```

### Step 5: Run tests to verify they pass

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_lookup_staff.py -v
```
Expected: PASS (3 tests)

### Step 6: Commit

```bash
git add letta/conversation_tools/lookup_staff.py
git add letta/conversation_tools/tests/test_lookup_staff.py
git add letta/conversation_tools/__init__.py
git commit -m "feat: add lookup_staff tool for colloquial name resolution"
```

---

## Task 5: Register and Attach lookup_staff Tool

**Files:**
- Modify: `letta/register_conversation_tools.py`
- Modify: `letta/attach_conversation_tools_to_agent.py`

### Step 1: Update registration script

Add `lookup_staff` to the tools list in `register_conversation_tools.py`:

```python
# In register_conversation_tools.py, update imports:
from conversation_tools.find_user_blocks import find_user_blocks
from conversation_tools.create_user_memory_block import create_user_memory_block
from conversation_tools.lookup_staff import lookup_staff

# Update tools list in main():
tools = [
    {
        "func": find_user_blocks,
        "name": "find_user_blocks",
        "tags": ["conversation", "multi-user", "memory", "custom"]
    },
    {
        "func": create_user_memory_block,
        "name": "create_user_memory_block",
        "tags": ["conversation", "multi-user", "memory", "custom"]
    },
    {
        "func": lookup_staff,
        "name": "lookup_staff",
        "tags": ["conversation", "identity", "lookup", "custom"]
    }
]
```

### Step 2: Update attachment script

Add `lookup_staff` to `CONVERSATION_TOOLS` in `attach_conversation_tools_to_agent.py`:

```python
CONVERSATION_TOOLS = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
```

### Step 3: Run registration

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python letta/register_conversation_tools.py
```
Expected: Shows `lookup_staff` registered (or "Already exists")

### Step 4: Run attachment

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python letta/attach_conversation_tools_to_agent.py
```
Expected: Shows `lookup_staff` attached to scheduler agent

### Step 5: Commit

```bash
git add letta/register_conversation_tools.py
git add letta/attach_conversation_tools_to_agent.py
git commit -m "feat: register and attach lookup_staff tool to scheduler agent"
```

---

## Task 6: Integration Test

**Files:**
- Modify: `scripts/test_conversation_pilot.py`

### Step 1: Add identity-related tests

Add these test functions to `test_conversation_pilot.py`:

```python
def test_identities_exist(client) -> bool:
    """Verify staff identities were migrated."""
    print("\n[Test 6] Staff Identities Exist")
    try:
        identities = list(client.identities.list())
        staff_count = len([i for i in identities if getattr(i, 'identity_type', '') == 'user'])

        if staff_count >= 20:  # We expect ~30 staff + family
            print(f"  [OK] Found {staff_count} staff identities")
            return True
        else:
            print(f"  [FAIL] Only found {staff_count} identities (expected 20+)")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_identity_has_properties(client) -> bool:
    """Verify identities have expected properties."""
    print("\n[Test 7] Identity Properties")
    try:
        identities = list(client.identities.list())

        # Find Dan Damelin
        dan = None
        for i in identities:
            if getattr(i, 'identifier_key', '') == 'ddamelin@concord.org':
                dan = i
                break

        if dan is None:
            print("  [FAIL] Dan Damelin identity not found")
            return False

        properties = {p.get('key') if isinstance(p, dict) else getattr(p, 'key', None): p.get('value') if isinstance(p, dict) else getattr(p, 'value', None)
                     for p in getattr(dan, 'properties', [])}

        required = ["colloquial_name", "slack_id", "calendar_id"]
        all_found = True
        for key in required:
            if key in properties:
                print(f"  [OK] {key}: {properties[key]}")
            else:
                print(f"  [FAIL] Missing {key}")
                all_found = False

        return all_found
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_lookup_staff_tool(client) -> bool:
    """Test the lookup_staff tool is attached and works."""
    print("\n[Test 8] lookup_staff Tool")
    try:
        # Check tool is attached
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
        tool_names = [t.name if hasattr(t, 'name') else t.get('name') for t in tools]

        if "lookup_staff" not in tool_names:
            print("  [FAIL] lookup_staff tool not registered")
            return False

        print("  [OK] lookup_staff tool registered")

        # Check attached to agent
        agent = client.agents.retrieve(agent_id=SCHEDULER_AGENT_ID)
        attached_tool_ids = []
        if hasattr(agent, 'tool_ids'):
            attached_tool_ids = agent.tool_ids or []
        elif hasattr(agent, 'tools'):
            attached_tool_ids = [t.id if hasattr(t, 'id') else t for t in (agent.tools or [])]

        id_to_name = {t.id if hasattr(t, 'id') else t.get('id'): t.name if hasattr(t, 'name') else t.get('name') for t in tools}
        attached_names = [id_to_name.get(tid, tid) for tid in attached_tool_ids]

        if "lookup_staff" in attached_names:
            print("  [OK] lookup_staff attached to scheduler agent")
            return True
        else:
            print("  [FAIL] lookup_staff not attached to agent")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False
```

### Step 2: Update main() to run new tests

Add to `main()`:
```python
# Test 6: Identities exist
if test_identities_exist(client):
    passed += 1
else:
    failed += 1

# Test 7: Identity properties
if test_identity_has_properties(client):
    passed += 1
else:
    failed += 1

# Test 8: lookup_staff tool
if test_lookup_staff_tool(client):
    passed += 1
else:
    failed += 1
```

### Step 3: Run integration tests

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python scripts/test_conversation_pilot.py
```
Expected: All 8 tests pass

### Step 4: Commit

```bash
git add scripts/test_conversation_pilot.py
git commit -m "test: add identity management integration tests"
```

---

## Execution Summary

| Task | Description | Est. Time |
|------|-------------|-----------|
| 1 | Create IdentityService | 30 min |
| 2 | Staff Directory Migration Script | 20 min |
| 3 | Update ConversationService | 30 min |
| 4 | Create lookup_staff Tool | 25 min |
| 5 | Register and Attach Tool | 10 min |
| 6 | Integration Testing | 15 min |

**Total:** ~2-2.5 hours

---

## Post-Implementation Verification

After completing all tasks, verify end-to-end:

1. **Staff member messages Slackbot:**
   - Should be recognized by slack_id
   - Conversation uses their staff identity
   - Blocks named with identity_id

2. **Agent uses lookup_staff:**
   - "What's Dan's schedule?" resolves to Dan Damelin
   - Returns calendar_id for scheduling integration

3. **Unknown user messages Slackbot:**
   - External identity created
   - Conversation works normally
   - Can be linked to staff identity later if needed
