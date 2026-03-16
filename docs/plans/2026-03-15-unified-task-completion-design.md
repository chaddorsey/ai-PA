# Unified Task Completion & Widget Queue Integration

## Goal

Unify task completion awareness across the entire PA ecosystem — replacing fragmented polling with a push-based architecture that catches all task completions regardless of source, integrates the new timer widget queue, and gives MC the time-awareness tools it needs for real-time coordination.

## Architecture Overview

Three new capabilities, one integration change:

1. **OmniFocus Completion Watcher Plugin** — server-side OmniFocus plugin that detects all task completions and pushes notifications to the Task Completion Service
2. **Task Completion Service** — extends the existing sync service (port 8092) to receive push notifications, process completions, and notify MC
3. **Rover Widget Queue Tool** — dedicated Letta tool for Rover to manage the timer widget queue
4. **Scheduler MCP Wake Timers** — merge v2 tools into deployed scheduler-mcp to enable MC self-scheduling for time-critical monitoring

Supporting changes:
- Dynamic heartbeat scheduling (work hours vs off-hours)
- Existing completion polling becomes reconciliation-only backup
- MC receives completion notifications and wake timer messages for real-time coordination

---

## Component 1: OmniFocus Completion Watcher Plugin

### Purpose

A new OmniFocus plugin running on the server's OmniFocus instance that polls for recently-completed tasks and POSTs completion events to the Task Completion Service. OmniFocus syncs via OmniSync with all devices, so this single observation point catches completions from phone, laptop, CLI, and widget.

### Design

- **Plugin type:** OmniFocus Omni Automation plugin (`.omnifocusjs` bundle)
- **Detection mechanism:** `Timer.repeating(60, callback)` — polls every 60 seconds (OmniFocus has no event-based completion callbacks; polling is the only option, as demonstrated by the existing timer plugin's guardian pattern)
- **What it checks:** Queries `flattenedTasks` for tasks where `taskStatus === Task.Status.Completed` or `taskStatus === Task.Status.Dropped` and `completionDate > lastCheckTimestamp`. Performance note: `flattenedTasks` returns all tasks including completed ones. To avoid iterating thousands of tasks every 60s, the plugin should filter early by checking `completionDate` before accessing other properties, or use a targeted query (e.g., tasks completed in the last 5 minutes). If performance is still a concern, the poll interval can be increased to 120s — still well within the timeliness requirement.
- **High-water mark:** Stores `lastCheckTimestamp` in `Preferences` (persisted across OmniFocus restarts). Updated in the `.then()` callback of the successful HTTP POST — not synchronously, since `URL.FetchRequest.fetch()` returns a Promise. The plugin processes one batch of completions per tick to avoid race conditions where the next timer fires before the previous fetch resolves (same pattern as the timer plugin's event queue).
- **Orphan recovery:** On plugin load, checks for completions during any downtime gap (difference between current time and stored `lastCheckTimestamp`)

### Completion Event Payload

```json
{
  "task_id": "abc123XYZ",
  "task_name": "Write follow-up email to Kate",
  "note": "Full task note text including timing data blocks",
  "completion_date": "2026-03-15T14:32:00Z",
  "was_dropped": false,
  "project_name": "Q2 Planning",
  "tags": ["work", "email"]
}
```

### External Communication

- HTTP POST to `http://localhost:8092/v1/completion` (Task Completion Service)
- Fire-and-forget with retry queue in `Preferences` (max 50 pending events, same pattern as timer plugin)
- Failed events are retried on next poll tick
- Heartbeat/health events are not queued

### Plugin Location

Installed at `/Users/dorseyhomeserver/Library/Application Support/OmniFocus/Plug-Ins/omnifocus-completion-watcher.omnifocusjs/` alongside the existing timer plugin and MCP plugin.

### Key Constraints

- Timers only run while OmniFocus is open on the server. If OmniFocus is closed, no polling occurs. Orphan recovery handles the gap on next launch.
- OmniSync propagation adds seconds to minutes of delay for completions from other devices.
- Total detection latency: OmniSync propagation + up to 60s poll interval = typically under 2 minutes.

---

## Component 2: Task Completion Service

### Purpose

Receives completion notifications from the OmniFocus plugin, deduplicates, routes to the extraction loop for ref_id tasks, and notifies MC of all completions.

### Design

Extend the existing standalone sync service at `/Volumes/main-drive/ai-PA/scripts/omnifocus_sync_service.py` (port 8092) rather than creating a new service. It already has archival memory integration, Letta API access, and Slack notification capability.

**Framework migration:** The existing service uses Python's raw `http.server.HTTPServer` with manual path matching. Adding multiple new endpoints with JSON parsing, error handling, and structured responses justifies migrating to FastAPI as part of this work. The migration scope is small (the service has one existing endpoint) and FastAPI aligns with the project's standard service pattern (scheduler-service, pa-routing-handler, etc.).

**Process management:** The service must be reliable since the OmniFocus plugin depends on it being up. Deploy as a Docker container on `pa-internal` (consistent with other services) or as a launchd service on the server. Docker is preferred for consistency with the rest of the stack. Add a health check endpoint.

### Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /v1/completion` | New | Receive push notification from OmniFocus plugin |
| `GET /v1/completions/recent` | New | Query recent completions (for MC/agents) |
| `POST /v1/sync` | Existing | Reconciliation polling (reduced frequency) |
| `GET /health` | Existing | Health check |

### Processing Flow (`POST /v1/completion`)

```
Completion event received
    |
    v
1. DEDUPLICATE
   - Key: OmniFocus task ID + completion timestamp
   - If already processed, return 200 (idempotent)
   - Store processed completions in a lightweight table/file
    |
    v
2. SEARCH ARCHIVAL MEMORY
   - GET /v1/agents/{tasks_agent_id}/archival-memory?search={task_id}
   - Check if any passage contains "- Task ID: {task_id}" with "status:confirmed"
    |
    v
3a. EXTRACTED TASK (passage found with status:confirmed)
    - Update passage: prefix [COMPLETED], set Status: completed, add timestamp
    - Extract routing metadata: source_type, from_person, has_external_origin
    - For external-origin tasks: trigger prepare_completion_feedback
    - Record completion with extraction metadata
    |
3b. NON-EXTRACTED TASK (no matching passage)
    - Record completion (task name, date, project, timing data if in notes)
    |
    v
4. NOTIFY MC
   - POST /v1/agents/{mc_agent_id}/messages
   - Message: "Task completed: '{task_name}' (project: {project}, completed: {time})"
   - Include timing summary if Time Tracking block found in notes
   - Include extraction status (extracted task with follow-up pending, or standalone)
    |
    v
5. UPDATE RECENT COMPLETIONS
   - Append to rolling in-memory list (last ~50 completions)
   - Available via GET /v1/completions/recent
```

### Timing Data Extraction

The service parses the task note for the timer plugin's delimited block:
```
--- Time Tracking ---
[2026-03-15 09:00-09:12] 12m 05s
Total: 20m 37s
--- End Time Tracking ---
```

If found, includes timing summary in the MC notification and completion record. No separate timing pipeline — the data travels with the task note through OmniSync.

### Deduplication Strategy

- In-memory set keyed by OmniFocus task ID, with the last-seen completion timestamp, persisted to a JSON file on disk
- Using task ID alone (not task_id + completion_date) avoids edge cases where OmniSync delivers the same completion with slightly different timestamp serialization
- Pruned to last 30 days on service startup
- Handles duplicate notifications from: plugin retry queue, reconciliation polling, OmniSync re-sync

### Reconciliation

The existing `POST /v1/sync` endpoint (and corresponding `sync_omnifocus_completions` Letta tool) continues running on a reduced schedule — every 2 hours instead of 15-30 minutes. It serves as a safety net for completions missed during plugin downtime. The sync logic feeds through the same deduplication layer, so duplicates are harmless.

### MC Notification Format

Notifications are sent via `POST /v1/agents/{mc_agent_id}/messages` with `role: "system"`. This is the same pattern used by the scheduler service's `agent_message` action type (e.g., the Gold-Standard Briefing job in production). The `system` role distinguishes automated notifications from user messages in MC's conversation history.

```json
{
  "messages": [
    {
      "role": "system",
      "content": "TASK COMPLETED: 'Write follow-up email to Kate'\nProject: Q2 Planning\nCompleted: 2026-03-15 14:32 ET\nTiming: 20m 37s active (2 sessions)\nExtraction: ref_id 8a3b5089, source: slack, follow-up pending"
    }
  ]
}
```

For non-extracted tasks without timing data:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "TASK COMPLETED: 'Buy groceries'\nProject: Personal\nCompleted: 2026-03-15 15:10 ET"
    }
  ]
}
```

Note: If `role: "system"` is rejected by the Letta API in testing, fall back to `role: "user"` with a `[SYSTEM NOTIFICATION]` prefix in the content to distinguish from user messages.

---

## Component 3: Rover Widget Queue Tool

### Purpose

A dedicated Letta tool for Rover to manage the timer widget queue directly, without needing MC as intermediary for queue operations.

### Tool Signature

```python
def manage_widget_queue(action: str, task_ids: Optional[str] = None, position: Optional[int] = None) -> Dict[str, Any]:
    """
    Manage the OmniFocus timer widget queue.

    Args:
        action: Queue operation — list, set, push, insert, remove, move, clear
        task_ids: Comma-separated OmniFocus task IDs (for set, push, insert, remove, move)
        position: Target position for insert/move (0-indexed)

    Returns:
        Dictionary with status and current queue state.
    """
```

### Actions

| Action | task_ids | position | Effect |
|---|---|---|---|
| `list` | — | — | Return current queue contents |
| `set` | Required (comma-sep) | — | Replace entire queue |
| `push` | Required (comma-sep) | — | Append to end (dedupes) |
| `insert` | Required (single) | Required | Insert at position |
| `remove` | Required (single) | — | Remove from queue |
| `move` | Required (single) | Required | Move to position |
| `clear` | — | — | Empty the queue |

### Implementation

**Execution context constraint:** Rover is a Letta agent whose tools execute in the Letta sandbox on the server (Docker container), not on the laptop where `widget-queue.sh` and `~/.omnifocus-timer-widget/queue.json` reside. The tool cannot shell out to a local script.

**Solution:** The tool calls the widget queue operations via HTTP to the laptop. Two options, in order of preference:

1. **LettaBot HTTP endpoint (preferred):** LettaBot already runs on the laptop with an HTTP API. Add a `/api/v1/widget-queue` endpoint to LettaBot that wraps `widget-queue.sh` operations. The Letta tool calls `http://{ROVER_LETTABOT_URL}/api/v1/widget-queue` with action/task_ids/position parameters. This reuses the existing LettaBot infrastructure and the `ROVER_LETTABOT_URL` env var already configured in docker-compose.

2. **OmniFocus MCP bridge fallback:** The OmniFocus MCP bridge runs on the laptop at port 8889. Queue operations could be added as bridge commands. However, this mixes concerns (OmniFocus task management vs widget queue management) and is less clean.

The tool implementation:
- Makes HTTP POST to `{ROVER_LETTABOT_URL}/api/v1/widget-queue` with JSON body `{"action": "push", "task_ids": "id1,id2"}`
- LettaBot endpoint calls `widget-queue.sh` locally and returns JSON result
- Standard Letta tool pattern: all imports inside function body, try-except wrapper, returns `Dict[str, Any]`

### Agent Assignment

- **Attached to Rover only.** MC instructs Rover via `message_rover_local` about what to queue; Rover uses this tool to execute.
- **Separation of concerns:** MC decides priorities and timing. Rover manages the queue. The widget handles user interaction and timing capture.
- **Note:** Although the tool is attached to Rover's agent on the server, the HTTP call routes to the laptop where LettaBot and the queue file reside. This is the same network path used by `message_rover_local`.

### No Feedback Responsibility

The widget queue tool is write/read-only from Rover's perspective. Completion feedback flows through the OmniFocus completion plugin → Task Completion Service path. The widget's job is displaying tasks and recording timing; the plugin's job is detecting completions.

---

## Component 4: Scheduler MCP Wake Timers

### Purpose

Enable MC to set one-shot "wake timers" — purposeful, self-directed wake-up calls at specific times for time-critical monitoring.

### Design

Merge key tools from the existing (but undeployed) `server_v2.py` into the deployed `server.py` in the scheduler-mcp service. The scheduler service backend already fully supports one-shot jobs with `agent_message` actions — the gap is only in the MCP tool layer.

### Tools to Add

**`schedule_reminder`** — simplified self-scheduling tool:
- Parameters: `when` (natural language: "at 1:45pm", "in 20 minutes"), `message` (context string), `agent_id` (optional, defaults to self)
- Creates a `one_off` job with an `agent_message` action targeting the specified agent
- Returns job ID for cancellation
- Sets `created_by` to the requesting agent's ID

**`cancel_reminder`** — cancel a previously-set timer:
- Parameter: `job_id`
- Calls DELETE on the scheduler API
- Only cancels jobs created by the requesting agent (safety check)

### Implementation Approach

- Add `schedule_reminder` and `cancel_reminder` as new tools in the deployed `server.py`
- Keep all existing tools (`scheduler_create_job`, `scheduler_list_jobs`, etc.) untouched
- No database migration needed — uses existing Job/Action models
- No changes to the scheduler-service itself — only the MCP tool layer
- Verify end-to-end: create timer → scheduler fires at time → message reaches MC

### Existing Job Safety

All 10+ production jobs continue unchanged. New tools are additive — they create jobs through the same API the existing tools use, just with a simplified interface optimized for the wake-timer pattern.

### MC Usage Pattern

When MC sets up a time-bound work session:

```
MC identifies: "User has 45 minutes before 2pm meeting,
               queuing 3 tasks (est. 30min, 5min, 5min)"

MC instructs Rover: "Queue tasks A, B, C"
MC sets timers:
  - schedule_reminder("at 1:30pm", "Midpoint check: is user on track? Meeting at 2pm, 3 tasks queued")
  - schedule_reminder("at 1:50pm", "10 min warning: assess remaining tasks, consider triage for 2pm meeting")

At 1:30pm: Scheduler fires → MC wakes up → checks recent_completions →
           sees task A completed at 1:25pm → task B in progress → on track → no action needed

At 1:50pm: Scheduler fires → MC wakes up → checks recent_completions →
           sees task B still not completed → tells Rover to remove task C from queue →
           messages user "Meeting in 10 min — suggest wrapping up current task"
```

---

## Component 5: Dynamic Heartbeat

### Purpose

Match heartbeat frequency to the pace of the day — faster during work hours when MC needs background awareness of calendar, inbox, and system state; slower off-hours.

### Design

Modify `HeartbeatService` in LettaBot to use self-scheduling `setTimeout` instead of fixed `setInterval`, recalculating the delay on each tick based on current time.

### Configuration

```yaml
features:
  heartbeat:
    enabled: true
    schedule:
      workHours:
        start: 8    # 8am local
        end: 18     # 6pm local
        intervalMin: 10
      offHours:
        intervalMin: 60
    skipRecentUserMin: 5
```

### Implementation

- Replace `setInterval(callback, fixedMs)` with a self-rescheduling pattern:
  ```
  tick() → run heartbeat → compute next interval based on current hour → setTimeout(tick, nextInterval)
  ```
- On each tick, check current hour against `workHours.start` / `workHours.end`
- Use the corresponding `intervalMin` for the next delay
- Existing skip-recent-user logic is unchanged

### Relationship to Wake Timers

The heartbeat and wake timers serve different purposes:

| Heartbeat | Wake Timers |
|---|---|
| Periodic, system-driven | One-shot, MC-driven |
| General awareness | Purpose-specific |
| "Look around" | "Check this specific thing at this specific time" |
| Background tempo | Intentional vigilance |

Both coexist. The heartbeat ensures MC stays aware of the general picture. Wake timers ensure MC acts on specific time-critical situations. Event notifications (completions) ensure MC reacts to discrete events as they happen.

---

## Integration: Existing Completion Loop Migration

### Current State

- `sync_omnifocus_completions` tool on tasks-agent-sleeptime polls archival memory for `status:confirmed` passages, batch-checks OmniFocus, updates passages, returns routing metadata
- Runs periodically (intended 15-30 min schedule)
- Only catches extracted tasks (those with archival passages)
- `prepare_completion_feedback` handles follow-up routing (Slack reply, Docs comment, email draft)

### Migration

1. **Task Completion Service becomes primary.** Push-based notifications from the OmniFocus plugin replace polling as the main detection mechanism.
2. **Extracted task processing reuses existing logic.** The passage update logic from `sync_omnifocus_completions` is extracted into a shared function used by both the push endpoint and the reconciliation poll.
3. **Follow-up triggering unchanged.** `prepare_completion_feedback` continues to handle routing. The Task Completion Service returns the same metadata (`source_type`, `from_person`, `has_external_origin`) that the sync tool currently returns.
4. **Reconciliation poll reduced.** `sync_omnifocus_completions` schedule changes from 15-30 minutes to every 2 hours. Same logic, same deduplication, just less frequent.
5. **New coverage.** Non-extracted tasks are now visible to the system via the `recent_completions` endpoint and MC notifications — previously invisible.

### Data Flow Diagram

```
TASK COMPLETED (any device/method)
         |
         v
    OmniSync
         |
         v
OmniFocus (server) ─── Completion Watcher Plugin (60s poll)
         |
         v
Task Completion Service (port 8092)
    |         |              |
    v         v              v
Extracted?  Record       Notify MC
    |       completion    (always)
    v
  Yes: Update archival passage
       Trigger follow-up (if external origin)
       prepare_completion_feedback
    |
  No: Record for awareness only
```

### Reconciliation Flow (backup)

```
sync_omnifocus_completions (every 2h)
    |
    v
Search archival for status:confirmed
    |
    v
Batch-check OmniFocus
    |
    v
Any newly completed? ─── Dedup check ─── Already processed? Skip
    |                                          |
    v                                          v
Process via same logic as push path       No-op (idempotent)
```

---

## Separation of Concerns Summary

| Component | Responsibility | Does NOT do |
|---|---|---|
| **Timer Widget** | Display queued tasks, capture user interaction, record timing data in OmniFocus notes | Notify anyone of completions, manage queue logic, make priority decisions |
| **Rover** | Manage widget queue contents (add/remove/reorder tasks) | Decide what to queue (MC decides), detect completions, track time |
| **MC** | Determine task priorities, instruct Rover on queue contents, set wake timers, react to completions and time events | Directly manage the queue, detect completions |
| **Completion Watcher Plugin** | Detect all task completions from all sources, POST to service | Process completions, make decisions, manage queue |
| **Task Completion Service** | Deduplicate, route to extraction loop, notify MC, record completions | Decide follow-up actions (that's MC/agents), manage queue |
| **Scheduler Service** | Execute wake timers at specified times, deliver messages to agents | Decide when timers should be set (that's MC) |
| **Extraction Loop** | Track extraction lifecycle (candidate → confirmed → completed), trigger follow-ups | Detect completions (that's the plugin/service now) |

---

## Implementation Order

1. **Rover widget queue tool** — standalone, no dependencies, immediately useful
2. **OmniFocus completion watcher plugin** — core new capability, enables push-based detection
3. **Task Completion Service extensions** — push endpoint, MC notification, deduplication
4. **Scheduler MCP wake timers** — merge v2 tools into deployed server, verify end-to-end
5. **Dynamic heartbeat** — LettaBot config change, low risk
6. **Reconciliation schedule reduction** — reduce polling frequency after push path is verified stable
