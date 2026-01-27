# Interactive Scheduling Proposals - Design Document

**Date:** 2026-01-27
**Status:** Draft
**Goal:** Transform scheduling orchestrator results into interactive, button-driven experiences while maintaining chat-centric agent continuity.

---

## Problem Statement

Currently, scheduling orchestrator results are:
- **Text-only** - Users must read and parse markdown output
- **One-way** - No direct action from results; users must rephrase selections
- **Error-prone** - Natural language re-specification can introduce mistakes

**Desired state:** Interactive buttons that users can click to schedule meetings directly, with pre-filled confirmation modals and agent-mediated scheduling that maintains conversational continuity.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interaction pattern | Pre-filled confirmation modal | Balance between speed and flexibility |
| Agent involvement | Agent-mediated via synthetic structured message | Maintains chat continuity; agent "owns" the action |
| State storage | In-memory dict with TTL | Lightweight; sufficient for single-user; graceful degradation |
| Conflict presentation | Progressive disclosure | Clean options first; expand to show conflict options |
| Platform approach | Abstraction-first | Platform-agnostic layer enables Slack now, web later |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Scheduling Orchestrator                       │
│  (outputs proposals with structured metadata)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│               Interactive Proposals Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Proposal    │  │   Action     │  │   Agent      │          │
│  │  Formatter   │  │   Handler    │  │   Bridge     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                 │                  │                   │
│         │    Platform-Agnostic Interfaces   │                   │
└─────────┼─────────────────┼──────────────────┼──────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Slack Adapter  │  │   Web Adapter   │  │ Telegram Adapter│
│  (Block Kit)    │  │   (future)      │  │  (future)       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Three core components:**

1. **Proposal Formatter** - Transforms orchestrator output into platform-agnostic `InteractiveProposalSet`
2. **Action Handler** - Processes button clicks, opens modals, generates synthetic agent messages
3. **Agent Bridge** - Injects structured messages into Letta conversation

---

## Data Models

### InteractiveProposal

```python
@dataclass
class InteractiveProposal:
    """A single selectable meeting proposal."""
    id: str                          # Unique ID (e.g., "prop_001")
    index: int                       # Display number (1, 2, 3...)
    label: str                       # Button text: "Mon 2-3pm"

    # Scheduling data (for tool call)
    start_utc: str                   # ISO 8601
    end_utc: str
    participants: List[str]          # Email addresses

    # Pre-fill hints
    suggested_title: Optional[str]   # From conversation context
    suggested_description: Optional[str]

    # Conflict metadata
    category: str                    # "clean" | "move" | "override"
    conflict_summary: Optional[str]  # "moves 'Standup' to 3pm"
    moved_events: List[MovedEventInfo]
```

### InteractiveProposalSet

```python
@dataclass
class InteractiveProposalSet:
    """Complete set of proposals ready for rendering."""
    session_id: str                  # Links back to conversation
    user_id: str

    clean_proposals: List[InteractiveProposal]
    conflict_proposals: List[InteractiveProposal]

    meeting_context: MeetingContext  # Title hints, description, Zoom link
    show_conflicts_expanded: bool    # True if no clean options
    created_at: datetime
```

### MeetingContext

```python
@dataclass
class MeetingContext:
    """Contextual hints extracted from conversation."""
    inferred_title: Optional[str]
    inferred_description: Optional[str]
    zoom_link: Optional[str]
    participant_names: Dict[str, str]  # email -> display name
```

---

## Interaction Flow

```
1. USER CLICKS PROPOSAL BUTTON
   Button value: "sess_abc123:prop_002"
        │
        ▼
2. ACTION HANDLER RECEIVES CLICK
   - Lookup InteractiveProposalSet from in-memory cache
   - Find specific proposal by ID
   - Prepare confirmation modal
        │
        ▼
3. CONFIRMATION MODAL OPENS
   ┌─────────────────────────────────────────────────────────┐
   │ Schedule Meeting                                         │
   │ ─────────────────────────────────────────────────────── │
   │ Title:       [Weekly Sync________________|]              │
   │ When:        Tuesday, Jan 28 · 2:00 - 3:00 PM EST       │
   │ With:        Alice Chen, Bob Smith                      │
   │ Description: [__________________________|]               │
   │ ─────────────────────────────────────────────────────── │
   │                            [Cancel]  [Yes — schedule it!]│
   └─────────────────────────────────────────────────────────┘
        │
        ▼
4. USER SUBMITS FORM
   Action Handler combines user edits with proposal data
        │
        ▼
5. AGENT BRIDGE GENERATES SYNTHETIC MESSAGE

   "User selected Option 2: Tuesday 2-3pm with Alice and Bob.
    They confirmed title 'Weekly Sync'.

    Please schedule this meeting:
    [SCHEDULE_MEETING_DATA]
    {"title": "Weekly Sync", "start": "2026-01-28T14:00:00-05:00", ...}
    [/SCHEDULE_MEETING_DATA]

    Call create_calendar_event and confirm once scheduled."
        │
        ▼
6. LETTA AGENT RESPONDS
   - Extracts structured data
   - Calls create_calendar_event tool
   - Responds conversationally: "Done! I've scheduled..."
```

---

## Slack Adapter (Block Kit)

### Message Structure

**With clean options:**
```
📅 *Best Options*

[1 Mon 2-3pm] [2 Tue 10-11] [3 Wed 3-4pm]

▸ Show more options (requires changes)...
```

**Conflict options (expanded or if no clean options):**
```
⚠️ *Options that require changes*

[4 Thu 11-12 ⚡ moves "Standup" → 12pm]
[5 Fri 2-3pm ⚡ overrides "Focus Time"]
```

### Button Payload

```json
{
  "action_id": "schedule_proposal_select",
  "value": "sess_abc123:prop_002"
}
```

### Modal Structure

```json
{
  "type": "modal",
  "title": {"type": "plain_text", "text": "Schedule Meeting"},
  "submit": {"type": "plain_text", "text": "Yes — schedule it!"},
  "blocks": [
    {
      "type": "input",
      "label": {"type": "plain_text", "text": "Title"},
      "element": {
        "type": "plain_text_input",
        "action_id": "meeting_title",
        "initial_value": "Weekly Sync",
        "placeholder": {"type": "plain_text", "text": "Meeting with Alice..."}
      }
    },
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "*When:* Tuesday, Jan 28 · 2:00 - 3:00 PM EST"}
    },
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "*With:* Alice Chen, Bob Smith"}
    },
    {
      "type": "input",
      "optional": true,
      "label": {"type": "plain_text", "text": "Description"},
      "element": {
        "type": "plain_text_input",
        "multiline": true,
        "action_id": "meeting_description"
      }
    }
  ]
}
```

---

## Storage: In-Memory Proposal Cache

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

PROPOSAL_TTL = timedelta(hours=1)

@dataclass
class CachedProposalSet:
    data: InteractiveProposalSet
    created_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.created_at + PROPOSAL_TTL


class ProposalCache:
    """Simple in-memory cache with TTL expiry."""

    def __init__(self):
        self._store: Dict[str, CachedProposalSet] = {}
        self._lock = threading.Lock()

    def store(self, session_id: str, proposals: InteractiveProposalSet) -> None:
        with self._lock:
            self._store[session_id] = CachedProposalSet(
                data=proposals,
                created_at=datetime.utcnow()
            )
            self._cleanup_expired()

    def get(self, session_id: str) -> Optional[InteractiveProposalSet]:
        with self._lock:
            cached = self._store.get(session_id)
            if cached and not cached.is_expired:
                return cached.data
            return None

    def _cleanup_expired(self) -> None:
        expired = [k for k, v in self._store.items() if v.is_expired]
        for k in expired:
            del self._store[k]


# Global instance
proposal_cache = ProposalCache()
```

**Graceful degradation:** If proposal not found or expired, respond: "Those options have expired. Want me to find times again?"

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Proposal expired / not found | "Those options have expired. Ask me to find times again." |
| Calendar API fails | Agent receives error, responds conversationally |
| User cancels modal | No action; proposals remain available |
| Network timeout | Show error in Slack |
| Slackbot restart | Proposals lost; user re-asks naturally |

---

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `slackbot/services/proposal_cache.py` | In-memory proposal storage |
| `slackbot/services/interactive_proposals.py` | Data models and formatter |
| `slackbot/adapters/slack_proposal_adapter.py` | Block Kit rendering |
| `slackbot/listeners/actions/proposal_actions.py` | Button click + modal handlers |
| `slackbot/services/agent_bridge.py` | Synthetic message generation |

### Modified Files

| File | Changes |
|------|---------|
| `letta/scheduling_orchestrator/formatting.py` | Emit `InteractiveProposalSet` alongside text |
| `slackbot/listeners/listeners.py` | Register new action handlers |
| `slackbot/ai/providers/letta_stream.py` | Detect interactive proposal output, trigger rendering |

---

## Implementation Phases

### Phase 1: Core Infrastructure
- Data models (`InteractiveProposal`, `InteractiveProposalSet`)
- Proposal cache
- Orchestrator changes to emit structured proposals

### Phase 2: Slack Adapter
- Block Kit rendering (buttons, sections)
- Button click handler
- Modal view

### Phase 3: Agent Integration
- Synthetic message generation
- Agent bridge to inject messages
- Test end-to-end flow

### Phase 4: Polish
- Progressive disclosure (expand button)
- Error handling
- Mobile testing

---

## Success Criteria

1. User can click a button to select a meeting time
2. Pre-filled modal appears with correct data
3. Submitting modal schedules the meeting via agent
4. Agent responds conversationally confirming the scheduling
5. Expired proposals handled gracefully
6. Works on Slack mobile

---

## Future Considerations

- **Web adapter** - Same data models, different rendering (React components)
- **Telegram adapter** - Inline keyboards
- **Undo/reschedule** - Button to modify after scheduling
- **Multi-user** - Would need persistent storage (Supabase)
