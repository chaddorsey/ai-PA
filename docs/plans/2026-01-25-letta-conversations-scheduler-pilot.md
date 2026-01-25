# Letta Conversations: Scheduler Agent Pilot Design

**Date:** 2026-01-25
**Status:** Design Complete
**Letta Version:** 0.16.3+ (Conversations API required)

## Overview

This document describes the architecture for implementing Letta's Conversations API with the Scheduler Agent as a pilot. The goal is to enable multiple users to interact with a single scheduling agent while maintaining isolated conversation contexts and per-user learned preferences.

### Key Insight

Letta Conversations isolate **context** (message history), not **memory** (blocks). All conversations share the agent's memory blocks. User data isolation is achieved through:
1. Naming conventions for block discovery
2. Tool-based permission enforcement
3. `CONVERSATION_USER_ID` tool variable

## Architecture

### Problem Statement

| Scenario | Description | Conversations Help? |
|----------|-------------|---------------------|
| Multi-agent routing | One user, multiple specialized agents | No - handled by pa-routing-handler |
| **Multi-user access** | **Multiple users, one specialized agent** | **Yes - this pilot** |

The scheduler agent is accessed by multiple users who each need:
- Isolated conversation context
- Personalized learned preferences
- Access to shared scheduling policies

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Scheduler Agent                                   │
│                (agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218)             │
├─────────────────────────────────────────────────────────────────────────┤
│  SHARED MEMORY BLOCKS                                                    │
│  • company_policies                                                     │
│  • scheduling_best_practices                                            │
│  • agent_info                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  USER-SPECIFIC MEMORY BLOCKS (all attached, access via tools)           │
│  • preferences_user_a, preferences_user_a_meeting_duration, ...         │
│  • preferences_user_b, preferences_user_b_video_call_preference, ...    │
│  • calendar_user_a, calendar_user_b, ...                                │
│  • meeting_scheduler_preferences_user_a_deep_work (agent-specific)      │
├─────────────────────────────────────────────────────────────────────────┤
│  TOOLS                                                                   │
│  • find_user_blocks(user_id, scope) - discovery with permission check   │
│  • create_user_memory_block(...) - emergent block creation              │
│  • orchestrate_scheduling(...) - existing scheduling tool               │
├─────────────────────────────────────────────────────────────────────────┤
│  CONVERSATIONS (isolated context per user)                              │
│  • Conversation: User A - Slack (CONVERSATION_USER_ID=user_a)           │
│  • Conversation: User B - Slack (CONVERSATION_USER_ID=user_b)           │
│  • Conversation: User C - Email (CONVERSATION_USER_ID=user_c)           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Memory Block Naming Conventions

### Pattern Types

| Type | Pattern | Example | Scope |
|------|---------|---------|-------|
| Cross-agent | `{category}_{user_id}` | `preferences_user_a` | All agents |
| Cross-agent + purpose | `{category}_{user_id}_{purpose}` | `preferences_user_a_meeting_duration` | All agents |
| Agent-specific | `{agent}_{category}_{user_id}` | `meeting_scheduler_preferences_user_a` | This agent only |
| Agent-specific + purpose | `{agent}_{category}_{user_id}_{purpose}` | `meeting_scheduler_preferences_user_a_deep_work` | This agent only |
| Shared (no user) | `{category}` | `company_policies` | All users |

### Discovery Logic

Blocks are discovered via naming convention pattern matching:
- Cross-agent blocks: Available to all agents for the user
- Agent-specific blocks: Only relevant to this agent's domain

## Tools

### find_user_blocks

```python
def find_user_blocks(user_id: str, scope: str = "all") -> list:
    """
    Discover all memory blocks for a user via naming convention.

    Args:
        user_id: The user identifier (e.g., "user_a", Slack ID)
        scope: "all", "cross_agent", or "agent_specific"

    Returns:
        List of block labels matching the user and scope.
        Empty list if permission denied.
    """
    import os
    import re

    # Permission check
    current_user = os.getenv("CONVERSATION_USER_ID")
    if not current_user:
        return {"error": "No CONVERSATION_USER_ID set"}
    if current_user != user_id:
        return []  # Cannot discover other users' blocks

    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": "Invalid user_id format"}

    all_blocks = get_all_memory_blocks()

    # Match blocks containing user_id
    user_blocks = [
        block for block in all_blocks
        if f"_{user_id}" in block.label or f"_{user_id}_" in block.label
    ]

    # Get agent name from tool variable
    agent_name = os.getenv("AGENT_NAME", "meeting_scheduler")
    agent_prefix = f"{agent_name}_"

    if scope == "cross_agent":
        return [b for b in user_blocks if not b.label.startswith(agent_prefix)]
    elif scope == "agent_specific":
        return [b for b in user_blocks if b.label.startswith(agent_prefix)]
    return user_blocks
```

### create_user_memory_block

```python
def create_user_memory_block(
    user_id: str,
    category: str,
    value: str,
    purpose: str = None,
    agent_specific: bool = False
) -> dict:
    """
    Create a new memory block for emergent user preferences.

    Args:
        user_id: The user identifier
        category: Block category (e.g., "preferences", "calendar")
        value: Initial block content
        purpose: Optional specific purpose (e.g., "meeting_duration")
        agent_specific: If True, prefix with agent name

    Returns:
        dict with block_id and label, or error
    """
    import os
    import re
    from letta_client import Letta

    # Initialize client
    client = Letta(api_key=os.getenv("LETTA_API_KEY"))

    # Permission check
    current_user = os.getenv("CONVERSATION_USER_ID")
    if not current_user:
        return {"error": "No CONVERSATION_USER_ID set"}
    if current_user != user_id:
        return {"error": f"Cannot create blocks for {user_id}"}

    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": "Invalid user_id format"}
    if not re.match(r'^[a-zA-Z0-9_-]+$', category):
        return {"error": "Invalid category format"}
    if purpose and not re.match(r'^[a-zA-Z0-9_-]+$', purpose):
        return {"error": "Invalid purpose format"}

    # Check value length
    if len(value) > 2000:
        return {"error": "Block value too long (max 2000 characters)"}

    # Get agent name from tool variable
    agent_name = os.getenv("AGENT_NAME", "meeting_scheduler")

    # Build label
    if agent_specific:
        label = f"{agent_name}_{category}_{user_id}"
    else:
        label = f"{category}_{user_id}"

    if purpose:
        label += f"_{purpose}"

    # Sanitize label
    label = label.lower().replace(" ", "_")

    # Check label length
    if len(label) > 200:
        return {"error": "Block label too long (max 200 characters)"}

    try:
        # Create block via Letta API
        block = client.agents.blocks.create(
            agent_id=os.getenv("LETTA_AGENT_ID"),
            block={
                "label": label,
                "value": value,
                "description": f"{category} for {user_id}" + (f": {purpose}" if purpose else ""),
                "limit": 2000
            }
        )

        # Invalidate block cache
        invalidate_block_cache()

        return {"block_id": block.id, "label": label}

    except Exception as e:
        return {"error": str(e)}
```

## Permission Enforcement Flow

```
When agent receives a message in User A's conversation:

1. Agent has ALL blocks attached (including all users)

2. Tool variable provides: CONVERSATION_USER_ID = "user_a"

3. Agent calls: find_user_blocks(user_id="user_a", scope="all")

4. find_user_blocks checks permissions:
   current_user = os.getenv("CONVERSATION_USER_ID")  # "user_a"
   if current_user != user_id:  # "user_a" != "user_a" → False
       return []

5. find_user_blocks returns only User A's blocks:
   - preferences_user_a
   - preferences_user_a_meeting_duration
   - preferences_user_a_video_call_preference
   - meeting_scheduler_preferences_user_a_deep_work
   - calendar_user_a

6. Agent works only with these blocks

7. Other users' blocks are attached but never accessed

SECURITY: If User B tries to access User A's blocks:
- CONVERSATION_USER_ID = "user_b"
- find_user_blocks(user_id="user_a", scope="all")
- Permission check: "user_b" != "user_a" → True
- Returns: [] (empty list)
- User B cannot discover User A's blocks exist
```

## User Onboarding Flow

### Handler Creates Initial Resources

```python
def onboard_user(user_id: str, display_name: str, email: str, source: str = "slack"):
    """
    Handler creates initial resources for new user.
    Agent handles everything else autonomously.
    """
    from letta_client import Letta

    client = Letta(api_key=os.getenv("LETTA_API_KEY"))
    scheduler_agent_id = os.getenv("SCHEDULER_AGENT_ID")

    # 1. Create initial preference block (empty)
    pref_block = client.agents.blocks.create(
        agent_id=scheduler_agent_id,
        block={
            "label": f"preferences_{user_id}",
            "value": "No preferences learned yet.",
            "description": f"Scheduling preferences for {user_id}",
            "limit": 2000
        }
    )

    # 2. Create initial calendar block
    cal_block = client.agents.blocks.create(
        agent_id=scheduler_agent_id,
        block={
            "label": f"calendar_{user_id}",
            "value": "Calendar integration pending configuration.",
            "description": f"Calendar integration for {user_id}",
            "limit": 1000
        }
    )

    # 3. Create identity (metadata)
    identity = client.identities.create(
        identifier_key=user_id,
        name=display_name,
        identity_type="user",
        properties={"email": email, "source": source}
    )

    # 4. Create conversation with user context
    conversation = client.conversations.create(
        agent_id=scheduler_agent_id,
        label=f"{user_id} - {source.capitalize()}",
        tool_variables={
            "CONVERSATION_USER_ID": user_id,
            "AGENT_NAME": "meeting_scheduler",
            "LETTA_AGENT_ID": scheduler_agent_id
        }
    )

    return {
        "user_id": user_id,
        "conversation_id": conversation.id,
        "identity_id": identity.id,
        "blocks": [pref_block.id, cal_block.id]
    }
```

### Conversation Mapping Table (Supabase)

```sql
CREATE TABLE user_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,              -- Slack user ID, email, etc.
    user_source TEXT NOT NULL,          -- 'slack', 'email', 'web'
    agent_id TEXT NOT NULL,             -- Letta agent ID
    conversation_id TEXT NOT NULL,      -- Letta conversation ID
    identity_id TEXT,                   -- Letta identity ID (optional)
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(user_id, user_source, agent_id)
);

CREATE INDEX idx_user_lookup ON user_conversations(user_id, agent_id);
```

## Agent Autonomous Learning

### Block Creation Over Time

```
Interaction 1:   User says "I prefer 30 minute meetings"
                 → Agent creates: preferences_user_a_meeting_duration

Interaction 15:  User says "I'd rather do video calls than phone"
                 → Agent creates: preferences_user_a_video_call_preference

Interaction 30:  User mentions "I'm usually slammed around the holidays"
                 → Agent creates: preferences_user_a_holiday_schedule

Interaction 50:  Agent notices user blocks mornings for deep work
                 → Agent creates: meeting_scheduler_preferences_user_a_deep_work
                   (agent-specific, not shared with other agents)
```

### Cross-Agent Learning

```
Scheduler Agent learns: "User A prefers video calls"
→ Creates: preferences_user_a_video_call_preference (cross-agent)

Email Agent later accesses same block:
→ find_user_blocks(user_id="user_a", scope="cross_agent")
→ Returns: preferences_user_a_video_call_preference
→ Email Agent suggests video meeting link in calendar invite
```

## Block Lifecycle Management

### Consolidation

Agent merges similar blocks over time to avoid fragmentation:
- `preferences_user_a_morning` + `preferences_user_a_early_meetings` → consolidated
- Redundant blocks archived to archival memory

### Archival for Inactive Users

```python
def archive_inactive_user_blocks(user_id: str, days_inactive: int = 30):
    """Move blocks to archival memory for inactive users."""
    user_blocks = find_user_blocks(user_id=user_id, scope="all")

    for block in user_blocks:
        # Store in archival memory with tags
        archival_insert(
            content=block.value,
            tags=[f"user:{user_id}", f"block:{block.label}", "archived"]
        )
        # Detach from agent
        client.agents.blocks.detach(agent_id, [block.id])


def restore_user_blocks(user_id: str):
    """Restore blocks from archival when user returns."""
    archived = archival_search(tags=[f"user:{user_id}", "archived"])

    for item in archived:
        # Recreate block
        block = client.blocks.create(
            label=item.tags["block"],
            value=item.content
        )
        client.agents.blocks.attach(agent_id, [block.id])
```

## Performance Optimization

### Block Discovery Caching

```python
def find_user_blocks_cached(user_id: str, scope: str = "all") -> list:
    """Cached version for performance."""
    cache_key = f"blocks_{user_id}_{scope}"

    # Check cache first
    cached = get_from_context_cache(cache_key)
    if cached is not None:
        return cached

    # Cache miss - do full discovery
    blocks = find_user_blocks(user_id=user_id, scope=scope)

    # Cache for this conversation session
    set_context_cache(cache_key, blocks)

    return blocks


def invalidate_block_cache():
    """Called when new block is created."""
    clear_context_cache_prefix("blocks_")
```

## System Prompt Addition

```
You manage user scheduling preferences via memory blocks.

DISCOVERY:
- Call find_user_blocks(user_id=CONVERSATION_USER_ID) to discover all blocks for this user
- Blocks follow naming conventions:
  - Cross-agent: {category}_{user_id}_{purpose}
  - Agent-specific: meeting_scheduler_{category}_{user_id}_{purpose}

READING PREFERENCES:
- Reference discovered blocks directly by label
- Cross-agent blocks contain preferences shared with other agents
- Agent-specific blocks contain your specialized learning

CREATING NEW BLOCKS:
When you learn something new about a user's preferences:
- Use create_user_memory_block() to create a new block
- Use agent_specific=False for preferences other agents should see
- Use agent_specific=True for your specialized domain knowledge
- Check if an existing block already covers this preference before creating

NEVER access blocks that don't match the current CONVERSATION_USER_ID.
```

## Implementation Plan

### Phase 1: Infrastructure
1. Create Supabase table for user→conversation mapping
2. Register `find_user_blocks` and `create_user_memory_block` tools with Letta
3. Update scheduler agent with new tools and system prompt

### Phase 2: Integration
1. Modify Slackbot to route scheduling requests through conversation lookup
2. Implement onboarding flow for new users
3. Add conversation_id to Letta API calls

### Phase 3: Testing
1. Test multi-user isolation (User A cannot see User B's blocks)
2. Test emergent block creation
3. Test cross-agent block sharing
4. Performance testing with block caching

### Phase 4: Rollout
1. Deploy to staging environment
2. Test with 2-3 internal users
3. Monitor and refine
4. Gradual rollout to additional users

## Files to Modify

| File | Change |
|------|--------|
| `letta/register_conversation_tools.py` | New file - register discovery/creation tools |
| `letta/attach_conversation_tools.py` | New file - attach tools to scheduler agent |
| `slackbot/listeners/messages/message_im_hybrid.py` | Add conversation lookup before sending to Letta |
| `pa-routing-handler/src/pa_routing/services/conversation_service.py` | New file - conversation management |
| Supabase migration | Create `user_conversations` table |

## Summary

| Component | Responsibility |
|-----------|----------------|
| **Handler/Slackbot** | Creates initial blocks, sets tool_variables, manages conversations |
| **Naming Convention** | Enables discovery without explicit tracking |
| **Discovery Tools** | Filter blocks by user/scope with permission checks |
| **Caching** | Performance optimization for repeated discovery |
| **Agent** | Creates emergent blocks autonomously, consolidates, archives |
| **Cross-agent Blocks** | Shared preferences (all agents benefit) |
| **Agent-specific Blocks** | Domain knowledge (scheduler-only) |
| **Archival** | Long-term storage for inactive users |

## References

- [Letta Conversations Documentation](https://docs.letta.com/guides/agents/conversations/)
- [Letta Identities Documentation](https://docs.letta.com/guides/agents/identities/)
- Letta Help Forum discussions (2026-01-25)
