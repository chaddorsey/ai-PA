"""Tests for proposal action handlers."""
import pytest
import sys
import importlib.util
from unittest.mock import MagicMock, patch


def _import_proposal_actions():
    """Import proposal_actions directly without triggering listeners/__init__.py."""
    spec = importlib.util.spec_from_file_location(
        "proposal_actions",
        "/Volumes/main-drive/ai-PA/slackbot/listeners/actions/proposal_actions.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["proposal_actions"] = module
    spec.loader.exec_module(module)
    return module


def test_register_adds_handlers():
    """Register function adds action handlers to app."""
    proposal_actions = _import_proposal_actions()
    register = proposal_actions.register

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
    proposal_actions = _import_proposal_actions()
    _handle_proposal_select = proposal_actions._handle_proposal_select
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
    proposal_actions = _import_proposal_actions()
    _handle_proposal_select = proposal_actions._handle_proposal_select

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
