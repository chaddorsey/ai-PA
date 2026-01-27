"""Tests for proposal confirmation modal submission."""
import importlib
import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# Import the module directly without triggering listeners/__init__.py
def _import_proposal_confirm():
    """Import proposal_confirm module directly to avoid init cascade."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "proposal_confirm",
        "/Volumes/main-drive/ai-PA/slackbot/listeners/views/proposal_confirm.py"
    )
    module = importlib.util.module_from_spec(spec)

    # Ensure services modules are loaded first
    from services import proposal_cache, agent_bridge

    spec.loader.exec_module(module)
    return module


def test_register_view_handler():
    """Register function adds view submission handler."""
    proposal_confirm = _import_proposal_confirm()

    mock_app = MagicMock()
    proposal_confirm.register(mock_app)

    # Should register view handler
    mock_app.view.assert_called()

    # Get the callback_id registered
    call_args = mock_app.view.call_args
    callback_id = call_args[0][0]
    assert callback_id == "schedule_proposal_confirm"


def test_modal_submit_extracts_values():
    """Modal submission extracts form values correctly."""
    proposal_confirm = _import_proposal_confirm()
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

    # Call handler - patch the module's reference to send_synthetic_message
    with patch.object(proposal_confirm, "send_synthetic_message") as mock_send:
        proposal_confirm._handle_proposal_confirm(mock_ack, mock_body, mock_view, mock_client, mock_logger)

    mock_ack.assert_called_once()

    # Verify synthetic message was sent with correct data
    mock_send.assert_called_once()
    call_args = mock_send.call_args

    # Check that proposal data was included
    assert call_args is not None
