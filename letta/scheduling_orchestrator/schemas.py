"""
Pydantic schemas for scheduling orchestration tool.

Defines the input/output data structures for the orchestrate_scheduling tool.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Represents a calendar event."""
    
    id: str = Field(..., description="Unique identifier for the event")
    title: str = Field(..., description="Event title or summary")
    start: str = Field(..., description="Event start time in ISO 8601 format (UTC)")
    end: str = Field(..., description="Event end time in ISO 8601 format (UTC)")
    locked: bool = Field(default=False, description="If True, event cannot be moved (hard constraint)")
    protected: bool = Field(default=False, description="If True, event should not be moved if possible (soft constraint)")
    flexible: bool = Field(default=True, description="If True, event can be moved to accommodate new meetings")
    owner: Optional[str] = Field(default=None, description="Participant ID who owns this event")
    location: Optional[str] = Field(default=None, description="Event location if available")
    description: Optional[str] = Field(default=None, description="Event description if available")
    
    class Config:
        # Ensure additionalProperties is false in JSON schema
        json_schema_extra = {
            "additionalProperties": False
        }


class EventsByParticipant(BaseModel):
    """Dictionary mapping participant IDs to their calendar events.
    
    This is a wrapper to ensure proper JSON schema generation with additionalProperties: false.
    In practice, this will be used as a dict[str, List[Event]].
    """
    
    class Config:
        # This model is just for schema generation - actual usage is dict[str, List[dict]]
        extra = "forbid"
        json_schema_extra = {
            "additionalProperties": False,
            "type": "object",
            "description": "Dictionary mapping participant IDs (strings) to lists of calendar events. Each event is a dict with keys: id, title, start, end, locked, protected, flexible."
        }


class ContextJSON(BaseModel):
    """Optional scheduling context and preferences.
    
    This is a wrapper to ensure proper JSON schema generation with additionalProperties: false.
    In practice, this will be used as a dict[str, Any].
    """
    
    class Config:
        # This model is just for schema generation - actual usage is dict[str, Any]
        extra = "allow"  # Allow extra fields since context_json is flexible
        json_schema_extra = {
            "additionalProperties": True,  # Context is flexible, but we document the structure
            "type": "object",
            "description": "Optional dictionary containing timeframe, participants, and policy preferences"
        }


class ParticipantPreference(BaseModel):
    """Preferences specific to a participant."""
    
    participant_id: str = Field(..., description="Participant ID (email address) this preference applies to")
    preferred_times: Optional[List[str]] = Field(default=None, description="Preferred time slots for this participant (ISO 8601 UTC)")
    preferred_days: Optional[List[str]] = Field(default=None, description="Preferred days of week for this participant (e.g., ['Monday', 'Tuesday'])")
    avoid_times: Optional[List[str]] = Field(default=None, description="Time slots to avoid for this participant (ISO 8601 UTC)")
    avoid_days: Optional[List[str]] = Field(default=None, description="Days of week to avoid for this participant (e.g., ['Friday'])")
    avoid_categories: Optional[List[str]] = Field(default=None, description="Event categories to avoid (e.g., ['lunch', 'meetings'])")
    flexibility_notes: Optional[str] = Field(default=None, description="Notes about flexibility (e.g., 'my meetings are flexible')")


class SchedulingProblem(BaseModel):
    """Encodes the scheduling request extracted from natural language."""
    
    participants: List[str] = Field(..., description="List of participant IDs required for the meeting")
    duration_minutes: int = Field(..., description="Required meeting duration in minutes")
    time_window_start: Optional[str] = Field(default=None, description="Earliest allowed start time (ISO 8601 UTC)")
    time_window_end: Optional[str] = Field(default=None, description="Latest allowed end time (ISO 8601 UTC)")
    preferred_times: Optional[List[str]] = Field(default=None, description="Preferred time slots (ISO 8601 UTC)")
    preferred_days: Optional[List[str]] = Field(default=None, description="Preferred days of week (e.g., ['Monday', 'Tuesday'])")
    participant_preferences: Optional[List[ParticipantPreference]] = Field(default=None, description="Preferences specific to individual participants")
    avoid_times: Optional[List[str]] = Field(default=None, description="Time slots to avoid (request-level, ISO 8601 UTC)")
    avoid_days: Optional[List[str]] = Field(default=None, description="Days of week to avoid (request-level, e.g., ['Friday'])")
    title: Optional[str] = Field(default=None, description="Proposed meeting title")
    location: Optional[str] = Field(default=None, description="Proposed meeting location")
    min_gap_minutes: Optional[int] = Field(default=0, description="Minimum gap between meetings in minutes (default: 0)")
    allow_off_hours: bool = Field(default=False, description="Allow scheduling outside work hours if needed")
    # Rescheduling metadata (optional, only present for rescheduling requests)
    is_rescheduling: Optional[bool] = Field(default=None, description="True if this is a rescheduling request (finding new time for existing meeting)")
    event_identifiers: Optional[Dict[str, Any]] = Field(default=None, description="Extracted event identifiers for rescheduling: participant_names (list), dates (list), times (list), titles (list). Used to match against existing events.")


class MovedEvent(BaseModel):
    """Details about an event that needs to be moved to accommodate the proposal."""
    
    owner: str = Field(..., description="Participant ID who owns the event")
    event_id: str = Field(..., description="Original event ID")
    old_start: str = Field(..., description="Original start time (ISO 8601 UTC)")
    new_start: str = Field(..., description="New start time (ISO 8601 UTC)")
    old_end: str = Field(..., description="Original end time (ISO 8601 UTC)")
    new_end: str = Field(..., description="New end time (ISO 8601 UTC)")
    shift_minutes: int = Field(..., description="Number of minutes the event was shifted")


class FreeBlockStats(BaseModel):
    """Statistics about unbroken free/solo-event blocks on requester's calendar."""
    
    free_block_score: float = Field(default=0.0, description="Overall free-block score (higher is better)")
    total_effective_hours: float = Field(default=0.0, description="Total effective free hours across all days")
    avg_block_hours: float = Field(default=0.0, description="Average unbroken block length in hours")
    max_block_hours: float = Field(default=0.0, description="Maximum unbroken block length in hours")
    median_block_hours: float = Field(default=0.0, description="Median unbroken block length in hours")


class ObjectiveScores(BaseModel):
    """Breakdown of optimization objective values."""
    
    moved_minutes: int = Field(..., description="Total minutes that existing events must be moved")
    focus_block_bonus: int = Field(default=0, description="Bonus points for creating long focus blocks (in minutes)")
    preference_penalty: int = Field(default=0, description="Penalty for deviating from preferences")
    protected_events_moved: int = Field(default=0, description="Number of protected events that were moved")
    priority_score: float = Field(default=0.0, description="Overall priority score (higher is better). Reflects attendee count, internal-only status, move distance, etc.")


class Proposal(BaseModel):
    """A proposed meeting slot with details."""
    
    title: str = Field(..., description="Meeting title")
    participants: List[str] = Field(..., description="List of participant email addresses or IDs")
    start_utc: str = Field(..., description="Proposed start time in ISO 8601 format (UTC)")
    end_utc: str = Field(..., description="Proposed end time in ISO 8601 format (UTC)")
    location: Optional[str] = Field(default=None, description="Proposed location")
    notes_for_invite: Optional[str] = Field(default=None, description="Notes to include in calendar invite")
    moved_events: List[MovedEvent] = Field(default_factory=list, description="Events that need to be moved")
    objective_scores: ObjectiveScores = Field(..., description="Optimization objective scores for this proposal")
    free_block_stats: Optional[FreeBlockStats] = Field(default=None, description="Free-block statistics for requester's calendar")
    proposal_id: Optional[str] = Field(default=None, description="Unique identifier for this proposal (for cross-referencing)")
    category: Optional[str] = Field(default=None, description="Category: 'zero_conflict' | 'single_move' | 'solo_override' | 'multi_move'")
    rank: Optional[int] = Field(default=None, description="Overall rank (1 = best)")
    preference_score: Optional[float] = Field(default=None, description="Preference score (higher = better)")
    overridden_event_ids: Optional[List[str]] = Field(default=None, description="List of event IDs for solo events that this proposal overrides (for solo_override proposals)")
    # Rescheduling metadata (optional, only present for rescheduling operations)
    original_event_id: Optional[str] = Field(default=None, description="ID of the original event being rescheduled (only present for rescheduling proposals)")
    original_event_details: Optional[Dict[str, Any]] = Field(default=None, description="Original event details: title, start_utc, end_utc, participants, location (only present for rescheduling proposals)")


class Relaxation(BaseModel):
    """A suggested relaxation to make an infeasible request satisfiable."""
    
    description: str = Field(..., description="Human-readable description of the relaxation")
    expected_impact: str = Field(..., description="Expected impact of this relaxation (e.g., 'high', 'medium', 'low')")
    policy_change: Dict[str, Any] = Field(..., description="Specific policy changes needed (e.g., {'min_gap_minutes': 10})")
    rank: int = Field(..., description="Ranking of this relaxation (1 = most recommended)")


class DebugInfo(BaseModel):
    """Debug information for troubleshooting."""
    
    asp_stats: Optional[Dict[str, Any]] = Field(default=None, description="clingo ASP solver statistics")
    extraction_time_ms: Optional[int] = Field(default=None, description="Time taken for DSPy extraction in milliseconds")
    normalization_time_ms: Optional[int] = Field(default=None, description="Time taken for event normalization in milliseconds")
    solve_time_ms: Optional[int] = Field(default=None, description="Time taken for ASP solving in milliseconds")
    total_time_ms: Optional[int] = Field(default=None, description="Total execution time in milliseconds")
    facts_generated: Optional[int] = Field(default=None, description="Number of ASP facts generated")
    slots_considered: Optional[int] = Field(default=None, description="Number of time slots in the planning horizon")
    input_summary: Optional[Dict[str, Any]] = Field(default=None, description="Summary of input parameters (utterance preview, participant counts, etc.)")
    total_busy_slots: Optional[int] = Field(default=None, description="Total number of busy slots across all participants")
    asp_program_lines: Optional[int] = Field(default=None, description="Number of lines in the generated ASP program")
    asp_facts_count: Optional[int] = Field(default=None, description="Number of fact lines in the ASP program")
    asp_program_size_chars: Optional[int] = Field(default=None, description="Size of ASP program in characters")
    horizon_reduced: Optional[bool] = Field(default=None, description="Whether the planning horizon was reduced to fit within ASP limits")
    original_slots: Optional[int] = Field(default=None, description="Original number of slots before reduction")
    reduced_slots: Optional[int] = Field(default=None, description="Number of slots after reduction")
    horizon_reduction_error: Optional[str] = Field(default=None, description="Error message if horizon reduction failed")
    free_slots_found: Optional[int] = Field(default=None, description="Number of free slots found by pre-filtering (inverse approach)")
    free_slots_ratio: Optional[float] = Field(default=None, description="Ratio of free slots to total slots (for debugging)")
    multi_shot_phase: Optional[int] = Field(default=None, description="Multi-shot phase that succeeded (1=minimal, 2=+work hours, 3=+min gap)")


class FormattedProposal(BaseModel):
    """User-facing formatted proposal display."""
    
    rank: int = Field(..., description="Ranking of this proposal (1 = best)")
    category: str = Field(..., description="Category: 'best_options' | 'with_moves' | 'with_overrides'")
    display_text: str = Field(..., description="Pre-formatted detailed display text")
    short_summary: str = Field(..., description="One-line summary")
    move_summary: Optional[str] = Field(default=None, description="Human-readable move description")
    override_summary: Optional[str] = Field(default=None, description="Human-readable override description")


class CategoryInfo(BaseModel):
    """Information about a proposal category."""
    
    count: int = Field(..., description="Number of proposals in this category")
    description: str = Field(..., description="Human-readable description of the category")


class EventGroup(BaseModel):
    """Group of proposals by moved event."""
    
    event_id: str = Field(..., description="Event ID")
    event_title: str = Field(..., description="Human-readable event title")
    owner: str = Field(..., description="Participant ID who owns the event")
    options: List[int] = Field(..., description="List of proposal ranks in this group")


class UserDisplay(BaseModel):
    """User-facing formatted content for display."""
    
    summary: str = Field(..., description="High-level summary")
    explanation: str = Field(..., description="Human-readable explanation")
    formatted_proposals: List[FormattedProposal] = Field(default_factory=list, description="Pre-formatted proposals")
    categories: Dict[str, CategoryInfo] = Field(default_factory=dict, description="Category information")
    grouped_by_event: Optional[Dict[str, List[EventGroup]]] = Field(default=None, description="Proposals grouped by moved event")
    refined_display: Optional[str] = Field(default=None, description="Refined user-facing formatted text with grouped proposals by day")


class EventMetadata(BaseModel):
    """Metadata about an event referenced in proposals."""
    
    title: str = Field(..., description="Event title")
    owner: str = Field(..., description="Participant ID who owns the event")
    start_utc: str = Field(..., description="Original start time (ISO 8601 UTC)")
    end_utc: str = Field(..., description="Original end time (ISO 8601 UTC)")
    locked: bool = Field(..., description="Whether event is locked")
    protected: bool = Field(..., description="Whether event is protected")
    flexible: bool = Field(..., description="Whether event is flexible")
    number_of_attendees: int = Field(default=0, description="Number of attendees")
    internal_only: bool = Field(default=True, description="Whether event is internal-only")
    human_readable: str = Field(..., description="Human-readable event description")


class RankingFactor(BaseModel):
    """A factor contributing to a proposal's ranking."""
    
    factor: str = Field(..., description="Factor name (e.g., 'zero_conflict', 'free_block_score')")
    value: Optional[float] = Field(default=None, description="Factor value if applicable")
    impact: str = Field(..., description="Impact level: 'high' | 'medium' | 'low'")


class ProposalComparison(BaseModel):
    """Comparison of a proposal with others."""
    
    better_than: List[str] = Field(default_factory=list, description="Proposal IDs this ranks better than")
    worse_than: List[str] = Field(default_factory=list, description="Proposal IDs this ranks worse than")
    tie_breakers: List[str] = Field(default_factory=list, description="Factors used as tie-breakers")


class RankingRationale(BaseModel):
    """Rationale for why a proposal is ranked as it is."""
    
    primary_factors: List[RankingFactor] = Field(default_factory=list, description="Primary ranking factors")
    comparison: Optional[ProposalComparison] = Field(default=None, description="Comparison with other proposals")


class OptimizationSummary(BaseModel):
    """Summary of optimization results."""
    
    total_proposals_found: int = Field(..., description="Total number of proposals")
    zero_conflict_count: int = Field(..., description="Number of zero-conflict proposals")
    single_move_count: int = Field(..., description="Number of single-move proposals")
    solo_override_count: int = Field(..., description="Number of solo-override proposals")
    multi_move_count: int = Field(..., description="Number of multi-move proposals")
    best_score: float = Field(..., description="Best free-block score")
    score_range: Dict[str, float] = Field(..., description="Score range: {'min': float, 'max': float}")
    preference_match_count: int = Field(default=0, description="Number of proposals matching user preferences")
    work_hours_compliance: str = Field(..., description="'full' | 'partial' | 'none'")


class ConstraintsApplied(BaseModel):
    """Summary of constraints that were applied."""
    
    work_hours_enforced: bool = Field(..., description="Whether work hours were enforced")
    min_gap_minutes: int = Field(..., description="Minimum gap in minutes")
    locked_events_blocked: int = Field(..., description="Number of locked events that blocked slots")
    preferences_applied: List[str] = Field(default_factory=list, description="List of preferences applied")


class AgentData(BaseModel):
    """Agent-facing structured data for reasoning."""
    
    proposals: List[Proposal] = Field(default_factory=list, description="Full structured proposals")
    event_registry: Dict[str, EventMetadata] = Field(default_factory=dict, description="Map event IDs to metadata")
    ranking_rationale: Dict[str, RankingRationale] = Field(default_factory=dict, description="Rationale for proposal rankings")
    optimization_summary: Optional[OptimizationSummary] = Field(default=None, description="Optimization summary")
    constraints_applied: Optional[ConstraintsApplied] = Field(default=None, description="Constraints that were applied")


class CrossReferenceMapping(BaseModel):
    """Mapping between user_display and agent_data."""
    
    rank_to_proposal_id: Dict[int, str] = Field(default_factory=dict, description="Map rank to proposal ID")
    proposal_id_to_rank: Dict[str, int] = Field(default_factory=dict, description="Map proposal ID to rank")
    event_id_to_proposals: Dict[str, List[str]] = Field(default_factory=dict, description="Map event ID to proposal IDs")
    category_to_proposals: Dict[str, List[str]] = Field(default_factory=dict, description="Map category to proposal IDs")


class ResponseEnvelope(BaseModel):
    """Complete tool response envelope."""
    
    status: Literal["ok", "unsat", "bad_input"] = Field(..., description="Status of the scheduling request")
    proposals: List[Proposal] = Field(default_factory=list, description="List of proposed meeting slots (backward compatibility)")
    explanation: str = Field(..., description="Human-readable explanation of the result (backward compatibility)")
    relaxations: Optional[List[Relaxation]] = Field(default=None, description="Suggested relaxations if status is 'unsat'")
    debug: Optional[DebugInfo] = Field(default=None, description="Debug information for troubleshooting")
    error_message: Optional[str] = Field(default=None, description="Error message if status is 'bad_input'")
    # Dual-format fields (new)
    user_display: Optional[UserDisplay] = Field(default=None, description="User-facing formatted content")
    agent_data: Optional[AgentData] = Field(default=None, description="Agent-facing structured data")
    mapping: Optional[CrossReferenceMapping] = Field(default=None, description="Cross-reference mapping between formats")

