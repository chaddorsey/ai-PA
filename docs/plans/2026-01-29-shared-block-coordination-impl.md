# Shared Block Coordination Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable agents to participate in coordinated tasks by writing findings to shared memory blocks, allowing cross-agent awareness and iterative refinement.

**Architecture:** Three-block system per identity with natural language format. Agents append to gathered block via `memory_insert`. Orchestrator polls for contributions.

**Tech Stack:** Letta API (blocks, agents, memory_insert), Python asyncio, httpx

---

## Current State

The orchestrator currently:
1. Creates coordination blocks (task, gathered, status)
2. Dispatches agents in parallel
3. **Captures direct responses** from Letta API ← Problem
4. Synthesizes from those direct responses
5. Logs events to PostgREST

**What's Missing:**
1. Blocks are not attached to participating agents
2. Agent system prompts don't include coordination protocol
3. Orchestrator captures direct responses instead of polling blocks
4. Agents respond directly instead of using `memory_insert` to write to gathered block

---

## Architecture (Three-Block System)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Coordination Task                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │     coordination_task_{identity_id} (READ ONLY)          │   │
│  │     "Meeting prep for Board Meeting..."                   │   │
│  │     Handler writes, all agents read                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                   │                   │                │
│         │ read              │ read              │ read           │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Calendar   │    │    Email     │    │    Pulse     │       │
│  │    Agent     │    │    Agent     │    │    Agent     │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         │ memory_insert     │ memory_insert     │ memory_insert  │
│         ▼                   ▼                   ▼                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │     coordination_gathered_{identity_id} (APPEND ONLY)    │   │
│  │     [Calendar 14:30] Board Meeting, 2pm, 3 participants  │   │
│  │     [Email 14:31] 3 threads: Alice timeline concern...   │   │
│  │     [Pulse 14:32] Bob OOO tomorrow, Alice remote Wed     │   │
│  │     Agents append via memory_insert, handler reads       │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                        │
│         │ parse via get_gathered_findings()                      │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │    Main      │  ← Synthesizes final response                 │
│  │    Agent     │                                               │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │     coordination_status_{identity_id} (HANDLER ONLY)     │   │
│  │     {"calendar":"done","email":"done","pulse":"pending"} │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Block Attachment

### Task 1.1: Add attach_block_to_agent Method

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

**Step 1: Add the attachment method**

```python
async def attach_block_to_agent(self, block_id: str, agent_id: str) -> bool:
    """Attach a block to an agent's memory.

    Args:
        block_id: Block ID to attach
        agent_id: Agent ID to attach to

    Returns:
        True if successful
    """
    try:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/agents/{agent_id}/memory/blocks/{block_id}"
            )
            if response.status_code == 200:
                logger.info("block_attached", block_id=block_id, agent_id=agent_id)
                return True
            logger.warning(
                "block_attach_failed",
                block_id=block_id,
                agent_id=agent_id,
                status=response.status_code
            )
            return False
    except Exception as e:
        logger.warning("block_attach_error", error=str(e))
        return False
```

**Step 2: Add detach_block_from_agent method**

```python
async def detach_block_from_agent(self, block_id: str, agent_id: str) -> bool:
    """Detach a block from an agent's memory."""
    try:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(
                f"{self.base_url}/v1/agents/{agent_id}/memory/blocks/{block_id}"
            )
            return response.status_code == 200
    except Exception as e:
        logger.warning("block_detach_error", error=str(e))
        return False
```

---

### Task 1.2: Update start_coordinated_task to Attach Blocks

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

**Step 1: Add required_agents parameter for block attachment**

Update `start_coordinated_task` to attach coordination blocks to all participating agents:

```python
async def start_coordinated_task(
    self,
    identity_id: str,
    task_type: str,
    title: str,
    event_id: Optional[str] = None,
    participants: Optional[list[str]] = None,
    required_agents: Optional[list[str]] = None,
    agent_ids: Optional[Dict[str, str]] = None,  # NEW: agent_name -> agent_id mapping
) -> Optional[str]:
    # ... existing block creation code ...

    # NEW: Attach task and gathered blocks to all participating agents
    if agent_ids:
        for agent_name, agent_id in agent_ids.items():
            if agent_name in agents:
                # Attach task block (read only for agents)
                await self.attach_block_to_agent(task_block_id, agent_id)
                # Attach gathered block (agents will memory_insert here)
                await self.attach_block_to_agent(gathered_block_id, agent_id)
                logger.info(
                    "coordination_blocks_attached",
                    agent_name=agent_name,
                    identity_id=identity_id
                )

    return task_id
```

---

### Task 1.3: Update complete_task to Detach Blocks

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`

After archiving, detach blocks from agents to clean up:

```python
async def complete_task(
    self,
    identity_id: str,
    main_agent_id: str,
    agent_ids: Optional[Dict[str, str]] = None,  # NEW
) -> bool:
    # ... existing archival code ...

    # NEW: Detach blocks from agents
    if agent_ids:
        task_block = await self.get_block_by_label(f"coordination_task_{identity_id}")
        gathered_block = await self.get_block_by_label(f"coordination_gathered_{identity_id}")

        for agent_id in agent_ids.values():
            if task_block:
                await self.detach_block_from_agent(task_block["id"], agent_id)
            if gathered_block:
                await self.detach_block_from_agent(gathered_block["id"], agent_id)

    # ... existing reset code ...
```

---

## Phase 2: Agent System Prompt Updates

### Task 2.1: Create Coordination Protocol Persona Block

**Files:**
- Create: `letta/blocks/coordination_protocol.txt`

This block will be attached to each specialist agent's persona:

```
<coordination_protocol>
When participating in multi-agent tasks, you'll see these memory blocks:

1. coordination_task (READ ONLY)
   - Contains current task context and what you need to contribute
   - Read this to understand your role
   - DO NOT modify this block

2. coordination_gathered (APPEND ONLY)
   - When you finish your work, call memory_insert to add ONE line
   - Tool: memory_insert("coordination_gathered", "[YourName HH:MM] Summary")
   - Format: [AgentName HH:MM] Brief summary (under 100 chars)
   - Example: [Calendar 10:30] Board Meeting, 2pm Jan 30, 3 participants
   - DO NOT use memory_replace or memory_rethink on this block

3. coordination_status (DO NOT TOUCH)
   - Handler uses this to track progress
   - You never need to read or modify this

Workflow:
1. Read coordination_task to understand what's needed
2. Do your specialized work (search, analyze, etc.)
3. Summarize findings in ONE line via memory_insert to coordination_gathered
4. Your part is done - handler will route to next agent if needed

If you encounter errors or can't complete your part, note it in your response and still add a line like:
[YourName HH:MM] Unable to complete - {brief reason}
</coordination_protocol>
```

### Task 2.2: Register Protocol Block with Agents

**Files:**
- Create: `letta/attach_coordination_protocol.py`

Script to attach the coordination protocol to each specialist agent:

```python
"""Attach coordination protocol to specialist agents."""

import httpx

LETTA_URL = "http://localhost:8283"

# Specialist agents that participate in coordination
COORDINATION_AGENTS = {
    "calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "email": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "pulse": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
    # Add others as needed
}

# Read protocol content
with open("blocks/coordination_protocol.txt") as f:
    protocol_content = f.read()

# Create protocol block
with httpx.Client(timeout=30.0) as client:
    # Check if block exists
    response = client.get(f"{LETTA_URL}/v1/blocks/", params={"label": "coordination_protocol"})
    blocks = response.json()

    if blocks:
        block_id = blocks[0]["id"]
        # Update existing
        client.patch(f"{LETTA_URL}/v1/blocks/{block_id}", json={"value": protocol_content})
        print(f"Updated coordination_protocol block: {block_id}")
    else:
        # Create new
        response = client.post(
            f"{LETTA_URL}/v1/blocks/",
            json={
                "label": "coordination_protocol",
                "value": protocol_content,
                "description": "Coordination protocol for multi-agent tasks",
                "limit": 2000,
            }
        )
        block_id = response.json()["id"]
        print(f"Created coordination_protocol block: {block_id}")

    # Attach to all coordination agents
    for agent_name, agent_id in COORDINATION_AGENTS.items():
        response = client.post(
            f"{LETTA_URL}/v1/agents/{agent_id}/memory/blocks/{block_id}"
        )
        if response.status_code == 200:
            print(f"Attached protocol to {agent_name}")
        else:
            print(f"Failed to attach to {agent_name}: {response.status_code}")
```

---

## Phase 3: Orchestrator Flow Changes

### Task 3.1: Pass Agent IDs to Handler

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Update `coordinate()` to pass agent_ids to handler methods:

```python
# In coordinate():

# Build agent_ids mapping for enabled agents
agent_ids = {
    name: AGENT_IDS[name]
    for name in enabled_agents
    if name in AGENT_IDS
}

# Update start_coordinated_task call
task_id = await self._handler.start_coordinated_task(
    identity_id=request.identity_id,
    task_type=request.task_type,
    title=request.context.get("meeting_title", request.task_type),
    event_id=request.context.get("event_id"),
    participants=request.context.get("participants", []),
    required_agents=list(enabled_agents.keys()),
    agent_ids=agent_ids,  # NEW
)

# ... later ...

# Update complete_task call
await self._handler.complete_task(
    request.identity_id,
    MAIN_AGENT_ID,
    agent_ids=agent_ids,  # NEW
)
```

---

### Task 3.2: Update Dispatch to Not Capture Direct Response

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Change `_dispatch_to_agent` to send the prompt but NOT return the direct response. The agent should write to the gathered block instead.

```python
async def _dispatch_to_agent(
    self,
    agent_name: str,
    prompt: str,
    identity_id: str,
    task_id: str,
    task_type: str,
    timeout: int,
) -> bool:
    """Dispatch a single agent.

    Sends message to agent. Agent is expected to write findings to
    coordination_gathered block via memory_insert.

    Returns:
        True if message sent successfully, False otherwise
    """
    agent_id = AGENT_IDS.get(agent_name)
    if not agent_id:
        logger.warning("agent_not_found", agent_name=agent_name)
        return False

    # Log dispatch event
    self._logger.log_event(
        event_type="agent_dispatch",
        task_id=task_id,
        identity_id=identity_id,
        task_type=task_type,
        data={"agent": agent_name, "timeout_seconds": timeout},
    )

    try:
        # Send message to agent - agent will process and memory_insert to gathered block
        await asyncio.wait_for(
            self._send_to_letta(agent_id, prompt, identity_id),
            timeout=timeout,
        )
        return True

    except asyncio.TimeoutError:
        self._logger.log_event(
            event_type="agent_timeout",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type,
            data={"agent": agent_name, "timeout_seconds": timeout},
        )
        return False

    except Exception as e:
        self._logger.log_event(
            event_type="agent_error",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type,
            data={"agent": agent_name, "error": str(e)},
        )
        return False
```

---

### Task 3.3: Implement Polling for Block Contributions

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Update `_wait_for_contributions` to actually poll the gathered block:

```python
async def _wait_for_contributions(
    self,
    identity_id: str,
    task_type: TaskType,
    task_id: str,
) -> Dict[str, str]:
    """Wait for agent contributions by polling the gathered block.

    Polls coordination_gathered_{identity_id} block looking for
    [AgentName HH:MM] patterns indicating agent contributions.

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
    polling_interval = 1.0  # Check every second

    agents_found = set()

    while time.time() < deadline:
        # Check each agent's contribution
        for agent_name in enabled_agents:
            if agent_name in agents_found:
                continue

            contributed = await self._handler.check_agent_contribution(
                identity_id, agent_name
            )
            if contributed:
                agents_found.add(agent_name)
                self._logger.log_event(
                    event_type="agent_contributed",
                    task_id=task_id,
                    identity_id=identity_id,
                    task_type=task_type.name,
                    data={"agent": agent_name},
                )

        # Check if all agents done
        if agents_found == set(enabled_agents.keys()):
            break

        await asyncio.sleep(polling_interval)

    # Get parsed findings from gathered block
    findings = await self._handler.get_gathered_findings(identity_id)
    return findings
```

---

### Task 3.4: Update coordinate() Main Flow

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`

Wire together the updated flow:

```python
async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
    """Execute a coordination task with shared block architecture."""
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
    agent_ids = {
        name: AGENT_IDS[name]
        for name in enabled_agents
        if name in AGENT_IDS
    }

    # Create coordination blocks and attach to agents
    task_id = await self._handler.start_coordinated_task(
        identity_id=request.identity_id,
        task_type=request.task_type,
        title=request.context.get("meeting_title", request.task_type),
        event_id=request.context.get("event_id"),
        participants=request.context.get("participants", []),
        required_agents=list(enabled_agents.keys()),
        agent_ids=agent_ids,
    )

    if not task_id:
        return CoordinateResponse(
            status="error",
            task_id="",
            error_message="Failed to create coordination blocks",
        )

    # Log start
    self._logger.log_event(
        event_type="start",
        task_id=task_id,
        identity_id=request.identity_id,
        task_type=request.task_type,
        task_version=task_type.version,
        data={
            "context": request.context,
            "agents": list(enabled_agents.keys()),
        },
    )

    # Dispatch all agents (they will write to gathered block)
    dispatch_results = await self._dispatch_all_agents(
        task_id=task_id,
        identity_id=request.identity_id,
        task_type=task_type,
        context=request.context,
    )

    # Wait for contributions by polling gathered block
    findings = await self._wait_for_contributions(
        identity_id=request.identity_id,
        task_type=task_type,
        task_id=task_id,
    )

    # Determine completion status from gathered findings
    agents_completed = list(findings.keys())
    agents_failed = [
        name for name in enabled_agents
        if name not in findings and name in agent_ids
    ]
    agents_skipped = [
        name for name in enabled_agents
        if name not in agent_ids
    ]

    # Synthesize response
    synthesis = await self._synthesize(
        task_type=task_type,
        findings=findings,
        context=request.context,
    )

    # Complete task (archive and detach blocks)
    await self._handler.complete_task(
        request.identity_id,
        MAIN_AGENT_ID,
        agent_ids=agent_ids,
    )

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

## Phase 4: Prompt Updates

### Task 4.1: Update Agent Prompts with Coordination Instructions

**Files:**
- Modify: `docs/task-types/meeting_prep.yaml`

Add explicit instructions for agents to use memory_insert:

```yaml
agents:
  calendar:
    enabled: true
    prompt_template: |
      COORDINATION TASK: Find details for the meeting '{meeting_title}'.

      Look up:
      - Start time, duration, and location
      - All participants (names and roles if available)
      - Any scheduling conflicts in the 30 minutes before or after
      - Link to the calendar event if available

      IMPORTANT: After finding information, you MUST use memory_insert to add
      your findings to the coordination_gathered block:

      memory_insert("coordination_gathered_{identity_id}", "[Calendar HH:MM] Your summary here")

      Format: [Calendar HH:MM] Brief summary under 100 chars
      Example: [Calendar 14:30] Board Meeting, 2pm Jan 30, Room A, 5 participants
```

---

## Phase 5: Testing

### Task 5.1: Unit Tests for Block Attachment

**Files:**
- Create: `pa-routing-handler/tests/services/test_coordination_handler_blocks.py`

```python
class TestBlockAttachment:
    @pytest.mark.asyncio
    async def test_attach_block_to_agent(self):
        """Block can be attached to agent."""
        handler = CoordinationBlockHandler("http://localhost:8283")

        # Create a test block
        block_id = await handler.get_or_create_block(
            "test_block_attach",
            "test content"
        )

        # Attach to agent
        result = await handler.attach_block_to_agent(
            block_id,
            "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"  # calendar
        )

        assert result is True

        # Cleanup
        await handler.detach_block_from_agent(
            block_id,
            "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
        )

    @pytest.mark.asyncio
    async def test_start_coordinated_task_attaches_blocks(self):
        """start_coordinated_task attaches blocks to agents."""
        handler = CoordinationBlockHandler("http://localhost:8283")

        agent_ids = {"calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"}

        task_id = await handler.start_coordinated_task(
            identity_id="test-identity",
            task_type="meeting_prep",
            title="Test Meeting",
            required_agents=["calendar"],
            agent_ids=agent_ids,
        )

        assert task_id is not None

        # Verify agent has coordination blocks attached
        # (would need to query agent's memory blocks)
```

---

### Task 5.2: Integration Test with Agent Writing to Block

**Files:**
- Create: `pa-routing-handler/tests/integration/test_shared_block_coordination.py`

```python
@pytest.mark.live
@pytest.mark.asyncio
async def test_agent_writes_to_gathered_block():
    """Agent writes findings to coordination_gathered block."""

    # This test requires:
    # 1. Letta running
    # 2. Calendar agent with coordination protocol attached
    # 3. Coordination blocks attached to calendar agent

    handler = CoordinationBlockHandler("http://localhost:8283")

    # Start task
    task_id = await handler.start_coordinated_task(
        identity_id="test-identity",
        task_type="meeting_prep",
        title="Test Board Meeting",
        required_agents=["calendar"],
        agent_ids={"calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"},
    )

    # Send message to calendar agent
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8283/v1/agents/agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218/messages",
            json={
                "messages": [{"role": "user", "content": "Find details for the Board Meeting"}]
            }
        )

    # Wait for agent to process
    await asyncio.sleep(5)

    # Check gathered block for calendar contribution
    contributed = await handler.check_agent_contribution("test-identity", "calendar")

    assert contributed, "Calendar agent should have written to gathered block"

    # Get findings
    findings = await handler.get_gathered_findings("test-identity")

    assert "calendar" in findings, "Should have calendar findings"
    assert "[Calendar" in findings.get("calendar", ""), "Should have Calendar marker"
```

---

## Migration Path

### From Direct Response to Block-Based

1. **Phase 1**: Add block attachment (no behavior change yet)
2. **Phase 2**: Update agent system prompts with coordination protocol
3. **Phase 3**: Update orchestrator to poll blocks
4. **Phase 4**: Update task type prompts with memory_insert instructions
5. **Phase 5**: Test end-to-end with real agents

### Fallback Strategy

If agents don't reliably write to blocks:
- Keep direct response capture as fallback
- Log when using fallback vs block
- Refine agent prompts based on failure patterns

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Blocks attached to agents | Check agent memory blocks via API |
| Agents write to gathered block | `[AgentName HH:MM]` pattern in block |
| Orchestrator polls blocks | Findings come from block, not direct response |
| Cross-agent awareness | Later agents can read earlier findings |
| Block cleanup | Blocks detached after task completion |

---

## Estimated Complexity

| Phase | Tasks | Dependencies |
|-------|-------|--------------|
| Phase 1: Block Attachment | 3 tasks | None |
| Phase 2: Agent Prompts | 2 tasks | None |
| Phase 3: Orchestrator Flow | 4 tasks | Phase 1 |
| Phase 4: Task Prompts | 1 task | Phase 2 |
| Phase 5: Testing | 2 tasks | Phase 3-4 |

**Total: 12 tasks**

Phases 1 and 2 can run in parallel.
Phase 3 depends on Phase 1.
Phase 4 depends on Phase 2.
Phase 5 depends on Phases 3 and 4.
