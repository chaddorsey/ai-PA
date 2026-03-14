# OmniFocus Task Timer — Design Spec

**Date:** 2026-03-14
**Status:** Draft
**Goal:** Capture actual time spent on OmniFocus tasks via a start/stop/pause timer, enabling an estimation evaluation and improvement loop. Designed for full two-way integration with the Letta PA ecosystem.

---

## Problem Statement

OmniFocus has a duration field (`estimatedMinutes`) for tasks, but no mechanism for recording actual time spent. Without actuals, there is no feedback loop for improving estimates. The user works primarily on macOS and relies on Letta agents (Rover on laptop, Mission Control on server) to surface and manage tasks.

## Success Criteria

1. User can start, pause, resume, and stop a timer on any OmniFocus task via Automation menu items (keyboard-shortcut bindable)
2. Switching to a new task auto-stops the previous timer
3. Actual time is logged to the task's note with session-level detail, preserving the original estimate
4. Timer state survives OmniFocus restarts (orphan recovery)
5. Data is persisted incrementally — a crash loses at most 60 seconds of tracking
6. Letta agents can query timer status, start/stop timers, and receive timer events as messages
7. No new microservices — integrates via existing omnifocus-cli and host bridge infrastructure

## Non-Goals

- Visible always-on timer widget (OmniFocus API does not support this)
- iOS support (Mac-primary workflow; iOS fallback via Letta messaging)
- Modification of the existing omnifocus-mcp plugin
- Analytics dashboard (future work; the note-based log is the data source)

---

## Architecture Overview

```
┌──────────────────────────────────────────────┐
│ OmniFocus Timer Plugin                        │
│ (omnifocus-timer.omnifocusjs)                │
│                                               │
│ Actions: Start, Pause, Resume, Stop, Check   │
│ Library: startTimer(), stopTimer(), etc.      │
│ Guardian: 60s poll, note writes, nudges       │
│                                               │
│ Outbound: POST localhost:8889/timer-event     │
│ Inbound: library functions via osascript      │
└──────────────┬───────────────┬───────────────┘
               │               │
          outbound          inbound
               │               │
               ▼               │
┌──────────────────────────────┴───────────────┐
│ Host Bridge Service (port 8889)              │
│ /execute — existing OmniFocus command bridge │
│ /timer-event — NEW relay to Letta agent      │
└──────────────┬───────────────▲───────────────┘
               │               │
               ▼               │
┌──────────────────────────────┴───────────────┐
│ Letta (Rover / Mission Control)              │
│ Receives: timer events as agent messages     │
│ Sends: timer commands via omnifocus-cli      │
└──────────────────────────────────────────────┘
```

**Data flow — outbound (timer → Letta):**
Plugin state change → `URL.FetchRequest` POST to `localhost:8889/timer-event` → host bridge formats natural-language message → POSTs to Letta agent messages API.

**Data flow — inbound (Letta → timer):**
Rover calls `omnifocus-cli timer start <taskId>` → `bridge.py` (with plugin-aware routing targeting `com.dorsey.omnifocus-timer`) → osascript → timer plugin library function `startTimer(taskId)`.

---

## Component 1: Timer Plugin (`omnifocus-timer.omnifocusjs`)

**Note on plugin format:** The existing `omnifocus-mcp.omnijs` is a single-file library plugin. The timer plugin uses the `.omnifocusjs` **bundle** format because it needs both UI actions (Automation menu items) and a library (for external callers). Bundles are directories containing a manifest, action files, and library files.

### Plugin Identifier

`com.dorsey.omnifocus-timer` — used in `PlugIn.find()` calls from osascript and cross-plugin references.

### Plugin Bundle Structure

```
omnifocus-timer.omnifocusjs/
  manifest.json              — plugin metadata, declares actions + library
  timer-lib.js               — library: core timer logic, state management
  start-timer.js             — action: Start/Switch Timer
  pause-timer.js             — action: Pause/Resume Timer
  stop-timer.js              — action: Stop Timer
  check-timer.js             — action: Check Timer Status
  Resources/
    config.js                — configurable endpoints, notification intervals
```

### Manifest

```json
{
  "defaultLocale": "en",
  "identifier": "com.dorsey.omnifocus-timer",
  "author": "Chad Dorsey",
  "description": "Start/stop/pause timer for tracking actual time spent on tasks",
  "version": "1.0.0",
  "actions": [
    { "identifier": "start-timer", "image": "clock" },
    { "identifier": "pause-timer", "image": "pause" },
    { "identifier": "stop-timer", "image": "stop" },
    { "identifier": "check-timer", "image": "info" }
  ],
  "libraries": [
    { "identifier": "timer-lib" }
  ]
}
```

### Actions

| Action | Menu Label | Behavior | Validate (enabled when) |
|--------|-----------|----------|------------------------|
| **Start/Switch Timer** | "Start Timer" | No timer → start on selected task. Different task running → stop+log that timer, start on selected. Same task running → alert "already timing this task." | Exactly 1 task selected |
| **Pause/Resume Timer** | "Pause Timer" / "Resume Timer" | Toggle pause state. Label changes based on current state. | Timer is active (running or paused) |
| **Stop Timer** | "Stop Timer" | Stop active timer, finalize session in task note, emit event, clear state. | Timer is active |
| **Check Timer** | "Check Timer" | Alert showing: task name, state, elapsed time, session count. "No timer active" if idle. | Always enabled |

### State Model (Preferences)

```javascript
{
  // Active timer state
  "activeTaskId": "omnifocus-task-identifier",
  "activeTaskName": "Review quarterly report",
  "activeProjectName": "Q1 Planning",
  "state": "running" | "paused" | "idle",
  "currentIntervalStart": 1710405300000,     // epoch ms when current interval began
  "accumulatedMs": 0,                         // ms from pause/resume cycles in current session
  "originalEstimate": 30,                     // snapshot of estimatedMinutes, taken once on first-ever timing

  // Session history for current task (JSON string)
  "sessions": "[{\"start\":1710405300000,\"end\":1710407100000,\"durationMs\":1800000}]",

  // Failed event delivery queue (JSON string)
  "pendingEvents": "[]",

  // Config
  "relayEndpoint": "http://localhost:8889/timer-event",
  "notificationIntervalMin": 15,
  "guardianIntervalSec": 60
}
```

Notes on Preferences:
- Preferences only stores primitives (Boolean, String, Number, Date, Data). Complex structures are JSON-serialized strings.
- `originalEstimate` is captured the first time a task is ever timed. If the note already contains a `--- Time Tracking ---` block with an original estimate, that value is preserved rather than re-snapshotted.
- **Size limits:** `sessions` array in Preferences holds only sessions for the *current timing engagement*. Once a session is finalized to the note, it can be pruned from Preferences. Maximum 100 sessions retained in Preferences as a safety bound. `pendingEvents` queue is capped at 50 entries; oldest events are dropped when the cap is reached (heartbeats are dropped first since they are stale by definition).

### Guardian Timer

A `Timer.repeating(60, callback)` created when a timer starts, cancelled when the timer stops (or state becomes `idle`). After orphan recovery, a new `Timer.repeating` is created since the previous timer object does not survive plugin re-initialization. On each tick:

1. **Persist to note** — compute current elapsed time, write/update the in-progress session line in the task's note. This ensures data loss on crash is bounded to 60 seconds.
2. **Check task status** — look up the task by ID. If completed or dropped, auto-stop the timer and log the final session. If task not found (deleted), auto-stop with error notation.
3. **Notification cadence** — every `notificationIntervalMin` minutes (default 15), fire a macOS `Notification`: "Timer: 45 min on 'Review quarterly report'". Clicking the notification could navigate to the task.
4. **Retry failed events** — drain `pendingEvents` queue, attempt redelivery to relay endpoint.
5. **Emit heartbeat** — POST a `timer.heartbeat` event to the relay endpoint every 5 minutes (not every tick — heartbeats are a low-frequency health signal). Heartbeats are **not queued** on failure since they are stale by definition.

### Orphan Recovery (on plugin load)

When OmniFocus launches and the plugin initializes, check Preferences for `state: "running"` or `state: "paused"`:

1. Compute the gap between `currentIntervalStart + accumulatedMs` and now.
2. If gap > `guardianIntervalSec * 2` (i.e., OmniFocus was closed), show an alert:
   - "Timer was running on 'Task Name' when OmniFocus quit. Approximately X min untracked."
   - Options: "Resume (exclude gap)" / "Stop and log" / "Resume (include gap)"
3. If gap is small (OmniFocus just restarted quickly), silently resume the guardian timer.
4. Note: the task's note already has data up to the last guardian write, so only the gap period is at risk.

### Note Format

Appended to the task's note, using delimiters for parseability:

```
--- Time Tracking ---
Original Estimate: 30 min
[2026-03-14 09:15–09:47] 32 min
[2026-03-14 14:00–14:22] 22 min
[2026-03-14 14:30 in progress] ~12 min
Total: 1h 06m
Variance: +36 min (+120%)
--- End Time Tracking ---
```

**Rules:**
- `--- Time Tracking ---` / `--- End Time Tracking ---` delimiters allow finding and updating the block without disturbing other note content.
- If the task already has notes, the time tracking block is appended at the end with a blank line separator.
- The `[in progress]` line includes the session start time and is updated by the guardian every 60s, then replaced with a finalized line on stop.
- `Total` and `Variance` lines are recomputed on every write.
- `Variance` line is only shown when an original estimate exists. Zero variance is formatted as `Variance: 0 min (0%)`.
- `Original Estimate` line reads "none" if no estimate was set.
- Times are in the local timezone, formatted as `HH:MM` for readability.
- **Sessions spanning midnight:** use dual-date format: `[2026-03-14 23:30–2026-03-15 00:15] 45 min`. The duration value is authoritative; the timestamps are informational. Parsers should use the duration, not compute from start/end times.
- Durations use minutes for <60 min, `Xh YYm` for longer.

### Outbound Events

On every state change, the plugin POSTs to the configured relay endpoint:

```json
{
  "event": "timer.started",
  "taskId": "omnifocus-task-id",
  "taskName": "Review quarterly report",
  "projectName": "Q1 Planning",
  "sessionDurationMs": 1920000,
  "totalDurationMs": 3240000,
  "originalEstimateMin": 30,
  "timestamp": "2026-03-14T09:47:00Z",
  "previousTaskId": "other-task-id"
}
```

**Event types:** `timer.started`, `timer.paused`, `timer.resumed`, `timer.stopped`, `timer.switched`, `timer.auto-stopped` (guardian detected completion), `timer.heartbeat`.

**Failure handling:** If the HTTP call fails, the event is serialized and appended to `pendingEvents` in Preferences. The guardian retries on subsequent ticks. The plugin never blocks on network availability.

### Inbound Library Functions

Exposed via `PlugIn.Library` for external callers (omnifocus-cli, host bridge):

| Function | Parameters | Returns | Behavior |
|----------|-----------|---------|----------|
| `startTimer` | `taskId: String` | `{status, taskName, ...}` | Start or switch timer. Same logic as Start action but without requiring UI selection. |
| `stopTimer` | none | `{status, finalSession, totalMs}` | Stop active timer. |
| `pauseTimer` | none | `{status, elapsedMs}` | Pause active timer. |
| `resumeTimer` | none | `{status}` | Resume paused timer. |
| `getTimerStatus` | none | `{state, taskId, taskName, projectName, currentSessionMs, totalMs, sessionCount, originalEstimateMin}` | Current timer state. Returns `{state: "idle"}` if no timer active. |
| `getTimerHistory` | `taskId: String` | `{sessions: [...], totalMs, originalEstimateMin, variance}` | Parse time tracking block from task note. Works on any task, not just the active one. |

These functions are called via:
```javascript
PlugIn.find('com.dorsey.omnifocus-timer').library('timer-lib').startTimer(taskId)
```

---

## Component 2: omnifocus-cli Timer Commands

New `timer` command group in the existing omnifocus-cli:

| Command | Arguments | Description |
|---------|-----------|-------------|
| `timer start` | `<task-id>` | Start timer on specified task. Auto-stops any running timer. |
| `timer stop` | none | Stop the active timer and finalize the session. |
| `timer pause` | none | Pause the active timer. |
| `timer resume` | none | Resume the paused timer. |
| `timer status` | none | Return current timer state as JSON. |
| `timer history` | `<task-id>` | Return parsed time tracking data from a task's note. |

**Implementation:** The existing `bridge.py` and `host-bridge-service.js` are hardcoded to call `PlugIn.find('omnifocus-mcp').library('omnifocus-mcp').request(payload)`. Timer commands need to target a different plugin. Two options:

1. **Plugin-aware bridge routing (recommended):** Modify `bridge.py` and `host-bridge-service.js` to accept an optional `plugin` parameter. When provided, the osascript template calls `PlugIn.find('<plugin-id>').library('<lib-id>').<method>(params)` instead of routing through the MCP plugin's `request()` dispatcher. When omitted, behavior is unchanged (backwards compatible). Timer CLI commands pass `plugin="com.dorsey.omnifocus-timer", library="timer-lib"`.

2. **Dedicated timer osascript path:** Timer CLI commands generate their own osascript strings directly, bypassing `bridge.py`. Simpler but duplicates the osascript generation logic.

Option 1 is preferred — it's a small change to the bridge (add a plugin/library parameter to the osascript template) that keeps all OmniFocus communication through a single path and makes future plugins easy to integrate.

**Status response example:**
```json
{
  "state": "running",
  "taskId": "abc123",
  "taskName": "Review quarterly report",
  "projectName": "Q1 Planning",
  "currentSessionMs": 1320000,
  "totalMs": 3240000,
  "sessionCount": 3,
  "originalEstimateMin": 30
}
```

---

## Component 3: Host Bridge Timer Relay

A new endpoint added to the existing `host-bridge-service.js` (port 8889).

**Note on routing:** The current host bridge only handles `POST /execute` and returns 404 for all other paths. Adding `/timer-event` requires expanding the URL routing in the request handler (a simple if/else chain — no framework needed, consistent with the bridge's minimal style).

### Endpoint: `POST /timer-event`

**Request body:** The event payload from the timer plugin (see Outbound Events above).

**Behavior:**
1. Format the event as a natural-language message appropriate for the Letta agent.
2. POST to `http://localhost:8283/v1/agents/{rover-agent-id}/messages` with the formatted message.
3. Return 200 to the caller regardless of Letta delivery success (the plugin must never block on Letta).
4. Log delivery failures to the bridge service log for debugging.

**Message formatting examples:**

| Event | Message to Rover |
|-------|-----------------|
| `timer.started` | "Timer started on 'Review quarterly report' (Q1 Planning). Estimated duration: 30 min." |
| `timer.switched` | "Timer switched from 'Draft email' to 'Review quarterly report'. Previous session: 22 min." |
| `timer.stopped` | "Timer stopped on 'Review quarterly report'. Session: 22 min. Total across 3 sessions: 1h 06m. Original estimate: 30 min — actual is 120% over." |
| `timer.auto-stopped` | "Timer auto-stopped: 'Review quarterly report' was marked complete. Final time: 1h 06m (estimate was 30 min)." |
| `timer.heartbeat` | Not forwarded to Letta (internal health signal only, unless Rover has subscribed to heartbeats). |

**Configuration:** The Rover agent ID is configured in the host bridge service's environment or a config file, not hardcoded.

---

## Component 4: Letta Agent Integration

### Rover's Timer Awareness

Rover uses the existing OmniFocus CLI tool pattern to execute timer commands. **Prerequisite check:** Phase 3 must verify that Rover has a tool capable of executing `omnifocus-cli` commands (e.g., `run_omnifocus_cli` or a shell execution tool). If no such tool exists, one must be created and attached as part of Phase 3.

Rover's system prompt / persona block should be updated with timer-related behaviors:

- **On receiving `timer.stopped` events:** Note the estimate vs. actual variance. If the user consistently underestimates certain types of tasks, surface the pattern: "Your last 5 'review' tasks averaged 2x their estimates."
- **On receiving `timer.started` events:** Brief acknowledgment, especially if Rover suggested the task.
- **On receiving `timer.switched` events:** Note the context switch for workload awareness.
- **On task presentation ("work on X next"):** When the user agrees, Rover issues `timer start <taskId>` automatically.
- **Periodic status checks:** Rover can call `timer status` on a cadence and nudge if time exceeds the estimate by a configurable threshold (e.g., 150%): "You've been on 'Review quarterly report' for 45 min — your estimate was 30 min. Want to keep going or switch?"
- **Before completing tasks:** When asked to complete a task, check if a timer is running on it and stop it first.

### Mission Control's Role

Mission Control (server-side) receives timer events forwarded from Rover or directly if configured. Its role is long-term pattern analysis:
- Track estimate accuracy trends over weeks/months
- Identify task categories where estimates are consistently off
- Surface insights during weekly reviews

This is a future enhancement — Phase 3 focuses on Rover only.

---

## Note Format Parsing Specification

For machine consumption (by `timer history`, Rover, analytics):

```
--- Time Tracking ---
Original Estimate: <N> min | none
[<YYYY-MM-DD HH:MM–HH:MM>] <duration>
[<YYYY-MM-DD HH:MM> in progress] ~<duration>
Total: <duration>
Variance: +/-<N> min (+/-<N>%) | n/a
--- End Time Tracking ---
```

**Regex patterns:**
- Session line (same day): `\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})–(\d{2}:\d{2})\] (.+)`
- Session line (cross-midnight): `\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})–(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\] (.+)`
- In-progress line: `\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) in progress\] ~(.+)`
- Original estimate: `Original Estimate: (?:(\d+) min|none)`
- Total: `Total: (.+)`
- Variance: `Variance: (?:([+-]?\d+) min \(([+-]?\d+)%\)|n\/a)`

The `timer history` command and Rover both use these patterns to extract structured data from the note text.

---

## Implementation Phases

### Phase 1: Core Plugin (standalone, no integration)
- Timer plugin with all four actions (Start/Switch, Pause/Resume, Stop, Check)
- Preferences-based state management
- Guardian timer with incremental note persistence
- macOS notifications on cadence
- Orphan recovery on OmniFocus launch
- **Deliverable:** Working timer within OmniFocus, no external dependencies

### Phase 2: CLI Integration
- Timer library functions exposed in the plugin
- Modify `bridge.py` and `host-bridge-service.js` to support plugin-aware routing (target plugin parameter)
- omnifocus-cli `timer` command group (start, stop, pause, resume, status, history)
- **Deliverable:** Letta agents (and any CLI user) can control the timer programmatically

### Phase 3: Letta Integration
- `/timer-event` relay endpoint on host bridge service
- Outbound event emission from the plugin
- Failed-event queue and retry logic
- Rover prompt/persona updates for timer awareness
- Rover periodic status checking and nudge behavior
- **Deliverable:** Full two-way integration; Rover is timer-aware

### Phase 4 (Future): Hardware Toggle
- Caps Lock key (or other physical key) mapped as timer start/stop toggle
- Implementation via Karabiner-Elements, Hammerspoon, or custom Swift utility
- Depends on Phase 2 (calls `omnifocus-cli timer` commands)
- **Separate mini-project**, orthogonal to Phases 1-3

### Phase 5 (Future): Analytics & Estimation Improvement
- Mission Control long-term trend tracking
- Estimate accuracy reports by project/tag/task type
- Suggested estimate adjustments based on historical data
- Web dashboard or periodic summary reports
- **Depends on:** sufficient timer data accumulated from Phases 1-3

---

## Technical Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Guardian timer stops when OmniFocus backgrounds | Gap in note persistence | Orphan recovery on relaunch; gap is bounded and surfaced to user |
| Plugin context resets on OmniFocus update | Timer state lost mid-session | All state in Preferences (survives updates); orphan recovery handles this |
| Task note gets very long with many sessions | Note readability degrades | Delimited block is at the end; could add a "compact" mode later that summarizes old sessions |
| Host bridge service not running when plugin emits events | Events lost | Failed-event queue in Preferences with guardian retry |
| Two OmniFocus windows with different selections | Ambiguous "selected task" for Start action | Start action validates exactly 1 task selected; library `startTimer(taskId)` takes explicit ID |
| Cross-device sync conflicts on task notes | Two devices write different note content | Mac-primary workflow mitigates this; note block uses append-only pattern within delimiters |
| `URL.FetchRequest` unavailable in Timer callback context | Outbound events cannot be sent from guardian | Validate in Phase 1 prototype; fallback: guardian writes events to Preferences queue, a separate `Timer.once` dispatches them |
| Preferences string size degrades with many sessions | Slowdown on read/write | Cap sessions at 100 in Preferences; cap pendingEvents at 50; prune after note persistence |

---

## Open Questions

1. **`URL.FetchRequest` in `Timer.repeating` callbacks:** The OmniFocus Automation API documentation does not explicitly state whether `URL.FetchRequest` is available inside timer callback contexts (vs. action/library contexts). This must be validated with a quick prototype early in Phase 1. If unavailable, the fallback is to queue events in Preferences and dispatch them from action invocations or a `Timer.once` chain.

2. **Rover's OmniFocus CLI tool:** Phase 3 assumes Rover has a Letta tool that can execute `omnifocus-cli` commands. This needs to be verified — if no such tool exists, it must be created as part of Phase 3.
