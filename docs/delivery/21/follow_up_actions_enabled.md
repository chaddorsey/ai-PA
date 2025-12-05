# Follow-Up Actions Enabled by Dual-Format Structure

## Overview

The dual-format payload structure enables the Letta agent to perform sophisticated follow-up actions that were previously difficult or impossible. This document outlines specific types of actions enabled by the structured metadata and cross-references.

---

## Categories of Follow-Up Actions

### 1. **Precise Proposal References**

#### Before Dual-Format
- Agent had to parse and extract information from formatted text
- Hard to reference specific proposals reliably
- "Option 3" ambiguous if proposals re-sorted

#### After Dual-Format
- **Proposal IDs enable stable references**: `prop_abc123def456`
- Cross-reference mapping: `rank_to_proposal_id`, `proposal_id_to_rank`
- Agent can say: "Tell me more about proposal `prop_abc123def456`" or "Why is proposal 3 ranked higher than proposal 5?"

**Example Follow-Ups:**
- "Can you show me the details for option 3?" → Agent uses `mapping.rank_to_proposal_id[3]` → Looks up in `agent_data.proposals`
- "Why is the Tuesday option better than Monday?" → Agent uses ranking rationale to explain differences
- "Compare options 2 and 4" → Agent uses proposal IDs and `ranking_rationale` to compare factors

---

### 2. **Event-Specific Calendar Operations**

#### Before Dual-Format
- Event IDs buried in `moved_events` list
- Hard to identify which events are involved across proposals
- No easy way to find all proposals involving a specific event

#### After Dual-Format
- **Event Registry**: Complete metadata for all referenced events
- **Event-to-Proposals Mapping**: `event_id_to_proposals` shows which proposals involve each event
- **Human-Readable Event Descriptions**: `event_metadata.human_readable`

**Example Follow-Ups:**
- "What would happen if we moved the 'Chad/Paul' meeting instead?" → Agent uses `mapping.event_id_to_proposals[event_id]` to find alternative proposals
- "Show me all options that involve moving Sue's calendar" → Agent filters by event owner in registry
- "Can we schedule without moving the 'All-hands meeting'?" → Agent excludes proposals that move that event
- "What other meetings would need to move if we choose option 5?" → Agent looks up proposal's `moved_events` using registry

**Calendar Operations Enabled:**
- **Move specific events**: Agent can call calendar API with `event_id` from registry
- **Check event details**: Agent can look up event metadata (locked, protected, flexible)
- **Find alternatives**: Agent can identify other proposals that don't move specific events
- **Batch operations**: Agent can identify all proposals affecting same event

---

### 3. **Ranking and Optimization Explanations**

#### Before Dual-Format
- Agent had to infer why proposals ranked as they did
- Hard to explain trade-offs
- No visibility into optimization factors

#### After Dual-Format
- **Ranking Rationale**: Explicit factors contributing to each proposal's rank
- **Primary Factors**: Clear indication of what made a proposal rank high/low
- **Comparison Data**: Which proposals rank better/worse and why

**Example Follow-Ups:**
- "Why is Tuesday preferred over Monday?" → Agent uses `ranking_rationale[prop_id].primary_factors` to explain
- "What makes option 1 the best?" → Agent references zero_conflict, free_block_score, etc.
- "Can you show me options that don't require moving protected events?" → Agent uses `objective_scores.protected_events_moved` in proposals
- "Why do these options have similar scores?" → Agent compares ranking factors across proposals

---

### 4. **Refinement and Constraint Adjustment**

#### Before Dual-Format
- Hard to understand what constraints are limiting options
- Difficult to suggest relaxations based on actual blocking factors
- No visibility into optimization summary

#### After Dual-Format
- **Constraints Applied**: Clear documentation of active constraints
- **Optimization Summary**: Statistics on proposal distribution
- **Event Registry**: See which locked events are blocking slots

**Example Follow-Ups:**
- "What if we allowed moving protected events?" → Agent understands current constraints and can suggest relaxation
- "Show me options that match my Thursday preference" → Agent uses `preference_score > 0` to filter
- "Can we expand the time range?" → Agent uses `optimization_summary` to understand current distribution
- "What locked events are preventing better options?" → Agent analyzes `event_registry` and `locked_events_blocked`

**Refinement Queries:**
- "Find more options by allowing multi-move solutions" → Agent can call orchestrator with adjusted constraints
- "What if we relax the work hours requirement?" → Agent understands current `work_hours_enforced` constraint
- "Show me options that prioritize morning meetings" → Agent filters by time and preference_score

---

### 5. **Strategic Decision Support**

#### Before Dual-Format
- Agent couldn't provide strategic insights
- No way to compare optimization approaches
- Limited understanding of trade-offs

#### After Dual-Format
- **Optimization Summary**: Statistics on proposal quality distribution
- **Category Breakdown**: Understanding of solution types available
- **Score Ranges**: Visibility into quality spread

**Example Follow-Ups:**
- "How many options don't require moving meetings?" → Agent uses `optimization_summary.zero_conflict_count`
- "What's the quality difference between free slots and move-required slots?" → Agent compares score ranges
- "Are there better options if we're willing to move multiple meetings?" → Agent uses category counts and scores
- "How well do these options match my preferences?" → Agent uses `preference_match_count` and individual `preference_score`

---

### 6. **Calendar Integration Actions**

#### Direct Calendar Operations Enabled

**Event Movement:**
```python
# Agent can now precisely identify and move events
event_id = agent_data.event_registry["evt_123"].event_id
owner = agent_data.event_registry["evt_123"].owner
new_start = proposal.moved_events[0].new_start
# Call calendar API to move event
```

**Proposal Acceptance:**
```python
# Agent can accept a proposal and execute all moves
proposal = agent_data.proposals[mapping.rank_to_proposal_id[3]]
for moved_event in proposal.moved_events:
    # Move each event using calendar API
    calendar_api.move_event(moved_event.owner, moved_event.event_id, 
                           moved_event.new_start, moved_event.new_end)
# Create new meeting
calendar_api.create_meeting(proposal.start_utc, proposal.end_utc, 
                           proposal.participants)
```

**Conflict Detection:**
```python
# Agent can check if specific events conflict with proposal
proposal = agent_data.proposals[proposal_id]
for moved in proposal.moved_events:
    event_meta = agent_data.event_registry[moved.event_id]
    if event_meta.locked:
        # Warn user this requires moving a locked event
```

---

### 7. **Multi-Tool Orchestration**

The structured data enables the agent to coordinate between the orchestrator and calendar tools:

**Workflow Examples:**

1. **Refinement Loop:**
   - Agent calls orchestrator → Gets proposals
   - User asks: "Can we avoid moving the 'All-hands' meeting?"
   - Agent identifies event_id from registry
   - Agent filters proposals: `[p for p in proposals if event_id not in [m.event_id for m in p.moved_events]]`
   - If no suitable options, agent calls orchestrator again with modified constraints

2. **Progressive Relaxation:**
   - Agent analyzes `optimization_summary.zero_conflict_count` → finds 0
   - Agent suggests: "No free slots available, but 5 options require moving 1 meeting"
   - User accepts exploring moves
   - Agent shows options from `agent_data.proposals` filtered by `category == "single_move"`
   - User selects: "Move the Chad/Paul meeting"
   - Agent uses `mapping.event_id_to_proposals` to find proposals involving that event

3. **Smart Defaults:**
   - Agent analyzes all proposals
   - Identifies highest `free_block_score` from `optimization_summary.best_score`
   - Suggests: "Option 1 has the best free-block score and requires no moves. Shall I schedule it?"
   - Uses `user_display.formatted_proposals[0]` for readable presentation

---

## Specific Query Patterns Enabled

### Pattern 1: "Why" Questions
- **Query**: "Why is option 3 ranked higher than option 7?"
- **Agent Process**:
  1. Get proposal IDs: `prop_3 = mapping.rank_to_proposal_id[3]`, `prop_7 = mapping.rank_to_proposal_id[7]`
  2. Compare `ranking_rationale[prop_3]` vs `ranking_rationale[prop_7]`
  3. Explain differences in primary_factors, comparison.better_than/worse_than

### Pattern 2: "What If" Scenarios
- **Query**: "What if we moved the 'Team Standup' instead of 'Chad/Paul'?"
- **Agent Process**:
  1. Find event_id for 'Team Standup' in `event_registry`
  2. Find proposals involving that event: `mapping.event_id_to_proposals[standup_event_id]`
  3. Present alternatives, or call orchestrator with modified preferences

### Pattern 3: "Filter" Requests
- **Query**: "Show me only options that don't require moving meetings"
- **Agent Process**:
  1. Filter `agent_data.proposals` where `category == "zero_conflict"`
  2. Map back to ranks: `[mapping.proposal_id_to_rank[p.proposal_id] for p in filtered]`
  3. Present using `user_display.formatted_proposals[rank-1]`

### Pattern 4: "Execute" Actions
- **Query**: "Schedule option 2"
- **Agent Process**:
  1. Get proposal: `proposal = agent_data.proposals[mapping.rank_to_proposal_id[2]]`
  2. For each `moved_event` in proposal:
     - Verify event is flexible: `event_registry[moved_event.event_id].flexible`
     - Call calendar API to move event
  3. Create new meeting using proposal times and participants
  4. Confirm completion

### Pattern 5: "Compare" Operations
- **Query**: "Compare Tuesday vs Wednesday options"
- **Agent Process**:
  1. Filter proposals by day of week (parse `start_utc`)
  2. Compare:
     - `free_block_score` from `free_block_stats`
     - `preference_score`
     - `objective_scores` (moved_minutes, protected_events_moved)
  3. Present comparison using `ranking_rationale` factors

---

## Technical Integration Examples

### Example 1: Smart Proposal Selection

```python
def select_best_proposal(agent_data: AgentData, user_preferences: dict) -> str:
    """Agent logic to select best proposal based on user preferences."""
    proposals = agent_data.proposals
    
    # Filter by user preferences
    if user_preferences.get("avoid_moves"):
        proposals = [p for p in proposals if p.category == "zero_conflict"]
    
    if user_preferences.get("prefer_mornings"):
        # Filter by time (parse start_utc)
        proposals = [p for p in proposals if is_morning(p.start_utc)]
    
    # Rank by free_block_score and preference_score
    proposals.sort(key=lambda p: (
        -(p.free_block_stats.free_block_score if p.free_block_stats else 0),
        -(p.preference_score or 0)
    ))
    
    return proposals[0].proposal_id
```

### Example 2: Event-Aware Filtering

```python
def find_alternatives_without_event(
    agent_data: AgentData, 
    mapping: CrossReferenceMapping,
    event_title: str
) -> List[str]:
    """Find proposals that don't involve moving a specific event."""
    # Find event_id from registry
    event_id = None
    for eid, meta in agent_data.event_registry.items():
        if event_title.lower() in meta.human_readable.lower():
            event_id = eid
            break
    
    if not event_id:
        return []
    
    # Get proposals involving this event
    proposals_with_event = mapping.event_id_to_proposals.get(event_id, [])
    all_proposal_ids = {p.proposal_id for p in agent_data.proposals}
    
    # Return proposals NOT involving this event
    return list(all_proposal_ids - set(proposals_with_event))
```

### Example 3: Ranking Explanation

```python
def explain_ranking(
    agent_data: AgentData,
    mapping: CrossReferenceMapping,
    rank1: int,
    rank2: int
) -> str:
    """Explain why one proposal ranks higher than another."""
    prop1_id = mapping.rank_to_proposal_id[rank1]
    prop2_id = mapping.rank_to_proposal_id[rank2]
    
    rationale1 = agent_data.ranking_rationale[prop1_id]
    rationale2 = agent_data.ranking_rationale[prop2_id]
    
    # Compare primary factors
    factors1 = {f.factor: f for f in rationale1.primary_factors}
    factors2 = {f.factor: f for f in rationale2.primary_factors}
    
    explanation = f"Proposal {rank1} ranks higher than {rank2} because:\n"
    
    # Compare zero_conflict
    if "zero_conflict" in factors1 and "zero_conflict" not in factors2:
        explanation += "- Proposal 1 requires no meeting moves (zero-conflict)\n"
        explanation += "- Proposal 2 requires moving meetings\n"
    
    # Compare scores
    if "free_block_score" in factors1 and "free_block_score" in factors2:
        score1 = factors1["free_block_score"].value
        score2 = factors2["free_block_score"].value
        if score1 > score2:
            explanation += f"- Proposal 1 has better free-block score ({score1:.2f} vs {score2:.2f})\n"
    
    return explanation
```

---

## Summary of Enabled Capabilities

### Information Retrieval
- ✅ Precise proposal references via stable IDs
- ✅ Event lookup and metadata access
- ✅ Ranking explanations with factors
- ✅ Cross-referencing between proposals and events

### Decision Support
- ✅ Filter proposals by category, score, or constraints
- ✅ Compare proposals with detailed rationale
- ✅ Understand trade-offs and optimization factors
- ✅ Strategic planning based on summary statistics

### Calendar Operations
- ✅ Move specific events using event IDs
- ✅ Check event constraints (locked, protected, flexible)
- ✅ Execute multi-event moves for proposal acceptance
- ✅ Validate feasibility before executing moves

### Agent Reasoning
- ✅ Answer "why" questions about rankings
- ✅ Handle "what if" scenarios with event alternatives
- ✅ Filter and refine based on user preferences
- ✅ Explain constraints and suggest relaxations

The dual-format structure transforms the orchestrator from a "black box" that returns proposals into a transparent system that enables sophisticated agent reasoning and precise calendar operations.

