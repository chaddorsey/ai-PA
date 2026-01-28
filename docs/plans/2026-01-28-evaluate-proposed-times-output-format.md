# Evaluate Proposed Times Output Format Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Enhance `evaluate_proposed_times` tool output to match scheduling orchestrator format with unified ranking, VERBATIM markers, and Slack-compatible interactive data.

**Architecture:** Add unified slot ranker that reuses existing preference_scorer and preference_merger. Output includes markdown_display (VERBATIM-wrapped) and interactive_data (for Slack rendering via existing proposal_formatter).

**Tech Stack:** Python 3.9+, Letta custom tools, existing scheduling_orchestrator modules

**Design Document:** Brainstorming session 2026-01-28 (context compacted)

---

## Files Overview

| File | Action | Purpose |
|------|--------|---------|
| `letta/scheduling_orchestrator/unified_slot_ranker.py` | Create | Single ranking entry point for both tools |
| `letta/scheduling_orchestrator/evaluate_proposed_times.py` | Modify | Use unified ranker, new output format |
| `letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py` | Create | Unit tests for ranker |
| `letta/scheduling_orchestrator/tests/test_evaluate_output_format.py` | Create | Tests for output formatting |

---

## Phase 1: Unified Slot Ranker

### Task 1.1: Create unified_slot_ranker.py with basic structure

**Files:**
- Create: `letta/scheduling_orchestrator/unified_slot_ranker.py`
- Test: `letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py`

**Step 1: Write failing test for basic ranking**

Create test file `letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py`:

```python
"""Tests for unified slot ranker."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Import will fail until we create the module
from letta.scheduling_orchestrator.unified_slot_ranker import rank_evaluated_slots
from letta.scheduling_orchestrator.evaluation_models import EvaluatedSlot


class TestRankEvaluatedSlots:
    """Tests for rank_evaluated_slots function."""

    def test_ranks_clean_above_conflicts(self):
        """Clean slots should rank higher than conflicted slots."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="solo_overlap",
                participants_available=[],
                participants_conflicted=["user1@example.com"],
                conflict_details=[{"summary": "Meeting", "participant": "user1@example.com"}]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com", "user2@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com", "user2@example.com"]
        )

        # Clean slot should be first
        assert ranked[0].category == "clean"
        assert ranked[1].category == "solo_overlap"
        # Scores should be assigned
        assert ranked[0].score > ranked[1].score

    def test_ranks_sooner_dates_higher(self):
        """Given same category, sooner dates should rank higher."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 31, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"]
        )

        # Jan 29 should be first (sooner)
        assert ranked[0].start.day == 29
        assert ranked[1].start.day == 31

    def test_handles_empty_slots(self):
        """Should handle empty slot list gracefully."""
        ranked = rank_evaluated_slots(
            slots=[],
            identity_id=None,
            participants=[]
        )
        assert ranked == []
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py -v
```
Expected: FAIL (module not found)

**Step 3: Create unified_slot_ranker.py with basic implementation**

Create `letta/scheduling_orchestrator/unified_slot_ranker.py`:

```python
"""
Unified slot ranking for scheduling tools.

Provides a single ranking entry point that can be used by both:
- evaluate_proposed_times (new tool)
- orchestrate_scheduling (existing orchestrator)

Combines:
- Category scoring (clean > solo_overlap > multi_person)
- Date proximity scoring (sooner is better)
- Preference scoring (via preference_scorer when context available)
"""

from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any

from .evaluation_models import EvaluatedSlot

# Category scores (higher = better)
CATEGORY_SCORES = {
    "clean": 100,
    "solo_overlap": 50,
    "multi_person": 0,
}

# Penalty per day in the future
DATE_PENALTY_PER_DAY = 2.0


def rank_evaluated_slots(
    slots: List[EvaluatedSlot],
    identity_id: Optional[str],
    participants: List[str],
    context_json: Optional[Dict[str, Any]] = None,
    reference_date: Optional[date] = None
) -> List[EvaluatedSlot]:
    """
    Rank evaluated slots by preference and feasibility.

    Scoring layers:
    1. Category score (clean=100, solo_overlap=50, multi_person=0)
    2. Date proximity (sooner dates preferred)
    3. Preference score (if identity/context provides preferences)

    Args:
        slots: List of EvaluatedSlot objects to rank
        identity_id: Optional Letta identity ID for preference lookup
        participants: List of participant email addresses
        context_json: Optional context with participant preferences
        reference_date: Date to calculate "days out" from (defaults to today)

    Returns:
        Sorted list of EvaluatedSlot objects (best first), with scores assigned
    """
    if not slots:
        return []

    if reference_date is None:
        reference_date = date.today()

    # Score each slot
    for slot in slots:
        score = _compute_slot_score(
            slot=slot,
            reference_date=reference_date,
            identity_id=identity_id,
            participants=participants,
            context_json=context_json
        )
        slot.score = score

    # Sort by score descending (higher = better)
    return sorted(slots, key=lambda s: s.score, reverse=True)


def _compute_slot_score(
    slot: EvaluatedSlot,
    reference_date: date,
    identity_id: Optional[str],
    participants: List[str],
    context_json: Optional[Dict[str, Any]]
) -> float:
    """Compute composite score for a single slot."""
    score = 0.0

    # 1. Category score
    score += CATEGORY_SCORES.get(slot.category, 0)

    # 2. Date proximity penalty
    slot_date = slot.start.date() if hasattr(slot.start, 'date') else slot.start
    days_out = (slot_date - reference_date).days
    score -= days_out * DATE_PENALTY_PER_DAY

    # 3. Preference score (Phase 1.2 will add this)
    # For now, skip if no context

    return score
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/unified_slot_ranker.py
git add letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py
git commit -m "feat: add unified_slot_ranker with basic category and date scoring"
```

---

### Task 1.2: Add preference scoring to unified ranker

**Files:**
- Modify: `letta/scheduling_orchestrator/unified_slot_ranker.py`
- Modify: `letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py`

**Step 1: Write failing test for preference scoring**

Add to test file:

```python
class TestPreferenceScoring:
    """Tests for preference-based scoring."""

    def test_applies_avoid_penalty(self):
        """Slots matching avoid preferences should score lower."""
        # Create two clean slots, one on an avoided day
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),  # Wednesday
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 30, 10, 0, tzinfo=timezone.utc),  # Thursday (avoided)
                end=datetime(2026, 1, 30, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        context_json = {
            "participants": [
                {
                    "id": "user1@example.com",
                    "preferences": {
                        "avoid_days": ["Thursday"]
                    }
                }
            ]
        }

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"],
            context_json=context_json,
            reference_date=date(2026, 1, 28)  # Fixed reference for test
        )

        # Wednesday should rank higher (Thursday is avoided)
        assert ranked[0].start.day == 29  # Wednesday
        assert ranked[1].start.day == 30  # Thursday

    def test_applies_preferred_bonus(self):
        """Slots matching preferred times should score higher."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),  # 2pm (not preferred)
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),  # 10am (morning preferred)
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        context_json = {
            "participants": [
                {
                    "id": "user1@example.com",
                    "preferences": {
                        "preferred_times": ["morning"]
                    }
                }
            ]
        }

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"],
            context_json=context_json,
            reference_date=date(2026, 1, 28)
        )

        # Morning slot should rank higher
        assert ranked[0].start.hour == 10
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py::TestPreferenceScoring -v
```
Expected: FAIL (preferences not applied)

**Step 3: Add preference scoring integration**

Update `unified_slot_ranker.py`:

```python
# Add imports at top
from .preference_scorer import compute_participant_preference_score
from .preference_merger import merge_standing_preferences
from .schemas import SchedulingProblem, ParticipantPreference
from .slot_indexer import SlotIndexer

# Update _compute_slot_score function:
def _compute_slot_score(
    slot: EvaluatedSlot,
    reference_date: date,
    identity_id: Optional[str],
    participants: List[str],
    context_json: Optional[Dict[str, Any]]
) -> float:
    """Compute composite score for a single slot."""
    score = 0.0

    # 1. Category score
    score += CATEGORY_SCORES.get(slot.category, 0)

    # 2. Date proximity penalty
    slot_date = slot.start.date() if hasattr(slot.start, 'date') else slot.start
    days_out = (slot_date - reference_date).days
    score -= days_out * DATE_PENALTY_PER_DAY

    # 3. Preference score
    if context_json and participants:
        preference_score = _compute_preference_score(
            slot=slot,
            participants=participants,
            context_json=context_json
        )
        score += preference_score * 2.0  # Weight factor for preferences

    return score


def _compute_preference_score(
    slot: EvaluatedSlot,
    participants: List[str],
    context_json: Dict[str, Any]
) -> float:
    """
    Compute preference score using preference_scorer module.

    Reuses the same scoring logic as the orchestrator.
    """
    # Build minimal SchedulingProblem for preference scoring
    scheduling_problem = SchedulingProblem(
        participants=participants,
        duration_minutes=int((slot.end - slot.start).total_seconds() / 60),
        participant_preferences=[]
    )

    # Merge standing preferences from context
    scheduling_problem = merge_standing_preferences(scheduling_problem, context_json)

    # Create slot indexer for datetime conversion
    # Use slot's date as the search range
    slot_indexer = SlotIndexer(
        search_start=slot.start.replace(hour=0, minute=0, second=0),
        search_end=slot.start.replace(hour=23, minute=59, second=59),
        slot_duration_minutes=30
    )

    # Compute score for each participant and aggregate
    total_score = 0.0
    slot_index = slot_indexer.datetime_to_slot(slot.start)

    if slot_index is not None:
        for participant_id in participants:
            participant_score = compute_participant_preference_score(
                slot=slot_index,
                participant_id=participant_id,
                scheduling_problem=scheduling_problem,
                context_json=context_json,
                slot_indexer=slot_indexer
            )
            total_score += participant_score

    return total_score
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/unified_slot_ranker.py
git add letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py
git commit -m "feat: add preference scoring to unified_slot_ranker"
```

---

### Task 1.3: Add identity-based preference lookup

**Files:**
- Modify: `letta/scheduling_orchestrator/unified_slot_ranker.py`
- Modify: `letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py`

**Step 1: Write failing test for identity lookup**

Add to test file:

```python
class TestIdentityPreferenceLookup:
    """Tests for identity-based preference lookup."""

    @patch('letta.scheduling_orchestrator.unified_slot_ranker.get_user_preferences_from_identity')
    def test_fetches_preferences_from_identity(self, mock_get_prefs):
        """Should fetch preferences from identity when identity_id provided."""
        mock_get_prefs.return_value = {
            "preferred_times": ["morning"],
            "avoid_days": ["Friday"]
        }

        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id="identity-123",
            participants=["user1@example.com"]
        )

        # Should have called the identity lookup
        mock_get_prefs.assert_called_once_with("identity-123")
        # Should return ranked slots
        assert len(ranked) == 1

    @patch('letta.scheduling_orchestrator.unified_slot_ranker.get_user_preferences_from_identity')
    def test_skips_identity_lookup_when_no_identity(self, mock_get_prefs):
        """Should not call identity lookup when identity_id is None."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"]
        )

        mock_get_prefs.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py::TestIdentityPreferenceLookup -v
```
Expected: FAIL

**Step 3: Add identity lookup integration**

Update `unified_slot_ranker.py`:

```python
# Add import
from .identity_helpers import get_user_preferences_from_identity

# Update rank_evaluated_slots function to fetch identity preferences:
def rank_evaluated_slots(
    slots: List[EvaluatedSlot],
    identity_id: Optional[str],
    participants: List[str],
    context_json: Optional[Dict[str, Any]] = None,
    reference_date: Optional[date] = None
) -> List[EvaluatedSlot]:
    """..."""  # Existing docstring

    if not slots:
        return []

    if reference_date is None:
        reference_date = date.today()

    # Build context_json from identity if provided
    if context_json is None:
        context_json = {"participants": []}

    # Fetch preferences from identity if available
    if identity_id:
        try:
            identity_prefs = get_user_preferences_from_identity(identity_id)
            if identity_prefs:
                # Add identity preferences to first participant (requester)
                if participants:
                    requester_id = participants[0]
                    _add_identity_preferences_to_context(
                        context_json, requester_id, identity_prefs
                    )
        except Exception:
            # Log but don't fail if identity lookup fails
            pass

    # Rest of existing implementation...


def _add_identity_preferences_to_context(
    context_json: Dict[str, Any],
    participant_id: str,
    preferences: Dict[str, Any]
) -> None:
    """Add identity-based preferences to context_json."""
    if "participants" not in context_json:
        context_json["participants"] = []

    # Find or create participant entry
    participant_entry = None
    for p in context_json["participants"]:
        if p.get("id") == participant_id:
            participant_entry = p
            break

    if participant_entry is None:
        participant_entry = {"id": participant_id, "preferences": {}}
        context_json["participants"].append(participant_entry)

    if "preferences" not in participant_entry:
        participant_entry["preferences"] = {}

    # Merge preferences (identity provides defaults, don't override existing)
    for key, value in preferences.items():
        if key not in participant_entry["preferences"]:
            participant_entry["preferences"][key] = value
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/unified_slot_ranker.py
git add letta/scheduling_orchestrator/tests/test_unified_slot_ranker.py
git commit -m "feat: add identity-based preference lookup to unified_slot_ranker"
```

---

## Phase 2: Output Formatting

### Task 2.1: Create format_evaluation_output helper

**Files:**
- Modify: `letta/scheduling_orchestrator/evaluate_proposed_times.py`
- Create: `letta/scheduling_orchestrator/tests/test_evaluate_output_format.py`

**Step 1: Write failing test for output formatting**

Create `letta/scheduling_orchestrator/tests/test_evaluate_output_format.py`:

```python
"""Tests for evaluate_proposed_times output formatting."""

import pytest
from datetime import datetime, timezone

from letta.scheduling_orchestrator.evaluate_proposed_times import format_evaluation_output
from letta.scheduling_orchestrator.evaluation_models import EvaluatedSlot


class TestFormatEvaluationOutput:
    """Tests for format_evaluation_output function."""

    def test_includes_verbatim_markers(self):
        """Output should be wrapped in VERBATIM markers."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        assert "[VERBATIM_USER_OUTPUT]" in result["markdown_display"]
        assert "[/VERBATIM_USER_OUTPUT]" in result["markdown_display"]

    def test_includes_participant_tags(self):
        """Output should include PARTICIPANTS and PARTICIPANT_NAMES tags."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com", "user2@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com", "user2@example.com"],
            participant_names=["User One", "User Two"],
            timezone="America/Los_Angeles"
        )

        assert "[PARTICIPANTS:user1@example.com,user2@example.com]" in result["markdown_display"]
        assert "[PARTICIPANT_NAMES:User One,User Two]" in result["markdown_display"]

    def test_groups_slots_by_day(self):
        """Slots should be grouped under day headers."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 30, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 30, 15, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=98.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Should have day headers
        assert "Wednesday, January 29" in result["markdown_display"]
        assert "Thursday, January 30" in result["markdown_display"]

    def test_includes_conflict_annotations(self):
        """Conflicted slots should show conflict details."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="solo_overlap",
                participants_available=["user2@example.com"],
                participants_conflicted=["user1@example.com"],
                conflict_details=[{
                    "summary": "Team Standup",
                    "participant": "user1@example.com"
                }],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com", "user2@example.com"],
            participant_names=["User One", "User Two"],
            timezone="America/Los_Angeles"
        )

        # Should show conflict indicator and details
        assert "Team Standup" in result["markdown_display"]
        assert "User One" in result["markdown_display"] or "user1@example.com" in result["markdown_display"]

    def test_includes_interactive_data(self):
        """Result should include interactive_data for Slack rendering."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        assert "interactive_data" in result
        assert "participants" in result["interactive_data"]
        assert "participant_names" in result["interactive_data"]
        assert "proposals" in result["interactive_data"]
        assert len(result["interactive_data"]["proposals"]) == 1

    def test_includes_summary_line(self):
        """Output should include summary of slot counts."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="solo_overlap",
                participants_available=[],
                participants_conflicted=["user1@example.com"],
                conflict_details=[],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Should have summary
        assert "2 times evaluated" in result["markdown_display"]
        assert "1 clean" in result["markdown_display"]
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_evaluate_output_format.py -v
```
Expected: FAIL (function not found)

**Step 3: Implement format_evaluation_output**

Add to `evaluate_proposed_times.py`:

```python
from collections import defaultdict
from typing import Dict, Any, List
import pytz

def format_evaluation_output(
    ranked_slots: List[EvaluatedSlot],
    participants: List[str],
    participant_names: List[str],
    timezone: str
) -> Dict[str, Any]:
    """
    Format ranked slots for both LLM display and Slack interaction.

    Args:
        ranked_slots: List of EvaluatedSlot objects, already ranked
        participants: List of participant email addresses
        participant_names: List of participant display names
        timezone: Timezone for display (e.g., "America/Los_Angeles")

    Returns:
        Dictionary with:
        - markdown_display: VERBATIM-wrapped text for LLM response
        - interactive_data: Structured data for Slack adapter
    """
    tz = pytz.timezone(timezone)

    # Build participant lookup for names
    name_lookup = dict(zip(participants, participant_names))

    # Group slots by day
    slots_by_day = defaultdict(list)
    for slot in ranked_slots:
        local_start = slot.start.astimezone(tz)
        day_key = local_start.strftime("%A, %B %d")
        slots_by_day[day_key].append(slot)

    # Build markdown output
    lines = [
        "[VERBATIM_USER_OUTPUT]",
        f"[PARTICIPANTS:{','.join(participants)}]",
        f"[PARTICIPANT_NAMES:{','.join(participant_names)}]",
        "",
        "## Available Times",
        ""
    ]

    # Category indicators
    category_icons = {
        "clean": "✅",
        "solo_overlap": "⚠️",
        "multi_person": "❌"
    }

    # Add slots grouped by day
    for day_key in slots_by_day:
        lines.append(f"### {day_key}")
        lines.append("")

        for slot in slots_by_day[day_key]:
            local_start = slot.start.astimezone(tz)
            local_end = slot.end.astimezone(tz)

            time_str = f"{local_start.strftime('%I:%M %p')} - {local_end.strftime('%I:%M %p')}"
            icon = category_icons.get(slot.category, "❓")

            lines.append(f"{icon} **{time_str}** ({slot.category.replace('_', ' ')})")

            if slot.category == "clean":
                lines.append("   No conflicts")
            else:
                # Show conflict details
                for conflict in slot.conflict_details:
                    participant = conflict.get("participant", "Unknown")
                    participant_name = name_lookup.get(participant, participant)
                    summary = conflict.get("summary", "Busy")
                    lines.append(f"   Conflicts with: \"{summary}\" ({participant_name})")

            lines.append("")

    # Summary line
    clean_count = sum(1 for s in ranked_slots if s.category == "clean")
    conflict_count = len(ranked_slots) - clean_count

    lines.append("---")
    summary_parts = [f"{len(ranked_slots)} times evaluated"]
    if clean_count > 0:
        summary_parts.append(f"{clean_count} clean")
    if conflict_count > 0:
        summary_parts.append(f"{conflict_count} with conflicts")
    lines.append(", ".join(summary_parts))

    lines.append("[/VERBATIM_USER_OUTPUT]")

    # Build interactive data for Slack
    interactive_data = {
        "participants": participants,
        "participant_names": participant_names,
        "proposals": [
            _slot_to_proposal_dict(slot, tz) for slot in ranked_slots
        ]
    }

    return {
        "markdown_display": "\n".join(lines),
        "interactive_data": interactive_data
    }


def _slot_to_proposal_dict(slot: EvaluatedSlot, tz: pytz.timezone) -> Dict[str, Any]:
    """Convert EvaluatedSlot to proposal dictionary for Slack rendering."""
    local_start = slot.start.astimezone(tz)
    local_end = slot.end.astimezone(tz)

    return {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "start_local": local_start.isoformat(),
        "end_local": local_end.isoformat(),
        "category": slot.category,
        "participants_available": slot.participants_available,
        "participants_conflicted": slot.participants_conflicted,
        "conflict_details": slot.conflict_details,
        "score": slot.score
    }
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_evaluate_output_format.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/evaluate_proposed_times.py
git add letta/scheduling_orchestrator/tests/test_evaluate_output_format.py
git commit -m "feat: add format_evaluation_output for VERBATIM and Slack formatting"
```

---

### Task 2.2: Update evaluate_proposed_times return structure

**Files:**
- Modify: `letta/scheduling_orchestrator/evaluate_proposed_times.py`
- Modify: `letta/scheduling_orchestrator/tests/test_evaluate_proposed_times.py`

**Step 1: Write failing test for new return structure**

Add to existing test file:

```python
class TestReturnStructure:
    """Tests for the new return structure."""

    def test_returns_markdown_display(self):
        """Result should include markdown_display field."""
        # Call evaluate_proposed_times with valid input
        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00,2026-01-29T14:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        assert "markdown_display" in result
        assert "[VERBATIM_USER_OUTPUT]" in result["markdown_display"]

    def test_returns_interactive_data(self):
        """Result should include interactive_data for Slack."""
        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        assert "interactive_data" in result
        assert "proposals" in result["interactive_data"]

    def test_maintains_backward_compatible_slots(self):
        """Result should still include slots field for compatibility."""
        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        assert "slots" in result
        assert isinstance(result["slots"], list)
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_evaluate_proposed_times.py::TestReturnStructure -v
```
Expected: FAIL

**Step 3: Update evaluate_proposed_times to use new formatting**

In `evaluate_proposed_times.py`, find the return statement (around line 260-280) and update:

```python
# Replace simple ranking call
from .unified_slot_ranker import rank_evaluated_slots

# In the main function, replace:
#   ranked_slots = rank_slots(all_slots, reference_date=today)
# With:
ranked_slots = rank_evaluated_slots(
    slots=all_slots,
    identity_id=identity_id,  # Pass through from function parameter
    participants=participant_list,
    context_json=context_json
)

# Replace the return statement with:
# Format output for both LLM and Slack
formatted = format_evaluation_output(
    ranked_slots=ranked_slots,
    participants=participant_list,
    participant_names=participant_names,
    timezone=timezone_str
)

return {
    "status": "ok",
    "slots": [_slot_to_dict(s) for s in ranked_slots],  # Backward compatible
    "markdown_display": formatted["markdown_display"],
    "interactive_data": formatted["interactive_data"],
    "summary": {
        "total_proposed": len(proposed_times_list),
        "total_evaluated": len(ranked_slots),
        "clean_count": sum(1 for s in ranked_slots if s.category == "clean"),
        "conflict_count": sum(1 for s in ranked_slots if s.category != "clean")
    }
}
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_evaluate_proposed_times.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/evaluate_proposed_times.py
git add letta/scheduling_orchestrator/tests/test_evaluate_proposed_times.py
git commit -m "feat: update evaluate_proposed_times with unified ranker and formatted output"
```

---

## Phase 3: Slack Integration Bridge

### Task 3.1: Create InteractiveProposal converter

**Files:**
- Modify: `letta/scheduling_orchestrator/evaluate_proposed_times.py`
- Create: `letta/scheduling_orchestrator/tests/test_interactive_conversion.py`

**Step 1: Write failing test for InteractiveProposal conversion**

Create `letta/scheduling_orchestrator/tests/test_interactive_conversion.py`:

```python
"""Tests for InteractiveProposal conversion."""

import pytest
from datetime import datetime, timezone

from letta.scheduling_orchestrator.evaluate_proposed_times import evaluated_slot_to_interactive_proposal
from letta.scheduling_orchestrator.evaluation_models import EvaluatedSlot
from letta.scheduling_orchestrator.interactive_models import InteractiveProposal


class TestInteractiveProposalConversion:
    """Tests for evaluated_slot_to_interactive_proposal."""

    def test_converts_clean_slot(self):
        """Should convert clean slot to InteractiveProposal."""
        slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            participants_available=["user1@example.com", "user2@example.com"],
            participants_conflicted=[],
            conflict_details=[],
            score=100.0
        )

        proposal = evaluated_slot_to_interactive_proposal(
            slot=slot,
            participants=["user1@example.com", "user2@example.com"]
        )

        assert isinstance(proposal, InteractiveProposal)
        assert proposal.start == slot.start
        assert proposal.end == slot.end
        assert proposal.category == "clean"

    def test_converts_conflicted_slot(self):
        """Should convert conflicted slot with conflict details."""
        slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
            category="solo_overlap",
            participants_available=["user2@example.com"],
            participants_conflicted=["user1@example.com"],
            conflict_details=[{
                "summary": "Team Meeting",
                "participant": "user1@example.com",
                "start": "2026-01-29T13:30:00Z",
                "end": "2026-01-29T14:30:00Z"
            }],
            score=50.0
        )

        proposal = evaluated_slot_to_interactive_proposal(
            slot=slot,
            participants=["user1@example.com", "user2@example.com"]
        )

        assert proposal.category == "solo_overlap"
        assert len(proposal.conflicts) >= 1

    def test_preserves_score(self):
        """Score should be preserved in conversion."""
        slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            participants_available=["user1@example.com"],
            participants_conflicted=[],
            conflict_details=[],
            score=95.5
        )

        proposal = evaluated_slot_to_interactive_proposal(
            slot=slot,
            participants=["user1@example.com"]
        )

        assert proposal.score == 95.5
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_interactive_conversion.py -v
```
Expected: FAIL (function not found)

**Step 3: Implement evaluated_slot_to_interactive_proposal**

Add to `evaluate_proposed_times.py`:

```python
from .interactive_models import InteractiveProposal, ConflictInfo

def evaluated_slot_to_interactive_proposal(
    slot: EvaluatedSlot,
    participants: List[str]
) -> InteractiveProposal:
    """
    Convert an EvaluatedSlot to InteractiveProposal for Slack rendering.

    This enables reuse of the existing proposal_formatter infrastructure.

    Args:
        slot: The evaluated slot to convert
        participants: List of all participant email addresses

    Returns:
        InteractiveProposal object compatible with proposal_formatter
    """
    # Convert conflict details to ConflictInfo objects
    conflicts = []
    for conflict in slot.conflict_details:
        conflicts.append(ConflictInfo(
            event_summary=conflict.get("summary", "Busy"),
            participant=conflict.get("participant", "Unknown"),
            event_start=conflict.get("start"),
            event_end=conflict.get("end")
        ))

    return InteractiveProposal(
        start=slot.start,
        end=slot.end,
        category=slot.category,
        participants_available=slot.participants_available,
        participants_conflicted=slot.participants_conflicted,
        conflicts=conflicts,
        score=slot.score
    )
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_interactive_conversion.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add letta/scheduling_orchestrator/evaluate_proposed_times.py
git add letta/scheduling_orchestrator/tests/test_interactive_conversion.py
git commit -m "feat: add evaluated_slot_to_interactive_proposal converter"
```

---

### Task 3.2: Verify Slack rendering compatibility

**Files:**
- Create: `letta/scheduling_orchestrator/tests/test_slack_rendering.py`

**Step 1: Write integration test for Slack rendering**

Create `letta/scheduling_orchestrator/tests/test_slack_rendering.py`:

```python
"""Integration tests for Slack rendering of evaluated slots."""

import pytest
from datetime import datetime, timezone

from letta.scheduling_orchestrator.evaluate_proposed_times import (
    evaluated_slot_to_interactive_proposal,
    format_evaluation_output
)
from letta.scheduling_orchestrator.evaluation_models import EvaluatedSlot
from letta.scheduling_orchestrator.interactive_models import InteractiveProposalSet
from letta.scheduling_orchestrator.proposal_formatter import format_proposals_for_slack


class TestSlackRenderingIntegration:
    """Integration tests for Slack Block Kit rendering."""

    def test_renders_evaluated_slots_to_slack_blocks(self):
        """Should produce valid Slack blocks from evaluated slots."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="solo_overlap",
                participants_available=[],
                participants_conflicted=["user1@example.com"],
                conflict_details=[{"summary": "Standup", "participant": "user1@example.com"}],
                score=50.0
            ),
        ]

        participants = ["user1@example.com"]
        participant_names = ["User One"]

        # Convert to InteractiveProposals
        proposals = [
            evaluated_slot_to_interactive_proposal(slot, participants)
            for slot in slots
        ]

        # Create proposal set
        proposal_set = InteractiveProposalSet(
            proposals=proposals,
            participants=participants,
            participant_names=participant_names,
            meeting_title="Test Meeting",
            duration_minutes=60
        )

        # Render to Slack blocks
        blocks = format_proposals_for_slack(proposal_set)

        # Verify we got valid blocks
        assert isinstance(blocks, list)
        assert len(blocks) > 0

        # Check for expected block types
        block_types = [b.get("type") for b in blocks]
        assert "section" in block_types or "header" in block_types

    def test_interactive_data_can_create_proposal_set(self):
        """interactive_data from format_evaluation_output should create valid ProposalSet."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                participants_available=["user1@example.com"],
                participants_conflicted=[],
                conflict_details=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Verify interactive_data has required fields
        data = result["interactive_data"]
        assert "participants" in data
        assert "participant_names" in data
        assert "proposals" in data

        # Verify proposals have required fields for InteractiveProposal
        for proposal in data["proposals"]:
            assert "start" in proposal
            assert "end" in proposal
            assert "category" in proposal
```

**Step 2: Run test**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_slack_rendering.py -v
```
Expected: PASS (if all dependencies are correct)

**Step 3: Commit**

```bash
git add letta/scheduling_orchestrator/tests/test_slack_rendering.py
git commit -m "test: add Slack rendering integration tests for evaluated slots"
```

---

## Phase 4: End-to-End Testing

### Task 4.1: Full integration test

**Files:**
- Create: `letta/scheduling_orchestrator/tests/test_evaluate_integration.py`

**Step 1: Write end-to-end integration test**

Create `letta/scheduling_orchestrator/tests/test_evaluate_integration.py`:

```python
"""End-to-end integration tests for evaluate_proposed_times."""

import pytest
from unittest.mock import patch, MagicMock

from letta.scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times


class TestEvaluateProposedTimesIntegration:
    """End-to-end tests for the complete flow."""

    @patch('letta.scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data')
    def test_full_flow_with_clean_slots(self, mock_fetch):
        """Test complete flow producing clean slots."""
        # Mock calendar data with no conflicts
        mock_fetch.return_value = {
            "user1@example.com": {
                "events": [],
                "working_hours": {"start": "09:00", "end": "17:00"}
            }
        }

        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00,2026-01-29T14:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        # Verify structure
        assert result["status"] == "ok"
        assert "markdown_display" in result
        assert "interactive_data" in result
        assert "slots" in result

        # Verify VERBATIM markers
        assert "[VERBATIM_USER_OUTPUT]" in result["markdown_display"]

        # Verify slots are clean
        for slot in result["slots"]:
            assert slot["category"] == "clean"

    @patch('letta.scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data')
    def test_full_flow_with_conflicts(self, mock_fetch):
        """Test complete flow with conflicting events."""
        mock_fetch.return_value = {
            "user1@example.com": {
                "events": [{
                    "summary": "Existing Meeting",
                    "start": {"dateTime": "2026-01-29T10:00:00-08:00"},
                    "end": {"dateTime": "2026-01-29T11:00:00-08:00"}
                }],
                "working_hours": {"start": "09:00", "end": "17:00"}
            }
        }

        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00,2026-01-29T14:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        assert result["status"] == "ok"

        # Should have mix of categories
        categories = [s["category"] for s in result["slots"]]
        assert "solo_overlap" in categories or "clean" in categories

    @patch('letta.scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data')
    @patch('letta.scheduling_orchestrator.unified_slot_ranker.get_user_preferences_from_identity')
    def test_full_flow_with_identity_preferences(self, mock_prefs, mock_fetch):
        """Test complete flow with identity-based preferences."""
        mock_fetch.return_value = {
            "user1@example.com": {
                "events": [],
                "working_hours": {"start": "09:00", "end": "17:00"}
            }
        }
        mock_prefs.return_value = {
            "preferred_times": ["morning"],
            "avoid_days": ["Friday"]
        }

        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00,2026-01-29T14:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting",
            identity_id="identity-123"
        )

        assert result["status"] == "ok"
        mock_prefs.assert_called_once_with("identity-123")

    @patch('letta.scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data')
    def test_ranking_prefers_clean_over_conflicts(self, mock_fetch):
        """Clean slots should be ranked above conflicted slots."""
        mock_fetch.return_value = {
            "user1@example.com": {
                "events": [{
                    "summary": "Conflict",
                    "start": {"dateTime": "2026-01-29T10:00:00-08:00"},
                    "end": {"dateTime": "2026-01-29T10:30:00-08:00"}
                }],
                "working_hours": {"start": "09:00", "end": "17:00"}
            }
        }

        result = evaluate_proposed_times(
            proposed_times="2026-01-29T10:00:00-08:00,2026-01-29T14:00:00-08:00",
            participants="user1@example.com",
            duration_minutes=60,
            meeting_title="Test Meeting"
        )

        # First slot in result should be the clean one (2pm)
        # Second should be the conflicted one (10am)
        slots = result["slots"]
        if len(slots) == 2:
            # Clean slot should have higher score and come first
            assert slots[0]["score"] >= slots[1]["score"]
```

**Step 2: Run integration tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/scheduling_orchestrator/tests/test_evaluate_integration.py -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add letta/scheduling_orchestrator/tests/test_evaluate_integration.py
git commit -m "test: add end-to-end integration tests for evaluate_proposed_times"
```

---

### Task 4.2: Manual verification via Letta

**Files:** None (manual testing)

**Step 1: Register updated tool with Letta**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python letta/register_evaluate_proposed_times.py
```

**Step 2: Test via Letta API**

Run:
```bash
curl -X POST http://localhost:8283/v1/agents/<AGENT_ID>/messages \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Can you evaluate these proposed meeting times: tomorrow at 10am, tomorrow at 2pm, and tomorrow at 4pm? The meeting is with cdorsey@concord.org for 1 hour."
    }]
  }'
```

**Step 3: Verify output**

Check that response includes:
- [ ] VERBATIM markers wrapping the output
- [ ] PARTICIPANTS tag with email addresses
- [ ] Day groupings with headers
- [ ] Conflict annotations (✅/⚠️/❌)
- [ ] Summary line with counts

**Step 4: Test Slack rendering (if applicable)**

If Slack adapter is available, send the same request via Slack and verify:
- [ ] Proposals render with buttons
- [ ] Day headers appear
- [ ] Conflict details show correctly

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| **Unified ranking** | Both tools use same ranking logic via unified_slot_ranker |
| **VERBATIM markers** | Output wrapped correctly, LLM doesn't summarize |
| **Participant tags** | PARTICIPANTS and PARTICIPANT_NAMES present |
| **Day grouping** | Slots grouped under day headers |
| **Conflict annotations** | ✅/⚠️/❌ icons and details shown |
| **Interactive data** | Slack can render with existing proposal_formatter |
| **Identity preferences** | Preferences fetched from identity when provided |
| **Backward compatible** | `slots` field still present for programmatic use |
| **All tests pass** | `pytest letta/scheduling_orchestrator/tests/ -v` green |

---

## Execution Order

**Phase 1 (Sequential):**
- Task 1.1: Create unified_slot_ranker with basic scoring
- Task 1.2: Add preference scoring integration
- Task 1.3: Add identity-based preference lookup

**Phase 2 (Sequential):**
- Task 2.1: Create format_evaluation_output helper
- Task 2.2: Update evaluate_proposed_times return structure

**Phase 3 (Sequential):**
- Task 3.1: Create InteractiveProposal converter
- Task 3.2: Verify Slack rendering compatibility

**Phase 4 (Sequential):**
- Task 4.1: Full integration tests
- Task 4.2: Manual verification via Letta
