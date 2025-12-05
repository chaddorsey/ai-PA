"""
Functions to build agent-facing structured data.

This module provides functions to construct the agent_data structure
with event registries, ranking rationale, and optimization summaries.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import pytz

from .schemas import (
    Proposal, EventMetadata, RankingRationale, RankingFactor,
    ProposalComparison, OptimizationSummary, ConstraintsApplied
)


def build_event_registry(
    proposals: List[Proposal],
    normalized_data: Dict[str, Any]
) -> Dict[str, EventMetadata]:
    """
    Build a registry of all events referenced in proposals.
    
    Args:
        proposals: List of all proposals
        normalized_data: Normalized data containing event metadata
    
    Returns:
        Dictionary mapping event_id -> EventMetadata
    """
    registry = {}
    event_metadata_map = normalized_data.get("event_metadata", {})
    
    # Collect all event IDs from moved_events
    for proposal in proposals:
        for moved in proposal.moved_events:
            event_key = (moved.owner, moved.event_id)
            if event_key in event_metadata_map and moved.event_id not in registry:
                meta = event_metadata_map[event_key]
                
                # Build human-readable description
                title = meta.get("title", moved.event_id[:40])
                start_dt_str = meta.get("start_str", moved.old_start)
                try:
                    dt = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = pytz.UTC.localize(dt)
                    et_tz = pytz.timezone("America/New_York")
                    dt_et = dt.astimezone(et_tz)
                    date_str = dt_et.strftime("%b %d at %I:%M %p").lstrip("0")
                    human_readable = f"{title} on {date_str}"
                except Exception:
                    human_readable = title
                
                registry[moved.event_id] = EventMetadata(
                    title=title,
                    owner=moved.owner,
                    start_utc=moved.old_start,
                    end_utc=moved.old_end,
                    locked=meta.get("locked", False),
                    protected=meta.get("protected", False),
                    flexible=meta.get("flexible", True),
                    number_of_attendees=meta.get("number_of_attendees", 0),
                    internal_only=meta.get("internal_only", True),
                    human_readable=human_readable
                )
    
    return registry


def identify_primary_factors(proposal: Proposal) -> List[RankingFactor]:
    """
    Identify the primary factors contributing to a proposal's ranking.
    
    Args:
        proposal: The proposal to analyze
    
    Returns:
        List of RankingFactor objects
    """
    factors = []
    
    # Category factor
    category = proposal.category or "unknown"
    if category == "zero_conflict":
        factors.append(RankingFactor(
            factor="zero_conflict",
            impact="high",
            value=None
        ))
    elif category == "single_move":
        factors.append(RankingFactor(
            factor="single_move",
            impact="high",
            value=1.0  # 1 move
        ))
    elif category == "solo_override":
        factors.append(RankingFactor(
            factor="solo_override",
            impact="medium",
            value=None
        ))
    
    # Free-block score
    if proposal.free_block_stats and proposal.free_block_stats.free_block_score:
        factors.append(RankingFactor(
            factor="free_block_score",
            impact="high",
            value=proposal.free_block_stats.free_block_score
        ))
    
    # Preference score
    if proposal.preference_score is not None and proposal.preference_score != 0:
        factors.append(RankingFactor(
            factor="preference_score",
            impact="medium",
            value=proposal.preference_score
        ))
    
    # Priority score
    if proposal.objective_scores.priority_score:
        factors.append(RankingFactor(
            factor="priority_score",
            impact="low",
            value=proposal.objective_scores.priority_score
        ))
    
    # Move count (fewer is better)
    move_count = len(proposal.moved_events)
    if move_count > 0:
        factors.append(RankingFactor(
            factor="move_count",
            impact="high",
            value=float(move_count)
        ))
    
    return factors


def compare_proposals(proposal: Proposal, other_proposals: List[Proposal]) -> ProposalComparison:
    """
    Compare a proposal with others to understand ranking relationships.
    
    Args:
        proposal: The proposal to compare
        other_proposals: Other proposals to compare against
    
    Returns:
        ProposalComparison object
    """
    better_than = []
    worse_than = []
    
    proposal_rank = proposal.rank or 999
    proposal_score = proposal.free_block_stats.free_block_score if proposal.free_block_stats else 0.0
    proposal_pref_score = proposal.preference_score or 0.0
    proposal_move_count = len(proposal.moved_events)
    
    for other in other_proposals:
        if not other.proposal_id:
            continue
        
        other_rank = other.rank or 999
        other_score = other.free_block_stats.free_block_score if other.free_block_stats else 0.0
        other_pref_score = other.preference_score or 0.0
        other_move_count = len(other.moved_events)
        
        if proposal_rank < other_rank:
            better_than.append(other.proposal_id)
        elif proposal_rank > other_rank:
            worse_than.append(other.proposal_id)
        # If ranks are equal, compare by score
        elif proposal_score > other_score:
            better_than.append(other.proposal_id)
        elif proposal_score < other_score:
            worse_than.append(other.proposal_id)
        elif proposal_pref_score > other_pref_score:
            better_than.append(other.proposal_id)
        elif proposal_pref_score < other_pref_score:
            worse_than.append(other.proposal_id)
    
    # Identify tie-breakers
    tie_breakers = []
    if proposal_pref_score != 0:
        tie_breakers.append("preference_score")
    if proposal_move_count > 0:
        tie_breakers.append("move_count")
    tie_breakers.append("time")  # Earlier times preferred
    
    return ProposalComparison(
        better_than=better_than,
        worse_than=worse_than,
        tie_breakers=tie_breakers
    )


def generate_ranking_rationale(proposals: List[Proposal]) -> Dict[str, RankingRationale]:
    """
    Generate ranking rationale for all proposals.
    
    Args:
        proposals: List of all proposals (should be sorted by rank)
    
    Returns:
        Dictionary mapping proposal_id -> RankingRationale
    """
    rationale = {}
    
    for i, proposal in enumerate(proposals):
        if not proposal.proposal_id:
            continue
        
        primary_factors = identify_primary_factors(proposal)
        
        # Compare with proposals ranked before this one (they rank better)
        comparison = compare_proposals(proposal, proposals[:i])
        
        rationale[proposal.proposal_id] = RankingRationale(
            primary_factors=primary_factors,
            comparison=comparison
        )
    
    return rationale


def build_optimization_summary(
    proposals: List[Proposal],
    scheduling_problem: Any  # SchedulingProblem
) -> OptimizationSummary:
    """
    Build a summary of optimization results.
    
    Args:
        proposals: List of all proposals
        scheduling_problem: The scheduling problem that was solved
    
    Returns:
        OptimizationSummary object
    """
    if not proposals:
        return OptimizationSummary(
            total_proposals_found=0,
            zero_conflict_count=0,
            single_move_count=0,
            solo_override_count=0,
            multi_move_count=0,
            best_score=0.0,
            score_range={"min": 0.0, "max": 0.0},
            preference_match_count=0,
            work_hours_compliance="none"
        )
    
    scores = []
    zero_conflict = 0
    single_move = 0
    solo_override = 0
    multi_move = 0
    preference_matches = 0
    
    for prop in proposals:
        # Count by category
        category = prop.category or "unknown"
        if category == "zero_conflict":
            zero_conflict += 1
        elif category == "single_move":
            single_move += 1
        elif category == "solo_override":
            solo_override += 1
        else:
            multi_move += 1
        
        # Collect scores
        if prop.free_block_stats and prop.free_block_stats.free_block_score:
            scores.append(prop.free_block_stats.free_block_score)
        
        # Count preference matches
        if prop.preference_score and prop.preference_score > 0:
            preference_matches += 1
    
    best_score = max(scores) if scores else 0.0
    score_range = {
        "min": min(scores) if scores else 0.0,
        "max": best_score
    }
    
    # Determine work hours compliance (all proposals should be within work hours if enforced)
    work_hours_compliance = "full"  # Assume full compliance unless we detect issues
    
    return OptimizationSummary(
        total_proposals_found=len(proposals),
        zero_conflict_count=zero_conflict,
        single_move_count=single_move,
        solo_override_count=solo_override,
        multi_move_count=multi_move,
        best_score=best_score,
        score_range=score_range,
        preference_match_count=preference_matches,
        work_hours_compliance=work_hours_compliance
    )


def build_constraints_applied(
    normalized_data: Dict[str, Any],
    scheduling_problem: Any,  # SchedulingProblem
    context_json: Optional[Dict[str, Any]]
) -> ConstraintsApplied:
    """
    Build a summary of constraints that were applied.
    
    Args:
        normalized_data: Normalized data
        scheduling_problem: The scheduling problem
        context_json: Optional context JSON
    
    Returns:
        ConstraintsApplied object
    """
    # Count locked events that blocked slots
    event_protection = normalized_data.get("event_protection", {})
    locked_count = sum(1 for level in event_protection.values() if level == "locked")
    
    # Extract preferences
    preferences_applied = []
    if scheduling_problem.preferred_days:
        preferences_applied.append(f"prefer_{'_'.join(scheduling_problem.preferred_days).lower()}")
    if scheduling_problem.avoid_days:
        preferences_applied.append(f"avoid_{'_'.join(scheduling_problem.avoid_days).lower()}")
    if scheduling_problem.participant_preferences:
        preferences_applied.append("participant_preferences")
    
    # Determine work hours enforcement
    work_hours_enforced = bool(context_json and context_json.get("participants"))
    
    # Get min gap
    min_gap_minutes = scheduling_problem.min_gap_minutes or 0
    if context_json and "policy" in context_json:
        policy = context_json["policy"]
        if "hard" in policy and "min_gap_min" in policy["hard"]:
            min_gap_minutes = policy["hard"]["min_gap_min"]
    
    return ConstraintsApplied(
        work_hours_enforced=work_hours_enforced,
        min_gap_minutes=min_gap_minutes,
        locked_events_blocked=locked_count,
        preferences_applied=preferences_applied
    )

