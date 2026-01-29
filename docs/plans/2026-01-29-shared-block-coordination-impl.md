# Shared Block Coordination Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable agents to see each other's findings during coordination via shared Letta memory blocks, allowing iterative refinement and cross-agent awareness.

**Architecture:** Coordination blocks are created per-task in Letta. Agents write findings to blocks. Orchestrator polls blocks and can trigger follow-up dispatches. Main agent synthesizes from accumulated block content.

**Tech Stack:** Letta API (blocks, agents), Python asyncio, httpx

---

## Current State

The orchestrator currently:
1. Dispatches agents in parallel
2. Captures responses directly from Letta API
3. Synthesizes from those direct responses
4. Logs events to PostgREST

**Missing:**
- Agents can't see each other's findings
- No iterative/sequential dispatch patterns
- No persistent coordination state in agent memory

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Coordination Task                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Calendar   │    │    Email     │    │    Pulse     │       │
│  │    Agent     │    │    Agent     │    │    Agent     │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         │ write             │ write             │ write          │
│         ▼                   ▼                   ▼                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Shared Coordination Block                   │    │
│  │  task_id: "task-meeting_prep-20260129-..."               │    │
│  │  ─────────────────────────────────────────               │    │
│  │  calendar_findings: "Meeting at 2pm with Alice, Bob"     │    │
│  │  email_findings: "Thread about Q4 budget attached"       │    │
│  │  pulse_findings: "Alice OOO tomorrow"                    │    │
│  │  status: { calendar: done, email: done, pulse: done }    │    │
│  └─────────────────────────────────────────────────────────┘    │
│         │                                                        │
│         │ read                                                   │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │    Main      │  ← Synthesizes final response                 │
│  │    Agent     │                                               │
│  └──────────────┘                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Block Management

### Task 1.1: Create Coordination Block Schema

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

**Step 1: Define block content structure**

The coordination block will store:
```json
{
  "task_id": "task-meeting_prep-20260129-123456",
  "task_type": "meeting_prep",
  "status": "in_progress",
  "context": { "meeting_title": "Board Meeting" },
  "findings": {
    "calendar": null,
    "email": null,
    "pulse": null
  },
  "agent_status": {
    "calendar": "pending",
    "email": "pending",
    "pulse": "pending"
  },
  "created_at": "2026-01-29T12:00:00Z"
}
```

**Step 2: Update CoordinationBlockHandler.start_coordinated_task**

Current implementation creates block but doesn't populate properly. Update to:

```python
async def start_coordinated_task(
    self,
    identity_id: str,
    task_type: str,
    title: str,
    required_agents: List[str],
    context: Dict[str, Any],
) -> Optional[str]:
    """Create coordination block for task.

    Args:
        identity_id: User identity
        task_type: Type of coordination task
        title: Human-readable title
        required_agents: List of agent names that will participate
        context: Request context to share with agents

    Returns:
        task_id if successful, None otherwise
    """
    task_id = f"task-{task_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    block_content = {
        "task_id": task_id,
        "task_type": task_type,
        "title": title,
        "status": "in_progress",
        "context": context,
        "findings": {agent: None for agent in required_agents},
        "agent_status": {agent: "pending" for agent in required_agents},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Create block via Letta API
    response = await self._create_block(
        label=f"coordination_{task_id}",
        value=json.dumps(block_content),
        limit=8000,  # Allow substantial findings
    )

    # Attach block to all participating agents + main agent
    for agent_name in required_agents + ["main"]:
        agent_id = AGENT_IDS.get(agent_name)
        if agent_id:
            await self._attach_block_to_agent(agent_id, response["id"])

    return task_id
```

**Step 3: Implement _create_block and _attach_block_to_agent**

```python
async def _create_block(self, label: str, value: str, limit: int) -> Dict:
    """Create a new block via Letta API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{self._letta_url}/v1/blocks",
            json={"label": label, "value": value, "limit": limit}
        )
        response.raise_for_status()
        return response.json()

async def _attach_block_to_agent(self, agent_id: str, block_id: str) -> bool:
    """Attach block to agent's memory."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{self._letta_url}/v1/agents/{agent_id}/memory/blocks/{block_id}"
        )
        return response.status_code == 200
```

---

### Task 1.2: Implement Block Reading

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

**Step 1: Add get_block_content method**

```python
async def get_block_content(self, task_id: str) -> Optional[Dict]:
    """Read current coordination block content."""
    block_label = f"coordination_{task_id}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # List blocks and find by label
        response = await client.get(f"{self._letta_url}/v1/blocks")
        response.raise_for_status()
        blocks = response.json()

        for block in blocks:
            if block.get("label") == block_label:
                return json.loads(block.get("value", "{}"))

    return None
```

**Step 2: Add get_agent_findings method**

```python
async def get_agent_findings(self, task_id: str, agent_name: str) -> Optional[str]:
    """Get specific agent's findings from block."""
    content = await self.get_block_content(task_id)
    if content:
        return content.get("findings", {}).get(agent_name)
    return None

async def get_all_findings(self, task_id: str) -> Dict[str, str]:
    """Get all agent findings from block."""
    content = await self.get_block_content(task_id)
    if content:
        findings = content.get("findings", {})
        return {k: v for k, v in findings.items() if v is not None}
    return {}
```

---

### Task 1.3: Implement Block Writing

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

**Step 1: Add update_agent_findings method**

```python
async def update_agent_findings(
    self,
    task_id: str,
    agent_name: str,
    findings: str
) -> bool:
    """Update agent's findings in coordination block."""
    block_label = f"coordination_{task_id}"

    # Get current content
    content = await self.get_block_content(task_id)
    if not content:
        return False

    # Update findings and status
    content["findings"][agent_name] = findings
    content["agent_status"][agent_name] = "done"

    # Write back
    return await self._update_block(block_label, json.dumps(content))

async def _update_block(self, label: str, value: str) -> bool:
    """Update block content by label."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Find block ID by label
        response = await client.get(f"{self._letta_url}/v1/blocks")
        blocks = response.json()

        block_id = None
        for block in blocks:
            if block.get("label") == label:
                block_id = block.get("id")
                break

        if not block_id:
            return False

        # Update block
        response = await client.patch(
            f"{self._letta_url}/v1/blocks/{block_id}",
            json={"value": value}
        )
        return response.status_code == 200
```

---

## Phase 2: Agent Integration

### Task 2.1: Create write_coordination_findings Tool

**Files:**
- Create: `letta/tools/write_coordination_findings.py`

Agents need a tool to write their findings to the shared block:

```python
from typing import Dict, Any, Optional

def write_coordination_findings(
    task_id: str,
    findings: str,
) -> Dict[str, Any]:
    """
    Write your findings to the shared coordination block.

    Call this tool when you have gathered information for a coordination task.
    Your findings will be visible to other agents and the main synthesizer.

    Args:
        task_id: The coordination task ID (provided in the coordination prompt)
        findings: Your findings as a formatted string

    Returns:
        Dictionary with status and confirmation
    """
    import httpx
    import os

    try:
        letta_url = os.getenv("LETTA_BASE_URL", "http://letta:8283")

        # Call the coordination handler endpoint
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{letta_url}/v1/coordination/findings",
                json={
                    "task_id": task_id,
                    "agent_name": os.getenv("AGENT_NAME"),  # Set per-agent
                    "findings": findings
                }
            )
            response.raise_for_status()

        return {
            "status": "ok",
            "message": f"Findings written to coordination block for task {task_id}"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e)
        }
```

### Task 2.2: Create read_coordination_context Tool

```python
def read_coordination_context(
    task_id: str,
) -> Dict[str, Any]:
    """
    Read the current coordination context including other agents' findings.

    Use this to see what other agents have contributed before finalizing
    your own findings.

    Args:
        task_id: The coordination task ID

    Returns:
        Dictionary with context and other agents' findings
    """
    import httpx
    import os

    try:
        letta_url = os.getenv("LETTA_BASE_URL", "http://letta:8283")

        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{letta_url}/v1/coordination/{task_id}"
            )
            response.raise_for_status()
            data = response.json()

        return {
            "status": "ok",
            "context": data.get("context", {}),
            "findings": data.get("findings", {}),
            "agent_status": data.get("agent_status", {})
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e)
        }
```

### Task 2.3: Register and Attach Tools to Agents

**Files:**
- Create: `letta/register_coordination_tools.py`
- Create: `letta/attach_coordination_tools.py`

```python
# register_coordination_tools.py
from letta import create_client

client = create_client(base_url="http://localhost:8283")

# Register write_coordination_findings
with open("tools/write_coordination_findings.py") as f:
    source = f.read()

client.create_tool(
    name="write_coordination_findings",
    source_code=source,
    source_type="python"
)

# Register read_coordination_context
with open("tools/read_coordination_context.py") as f:
    source = f.read()

client.create_tool(
    name="read_coordination_context",
    source_code=source,
    source_type="python"
)
```

```python
# attach_coordination_tools.py
COORDINATION_AGENTS = [
    "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",  # calendar
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",  # task
    "agent-b4928949-8012-4436-a3c7-a9e510785147",  # email
    "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",  # pulse
    "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",  # main
]

for agent_id in COORDINATION_AGENTS:
    client.add_tool_to_agent(
        agent_id=agent_id,
        tool_name="write_coordination_findings"
    )
    client.add_tool_to_agent(
        agent_id=agent_id,
        tool_name="read_coordination_context"
    )
```

---

## Phase 3: Orchestrator Updates

### Task 3.1: Add Coordination API Endpoints

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`

Add endpoints for agents to read/write coordination state:

```python
@router.get("/coordination/{task_id}")
async def get_coordination_state(task_id: str):
    """Get current coordination state for agents."""
    if _orchestrator is None:
        raise HTTPException(503, "Orchestrator not initialized")

    content = await _orchestrator._handler.get_block_content(task_id)
    if not content:
        raise HTTPException(404, f"Task not found: {task_id}")

    return content

@router.post("/coordination/findings")
async def submit_findings(
    task_id: str,
    agent_name: str,
    findings: str
):
    """Agent submits findings to coordination block."""
    if _orchestrator is None:
        raise HTTPException(503, "Orchestrator not initialized")

    success = await _orchestrator._handler.update_agent_findings(
        task_id, agent_name, findings
    )

    if not success:
        raise HTTPException(500, "Failed to update findings")

    return {"status": "ok"}
```

### Task 3.2: Update Dispatch Prompts to Include Task ID

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Update `_build_agent_prompt` to include task_id and instructions:

```python
def _build_agent_prompt(
    self,
    agent_config: AgentConfig,
    context: Dict[str, Any],
    task_id: str,
) -> str:
    """Build agent prompt with coordination context."""
    # Substitute context values
    prompt = agent_config.prompt_template
    for key, value in context.items():
        placeholder = "{" + key + "}"
        if placeholder in prompt:
            prompt = prompt.replace(placeholder, str(value))

    # Add coordination instructions
    coordination_instructions = f"""
---
COORDINATION TASK: {task_id}

After gathering your findings, use the write_coordination_findings tool:
- task_id: "{task_id}"
- findings: Your formatted findings

You can also use read_coordination_context to see what other agents have found.
---

"""
    return coordination_instructions + prompt
```

### Task 3.3: Implement Polling for Block Contributions

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Update `_wait_for_contributions` to actually poll blocks:

```python
async def _wait_for_contributions(
    self,
    identity_id: str,
    task_type: TaskType,
    task_id: str,
) -> Dict[str, str]:
    """Wait for agent contributions via block polling.

    Returns:
        Dict of agent_name -> findings
    """
    enabled_agents = task_type.get_enabled_agents()

    # Calculate deadline from max agent timeout + buffer
    max_timeout = max(
        agent.timeout_seconds for agent in enabled_agents.values()
    )
    buffer_seconds = 5
    deadline = time.time() + max_timeout + buffer_seconds
    polling_interval = 0.5

    while time.time() < deadline:
        content = await self._handler.get_block_content(task_id)
        if not content:
            await asyncio.sleep(polling_interval)
            continue

        agent_status = content.get("agent_status", {})
        findings = content.get("findings", {})

        # Check if all agents are done
        all_done = all(
            agent_status.get(name) == "done"
            for name in enabled_agents
        )

        if all_done:
            return {k: v for k, v in findings.items() if v}

        await asyncio.sleep(polling_interval)

    # Return whatever we have at deadline
    content = await self._handler.get_block_content(task_id)
    if content:
        return {k: v for k, v in content.get("findings", {}).items() if v}
    return {}
```

### Task 3.4: Update coordinate() to Use Block-Based Flow

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

```python
async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
    """Execute coordination with shared block architecture."""
    start_time = time.time()

    # Load task type
    try:
        task_type = self._loader.load(request.task_type)
    except TaskTypeNotFoundError:
        return CoordinateResponse(
            status="error",
            task_id="",
            error_message=f"Task type not found: {request.task_type}",
        )

    if not task_type.is_executable():
        return CoordinateResponse(
            status="error",
            task_id="",
            error_message=f"Task type '{request.task_type}' is in draft stage",
        )

    enabled_agents = task_type.get_enabled_agents()

    # Create coordination block (shared state)
    task_id = await self._handler.start_coordinated_task(
        identity_id=request.identity_id,
        task_type=request.task_type,
        title=request.context.get("meeting_title", request.task_type),
        required_agents=list(enabled_agents.keys()),
        context=request.context,  # Share context with agents
    )

    if not task_id:
        return CoordinateResponse(
            status="error",
            task_id="",
            error_message="Failed to create coordination block",
        )

    # Log start
    self._logger.log_event(
        event_type="start",
        task_id=task_id,
        identity_id=request.identity_id,
        task_type=request.task_type,
        task_version=task_type.version,
        data={"agents": list(enabled_agents.keys())},
    )

    # Dispatch all agents (they'll write to shared block)
    await self._dispatch_all_agents(
        task_id=task_id,
        identity_id=request.identity_id,
        task_type=task_type,
        context=request.context,
    )

    # Wait for contributions via block polling
    findings = await self._wait_for_contributions(
        identity_id=request.identity_id,
        task_type=task_type,
        task_id=task_id,
    )

    # Determine completion status from block
    content = await self._handler.get_block_content(task_id)
    agent_status = content.get("agent_status", {}) if content else {}

    agents_completed = [a for a, s in agent_status.items() if s == "done"]
    agents_failed = [a for a, s in agent_status.items() if s in ("timeout", "error")]
    agents_skipped = [a for a in enabled_agents if a not in agent_status]

    # Synthesize
    synthesis = await self._synthesize(task_type, findings, request.context)

    # Complete and archive block
    await self._handler.complete_task(request.identity_id, MAIN_AGENT_ID)

    elapsed_ms = int((time.time() - start_time) * 1000)

    # Log completion
    self._logger.log_event(
        event_type="complete",
        task_id=task_id,
        identity_id=request.identity_id,
        task_type=request.task_type,
        task_version=task_type.version,
        elapsed_ms=elapsed_ms,
        data={
            "agents_completed": agents_completed,
            "agents_failed": agents_failed,
        },
    )

    # Determine status
    if not agents_completed:
        overall_status = "error"
    elif agents_failed:
        overall_status = "partial"
    else:
        overall_status = "complete"

    return CoordinateResponse(
        status=overall_status,
        task_id=task_id,
        synthesis=synthesis,
        findings=findings,
        agents_completed=agents_completed,
        agents_failed=agents_failed,
        agents_skipped=agents_skipped,
        coordination_time_ms=elapsed_ms,
    )
```

---

## Phase 4: Advanced Patterns

### Task 4.1: Sequential Dispatch Support

Enable patterns like "Calendar first, then Pulse with Calendar's findings":

```python
# In task_type YAML:
dispatch_mode: sequential  # or "parallel" (default)
dispatch_order:
  - calendar
  - email  # Runs after calendar, can see calendar's findings
  - pulse  # Runs after email, can see calendar + email findings
```

```python
async def _dispatch_sequential(
    self,
    task_id: str,
    task_type: TaskType,
    context: Dict[str, Any],
) -> None:
    """Dispatch agents sequentially, each seeing previous findings."""
    enabled_agents = task_type.get_enabled_agents()
    order = task_type.dispatch_order or list(enabled_agents.keys())

    for agent_name in order:
        if agent_name not in enabled_agents:
            continue

        agent_config = enabled_agents[agent_name]

        # Build prompt with current findings context
        current_findings = await self._handler.get_all_findings(task_id)
        prompt = self._build_agent_prompt_with_findings(
            agent_config, context, task_id, current_findings
        )

        # Dispatch and wait for this agent
        await self._dispatch_to_agent(
            agent_name=agent_name,
            prompt=prompt,
            task_id=task_id,
            timeout=agent_config.timeout_seconds,
        )

        # Wait for this agent's contribution before next
        await self._wait_for_agent(task_id, agent_name, agent_config.timeout_seconds)
```

### Task 4.2: Conditional Dispatch Support

Only dispatch certain agents based on previous findings:

```python
# In task_type YAML:
agents:
  pulse:
    condition: "calendar_findings contains 'participants'"
    prompt_template: |
      Check availability for these participants from calendar:
      {calendar_findings}
```

```python
def _should_dispatch_agent(
    self,
    agent_config: AgentConfig,
    current_findings: Dict[str, str],
) -> bool:
    """Evaluate if agent should be dispatched based on conditions."""
    if not agent_config.condition:
        return True

    # Simple condition evaluation
    condition = agent_config.condition

    # "X contains 'Y'" pattern
    if " contains " in condition:
        field, value = condition.split(" contains ")
        field = field.strip()
        value = value.strip().strip("'\"")

        field_content = current_findings.get(field.replace("_findings", ""), "")
        return value.lower() in field_content.lower()

    return True
```

---

## Phase 5: Testing

### Task 5.1: Unit Tests for Block Operations

```python
class TestCoordinationBlockHandler:
    @pytest.mark.asyncio
    async def test_create_and_read_block(self):
        """Block content can be created and read."""
        handler = CoordinationBlockHandler("http://localhost:8283")

        task_id = await handler.start_coordinated_task(
            identity_id="test-identity",
            task_type="meeting_prep",
            title="Test Meeting",
            required_agents=["calendar", "email"],
            context={"meeting_title": "Test"},
        )

        content = await handler.get_block_content(task_id)

        assert content["task_id"] == task_id
        assert content["findings"]["calendar"] is None
        assert content["agent_status"]["calendar"] == "pending"

    @pytest.mark.asyncio
    async def test_update_findings(self):
        """Agent findings can be written and read."""
        handler = CoordinationBlockHandler("http://localhost:8283")

        task_id = await handler.start_coordinated_task(...)

        await handler.update_agent_findings(
            task_id, "calendar", "Meeting at 2pm"
        )

        findings = await handler.get_agent_findings(task_id, "calendar")
        assert findings == "Meeting at 2pm"
```

### Task 5.2: Integration Test with Real Agents

```python
@pytest.mark.live
@pytest.mark.asyncio
async def test_full_coordination_with_blocks():
    """Full coordination with shared block communication."""
    response = await client.post(
        "/v1/coordinate",
        json={
            "identity_id": "test-identity",
            "task_type": "meeting_prep",
            "context": {"meeting_title": "Board Meeting"},
        }
    )

    data = response.json()

    # Verify findings came from block
    assert data["status"] == "complete"
    assert "calendar" in data["findings"]

    # Verify block was created and populated
    block_response = await client.get(f"/v1/coordination/{data['task_id']}")
    block_data = block_response.json()

    assert block_data["findings"]["calendar"] is not None
    assert block_data["agent_status"]["calendar"] == "done"
```

---

## Migration Path

### From Direct Response to Shared Blocks

1. **Phase 1**: Add block management (no behavior change)
2. **Phase 2**: Register tools but don't require them
3. **Phase 3**: Update prompts to include task_id
4. **Phase 4**: Add block polling as secondary source
5. **Phase 5**: Make block writing primary, direct response fallback
6. **Phase 6**: Remove direct response capture (blocks only)

### Backwards Compatibility

- Keep direct response capture as fallback
- Agents without coordination tools still work
- Gradual rollout per task type

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Block created per task | Check Letta blocks API |
| Agents can write findings | Tool invocation in logs |
| Agents can read others' findings | read_coordination_context calls |
| Polling detects contributions | Completion without direct response |
| Sequential patterns work | Calendar findings in Pulse prompt |
| Cross-agent awareness | Pulse mentions Calendar-found participants |

---

## Estimated Complexity

| Phase | Tasks | Dependencies |
|-------|-------|--------------|
| Phase 1: Block Management | 3 tasks | None |
| Phase 2: Agent Integration | 3 tasks | Phase 1 |
| Phase 3: Orchestrator Updates | 4 tasks | Phase 1, 2 |
| Phase 4: Advanced Patterns | 2 tasks | Phase 3 |
| Phase 5: Testing | 2 tasks | Phase 3 |

**Total: 14 tasks**

Phase 1-3 are required for basic shared block coordination.
Phase 4-5 are enhancements for advanced patterns.
