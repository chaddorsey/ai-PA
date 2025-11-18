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


class SchedulingProblem(BaseModel):
    """Encodes the scheduling request extracted from natural language."""
    
    participants: List[str] = Field(..., description="List of participant IDs required for the meeting")
    duration_minutes: int = Field(..., description="Required meeting duration in minutes")
    time_window_start: Optional[str] = Field(default=None, description="Earliest allowed start time (ISO 8601 UTC)")
    time_window_end: Optional[str] = Field(default=None, description="Latest allowed end time (ISO 8601 UTC)")
    preferred_times: Optional[List[str]] = Field(default=None, description="Preferred time slots (ISO 8601 UTC)")
    preferred_days: Optional[List[str]] = Field(default=None, description="Preferred days of week (e.g., ['Monday', 'Tuesday'])")
    title: Optional[str] = Field(default=None, description="Proposed meeting title")
    location: Optional[str] = Field(default=None, description="Proposed meeting location")
    min_gap_minutes: Optional[int] = Field(default=15, description="Minimum gap between meetings in minutes")
    allow_off_hours: bool = Field(default=False, description="Allow scheduling outside work hours if needed")


class MovedEvent(BaseModel):
    """Details about an event that needs to be moved to accommodate the proposal."""
    
    owner: str = Field(..., description="Participant ID who owns the event")
    event_id: str = Field(..., description="Original event ID")
    old_start: str = Field(..., description="Original start time (ISO 8601 UTC)")
    new_start: str = Field(..., description="New start time (ISO 8601 UTC)")
    old_end: str = Field(..., description="Original end time (ISO 8601 UTC)")
    new_end: str = Field(..., description="New end time (ISO 8601 UTC)")
    shift_minutes: int = Field(..., description="Number of minutes the event was shifted")


class ObjectiveScores(BaseModel):
    """Breakdown of optimization objective values."""
    
    moved_minutes: int = Field(..., description="Total minutes that existing events must be moved")
    focus_block_bonus: int = Field(default=0, description="Bonus points for creating long focus blocks (in minutes)")
    preference_penalty: int = Field(default=0, description="Penalty for deviating from preferences")
    protected_events_moved: int = Field(default=0, description="Number of protected events that were moved")


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


class ResponseEnvelope(BaseModel):
    """Complete tool response envelope."""
    
    status: Literal["ok", "unsat", "bad_input"] = Field(..., description="Status of the scheduling request")
    proposals: List[Proposal] = Field(default_factory=list, description="List of proposed meeting slots (typically one)")
    explanation: str = Field(..., description="Human-readable explanation of the result")
    relaxations: Optional[List[Relaxation]] = Field(default=None, description="Suggested relaxations if status is 'unsat'")
    debug: Optional[DebugInfo] = Field(default=None, description="Debug information for troubleshooting")
    error_message: Optional[str] = Field(default=None, description="Error message if status is 'bad_input'")

