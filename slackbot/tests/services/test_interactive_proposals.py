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
