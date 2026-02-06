# Extracted Tasks Tools

## Overview

Two concurrent-safe tools for managing a shared `extracted_tasks` memory block:

1. **`add_extracted_tasks`** - Quick task additions (append-only)
2. **`update_tasks_section`** - Curate entire section (scoped replacement)

Both tools allow multiple Letta agents to work with the shared block without race conditions.

## Problem Solved

When multiple agents need to write to the same memory block:
- **Race Condition**: Agent A reads block, Agent B reads block, both modify and write back → one overwrites the other
- **Solution**: Use append-only `memory_insert` operation with agent-segmented headers

## Architecture

### Shared Memory Block

- **Block Label**: `extracted_tasks`
- **Block ID**: `block-5a516880-1e01-4da5-a71b-23cad597a339`
- **Attached to**: All 25 agents

### Tool Format

Each agent's tasks are organized under a header:

```
=== Agent Name (agent_id) ===
[2026-02-05 14:30] Task description here
[2026-02-05 14:45] Another task description
```

### Concurrent Safety

The tool uses Letta's `memory_insert` API with `insert_line=-1` (append to end), which is:
- **Atomic**: Single operation, no read-modify-write cycle
- **Append-only**: No overwrites possible
- **Concurrent-safe**: Multiple agents can write simultaneously

## Usage

### Tool 1: add_extracted_tasks (Quick Additions)

**Use when**: Adding individual tasks in real-time

```python
add_extracted_tasks(task_description="Review budget proposal by Friday")
add_extracted_tasks(task_description="Email team about Q2 planning")
add_extracted_tasks(task_description="Schedule 1:1 with Danielle")
```

**Response**:
```json
{
  "status": "ok",
  "message": "Added task to extracted_tasks block",
  "agent_name": "pulse-monitor-agent",
  "timestamp": "2026-02-05T14:30:00-05:00"
}
```

### Tool 2: update_tasks_section (Section Curation)

**Use when**: Reorganizing, updating, or curating your entire section

```python
update_tasks_section(new_content="""
HIGH PRIORITY:
- [2026-02-05 14:30] Review budget by Friday (IN PROGRESS)
- [2026-02-05 14:45] Schedule 1:1 with Danielle (URGENT)

COMPLETED:
- [2026-02-05 14:35] Email team about Q2 planning ✓

NOTES:
- Budget review requires input from finance team
""")
```

**Response**:
```json
{
  "status": "ok",
  "message": "Updated your tasks section (245 chars)",
  "agent_name": "pulse-monitor-agent",
  "section_size": 245,
  "timestamp": "2026-02-05T15:00:00-05:00"
}
```

**Key Features**:
- ✅ Replaces your entire section with new content
- ✅ Auto-creates section header if it doesn't exist
- ✅ Validates you're not modifying other agents' sections
- ✅ Safe for concurrent use (scoped replacement)

## Workflow Patterns

### Pattern 1: Accumulate + Curate
```python
# Throughout the day: Quick additions
add_extracted_tasks("Task 1")
add_extracted_tasks("Task 2")
add_extracted_tasks("Task 3")

# End of day: Curate section
update_tasks_section("""
ACTIVE:
- Task 1 (HIGH PRIORITY)
- Task 3 (MEDIUM PRIORITY)

COMPLETED:
- Task 2 ✓
""")
```

### Pattern 2: Fresh Start
```python
# Clear and reorganize everything
update_tasks_section("""
TODAY:
- New task 1
- New task 2

BACKLOG:
- Task from yesterday
- Task from last week
""")
```

### Pattern 3: Incremental Curation
```python
# Add task immediately
add_extracted_tasks("Urgent: Review document")

# Later, curate to add context
update_tasks_section("""
URGENT (Due Today):
- [14:30] Review document - needs feedback by 5pm
  Link: https://docs.google.com/...

OTHER:
- [Previous tasks...]
""")
```

## Example Output in Block

```
# Extracted Tasks

This is a shared memory block where agents can contribute tasks...

=== pulse-monitor-agent (agent-6e) ===
[2026-02-05 14:30] Review budget proposal by Friday
[2026-02-05 14:35] Follow up with Danielle about charter meeting

=== main-assistant-agent-samantha (agent-b1) ===
[2026-02-05 14:32] Schedule Q1 planning meeting
[2026-02-05 14:40] Coordinate with calendar agent on availability

=== tasks-agent (agent-dd) ===
[2026-02-05 14:36] Create OmniFocus project for Gates hackathon
```

## Implementation Details

### Tool Compliance

The tool follows all Letta tool compliance requirements:
- ✅ All imports inside function at the beginning
- ✅ No nested `def` statements (all logic inlined)
- ✅ Only basic JSON types for parameters (`str`)
- ✅ All parameters documented in `Args:` section
- ✅ Entire function wrapped in try-except
- ✅ Returns `Dict[str, Any]` with consistent structure

### Files

**Tool 1: add_extracted_tasks**
- **Tool Definition**: [`letta/extracted_tasks_tool.py`](extracted_tasks_tool.py)
- **Registration Script**: [`letta/register_extracted_tasks_tool.py`](register_extracted_tasks_tool.py)
- **Attachment Script**: [`letta/attach_extracted_tasks_tool_to_agents.py`](attach_extracted_tasks_tool_to_agents.py)

**Tool 2: update_tasks_section**
- **Tool Definition**: [`letta/update_tasks_section_tool.py`](update_tasks_section_tool.py)
- **Registration Script**: [`letta/register_update_tasks_section_tool.py`](register_update_tasks_section_tool.py)
- **Attachment Script**: [`letta/attach_update_tasks_section_to_agents.py`](attach_update_tasks_section_to_agents.py)

**Management**
- **Cleanup Script**: [`letta/remove_extracted_tasks_from_non_paweb_agents.py`](remove_extracted_tasks_from_non_paweb_agents.py)

## Management

### Re-register Tools

If tool code is updated:

```bash
# Re-register add_extracted_tasks
python3 letta/register_extracted_tasks_tool.py

# Re-register update_tasks_section
python3 letta/register_update_tasks_section_tool.py
```

### Attach to New Agent

```bash
# Attach both tools to specific agent
python3 letta/attach_extracted_tasks_tool_to_agents.py agent-<new-agent-id>
python3 letta/attach_update_tasks_section_to_agents.py agent-<new-agent-id>
```

### Initial Setup (Already Done)

```bash
# Register both tools
python3 letta/register_extracted_tasks_tool.py
python3 letta/register_update_tasks_section_tool.py

# Attach to PA-Web and sleeptime agents
python3 letta/attach_extracted_tasks_tool_to_agents.py
python3 letta/attach_update_tasks_section_to_agents.py
```

### View Shared Block

```bash
curl -s http://localhost:8283/v1/blocks/block-5a516880-1e01-4da5-a71b-23cad597a339 | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['value'])"
```

## Concurrent Safety

### How It Works

Both tools are safe for concurrent use by multiple agents:

**add_extracted_tasks (Append-Only)**:
- Uses `memory_insert` with `insert_line=-1` (append to end)
- Atomic operation - no read-modify-write cycle
- Multiple agents can append simultaneously
- ✅ **Zero race condition risk**

**update_tasks_section (Scoped Replacement)**:
- Uses `memory_replace` with agent's section boundaries
- Each agent has unique section markers: `=== AgentName (agent_id) ===`
- Sections don't overlap - they're sequential
- Agent only replaces content between their own markers
- ✅ **Safe: Non-overlapping edits**

### Edge Case: Concurrent Curation

**Scenario**: Agent A and Agent B both call `update_tasks_section` simultaneously

**Result**: Both succeed!
- Agent A replaces their section
- Agent B replaces their section
- Sections are distinct, no conflict

**Race condition would only occur if**: Two agents tried to curate the **same agent's section** (which they can't - validation prevents this)

## Design Decisions

### Why Agent-Segmented Format?

**Considered Alternatives**:
1. JSON array - requires parsing, can break on malformed JSON
2. Flat chronological log - hard to filter by agent
3. Agent-segmented with headers - **Chosen**

**Why Chosen**:
- ✅ Clear visual separation
- ✅ Easy to parse (simple string search)
- ✅ Human-readable
- ✅ Works with append-only operations
- ✅ No JSON complexity

### Why memory_insert vs memory_replace?

**memory_replace** (UNSAFE):
```python
# ❌ Race condition possible
block = get_block("extracted_tasks")
new_content = block.value + "\nMy update"
memory_replace("extracted_tasks", block.value, new_content)
# If another agent wrote between get_block and memory_replace, their update is lost!
```

**memory_insert** (SAFE):
```python
# ✅ Atomic append operation
memory_insert(
    label="extracted_tasks",
    new_str="\nMy update",
    insert_line=-1  # Append to end
)
```

## Testing

### Test with Specific Agent

```bash
# Via Letta API
curl -X POST http://localhost:8283/v1/agents/agent-6eb765bf-7268-4f6d-a380-c527c9c53000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "text": "Add a test task using add_extracted_tasks: Review this weeks pulse report"
    }]
  }'
```

### Verify Concurrent Safety

Run multiple agents simultaneously adding tasks - no overwrites should occur.

## Monitoring

### Check Tool Attachment

```bash
# List all agents with the tool
curl -s http://localhost:8283/v1/tools/tool-a52477da-3e31-43f1-887b-65d2a93f506c | \
  python3 -c "import sys, json; print(len(json.load(sys.stdin).get('agents', [])))"
```

### Check Block Size

```bash
# Get current block size
curl -s http://localhost:8283/v1/blocks/block-5a516880-1e01-4da5-a71b-23cad597a339 | \
  python3 -c "import sys, json; b=json.load(sys.stdin); print(f\"{len(b['value'])} / {b['limit']} chars\")"
```

## Troubleshooting

### "Block not found" Error

The agent doesn't have the `extracted_tasks` block attached:

```bash
python3 letta/attach_extracted_tasks_tool_to_agents.py agent-<agent-id>
```

### Block Full (Hit Limit)

If block approaches limit (default 5000 chars), consider:
1. Archive old tasks to separate block
2. Increase block limit via API
3. Create time-based blocks (e.g., `extracted_tasks_2026_02`)

### Tool Not Available

Re-register and re-attach:

```bash
python3 letta/register_extracted_tasks_tool.py
python3 letta/attach_extracted_tasks_tool_to_agents.py
```

## Future Enhancements

Possible improvements:
- Time-based block rotation (monthly archives)
- Task priority/status tracking
- Task assignment to specific agents
- Task completion tracking
- Search/filter tools for extracted tasks
