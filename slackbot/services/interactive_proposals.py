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

    # Conflict categorization for UI grouping
    # "single_solo_overlap" = overlaps one single-person event
    # "multiple_solo_overlap" = overlaps more than one single-person event
    # "multi_person" = moves multi-attendee meeting or affects multiple people
    # Legacy "solo_overlap" maps to "single_solo_overlap"
    conflict_type: Optional[str] = None


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

    def get_single_solo_overlap_proposals(self) -> List[InteractiveProposal]:
        """Get conflict proposals that overlap one single-person event."""
        return [
            p for p in self.conflict_proposals
            if p.conflict_type in ("single_solo_overlap", "solo_overlap")  # Include legacy
        ]

    def get_multiple_solo_overlap_proposals(self) -> List[InteractiveProposal]:
        """Get conflict proposals that overlap more than one single-person event."""
        return [p for p in self.conflict_proposals if p.conflict_type == "multiple_solo_overlap"]

    def get_multi_person_proposals(self) -> List[InteractiveProposal]:
        """Get conflict proposals involving multi-attendee meeting moves."""
        return [p for p in self.conflict_proposals if p.conflict_type == "multi_person"]

    # Legacy compatibility
    def get_solo_overlap_proposals(self) -> List[InteractiveProposal]:
        """Legacy: Get all solo overlap proposals (single + multiple)."""
        return self.get_single_solo_overlap_proposals() + self.get_multiple_solo_overlap_proposals()
