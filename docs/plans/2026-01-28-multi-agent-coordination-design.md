# Multi-Agent Coordination Design

> **Status:** Design complete, ready for implementation
> **Date:** 2026-01-28
> **Related:** Identity-based conversations, routing handler orchestration

## Overview

This design enables multiple specialist agents (Calendar, Document, Email, Pulse) to contribute to coordinated tasks like "prep me for my next meeting" without posting summaries to each other or causing coordination loops.

**Key Principles (from Letta guidance):**
- ONE conversation per identity per agent (already implemented)
- Shared memory blocks for cross-agent awareness (not archival search)
- Handler orchestration in application code (not agent-to-agent messaging)
- Append-only updates to avoid race conditions and fragile JSON matching

## Architecture

### Three-Block Coordination System

Instead of one monolithic JSON block, we use three focused blocks per identity:

| Block | Purpose | Writer | Reader | Format |
|-------|---------|--------|--------|--------|
| `coordination_task_{identity_id}` | Task context | Handler only | All agents | Plain text |
| `coordination_gathered_{identity_id}` | Agent findings | Agents (append) | Handler | Plain text |
| `coordination_status_{identity_id}` | Completion tracking | Handler only | Handler only | JSON |

### Why Three Blocks?

1. **Avoids fragile JSON string matching** - Agents don't need to parse/update JSON
2. **Append-only prevents race conditions** - `memory_insert` is safe for concurrent agents
3. **Clear ownership** - Each block has a single writer pattern
4. **Scales within 2000 char limit** - Total ~600-800 chars, room for growth

---

## Block Specifications

### Block 1: `coordination_task_{identity_id}`

**Purpose:** Immutable task context that agents read to understand what they're contributing to.

**Example:**
```
Meeting prep for Board Meeting (Jan 30, 2pm)
Event ID: event-abc123
Participants: Alice, Bob, Carol
Task ID: task-meeting-prep-20260128-103000
Agents: calendar, document, email, pulse

Expected contributions:
- Calendar: event details, conflicts
- Document: agenda summary, action items
- Email: relevant threads (last 7 days)
- Pulse: availability/status updates
```

**Characteristics:**
- Size: ~200-300 chars
- Writer: Handler only (when starting coordinated task)
- Readers: All participating agents
- Format: Plain text (agents read naturally, no JSON parsing)

---

### Block 2: `coordination_gathered_{identity_id}`

**Purpose:** Append-only findings log. Each agent adds one line when done.

**Example:**
```
[Calendar 10:30] Event: Board Meeting, 2pm Jan 30, 3 participants
[Document 10:31] Agenda: Q1 budget review, 4 topics, 2 pending actions
[Email 10:32] 3 threads: Alice timeline concern, Bob confirmed, Carol venue Q
[Pulse 10:33] Bob OOO tomorrow, Alice remote Wednesday
```

**Characteristics:**
- Size: ~300-500 chars (grows with contributions)
- Writer: Specialist agents via `memory_insert` (append-only)
- Reader: Handler parses to extract findings
- Format: Plain text with `[AgentName HH:MM]` prefix
- Limit: 100 chars per entry

**Rotation Strategy:**
When block approaches 1500 chars:
1. Archive current content to Main Agent's archival memory with tags
2. Reset block with `[Archived at HH:MM]` marker
3. Continue collecting new findings

---

### Block 3: `coordination_status_{identity_id}`

**Purpose:** Track which agents have contributed. Agents never touch this.

**Example:**
```json
{"calendar":"done","document":"done","email":"in_progress","pulse":"pending","task_id":"task-meeting-prep-20260128-103000"}
```

**Characteristics:**
- Size: ~100 chars
- Writer: Handler only (updates after parsing gathered block)
- Readers: Handler only
- Format: Compact JSON (handler-only, so JSON is fine)

---

## Agent System Prompt Additions

Add this protocol to each specialist agent's persona (Calendar, Document, Email, Pulse):

```xml
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

---

## Handler Orchestration

### Orchestration Flow

```
1. User: "Prep me for my next meeting"

2. Handler: start_coordinated_task()
   - Create coordination_task block with context
   - Initialize coordination_gathered (empty)
   - Initialize coordination_status (all "pending")

3. Handler: dispatch_to_agent("calendar", "Find next meeting details")
   - Calendar agent reads task block, fetches event
   - Calendar agent: memory_insert -> [Calendar 10:30] Board Meeting, 2pm, 3 participants

4. Handler: check_agent_contribution() -> status["calendar"] = "done"

5. Handler: dispatch_to_agent("document", "Summarize meeting agenda")
   - Document agent reads task block + gathered findings
   - Document agent: memory_insert -> [Document 10:31] Agenda: Q1 budget, 4 topics

6. (Repeat for email, pulse...)

7. Handler: All agents done -> complete_task()
   - Archive session to Main Agent's archival
   - Reset blocks for next task
```

### Handler Implementation

```python
class CoordinationBlockHandler:
    """Manages coordination blocks for multi-agent tasks."""

    def start_coordinated_task(
        self,
        identity_id: str,
        task_type: str,
        event_id: str,
        title: str,
        participants: list,
        required_agents: list
    ) -> str:
        """Initialize coordination blocks for multi-agent task."""

        task_id = f"task-{task_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # 1. Create/update task block
        task_content = f"""Meeting prep for {title}
Event ID: {event_id}
Participants: {', '.join(participants)}
Task ID: {task_id}
Agents: {', '.join(required_agents)}

Expected contributions:
- Calendar: event details, conflicts
- Document: agenda summary, action items
- Email: relevant threads (last 7 days)
- Pulse: availability/status updates"""

        self.update_or_create_block(
            f"coordination_task_{identity_id}",
            task_content
        )

        # 2. Reset gathered block
        self.update_or_create_block(
            f"coordination_gathered_{identity_id}",
            ""  # Empty, ready for agent contributions
        )

        # 3. Initialize status block
        status = {agent: "pending" for agent in required_agents}
        status["task_id"] = task_id

        self.update_or_create_block(
            f"coordination_status_{identity_id}",
            json.dumps(status)
        )

        return task_id

    def check_agent_contribution(self, identity_id: str, agent_name: str) -> bool:
        """Check if agent added findings, update status."""

        gathered_block = self.letta.blocks.retrieve_by_label(
            f"coordination_gathered_{identity_id}"
        )

        # Look for agent's entry
        if f"[{agent_name.title()}" in gathered_block.value:
            # Update status
            status_block = self.letta.blocks.retrieve_by_label(
                f"coordination_status_{identity_id}"
            )
            status = json.loads(status_block.value)
            status[agent_name] = "done"

            self.letta.blocks.update(
                status_block.id,
                value=json.dumps(status)
            )
            return True
        return False

    def check_and_rotate_gathered_block(self, identity_id: str):
        """Archive and reset gathered block if approaching capacity."""

        block = self.letta.blocks.retrieve_by_label(
            f"coordination_gathered_{identity_id}"
        )

        if len(block.value) > 1500:  # Approaching 2000 char limit
            # Archive to archival memory
            task_block = self.letta.blocks.retrieve_by_label(
                f"coordination_task_{identity_id}"
            )

            self.letta.archival_memory_insert(
                agent_id=self.main_agent_id,
                content=f"""Coordination Session Findings

Task: {task_block.value}
Timestamp: {datetime.now()}

{block.value}""",
                tags=[
                    f"identity:{identity_id}",
                    "type:coordination_findings",
                ]
            )

            # Reset block with reference
            self.letta.blocks.update(
                block.id,
                value=f"[Archived at {datetime.now().strftime('%H:%M')}]\n\n"
            )

    def complete_task(self, identity_id: str):
        """Archive coordination state and reset blocks."""

        # Get all blocks
        task_block = self.letta.blocks.retrieve_by_label(
            f"coordination_task_{identity_id}"
        )
        gathered_block = self.letta.blocks.retrieve_by_label(
            f"coordination_gathered_{identity_id}"
        )
        status_block = self.letta.blocks.retrieve_by_label(
            f"coordination_status_{identity_id}"
        )

        status = json.loads(status_block.value)

        # Archive complete session
        self.letta.archival_memory_insert(
            agent_id=self.main_agent_id,
            content=f"""COMPLETED COORDINATION TASK

{task_block.value}

Gathered Findings:
{gathered_block.value}

Status: {json.dumps(status, indent=2)}
Completed: {datetime.now()}""",
            tags=[
                f"identity:{identity_id}",
                "status:completed",
                f"task_id:{status.get('task_id')}"
            ]
        )

        # Reset blocks for next task
        self.letta.blocks.update(task_block.id, value="")
        self.letta.blocks.update(gathered_block.id, value="")
        self.letta.blocks.update(status_block.id, value="{}")
```

---

## Block Lifecycle

### Creation
Handler creates blocks when first coordinated task starts for an identity. Blocks persist across sessions (core memory, not ephemeral).

### During Task
- Handler writes to `coordination_task` once at start
- Agents append to `coordination_gathered` via `memory_insert`
- Handler updates `coordination_status` after each agent contribution
- Handler checks for rotation when `coordination_gathered` approaches 1500 chars

### Task Completion
1. Archive full session to Main Agent's archival memory with tags
2. Clear all three blocks for next task
3. Session history preserved in archival for future reference

### Rotation (if needed during task)
When `coordination_gathered` exceeds 1500 chars:
1. Archive current findings to archival memory
2. Reset block with `[Archived at HH:MM]` marker
3. Continue collecting new findings

---

## Comparison with Current Architecture

| Aspect | Current | New Design |
|--------|---------|------------|
| Cross-agent awareness | Archival passages (requires search) | Shared memory blocks (immediate) |
| Agent coordination | Handler writes summaries to archival | Agents append to shared block |
| Status tracking | None | Handler-managed status block |
| Data format | JSON in passages | Plain text (easier for agents) |
| Race conditions | Possible with parallel writes | Prevented by append-only pattern |

---

## Implementation Tasks

1. **Create CoordinationBlockHandler class** in routing handler
2. **Add agent system prompts** with coordination protocol
3. **Implement block creation/management** via Letta Blocks API
4. **Add rotation strategy** for gathered block
5. **Add task completion archival** flow
6. **Test with meeting prep use case**

---

## Future Extensions

- **Per-agent detailed blocks** if agents produce >500 chars each
- **`report_findings` tool** as alternative to direct `memory_insert`
- **Priority/urgency flags** in task block
- **Timeout handling** for unresponsive agents
- **Parallel agent dispatch** for independent contributions
