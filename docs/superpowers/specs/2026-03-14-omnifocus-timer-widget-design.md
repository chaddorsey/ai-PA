# OmniFocus Timer Floating Widget — Design Spec

**Date:** 2026-03-14
**Status:** Draft
**Goal:** A small floating macOS widget that displays the active OmniFocus timer state, provides play/pause/done controls, accepts task queue commands from Letta/Rover, and serves as an ambient indicator of active work with celebratory completion animations.

---

## Overview

A standalone Swift macOS app that renders a borderless floating window pinned to the upper-right corner of the screen, just below the menu bar. The widget shows the currently timed OmniFocus task with play/pause/done controls. It polls the OmniFocus timer plugin for state, provides direct control via osascript, and accepts task queue commands from Letta/Rover via a local command file.

## Success Criteria

1. Widget appears automatically when a timer is running, paused, or tasks are queued
2. User can play/pause/complete tasks directly from the widget
3. Completing a task marks it done in OmniFocus, triggers a confetti celebration, and transitions to the next queued task
4. Undo is available for a limited window after completion
5. User can browse queued tasks; browsing while running pauses the current task
6. Clicking the task name brings OmniFocus to the front with the task selected
7. Caps Lock integration: starts tasks and completes running tasks
8. Widget is visible on all Spaces/desktops and stays above other windows
9. No Dock icon, no menu bar icon — the widget is the entire UI

## Non-Goals

- Displaying elapsed time in the widget (user checks via Check Timer action or CLI)
- Displaying project name (task name is sufficient)
- Stop/abandon button (user pauses and switches to another task instead)
- Visual distinction between pristine and in-progress queued tasks (future enhancement)

---

## Visual States

### Queued (Light Green — tasks waiting to be started)

- **Background:** Light green (`#A8E6CF` or similar soft green)
- **Text:** Black
- **Animation:** 3-second pulse cycle — 0.5s quick fade to full opacity (1.0), then 2.5s gradual ease-out fade to 70% opacity (0.7). Repeat.
- **Play button:** Full green bubble-like glow effect around the Play icon, enticing the user to start. The glow pulses in sync with the window animation.
- **Left buttons:** Play (▶) only
- **Right side:** Estimate display (large number + small unit) and navigation dots with ◀/▶ arrows
- **Trigger:** Letta/Rover writes tasks to the command file, or timer status becomes idle with tasks in queue

### Running (Green)

- **Background:** Green (`#34C759` or system green)
- **Text:** Black
- **Animation:** Subtle 1-second pulse cycle — opacity oscillates between 0.92 and 1.0, with a soft outer glow that waxes and wanes in sync. Barely noticeable; conveys "alive" without being distracting.
- **Left buttons:** Pause (⏸) vertically stacked with Done (✓). The Done check mark is darker green than the background with an attractive glossy appearance, enticing the user to complete the task.
- **Right side:** Navigation dots only (if queued tasks exist). No estimate display during execution.

### Paused (Gray)

- **Background:** Gray (`#8E8E93` or system gray)
- **Text:** Black
- **Animation:** None (completely static)
- **Left buttons:** Play (▶) vertically stacked with Done (✓)
- **Right side:** Navigation dots with ◀/▶ arrows (user can browse queue while paused)

### Completing (Transition — ~4.5 seconds)

A multi-phase animation triggered when the user clicks Done (✓) or presses Caps Lock while running:

**Phase 1 — Celebration (0s–2s):**
- Task is marked complete in OmniFocus and timer is stopped
- Widget pulses once (brief scale/opacity bump)
- Miniature confetti shower erupts from the widget — particles propelled both upward (slightly into the menu bar space) and downward. Confetti falls with gravity acceleration, fading in opacity as it descends, fully transparent by the vertical midpoint of the screen. Total confetti duration: ~2 seconds.
- Pause button becomes Undo (↩) button

**Phase 2 — Task Exit (0s–3s, overlaps with confetti):**
- Completed task text slides right, easing up in speed as it exits, disappearing under/past the button area
- The completed task's navigation dot slides off the left edge of the dot row

**Phase 3 — New Task Entry (1.5s–4.5s, staggered):**
- New task text fades in from 0% opacity over 3 seconds (ease-in), beginning 1.5 seconds after the slide-out starts
- Navigation dots adjust to reflect the remaining queue

**Phase 4 — Button Reset (after new task is fully visible):**
- Undo button animates to a very small round undo button, repositioning to the upper-left corner of the widget
- Main button position becomes Play (▶) again (new task is queued, not yet started)
- Small undo button fades over 15 seconds with the same hover behavior as the fade-out (hover snaps to full opacity; <5s hover resumes fade; 5s+ hover resets the 15s timer)

### Last Task Completed (Green → Fade Out)

When the completed task is the only/last task in the queue:

- Same confetti celebration
- Widget remains **green** (NOT red) — no task text to slide out, just fades
- Undo (↩) replaces Play button
- Widget begins 30-second fade-out (ease-in-ease-out, opacity 1.0 → 0.0)
- Same hover behavior as before (snap to 1.0 on hover; <5s resumes; 5s+ resets)
- Undo button available throughout the fade period
- Once fully faded, transitions to Idle (Hidden)

### Idle (Hidden)

- Widget is not visible
- Polling continues in the background to detect new timers or queued tasks

---

## Layout

### Queued State (full layout with estimate and navigation)

```
┌──────────────────────────────────────────────────┐
│ ▶  Review quarterly report for the       30      │
│    upcoming board meeting and ens…       min      │
│                                     ◀  ● ○ ○  ▶  │
└──────────────────────────────────────────────────┘
```

### Running State (pause + done buttons, dots if queued tasks exist)

```
┌──────────────────────────────────────────────────┐
│ ⏸  Review quarterly report for the    ● ○ ○     │
│ ✓  upcoming board meeting and ens…               │
└──────────────────────────────────────────────────┘
```

### Paused State (play + done, navigation available)

```
┌──────────────────────────────────────────────────┐
│ ▶  Review quarterly report for the    ● ○ ○     │
│ ✓  upcoming board meeting and ens…    ◀     ▶   │
└──────────────────────────────────────────────────┘
```

### Post-Completion (small undo in corner, new task queued)

```
┌──────────────────────────────────────────────────┐
│↩▶  Reply to Sarah's email               5       │
│    about the budget proposal            min      │
│                                       ● ○  ▶    │
└──────────────────────────────────────────────────┘
```

The small ↩ in the upper-left is the fading undo button (round, compact).

---

## Layout Details

**Position:** Upper-right corner of the screen, pinned just below the menu bar. Right edge aligned approximately with the WiFi icon in the menu bar.

**Dimensions:**
- Width: ~300px
- Height: ~36px (single-line), ~52px (two-line), ~64px (two-line + navigation row)
- Corner radius: 8px
- Padding: 6px horizontal, 4px vertical

**Left Buttons:**
- Play/Pause (▶/⏸) and Done (✓) as SF Symbol icons, ~14pt
- Stacked vertically on the left side
- Done check mark: darker green than background, glossy/raised appearance
- Subtle background highlight on hover (white at 15% opacity, small rounded rect) on all buttons

**Task Name (center):**
- Left-aligned to an invisible vertical border right of the buttons
- System font, 11pt, bold
- Up to 2 lines, wrapping at word boundaries
- After ~50 characters across two lines, truncate with ellipsis (…)

**Right Side — Estimate (Queued state only):**
- Large number (e.g., "30") — system font, 18pt, semibold
- Small unit below ("min" or "hr") — system font, 8pt, regular
- Vertically centered in the right portion

**Right Side — Navigation:**
- ◀ and ▶ arrow buttons flanking navigation dots (in Queued and Paused states)
- Dots only, no arrows (in Running state — user must pause to browse)
- Filled circle (●) for current task, hollow circle (○) for others
- First item: only ▶ visible. Last item: only ◀ visible.
- New dots animate in with a 1-second fade, smoothly pushing existing dots to their positions
- Completed task dots slide off the left edge during completion animation

**Small Undo Button (post-completion):**
- Round, compact (~16px diameter), positioned in the upper-left corner of the widget
- Fades from full opacity to 0 over 15 seconds
- Hover behavior: snap to 1.0 on enter; <5s hover resumes fade; 5s+ hover resets 15s timer

**Window Properties:**
- `NSWindow.Level.floating` — stays above all other windows
- `NSWindow.CollectionBehavior.canJoinAllSpaces` and `.stationary` — visible on every Space/desktop, not shown in Mission Control
- `NSWindow.StyleMask.borderless` — no title bar, no chrome
- `LSUIElement = true` — no Dock icon
- When fully faded (opacity 0), ignores mouse events (clicks pass through)

---

## Caps Lock Integration

The toggle script (`~/Dropbox/dev/omnifocus-timer/toggle-timer.sh`) integrates with the widget:

| Current State | Caps Lock Press | Result |
|--------------|----------------|--------|
| Idle/Queued (no timer) | Start timer on displayed task | → Running, LED on |
| Running | Complete task (same as ✓ click) | → Completing transition, LED off |
| Paused | Start/resume the paused task | → Running, LED on |

**Caps Lock does NOT pause.** Pausing is a widget-only function.

The toggle script needs to be updated to call `markComplete` + `stopTimer` instead of just `stopTimer` when a timer is running.

---

## Queue Browsing While Running

When the user pages ◀/▶ through the queue while a task is **running**:
1. The current running task is **paused** (timer paused in OmniFocus)
2. Caps Lock LED turns off
3. Widget transitions to show the browsed-to task in **Queued** state (light green, with Play button)
4. The paused task remains in the queue (it retains its timer data in the OmniFocus note)
5. User can:
   - Click Play on the new task → starts timing it
   - Page back to the paused task → click Play to resume it
   - Browse further through the queue

**Navigation dots during Running state** show dots but NO arrows. The user must first pause (via the Pause button) to enable browsing. This prevents accidental task switches during active work.

Wait — correction per the design: paging itself pauses the task. So the arrows ARE visible during Running, and clicking them triggers the pause + browse behavior.

Actually, let me re-read the requirement: "If the user pages to a new task while a task is running, that task is paused." This means arrows are visible during Running and clicking them auto-pauses.

**Revised:** Navigation arrows are visible in Running state when queued tasks exist. Clicking ◀/▶ while running auto-pauses the current task and shows the target queued task.

---

## Interaction Summary

**Click on task name area:**
Open OmniFocus and navigate to the task via `omnifocus:///task/<taskId>`.

**Click Play (▶):**
- Queued → start timer on displayed task. Transition to Running. Remove from queue.
- Paused → resume timer. Transition to Running.

**Click Pause (⏸):**
- Running → pause timer. Transition to Paused. Caps Lock LED off.

**Click Done (✓):**
- Running or Paused → stop timer, mark task complete in OmniFocus. Trigger Completing transition.

**Click Undo (↩) — small button, post-completion:**
- Mark task incomplete in OmniFocus. Place task back in Paused state. Timer data preserved.

**Click ◀/▶ navigation:**
- Queued/Paused → browse to adjacent task in queue. No state change.
- Running → auto-pause current task, browse to adjacent queued task.

**Button hover:**
All buttons show a subtle highlight (white at 15% opacity, small rounded rect) on hover.

---

## Undo Behavior

When Done (✓) is clicked:
1. Pause button immediately becomes Undo (↩)
2. Timer is stopped, task is marked complete in OmniFocus
3. Completion animation plays (confetti, slide-out, new task fade-in)
4. After new task is visible, Undo animates to a small round button in the upper-left corner
5. Undo fades over 15 seconds (hover behavior: snap on enter, <5s resumes, 5s+ resets)

When Undo (↩) is clicked (during the fade window):
1. Task is marked incomplete in OmniFocus (`markIncomplete()`)
2. Task is placed back in Paused state (timer data preserved in notes)
3. Widget shows the un-done task in Paused state
4. If a new task had already been started, it is paused and the un-done task takes focus

---

## Letta/Rover Command Interface

### Command File

The widget watches `~/.omnifocus-timer-widget/queue.json` for changes (via `DispatchSource.makeFileSystemObjectSource` or polling).

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

- Rover can add tasks to any position in the queue except displacing the currently viewed task
- When a task is started (Play clicked), it is removed from the queue
- When a task is completed (Done clicked), it is marked done in OmniFocus and removed from the queue
- Tasks that were previously started and paused retain their timer data (in OmniFocus notes) and remain in the queue
- Maximum queue size: ~10 tasks
- The widget re-reads the command file on each poll cycle or via filesystem watcher

### New Task Arrival Animation

When a new task appears in the queue:
- A new navigation dot fades in over 1 second
- Existing dots smoothly slide to their new positions
- The widget does NOT auto-navigate to the new task
- If the widget was Idle/Hidden, it transitions to the Queued state

---

## Data Flow

### Polling (every 2 seconds, poll-then-wait)

The next poll starts 2 seconds after the previous poll **completes** to prevent stacking.

```
osascript -e 'tell application "OmniFocus" to evaluate javascript
  "JSON.stringify(PlugIn.find(\"com.dorsey.omnifocus-timer\").library(\"timerLib\").getTimerStatus())"'
```

**State mapping:**
- `"running"` → Running (green, pulsing)
- `"paused"` → Paused (gray, static)
- `"idle"` → if previous poll was `"running"` or `"paused"`, check queue: if tasks queued → Queued state; if no tasks → Last Task Completed fade-out. If previous poll was also `"idle"`, remain in current state.

**The widget must locally cache the most recent `taskId` and `taskName`** from polling responses so they remain available during transitions and undo, when the plugin reports `idle`.

### Queue File Monitoring

On each poll cycle (or via filesystem watcher), read `~/.omnifocus-timer-widget/queue.json`. Diff against the in-memory queue to detect additions/removals and trigger dot animations.

### Button Actions

Each action runs osascript asynchronously (fire-and-forget, next poll picks up state change):

- **Play:** `timerLib.startTimerOnTask(taskId)`
- **Pause:** `timerLib.pauseTimer()`
- **Resume:** `timerLib.resumeTimer()`
- **Done:** `timerLib.stopTimer()` then mark task complete via `Task.byIdentifier(taskId).markComplete()`
- **Undo:** `Task.byIdentifier(taskId).markIncomplete()` then show task in Paused state

**Note:** The JS string must be properly escaped for AppleScript embedding. Use temp files or `NSAppleScript` to avoid shell quoting issues with task IDs.

### Navigate to Task

```swift
NSWorkspace.shared.open(URL(string: "omnifocus:///task/\(taskId)")!)
```

---

## Architecture

**SwiftUI app** with AppKit window management.

```
TimerWidget/
  TimerWidgetApp.swift      — App entry point, NSWindow setup
  WidgetView.swift          — SwiftUI view with state-dependent rendering
  TimerState.swift          — ObservableObject: timer state, queue, animations
  OmniFocusBridge.swift     — osascript polling, timer commands, task completion
  QueueManager.swift        — File watching, queue diffing, Letta command interface
  ConfettiView.swift        — Confetti particle animation overlay
  Info.plist                — LSUIElement=true, bundle ID
```

**Build:** Xcode project or Swift Package. Target: macOS 13+.

**Launch at login:** macOS Login Items or launchd plist.

---

## Technical Notes

- The osascript call takes ~0.5-1s. With poll-then-wait at 2s, there's a ~1-3 second lag. Animations run independently.
- When OmniFocus is not running, osascript fails. Widget stays hidden or shows only Queued state.
- If the timer plugin is not installed, `PlugIn.find()` returns null. Same handling as OmniFocus-not-running.
- The `~/.omnifocus-timer-widget/` directory is created by the app on first launch.
- Confetti particles are rendered as a transparent overlay window that extends below the widget, allowing particles to fall through the space below.
- The toggle script (`toggle-timer.sh`) needs updating: when a timer is running, it should call both `stopTimer()` and `markComplete()` instead of just `stopTimer()`.
