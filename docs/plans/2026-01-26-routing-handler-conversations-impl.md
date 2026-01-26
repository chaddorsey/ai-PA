# Routing Handler Conversations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add persistence, identity resolution, and Letta Conversations to the routing handler for multi-modality support.

**Architecture:** Hybrid persistence (in-memory + Supabase), identity resolution via IdentityService, conversation lookup centralized in handler. Adapters become thin pass-throughs.

**Tech Stack:** Python 3.9+, FastAPI, Supabase (PostgreSQL), Letta Conversations API, pytest

**Design Document:** `docs/plans/2026-01-26-routing-handler-conversations-design.md`

---

## Phase 1: Infrastructure (No Behavior Change)

### Task 1: Create Session State Table in Supabase

**Files:**
- Create: SQL migration (run manually or via Supabase Studio)

**Step 1: Create the table**

```sql
-- Run in Supabase SQL editor
CREATE TABLE IF NOT EXISTS pa_web.session_state (
    identity_id TEXT PRIMARY KEY,
    last_responding_agent_id TEXT,
    last_responding_agent_name TEXT,
    last_response_time TIMESTAMPTZ,
    context_entries JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_state_updated
ON pa_web.session_state(updated_at);

-- Add trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION pa_web.update_session_state_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS session_state_updated_at ON pa_web.session_state;
CREATE TRIGGER session_state_updated_at
    BEFORE UPDATE ON pa_web.session_state
    FOR EACH ROW
    EXECUTE FUNCTION pa_web.update_session_state_timestamp();
```

**Step 2: Verify table exists**

Run:
```bash
docker exec -it supabase-db psql -U postgres -d postgres -c "\d pa_web.session_state"
```
Expected: Table schema displayed

**Step 3: Commit**

```bash
git add docs/plans/2026-01-26-routing-handler-conversations-impl.md
git commit -m "docs: add routing handler conversations implementation plan"
```

---

### Task 2: Add Identity Fields to Route Request Model

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/models/requests.py`
- Test: `pa-routing-handler/tests/models/test_requests.py`

**Step 1: Write failing test**

```python
# pa-routing-handler/tests/models/test_requests.py
"""Tests for request models."""

import pytest
from uuid import uuid4


class TestRouteRequest:
    """Tests for RouteRequest model with identity fields."""

    def test_route_request_accepts_platform_fields(self):
        """RouteRequest accepts optional platform and platform_id."""
        from pa_routing.models.requests import RouteRequest

        request = RouteRequest(
            session_id=uuid4(),
            message="Hello",
            platform="telegram",
            platform_id="123456789",
        )

        assert request.platform == "telegram"
        assert request.platform_id == "123456789"

    def test_route_request_platform_fields_optional(self):
        """RouteRequest works without platform fields (backward compatible)."""
        from pa_routing.models.requests import RouteRequest

        request = RouteRequest(
            session_id=uuid4(),
            message="Hello",
        )

        assert request.platform is None
        assert request.platform_id is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_requests.py -v
```
Expected: FAIL (AttributeError or ValidationError - fields don't exist)

**Step 3: Read existing model**

Read `pa-routing-handler/src/pa_routing/models/requests.py` to understand current structure.

**Step 4: Add platform fields to RouteRequest**

```python
# Add to RouteRequest class:
    # Optional identity context (for multi-modality)
    platform: Optional[str] = None      # "slack", "telegram", "web", "email"
    platform_id: Optional[str] = None   # Platform-specific user ID
```

**Step 5: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_requests.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/models/requests.py
git add pa-routing-handler/tests/models/test_requests.py
git commit -m "feat: add platform identity fields to RouteRequest"
```

---

### Task 3: Add Identity and Conversation Fields to Route Response Model

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/models/responses.py`
- Test: `pa-routing-handler/tests/models/test_responses.py`

**Step 1: Write failing test**

```python
# pa-routing-handler/tests/models/test_responses.py
"""Tests for response models."""

import pytest


class TestRouteResponse:
    """Tests for RouteResponse model with identity/conversation fields."""

    def test_route_response_includes_identity_fields(self):
        """RouteResponse includes identity_id and conversation_id."""
        from pa_routing.models.responses import RouteResponse

        response = RouteResponse(
            agent_id="agent-123",
            agent_name="Calendar Agent",
            routing_method="keyword",
            routing_reason="Matched 'schedule'",
            confidence=0.9,
            processing_time_ms=5,
            identity_id="identity-chad-456",
            conversation_id="conv-789",
        )

        assert response.identity_id == "identity-chad-456"
        assert response.conversation_id == "conv-789"

    def test_route_response_identity_fields_optional(self):
        """RouteResponse works without identity fields (backward compatible)."""
        from pa_routing.models.responses import RouteResponse

        response = RouteResponse(
            agent_id="agent-123",
            agent_name="Calendar Agent",
            routing_method="keyword",
            routing_reason="Matched 'schedule'",
            confidence=0.9,
            processing_time_ms=5,
        )

        assert response.identity_id is None
        assert response.conversation_id is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_responses.py -v
```
Expected: FAIL

**Step 3: Read existing model**

Read `pa-routing-handler/src/pa_routing/models/responses.py` to understand current structure.

**Step 4: Add identity and conversation fields to RouteResponse**

```python
# Add to RouteResponse class:
    # Identity and conversation resolution
    identity_id: Optional[str] = None       # Resolved Letta identity
    conversation_id: Optional[str] = None   # For caller to use with Letta
```

**Step 5: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_responses.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/models/responses.py
git add pa-routing-handler/tests/models/test_responses.py
git commit -m "feat: add identity_id and conversation_id to RouteResponse"
```

---

### Task 4: Add default_identity_id to Settings

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/settings.py`
- Modify: `.env` (add new variable)

**Step 1: Read existing settings**

Read `pa-routing-handler/src/pa_routing/settings.py` to understand current structure.

**Step 2: Add default_identity_id setting**

```python
# Add to Settings class:
    default_identity_id: Optional[str] = None  # Your Letta identity ID for single-user default
```

**Step 3: Look up your identity ID**

Run:
```bash
curl -s http://localhost:8283/v1/identities/ | python3 -c "
import sys, json
data = json.load(sys.stdin)
for i in data:
    if 'chad' in i.get('name', '').lower() or 'cdorsey' in i.get('identifier_key', '').lower():
        print(f\"{i['name']}: {i['id']}\")
"
```

**Step 4: Add to .env file**

```bash
# Add to .env:
DEFAULT_IDENTITY_ID=identity-xxx-your-id-here
```

**Step 5: Verify setting loads**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -c "from pa_routing.settings import settings; print(f'default_identity_id: {settings.default_identity_id}')"
```
Expected: Shows your identity ID

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/settings.py
git commit -m "feat: add default_identity_id setting for single-user default"
```

---

## Phase 2: Identity Resolution

### Task 5: Add Identity Resolution to Routing Endpoint

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`
- Test: `pa-routing-handler/tests/routers/test_routing_identity.py`

**Step 1: Write failing test**

```python
# pa-routing-handler/tests/routers/test_routing_identity.py
"""Tests for identity resolution in routing."""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestRoutingIdentityResolution:
    """Tests for identity resolution in route_message."""

    @pytest.fixture
    def mock_identity_service(self):
        """Create mock IdentityService."""
        service = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_resolves_identity_from_platform(self, mock_identity_service):
        """Resolves identity when platform and platform_id provided."""
        from pa_routing.routers.routing import resolve_identity

        mock_identity = MagicMock()
        mock_identity.id = "identity-telegram-user"
        mock_identity_service.find_by_property.return_value = mock_identity

        result = resolve_identity(
            platform="telegram",
            platform_id="123456789",
            identity_service=mock_identity_service,
            default_identity_id="identity-default",
        )

        assert result == "identity-telegram-user"
        mock_identity_service.find_by_property.assert_called_once_with(
            "telegram_id", "123456789"
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_default_identity(self, mock_identity_service):
        """Falls back to default when no platform provided."""
        from pa_routing.routers.routing import resolve_identity

        result = resolve_identity(
            platform=None,
            platform_id=None,
            identity_service=mock_identity_service,
            default_identity_id="identity-default",
        )

        assert result == "identity-default"
        mock_identity_service.find_by_property.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_when_identity_not_found(self, mock_identity_service):
        """Falls back to default when platform identity not found."""
        from pa_routing.routers.routing import resolve_identity

        mock_identity_service.find_by_property.return_value = None

        result = resolve_identity(
            platform="telegram",
            platform_id="unknown-user",
            identity_service=mock_identity_service,
            default_identity_id="identity-default",
        )

        assert result == "identity-default"
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_routing_identity.py -v
```
Expected: FAIL (ImportError - resolve_identity doesn't exist)

**Step 3: Implement resolve_identity function**

Add to `pa-routing-handler/src/pa_routing/routers/routing.py`:

```python
def resolve_identity(
    platform: Optional[str],
    platform_id: Optional[str],
    identity_service: Any,
    default_identity_id: Optional[str],
) -> Optional[str]:
    """
    Resolve identity from platform context or fall back to default.

    Args:
        platform: Platform name (e.g., "telegram", "slack")
        platform_id: Platform-specific user ID
        identity_service: IdentityService instance
        default_identity_id: Fallback identity for single-user mode

    Returns:
        Resolved identity_id or None
    """
    if platform and platform_id:
        # Multi-modality: resolve via IdentityService
        property_key = f"{platform}_id"
        identity = identity_service.find_by_property(property_key, platform_id)
        if identity:
            return identity.id
        # Fall through to default if not found

    # Single-user default (web UI, etc.)
    return default_identity_id
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_routing_identity.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git add pa-routing-handler/tests/routers/test_routing_identity.py
git commit -m "feat: add identity resolution function for multi-modality"
```

---

### Task 6: Integrate Identity Resolution into route_message

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

**Step 1: Read current route_message implementation**

Read `pa-routing-handler/src/pa_routing/routers/routing.py` to understand the current flow.

**Step 2: Initialize IdentityService**

Add near top of file with other initializations:

```python
from pa_routing.services.identity_service import IdentityService

# Initialize identity service
_letta_client_for_identity = LettaClient(LETTA_BASE_URL)
_identity_service = IdentityService(letta_client=_letta_client_for_identity._client)
```

**Step 3: Add identity resolution to route_message**

In `route_message()`, after getting session context:

```python
    # Resolve identity
    identity_id = resolve_identity(
        platform=request.platform,
        platform_id=request.platform_id,
        identity_service=_identity_service,
        default_identity_id=settings.default_identity_id,
    )
```

**Step 4: Include identity_id in response**

Update the return statement:

```python
    return RouteResponse(
        agent_id=result.agent_id,
        agent_name=result.agent_name,
        routing_method=routing_method,
        routing_reason=result.reason,
        confidence=result.confidence,
        processing_time_ms=processing_time_ms,
        session_context_entries=session_ctx.entry_count,
        request_id=thread.request_id if thread else None,
        context_injection=context_injection if context_injection else None,
        briefing_injection=briefing_injection if briefing_injection else None,
        identity_id=identity_id,  # NEW
    )
```

**Step 5: Add logging**

Update the logger.info call to include identity:

```python
    logger.info(
        "route_decision",
        session_id=str(request.session_id),
        identity_id=identity_id,  # NEW
        agent_id=result.agent_id,
        ...
    )
```

**Step 6: Test manually**

Run:
```bash
curl -X POST http://localhost:5201/v1/route \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "hello"}' | jq '.identity_id'
```
Expected: Your default identity ID

**Step 7: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: integrate identity resolution into route_message"
```

---

## Phase 3: Session Persistence

### Task 7: Create Persistent Session Store

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/session_store.py`
- Test: `pa-routing-handler/tests/services/test_session_store_persistence.py`

**Step 1: Write failing tests**

```python
# pa-routing-handler/tests/services/test_session_store_persistence.py
"""Tests for persistent session store."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestPersistentSessionStore:
    """Tests for SessionStore with Supabase persistence."""

    @pytest.fixture
    def mock_supabase(self):
        """Create mock Supabase client."""
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        return client

    def test_loads_from_supabase_on_cache_miss(self, mock_supabase):
        """Loads session state from Supabase when not in cache."""
        from pa_routing.services.session_store import PersistentSessionStore

        # Simulate existing data in Supabase
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{
            "identity_id": "identity-123",
            "last_responding_agent_id": "agent-abc",
            "last_responding_agent_name": "Calendar Agent",
            "context_entries": [{"agent": "Calendar", "action": "Scheduled meeting"}],
        }]

        store = PersistentSessionStore(supabase_client=mock_supabase)
        ctx = store.get_or_create("identity-123")

        assert ctx.last_responding_agent_id == "agent-abc"
        assert ctx.last_responding_agent_name == "Calendar Agent"

    def test_uses_cache_on_subsequent_calls(self, mock_supabase):
        """Uses cached session on subsequent calls (no DB hit)."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(supabase_client=mock_supabase)

        # First call - cache miss
        ctx1 = store.get_or_create("identity-123")
        # Second call - should use cache
        ctx2 = store.get_or_create("identity-123")

        assert ctx1 is ctx2
        # Supabase should only be called once
        assert mock_supabase.table.return_value.select.call_count == 1

    def test_persists_on_update(self, mock_supabase):
        """Persists session state to Supabase on update."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(supabase_client=mock_supabase)
        ctx = store.get_or_create("identity-123")

        # Update session
        ctx.last_responding_agent_id = "agent-xyz"
        ctx.last_responding_agent_name = "Email Agent"
        store.persist("identity-123")

        # Verify upsert was called
        mock_supabase.table.assert_called_with("session_state")
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_session_store_persistence.py -v
```
Expected: FAIL (ImportError - PersistentSessionStore doesn't exist)

**Step 3: Read existing session_store.py**

Read `pa-routing-handler/src/pa_routing/services/session_store.py` to understand current structure.

**Step 4: Implement PersistentSessionStore**

Replace or extend session_store.py:

```python
"""Persistent session store with Supabase backing.

Phase 1: Simple in-memory dict with TTL.
Phase 3: Adds Supabase persistence for restart recovery.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog

from pa_routing.models.session_context import SessionContext

logger = structlog.get_logger()

SESSION_TTL_MINUTES = 60


class PersistentSessionStore:
    """
    Session store with in-memory cache and Supabase persistence.

    - Fast reads from in-memory cache (~0ms)
    - Hydrates from Supabase on cache miss (~20ms)
    - Async persistence on updates (non-blocking)
    """

    def __init__(self, supabase_client: Any = None):
        self._cache: dict[str, SessionContext] = {}
        self._supabase = supabase_client

    def get_or_create(self, identity_id: str) -> SessionContext:
        """Get existing session or create new one."""
        self._cleanup_stale()

        # Check cache first (fast path)
        if identity_id in self._cache:
            return self._cache[identity_id]

        # Cache miss: try to hydrate from Supabase
        ctx = self._load_from_db(identity_id)
        if ctx is None:
            ctx = SessionContext()

        self._cache[identity_id] = ctx
        return ctx

    def get(self, identity_id: str) -> Optional[SessionContext]:
        """Get session if exists, None otherwise."""
        if identity_id in self._cache:
            return self._cache[identity_id]
        return self._load_from_db(identity_id)

    def clear(self, identity_id: str) -> None:
        """Remove session for identity."""
        if identity_id in self._cache:
            del self._cache[identity_id]
        self._delete_from_db(identity_id)

    def persist(self, identity_id: str) -> None:
        """Persist session state to Supabase (fire-and-forget)."""
        ctx = self._cache.get(identity_id)
        if ctx and self._supabase:
            try:
                self._supabase.table("session_state").upsert({
                    "identity_id": identity_id,
                    "last_responding_agent_id": ctx.last_responding_agent_id,
                    "last_responding_agent_name": ctx.last_responding_agent_name,
                    "last_response_time": ctx.last_response_time.isoformat() if ctx.last_response_time else None,
                    "context_entries": [e.to_dict() if hasattr(e, 'to_dict') else e for e in ctx.entries[-20:]],  # Last 20 entries
                }).execute()
            except Exception as e:
                logger.warning("session_persist_failed", error=str(e), identity_id=identity_id)

    def _load_from_db(self, identity_id: str) -> Optional[SessionContext]:
        """Load session state from Supabase."""
        if not self._supabase:
            return None

        try:
            result = (
                self._supabase.table("session_state")
                .select("*")
                .eq("identity_id", identity_id)
                .execute()
            )
            if result.data:
                row = result.data[0]
                ctx = SessionContext()
                ctx.last_responding_agent_id = row.get("last_responding_agent_id")
                ctx.last_responding_agent_name = row.get("last_responding_agent_name")
                if row.get("last_response_time"):
                    ctx.last_response_time = datetime.fromisoformat(row["last_response_time"].replace("Z", "+00:00"))
                # Restore context entries if needed
                return ctx
        except Exception as e:
            logger.warning("session_load_failed", error=str(e), identity_id=identity_id)

        return None

    def _delete_from_db(self, identity_id: str) -> None:
        """Delete session state from Supabase."""
        if self._supabase:
            try:
                self._supabase.table("session_state").delete().eq("identity_id", identity_id).execute()
            except Exception as e:
                logger.warning("session_delete_failed", error=str(e), identity_id=identity_id)

    def _cleanup_stale(self) -> None:
        """Remove sessions that haven't been active in TTL minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
        stale = [
            identity_id
            for identity_id, ctx in self._cache.items()
            if ctx.last_activity < cutoff
        ]
        for identity_id in stale:
            del self._cache[identity_id]


# For backward compatibility, keep the old name
SessionStore = PersistentSessionStore

# Global session store instance (initialized without Supabase - will be set in main.py)
session_store = PersistentSessionStore()
```

**Step 5: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_session_store_persistence.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/session_store.py
git add pa-routing-handler/tests/services/test_session_store_persistence.py
git commit -m "feat: add Supabase persistence to session store"
```

---

### Task 8: Initialize Session Store with Supabase Client

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/main.py` or initialization code
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

**Step 1: Read main.py to understand app initialization**

Read `pa-routing-handler/src/pa_routing/main.py`.

**Step 2: Add Supabase client initialization**

Add Supabase client setup and pass to session_store:

```python
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://supabase-rest:3000")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_KEY else None

# Initialize session store with Supabase
from pa_routing.services.session_store import session_store
session_store._supabase = supabase_client
```

**Step 3: Update routing.py to persist after updates**

In `complete_thread()`, add persistence call:

```python
    # After updating session context
    session_store.persist(identity_id)
```

**Step 4: Test manually**

Run:
```bash
# Send a message
curl -X POST http://localhost:5201/v1/route \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "schedule meeting"}'

# Check Supabase for persisted state
docker exec -it supabase-db psql -U postgres -d postgres -c \
  "SELECT * FROM pa_web.session_state LIMIT 5;"
```

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/main.py
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: initialize session store with Supabase client"
```

---

### Task 9: Update Session Store Key from session_id to identity_id

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

**Step 1: Read routing.py to find session_store usage**

Identify all places where `session_store.get_or_create(user_id)` is called.

**Step 2: Update to use identity_id**

Change from:
```python
user_id = request.user_id or str(request.session_id)
session_ctx = session_store.get_or_create(user_id)
```

To:
```python
# Resolve identity first
identity_id = resolve_identity(
    platform=request.platform,
    platform_id=request.platform_id,
    identity_service=_identity_service,
    default_identity_id=settings.default_identity_id,
)

# Use identity_id for session context (enables cross-platform context sharing)
session_key = identity_id or str(request.session_id)  # Fallback if no identity
session_ctx = session_store.get_or_create(session_key)
```

**Step 3: Update other endpoints that use session_store**

Review and update:
- `complete_thread()`
- `get_session_threads()`
- `clear_session_context()`
- etc.

**Step 4: Test manually**

Run:
```bash
# Restart handler
docker-compose restart pa-routing-handler

# Send message, verify session restored from Supabase
curl -X POST http://localhost:5201/v1/route \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "hello"}'
```

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: key session store by identity_id for cross-platform context"
```

---

## Phase 4: Conversation Integration

### Task 10: Add Conversation Lookup to route_message

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`
- Test: `pa-routing-handler/tests/routers/test_routing_conversation.py`

**Step 1: Write failing test**

```python
# pa-routing-handler/tests/routers/test_routing_conversation.py
"""Tests for conversation lookup in routing."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


class TestRoutingConversationLookup:
    """Tests for conversation lookup in route_message."""

    @pytest.fixture
    def mock_conversation_service(self):
        """Create mock ConversationService."""
        service = MagicMock()
        service.get_or_create_conversation = AsyncMock(return_value={
            "conversation_id": "conv-test-123",
            "identity_id": "identity-test",
            "created": False,
        })
        return service

    @pytest.mark.asyncio
    async def test_returns_conversation_id_in_response(self):
        """Route response includes conversation_id."""
        # This will be an integration test after implementation
        pass
```

**Step 2: Add conversation lookup to route_message**

In `route_message()`, after routing decision:

```python
    # Lookup or create conversation for this identity + agent
    conversation_id = None
    if identity_id:
        try:
            conv_result = await _conversation_service.get_or_create_conversation(
                user_id=identity_id,
                user_source=request.platform or "web",
                agent_id=result.agent_id,
            )
            conversation_id = conv_result.get("conversation_id")
        except Exception as e:
            logger.warning("conversation_lookup_failed", error=str(e), identity_id=identity_id)
```

**Step 3: Initialize ConversationService**

Add near top of routing.py:

```python
from pa_routing.services.conversation_service import ConversationService

# Initialize conversation service
_conversation_service = ConversationService(
    letta_client=_letta_client._client,
    supabase_client=supabase_client,
    identity_service=_identity_service,
)
```

**Step 4: Include conversation_id in response**

Update return statement:

```python
    return RouteResponse(
        ...
        identity_id=identity_id,
        conversation_id=conversation_id,  # NEW
    )
```

**Step 5: Test manually**

Run:
```bash
curl -X POST http://localhost:5201/v1/route \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "message": "schedule meeting"}' | jq '.conversation_id'
```
Expected: A conversation ID string

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git add pa-routing-handler/tests/routers/test_routing_conversation.py
git commit -m "feat: add conversation lookup to route_message"
```

---

### Task 11: Update Web UI to Pass conversation_id to Letta

**Files:**
- Modify: `pa-web-ui/app.py`

**Step 1: Read current Letta call in app.py**

Find where `letta_payload` is built and sent to Letta.

**Step 2: Add conversation_id to Letta payload**

Update the Letta payload construction:

```python
# Get conversation_id from route response
conversation_id = route_data.get("conversation_id")

letta_payload = {
    "messages": [{"role": "user", "content": augmented_message}],
}

# Add conversation_id if available
if conversation_id:
    letta_payload["conversation_id"] = conversation_id
```

**Step 3: Add logging**

```python
logger.info(
    "letta_stream_starting",
    agent_id=selected_agent_id,
    agent_name=agent_name,
    request_id=request_id,
    conversation_id=conversation_id,  # NEW
)
```

**Step 4: Test manually**

1. Open web UI
2. Send a message
3. Check logs for `conversation_id` in Letta request
4. Send another message to same agent
5. Verify agent has context from previous message

**Step 5: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: pass conversation_id to Letta for persistent context"
```

---

## Phase 5: Verification

### Task 12: Integration Tests

**Files:**
- Create: `pa-routing-handler/tests/integration/test_conversations_e2e.py`

**Step 1: Write integration test**

```python
# pa-routing-handler/tests/integration/test_conversations_e2e.py
"""End-to-end tests for conversation integration."""

import pytest
import httpx
import os

ROUTING_HANDLER_URL = os.getenv("ROUTING_HANDLER_URL", "http://localhost:5201")


@pytest.mark.integration
class TestConversationsE2E:
    """End-to-end conversation integration tests."""

    def test_route_returns_identity_and_conversation(self):
        """Route response includes identity_id and conversation_id."""
        response = httpx.post(
            f"{ROUTING_HANDLER_URL}/v1/route",
            json={
                "session_id": "e2e-test-session",
                "message": "schedule a meeting",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify identity resolution
        assert "identity_id" in data
        assert data["identity_id"] is not None

        # Verify conversation lookup
        assert "conversation_id" in data
        assert data["conversation_id"] is not None

    def test_session_persists_across_restart(self):
        """Session context survives handler restart."""
        # This test requires manual verification:
        # 1. Send message, note last_responding_agent
        # 2. Restart handler
        # 3. Send follow-up, verify contextual routing works
        pass
```

**Step 2: Run integration tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/integration/test_conversations_e2e.py -v -m integration
```

**Step 3: Manual verification checklist**

- [ ] Route response includes `identity_id`
- [ ] Route response includes `conversation_id`
- [ ] Restart handler → session context restored
- [ ] Web UI messages include conversation context
- [ ] Agent remembers previous conversation

**Step 4: Commit**

```bash
git add pa-routing-handler/tests/integration/test_conversations_e2e.py
git commit -m "test: add e2e tests for conversation integration"
```

---

### Task 13: Final Verification and Cleanup

**Step 1: Run all tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest -v
```
Expected: All tests pass

**Step 2: Check for any regressions**

Run:
```bash
# Test existing functionality
curl http://localhost:5201/v1/agents | jq '.count'
curl http://localhost:5201/health
```

**Step 3: Update documentation**

Add note to CLAUDE.md about new identity/conversation fields if needed.

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete routing handler conversations integration"
```

---

## Verification Plan

### Unit Tests
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/ -v
```

### Integration Tests
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/integration/ -v -m integration
```

### Manual Verification
1. **Identity Resolution:** Send request with platform/platform_id → verify correct identity_id
2. **Session Persistence:** Restart handler → verify session context restored
3. **Conversation Lookup:** Send message → verify conversation_id in response
4. **Agent Context:** Send multiple messages → verify agent remembers conversation

---

## Success Criteria

1. **Persistence:** Restart handler → session context restored from Supabase
2. **Identity Resolution:** Handler logs show `identity_id` resolved for requests
3. **Conversations:** Letta agent receives `conversation_id`, maintains history
4. **Multi-modality Ready:** Request with `platform`/`platform_id` resolves correct identity
5. **No Regression:** Existing routing behavior unchanged, all tests pass
