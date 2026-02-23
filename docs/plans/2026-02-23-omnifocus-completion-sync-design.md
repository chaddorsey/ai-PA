# OmniFocus Completion Sync: Closing the Loop to Letta

## Context

Extracted tasks flow from Letta to OmniFocus: the agent creates the OmniFocus task, then calls `transition_extracted_task(ref_id, "confirm", omnifocus_task_id)` to record the link. The archival passage moves from `status:extracted` to `status:confirmed` with the OmniFocus task ID embedded in the text.

**The gap**: When a user completes (or drops) a task in OmniFocus, Letta never finds out. The passage stays `confirmed` indefinitely. We need an automatic mechanism to detect OmniFocus completions and update the Letta archive accordingly.

## Constraints Discovered

1. **OmniFocus has no event system.** No task-completion listeners, webhooks, or push notifications. Active feature request on Omni Group forums. All communication must be pull-based.

2. **OmniFocus plugins CAN make HTTP calls** (`URL.FetchRequest`), but cannot run background timers. A plugin method only runs when explicitly called.

3. **Letta archival search quirk**: The archive has no `embedding_config`, so `/v1/passages/search` (semantic) returns empty. Agent-level `archival-memory?search=` (substring) works reliably.

4. **Existing transition logic** (`transition_extracted_task` with action `"complete"`) already handles all passage mutations. The problem is purely about *triggering* it.

5. **Bridge double-encoding**: The host bridge returns `{"success": true, "result": "<json-string>"}` where `result` is a string that needs an additional `JSON.parse`.

## Solution Implemented: Path A+C

**Custom Letta tool + OmniFocus plugin batch method**, assigned to `tasks-agent-sleeptime`.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Plugin batch method | `omnifocus-mcp-letta/extra-files/omnifocus-mcp.omnijs` | `checkTaskCompletionStatus({taskIds})` — single bridge call for N tasks |
| Sync tool | `letta/sync_omnifocus_completions_tool.py` | Deterministic: find confirmed passages, batch-check OmniFocus, transition completed |
| Registration script | `letta/register_sync_omnifocus_tool.py` | Registers tool and attaches to `tasks-agent-sleeptime` |
| Scheduler cron job | Job ID `c243c1e4-cb55-40d1-a550-3d343b9cc5fc` | `*/30 8-22 * * *` (every 30 min, 8am-10pm ET) |

### How It Works

1. Scheduler sends `agent_message` to `tasks-agent-sleeptime` every 30 minutes
2. Agent calls `sync_omnifocus_completions()` tool
3. Tool queries agent's archival memory for `Status: confirmed` passages (substring search)
4. Tool extracts OmniFocus task IDs from passages
5. Tool calls bridge `checkTaskCompletionStatus` with all task IDs in one batch
6. For completed/dropped/not-found tasks: updates passage text, tags, and timestamps
7. Returns summary to agent for logging

### Passage Transition Logic

- **Completed**: `[COMPLETED]` prefix, `status:completed` tag, `Completed` timestamp
- **Dropped**: `[DROPPED]` prefix, `status:dropped` tag, `Dropped` timestamp
- **Not found**: Treated same as completed (task was deleted from OmniFocus)

### Verified 2026-02-23

- `b3211e86` (not found in OmniFocus) → automatically transitioned to `[COMPLETED]`
- `d6b5c30f` (manually completed in OmniFocus) → detected and transitioned to `[COMPLETED]` on next sync
- 4 remaining tasks correctly identified as still active
