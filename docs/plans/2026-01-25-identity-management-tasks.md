# Identity Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable staff recognition when messaging Chadbot and colloquial lookup ("What's Dan's schedule?")

**Architecture:** Staff identities are pre-populated via migration script. ConversationService looks up identities by platform ID (slack_id, email) before creating conversations. IdentityService wraps the Letta API for identity operations. A lookup_staff tool enables agents to resolve colloquial references.

**Tech Stack:** Python 3.9+, Letta Identities API, Supabase (user_conversations table), pytest

**Design Document:** `docs/plans/2026-01-25-identity-management-design.md`

---

## Pre-Implementation: Git Setup for Plan Files

**Problem:** Superpowers creates plans in `~/.claude/plans/` which is outside the repo. These should be tracked in Git for project continuity.

**Step 1: Copy this plan to the repo**
```bash
cp /Users/dorseyhomeserver/.claude/plans/serene-hopping-acorn.md /Volumes/main-drive/ai-PA/docs/plans/2026-01-25-identity-management-tasks.md
```

**Step 2: Add all untracked plan files to Git**
```bash
cd /Volumes/main-drive/ai-PA
git add docs/plans/2026-01-25-identity-management-impl.md
git add docs/plans/2026-01-25-identity-management-tasks.md
git add docs/plans/2026-01-25-letta-conversations-scheduler-pilot-impl.md
```

**Step 3: Commit plan files**
```bash
git commit -m "docs: add implementation plans and tasks for identity management and conversations pilot"
```

---

## API Discovery Notes

The Letta Identities API (v0.16.3) works as follows:
- **Create:** `POST /v1/identities/` with `identifier_key`, `name`, `identity_type`, `properties`
- **Properties format:** List of `{"key": "...", "value": "...", "type": "string"}`
- **List:** `GET /v1/identities/` returns all identities
- **Search:** `GET /v1/identities/?identifier_key=xxx` filters by identifier_key
- **Delete:** `DELETE /v1/identities/{id}`

**Note:** No direct search by property value - must list all and filter client-side.

---

## Current State Summary

| Component | Status | Notes |
|-----------|--------|-------|
| IdentityService | **Does not exist** | CREATE |
| ConversationService | Exists, creates new identities | MODIFY to lookup existing staff first |
| lookup_staff tool | **Does not exist** | CREATE |
| Migration script | **Does not exist** | CREATE for 30 staff/family |
| find_user_blocks | Exists, uses platform ID naming | Future Phase 3 migration |

---

## Agent Parallelization Opportunities

| Opportunity | Tasks | Notes |
|-------------|-------|-------|
| **Parallel Test Writing** | Task 1 tests + Task 4 tests | No dependencies between IdentityService and lookup_staff tests |
| **Parallel After Task 1** | Task 2 + Task 5 | Migration script and registration updates can run simultaneously |
| **Code Review Checkpoint** | After Phase 1 | Use code-reviewer agent before Phase 2 |

---

## Phase 1: Foundation

### Task 1: Create IdentityService

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/identity_service.py`
- Modify: `pa-routing-handler/src/pa_routing/services/__init__.py`
- Test: `pa-routing-handler/tests/services/test_identity_service.py`

**Step 1: Write failing tests**

```python
# pa-routing-handler/tests/services/test_identity_service.py
"""Tests for IdentityService."""

import pytest
from unittest.mock import MagicMock, patch


class TestIdentityService:
    """Tests for identity lookup and management."""

    @pytest.fixture
    def mock_letta_client(self):
        """Create mock Letta client with identities namespace."""
        client = MagicMock()
        client.identities = MagicMock()
        return client

    @pytest.fixture
    def sample_identities(self):
        """Sample identity objects for testing."""
        dan = MagicMock()
        dan.id = "identity-dan-123"
        dan.identifier_key = "ddamelin@concord.org"
        dan.name = "Dan Damelin"
        dan.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
            {"key": "slack_id", "value": "U0303SG91", "type": "string"},
            {"key": "calendar_id", "value": "ddamelin@concord.org", "type": "string"},
            {"key": "email", "value": "ddamelin@concord.org", "type": "string"},
        ]

        scott = MagicMock()
        scott.id = "identity-scott-456"
        scott.identifier_key = "scytacki@concord.org"
        scott.name = "Scott Cytacki"
        scott.properties = [
            {"key": "colloquial_name", "value": "Scott", "type": "string"},
            {"key": "slack_id", "value": "U02V82YB9", "type": "string"},
            {"key": "calendar_id", "value": "scytacki@concord.org", "type": "string"},
            {"key": "email", "value": "scytacki@concord.org", "type": "string"},
        ]

        return [dan, scott]

    def test_find_by_identifier_key_found(self, mock_letta_client, sample_identities):
        """Finds identity by exact identifier_key (email)."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("ddamelin@concord.org")

        assert result is not None
        assert result.id == "identity-dan-123"
        assert result.name == "Dan Damelin"

    def test_find_by_identifier_key_not_found(self, mock_letta_client, sample_identities):
        """Returns None when identifier_key not found."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_identifier_key("unknown@example.com")

        assert result is None

    def test_find_by_property_slack_id(self, mock_letta_client, sample_identities):
        """Finds identity by slack_id property."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_property("slack_id", "U02V82YB9")

        assert result is not None
        assert result.id == "identity-scott-456"

    def test_find_by_colloquial_name(self, mock_letta_client, sample_identities):
        """Finds identity by colloquial_name property."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("Dan")

        assert result is not None
        assert result.id == "identity-dan-123"

    def test_find_by_colloquial_name_case_insensitive(self, mock_letta_client, sample_identities):
        """Colloquial name search is case-insensitive."""
        from pa_routing.services.identity_service import IdentityService

        mock_letta_client.identities.list.return_value = sample_identities

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("dan")

        assert result is not None
        assert result.id == "identity-dan-123"

    def test_find_by_colloquial_name_fallback_to_first_name(self, mock_letta_client):
        """Falls back to first name of full name if no colloquial_name match."""
        from pa_routing.services.identity_service import IdentityService

        # Identity without colloquial_name property
        person = MagicMock()
        person.id = "identity-new-789"
        person.identifier_key = "newperson@concord.org"
        person.name = "New Person"
        person.properties = [
            {"key": "email", "value": "newperson@concord.org", "type": "string"},
        ]
        mock_letta_client.identities.list.return_value = [person]

        service = IdentityService(letta_client=mock_letta_client)
        result = service.find_by_colloquial_name("New")

        assert result is not None
        assert result.id == "identity-new-789"

    def test_create_external_user(self, mock_letta_client):
        """Creates external identity for unknown users."""
        from pa_routing.services.identity_service import IdentityService

        mock_identity = MagicMock()
        mock_identity.id = "identity-external-999"
        mock_letta_client.identities.create.return_value = mock_identity

        service = IdentityService(letta_client=mock_letta_client)
        result = service.create_external_user(
            platform="slack",
            platform_id="U99999999",
            display_name="External User"
        )

        assert result.id == "identity-external-999"
        mock_letta_client.identities.create.assert_called_once()

    def test_get_property_helper(self, mock_letta_client, sample_identities):
        """Helper extracts property value from identity."""
        from pa_routing.services.identity_service import IdentityService

        service = IdentityService(letta_client=mock_letta_client)
        dan = sample_identities[0]

        assert service.get_property(dan, "slack_id") == "U0303SG91"
        assert service.get_property(dan, "calendar_id") == "ddamelin@concord.org"
        assert service.get_property(dan, "nonexistent") is None
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_identity_service.py -v
```
Expected: FAIL (ModuleNotFoundError: No module named 'pa_routing.services.identity_service')

**Step 3: Write implementation**

```python
# pa-routing-handler/src/pa_routing/services/identity_service.py
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
```

**Step 4: Update services __init__.py**

Add to `pa-routing-handler/src/pa_routing/services/__init__.py`:
```python
from .identity_service import IdentityService
```

**Step 5: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_identity_service.py -v
```
Expected: PASS (8 tests)

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/identity_service.py
git add pa-routing-handler/src/pa_routing/services/__init__.py
git add pa-routing-handler/tests/services/test_identity_service.py
git commit -m "feat: add IdentityService for staff recognition"
```

---

### Task 2: Staff Directory Migration Script

**Files:**
- Create: `scripts/migrate_staff_to_identities.py`

**Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""
Migrate staff directory to Letta Identities.

Reads hardcoded staff/family data (from memory block export) and creates
Letta identities with properties:
- colloquial_name, email, slack_id, calendar_id, working_hours, working_week, imessage

Usage:
    python scripts/migrate_staff_to_identities.py --dry-run
    python scripts/migrate_staff_to_identities.py
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

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
        sys.exit(1)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Staff directory data (from memory block export - actual Concord staff)
STAFF_DIRECTORY: List[Dict[str, Any]] = [
    {"name": "Ethan McElroy", "email": "emcelroy@concord.org", "slack_id": "U02V96MQC", "calendar_id": "emcelroy@concord.org", "colloquial_name": "Ethan"},
    {"name": "Kirk Swenson", "email": "kswenson@concord.org", "slack_id": "U0GQHHS1W", "calendar_id": "kswenson@concord.org", "colloquial_name": "Kirk", "working_hours": "11:30AM-7:30PM"},
    {"name": "Scott Cytacki", "email": "scytacki@concord.org", "slack_id": "U02V82YB9", "calendar_id": "scytacki@concord.org", "colloquial_name": "Scott"},
    {"name": "Paul Horwitz", "email": "phorwitz@concord.org", "slack_id": "U031V0J1M", "calendar_id": "phorwitz@concord.org", "colloquial_name": "Paul"},
    {"name": "Hee-Sun Lee", "email": "hlee@concord.org", "slack_id": "U09M9UU3A", "calendar_id": "hlee@concord.org", "colloquial_name": "Hee-Sun", "working_hours": "12:00PM-5:00PM"},
    {"name": "Trudi Lord", "email": "tlord@concord.org", "slack_id": "U02V941L0", "calendar_id": "tlord@concord.org", "colloquial_name": "Trudi"},
    {"name": "Dan Damelin", "email": "ddamelin@concord.org", "slack_id": "U0303SG91", "calendar_id": "ddamelin@concord.org", "colloquial_name": "Dan"},
    {"name": "Judi Raiff", "email": "jraiff@concord.org", "slack_id": "U48DTGUGJ", "calendar_id": "jraiff@concord.org", "colloquial_name": "Judi"},
    {"name": "Cynthia McIntyre", "email": "cmcintyre@concord.org", "slack_id": "U09DXRLAH", "calendar_id": "cmcintyre@concord.org", "colloquial_name": "Cynthia"},
    {"name": "Bill Finzer", "email": "wfinzer@concord.org", "slack_id": "U02VCM7TL", "calendar_id": "wfinzer@concord.org", "colloquial_name": "Bill", "working_hours": "11:00AM-7:00PM"},
    {"name": "Kiley Brown", "email": "kbrown@concord.org", "slack_id": None, "calendar_id": "kbrown@concord.org", "colloquial_name": "Kiley"},
    {"name": "Leslie Bondaryk", "email": "lbondaryk@concord.org", "slack_id": "UACG5LG3Y", "calendar_id": "lbondaryk@concord.org", "colloquial_name": "Leslie", "working_week": "Monday-Thursday"},
    {"name": "Jie Chao", "email": "jchao@concord.org", "slack_id": "U0AEJSLQJ", "calendar_id": "jchao@concord.org", "colloquial_name": "Jie"},
    {"name": "Amy Pallant", "email": "apallant@concord.org", "slack_id": "U09LTDGKX", "calendar_id": "apallant@concord.org", "colloquial_name": "Amy", "working_week": "Monday-Thursday"},
    {"name": "Chris Lore", "email": "clore@concord.org", "slack_id": "UG8PJCU1L", "calendar_id": "clore@concord.org", "colloquial_name": "Chris", "working_week": "Monday-Thursday"},
    {"name": "Kate Miller", "email": "kmiller@concord.org", "slack_id": "U04DMBL0YAU", "calendar_id": "kmiller@concord.org", "colloquial_name": "Kate"},
    {"name": "Kathy Jessen Eller", "email": "kjesseneller@concord.org", "slack_id": "U0836P6REKF", "calendar_id": "kjesseneller@concord.org", "colloquial_name": "Kathy"},
    {"name": "Rebecca Ellis", "email": "rellis@concord.org", "slack_id": "UK486BUSX", "calendar_id": "rellis@concord.org", "colloquial_name": "Rebecca"},
    {"name": "Teale Fristoe", "email": "tfristoe@concord.org", "slack_id": "U03HRBXLJ12", "calendar_id": "tfristoe@concord.org", "colloquial_name": "Teale"},
    {"name": "Lisa Buoncuore", "email": "lbuoncuore@concord.org", "slack_id": "U09DZHHPT", "calendar_id": "lbuoncuore@concord.org", "colloquial_name": "Lisa"},
    {"name": "Danielle Kehoe", "email": "dkehoe@concord.org", "slack_id": "U09B5JUK2TY", "calendar_id": "dkehoe@concord.org", "colloquial_name": "Danielle"},
    {"name": "Sue Brau", "email": "sbrau@concord.org", "slack_id": "U09C3N5LZ", "calendar_id": "sbrau@concord.org", "colloquial_name": "Sue"},
    {"name": "Doug Martin", "email": "dmartin@concord.org", "slack_id": "U048JG9CU", "calendar_id": "dmartin@concord.org", "colloquial_name": "Doug"},
    {"name": "Lynn Stephens", "email": "lstephens@concord.org", "slack_id": "U7DMA61BN", "calendar_id": "lstephens@concord.org", "colloquial_name": "Lynn"},
    {"name": "Michael Tirenin", "email": "mtirenin@concord.org", "slack_id": "UBRAAE2FM", "calendar_id": "mtirenin@concord.org", "colloquial_name": "Michael"},
    {"name": "Aditi Wagh", "email": "awagh@concord.org", "slack_id": "U096MABDPNF", "calendar_id": "awagh@concord.org", "colloquial_name": "Aditi"},
]

# Family directory data
FAMILY_DIRECTORY: List[Dict[str, Any]] = [
    {"name": "Sophia Dorsey", "email": "sophiadorsey@gmail.com", "calendar_id": "sb06g6b1g2jlkplc1bcd7k4ofk@group.calendar.google.com", "colloquial_name": "Sophia", "imessage": "sophiadorsey@gmail.com"},
    {"name": "Liam Dorsey", "email": "liamdorsey00@gmail.com", "calendar_id": "cr89gktnjrcrtm9j9a48j060hc@group.calendar.google.com", "colloquial_name": "Liam", "imessage": "liamdorsey00@gmail.com"},
    {"name": "Liz Dorsey", "email": "lizdorsey@gmail.com", "calendar_id": "lizdorsey@gmail.com", "colloquial_name": "Liz", "imessage": "lizdorsey@gmail.com"},
    {"name": "Chad Dorsey", "email": "cdorsey@concord.org", "calendar_id": "concord.org_ouqdctthtvfm6bklntoq2rbg9s@group.calendar.google.com", "colloquial_name": "Chad", "imessage": "chaddorsey@gmail.com", "personal_email": "chaddorsey@gmail.com"},
]


def build_properties(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build properties list from staff/family data."""
    properties = []

    # Always include colloquial_name
    if data.get("colloquial_name"):
        properties.append({"key": "colloquial_name", "value": data["colloquial_name"], "type": "string"})

    # Platform IDs (skip None values)
    if data.get("slack_id"):
        properties.append({"key": "slack_id", "value": data["slack_id"], "type": "string"})
    if data.get("calendar_id"):
        properties.append({"key": "calendar_id", "value": data["calendar_id"], "type": "string"})

    # Optional fields
    if data.get("working_hours"):
        properties.append({"key": "working_hours", "value": data["working_hours"], "type": "string"})
    if data.get("working_week"):
        properties.append({"key": "working_week", "value": data["working_week"], "type": "string"})
    if data.get("imessage"):
        properties.append({"key": "imessage", "value": data["imessage"], "type": "string"})
    if data.get("personal_email"):
        properties.append({"key": "personal_email", "value": data["personal_email"], "type": "string"})

    return properties


def create_identity(client, data: Dict[str, Any], category: str, dry_run: bool = False) -> bool:
    """Create a single identity. Returns True on success."""
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

    print(f"Migrating {len(STAFF_DIRECTORY)} staff members...")
    print("-" * 40)
    for staff in STAFF_DIRECTORY:
        if create_identity(client, staff, "staff", dry_run):
            created += 1
        else:
            failed += 1

    print()
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

**Step 2: Run with dry-run to verify**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python scripts/migrate_staff_to_identities.py --dry-run
```
Expected: Lists all 30 people (26 staff + 4 family) with `[DRY RUN - not created]` messages

**Step 3: Run actual migration**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python scripts/migrate_staff_to_identities.py
```
Expected: `Migration Complete: 30 created, 0 failed`

**Step 4: Verify identities were created**

Run:
```bash
curl -s http://localhost:8283/v1/identities/ | python3 -c "import sys,json; data=json.load(sys.stdin); print(f'{len(data)} identities found')"
```
Expected: `30 identities found` (or more if other identities existed)

**Step 5: Commit**

```bash
git add scripts/migrate_staff_to_identities.py
git commit -m "feat: add staff directory migration to Letta Identities"
```

---

### Task 3: Update ConversationService to Resolve Identities

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/conversation_service.py`
- Test: `pa-routing-handler/tests/services/test_conversation_service.py` (add tests)

**Step 1: Add identity resolution tests**

Add to existing test file:

```python
# Add to pa-routing-handler/tests/services/test_conversation_service.py

    @pytest.fixture
    def mock_identity_service(self):
        """Create mock IdentityService."""
        service = MagicMock()
        service.find_by_property = MagicMock(return_value=None)
        service.find_by_identifier_key = MagicMock(return_value=None)
        service.create_external_user = MagicMock()
        service.get_property = MagicMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_resolves_staff_identity_by_slack_id(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Resolves existing staff identity when messaging from Slack."""
        from pa_routing.services.conversation_service import ConversationService

        # Staff identity exists
        staff_identity = MagicMock()
        staff_identity.id = "identity-staff-123"
        staff_identity.name = "Dan Damelin"
        mock_identity_service.find_by_property.return_value = staff_identity

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-new"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="U0303SG91",  # Dan's Slack ID
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should have looked up by slack_id
        mock_identity_service.find_by_property.assert_called_with("slack_id", "U0303SG91")
        # Should use existing identity, NOT create new one
        mock_letta_client.identities.create.assert_not_called()
        assert result["identity_id"] == "identity-staff-123"

    @pytest.mark.asyncio
    async def test_creates_external_identity_for_unknown_user(
        self, mock_letta_client, mock_supabase_client, mock_identity_service
    ):
        """Creates external identity for unknown Slack user."""
        from pa_routing.services.conversation_service import ConversationService

        # No staff identity found
        mock_identity_service.find_by_property.return_value = None
        mock_identity_service.find_by_identifier_key.return_value = None

        # External identity created
        external_identity = MagicMock()
        external_identity.id = "identity-external-999"
        mock_identity_service.create_external_user.return_value = external_identity

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "conv-new"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-1"
        mock_letta_client.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client,
            identity_service=mock_identity_service
        )

        result = await service.get_or_create_conversation(
            user_id="U99999999",  # Unknown user
            user_source="slack",
            agent_id="agent-abc"
        )

        # Should create external identity
        mock_identity_service.create_external_user.assert_called_once()
        assert result["identity_id"] == "identity-external-999"
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v -k "identity"
```
Expected: FAIL (TypeError: __init__() got unexpected keyword argument 'identity_service')

**Step 3: Replace ConversationService with complete implementation**

Replace entire `pa-routing-handler/src/pa_routing/services/conversation_service.py`:

```python
"""
Conversation service for managing user→conversation mappings.

Handles:
- Looking up existing conversations for user+agent pairs
- Creating new conversations with Letta Conversations API
- Resolving user identity via IdentityService before conversation creation
- Creating initial user blocks on onboarding (with identity-based naming)
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

SCHEDULER_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
AGENT_NAME = "meeting_scheduler"


class ConversationService:
    """Manages Letta Conversations for multi-user agent access."""

    def __init__(
        self,
        letta_client: Any,
        supabase_client: Any,
        identity_service: Optional[Any] = None
    ):
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
        """Get existing conversation or create new one for user+agent pair."""
        # Try to find existing conversation
        existing = await self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            logger.info("conversation_found", user_id=user_id, conversation_id=existing["conversation_id"])
            return {
                "conversation_id": existing["conversation_id"],
                "identity_id": existing.get("identity_id"),
                "created": False
            }

        # Resolve identity before creating conversation
        identity = await self._resolve_identity(user_id, user_source, display_name, email)

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
        """Resolve user identity from platform ID."""
        if not self.identity_service:
            return None

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
                logger.info("staff_identity_found_by_email", user_id=user_id, email=email, identity_id=identity.id)
                return identity

        # Create external identity for unknown user
        try:
            identity = self.identity_service.create_external_user(
                platform=user_source,
                platform_id=user_id,
                display_name=display_name
            )
            logger.info("external_identity_created", user_id=user_id, identity_id=identity.id)
            return identity
        except Exception as e:
            logger.warning("identity_resolution_failed", error=str(e), user_id=user_id)
            return None

    async def _lookup_conversation(
        self, user_id: str, user_source: str, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up existing conversation in Supabase."""
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
        """Create conversation and initial resources for new user."""
        identity_id = identity.id if identity else None
        block_user_key = identity_id if identity_id else user_id
        block_ids = []

        # Create preference block with identity-based naming
        try:
            pref_block = self.letta.blocks.create(
                label=f"preferences_{block_user_key}",
                value="No preferences learned yet. This block stores scheduling preferences for this user.",
                description=f"Scheduling preferences for {display_name}",
                limit=2000
            )
            block_ids.append(pref_block.id)
            self.letta.agents.blocks.attach(agent_id=agent_id, block_id=pref_block.id)
            logger.info("preference_block_created", user_id=user_id, block_id=pref_block.id)
        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id, block_type="preferences")

        # Create calendar block with identity-based naming
        try:
            cal_block = self.letta.blocks.create(
                label=f"calendar_{block_user_key}",
                value="Calendar integration pending configuration.",
                description=f"Calendar integration for {display_name}",
                limit=2000
            )
            block_ids.append(cal_block.id)
            self.letta.agents.blocks.attach(agent_id=agent_id, block_id=cal_block.id)
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
            return {"error": f"Failed to create conversation: {str(e)}", "created": False}

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
            logger.error("conversation_mapping_insert_failed", error=str(e), user_id=user_id, conversation_id=conversation_id)

        logger.info("user_onboarded", user_id=user_id, conversation_id=conversation_id, identity_id=identity_id, block_count=len(block_ids))
        return {"conversation_id": conversation_id, "identity_id": identity_id, "created": True}

    async def update_last_active(self, user_id: str, user_source: str, agent_id: str) -> None:
        """Update last_active_at timestamp for a conversation."""
        try:
            self.supabase.table("user_conversations").update({
                "last_active_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("user_source", user_source).eq("agent_id", agent_id).execute()
            logger.debug("last_active_updated", user_id=user_id)
        except Exception as e:
            logger.warning("last_active_update_failed", error=str(e), user_id=user_id)
```

**Step 4: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v
```
Expected: PASS (all tests including new identity tests)

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/conversation_service.py
git add pa-routing-handler/tests/services/test_conversation_service.py
git commit -m "feat: add identity resolution to ConversationService"
```

---

## Phase 2: Agent Integration

### Task 4: Create lookup_staff Tool

**Files:**
- Create: `letta/conversation_tools/lookup_staff.py`
- Test: `letta/conversation_tools/tests/test_lookup_staff.py`

**Step 1: Write failing tests**

```python
# letta/conversation_tools/tests/test_lookup_staff.py
"""Tests for lookup_staff agent tool."""

import pytest
from unittest.mock import MagicMock, patch


class TestLookupStaff:
    """Tests for staff lookup by colloquial name or email."""

    @pytest.fixture
    def sample_identity(self):
        """Sample staff identity."""
        identity = MagicMock()
        identity.id = "identity-dan-123"
        identity.identifier_key = "ddamelin@concord.org"
        identity.name = "Dan Damelin"
        identity.properties = [
            {"key": "colloquial_name", "value": "Dan", "type": "string"},
            {"key": "slack_id", "value": "U0303SG91", "type": "string"},
            {"key": "calendar_id", "value": "ddamelin@concord.org", "type": "string"},
            {"key": "email", "value": "ddamelin@concord.org", "type": "string"},
        ]
        return identity

    def test_lookup_by_colloquial_name(self, sample_identity):
        """Finds staff by colloquial name."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = sample_identity

        with patch("letta.conversation_tools.lookup_staff._get_identity_service", return_value=mock_service):
            result = lookup_staff(name_or_email="Dan")

        assert result["name"] == "Dan Damelin"
        assert result["identity_id"] == "identity-dan-123"
        assert result["slack_id"] == "U0303SG91"
        assert result["calendar_id"] == "ddamelin@concord.org"

    def test_lookup_by_email(self, sample_identity):
        """Finds staff by email address."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = None
        mock_service.find_by_identifier_key.return_value = sample_identity

        with patch("letta.conversation_tools.lookup_staff._get_identity_service", return_value=mock_service):
            result = lookup_staff(name_or_email="ddamelin@concord.org")

        assert result["name"] == "Dan Damelin"
        assert result["email"] == "ddamelin@concord.org"

    def test_lookup_not_found(self):
        """Returns error when staff not found."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = None
        mock_service.find_by_identifier_key.return_value = None

        with patch("letta.conversation_tools.lookup_staff._get_identity_service", return_value=mock_service):
            result = lookup_staff(name_or_email="Unknown")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_lookup_case_insensitive(self, sample_identity):
        """Lookup is case-insensitive."""
        from letta.conversation_tools.lookup_staff import lookup_staff

        mock_service = MagicMock()
        mock_service.find_by_colloquial_name.return_value = sample_identity

        with patch("letta.conversation_tools.lookup_staff._get_identity_service", return_value=mock_service):
            result = lookup_staff(name_or_email="dan")

        assert result["name"] == "Dan Damelin"
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_lookup_staff.py -v
```
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write implementation**

```python
# letta/conversation_tools/lookup_staff.py
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
```

**Step 4: Update conversation_tools __init__.py**

Add to `letta/conversation_tools/__init__.py`:
```python
from .lookup_staff import lookup_staff

__all__ = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
```

**Step 5: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_lookup_staff.py -v
```
Expected: PASS (4 tests)

**Step 6: Commit**

```bash
git add letta/conversation_tools/lookup_staff.py
git add letta/conversation_tools/tests/test_lookup_staff.py
git add letta/conversation_tools/__init__.py
git commit -m "feat: add lookup_staff tool for agent colloquial name resolution"
```

---

### Task 5: Register and Attach lookup_staff Tool

**Files:**
- Modify: `letta/register_conversation_tools.py`
- Modify: `letta/attach_conversation_tools_to_agent.py`

**Step 1: Update registration script**

Add lookup_staff to tools list in `letta/register_conversation_tools.py`:

```python
from conversation_tools.lookup_staff import lookup_staff

# In main():
tools = [
    ("find_user_blocks", find_user_blocks),
    ("create_user_memory_block", create_user_memory_block),
    ("lookup_staff", lookup_staff),  # NEW
]
```

**Step 2: Update attachment script**

Add lookup_staff to tool names list in `letta/attach_conversation_tools_to_agent.py`:

```python
tool_names = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
```

**Step 3: Run registration**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python letta/register_conversation_tools.py
```
Expected: "Registered: lookup_staff (ID: tool-...)"

**Step 4: Run attachment**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python letta/attach_conversation_tools_to_agent.py
```
Expected: "Attached: lookup_staff"

**Step 5: Commit**

```bash
git add letta/register_conversation_tools.py
git add letta/attach_conversation_tools_to_agent.py
git commit -m "feat: register and attach lookup_staff tool"
```

---

### Task 6: Integration Tests

**Files:**
- Modify: `scripts/test_conversation_pilot.py`

**Step 1: Add identity-related tests**

Add to `scripts/test_conversation_pilot.py`:

```python
def test_identities_exist(client) -> bool:
    """Verify staff identities were migrated."""
    print("\n[Test 5] Staff Identities Exist")
    try:
        identities = list(client.identities.list())
        staff_count = len(identities)

        if staff_count >= 20:
            print(f"  [OK] Found {staff_count} identities")
            return True
        else:
            print(f"  [FAIL] Only {staff_count} identities (expected 20+)")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_identity_has_properties(client) -> bool:
    """Verify Dan Damelin identity has required properties."""
    print("\n[Test 6] Identity Has Properties")
    try:
        identities = list(client.identities.list())
        dan = None
        for identity in identities:
            if identity.identifier_key == "ddamelin@concord.org":
                dan = identity
                break

        if not dan:
            print("  [FAIL] Dan Damelin identity not found")
            return False

        # Check required properties
        props = {p["key"]: p["value"] for p in (dan.properties or []) if isinstance(p, dict)}
        required = ["colloquial_name", "slack_id", "calendar_id"]

        for key in required:
            if key in props:
                print(f"  [OK] {key}: {props[key]}")
            else:
                print(f"  [FAIL] Missing {key}")
                return False

        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_lookup_staff_tool_attached(client) -> bool:
    """Verify lookup_staff tool is attached to agent."""
    print("\n[Test 7] lookup_staff Tool Attached")
    try:
        tools = client.tools.list()
        tool_names = [t.name for t in tools]

        if "lookup_staff" in tool_names:
            print("  [OK] lookup_staff tool registered")
        else:
            print("  [FAIL] lookup_staff tool not registered")
            return False

        attached = client.agents.tools.list(agent_id=SCHEDULER_AGENT_ID)
        attached_names = [t.name for t in attached]

        if "lookup_staff" in attached_names:
            print("  [OK] lookup_staff attached to scheduler agent")
            return True
        else:
            print("  [FAIL] lookup_staff not attached to scheduler agent")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False
```

**Step 2: Update main() to run new tests**

Add calls to new tests in `main()`:

```python
# After existing tests...
if test_identities_exist(client):
    passed += 1
else:
    failed += 1

if test_identity_has_properties(client):
    passed += 1
else:
    failed += 1

if test_lookup_staff_tool_attached(client):
    passed += 1
else:
    failed += 1
```

**Step 3: Run integration tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python scripts/test_conversation_pilot.py
```
Expected: All tests pass (7+ passed, 0 failed)

**Step 4: Commit**

```bash
git add scripts/test_conversation_pilot.py
git commit -m "test: add identity management integration tests"
```

---

## Verification Plan

### Unit Tests
```bash
# Run IdentityService tests
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_identity_service.py -v

# Run ConversationService tests (including identity resolution)
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v

# Run lookup_staff tool tests
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_lookup_staff.py -v
```

### Integration Tests
```bash
python scripts/test_conversation_pilot.py
```

### Manual Verification
1. **Staff Recognition:** DM Slackbot as a staff member → verify identity resolved (check logs)
2. **Colloquial Lookup:** Ask agent "What's Dan's schedule?" → should resolve without error
3. **External User:** DM Slackbot from unknown user → verify external identity created

---

## Execution Order

1. **Task 1:** Create IdentityService (foundation)
2. **Task 2:** Run staff migration script (populate data)
3. **Task 3:** Update ConversationService (integrate identity lookup)
4. **Task 4:** Create lookup_staff tool (agent capability)
5. **Task 5:** Register and attach tool (connect to agent)
6. **Task 6:** Run integration tests (verify end-to-end)

---

## Success Criteria

1. **Recognition:** Staff member messages Slackbot → logs show "identity_resolved_by_platform"
2. **Lookup:** "What's Dan's schedule?" → returns Dan Damelin's calendar_id
3. **External:** Unknown user messages → external identity created automatically
4. **Tests:** All unit and integration tests pass
