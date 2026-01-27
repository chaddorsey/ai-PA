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
