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
    # Should have day name (either from label or formatted from UTC)
    assert any(day in message for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])

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
