# Interactive Scheduling Proposals - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform scheduling orchestrator results into interactive button-driven Slack experiences with pre-filled confirmation modals and agent-mediated scheduling.

**Architecture:** Platform-agnostic abstraction layer (Proposal Formatter, Action Handler, Agent Bridge) with Slack Block Kit adapter. In-memory proposal cache with TTL. Agent receives synthetic structured messages for scheduling continuity.

**Tech Stack:** Python 3.9+, Slack Bolt, Slack Block Kit, Letta API (streaming), threading for cache

**Design Document:** `docs/plans/2026-01-27-interactive-scheduling-proposals-design.md`

---

## Components to Create

| File | Purpose |
|------|---------|
| `slackbot/services/proposal_cache.py` | In-memory proposal storage with TTL |
| `slackbot/services/interactive_proposals.py` | Data models and formatter |
| `slackbot/adapters/slack_proposal_adapter.py` | Block Kit rendering |
| `slackbot/listeners/actions/proposal_actions.py` | Button click + modal handlers |
| `slackbot/services/agent_bridge.py` | Synthetic message generation |

## Components to Modify

| File | Changes |
|------|---------|
| `letta/scheduling_orchestrator/formatting.py` | Emit `InteractiveProposalSet` alongside text |
| `slackbot/listeners/listeners.py` | Register new action handlers |
| `slackbot/ai/providers/letta_stream.py` | Detect interactive proposal output, trigger rendering |

---

## Agent Parallelization Opportunities

| Opportunity | Tasks | Notes |
|-------------|-------|-------|
| **Phase 1 Parallel** | Tasks 1.1 + 1.2 | Data models and cache are independent |
| **Phase 2 Parallel** | Tasks 2.1 + 2.2 | Block Kit adapter and action handler skeleton |
| **Code Review** | After Phase 2 | Checkpoint before orchestrator integration |
| **Phase 3 Parallel** | Tasks 3.1 + 3.2 | Modal handler and agent bridge |

---

## Phase 1: Core Infrastructure

### Task 1.1: Create Data Models

**Files:**
- Create: `slackbot/services/interactive_proposals.py`
- Test: `slackbot/tests/services/test_interactive_proposals.py`

**Step 1: Create test directory if needed**

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/slackbot/tests/services
touch /Volumes/main-drive/ai-PA/slackbot/tests/services/__init__.py
```
Expected: Directory created

**Step 2: Write failing test for data models**

Create `slackbot/tests/services/test_interactive_proposals.py`:
```python
"""Tests for interactive proposal data models."""
import pytest
from datetime import datetime


def test_interactive_proposal_creation():
    """InteractiveProposal can be created with required fields."""
    from services.interactive_proposals import InteractiveProposal

    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com", "bob@example.com"],
        category="clean",
    )
    assert proposal.id == "prop_001"
    assert proposal.index == 1
    assert proposal.label == "Mon 2-3pm"
    assert proposal.category == "clean"
    assert len(proposal.participants) == 2


def test_interactive_proposal_with_conflict():
    """InteractiveProposal can include conflict metadata."""
    from services.interactive_proposals import InteractiveProposal, MovedEventInfo

    moved = MovedEventInfo(
        event_id="evt_123",
        event_title="Standup",
        old_start="2026-01-28T14:00:00Z",
        new_start="2026-01-28T15:00:00Z",
        owner="alice@example.com",
    )

    proposal = InteractiveProposal(
        id="prop_002",
        index=2,
        label="Mon 2-3pm ⚡",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="moves 'Standup' to 3pm",
        moved_events=[moved],
    )
    assert proposal.category == "move"
    assert proposal.conflict_summary == "moves 'Standup' to 3pm"
    assert len(proposal.moved_events) == 1


def test_interactive_proposal_set_creation():
    """InteractiveProposalSet groups proposals correctly."""
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
        MeetingContext,
    )

    clean_prop = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
    )

    conflict_prop = InteractiveProposal(
        id="prop_002",
        index=2,
        label="Tue 10-11am",
        start_utc="2026-01-29T10:00:00Z",
        end_utc="2026-01-29T11:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="requires moving 1 event",
    )

    context = MeetingContext(
        inferred_title="Weekly Sync",
        participant_names={"alice@example.com": "Alice Chen"},
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        clean_proposals=[clean_prop],
        conflict_proposals=[conflict_prop],
        meeting_context=context,
    )

    assert proposal_set.session_id == "sess_abc123"
    assert len(proposal_set.clean_proposals) == 1
    assert len(proposal_set.conflict_proposals) == 1
    assert proposal_set.meeting_context.inferred_title == "Weekly Sync"


def test_meeting_context_optional_fields():
    """MeetingContext handles optional fields."""
    from services.interactive_proposals import MeetingContext

    # Minimal context
    context = MeetingContext()
    assert context.inferred_title is None
    assert context.zoom_link is None
    assert context.participant_names == {}

    # Full context
    full_context = MeetingContext(
        inferred_title="Team Standup",
        inferred_description="Daily sync meeting",
        zoom_link="https://zoom.us/j/123",
        participant_names={"a@b.com": "Alice"},
    )
    assert full_context.inferred_title == "Team Standup"
    assert full_context.zoom_link == "https://zoom.us/j/123"
```

**Step 3: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_interactive_proposals.py -v
```
Expected: FAIL (module not found)

**Step 4: Create services directory if needed**

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/slackbot/services
touch /Volumes/main-drive/ai-PA/slackbot/services/__init__.py
```
Expected: Directory created

**Step 5: Implement data models**

Create `slackbot/services/interactive_proposals.py`:
```python
"""
Data models for interactive scheduling proposals.

Platform-agnostic models that can be rendered to Slack Block Kit,
web components, or other UIs.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class MovedEventInfo:
    """Information about an event that would be moved."""
    event_id: str
    event_title: str
    old_start: str  # ISO 8601 UTC
    new_start: str  # ISO 8601 UTC
    owner: str  # Email address


@dataclass
class InteractiveProposal:
    """A single selectable meeting proposal."""
    id: str                                    # Unique ID (e.g., "prop_001")
    index: int                                 # Display number (1, 2, 3...)
    label: str                                 # Button text: "Mon 2-3pm"

    # Scheduling data (for tool call)
    start_utc: str                             # ISO 8601
    end_utc: str
    participants: List[str]                    # Email addresses

    # Category and conflict info
    category: str                              # "clean" | "move" | "override"

    # Optional fields
    suggested_title: Optional[str] = None      # From conversation context
    suggested_description: Optional[str] = None
    conflict_summary: Optional[str] = None     # "moves 'Standup' to 3pm"
    moved_events: List[MovedEventInfo] = field(default_factory=list)


@dataclass
class MeetingContext:
    """Contextual hints extracted from conversation."""
    inferred_title: Optional[str] = None
    inferred_description: Optional[str] = None
    zoom_link: Optional[str] = None
    participant_names: Dict[str, str] = field(default_factory=dict)  # email -> display name


@dataclass
class InteractiveProposalSet:
    """Complete set of proposals ready for rendering."""
    session_id: str                            # Links back to conversation
    user_id: str                               # Slack user ID

    clean_proposals: List[InteractiveProposal] = field(default_factory=list)
    conflict_proposals: List[InteractiveProposal] = field(default_factory=list)

    meeting_context: MeetingContext = field(default_factory=MeetingContext)
    show_conflicts_expanded: bool = False      # True if no clean options
    created_at: datetime = field(default_factory=datetime.utcnow)

    def get_proposal_by_id(self, proposal_id: str) -> Optional[InteractiveProposal]:
        """Find a proposal by its ID."""
        for prop in self.clean_proposals + self.conflict_proposals:
            if prop.id == proposal_id:
                return prop
        return None
```

**Step 6: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_interactive_proposals.py -v
```
Expected: PASS

**Step 7: Commit**

```bash
git add slackbot/services/interactive_proposals.py slackbot/services/__init__.py
git add slackbot/tests/services/test_interactive_proposals.py slackbot/tests/services/__init__.py
git commit -m "feat: add interactive proposal data models"
```

---

### Task 1.2: Create Proposal Cache

**Files:**
- Create: `slackbot/services/proposal_cache.py`
- Test: `slackbot/tests/services/test_proposal_cache.py`

**Step 1: Write failing test**

Create `slackbot/tests/services/test_proposal_cache.py`:
```python
"""Tests for proposal cache."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch


def test_store_and_retrieve():
    """Can store and retrieve a proposal set."""
    from services.proposal_cache import ProposalCache
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    cache = ProposalCache()

    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        clean_proposals=[proposal],
    )

    cache.store("sess_abc123", proposal_set)
    retrieved = cache.get("sess_abc123")

    assert retrieved is not None
    assert retrieved.session_id == "sess_abc123"
    assert len(retrieved.clean_proposals) == 1


def test_retrieve_nonexistent_returns_none():
    """Retrieving nonexistent session returns None."""
    from services.proposal_cache import ProposalCache

    cache = ProposalCache()
    result = cache.get("nonexistent")
    assert result is None


def test_expired_proposals_return_none():
    """Expired proposals return None."""
    from services.proposal_cache import ProposalCache, CachedProposalSet, PROPOSAL_TTL
    from services.interactive_proposals import InteractiveProposalSet

    cache = ProposalCache()

    proposal_set = InteractiveProposalSet(
        session_id="sess_expired",
        user_id="U12345",
    )

    # Manually insert with old timestamp
    expired_time = datetime.utcnow() - PROPOSAL_TTL - timedelta(minutes=1)
    cache._store["sess_expired"] = CachedProposalSet(
        data=proposal_set,
        created_at=expired_time,
    )

    result = cache.get("sess_expired")
    assert result is None


def test_cleanup_removes_expired():
    """Cleanup removes expired entries."""
    from services.proposal_cache import ProposalCache, CachedProposalSet, PROPOSAL_TTL
    from services.interactive_proposals import InteractiveProposalSet

    cache = ProposalCache()

    # Add fresh entry
    fresh_set = InteractiveProposalSet(session_id="sess_fresh", user_id="U1")
    cache.store("sess_fresh", fresh_set)

    # Add expired entry manually
    expired_set = InteractiveProposalSet(session_id="sess_old", user_id="U2")
    expired_time = datetime.utcnow() - PROPOSAL_TTL - timedelta(minutes=1)
    cache._store["sess_old"] = CachedProposalSet(
        data=expired_set,
        created_at=expired_time,
    )

    # Trigger cleanup via store
    another_set = InteractiveProposalSet(session_id="sess_new", user_id="U3")
    cache.store("sess_new", another_set)

    # Expired should be gone
    assert "sess_old" not in cache._store
    assert "sess_fresh" in cache._store
    assert "sess_new" in cache._store


def test_global_instance_available():
    """Global proposal_cache instance is available."""
    from services.proposal_cache import proposal_cache

    assert proposal_cache is not None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_proposal_cache.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement proposal cache**

Create `slackbot/services/proposal_cache.py`:
```python
"""
In-memory proposal cache with TTL expiry.

Stores interactive proposal sets for button click handling.
Graceful degradation: if proposal not found, user re-asks naturally.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

from services.interactive_proposals import InteractiveProposalSet


PROPOSAL_TTL = timedelta(hours=1)


@dataclass
class CachedProposalSet:
    """Wrapper with timestamp for TTL tracking."""
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
        """Store a proposal set, keyed by session ID."""
        with self._lock:
            self._store[session_id] = CachedProposalSet(
                data=proposals,
                created_at=datetime.utcnow(),
            )
            self._cleanup_expired()

    def get(self, session_id: str) -> Optional[InteractiveProposalSet]:
        """Retrieve a proposal set if it exists and hasn't expired."""
        with self._lock:
            cached = self._store.get(session_id)
            if cached and not cached.is_expired:
                return cached.data
            # Remove if expired
            if cached and cached.is_expired:
                del self._store[session_id]
            return None

    def get_proposal(self, session_id: str, proposal_id: str):
        """Convenience method to get a specific proposal."""
        proposal_set = self.get(session_id)
        if proposal_set:
            return proposal_set.get_proposal_by_id(proposal_id)
        return None

    def _cleanup_expired(self) -> None:
        """Remove all expired entries. Called within lock."""
        expired = [k for k, v in self._store.items() if v.is_expired]
        for k in expired:
            del self._store[k]


# Global instance
proposal_cache = ProposalCache()
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_proposal_cache.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add slackbot/services/proposal_cache.py
git add slackbot/tests/services/test_proposal_cache.py
git commit -m "feat: add in-memory proposal cache with TTL"
```

---

## Phase 2: Slack Adapter and Action Handler

### Task 2.1: Create Slack Block Kit Adapter

**Files:**
- Create: `slackbot/adapters/__init__.py`
- Create: `slackbot/adapters/slack_proposal_adapter.py`
- Test: `slackbot/tests/adapters/test_slack_proposal_adapter.py`

**Step 1: Create directories**

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/slackbot/adapters
touch /Volumes/main-drive/ai-PA/slackbot/adapters/__init__.py
mkdir -p /Volumes/main-drive/ai-PA/slackbot/tests/adapters
touch /Volumes/main-drive/ai-PA/slackbot/tests/adapters/__init__.py
```
Expected: Directories created

**Step 2: Write failing test**

Create `slackbot/tests/adapters/test_slack_proposal_adapter.py`:
```python
"""Tests for Slack Block Kit proposal adapter."""
import pytest


def test_render_proposal_buttons_clean():
    """Renders clean proposals as buttons."""
    from adapters.slack_proposal_adapter import render_proposal_blocks
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        clean_proposals=[proposal],
    )

    blocks = render_proposal_blocks(proposal_set)

    assert isinstance(blocks, list)
    assert len(blocks) > 0

    # Should have a section with "Best Options" header
    section_texts = [
        b.get("text", {}).get("text", "")
        for b in blocks
        if b.get("type") == "section"
    ]
    assert any("Best Options" in t for t in section_texts)

    # Should have actions block with buttons
    actions_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions_blocks) > 0

    # Button should have correct action_id and value format
    button = actions_blocks[0]["elements"][0]
    assert button["action_id"] == "schedule_proposal_select"
    assert button["value"] == "sess_abc123:prop_001"


def test_render_conflict_proposals_with_expand():
    """Conflict proposals show with expand button when clean options exist."""
    from adapters.slack_proposal_adapter import render_proposal_blocks
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    clean_prop = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
    )

    conflict_prop = InteractiveProposal(
        id="prop_002",
        index=2,
        label="Tue 10-11am",
        start_utc="2026-01-29T10:00:00Z",
        end_utc="2026-01-29T11:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="moves 'Standup' to 3pm",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        clean_proposals=[clean_prop],
        conflict_proposals=[conflict_prop],
        show_conflicts_expanded=False,
    )

    blocks = render_proposal_blocks(proposal_set)

    # Should have expand button
    button_texts = []
    for b in blocks:
        if b.get("type") == "actions":
            for elem in b.get("elements", []):
                if elem.get("type") == "button":
                    button_texts.append(elem.get("text", {}).get("text", ""))

    assert any("more options" in t.lower() for t in button_texts)


def test_render_only_conflict_proposals():
    """When no clean options, conflict proposals shown directly."""
    from adapters.slack_proposal_adapter import render_proposal_blocks
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    conflict_prop = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Tue 10-11am ⚡",
        start_utc="2026-01-29T10:00:00Z",
        end_utc="2026-01-29T11:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="moves 'Standup' to 3pm",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        conflict_proposals=[conflict_prop],
        show_conflicts_expanded=True,  # No clean options
    )

    blocks = render_proposal_blocks(proposal_set)

    # Should show conflict section header
    section_texts = [
        b.get("text", {}).get("text", "")
        for b in blocks
        if b.get("type") == "section"
    ]
    assert any("changes" in t.lower() or "move" in t.lower() for t in section_texts)


def test_render_confirmation_modal():
    """Renders confirmation modal with pre-filled data."""
    from adapters.slack_proposal_adapter import render_confirmation_modal
    from services.interactive_proposals import (
        InteractiveProposal,
        MeetingContext,
    )

    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com", "bob@example.com"],
        category="clean",
        suggested_title="Weekly Sync",
    )

    context = MeetingContext(
        inferred_title="Weekly Sync",
        participant_names={
            "alice@example.com": "Alice Chen",
            "bob@example.com": "Bob Smith",
        },
    )

    modal = render_confirmation_modal(proposal, context, "sess_abc123")

    assert modal["type"] == "modal"
    assert modal["callback_id"] == "schedule_proposal_confirm"
    assert "Schedule Meeting" in modal["title"]["text"]

    # Should have submit button
    assert "schedule" in modal["submit"]["text"].lower()

    # Should have blocks with pre-filled title
    block_texts = []
    for block in modal["blocks"]:
        if block.get("type") == "input":
            elem = block.get("element", {})
            if elem.get("initial_value"):
                block_texts.append(elem["initial_value"])

    assert "Weekly Sync" in block_texts
```

**Step 3: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/adapters/test_slack_proposal_adapter.py -v
```
Expected: FAIL (module not found)

**Step 4: Implement Slack adapter**

Create `slackbot/adapters/slack_proposal_adapter.py`:
```python
"""
Slack Block Kit adapter for interactive proposals.

Converts platform-agnostic InteractiveProposalSet to Slack Block Kit JSON.
"""
from typing import Any, Dict, List

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
)


def render_proposal_blocks(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """
    Render an InteractiveProposalSet as Slack Block Kit blocks.

    Returns a list of blocks suitable for chat.postMessage or views.publish.
    """
    blocks: List[Dict[str, Any]] = []

    # Section 1: Clean proposals (Best Options)
    if proposal_set.clean_proposals:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📅 *Best Options*",
            },
        })

        # Create buttons for clean proposals (max 5 per actions block)
        clean_buttons = _create_proposal_buttons(
            proposal_set.clean_proposals,
            proposal_set.session_id,
        )

        # Slack limits actions blocks to 25 elements, but 5 buttons per row is cleaner
        for i in range(0, len(clean_buttons), 5):
            blocks.append({
                "type": "actions",
                "elements": clean_buttons[i:i+5],
            })

    # Section 2: Conflict proposals
    if proposal_set.conflict_proposals:
        # If we have clean options, add expand button first
        if proposal_set.clean_proposals and not proposal_set.show_conflicts_expanded:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "▸ Show more options (requires changes)...",
                    },
                    "action_id": "schedule_proposal_expand",
                    "value": proposal_set.session_id,
                }],
            })
        else:
            # Show conflict section directly
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Options that require changes*",
                },
            })

            conflict_buttons = _create_proposal_buttons(
                proposal_set.conflict_proposals,
                proposal_set.session_id,
                include_conflict_indicator=True,
            )

            for i in range(0, len(conflict_buttons), 5):
                blocks.append({
                    "type": "actions",
                    "elements": conflict_buttons[i:i+5],
                })

    return blocks


def _create_proposal_buttons(
    proposals: List[InteractiveProposal],
    session_id: str,
    include_conflict_indicator: bool = False,
) -> List[Dict[str, Any]]:
    """Create button elements for proposals."""
    buttons = []

    for prop in proposals:
        label = prop.label
        if include_conflict_indicator and prop.conflict_summary:
            label = f"{label} ⚡"

        buttons.append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": f"{prop.index} {label}",
                "emoji": True,
            },
            "action_id": "schedule_proposal_select",
            "value": f"{session_id}:{prop.id}",
        })

    return buttons


def render_confirmation_modal(
    proposal: InteractiveProposal,
    context: MeetingContext,
    session_id: str,
) -> Dict[str, Any]:
    """
    Render confirmation modal with pre-filled meeting details.

    Returns Slack modal view object.
    """
    # Format participants list
    participant_names = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_names.append(name)
        else:
            # Extract name from email
            participant_names.append(email.split("@")[0].capitalize())

    participants_text = ", ".join(participant_names) if participant_names else "No participants"

    # Format date/time for display
    from datetime import datetime
    import pytz

    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(proposal.end_utc.replace("Z", "+00:00"))

        tz = pytz.timezone("America/New_York")
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)

        # Format: "Tuesday, Jan 28 · 2:00 - 3:00 PM EST"
        date_str = start_local.strftime("%A, %b %d")
        start_time = start_local.strftime("%I:%M").lstrip("0")
        end_time = end_local.strftime("%I:%M %p %Z").lstrip("0")
        when_text = f"{date_str} · {start_time} - {end_time}"
    except Exception:
        when_text = f"{proposal.start_utc} - {proposal.end_utc}"

    # Determine title (from proposal or context)
    title = proposal.suggested_title or context.inferred_title or ""
    title_placeholder = f"Meeting with {participant_names[0]}..." if participant_names else "Meeting title"

    # Build modal blocks
    blocks: List[Dict[str, Any]] = [
        {
            "type": "input",
            "block_id": "title_block",
            "label": {"type": "plain_text", "text": "Title"},
            "element": {
                "type": "plain_text_input",
                "action_id": "meeting_title",
                "initial_value": title,
                "placeholder": {"type": "plain_text", "text": title_placeholder},
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*When:* {when_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*With:* {participants_text}",
            },
        },
        {
            "type": "input",
            "block_id": "description_block",
            "optional": True,
            "label": {"type": "plain_text", "text": "Description"},
            "element": {
                "type": "plain_text_input",
                "action_id": "meeting_description",
                "multiline": True,
                "initial_value": context.inferred_description or "",
            },
        },
    ]

    # Add conflict warning if applicable
    if proposal.conflict_summary:
        blocks.insert(0, {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Note:* This option {proposal.conflict_summary}",
            },
        })

    return {
        "type": "modal",
        "callback_id": "schedule_proposal_confirm",
        "private_metadata": f"{session_id}:{proposal.id}",
        "title": {"type": "plain_text", "text": "Schedule Meeting"},
        "submit": {"type": "plain_text", "text": "Yes — schedule it!"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def render_expanded_conflicts(proposal_set: InteractiveProposalSet) -> List[Dict[str, Any]]:
    """
    Render conflict proposals section after user clicks expand.

    Returns blocks to append to existing message.
    """
    if not proposal_set.conflict_proposals:
        return []

    blocks: List[Dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚠️ *Options that require changes*",
            },
        },
    ]

    conflict_buttons = _create_proposal_buttons(
        proposal_set.conflict_proposals,
        proposal_set.session_id,
        include_conflict_indicator=True,
    )

    for i in range(0, len(conflict_buttons), 5):
        blocks.append({
            "type": "actions",
            "elements": conflict_buttons[i:i+5],
        })

    return blocks
```

**Step 5: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/adapters/test_slack_proposal_adapter.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add slackbot/adapters/
git add slackbot/tests/adapters/
git commit -m "feat: add Slack Block Kit adapter for proposals"
```

---

### Task 2.2: Create Action Handler Skeleton

**Files:**
- Create: `slackbot/listeners/actions/proposal_actions.py`
- Test: `slackbot/tests/listeners/actions/test_proposal_actions.py`

**Step 1: Create test directory if needed**

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/slackbot/tests/listeners/actions
touch /Volumes/main-drive/ai-PA/slackbot/tests/listeners/actions/__init__.py
```
Expected: Directory created

**Step 2: Write failing test**

Create `slackbot/tests/listeners/actions/test_proposal_actions.py`:
```python
"""Tests for proposal action handlers."""
import pytest
from unittest.mock import MagicMock, patch


def test_register_adds_handlers():
    """Register function adds action handlers to app."""
    from listeners.actions.proposal_actions import register

    mock_app = MagicMock()
    register(mock_app)

    # Should register handlers for:
    # - schedule_proposal_select (button click)
    # - schedule_proposal_expand (expand conflicts)
    assert mock_app.action.call_count >= 2

    # Get the action IDs registered
    action_ids = [call[0][0] for call in mock_app.action.call_args_list]
    assert "schedule_proposal_select" in action_ids
    assert "schedule_proposal_expand" in action_ids


def test_proposal_select_opens_modal():
    """Clicking proposal button opens confirmation modal."""
    from listeners.actions.proposal_actions import _handle_proposal_select
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
        MeetingContext,
    )
    from services.proposal_cache import proposal_cache

    # Set up test data
    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
        suggested_title="Test Meeting",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_test",
        user_id="U12345",
        clean_proposals=[proposal],
        meeting_context=MeetingContext(inferred_title="Test Meeting"),
    )

    proposal_cache.store("sess_test", proposal_set)

    # Mock Slack objects
    mock_ack = MagicMock()
    mock_client = MagicMock()
    mock_body = {
        "trigger_id": "trigger_123",
        "actions": [{"value": "sess_test:prop_001"}],
    }
    mock_logger = MagicMock()

    # Call handler
    _handle_proposal_select(mock_ack, mock_body, mock_client, mock_logger)

    # Verify modal opened
    mock_ack.assert_called_once()
    mock_client.views_open.assert_called_once()

    # Verify modal has correct callback_id
    call_args = mock_client.views_open.call_args
    view = call_args.kwargs.get("view") or call_args[1].get("view")
    assert view["callback_id"] == "schedule_proposal_confirm"


def test_proposal_select_expired_shows_message():
    """Clicking expired proposal shows friendly message."""
    from listeners.actions.proposal_actions import _handle_proposal_select

    mock_ack = MagicMock()
    mock_client = MagicMock()
    mock_body = {
        "trigger_id": "trigger_123",
        "actions": [{"value": "sess_nonexistent:prop_001"}],
        "channel": {"id": "C12345"},
        "user": {"id": "U12345"},
    }
    mock_logger = MagicMock()

    _handle_proposal_select(mock_ack, mock_body, mock_client, mock_logger)

    # Should ack
    mock_ack.assert_called_once()

    # Should NOT open modal
    mock_client.views_open.assert_not_called()

    # Should send ephemeral message
    mock_client.chat_postEphemeral.assert_called_once()
    call_args = mock_client.chat_postEphemeral.call_args
    text = call_args.kwargs.get("text") or call_args[1].get("text")
    assert "expired" in text.lower()
```

**Step 3: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/listeners/actions/test_proposal_actions.py -v
```
Expected: FAIL (module not found)

**Step 4: Implement action handler**

Create `slackbot/listeners/actions/proposal_actions.py`:
```python
"""
Action handlers for interactive scheduling proposals.

Handles button clicks, modal confirmations, and expand actions.
"""
from logging import Logger
from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.proposal_cache import proposal_cache
from adapters.slack_proposal_adapter import (
    render_confirmation_modal,
    render_expanded_conflicts,
)


def _handle_proposal_select(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle proposal button click - opens confirmation modal."""
    ack()

    try:
        # Extract session_id and proposal_id from button value
        action_value = body["actions"][0]["value"]
        session_id, proposal_id = action_value.split(":", 1)

        # Look up proposal from cache
        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            # Proposals expired or not found
            channel_id = body.get("channel", {}).get("id")
            user_id = body.get("user", {}).get("id")

            if channel_id and user_id:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Those options have expired. Ask me to find times again! 🔄",
                )
            logger.warning(f"Proposal set not found for session: {session_id}")
            return

        # Find the specific proposal
        proposal = proposal_set.get_proposal_by_id(proposal_id)

        if not proposal:
            logger.error(f"Proposal {proposal_id} not found in session {session_id}")
            return

        # Render and open confirmation modal
        modal = render_confirmation_modal(
            proposal=proposal,
            context=proposal_set.meeting_context,
            session_id=session_id,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

        logger.info(f"Opened confirmation modal for proposal {proposal_id}")

    except Exception as e:
        logger.error(f"Error handling proposal select: {e}", exc_info=True)


def _handle_proposal_expand(
    ack: Ack,
    body: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle expand button click - shows conflict proposals."""
    ack()

    try:
        session_id = body["actions"][0]["value"]

        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            channel_id = body.get("channel", {}).get("id")
            user_id = body.get("user", {}).get("id")

            if channel_id and user_id:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Those options have expired. Ask me to find times again! 🔄",
                )
            return

        # Mark as expanded and get new blocks
        proposal_set.show_conflicts_expanded = True

        # Get the expanded conflict blocks
        expanded_blocks = render_expanded_conflicts(proposal_set)

        if expanded_blocks:
            # Update the message to include expanded conflicts
            # We need to reconstruct the full block list
            from adapters.slack_proposal_adapter import render_proposal_blocks
            full_blocks = render_proposal_blocks(proposal_set)

            # Update the message
            channel_id = body.get("channel", {}).get("id")
            message_ts = body.get("message", {}).get("ts")

            if channel_id and message_ts:
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=full_blocks,
                )

        logger.info(f"Expanded conflict proposals for session {session_id}")

    except Exception as e:
        logger.error(f"Error handling proposal expand: {e}", exc_info=True)


def register(app: App) -> None:
    """Register action handlers with the Slack app."""

    @app.action("schedule_proposal_select")
    def on_proposal_select(ack, body, client, logger):
        _handle_proposal_select(ack, body, client, logger)

    @app.action("schedule_proposal_expand")
    def on_proposal_expand(ack, body, client, logger):
        _handle_proposal_expand(ack, body, client, logger)
```

**Step 5: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/listeners/actions/test_proposal_actions.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add slackbot/listeners/actions/proposal_actions.py
git add slackbot/tests/listeners/actions/test_proposal_actions.py
git commit -m "feat: add proposal action handlers for button clicks"
```

---

## Phase 3: Modal and Agent Integration

### Task 3.1: Add Modal Submission Handler

**Files:**
- Create: `slackbot/listeners/views/proposal_confirm.py`
- Modify: `slackbot/listeners/actions/proposal_actions.py` (add view handler)
- Test: `slackbot/tests/listeners/views/test_proposal_confirm.py`

**Step 1: Write failing test**

Create `slackbot/tests/listeners/views/test_proposal_confirm.py`:
```python
"""Tests for proposal confirmation modal submission."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_register_view_handler():
    """Register function adds view submission handler."""
    from listeners.views.proposal_confirm import register

    mock_app = MagicMock()
    register(mock_app)

    # Should register view handler
    mock_app.view.assert_called()

    # Get the callback_id registered
    call_args = mock_app.view.call_args
    callback_id = call_args[0][0]
    assert callback_id == "schedule_proposal_confirm"


def test_modal_submit_extracts_values():
    """Modal submission extracts form values correctly."""
    from listeners.views.proposal_confirm import _handle_proposal_confirm
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
        MeetingContext,
    )
    from services.proposal_cache import proposal_cache

    # Set up test data
    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="clean",
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_modal_test",
        user_id="U12345",
        clean_proposals=[proposal],
    )

    proposal_cache.store("sess_modal_test", proposal_set)

    # Mock view with form values
    mock_view = {
        "private_metadata": "sess_modal_test:prop_001",
        "state": {
            "values": {
                "title_block": {
                    "meeting_title": {"value": "Team Sync"},
                },
                "description_block": {
                    "meeting_description": {"value": "Weekly team meeting"},
                },
            },
        },
    }

    mock_ack = MagicMock()
    mock_body = {"user": {"id": "U12345"}}
    mock_client = MagicMock()
    mock_logger = MagicMock()

    # Call handler
    with patch("listeners.views.proposal_confirm.send_synthetic_message") as mock_send:
        _handle_proposal_confirm(mock_ack, mock_body, mock_view, mock_client, mock_logger)

    mock_ack.assert_called_once()

    # Verify synthetic message was sent with correct data
    mock_send.assert_called_once()
    call_args = mock_send.call_args

    # Check that proposal data was included
    assert call_args is not None
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/listeners/views/test_proposal_confirm.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement modal handler**

Create `slackbot/listeners/views/proposal_confirm.py`:
```python
"""
View submission handler for proposal confirmation modal.

Extracts form values, combines with proposal data, and sends
synthetic message to agent for scheduling.
"""
from logging import Logger
from slack_bolt import Ack, App
from slack_sdk import WebClient

from services.proposal_cache import proposal_cache
from services.agent_bridge import send_synthetic_message


def _handle_proposal_confirm(
    ack: Ack,
    body: dict,
    view: dict,
    client: WebClient,
    logger: Logger,
) -> None:
    """Handle modal form submission - triggers agent scheduling."""
    ack()

    try:
        # Extract session_id and proposal_id from private_metadata
        metadata = view.get("private_metadata", "")
        if ":" not in metadata:
            logger.error(f"Invalid private_metadata format: {metadata}")
            return

        session_id, proposal_id = metadata.split(":", 1)

        # Look up proposal from cache
        proposal_set = proposal_cache.get(session_id)

        if not proposal_set:
            logger.warning(f"Proposal set expired during modal: {session_id}")
            # Send ephemeral message to user
            user_id = body.get("user", {}).get("id")
            if user_id:
                client.chat_postMessage(
                    channel=user_id,  # DM the user
                    text="Those options expired while you were editing. Please ask me to find times again! 🔄",
                )
            return

        proposal = proposal_set.get_proposal_by_id(proposal_id)

        if not proposal:
            logger.error(f"Proposal {proposal_id} not found in session {session_id}")
            return

        # Extract form values
        values = view.get("state", {}).get("values", {})

        title = values.get("title_block", {}).get("meeting_title", {}).get("value", "")
        description = values.get("description_block", {}).get("meeting_description", {}).get("value", "")

        # Use extracted values or fall back to proposal defaults
        final_title = title or proposal.suggested_title or "Meeting"
        final_description = description or ""

        # Build scheduling data
        scheduling_data = {
            "title": final_title,
            "description": final_description,
            "start": proposal.start_utc,
            "end": proposal.end_utc,
            "participants": proposal.participants,
            "proposal_id": proposal.id,
            "proposal_index": proposal.index,
            "category": proposal.category,
        }

        # Add conflict info if present
        if proposal.moved_events:
            scheduling_data["moved_events"] = [
                {
                    "event_id": me.event_id,
                    "event_title": me.event_title,
                    "old_start": me.old_start,
                    "new_start": me.new_start,
                    "owner": me.owner,
                }
                for me in proposal.moved_events
            ]

        user_id = body.get("user", {}).get("id")

        # Send synthetic message to agent
        send_synthetic_message(
            user_id=user_id,
            proposal=proposal,
            scheduling_data=scheduling_data,
            meeting_context=proposal_set.meeting_context,
            client=client,
            logger=logger,
        )

        logger.info(f"Sent synthetic scheduling message for proposal {proposal_id}")

    except Exception as e:
        logger.error(f"Error handling proposal confirmation: {e}", exc_info=True)


def register(app: App) -> None:
    """Register view submission handler with the Slack app."""

    @app.view("schedule_proposal_confirm")
    def on_proposal_confirm(ack, body, view, client, logger):
        _handle_proposal_confirm(ack, body, view, client, logger)
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/listeners/views/test_proposal_confirm.py -v
```
Expected: PASS (after implementing agent_bridge stub)

**Step 5: Commit**

```bash
git add slackbot/listeners/views/proposal_confirm.py
git add slackbot/tests/listeners/views/test_proposal_confirm.py
git commit -m "feat: add modal submission handler for proposal confirmation"
```

---

### Task 3.2: Create Agent Bridge

**Files:**
- Create: `slackbot/services/agent_bridge.py`
- Test: `slackbot/tests/services/test_agent_bridge.py`

**Step 1: Write failing test**

Create `slackbot/tests/services/test_agent_bridge.py`:
```python
"""Tests for agent bridge."""
import pytest
from unittest.mock import MagicMock, patch
import json


def test_generate_synthetic_message():
    """Generates correct synthetic message format."""
    from services.agent_bridge import generate_synthetic_message
    from services.interactive_proposals import (
        InteractiveProposal,
        MeetingContext,
    )

    proposal = InteractiveProposal(
        id="prop_001",
        index=2,
        label="Tue 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com", "bob@example.com"],
        category="clean",
    )

    scheduling_data = {
        "title": "Weekly Sync",
        "description": "Team meeting",
        "start": "2026-01-28T14:00:00Z",
        "end": "2026-01-28T15:00:00Z",
        "participants": ["alice@example.com", "bob@example.com"],
    }

    context = MeetingContext(
        participant_names={
            "alice@example.com": "Alice Chen",
            "bob@example.com": "Bob Smith",
        },
    )

    message = generate_synthetic_message(proposal, scheduling_data, context)

    # Should contain conversational context
    assert "Option 2" in message
    assert "Tuesday" in message or "Tue" in message

    # Should contain SCHEDULE_MEETING_DATA block
    assert "[SCHEDULE_MEETING_DATA]" in message
    assert "[/SCHEDULE_MEETING_DATA]" in message

    # Extract and parse JSON from block
    start_marker = "[SCHEDULE_MEETING_DATA]"
    end_marker = "[/SCHEDULE_MEETING_DATA]"
    start_idx = message.index(start_marker) + len(start_marker)
    end_idx = message.index(end_marker)
    json_str = message[start_idx:end_idx].strip()

    data = json.loads(json_str)
    assert data["title"] == "Weekly Sync"
    assert len(data["participants"]) == 2


def test_synthetic_message_includes_conflict_info():
    """Synthetic message includes conflict info when present."""
    from services.agent_bridge import generate_synthetic_message
    from services.interactive_proposals import (
        InteractiveProposal,
        MeetingContext,
        MovedEventInfo,
    )

    moved = MovedEventInfo(
        event_id="evt_123",
        event_title="Standup",
        old_start="2026-01-28T14:00:00Z",
        new_start="2026-01-28T15:00:00Z",
        owner="alice@example.com",
    )

    proposal = InteractiveProposal(
        id="prop_002",
        index=3,
        label="Mon 2-3pm",
        start_utc="2026-01-28T14:00:00Z",
        end_utc="2026-01-28T15:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="moves 'Standup' to 3pm",
        moved_events=[moved],
    )

    scheduling_data = {
        "title": "Quick Chat",
        "start": "2026-01-28T14:00:00Z",
        "end": "2026-01-28T15:00:00Z",
        "participants": ["alice@example.com"],
        "moved_events": [{
            "event_id": "evt_123",
            "event_title": "Standup",
            "old_start": "2026-01-28T14:00:00Z",
            "new_start": "2026-01-28T15:00:00Z",
            "owner": "alice@example.com",
        }],
    }

    message = generate_synthetic_message(proposal, scheduling_data, MeetingContext())

    # Should mention the move
    assert "move" in message.lower() or "Standup" in message

    # JSON should include moved_events
    start_marker = "[SCHEDULE_MEETING_DATA]"
    end_marker = "[/SCHEDULE_MEETING_DATA]"
    start_idx = message.index(start_marker) + len(start_marker)
    end_idx = message.index(end_marker)
    json_str = message[start_idx:end_idx].strip()

    data = json.loads(json_str)
    assert "moved_events" in data
    assert len(data["moved_events"]) == 1
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_agent_bridge.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement agent bridge**

Create `slackbot/services/agent_bridge.py`:
```python
"""
Agent bridge for sending synthetic structured messages to Letta.

Generates messages that combine conversational context with
machine-parseable scheduling data for agent-mediated scheduling.
"""
import json
import os
from logging import Logger
from typing import Any, Dict, Optional

from slack_sdk import WebClient

from services.interactive_proposals import (
    InteractiveProposal,
    MeetingContext,
)


def generate_synthetic_message(
    proposal: InteractiveProposal,
    scheduling_data: Dict[str, Any],
    context: MeetingContext,
) -> str:
    """
    Generate a synthetic message for the agent.

    The message contains:
    1. Conversational context (what the user selected)
    2. Machine-parseable SCHEDULE_MEETING_DATA block
    3. Clear instruction to call create_calendar_event

    Returns:
        Formatted message string ready to send to Letta.
    """
    # Format participant names for display
    participant_display = []
    for email in proposal.participants:
        name = context.participant_names.get(email)
        if name:
            participant_display.append(name)
        else:
            participant_display.append(email.split("@")[0].capitalize())

    participants_str = " and ".join(participant_display) if participant_display else "the participants"

    # Format time for conversational context
    from datetime import datetime
    import pytz

    try:
        start_dt = datetime.fromisoformat(proposal.start_utc.replace("Z", "+00:00"))
        tz = pytz.timezone("America/New_York")
        start_local = start_dt.astimezone(tz)
        time_str = start_local.strftime("%A at %I:%M %p").replace(" 0", " ")
    except Exception:
        time_str = proposal.label

    # Build conversational intro
    lines = []
    lines.append(f"User selected Option {proposal.index}: {time_str} with {participants_str}.")

    title = scheduling_data.get("title", "Meeting")
    lines.append(f"They confirmed title '{title}'.")

    # Add conflict context if present
    if proposal.conflict_summary:
        lines.append(f"Note: This option {proposal.conflict_summary}.")

    lines.append("")
    lines.append("Please schedule this meeting:")
    lines.append("")

    # Add machine-parseable data block
    lines.append("[SCHEDULE_MEETING_DATA]")
    lines.append(json.dumps(scheduling_data, indent=2))
    lines.append("[/SCHEDULE_MEETING_DATA]")
    lines.append("")
    lines.append("Call create_calendar_event and confirm once scheduled.")

    return "\n".join(lines)


def send_synthetic_message(
    user_id: str,
    proposal: InteractiveProposal,
    scheduling_data: Dict[str, Any],
    meeting_context: MeetingContext,
    client: WebClient,
    logger: Logger,
) -> None:
    """
    Send a synthetic scheduling message to the Letta agent.

    This function:
    1. Generates the synthetic message
    2. Opens a DM channel with the user
    3. Posts an indicator message
    4. Sends the synthetic message to Letta
    5. Streams the response back to Slack

    Args:
        user_id: Slack user ID
        proposal: The selected proposal
        scheduling_data: Combined form + proposal data
        meeting_context: Meeting context from proposal set
        client: Slack WebClient
        logger: Logger instance
    """
    from ai.conversation_helper import get_conversation_for_user
    from ai.providers.letta_stream import LettaAPIStreaming

    try:
        # Generate the synthetic message
        synthetic_message = generate_synthetic_message(
            proposal=proposal,
            scheduling_data=scheduling_data,
            context=meeting_context,
        )

        logger.info(f"Generated synthetic message for user {user_id}")
        logger.debug(f"Synthetic message:\n{synthetic_message}")

        # Open DM channel with user
        dm_response = client.conversations_open(users=[user_id])
        if not dm_response.get("ok"):
            logger.error(f"Failed to open DM with user {user_id}")
            return

        channel_id = dm_response.get("channel", {}).get("id")
        if not channel_id:
            logger.error("No channel ID in conversations.open response")
            return

        # Post an indicator message
        client.chat_postMessage(
            channel=channel_id,
            text=f"📅 Scheduling your meeting: *{scheduling_data.get('title', 'Meeting')}*...",
        )

        # Get or create conversation for this user
        conversation_id = None
        try:
            conversation_id = get_conversation_for_user(user_id, logger=logger)
        except Exception as e:
            logger.warning(f"Could not get conversation for user: {e}")

        # Send to Letta agent
        streamer = LettaAPIStreaming(logger=logger, conversation_id=conversation_id)

        # Use system prompt that clarifies this is a scheduling action
        system_prompt = (
            "The user has selected a meeting time from the interactive proposals. "
            "Parse the SCHEDULE_MEETING_DATA block and call create_calendar_event to schedule the meeting. "
            "Respond conversationally to confirm the scheduling was successful."
        )

        # Collect response
        text_chunks = []
        for event in streamer.chat_stream_with_events(system_prompt, synthetic_message):
            event_type = event.get("type")
            if event_type == "text":
                text_chunks.append(event.get("content", ""))
            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "")
                logger.info(f"Agent called tool: {tool_name}")

        # Post agent response
        final_text = (streamer.last_message or "".join(text_chunks)).strip()

        if final_text:
            client.chat_postMessage(
                channel=channel_id,
                text=final_text,
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                text="Meeting scheduled! Check your calendar for the invite. 📅",
            )

        logger.info(f"Completed synthetic scheduling flow for user {user_id}")

    except Exception as e:
        logger.error(f"Error in send_synthetic_message: {e}", exc_info=True)

        # Try to notify user of error
        try:
            dm_response = client.conversations_open(users=[user_id])
            if dm_response.get("ok"):
                channel_id = dm_response.get("channel", {}).get("id")
                if channel_id:
                    client.chat_postMessage(
                        channel=channel_id,
                        text="Sorry, I had trouble scheduling that meeting. Please try again or ask me to find new times.",
                    )
        except Exception:
            pass
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_agent_bridge.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add slackbot/services/agent_bridge.py
git add slackbot/tests/services/test_agent_bridge.py
git commit -m "feat: add agent bridge for synthetic scheduling messages"
```

---

## Phase 4: Integration

### Task 4.1: Register Handlers in listeners.py

**Files:**
- Modify: `slackbot/listeners/listeners.py`

**Step 1: Add imports and registration**

Add to `slackbot/listeners/listeners.py`:

```python
# Add imports at top of file
from listeners.actions.proposal_actions import register as reg_proposal_actions
from listeners.views.proposal_confirm import register as reg_proposal_confirm

# Add in register_listeners function:
def register_listeners(app: App):
    # ... existing registrations ...
    reg_proposal_actions(app)
    reg_proposal_confirm(app)
```

**Step 2: Verify import works**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -c "from listeners.listeners import register_listeners; print('OK')"
```
Expected: OK

**Step 3: Commit**

```bash
git add slackbot/listeners/listeners.py
git commit -m "feat: register proposal action and view handlers"
```

---

### Task 4.2: Create Proposal Formatter for Orchestrator Output

**Files:**
- Create: `slackbot/services/proposal_formatter.py`
- Test: `slackbot/tests/services/test_proposal_formatter.py`

**Step 1: Write failing test**

Create `slackbot/tests/services/test_proposal_formatter.py`:
```python
"""Tests for proposal formatter."""
import pytest


def test_parse_orchestrator_proposals():
    """Parses orchestrator output into InteractiveProposalSet."""
    from services.proposal_formatter import parse_orchestrator_proposals

    # Sample orchestrator output (markdown format)
    orchestrator_output = '''
## Best Options

Wednesday, Jan. 29
* 2:00 – 3:00
* 4:00 – 5:00

Thursday, Jan. 30
* 10:00 – 11:00

## If We Can Move or Override Current Meetings

Friday, Jan. 31 – If your 2:00 – 3:00 *Standup* event moves to 3:00 – 4:00
* 2:00 – 3:00
'''

    proposal_set = parse_orchestrator_proposals(
        output=orchestrator_output,
        session_id="sess_test",
        user_id="U12345",
        participants=["alice@example.com", "bob@example.com"],
    )

    assert proposal_set is not None
    assert proposal_set.session_id == "sess_test"
    assert len(proposal_set.clean_proposals) == 3
    assert len(proposal_set.conflict_proposals) == 1

    # Check clean proposal structure
    first_clean = proposal_set.clean_proposals[0]
    assert first_clean.category == "clean"
    assert first_clean.index == 1

    # Check conflict proposal structure
    first_conflict = proposal_set.conflict_proposals[0]
    assert first_conflict.category in ["move", "override"]
    assert first_conflict.conflict_summary is not None


def test_handles_empty_sections():
    """Handles output with only one section."""
    from services.proposal_formatter import parse_orchestrator_proposals

    orchestrator_output = '''
## Best Options

Monday, Feb. 3
* 9:00 – 10:00
* 11:00 – 12:00
'''

    proposal_set = parse_orchestrator_proposals(
        output=orchestrator_output,
        session_id="sess_empty",
        user_id="U12345",
        participants=["alice@example.com"],
    )

    assert len(proposal_set.clean_proposals) == 2
    assert len(proposal_set.conflict_proposals) == 0


def test_generates_unique_ids():
    """Each proposal gets a unique ID."""
    from services.proposal_formatter import parse_orchestrator_proposals

    orchestrator_output = '''
## Best Options

Monday, Feb. 3
* 9:00 – 10:00
* 11:00 – 12:00
* 2:00 – 3:00
'''

    proposal_set = parse_orchestrator_proposals(
        output=orchestrator_output,
        session_id="sess_ids",
        user_id="U12345",
        participants=[],
    )

    ids = [p.id for p in proposal_set.clean_proposals]
    assert len(ids) == len(set(ids))  # All unique
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_proposal_formatter.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement proposal formatter**

Create `slackbot/services/proposal_formatter.py`:
```python
"""
Proposal formatter for converting orchestrator output to interactive proposals.

Parses the markdown-formatted scheduling orchestrator output and creates
InteractiveProposalSet for rendering in Slack.
"""
import re
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytz

from services.interactive_proposals import (
    InteractiveProposal,
    InteractiveProposalSet,
    MeetingContext,
    MovedEventInfo,
)


def parse_orchestrator_proposals(
    output: str,
    session_id: str,
    user_id: str,
    participants: List[str],
    meeting_context: Optional[MeetingContext] = None,
    timezone_str: str = "America/New_York",
) -> InteractiveProposalSet:
    """
    Parse orchestrator markdown output into InteractiveProposalSet.

    Args:
        output: Markdown output from scheduling orchestrator
        session_id: Session ID for tracking
        user_id: Slack user ID
        participants: List of participant email addresses
        meeting_context: Optional meeting context (title, description hints)
        timezone_str: Timezone for date parsing

    Returns:
        InteractiveProposalSet ready for rendering
    """
    clean_proposals: List[InteractiveProposal] = []
    conflict_proposals: List[InteractiveProposal] = []

    # Split into sections
    sections = re.split(r'^##\s+', output, flags=re.MULTILINE)

    proposal_index = 1
    current_year = datetime.now().year
    tz = pytz.timezone(timezone_str)

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split('\n')
        header = lines[0].strip()
        content = '\n'.join(lines[1:])

        is_conflict_section = "move" in header.lower() or "override" in header.lower()

        # Parse proposals from content
        current_day = None
        current_conflict_info = None

        for line in content.split('\n'):
            line = line.strip()

            if not line:
                continue

            # Check for day header (e.g., "Wednesday, Jan. 29")
            day_match = re.match(
                r'^(\w+),?\s+(\w+\.?)\s+(\d+)',
                line
            )
            if day_match:
                weekday, month, day = day_match.groups()
                current_day = (weekday, month, int(day))

                # Check for conflict info in the same line
                conflict_match = re.search(
                    r'–\s+(.*?)(?:\*([^*]+)\*)?.*?moves?\s+to',
                    line,
                    re.IGNORECASE
                )
                if conflict_match:
                    current_conflict_info = line.split('–', 1)[1].strip() if '–' in line else None
                else:
                    current_conflict_info = None
                continue

            # Check for time slot (e.g., "* 2:00 – 3:00")
            time_match = re.match(
                r'^\*?\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})',
                line
            )
            if time_match and current_day:
                start_time, end_time = time_match.groups()

                # Parse times
                weekday, month, day = current_day
                start_utc, end_utc = _parse_times_to_utc(
                    month, day, start_time, end_time,
                    current_year, tz
                )

                if start_utc and end_utc:
                    # Generate label
                    label = _format_short_label(weekday, start_time, end_time)

                    # Create proposal
                    proposal = InteractiveProposal(
                        id=f"prop_{uuid.uuid4().hex[:8]}",
                        index=proposal_index,
                        label=label,
                        start_utc=start_utc,
                        end_utc=end_utc,
                        participants=participants,
                        category="move" if is_conflict_section else "clean",
                        conflict_summary=current_conflict_info if is_conflict_section else None,
                    )

                    if is_conflict_section:
                        conflict_proposals.append(proposal)
                    else:
                        clean_proposals.append(proposal)

                    proposal_index += 1

    return InteractiveProposalSet(
        session_id=session_id,
        user_id=user_id,
        clean_proposals=clean_proposals,
        conflict_proposals=conflict_proposals,
        meeting_context=meeting_context or MeetingContext(),
        show_conflicts_expanded=len(clean_proposals) == 0,
    )


def _parse_times_to_utc(
    month: str,
    day: int,
    start_time: str,
    end_time: str,
    year: int,
    tz: pytz.tzinfo,
) -> Tuple[Optional[str], Optional[str]]:
    """Parse time strings to UTC ISO format."""
    try:
        # Map month abbreviations
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
            'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
            'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        }

        month_lower = month.lower().replace('.', '')
        month_num = month_map.get(month_lower[:3], 1)

        # Parse start time
        start_parts = start_time.split(':')
        start_hour = int(start_parts[0])
        start_minute = int(start_parts[1]) if len(start_parts) > 1 else 0

        # Parse end time
        end_parts = end_time.split(':')
        end_hour = int(end_parts[0])
        end_minute = int(end_parts[1]) if len(end_parts) > 1 else 0

        # Assume business hours (adjust PM if hour < 8)
        if start_hour < 8:
            start_hour += 12
        if end_hour < 8:
            end_hour += 12
        if end_hour < start_hour:
            end_hour += 12

        # Create datetime objects
        start_dt = tz.localize(datetime(year, month_num, day, start_hour, start_minute))
        end_dt = tz.localize(datetime(year, month_num, day, end_hour, end_minute))

        # Handle year rollover
        now = datetime.now(tz)
        if start_dt < now - timedelta(days=30):
            start_dt = start_dt.replace(year=year + 1)
            end_dt = end_dt.replace(year=year + 1)

        # Convert to UTC
        start_utc = start_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        return start_utc, end_utc

    except Exception:
        return None, None


def _format_short_label(weekday: str, start_time: str, end_time: str) -> str:
    """Format a short label like 'Wed 2-3pm'."""
    # Get abbreviated weekday
    weekday_abbrev = weekday[:3]

    # Format times
    start_hour = int(start_time.split(':')[0])
    end_hour = int(end_time.split(':')[0])

    # Determine AM/PM
    start_period = "am" if start_hour < 12 else "pm"
    end_period = "am" if end_hour < 12 else "pm"

    # Convert to 12-hour
    if start_hour > 12:
        start_hour -= 12
    if end_hour > 12:
        end_hour -= 12

    # Omit period on start if same as end
    if start_period == end_period:
        return f"{weekday_abbrev} {start_hour}-{end_hour}{end_period}"
    else:
        return f"{weekday_abbrev} {start_hour}{start_period}-{end_hour}{end_period}"
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA/slackbot && python -m pytest tests/services/test_proposal_formatter.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add slackbot/services/proposal_formatter.py
git add slackbot/tests/services/test_proposal_formatter.py
git commit -m "feat: add proposal formatter for orchestrator output parsing"
```

---

### Task 4.3: Integrate with Letta Stream Detection

**Files:**
- Modify: `slackbot/listeners/messages/message_im_hybrid.py`

**Step 1: Add detection for scheduling proposals**

Add logic to detect when Letta returns scheduling proposals and trigger interactive rendering.

This task involves modifying `_handle_dm` in `message_im_hybrid.py` to:
1. Detect when the response contains `[VERBATIM_USER_OUTPUT]` markers
2. Parse the scheduling proposals
3. Store in proposal cache
4. Render interactive buttons alongside the text

**Changes to add in `message_im_hybrid.py`:**

After the streamer collects the response, before posting to Slack:

```python
# Check if response contains scheduling proposals
if "[VERBATIM_USER_OUTPUT]" in final_text:
    try:
        from services.proposal_formatter import parse_orchestrator_proposals
        from services.proposal_cache import proposal_cache
        from adapters.slack_proposal_adapter import render_proposal_blocks

        # Generate a unique session ID
        import uuid
        session_id = f"sess_{uuid.uuid4().hex[:12]}"

        # Parse proposals from the response
        proposal_set = parse_orchestrator_proposals(
            output=final_text,
            session_id=session_id,
            user_id=user_id,
            participants=[],  # Will be populated from context
        )

        # Store in cache
        proposal_cache.store(session_id, proposal_set)

        # Render interactive blocks
        proposal_blocks = render_proposal_blocks(proposal_set)

        # Post text response first
        client.chat_postMessage(
            channel=working_channel,
            text=final_text,
        )

        # Then post interactive buttons
        if proposal_blocks:
            client.chat_postMessage(
                channel=working_channel,
                text="Select a time:",
                blocks=proposal_blocks,
            )

        logger.info(f"Posted interactive scheduling proposals for session {session_id}")

    except Exception as e:
        logger.warning(f"Could not parse scheduling proposals: {e}")
        # Fall through to regular posting
```

**Step 2: Test manually**

Run a scheduling request through Slack and verify buttons appear.

**Step 3: Commit**

```bash
git add slackbot/listeners/messages/message_im_hybrid.py
git commit -m "feat: integrate interactive proposal rendering with DM handler"
```

---

## Phase 5: End-to-End Testing

### Task 5.1: Manual Integration Test

**Checklist:**

1. [ ] Start all services: `docker-compose up -d`
2. [ ] Send scheduling request via Slack DM
3. [ ] Verify buttons appear below scheduling text
4. [ ] Click a proposal button
5. [ ] Verify confirmation modal appears with pre-filled title
6. [ ] Submit the modal
7. [ ] Verify agent responds confirming the scheduling
8. [ ] Check calendar for the created event

### Task 5.2: Error Handling Verification

**Checklist:**

1. [ ] Test expired proposals (wait 1+ hour, click button)
2. [ ] Test expand button for conflict proposals
3. [ ] Test modal cancellation (no side effects)
4. [ ] Test Slackbot restart (proposals lost, graceful message)

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| **Buttons render** | Scheduling response shows clickable buttons |
| **Modal opens** | Clicking button opens pre-filled confirmation modal |
| **Agent schedules** | Submitting modal triggers agent to call create_calendar_event |
| **Conversational** | Agent responds naturally confirming the scheduling |
| **Expiry handled** | Expired proposals show friendly re-ask message |
| **Mobile works** | Buttons and modals work on Slack mobile |

---

## Execution Order

**Phase 1 (Parallel - 2 agents):**
- Task 1.1: Create Data Models
- Task 1.2: Create Proposal Cache

**Phase 2 (Parallel - 2 agents):**
- Task 2.1: Create Slack Block Kit Adapter
- Task 2.2: Create Action Handler Skeleton

**Code Review Checkpoint**

**Phase 3 (Parallel - 2 agents):**
- Task 3.1: Add Modal Submission Handler
- Task 3.2: Create Agent Bridge

**Phase 4 (Sequential):**
- Task 4.1: Register Handlers
- Task 4.2: Create Proposal Formatter
- Task 4.3: Integrate with Letta Stream Detection

**Phase 5 (Manual):**
- Task 5.1: Manual Integration Test
- Task 5.2: Error Handling Verification
