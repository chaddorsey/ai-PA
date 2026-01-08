# PBI-31: Contextual Routing and Threaded Conversations - Tasks

## Task Summary

| Task ID | Description | Status |
|---------|-------------|--------|
| 31-1 | Add conversation thread tracking to session context | Done |
| 31-2 | Implement contextual routing tier | Done |
| 31-3 | Add request_id to frontend and SSE stream | Done |
| 31-4 | Implement threaded card UI | Done |
| 31-5 | Handle concurrent requests | Done |
| 31-6 | Add "reply to agent" routing mode | Done |

## Task Details

### 31-1: Add conversation thread tracking to session context
**Status:** Done

**Scope:**
- Track request_id, agent_id, status per message pair
- Store in session_store with conversation history
- Expose via routing handler API

**Implementation:**
- Created `ConversationThread` model (`pa-routing-handler/src/pa_routing/models/conversation_thread.py`)
- Updated `SessionContext` with thread management methods (`session_context.py`)
- Added thread management API endpoints in routing.py:
  - `GET /sessions/{session_id}/threads` - List threads
  - `GET /sessions/{session_id}/threads/{request_id}` - Get specific thread
  - `POST /sessions/{session_id}/threads` - Create thread
  - `POST /sessions/{session_id}/threads/{request_id}/complete` - Mark complete
  - `GET /sessions/{session_id}/context-agent` - Get contextual agent
- Updated `RouteRequest` to include `request_id`
- Updated `RouteResponse` to return `request_id`

---

### 31-2: Implement contextual routing tier
**Status:** Done

**Scope:**
- Add Tier 3.5: "Recent context affinity"
- Detect conversational follow-ups
- Route to last responding agent when appropriate
- Add confidence scoring for context matches

**Implementation:**
- Added `ContextInfo` dataclass for passing context to selector
- Added `_is_conversational_followup()` method with heuristics:
  - Short messages (< 20 words)
  - Conversational starters (yes, no, that, this, etc.)
  - Very short messages (1-5 words) without keywords
- Added Tier 4 (contextual) with confidence 0.75
- Keywords still take precedence over contextual routing
- Updated routing endpoint to pass session context to selector

---

### 31-3: Add request_id to frontend and SSE stream
**Status:** Done

**Scope:**
- Generate request_id for each user message
- Include request_id in routing request
- Return request_id in SSE events
- Track in-flight requests in frontend state

**Implementation:**
- Backend generates `request_id` in routing handler (done in 31-1)
- SSE routing event includes `request_id` (`pa-web-ui/app.py`)
- Backend calls `/complete` after stream finishes to update last_responding_agent
- Frontend `ChatUI` class now tracks:
  - `this.threads` Map storing request_id → thread data
  - `this.currentRequestId` for active request
- Thread data includes: userMessage, agentId, agentName, response, status, createdAt
- Messages store `data-request-id` attribute for future threading UI

---

### 31-4: Implement threaded card UI
**Status:** Done

**Scope:**
- Replace flat message list with threaded cards
- Show request + response grouped together
- Support multiple concurrent cards
- Add [Reply] button to continue thread

**Implementation:**
- Added CSS for `.thread-card` with sections: user message, status, response, footer
- Cards show user message at top with 👤 icon
- Status indicator with animated dots during streaming
- Response section shows agent name and rendered markdown content
- Reply button in footer enables reply mode
- Reply indicator bar shows when replying to specific agent
- Reply mode can be cleared with × button or Escape key
- Thread cards store `data-request-id`, `data-agent-id`, `data-agent-name` attributes

---

### 31-5: Handle concurrent requests
**Status:** Done

**Scope:**
- Allow sending while response pending
- Visual indication of multiple in-flight requests
- Proper ordering as responses arrive
- Handle edge cases (errors, timeouts)

**Implementation:**
- Removed `isStreaming` blocking flag
- Send button no longer disabled during streaming
- Added `inFlightRequests` Set to track active requests
- `sendMessage()` now fires off requests without awaiting
- New `processStreamRequest()` handles async streaming independently
- Thread cards created immediately so ordering is preserved (FIFO)
- Each request streams into its own card regardless of other requests

---

### 31-6: Add "reply to agent" routing mode
**Status:** Done

**Scope:**
- [Reply] button sets explicit agent routing
- Visual indicator when in "reply" mode
- Clear reply context on new topic

**Implementation:**
- Implemented as part of Task 31-4 (threaded card UI)
- Reply button on each thread card calls `setReplyMode(agentId, agentName)`
- Reply indicator bar shows "Replying to [Agent Name]"
- Reply mode passes explicit `agent_id` to routing (overrides dropdown and contextual routing)
- Clear button (×) and Escape key clear reply mode
- Reply mode auto-clears after sending message
