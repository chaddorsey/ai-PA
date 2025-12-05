# Dual-Format Payload Proposal for Letta Integration

## Executive Summary

The scheduling orchestrator currently returns a single unified payload containing both user-facing information (formatted meeting proposals) and agent-facing metadata (event IDs, scoring details, optimization rationale). This document analyzes whether a dual-format payload would improve the Letta agent's ability to reason about results while maintaining high-quality user presentation.

**Recommendation**: Implement a **structured dual-format response** with clear separation between user-facing formatted content and agent-facing metadata. This provides the best balance of agent reasoning capability and user experience.

---

## Current State Analysis

### Current Return Format

The orchestrator returns a `ResponseEnvelope` with:

```python
{
    "status": "ok" | "unsat" | "bad_input",
    "proposals": [
        {
            "title": str,
            "participants": List[str],
            "start_utc": str,
            "end_utc": str,
            "location": Optional[str],
            "notes_for_invite": Optional[str],
            "moved_events": [MovedEvent],
            "objective_scores": ObjectiveScores,
            "free_block_stats": Optional[FreeBlockStats]
        }
    ],
    "explanation": str,  # Human-readable summary
    "relaxations": Optional[List[Relaxation]],
    "debug": Optional[DebugInfo],
    "error_message": Optional[str]
}
```

### Current Challenges

1. **Mixed Concerns**: User-facing formatting (times, dates) is mixed with agent metadata (scores, IDs)
2. **Agent Reasoning Gaps**: The agent cannot easily:
   - Reference specific events by ID for follow-up questions
   - Understand why one proposal ranks higher than another
   - Make informed decisions about which proposal to select
   - Refine requests based on optimization scores
3. **Presentation Limitations**: The agent must format the response from structured data, potentially missing nuances
4. **Traceability**: Hard to link proposals back to specific calendar events for follow-up actions

---

## Use Case Analysis

### User-Facing Needs

**What users need to see:**
- Clear, formatted meeting options (e.g., "Monday, Dec 15 at 2:00 PM EST")
- Understandable move descriptions (e.g., "Move 'Team Standup' from 2:00 PM to 3:00 PM")
- Category groupings (Best Options, With Moves, Overrides)
- Priority ordering with visual indicators
- Summary statistics (e.g., "6 free slots, 12 requiring moves")

**What users DON'T need:**
- Raw event IDs (e.g., `"7offpto7upcc4cmitaia5drlso"`)
- Numeric optimization scores (e.g., `priority_score: 1000.0`)
- Internal algorithm details
- Debug information

### Agent-Facing Needs

**What the agent needs to reason about:**
- Event IDs for follow-up actions ("What conflicts with event `evt_123`?")
- Ranking rationale (why Proposal A > Proposal B)
- Score breakdowns (preference_score, free_block_score, priority_score)
- Move feasibility (which events can be moved, which are locked)
- Optimization metadata (how close to optimal, what constraints were relaxed)
- Relationship mappings (proposal → moved events → original calendar state)

**What the agent needs for follow-up queries:**
- "Can we move the 'Chad/Paul' meeting instead?" (requires event ID mapping)
- "Why is Tuesday preferred over Monday?" (requires score comparison)
- "What other options involve moving fewer meetings?" (requires move count analysis)
- "Show me options that don't require moving protected events" (requires protection level metadata)

---

## Dual-Format Proposal

### Structure

```python
{
    # Control/Metadata
    "status": "ok" | "unsat" | "bad_input",
    "error_message": Optional[str],
    "debug": Optional[DebugInfo],  # Technical debugging info
    
    # User-Facing Content (Pre-formatted for display)
    "user_display": {
        "summary": str,  # High-level summary (e.g., "Found 43 meeting options")
        "explanation": str,  # Human-readable explanation
        "formatted_proposals": [
            {
                "rank": int,  # 1, 2, 3, ...
                "category": str,  # "best_options" | "with_moves" | "with_overrides"
                "display_text": str,  # Pre-formatted string
                # Example: "Monday, December 15, 2025 at 1:15 PM EST - 2:00 PM EST\nType: Free slot (zero-conflict)"
                "short_summary": str,  # One-line summary
                # Example: "Monday, Dec 15 at 1:15 PM (Free slot)"
                "move_summary": Optional[str],  # Human-readable move description
                # Example: "Move 'Chad/Paul' meeting 75 minutes later (12:00 PM → 1:15 PM)"
                "override_summary": Optional[str],  # Human-readable override description
                # Example: "Override 'Hold' solo event"
            }
        ],
        "categories": {
            "best_options": {
                "count": int,
                "description": str  # "Zero-conflict slots available immediately"
            },
            "with_moves": {
                "count": int,
                "description": str,  # "Options requiring moving 1 existing meeting"
                "grouped_by_event": {  # Grouped by moved event for clarity
                    "event_id": str,
                    "event_title": str,
                    "owner": str,
                    "options": [proposal_rank_numbers]
                }
            },
            "with_overrides": {
                "count": int,
                "description": str
            }
        }
    },
    
    # Agent-Facing Structured Data
    "agent_data": {
        "proposals": [  # Full structured proposals (existing format)
            {
                "proposal_id": str,  # New: Unique ID for referencing
                "title": str,
                "participants": List[str],
                "start_utc": str,
                "end_utc": str,
                "location": Optional[str],
                "moved_events": [MovedEvent],
                "objective_scores": ObjectiveScores,
                "free_block_stats": Optional[FreeBlockStats],
                "preference_score": float,  # New: Explicit preference score
                "category": str,  # "zero_conflict" | "single_move" | "solo_override" | "multi_move"
                "rank": int,  # Overall rank (1 = best)
            }
        ],
        "event_registry": {  # New: Map event IDs to metadata
            "event_id": {
                "title": str,
                "owner": str,
                "start_utc": str,
                "end_utc": str,
                "locked": bool,
                "protected": bool,
                "flexible": bool,
                "number_of_attendees": int,
                "internal_only": bool,
                "human_readable": str  # "Chad/Paul meeting on Dec 15 at 12:00 PM"
            }
        },
        "ranking_rationale": {  # New: Why proposals are ranked as they are
            "proposal_id": {
                "primary_factors": [
                    {"factor": "zero_conflict", "impact": "high"},
                    {"factor": "free_block_score", "value": 1489.29, "impact": "medium"}
                ],
                "comparison": {  # How this proposal compares to others
                    "better_than": [proposal_ids],
                    "worse_than": [proposal_ids],
                    "tie_breakers": ["preference_score", "time"]
                }
            }
        },
        "optimization_summary": {  # New: High-level optimization insights
            "total_proposals_found": int,
            "zero_conflict_count": int,
            "single_move_count": int,
            "solo_override_count": int,
            "multi_move_count": int,
            "best_score": float,
            "score_range": {"min": float, "max": float},
            "preference_match_count": int,  # How many match user preferences
            "work_hours_compliance": "full" | "partial" | "none"
        },
        "constraints_applied": {  # New: What constraints were active
            "work_hours_enforced": bool,
            "min_gap_minutes": int,
            "locked_events_blocked": int,  # Count of locked events that blocked slots
            "preferences_applied": List[str]  # e.g., ["prefer_thursdays", "avoid_fridays"]
        }
    },
    
    # Cross-Reference Mapping
    "mapping": {  # New: Links between user_display and agent_data
        "rank_to_proposal_id": {1: "prop_abc123", 2: "prop_def456", ...},
        "proposal_id_to_rank": {"prop_abc123": 1, ...},
        "event_id_to_proposals": {
            "evt_789": ["prop_abc123", "prop_xyz789"]  # Which proposals involve this event
        },
        "category_to_proposals": {
            "best_options": ["prop_abc123", "prop_def456"],
            "with_moves": ["prop_ghi789"]
        }
    }
}
```

---

## Benefits of Dual-Format Approach

### ✅ Advantages

1. **Separation of Concerns**
   - User display logic isolated from agent reasoning
   - Formatting can evolve independently
   - Easier to maintain and test

2. **Agent Reasoning Enhancement**
   - Clear access to structured metadata for decision-making
   - Event ID mapping enables precise follow-up queries
   - Ranking rationale supports "why" questions
   - Optimization summary enables strategic planning

3. **User Experience**
   - Pre-formatted text reduces agent formatting errors
   - Consistent presentation across interactions
   - Category grouping improves readability
   - Short summaries enable quick scanning

4. **Traceability**
   - Proposal IDs enable precise references ("Tell me more about option 3")
   - Event registry enables follow-up actions ("Move event `evt_123`")
   - Cross-reference mapping enables bidirectional navigation

5. **Extensibility**
   - Easy to add new metadata without affecting user display
   - Can add agent-specific fields (confidence scores, alternative interpretations)
   - Support for multi-modal outputs (structured + formatted)

### ⚠️ Disadvantages

1. **Increased Complexity**
   - More fields to maintain
   - Potential for inconsistency between formats
   - Larger payload size

2. **Duplication Risk**
   - Same information in multiple places
   - Need to keep formats in sync

3. **Agent Choice**
   - Agent must decide when to use formatted vs structured
   - Could lead to inconsistent behavior

4. **Backward Compatibility**
   - Existing integrations may expect current format
   - Migration path needed

---

## Alternative Approaches

### Alternative 1: Single Format with Metadata Flags

Keep current format but add `_user_display` and `_agent_only` fields:

```python
{
    "proposals": [{
        "start_utc": "...",
        "_user_display": {
            "formatted_time": "Monday, Dec 15 at 2:00 PM EST"
        },
        "_agent_only": {
            "proposal_id": "...",
            "ranking_rationale": {...}
        }
    }]
}
```

**Pros**: Minimal change, backward compatible  
**Cons**: Still mixed concerns, harder to reason about

### Alternative 2: Separate Tool Calls

Two tools: `orchestrate_scheduling` (user-facing) and `orchestrate_scheduling_verbose` (agent-facing).

**Pros**: Clean separation, agent chooses  
**Cons**: Duplicate logic, two calls needed, harder to keep in sync

### Alternative 3: Format Parameter

Add `format: "user" | "agent" | "both"` parameter.

**Pros**: Flexible, backward compatible  
**Cons**: More code paths, agent must know what to request

---

## Recommended Implementation Strategy

### Phase 1: Add Dual Format (Non-Breaking)

1. **Enhance ResponseEnvelope schema** with optional `user_display` and `agent_data` fields
2. **Keep existing fields** for backward compatibility (`proposals`, `explanation`)
3. **Populate both formats** in parallel
4. **Add proposal IDs** and cross-reference mapping

### Phase 2: Agent Integration

1. **Update agent instructions** to prefer `user_display` for presentation
2. **Use `agent_data`** for reasoning and follow-up queries
3. **Test with real queries** to identify gaps

### Phase 3: Migration (Optional)

1. **Deprecate old format** after agent migration
2. **Remove redundant fields** once agent fully uses dual format

### Key Implementation Details

#### Formatting Function

```python
def format_proposal_for_display(proposal: Proposal, rank: int, event_registry: Dict) -> Dict:
    """Generate user-facing formatted content from structured proposal."""
    return {
        "rank": rank,
        "display_text": format_detailed_proposal(proposal, event_registry),
        "short_summary": format_short_summary(proposal),
        "move_summary": format_move_description(proposal.moved_events, event_registry),
        "override_summary": format_override_description(proposal, event_registry)
    }
```

#### Event Registry Builder

```python
def build_event_registry(normalized_data: Dict, all_proposals: List[Proposal]) -> Dict:
    """Build registry of all events mentioned in proposals."""
    registry = {}
    for prop in all_proposals:
        for moved in prop.moved_events:
            if moved.event_id not in registry:
                registry[moved.event_id] = load_event_metadata(moved.event_id, normalized_data)
    return registry
```

#### Ranking Rationale Generator

```python
def generate_ranking_rationale(proposals: List[Proposal]) -> Dict:
    """Explain why proposals are ranked as they are."""
    rationale = {}
    for i, prop in enumerate(proposals):
        rationale[prop.proposal_id] = {
            "primary_factors": identify_primary_factors(prop),
            "comparison": compare_with_others(prop, proposals[:i])
        }
    return rationale
```

---

## Considerations & Edge Cases

### 1. **Privacy & Security**
- Event IDs might be sensitive (expose calendar structure)
- **Mitigation**: Event IDs are already in moved_events, this doesn't add new exposure

### 2. **Payload Size**
- Dual format increases JSON size
- **Mitigation**: Use compression for transmission, lazy-load detailed fields

### 3. **Consistency Guarantees**
- User display and agent data must stay in sync
- **Mitigation**: Generate both from single source of truth (structured proposals)

### 4. **Agent Decision Making**
- When should agent use formatted vs structured?
- **Guidance**: 
  - Use `user_display` for direct presentation to user
  - Use `agent_data` for reasoning, follow-up queries, refinement

### 5. **Error States**
- How to handle partial formatting failures?
- **Mitigation**: Fallback to structured data, log formatting errors

### 6. **Internationalization**
- Formatted times should respect user locale
- **Mitigation**: Format in agent_data timezone context, let agent apply locale

---

## Success Metrics

### Agent Capability Improvements

- **Follow-up Query Accuracy**: Can agent answer "Why is option 3 better than option 5?" (should be 90%+)
- **Event Reference Precision**: Can agent reference specific events in follow-up? (should be 100%)
- **Formatting Quality**: Are user-facing messages consistently well-formatted? (should be 95%+)

### User Experience Improvements

- **Response Clarity**: Users understand options without asking for clarification (measured via feedback)
- **Action Completion**: Users successfully schedule meetings from proposals (measured via conversion)

### Technical Metrics

- **Payload Size**: Average response size increase (target: <20% increase)
- **Generation Time**: Time to generate both formats (target: <100ms overhead)
- **Consistency**: Format sync accuracy (target: 100%)

---

## Conclusion

The dual-format approach provides significant benefits for agent reasoning while maintaining high-quality user presentation. The increased complexity is justified by:

1. **Clear separation of concerns** enabling independent evolution
2. **Enhanced agent reasoning** through structured metadata
3. **Better user experience** through pre-formatted content
4. **Traceability** enabling precise follow-up actions

**Recommendation**: Implement Phase 1 (non-breaking dual format) and validate with agent integration before considering migration away from current format.

---

## Next Steps

1. **Design Review**: Validate schema with team
2. **Prototype Implementation**: Add dual format alongside current format
3. **Agent Testing**: Test with real Letta agent queries
4. **Iterate**: Refine based on agent behavior
5. **Document**: Update agent instructions and tool documentation

