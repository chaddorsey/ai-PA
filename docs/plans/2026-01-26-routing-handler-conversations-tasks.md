# Routing Handler Conversations Integration - Task Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add persistence, identity resolution, and Letta Conversations to the routing handler while maintaining ~2ms routing latency.

**Architecture:** Hybrid persistence (in-memory cache + Supabase backup). Handler resolves identity and looks up/creates conversations. State keyed by `identity_id` for cross-platform support.

**Tech Stack:** Python 3.9+, FastAPI, Letta API (Identities + Conversations), Supabase, pytest

**Design Document:** `docs/plans/2026-01-26-routing-handler-conversations-design.md`

---

## Components to Modify

| File | Changes |
|------|---------|
| `pa-routing-handler/src/pa_routing/models/requests.py` | Add `platform`, `platform_id` fields |
| `pa-routing-handler/src/pa_routing/models/responses.py` | Add `identity_id`, `conversation_id` fields |
| `pa-routing-handler/src/pa_routing/routers/routing.py` | Identity resolution, conversation lookup |
| `pa-routing-handler/src/pa_routing/services/session_store.py` | Supabase persistence, identity-keyed |
| `pa-routing-handler/src/pa_routing/settings.py` | Add `default_identity_id` |
| `pa-web-ui/app.py` | Pass `conversation_id` to Letta |
| Supabase | New table `pa_web.session_state` |

---

## Agent Parallelization Opportunities

| Opportunity | Tasks | Notes |
|-------------|-------|-------|
| **Phase 1 Parallel** | Tasks 1.1-1.4 | All infrastructure tasks are independent |
| **Phase 2 Parallel** | Tasks 2.1 + 2.2 | Settings and identity resolution can run together |
| **Code Review** | After Phase 2 | Checkpoint before persistence changes |
| **Phase 4 Parallel** | Tasks 4.1 + 4.2 | Handler conversation + Web UI update are independent |

---

## Phase 1: Infrastructure (No Behavior Change)

### Task 1.1: Create Session State Table in Supabase

**Files:**
- Create: SQL migration in Supabase

**Step 1: Create the table with auto-update trigger**

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
docker exec supabase-db psql -U postgres -d postgres -c "\d pa_web.session_state"
```
Expected: Table schema displayed

**Step 3: Commit migration notes**

```bash
git add docs/plans/
git commit -m "docs: add session_state table migration"
```

---

### Task 1.2: Add Identity Fields to RouteRequest

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/models/requests.py`
- Test: `pa-routing-handler/tests/models/test_requests.py`

**Step 1: Write failing test**

```python
def test_route_request_with_platform_fields():
    """RouteRequest accepts platform and platform_id fields."""
    from pa_routing.models.requests import RouteRequest
    from uuid import uuid4

    req = RouteRequest(
        session_id=uuid4(),
        message="test",
        platform="telegram",
        platform_id="123456789"
    )
    assert req.platform == "telegram"
    assert req.platform_id == "123456789"

def test_route_request_platform_fields_optional():
    """Platform fields are optional (backwards compatible)."""
    from pa_routing.models.requests import RouteRequest
    from uuid import uuid4

    req = RouteRequest(session_id=uuid4(), message="test")
    assert req.platform is None
    assert req.platform_id is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_requests.py -v -k "platform"
```
Expected: FAIL

**Step 3: Add fields to RouteRequest**

Add to `RouteRequest` class:
```python
# NEW: Optional identity context (for multi-modality)
platform: Optional[str] = None      # "slack", "telegram", "web"
platform_id: Optional[str] = None   # Platform-specific user ID
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_requests.py -v -k "platform"
```
Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/models/requests.py
git add pa-routing-handler/tests/models/test_requests.py
git commit -m "feat: add platform and platform_id to RouteRequest"
```

---

### Task 1.3: Add Identity and Conversation Fields to RouteResponse

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/models/responses.py`
- Test: `pa-routing-handler/tests/models/test_responses.py`

**Step 1: Write failing test**

```python
def test_route_response_with_identity_fields():
    """RouteResponse includes identity_id and conversation_id."""
    from pa_routing.models.responses import RouteResponse

    resp = RouteResponse(
        agent_id="agent-123",
        agent_name="Test Agent",
        routing_method="explicit",
        routing_reason="test",
        confidence=1.0,
        processing_time_ms=2,
        identity_id="identity-456",
        conversation_id="conv-789"
    )
    assert resp.identity_id == "identity-456"
    assert resp.conversation_id == "conv-789"

def test_route_response_identity_fields_optional():
    """Identity fields are optional (backwards compatible)."""
    from pa_routing.models.responses import RouteResponse

    resp = RouteResponse(
        agent_id="agent-123",
        agent_name="Test Agent",
        routing_method="explicit",
        routing_reason="test",
        confidence=1.0,
        processing_time_ms=2
    )
    assert resp.identity_id is None
    assert resp.conversation_id is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_responses.py -v -k "identity"
```
Expected: FAIL

**Step 3: Add fields to RouteResponse**

Add to `RouteResponse` class:
```python
# NEW: Identity and conversation resolution
identity_id: Optional[str] = None       # Resolved Letta identity
conversation_id: Optional[str] = None   # For caller to use with Letta
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_responses.py -v -k "identity"
```
Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/models/responses.py
git add pa-routing-handler/tests/models/test_responses.py
git commit -m "feat: add identity_id and conversation_id to RouteResponse"
```

---

### Task 1.4: Add default_identity_id to Settings

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/settings.py`
- Modify: `.env` (add DEFAULT_IDENTITY_ID)

**Step 1: Add setting**

Add to Settings class:
```python
# Identity resolution
default_identity_id: Optional[str] = Field(
    default=None,
    description="Default identity ID for single-user mode (web UI)"
)
```

**Step 2: Look up your identity ID from Letta**

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
Note the identity ID for use in .env.

**Step 3: Add to .env file**

```bash
# Add to .env:
DEFAULT_IDENTITY_ID=identity-xxx-your-id-here
```

**Step 4: Verify settings load**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -c "from pa_routing.settings import settings; print(f'default_identity_id: {settings.default_identity_id}')"
```
Expected: Shows your identity ID

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/settings.py
git commit -m "feat: add default_identity_id setting"
```

---

## Phase 2: Identity Resolution

### Task 2.1: Create resolve_identity Function

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`
- Test: `pa-routing-handler/tests/routers/test_routing_identity.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_resolve_identity_with_platform():
    """Resolves identity when platform/platform_id provided."""
    from pa_routing.routers.routing import resolve_identity

    # Mock IdentityService
    mock_service = MagicMock()
    mock_identity = MagicMock()
    mock_identity.id = "identity-123"
    mock_service.find_by_property.return_value = mock_identity

    result = await resolve_identity(
        platform="telegram",
        platform_id="user456",
        identity_service=mock_service,
        default_identity_id=None
    )

    assert result == "identity-123"
    mock_service.find_by_property.assert_called_with("telegram_id", "user456")

@pytest.mark.asyncio
async def test_resolve_identity_default_fallback():
    """Falls back to default_identity_id when no platform provided."""
    from pa_routing.routers.routing import resolve_identity

    result = await resolve_identity(
        platform=None,
        platform_id=None,
        identity_service=None,
        default_identity_id="identity-default"
    )

    assert result == "identity-default"
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_routing.py -v -k "resolve_identity"
```
Expected: FAIL (function doesn't exist)

**Step 3: Implement resolve_identity**

Add to `routing.py`:
```python
async def resolve_identity(
    platform: Optional[str],
    platform_id: Optional[str],
    identity_service: Optional[Any],
    default_identity_id: Optional[str]
) -> Optional[str]:
    """
    Resolve identity from platform credentials or fall back to default.

    Args:
        platform: Platform name ("telegram", "slack", etc.)
        platform_id: Platform-specific user ID
        identity_service: IdentityService instance (optional)
        default_identity_id: Fallback identity for single-user mode

    Returns:
        Resolved identity_id or None if resolution fails
    """
    if platform and platform_id and identity_service:
        property_key = f"{platform}_id"
        identity = identity_service.find_by_property(property_key, platform_id)
        if identity:
            logger.info("identity_resolved", platform=platform, identity_id=identity.id)
            return identity.id
        logger.warning("identity_not_found", platform=platform, platform_id=platform_id)

    if default_identity_id:
        logger.debug("using_default_identity", identity_id=default_identity_id)
        return default_identity_id

    return None
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_routing.py -v -k "resolve_identity"
```
Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git add pa-routing-handler/tests/routers/test_routing.py
git commit -m "feat: add resolve_identity function"
```

---

### Task 2.2: Integrate Identity Resolution into route_message

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

**Step 1: Initialize IdentityService**

Add near top of file with other initializations:
```python
from pa_routing.services.identity_service import IdentityService

# Initialize identity service (uses existing Letta client)
_identity_service = IdentityService(letta_client=_letta_client._client)
```

**Step 2: Add identity resolution to route_message**

Add after session context retrieval:
```python
# Resolve identity
identity_id = resolve_identity(
    platform=request.platform,
    platform_id=request.platform_id,
    identity_service=_identity_service,
    default_identity_id=settings.default_identity_id
)
```

**Step 2: Include identity_id in response**

Update return statement:
```python
return RouteResponse(
    # ... existing fields ...
    identity_id=identity_id,
    conversation_id=None,  # Phase 4 will populate this
)
```

**Step 3: Test manually**

Run:
```bash
curl -X POST http://localhost:5201/v1/route \
  -H "Content-Type: application/json" \
  -d '{"session_id": "00000000-0000-0000-0000-000000000001", "message": "test"}'
```
Expected: Response includes `identity_id` field

**Step 4: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: integrate identity resolution into route_message"
```

---

## Phase 3: Session Persistence

### Task 3.1: Create PersistentSessionStore

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/session_store.py`
- Test: `pa-routing-handler/tests/services/test_session_store.py`

**Step 1: Write failing tests**

```python
class TestPersistentSessionStore:
    @pytest.fixture
    def mock_supabase(self):
        client = MagicMock()
        client.table.return_value = client
        client.select.return_value = client
        client.eq.return_value = client
        client.upsert.return_value = client
        client.execute.return_value = MagicMock(data=[])
        return client

    def test_get_or_create_cache_hit(self, mock_supabase):
        """Returns cached session without DB call."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)
        # Prime the cache
        ctx1 = store.get_or_create("identity-123")
        ctx1.append(agent="test", action="first")

        # Should return cached version
        ctx2 = store.get_or_create("identity-123")
        assert ctx2.entry_count == 1

        # DB should NOT be called for cached lookup
        mock_supabase.table.assert_called_once()  # Only initial hydration

    def test_hydrates_from_db_on_cold_start(self, mock_supabase):
        """Hydrates session from Supabase on first access."""
        from pa_routing.services.session_store import PersistentSessionStore

        # Simulate existing DB record
        mock_supabase.execute.return_value = MagicMock(data=[{
            "identity_id": "identity-123",
            "last_responding_agent_id": "agent-abc",
            "last_responding_agent_name": "Main Agent",
            "context_entries": [{"agent": "test", "action": "previous"}]
        }])

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-123")

        assert ctx.last_responding_agent_id == "agent-abc"
        assert ctx.entry_count >= 1

    def test_persists_on_append(self, mock_supabase):
        """Persists to Supabase when context is modified."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-123")
        ctx.append(agent="test", action="new action")

        # Trigger persist (may be async/debounced)
        store._persist("identity-123", ctx)

        mock_supabase.table.assert_called_with("session_state")
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_session_store.py -v -k "Persistent"
```
Expected: FAIL (PersistentSessionStore doesn't exist)

**Step 3: Implement PersistentSessionStore**

Replace `session_store.py`:
```python
"""Hybrid session store with in-memory cache and Supabase persistence.

Architecture (2026-01-26):
- In-memory cache for fast lookups (~0ms)
- Supabase backup for persistence across restarts (~20ms hydration)
- Fire-and-forget async writes for non-blocking persistence
- Keyed by identity_id for cross-platform state sharing
"""

from datetime import datetime, timedelta
from typing import Any, Optional
import asyncio
import structlog

from pa_routing.models.session_context import SessionContext

logger = structlog.get_logger()

SESSION_TTL_MINUTES = 60


class PersistentSessionStore:
    """Hybrid session store with in-memory cache and Supabase backup."""

    def __init__(self, supabase_client: Any):
        self._cache: dict[str, SessionContext] = {}
        self._supabase = supabase_client

    def get_or_create(self, identity_id: str) -> SessionContext:
        """Get existing session or create new one."""
        self._cleanup_stale()

        if identity_id in self._cache:
            return self._cache[identity_id]

        # Cache miss: hydrate from Supabase
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
        # Also clear from DB
        try:
            self._supabase.table("session_state").delete().eq(
                "identity_id", identity_id
            ).execute()
        except Exception as e:
            logger.warning("session_clear_db_failed", error=str(e))

    def _load_from_db(self, identity_id: str) -> Optional[SessionContext]:
        """Load session from Supabase."""
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
                    ctx.last_response_time = datetime.fromisoformat(
                        row["last_response_time"].replace("Z", "+00:00")
                    )
                # Restore context entries
                for entry in row.get("context_entries", []):
                    ctx.append(
                        agent=entry.get("agent", "unknown"),
                        action=entry.get("action", ""),
                        refs=entry.get("refs")
                    )
                logger.info("session_hydrated", identity_id=identity_id)
                return ctx
        except Exception as e:
            logger.warning("session_hydrate_failed", identity_id=identity_id, error=str(e))
        return None

    def _persist(self, identity_id: str, ctx: SessionContext) -> None:
        """Persist session to Supabase (fire-and-forget)."""
        try:
            self._supabase.table("session_state").upsert({
                "identity_id": identity_id,
                "last_responding_agent_id": ctx.last_responding_agent_id,
                "last_responding_agent_name": ctx.last_responding_agent_name,
                "last_response_time": ctx.last_response_time.isoformat() if ctx.last_response_time else None,
                "context_entries": [e.to_dict() for e in ctx._entries],
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            logger.debug("session_persisted", identity_id=identity_id)
        except Exception as e:
            logger.warning("session_persist_failed", identity_id=identity_id, error=str(e))

    def persist_async(self, identity_id: str, ctx: SessionContext) -> None:
        """Schedule async persist (non-blocking)."""
        asyncio.create_task(self._persist_async(identity_id, ctx))

    async def _persist_async(self, identity_id: str, ctx: SessionContext) -> None:
        """Async wrapper for persist."""
        self._persist(identity_id, ctx)

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


# Backwards compatible: default to in-memory only
class SessionStore(PersistentSessionStore):
    """Legacy wrapper - uses in-memory only if no Supabase provided."""

    def __init__(self, supabase_client: Any = None):
        if supabase_client:
            super().__init__(supabase_client)
        else:
            self._cache: dict[str, SessionContext] = {}
            self._supabase = None

    def _load_from_db(self, identity_id: str) -> Optional[SessionContext]:
        if self._supabase is None:
            return None
        return super()._load_from_db(identity_id)

    def _persist(self, identity_id: str, ctx: SessionContext) -> None:
        if self._supabase is None:
            return
        super()._persist(identity_id, ctx)


# Global session store instance (will be initialized with Supabase in main.py)
session_store = SessionStore()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_session_store.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/session_store.py
git add pa-routing-handler/tests/services/test_session_store.py
git commit -m "feat: add PersistentSessionStore with Supabase backup"
```

---

### Task 3.2: Initialize Session Store with Supabase Client

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/main.py`

**Step 1: Add Supabase client initialization**

Add to app startup:
```python
from supabase import create_client
from pa_routing.services.session_store import session_store

@app.on_event("startup")
async def startup():
    # Initialize session store with Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        supabase = create_client(supabase_url, supabase_key)
        session_store._supabase = supabase
        logger.info("session_store_initialized", persistence="supabase")
    else:
        logger.warning("session_store_initialized", persistence="memory_only")
```

**Step 2: Test restart persistence**

Run:
```bash
# Send a message
curl -X POST http://localhost:5201/v1/route -H "Content-Type: application/json" \
  -d '{"session_id": "00000000-0000-0000-0000-000000000001", "message": "test"}'

# Restart handler
docker-compose restart pa-routing-handler

# Send another message - should have context
curl -X POST http://localhost:5201/v1/route -H "Content-Type: application/json" \
  -d '{"session_id": "00000000-0000-0000-0000-000000000001", "message": "follow up"}'
```
Expected: Second message routes with preserved context

**Step 3: Commit**

```bash
git add pa-routing-handler/src/pa_routing/main.py
git commit -m "feat: initialize session store with Supabase client"
```

---

### Task 3.3: Update Session Store Key from session_id to identity_id

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

**Step 1: Update route_message to use identity_id as session key**

Change:
```python
# OLD
user_id = request.user_id or str(request.session_id)
session_ctx = session_store.get_or_create(user_id)
```

To:
```python
# NEW: Use identity_id for session state (falls back to session_id)
session_key = identity_id or str(request.session_id)
session_ctx = session_store.get_or_create(session_key)
```

**Step 2: Update complete_thread to persist**

Add after session context update:
```python
# Persist session state (fire-and-forget)
session_store.persist_async(session_id, session_ctx)
```

**Step 3: Run existing tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_routing.py -v
```
Expected: PASS

**Step 4: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: key session state by identity_id"
```

---

## Phase 4: Conversation Integration

### Task 4.1: Add Conversation Lookup to route_message

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`
- Test: `pa-routing-handler/tests/routers/test_routing_conversation.py`

**Step 1: Initialize ConversationService**

Add near top of file with other initializations:
```python
from pa_routing.services.conversation_service import ConversationService

# Initialize conversation service (requires Supabase client from main.py)
_conversation_service = None  # Set during app startup

def init_conversation_service(supabase_client):
    global _conversation_service
    _conversation_service = ConversationService(
        letta_client=_letta_client._client,
        supabase_client=supabase_client,
        identity_service=_identity_service
    )
```

**Step 2: Add conversation lookup after routing**

Add after agent selection:
```python
# Look up or create conversation for identity + agent
conversation_id = None
if identity_id and _conversation_service:
    try:
        conv_result = await _conversation_service.get_or_create_conversation(
            user_id=identity_id,
            user_source=request.platform or "web",
            agent_id=result.agent_id
        )
        conversation_id = conv_result.get("conversation_id")
        logger.info("conversation_resolved",
                   identity_id=identity_id,
                   conversation_id=conversation_id)
    except Exception as e:
        logger.warning("conversation_lookup_failed", error=str(e))
```

**Step 2: Include conversation_id in response**

Update return statement:
```python
return RouteResponse(
    # ... existing fields ...
    identity_id=identity_id,
    conversation_id=conversation_id,
)
```

**Step 3: Test manually**

Run:
```bash
curl -X POST http://localhost:5201/v1/route -H "Content-Type: application/json" \
  -d '{"session_id": "00000000-0000-0000-0000-000000000001", "message": "test"}'
```
Expected: Response includes `conversation_id` field

**Step 4: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git commit -m "feat: add conversation lookup to route_message"
```

---

### Task 4.2: Update Web UI to Pass conversation_id to Letta

**Files:**
- Modify: `pa-web-ui/app.py`

**Step 1: Extract conversation_id from route response**

In the `/stream` endpoint, after routing:
```python
# Get conversation_id from routing response
conversation_id = route_response.get("conversation_id")
```

**Step 2: Pass conversation_id to Letta send_message**

Update Letta API call:
```python
response = letta_client.send_message(
    agent_id=agent_id,
    message=message,
    conversation_id=conversation_id  # NEW
)
```

**Step 3: Test manually**

Open web UI, send message, verify in Letta logs that conversation_id is received.

**Step 4: Commit**

```bash
git add pa-web-ui/app.py
git commit -m "feat: pass conversation_id to Letta in web UI"
```

---

## Phase 5: Verification

### Task 5.1: Integration Tests

**Files:**
- Create: `pa-routing-handler/tests/integration/test_conversations_integration.py`

**Step 1: Write integration tests**

```python
"""Integration tests for routing handler conversations."""

import pytest
import httpx


class TestConversationsIntegration:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url="http://localhost:5201")

    def test_route_returns_identity_id(self, client):
        """Route response includes identity_id."""
        response = client.post("/route", json={
            "session_id": "00000000-0000-0000-0000-000000000001",
            "message": "test message"
        })
        assert response.status_code == 200
        data = response.json()
        assert "identity_id" in data

    def test_route_returns_conversation_id(self, client):
        """Route response includes conversation_id."""
        response = client.post("/route", json={
            "session_id": "00000000-0000-0000-0000-000000000001",
            "message": "test message"
        })
        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data

    def test_session_persists_across_restart(self, client):
        """Session context survives handler restart."""
        # This test requires manual restart verification
        pass
```

**Step 2: Run integration tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/integration/ -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add pa-routing-handler/tests/integration/
git commit -m "test: add conversations integration tests"
```

---

### Task 5.2: Final Verification and Cleanup

**Manual Verification Checklist:**

1. [ ] **Persistence Test**: Restart handler → session context restored
2. [ ] **Identity Resolution**: Logs show `identity_id` resolved for requests
3. [ ] **Conversation Resolution**: Logs show `conversation_id` returned
4. [ ] **Multi-modality Ready**: Adding platform/platform_id resolves identity
5. [ ] **Latency Check**: Warm cache routing still ~2ms
6. [ ] **Web UI**: Conversation history persists across browser refreshes

**Cleanup:**

- Remove any debug logging
- Update CLAUDE.md if needed
- Create release notes

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| **Persistence** | Restart handler → session context restored from Supabase |
| **Identity resolution** | Handler logs show `identity_id` resolved for requests |
| **Conversations** | Letta agent receives `conversation_id`, maintains history |
| **Multi-modality ready** | Adding `platform`/`platform_id` resolves correct identity |
| **No regression** | Existing routing behavior unchanged, latency ~2ms warm cache |

---

## Execution Order

**Phase 1 (Parallel - 4 agents):**
- Task 1.1: Create Session State Table
- Task 1.2: Add Identity Fields to RouteRequest
- Task 1.3: Add Identity/Conversation Fields to RouteResponse
- Task 1.4: Add default_identity_id to Settings

**Phase 2 (Parallel - 2 agents):**
- Task 2.1: Create resolve_identity Function
- Task 2.2: Integrate Identity Resolution into route_message

**Code Review Checkpoint**

**Phase 3 (Sequential):**
- Task 3.1: Create PersistentSessionStore
- Task 3.2: Initialize Session Store with Supabase
- Task 3.3: Update Session Store Key

**Phase 4 (Parallel - 2 agents):**
- Task 4.1: Add Conversation Lookup to route_message
- Task 4.2: Update Web UI to Pass conversation_id

**Phase 5 (Sequential):**
- Task 5.1: Integration Tests
- Task 5.2: Final Verification

---

## Plan Comparison Notes

This plan was created by comparing two approaches:

1. **Task-based Plan** (this document) - Created from design document
2. **Alternate Plan** (`2026-01-26-routing-handler-conversations-impl.md`) - Step-by-step implementation

### Integrated from Alternate Plan:
- SQL trigger for automatic `updated_at` maintenance
- Step to look up default identity ID from Letta API
- Correct API endpoint path (`/v1/route` not `/route`)
- Specific test file names (e.g., `test_routing_identity.py`)

### Retained from Task-based Plan:
- Hierarchical task numbering (1.1, 1.2 for better phase grouping)
- Explicit agent parallelization opportunities
- Code review checkpoint after Phase 2
- Async `persist_async()` for non-blocking persistence
- Clear execution order with parallel/sequential annotations

### Key Differences:
| Aspect | Task Plan | Alternate | Decision |
|--------|-----------|-----------|----------|
| Task structure | 5 phases, 12 tasks | 5 phases, 13 tasks | Merged structure |
| Parallelization | Documented | Not mentioned | Keep explicit |
| SQL trigger | Missing | Included | Added |
| persist() | Async | Sync | Keep async |
| Test files | Generic | Specific names | Added specifics |
