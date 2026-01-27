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
