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
