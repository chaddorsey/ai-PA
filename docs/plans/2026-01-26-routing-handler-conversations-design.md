# Routing Handler Conversations Integration Design

**Date:** 2026-01-26
**Status:** Draft - Pending comparison with alternate approach

## Problem Statement

The pa-routing-handler currently uses ephemeral in-memory session storage that is lost on restart and has no identity resolution. This limits:
- Persistence of routing context across restarts
- Multi-modality support (Telegram, email, SMS)
- Agent conversation history with the user

## Goals

1. Add persistence to session/routing context (survives restarts)
2. Enable identity resolution for future multi-modality support
3. Integrate Letta Conversations for per-agent persistent history
4. Maintain fast routing performance (~2ms)

## Design Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Identity resolution | Trust platform identity via IdentityService; default identity for web UI | Single-user system with controlled platform access |
| Conversation scope | Per-agent Letta Conversations | Keeps context focused; matches Letta's natural model |
| Session store | Hybrid persistence (in-memory + Supabase backup) | Fast routing (~2ms) with persistence on restart |
| Integration point | Handler does identity + conversation lookup | Keeps adapters thin; centralizes logic |
| State keying | Session state keyed by `identity_id`, not `session_id` | Enables cross-platform context sharing |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Web UI    │     │  Telegram   │     │   Email     │
│             │     │    Bot      │     │   Gateway   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ platform=web      │ platform=telegram │ platform=email
       │ platform_id=null  │ platform_id=123   │ platform_id=me@x.com
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                 ┌─────────────────────┐
                 │   Routing Handler   │
                 │   • Identity resolve│◄──── IdentityService
                 │   • Route message   │
                 │   • Session context │◄──── SessionStore (memory + Supabase)
                 │   • Conversation    │◄──── ConversationService
                 │     lookup/create   │
                 └──────────┬──────────┘
                           │
                           │ {agent_id, identity_id, conversation_id}
                           ▼
                 ┌─────────────────────┐
                 │       Letta         │
                 │   (with convo_id)   │
                 └─────────────────────┘
```

### Data Flow

1. Adapter (Web UI, Telegram, etc.) sends message to handler
2. Handler resolves identity:
   - If `platform` + `platform_id` provided → resolve via IdentityService
   - If not → use `DEFAULT_IDENTITY_ID` (single-user default)
3. Handler routes message using tiered agent selector
4. Handler looks up/creates conversation for identity + selected agent
5. Handler returns `{agent_id, identity_id, conversation_id, ...}`
6. Adapter sends message to Letta with `conversation_id`
7. Agent has persistent conversation history

## API Changes

### Route Request (updated)

```python
class RouteRequest(BaseModel):
    session_id: UUID
    message: str
    agent_id: Optional[str] = None      # Explicit agent override

    # NEW: Optional identity context (for multi-modality)
    platform: Optional[str] = None      # "slack", "telegram", "web"
    platform_id: Optional[str] = None   # Platform-specific user ID
```

### Route Response (updated)

```python
class RouteResponse(BaseModel):
    agent_id: str
    agent_name: str
    routing_method: str
    routing_reason: str
    confidence: float
    processing_time_ms: int
    request_id: Optional[str] = None
    context_injection: Optional[str] = None
    briefing_injection: Optional[str] = None

    # NEW: Identity and conversation resolution
    identity_id: Optional[str] = None       # Resolved Letta identity
    conversation_id: Optional[str] = None   # For caller to use with Letta
```

### Identity Resolution Logic

```python
# In route_message():
if request.platform and request.platform_id:
    # Multi-modality: resolve via IdentityService
    identity = identity_service.find_by_property(
        f"{request.platform}_id",
        request.platform_id
    )
    identity_id = identity.id if identity else None
else:
    # Single-user default (web UI, etc.)
    identity_id = settings.default_identity_id
```

## Session Store Persistence

### New Supabase Table

```sql
CREATE TABLE pa_web.session_state (
    identity_id TEXT PRIMARY KEY,
    last_responding_agent_id TEXT,
    last_responding_agent_name TEXT,
    last_response_time TIMESTAMPTZ,
    context_entries JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_session_state_updated ON pa_web.session_state(updated_at);
```

### Updated SessionStore Class

```python
class SessionStore:
    def __init__(self, supabase_client):
        self._cache: dict[str, SessionContext] = {}
        self._supabase = supabase_client

    def get_or_create(self, identity_id: str) -> SessionContext:
        # Check cache first (fast path, ~0ms)
        if identity_id in self._cache:
            return self._cache[identity_id]

        # Cache miss: hydrate from Supabase (~20ms, once per restart)
        ctx = self._load_from_db(identity_id)
        if ctx is None:
            ctx = SessionContext()

        self._cache[identity_id] = ctx
        return ctx

    def _persist(self, identity_id: str, ctx: SessionContext) -> None:
        # Async upsert to Supabase (fire-and-forget, non-blocking)
        ...
```

### Latency Profile

| Scenario | Latency |
|----------|---------|
| Warm cache (typical) | ~2ms |
| Cold start (after restart) | ~22ms |
| Conversation creation (first time per agent) | +~100ms |

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

## Rollout Plan

### Phase 1: Add Infrastructure (no behavior change)
- Create `pa_web.session_state` table
- Add `identity_id` and `conversation_id` to RouteResponse (optional fields)
- Handler still works exactly as before

### Phase 2: Enable Identity Resolution
- Add `DEFAULT_IDENTITY_ID` to handler settings
- Handler resolves identity, returns `identity_id` in response
- Web UI ignores it (no change yet)

### Phase 3: Enable Session Persistence
- Update SessionStore to use `identity_id` as key
- Add Supabase read/write
- Existing behavior preserved, now persists

### Phase 4: Enable Conversations
- Handler does conversation lookup, returns `conversation_id`
- Update Web UI to pass `conversation_id` to Letta
- Agents now have persistent conversation context

Each phase is independently reversible.

## Success Criteria

1. **Persistence**: Restart handler → session context restored from Supabase
2. **Identity resolution**: Handler logs show `identity_id` resolved for requests
3. **Conversations**: Letta agent receives `conversation_id`, maintains history across sessions
4. **Multi-modality ready**: Adding `platform`/`platform_id` to request resolves correct identity
5. **No regression**: Existing routing behavior unchanged, latency remains ~2ms for warm cache

## Future Considerations

- If adapter complexity grows, extract identity + conversation logic into shared library
- Consider caching identity lookups if IdentityService calls become a bottleneck
- Multi-user support would require authentication layer (out of scope for now)

## Appendix: Rejected Alternatives

### Option B: Migrate Session Store to Supabase Queries
- Replace in-memory session_store entirely with Supabase queries
- Simpler (single source of truth) but ~30-50ms latency per routing decision
- Rejected: Performance penalty not justified for single-instance deployment

### Option A (Q3): Keep Both Layers Separate
- Session store in-memory without persistence
- Letta Conversations for agent history only
- Rejected: Doesn't solve restart persistence problem
