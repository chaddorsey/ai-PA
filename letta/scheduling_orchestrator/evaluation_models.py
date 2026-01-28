"""Data models for time window evaluation."""
from dataclasses import dataclass, field
from datetime import date, time, datetime
from typing import List, Optional


@dataclass
class TimeRange:
    """A time range within a single day."""
    start: time
    end: time


@dataclass
class ProposedWindow:
    """A proposed meeting time window from external party."""
    date: date
    start_time: time  # Start of available window
    end_time: time    # End of available window
    exclusions: List[TimeRange] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ConflictInfo:
    """Information about a calendar conflict."""
    participant: str       # Email of person with conflict
    event_title: str       # Title of conflicting event
    event_time: str        # Human-readable time range
    event_property: str    # locked/protected/flexible/transparent


@dataclass
class EvaluatedSlot:
    """A concrete time slot that has been evaluated."""
    start: datetime
    end: datetime
    category: str          # "clean" | "solo_adjust" | "multi_adjust"
    conflicts: List[ConflictInfo] = field(default_factory=list)
    score: float = 0.0


@dataclass
class EvaluationResult:
    """Complete result of evaluating proposed windows."""
    clean_slots: List[EvaluatedSlot] = field(default_factory=list)
    solo_adjust_slots: List[EvaluatedSlot] = field(default_factory=list)
    multi_adjust_slots: List[EvaluatedSlot] = field(default_factory=list)
    no_availability_windows: List[str] = field(default_factory=list)
