# OmniFocus Timer Floating Widget — Design Spec

**Date:** 2026-03-14
**Status:** Draft
**Goal:** A small floating macOS widget that displays the active OmniFocus timer state, provides play/pause/stop controls, accepts task queue commands from Letta/Rover, and serves as an ambient indicator of active work.

---

## Overview

A standalone Swift macOS app that renders a borderless floating window pinned to the upper-right corner of the screen, just below the menu bar. The widget shows the currently timed OmniFocus task with play/pause/stop controls. It polls the OmniFocus timer plugin for state, provides direct control via osascript, and accepts task queue commands from Letta/Rover via a local command file.

## Success Criteria

1. Widget appears automatically when a timer is running or paused
2. Widget appears when Letta/Rover pushes tasks to the queue
3. Widget disappears (fades out) when the timer is stopped and no queued tasks remain
4. User can play/pause/stop the timer directly from the widget
5. User can browse queued tasks with navigation arrows and start any of them
6. Clicking the task name brings OmniFocus to the front with the task selected
7. Widget is visible on all Spaces/desktops and stays above other windows
8. No Dock icon, no menu bar icon — the widget is the entire UI

## Non-Goals

- Server communication (Letta events are handled by the plugin independently)
- Multiple simultaneous timers (only one timer can be active at a time)
- Displaying elapsed time (space constraint; user checks via Check Timer action or CLI)
- Displaying project name (task name is sufficient for the widget's purpose)

---

## Visual States

### Queued (Light Green — Letta suggested tasks)

- **Background:** Light green (`#A8E6CF` or similar soft green)
- **Text:** Black
- **Animation:** 3-second pulse cycle — 0.5s quick fade to full opacity (1.0), then 2.5s gradual ease-out fade to 70% opacity (0.7). Repeat.
- **Play button:** Full green bubble-like glow effect around the Play icon, enticing the user to start. The glow pulses in sync with the window animation.
- **Left buttons:** Play (▶) and Stop/dismiss (⏹), stacked vertically
- **Right side:** Estimate display (large number + small unit) and navigation dots with ◀/▶ arrows
- **Trigger:** Letta/Rover writes tasks to the command file

### Running (Green)

- **Background:** Green (`#34C759` or system green)
- **Text:** Black
- **Animation:** Subtle 1-second pulse cycle — opacity oscillates between 0.92 and 1.0, with a soft outer glow that waxes and wanes in sync. Barely noticeable; conveys "alive" without being distracting.
- **Left buttons:** Pause (⏸) and Stop (⏹), stacked vertically
- **Right side:** Navigation dots only (if queued tasks exist), no estimate display. New dots animate in with a 1s fade when Rover pushes tasks.

### Paused (Gray)

- **Background:** Gray (`#8E8E93` or system gray)
- **Text:** Black
- **Animation:** None (completely static)
- **Left buttons:** Play (▶) and Stop (⏹), stacked vertically
- **Right side:** Navigation dots only (if queued tasks exist)

### Stopped (Red → Fade Out)

- **Background:** Red (`#FF3B30` or system red)
- **Text:** Black
- **Animation:** 30-second fade-out. Opacity decreases from 1.0 to 0.0 using an ease-in-ease-out curve. If queued tasks exist, transitions to Queued state instead of fading.
- **Left buttons:** Play (▶) visible (restarts the same task using cached taskId)

**Fade-out hover behavior:**
- Mouse enters the widget: immediately snap to opacity 1.0
- Mouse leaves before 5 seconds of hover: resume the fade from the opacity it was at when interrupted (visible jump from 1.0 back to the interrupted opacity is intentional — the hover is a brief "peek")
- Mouse stays for 5+ seconds: reset the 30-second fade timer entirely. Fade restarts from the beginning after the mouse leaves.

### Idle (Hidden)

- Widget is not visible
- Polling continues in the background to detect when a new timer starts or tasks are queued

---

## Layout

### Queued State (full layout)

```
┌──────────────────────────────────────────────────┐
│ ▶  Review quarterly report for the       30      │
│ ⏹  upcoming board meeting and ens…      min      │
│                                     ◀  ● ○ ○  ▶  │
└──────────────────────────────────────────────────┘
```

### Running/Paused State (compact right side)

```
┌──────────────────────────────────────────────────┐
│ ⏸  Review quarterly report for the    ● ○ ○     │
│ ⏹  upcoming board meeting and ens…               │
└──────────────────────────────────────────────────┘
```

Navigation dots appear only when queued tasks exist alongside the active timer. No estimate display during Running/Paused — the estimate is relevant during task selection (Queued), not during execution.

### Stopped State (minimal)

```
┌──────────────────────────────────────────────────┐
│ ▶  Review quarterly report for the               │
│    upcoming board meeting and ens…                │
└──────────────────────────────────────────────────┘
```

---

## Layout Details

**Position:** Upper-right corner of the screen, pinned just below the menu bar. Right edge aligned approximately with the WiFi icon in the menu bar.

**Dimensions:**
- Width: ~300px (slightly wider to accommodate right-side elements)
- Height: ~36px (single-line), ~52px (two-line), ~64px (two-line + navigation row in Queued state)
- Corner radius: 8px
- Padding: 6px horizontal, 4px vertical

**Left Buttons:**
- Play/Pause (▶/⏸) and Stop (⏹) as SF Symbol icons, ~14pt
- Stacked vertically on the left side
- Subtle background highlight on hover (white at 15% opacity, small rounded rect) to telegraph clickability

**Task Name (center):**
- Left-aligned to an invisible vertical border right of the buttons
- System font, 11pt, bold
- Up to 2 lines, wrapping at word boundaries
- After ~50 characters across two lines, truncate with ellipsis (…)

**Right Side — Estimate (Queued state only):**
- Large number (e.g., "30") — system font, 18pt, semibold. Larger and bolder than task text.
- Small unit below ("min" or "hr") — system font, 8pt, regular. Notably smaller than task text.
- Vertically centered in the right portion of the widget

**Right Side — Navigation (Queued state, bottom row):**
- ◀ and ▶ arrow buttons flanking navigation dots
- Dots: filled circle (●) for current task, hollow circle (○) for others
- First item in queue: only ▶ arrow visible. Last item: only ◀ arrow visible. Middle items: both visible.
- New dots animate in with a 1-second fade, smoothly pushing existing dots to their new positions
- Arrow buttons and dots have subtle hover highlight

**Right Side — Navigation (Running/Paused state):**
- Navigation dots only (no arrows, no estimate). Shown only if queued tasks exist.
- Dots indicate that tasks are waiting; user must stop or complete the current timer to browse them.

**Window Properties:**
- `NSWindow.Level.floating` — stays above all other windows
- `NSWindow.CollectionBehavior.canJoinAllSpaces` and `.stationary` — visible on every Space/desktop, not shown in Mission Control
- `NSWindow.StyleMask.borderless` — no title bar, no chrome
- `LSUIElement = true` — no Dock icon
- When fully faded (opacity 0), ignores mouse events (clicks pass through to windows below)

---

## Interaction

**Click on task name area:**
Open OmniFocus and navigate to the task. Use the URL scheme: `omnifocus:///task/<taskId>`. This brings OmniFocus to the front and selects the task.

**Click Play button:**
- Queued → start timer on the displayed task via `timerLib.startTimerOnTask(taskId)`. Transition to Running. Remove task from queue.
- Paused → resume via `timerLib.resumeTimer()`. Transition to Running.
- Stopped → restart the same task via `timerLib.startTimerOnTask(cachedTaskId)`. Transition to Running.

**Click Pause button:**
- Running → pause via `timerLib.pauseTimer()`. Transition to Paused.

**Click Stop button:**
- Running or Paused → stop via `timerLib.stopTimer()`. If queued tasks exist, transition to Queued. Otherwise transition to Stopped (red, fade).
- Queued → dismiss the current queued task. Remove it from the queue. If more tasks remain, show the next one. If no tasks remain, transition to Idle.

**Click ◀/▶ navigation arrows (Queued state only):**
Browse through the queued task list. Updates the displayed task name, estimate, and navigation dots. Does not start a timer.

**Button hover:**
All buttons show a subtle highlight (white at 15% opacity, small rounded rect behind the icon) when the mouse hovers over them.

---

## Letta/Rover Command Interface

### Command File

The widget watches `~/.omnifocus-timer-widget/queue.json` for changes (via `DispatchSource.makeFileSystemObjectSource` or polling). Rover writes to this file from the laptop via Bash.

**File format:**

```json
{
  "tasks": [
    {
      "taskId": "kfoxe4jHuHr",
      "taskName": "Review quarterly report for the board meeting",
      "estimateMin": 30
    },
    {
      "taskId": "abc123",
      "taskName": "Reply to Sarah's email",
      "estimateMin": 5
    }
  ]
}
```

### Rover Commands (via Bash on the laptop)

**Push a task to the queue:**
```bash
# Read current queue, append task, write back
python3 -c "
import json, os
path = os.path.expanduser('~/.omnifocus-timer-widget/queue.json')
try:
    data = json.load(open(path))
except:
    data = {'tasks': []}
data['tasks'].append({'taskId': '$TASK_ID', 'taskName': '$TASK_NAME', 'estimateMin': $EST})
json.dump(data, open(path, 'w'))
"
```

**Replace the entire queue:**
```bash
echo '{"tasks": [...]}' > ~/.omnifocus-timer-widget/queue.json
```

**Clear the queue:**
```bash
echo '{"tasks": []}' > ~/.omnifocus-timer-widget/queue.json
```

### Queue Rules

- Rover can add tasks to any position in the queue except displacing the currently viewed task (the task at the current navigation index)
- When a task is started (Play clicked), it is removed from the queue
- When a task is dismissed (Stop clicked in Queued state), it is removed from the queue
- Maximum queue size: ~10 tasks (practical limit; navigation dots become unwieldy beyond this)
- The widget re-reads the command file on each poll cycle (every 2 seconds) or via filesystem watcher

### New Task Arrival Animation

When a new task appears in the queue (file changed, new entry detected):
- A new navigation dot fades in over 1 second
- Existing dots smoothly slide to their new positions
- The widget does NOT auto-navigate to the new task — the user stays on their current selection
- If the widget was Idle/Hidden and tasks are pushed, it transitions to the Queued state

---

## Data Flow

### Polling (every 2 seconds, poll-then-wait)

The app polls timer status. The next poll starts 2 seconds after the previous poll **completes** (not on a fixed interval) to prevent stacking if osascript is slow.

```
osascript -e 'tell application "OmniFocus" to evaluate javascript
  "JSON.stringify(PlugIn.find(\"com.dorsey.omnifocus-timer\").library(\"timerLib\").getTimerStatus())"'
```

Response JSON:
```json
{
  "status": "running" | "paused" | "idle",
  "taskId": "kfoxe4jHuHr",
  "taskName": "Review quarterly report for the upcoming board meeting",
  "projectName": "Q1 Planning",
  "elapsedFormatted": "3m 25s",
  "sessionCount": 2,
  "originalEstimate": 30
}
```

**State mapping:**
- `"running"` → Running (green, pulsing)
- `"paused"` → Paused (gray, static)
- `"idle"` → if previous poll was `"running"` or `"paused"`, transition to Stopped (red, fade) — or to Queued if tasks are queued. If previous poll was also `"idle"`, remain in current state (Hidden or Queued).

**The widget must locally cache the most recent `taskId` and `taskName`** from polling responses so they remain available during the Stopped/fade-out state, when the plugin reports `idle` with no task information.

### Queue File Monitoring

On each poll cycle (or via filesystem watcher), read `~/.omnifocus-timer-widget/queue.json`. Diff against the current in-memory queue to detect additions/removals and trigger dot animations.

### Button Actions

Each button action runs osascript asynchronously (fire-and-forget). The next poll picks up the state change.

```swift
func runOmniJS(_ js: String) {
    // Use Process with osascript, escaping the JS string properly
    // for embedding in AppleScript double-quoted strings
}
```

**Note:** The JS string must be properly escaped for AppleScript embedding. Task IDs containing special characters should be escaped. Use `NSAppleScript` or write to a temp file to avoid shell quoting issues.

### Navigate to Task

```swift
NSWorkspace.shared.open(URL(string: "omnifocus:///task/\(taskId)")!)
```

---

## Architecture

**SwiftUI app** with AppKit window management. No external dependencies.

```
TimerWidget/
  TimerWidgetApp.swift    — App entry point, NSWindow setup
  WidgetView.swift        — SwiftUI view with state-dependent rendering
  TimerState.swift        — ObservableObject: timer state, queue, fade, animation
  OmniFocusBridge.swift   — osascript polling and command execution
  QueueManager.swift      — File watching, queue diffing, Letta command interface
  Info.plist              — LSUIElement=true, bundle ID
```

**Build:** Xcode project or Swift Package. Target: macOS 13+.

**Launch at login:** macOS Login Items (System Settings → General → Login Items) or a launchd plist.

---

## Technical Notes

- The osascript call takes ~0.5-1s. With a 2-second poll-then-wait interval, there's a ~1-3 second lag between timer state changes and widget updates. Animations run independently of the data refresh.
- When OmniFocus is not running, the osascript call will fail. The widget handles this gracefully — stays hidden or shows only the Queued state (which doesn't require OmniFocus).
- If the timer plugin is not installed, `PlugIn.find()` returns null and the osascript call throws. Same handling as OmniFocus-not-running.
- The widget should not prevent sleep or interfere with screen savers.
- The fade-out animation state (current opacity, hover timer) is local to the Swift app and independent of the OmniFocus timer state.
- The `~/.omnifocus-timer-widget/` directory is created by the app on first launch if it doesn't exist.
