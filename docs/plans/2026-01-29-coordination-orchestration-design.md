# Multi-Agent Coordination Orchestration Design

> **Status:** Design complete, ready for implementation
> **Date:** 2026-01-29
> **Related:** [Multi-Agent Coordination Design](./2026-01-28-multi-agent-coordination-design.md)
> **Philosophy:** Lean/MVP approach - conversational discovery with observability for pattern honing

## Overview

This design adds orchestration to the existing CoordinationBlockHandler infrastructure, enabling the Main Agent to coordinate specialist agents (Calendar, Document, Email, Pulse) for complex tasks like "prep me for my next meeting."

**Key Principles:**
- **V1 Mindset**: Start conversational, discover patterns, graduate to structure
- **Supervisor Pattern**: Handler orchestrates, agents contribute, Main Agent synthesizes
- **Observability First**: Log everything to enable pattern discovery
- **No Premature UI**: Let usage patterns emerge before building structured interfaces

---

## Architecture

### Flow Overview

```
User: "Prep me for my next meeting"
         ↓
    Main Agent (via normal routing)
         ↓
    Conversational clarification
    "Which meeting? What focus areas?"
         ↓
    User provides context
         ↓
    Main Agent calls coordinate_task tool
         ↓
    POST /coordinate (with full context)
         ↓
┌────────────────────────────────────┐
│     Coordination Orchestrator      │
│  1. Initialize blocks              │
│  2. Dispatch agents (parallel)     │
│  3. Collect findings               │
│  4. Synthesize response            │
│  5. Archive & cleanup              │
└────────────────────────────────────┘
         ↓
    Synthesized response to Main Agent
         ↓
    Main Agent delivers to user
```

### Key Insight: Main Agent as Conversation Layer

The Main Agent handles:
- Natural language understanding
- Clarifying questions (conversationally)
- Context gathering
- Final delivery to user

The `/coordinate` endpoint handles:
- Agent dispatch
- Block management
- Findings collection
- Response synthesis

This separation means the orchestrator receives **fully-clarified context**, not ambiguous requests.

---

## API Design

### Endpoint: `POST /v1/coordinate`

Called by Main Agent after gathering context conversationally.

**Request:**
```json
{
    "identity_id": "identity-123",
    "task_type": "meeting_prep",
    "context": {
        "meeting_identifier": "Board Meeting tomorrow 2pm",
        "event_id": "event-abc123",
        "focus_areas": ["participants", "prep_materials", "recent_context"],
        "depth": "thorough",
        "additional_context": "User mentioned Alice has timeline concerns"
    },
    "conversation_id": "conv-456"
}
```

**Response:**
```json
{
    "status": "complete",
    "task_id": "task-meeting-prep-20260129-143000",
    "synthesis": "**Board Meeting** - Tomorrow 2:00 PM\n\n**Participants:**\n- Alice Chen...",
    "findings": {
        "calendar": "[Calendar 14:30] Board Meeting, 2pm Jan 30, 3 participants confirmed",
        "document": "[Document 14:31] Q4 Budget deck updated yesterday, 2 action items pending",
        "email": "[Email 14:31] Alice flagged timeline, Bob confirmed ready",
        "pulse": "[Pulse 14:32] Carol OOO Friday"
    },
    "agents_completed": ["calendar", "document", "email", "pulse"],
    "agents_failed": [],
    "coordination_time_ms": 4500
}
```

---

## Task Type Configuration

Minimal configuration - just enough to know which agents to dispatch and how to synthesize.

```python
TASK_TYPES = {
    "meeting_prep": {
        "agents": ["calendar", "document", "email", "pulse"],
        "synthesis_mode": "template_with_enhancement",
        "template": """**{meeting_title}** - {meeting_time}

**Participants:**
{participant_details}

**Prep Materials:**
{document_findings}

**Recent Context:**
{email_findings}

**Availability Notes:**
{pulse_findings}
""",
        "main_agent_prompt": "Review these findings and add any insights about preparation priorities or potential issues.",
        "timeout_seconds": 30
    },

    "project_status": {
        "agents": ["document", "email", "task"],
        "synthesis_mode": "main_agent_only",
        "main_agent_prompt": "Synthesize these findings into a concise project status update.",
        "timeout_seconds": 45
    },

    "weekly_prep": {
        "agents": ["calendar", "task", "email"],
        "synthesis_mode": "template_only",
        "template": "...",
        "timeout_seconds": 30
    }
}
```

**Synthesis Modes:**
- `template_only`: Use template, no LLM call
- `template_with_enhancement`: Template + Main Agent polish
- `main_agent_only`: Main Agent synthesizes from scratch

---

## Orchestration Implementation

### Phase 1: Initialize

```python
async def coordinate(request: CoordinateRequest) -> CoordinateResponse:
    task_config = TASK_TYPES[request.task_type]

    # Start coordinated task (creates blocks)
    task_id = coordination_handler.start_coordinated_task(
        identity_id=request.identity_id,
        task_type=request.task_type,
        context=request.context,
        required_agents=task_config["agents"]
    )

    # Log coordination start
    log_coordination_event("start", task_id, request)
```

### Phase 2: Dispatch Agents (Parallel)

```python
    # Build agent-specific prompts from context
    agent_prompts = build_agent_prompts(request.context, task_config)

    # Dispatch all agents in parallel
    dispatch_tasks = [
        dispatch_to_agent(agent, agent_prompts[agent], request.identity_id)
        for agent in task_config["agents"]
    ]

    results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)

    # Log dispatch results
    for agent, result in zip(task_config["agents"], results):
        log_coordination_event("agent_dispatch", task_id, {
            "agent": agent,
            "success": not isinstance(result, Exception),
            "error": str(result) if isinstance(result, Exception) else None
        })
```

### Phase 3: Collect Findings

```python
    # Poll for agent contributions (with timeout)
    deadline = time.time() + task_config["timeout_seconds"]

    while time.time() < deadline:
        status = coordination_handler.get_task_status(request.identity_id)

        if coordination_handler.is_task_complete(request.identity_id):
            break

        # Check for new contributions
        for agent in task_config["agents"]:
            if status.get(agent) == "pending":
                if coordination_handler.check_agent_contribution(
                    request.identity_id, agent
                ):
                    log_coordination_event("agent_contributed", task_id, {
                        "agent": agent
                    })

        await asyncio.sleep(0.5)  # Poll interval

    # Get gathered findings
    findings = coordination_handler.get_gathered_findings(request.identity_id)
```

### Phase 4: Synthesize Response

```python
    synthesis_mode = task_config["synthesis_mode"]

    if synthesis_mode == "template_only":
        synthesis = apply_template(task_config["template"], findings, request.context)

    elif synthesis_mode == "template_with_enhancement":
        template_output = apply_template(task_config["template"], findings, request.context)
        synthesis = await enhance_with_main_agent(
            template_output,
            task_config["main_agent_prompt"]
        )

    elif synthesis_mode == "main_agent_only":
        synthesis = await synthesize_with_main_agent(
            findings,
            task_config["main_agent_prompt"]
        )

    # Log synthesis
    log_coordination_event("synthesis", task_id, {
        "mode": synthesis_mode,
        "findings_count": len(findings),
        "synthesis_length": len(synthesis)
    })
```

### Phase 5: Archive & Cleanup

```python
    # Archive completed task
    coordination_handler.complete_task(request.identity_id)

    # Log completion
    log_coordination_event("complete", task_id, {
        "agents_completed": [a for a, s in status.items() if s == "done"],
        "agents_failed": [a for a, s in status.items() if s in ("error", "timeout")],
        "total_time_ms": (time.time() - start_time) * 1000
    })

    return CoordinateResponse(
        status="complete",
        task_id=task_id,
        synthesis=synthesis,
        findings=findings,
        ...
    )
```

---

## Main Agent Integration

The Main Agent needs a tool to trigger coordination. This is simpler than having the endpoint handle natural language.

### coordinate_task Tool

```python
def coordinate_task(
    task_type: str,
    context: str
) -> Dict[str, Any]:
    """
    Trigger multi-agent coordination for complex tasks.

    Args:
        task_type: Type of coordination task (meeting_prep, project_status, weekly_prep)
        context: JSON string with task-specific context gathered from conversation

    Returns:
        Dictionary with synthesis and findings from specialist agents.
    """
    import json
    import requests

    try:
        context_dict = json.loads(context)

        response = requests.post(
            "http://pa-routing-handler:5201/v1/coordinate",
            json={
                "identity_id": get_current_identity_id(),
                "task_type": task_type,
                "context": context_dict
            },
            timeout=60
        )

        return response.json()

    except Exception as e:
        return {"status": "error", "error_message": str(e)}
```

### Main Agent Persona Addition

```
## Multi-Agent Coordination

For complex tasks requiring multiple information sources (meeting prep, project status, weekly planning), you can coordinate specialist agents.

**How to use:**
1. Gather context conversationally - ask clarifying questions
2. Once you have enough context, call coordinate_task() with:
   - task_type: "meeting_prep", "project_status", or "weekly_prep"
   - context: JSON with gathered details

**Example flow:**
User: "Prep me for my next meeting"
You: "Which meeting would you like to prep for? I see:
     - Board Meeting (tomorrow 2pm)
     - 1:1 with Sarah (tomorrow 4pm)"
User: "Board meeting, I need to know about participants"
You: *calls coordinate_task("meeting_prep", {"meeting": "Board Meeting", "focus": ["participants"]})*
You: *delivers synthesized response*
```

---

## Observability Layer

### Logging Schema

All coordination events logged to enable pattern discovery.

```python
@dataclass
class CoordinationLogEntry:
    timestamp: datetime
    event_type: str  # start, agent_dispatch, agent_contributed, synthesis, complete, error
    task_id: str
    identity_id: str
    task_type: str

    # Event-specific data
    data: Dict[str, Any]

    # Metrics
    elapsed_ms: Optional[int] = None
```

### Events to Log

| Event | Data Captured | Analysis Purpose |
|-------|---------------|------------------|
| `start` | task_type, context provided | What tasks are requested |
| `agent_dispatch` | agent, prompt used | Which agents get dispatched |
| `agent_contributed` | agent, contribution length | Agent response quality |
| `agent_timeout` | agent, elapsed_ms | Reliability issues |
| `agent_error` | agent, error_message | Failure patterns |
| `synthesis` | mode, input_length, output_length | Synthesis effectiveness |
| `complete` | total_time_ms, agents_completed | End-to-end performance |

### Storage

For MVP, log to a dedicated table in Supabase:

```sql
CREATE TABLE pa_web.coordination_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    elapsed_ms INT
);

CREATE INDEX idx_coordination_logs_task ON pa_web.coordination_logs(task_id);
CREATE INDEX idx_coordination_logs_type ON pa_web.coordination_logs(task_type);
CREATE INDEX idx_coordination_logs_time ON pa_web.coordination_logs(timestamp);
```

### Future Analysis Queries

```sql
-- Most common task types
SELECT task_type, COUNT(*) FROM pa_web.coordination_logs
WHERE event_type = 'complete'
GROUP BY task_type;

-- Agent reliability
SELECT
    data->>'agent' as agent,
    COUNT(*) FILTER (WHERE event_type = 'agent_contributed') as successes,
    COUNT(*) FILTER (WHERE event_type = 'agent_timeout') as timeouts,
    COUNT(*) FILTER (WHERE event_type = 'agent_error') as errors
FROM pa_web.coordination_logs
GROUP BY data->>'agent';

-- Average coordination time by task type
SELECT
    task_type,
    AVG(elapsed_ms) as avg_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY elapsed_ms) as p95_ms
FROM pa_web.coordination_logs
WHERE event_type = 'complete'
GROUP BY task_type;

-- Context patterns (what fields are usually provided)
SELECT
    task_type,
    jsonb_object_keys(data->'context') as context_field,
    COUNT(*) as frequency
FROM pa_web.coordination_logs
WHERE event_type = 'start'
GROUP BY task_type, jsonb_object_keys(data->'context');
```

---

## Error Handling

| Failure | Handling |
|---------|----------|
| Agent times out | Mark as "timeout", continue with others, note in synthesis |
| Agent errors | Mark as "error", continue with others, note in synthesis |
| Agent doesn't contribute | Mark as "no_contribution", continue |
| All agents fail | Return partial error response, log for analysis |
| Partial success | Return available findings, note which agents failed |
| Main Agent synthesis fails | Fall back to template-only or raw findings |
| Coordination timeout | Return whatever was gathered, note incomplete |

---

## Implementation Tasks

1. **Create `/v1/coordinate` endpoint** in routing handler
2. **Implement orchestration flow** (dispatch, collect, synthesize)
3. **Create `coordinate_task` tool** for Main Agent
4. **Update Main Agent persona** with coordination instructions
5. **Create logging infrastructure** (table + logging functions)
6. **Add task type configurations** (meeting_prep first)
7. **Integration test** with real agents

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Main Agent can trigger coordination | Tool call works, agents dispatched |
| Parallel dispatch works | 4 agents complete in <10s total (not 40s) |
| Findings are gathered | `coordination_gathered` block populated |
| Synthesis produces usable output | Response includes all agent contributions |
| Logging captures events | Logs queryable for pattern analysis |
| Errors handled gracefully | Partial failures don't crash coordination |

---

## Future Evolution (Post-Pattern Discovery)

Once logging reveals stable patterns:

1. **Structured UI shortcuts** - Slack buttons for common task types
2. **Smart defaults** - Auto-detect meeting from calendar
3. **Agent pruning** - Remove consistently unhelpful agents from task types
4. **Prompt refinement** - Improve agent prompts based on contribution quality
5. **Caching** - Cache coordination for repeated similar requests

The observability layer enables all of these without upfront over-engineering.
