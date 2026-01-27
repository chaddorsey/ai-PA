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
