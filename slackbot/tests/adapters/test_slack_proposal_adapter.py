"""Tests for Slack Block Kit proposal adapter."""
import pytest


def test_render_proposal_buttons_clean():
    """Renders clean proposals as buttons grouped by day."""
    from adapters.slack_proposal_adapter import render_proposal_blocks
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    proposal = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Mon 2-3pm",
        start_utc="2026-01-28T19:00:00Z",  # 2pm ET
        end_utc="2026-01-28T20:00:00Z",    # 3pm ET
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

    # Should have header block for "Best Options" section and date headers
    header_blocks = [b for b in blocks if b.get("type") == "header"]
    header_texts = [b.get("text", {}).get("text", "") for b in header_blocks]
    assert any("Best Options" in t for t in header_texts)
    assert any("Jan" in t or "Wed" in t for t in header_texts)

    # Buttons should be in actions blocks
    actions_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions_blocks) > 0

    # Find the button
    button = actions_blocks[0]["elements"][0]
    assert button["action_id"] == "schedule_proposal_select_prop_001"
    assert button["value"] == "sess_abc123:prop_001"
    # Button text should be time range format
    assert "-" in button["text"]["text"]  # e.g., "2:00-3:00"


def test_render_conflict_proposals_with_modal_button():
    """Conflict proposals show modal button when clean options exist."""
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
        conflict_type="multi_person",  # Moving standup is multi-person
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        clean_proposals=[clean_prop],
        conflict_proposals=[conflict_prop],
        show_conflicts_expanded=False,
    )

    blocks = render_proposal_blocks(proposal_set)

    # Should have button to open modal with override/move/share text
    button_found = False
    button_text = ""
    for b in blocks:
        if b.get("type") == "actions":
            for elem in b.get("elements", []):
                if elem.get("action_id") == "open_options_modal":
                    button_found = True
                    button_text = elem.get("text", {}).get("text", "")
                    break

    assert button_found, "Expected 'open_options_modal' button"
    assert "override" in button_text.lower() or "move" in button_text.lower() or "share" in button_text.lower()


def test_render_only_conflict_proposals():
    """When only conflict options exist, show button to open modal."""
    from adapters.slack_proposal_adapter import render_proposal_blocks
    from services.interactive_proposals import (
        InteractiveProposal,
        InteractiveProposalSet,
    )

    conflict_prop = InteractiveProposal(
        id="prop_001",
        index=1,
        label="Tue 10-11am",
        start_utc="2026-01-29T10:00:00Z",
        end_utc="2026-01-29T11:00:00Z",
        participants=["alice@example.com"],
        category="move",
        conflict_summary="moves 'Standup' to 3pm",
        conflict_type="multi_person",  # Moving standup is multi-person
    )

    proposal_set = InteractiveProposalSet(
        session_id="sess_abc123",
        user_id="U12345",
        conflict_proposals=[conflict_prop],
        show_conflicts_expanded=True,  # No clean options
    )

    blocks = render_proposal_blocks(proposal_set)

    # Should have button to open modal (since we have conflict proposals)
    actions_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions_blocks) > 0

    # Find the open modal button
    button_found = False
    for b in actions_blocks:
        for elem in b.get("elements", []):
            if elem.get("action_id") == "open_options_modal":
                button_found = True
                break
    assert button_found, "Expected 'open_options_modal' button"


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
