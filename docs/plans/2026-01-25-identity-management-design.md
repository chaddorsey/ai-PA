# Identity Management Design

> **Date:** 2026-01-25
> **Status:** Design Complete
> **Builds on:** Letta Conversations Scheduler Pilot

## Overview

This design establishes a unified identity management system using Letta Identities as the central user profile store. It enables:

1. **Staff recognition** - When a known staff member messages Chadbot, the system recognizes them and has full context
2. **Colloquial lookup** - Agents can resolve "What's Dan's schedule?" without secondary lookups
3. **Cross-platform coherence** - Same user across Slack/email/Jira shares one identity and memory
4. **External system integration** - Any system with a user identifier can query the identity store for personalization

## Architecture

### Three-Layer Data Model

| Layer | Storage | Scope | Content |
|-------|---------|-------|---------|
| **Identity** | Letta Identities | Global (all agents) | Credential/reference data: email, slack_id, calendar_id, colloquial_name |
| **User Facts** | Shared memory blocks | Global (all agents) | General knowledge: relationships, interests, context |
| **Preferences** | Agent-specific blocks | Per-agent | Learned behaviors: scheduling preferences, communication patterns |

**Why this separation:**
- **Identities** are for technical linking ("message Dan on Slack" → needs `slack_id`)
- **User Facts** are for understanding ("Dan's wife works at X" → context for scheduling)
- **Preferences** are agent-specific learning ("Dan prefers 30-min meetings" → scheduler only)

### Unified Identity Flow

Staff identities are the primary way to recognize who is messaging the bot:

```
Scott (slack_id: U02V82YB9) sends DM to Chadbot
    ↓
ConversationService: lookup identity by slack_id
    ↓
Found: Scott Cytacki identity
    → email, calendar_id, colloquial_name already known
    ↓
Get/create conversation linked to Scott's identity
    ↓
Agent context: "Scott is messaging me. I know his calendar, preferences, etc."
```

### Identity Types

| Type | How Identified | Created By |
|------|----------------|------------|
| **Staff** | Pre-populated with all platform IDs | Admin script (migration) |
| **Family** | Pre-populated (same as staff) | Admin script (migration) |
| **External** | Unknown platform ID, no match found | ConversationService (on first message) |

## Identity-Linked Memory

The identity ID is the universal key for all user-related data:

```
Scott's Identity (id: identity-abc123)
├── properties: {email, slack_id, calendar_id, colloquial_name}
├── linked blocks:
│   ├── preferences_identity-abc123  (agent-specific: scheduling prefs)
│   ├── facts_identity-abc123        (shared: relationships, context)
│   └── calendar_identity-abc123     (agent-specific: availability patterns)
```

**Cross-platform resolution:**
```
Scott via Slack (U02V82YB9)  ─┐
Scott via email              ─┼─→ identity-abc123 → same blocks
Scott via Jira               ─┘
```

### Block Naming Convention

| Old (platform-specific) | New (identity-based) |
|-------------------------|----------------------|
| `preferences_U02V82YB9` | `preferences_identity-abc123` |
| `preferences_scytacki@concord.org` | (same identity, same block) |

## Identity Properties Schema

```python
{
    "id": "identity-abc123",                    # Letta-generated, stable
    "identifier_key": "scytacki@concord.org",   # Canonical (email)
    "name": "Scott Cytacki",
    "identity_type": "user",
    "properties": {
        "colloquial_name": "Scott",
        "email": "scytacki@concord.org",
        "slack_id": "U02V82YB9",
        "calendar_id": "scytacki@concord.org",
        "working_hours": null,                  # Optional, e.g., "11:30AM-7:30PM"
        "working_week": null,                   # Optional, e.g., "Monday-Thursday"
        "imessage": null                        # Family only
    }
}
```

## Colloquial Name Resolution

**Approach:** Curated defaults with learned refinement

- Each identity has an explicit `colloquial_name` field (e.g., "Dan" for Dan Damelin, "Danielle" for Danielle Kehoe)
- Agent uses context to disambiguate when needed
- Agent can learn patterns over time and flag identity updates

**Resolution flow:**
```
User: "What's Dan's schedule?"
    ↓
Agent: lookup_staff("Dan")
    ↓
IdentityService: find_by_colloquial_name("Dan")
    ↓
Returns: Dan Damelin identity (colloquial_name = "Dan")
    ↓
Agent: check_calendar(identity.properties.calendar_id)
```

## Cross-System Integration

The identity becomes a universal profile that any integrated system can query:

```
Any system with a user identifier
    ↓
Query: find_identity_by_property(field, value)
    ↓
Get identity + linked blocks
    ↓
Personalized, context-aware interaction
```

**Example: Smart Office**
```
Leslie badges in (email from Google Workspace: lbondaryk@concord.org)
    ↓
Lookup: identity with email = "lbondaryk@concord.org"
    ↓
Found: Leslie Bondaryk
    properties.working_week = "Monday-Thursday"
    ↓
Check: It's Thursday (her last workday this week)
    ↓
Query: preferences_identity-leslie → "prefers quiet focused work"
    ↓
Smart Office: "Good morning Leslie! Huddle Room #2 is free all day."
```

**Integration examples:**

| System | Identifier Used | Personalization |
|--------|-----------------|-----------------|
| Slackbot | slack_id | Knows preferences, calendar, context |
| Smart Office | email (Google auth) | Knows working days, workspace preferences |
| Email Agent | email | Knows communication style, response patterns |
| Jira Integration | email | Knows workload, project context |
| Calendar Assistant | calendar_id | Knows availability patterns, meeting preferences |

## Implementation Components

### 1. IdentityService (new)

```python
class IdentityService:
    def find_by_property(self, field: str, value: str) -> Optional[Identity]
    def find_by_colloquial_name(self, name: str) -> Optional[Identity]
    def list_all_staff(self) -> List[Identity]
    def create_external_user(self, platform: str, platform_id: str) -> Identity
```

### 2. Updated ConversationService (modify existing)

```python
async def get_or_create_conversation(self, user_id, user_source, agent_id, ...):
    # Try to find existing identity by platform ID
    identity = self.identity_service.find_by_property(
        f"{user_source}_id",  # e.g., "slack_id"
        user_id
    )

    if identity:
        # Known user - use their identity
        identity_id = identity.id
    else:
        # Unknown user - create external identity
        identity = self.identity_service.create_external_user(user_source, user_id)
        identity_id = identity.id

    # Rest of conversation creation using identity_id for block naming
```

### 3. Staff Directory Migration Script (one-time)

- Reads current memory block data (Concord Staff Info, Family and Personal Info)
- Creates Letta identities for each person
- Populates properties (email, slack_id, calendar_id, colloquial_name, working_hours, etc.)

### 4. Agent Lookup Tool

```python
def lookup_staff(name: str) -> dict:
    """Look up staff member by colloquial name or email."""
    # Agent calls this when user says "What's Dan's schedule?"
    identity = identity_service.find_by_colloquial_name(name)
    return identity.properties if identity else None
```

## Implementation Phases

### Phase 1: Foundation
1. Create `IdentityService` with Letta API wrapper
2. Run staff directory migration script (memory block → identities)
3. Update `ConversationService` to use identity lookup
4. **Test:** Staff member messages Slackbot → recognized by name

### Phase 2: Agent Integration
1. Create `lookup_staff` tool for agents
2. Attach to scheduler agent (and others)
3. Update agent system prompts to use the tool
4. **Test:** "What's Dan's schedule?" → resolves correctly

### Phase 3: Block Migration
1. Rename existing blocks from `preferences_{slack_id}` to `preferences_{identity_id}`
2. Update `find_user_blocks` / `create_user_memory_block` tools
3. **Test:** Cross-platform memory coherence

### Phase 4: External Integrations (future)
- Smart office integration
- Email agent identity resolution
- Jira/other platform linking

## Current Staff Directory Data

To be migrated to identities:

**Concord Staff (~24 people):**
- Required fields: name, email, calendar_info
- Common fields: slack_id (1 missing)
- Optional fields: working_hours, working_week

**Family (~4 people):**
- Same as staff plus: imessage

**Shared Calendars (~10):**
- Not identities - remain as reference data in memory block or separate config

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Identity scope | Shared globally | All agents need access to staff data |
| Canonical identifier | Email | Universal across platforms |
| Colloquial resolution | Curated + learned | Explicit `colloquial_name` field with agent learning |
| Block naming | Identity ID | Enables cross-platform memory coherence |
| External users | Create minimal identity | Still get conversation isolation |

## Relationship to Conversation Isolation

This design builds on the Letta Conversations Scheduler Pilot:

- **Conversation isolation** provides per-user message history and context
- **Identity management** provides recognition of WHO is in that conversation
- Together: "Scott is messaging me in his conversation, and I know he prefers morning meetings"

The `ConversationService` is updated to:
1. First look up identity by platform ID (slack_id, email, etc.)
2. Use existing staff identity if found
3. Create external identity if not found
4. Use identity ID for block naming (not platform ID)

## Success Criteria

1. **Recognition:** Staff member messages Slackbot → agent knows who they are
2. **Lookup:** "What's Dan's schedule?" → resolves without secondary lookup
3. **Cross-platform:** Same user via Slack and email → same identity and blocks
4. **External integration:** System with user email → can query identity for personalization
