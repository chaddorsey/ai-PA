# PBI-31: Contextual Routing and Threaded Conversations

## Problem Statement

The current PA Web UI has two limitations that reduce usability in multi-agent conversations:

1. **Contextual follow-ups get misrouted**: Brief responses like "You got the wrong day" or "Yes, do that" lack keywords and get routed to the wrong agent, even when they clearly relate to the previous exchange.

2. **No support for concurrent conversations**: Users cannot send a second request while waiting for the first response, and when multiple responses arrive, there's no visual threading to associate responses with their originating requests.

## Goals

1. Implement response-aware routing that considers the conversational context
2. Enable concurrent requests with proper visual threading
3. Allow easy continuation of conversations with specific agents

## User Stories

### Contextual Routing
- As a user, when I send a brief follow-up like "try again" after a calendar query, I want it routed to the calendar agent, not the default agent.
- As a user, when an agent asks me a question and I reply briefly, I want my reply to go to that same agent.

### Concurrent Conversations
- As a user, I want to send a task query while waiting for a calendar response.
- As a user, I want to see which response belongs to which request when multiple are in flight.
- As a user, I want to click on a response to continue that specific conversation thread.

## Design

### Contextual Routing Logic

Track conversation pairs (request → response → follow-up) rather than simple timeouts:

```
Message Flow:
  User → Agent A (request 1)
  Agent A → User (response 1)
  User → ??? (follow-up)  ← Should route to Agent A if contextual

Heuristics for "contextual follow-up":
  - Message is short (< 20 words)
  - No strong keyword match (confidence < 0.7)
  - Previous response was from a specific agent
  - Message appears conversational (starts with yes/no, pronouns, etc.)
```

### Threaded UI Design

```
┌─ Request 1 ─────────────────────────────────────┐
│ 👤 What's on my calendar today?                 │
│                                                 │
│ 📅 Calendar Agent                               │
│ Here's your schedule for January 9...           │
│                                          [Reply]│
└─────────────────────────────────────────────────┘

┌─ Request 2 ─────────────────────────────────────┐
│ 👤 Check my OmniFocus inbox                     │
│                                                 │
│ ⏳ Task Agent: Searching OmniFocus...           │
└─────────────────────────────────────────────────┘

┌─ Input ─────────────────────────────────────────┐
│ Type a message...                        [Send] │
└─────────────────────────────────────────────────┘
```

- Each request/response pair lives in a "card"
- Cards stack with newest at bottom
- In-progress cards show status indicator
- Clicking [Reply] sends next message to that agent
- New messages without [Reply] context use normal routing

### Data Model Changes

```python
# Add to session context
class ConversationThread:
    request_id: str
    agent_id: str
    agent_name: str
    started_at: datetime
    last_activity: datetime
    status: "pending" | "complete"
```

```javascript
// Frontend message structure
{
    request_id: "uuid",
    user_message: "...",
    agent_id: "...",
    agent_name: "...",
    response: "...",
    status: "pending" | "streaming" | "complete",
    tool_calls: [...]
}
```

## Tasks

### 31-1: Add conversation thread tracking to session context
- Track request_id, agent_id, status per message pair
- Store in session_store with conversation history
- Expose via routing handler API

### 31-2: Implement contextual routing tier
- Add Tier 3.5: "Recent context affinity"
- Detect conversational follow-ups
- Route to last responding agent when appropriate
- Add confidence scoring for context matches

### 31-3: Add request_id to frontend and SSE stream
- Generate request_id for each user message
- Include request_id in routing request
- Return request_id in SSE events
- Track in-flight requests in frontend state

### 31-4: Implement threaded card UI
- Replace flat message list with threaded cards
- Show request + response grouped together
- Support multiple concurrent cards
- Add [Reply] button to continue thread

### 31-5: Handle concurrent requests
- Allow sending while response pending
- Visual indication of multiple in-flight requests
- Proper ordering as responses arrive
- Handle edge cases (errors, timeouts)

### 31-6: Add "reply to agent" routing mode
- [Reply] button sets explicit agent routing
- Visual indicator when in "reply" mode
- Clear reply context on new topic

## Conditions of Satisfaction

1. Brief follow-ups route correctly to the previous agent 80%+ of the time
2. Users can send concurrent requests without blocking
3. Responses are visually threaded under their originating requests
4. Users can explicitly continue a conversation with a specific agent
5. No regression in keyword-based routing accuracy

## Dependencies

- PBI-30 (PA Web Interface) - Complete
