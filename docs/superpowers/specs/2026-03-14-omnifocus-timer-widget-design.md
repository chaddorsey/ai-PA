# OmniFocus Timer Floating Widget — Design Spec

**Date:** 2026-03-14
**Status:** Draft
**Goal:** A small floating macOS widget that displays the active OmniFocus timer state, provides play/pause/stop controls, and serves as an ambient indicator of active work.

---

## Overview

A standalone Swift macOS app that renders a borderless floating window pinned to the upper-right corner of the screen, just below the menu bar. The widget shows the currently timed OmniFocus task with play/pause and stop controls. It polls the OmniFocus timer plugin for state and provides direct control via osascript.

## Success Criteria

1. Widget appears automatically when a timer is running or paused
2. Widget disappears (fades out) when the timer is stopped
3. User can play/pause/stop the timer directly from the widget
4. Clicking the task name brings OmniFocus to the front with the task selected
5. Widget is visible on all Spaces/desktops and stays above other windows
6. No Dock icon, no menu bar icon — the widget is the entire UI

## Non-Goals

- Server communication (Letta events are handled by the plugin independently)
- Timer creation (user starts timers via Caps Lock, keyboard shortcuts, or OmniFocus actions)
- Multiple timer support (only one timer can be active at a time)

---

## Visual States

### Running (Green)

- **Background:** Green (`#34C759` or system green)
- **Text:** Black
- **Animation:** Subtle 1-second pulse cycle — opacity oscillates between 0.92 and 1.0, with a soft outer glow that waxes and wanes in sync. Barely noticeable; conveys "alive" without being distracting.
- **Buttons:** Pause (⏸) and Stop (⏹) visible, stacked vertically on the left

### Paused (Gray)

- **Background:** Gray (`#8E8E93` or system gray)
- **Text:** Black
- **Animation:** None (completely static)
- **Buttons:** Play (▶) and Stop (⏹) visible, stacked vertically on the left

### Stopped (Red → Fade Out)

- **Background:** Red (`#FF3B30` or system red)
- **Text:** Black
- **Animation:** 30-second fade-out. Opacity decreases from 1.0 to 0.0 using an ease-in-ease-out curve. Once fully faded, the widget hides and transitions to Idle.
- **Buttons:** Play (▶) visible (allows restarting the same task)

**Fade-out hover behavior:**
- Mouse enters the widget: immediately snap to opacity 1.0
- Mouse leaves before 5 seconds of hover: resume the fade from the point it was at when interrupted, continue fading out
- Mouse stays for 5+ seconds: reset the 30-second fade timer entirely. Fade restarts from the beginning after the mouse leaves.

### Idle (Hidden)

- Widget is not visible
- Polling continues in the background to detect when a new timer starts

---

## Layout

```
┌──────────────────────────────────────────┐
│ ⏸  Review quarterly report for the      │
│ ⏹  upcoming board meeting and ens…      │
└──────────────────────────────────────────┘
```

**Position:** Upper-right corner of the screen, pinned just below the menu bar. Right edge aligned approximately with the WiFi icon in the menu bar.

**Dimensions:**
- Width: ~280px
- Height: ~36px (single-line task name), ~48px (two-line task name)
- Corner radius: 8px
- Padding: 6px horizontal, 4px vertical

**Buttons:**
- Play/Pause (▶/⏸) and Stop (⏹) as SF Symbol icons, ~14pt
- Stacked vertically on the left side of the widget
- Subtle background highlight on hover (e.g., white at 15% opacity rounded rect) to telegraph clickability

**Task Name:**
- Left-aligned to an invisible vertical border right of the buttons
- System font, 11pt, bold
- Up to 2 lines, wrapping at word boundaries
- After ~50 characters across two lines, truncate with ellipsis (…)
- When task name fits on one line, widget height is compact (~36px)

**Window Properties:**
- `NSWindow.Level.floating` — stays above all other windows
- `NSWindow.CollectionBehavior.canJoinAllSpaces` — visible on every Space/desktop
- `NSWindow.StyleMask.borderless` — no title bar, no chrome
- `LSUIElement = true` — no Dock icon
- Not shown in Mission Control
- When fully faded (opacity 0), ignores mouse events (clicks pass through to windows below)

---

## Interaction

**Click on task name area:**
Open OmniFocus and navigate to the task. Use the URL scheme: `omnifocus:///task/<taskId>`. This brings OmniFocus to the front and selects the task.

**Click Pause/Play button:**
- If running → call `timerLib.pauseTimer()` via osascript. Widget transitions to Paused state.
- If paused → call `timerLib.resumeTimer()` via osascript. Widget transitions to Running state.
- If stopped → call `timerLib.startTimerOnTask(lastTaskId)` via osascript. Widget transitions to Running state.

**Click Stop button:**
Call `timerLib.stopTimer()` via osascript. Widget transitions to Stopped state (red, begins 30-second fade).

**Button hover:**
Buttons show a subtle highlight (white at 15% opacity, small rounded rect behind the icon) when the mouse hovers over them.

---

## Data Flow

### Polling

Every 2 seconds, the app runs:

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

The app maps `status` to widget state:
- `"running"` → Running (green, pulsing)
- `"paused"` → Paused (gray, static)
- `"idle"` → check if we were previously running/paused: if so, transition to Stopped (red, fade). If we've been idle for a while, stay Hidden.

### Button Actions

Each button action runs osascript asynchronously (fire-and-forget, the next poll will pick up the state change):

```swift
func runOmniJS(_ js: String) {
    let script = "tell application \"OmniFocus\" to evaluate javascript \"\(js)\""
    // NSAppleScript or Process with osascript
}

// Pause
runOmniJS("PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib').pauseTimer()")

// Resume
runOmniJS("PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib').resumeTimer()")

// Stop
runOmniJS("PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib').stopTimer()")

// Restart (from stopped)
runOmniJS("PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib').startTimerOnTask('\(taskId)')")
```

### Navigate to Task

```swift
NSWorkspace.shared.open(URL(string: "omnifocus:///task/\(taskId)")!)
```

---

## Architecture

**Single-file SwiftUI app** (~200-250 lines). No external dependencies.

```
TimerWidget/
  TimerWidgetApp.swift    — App entry, window setup, polling, state management, UI
  Info.plist              — LSUIElement=true, bundle ID
```

Key components within the single file:
- `TimerWidgetApp` — SwiftUI App, creates the floating NSWindow
- `TimerState` — ObservableObject holding current state, task info, fade progress
- `WidgetView` — SwiftUI view with conditional rendering per state
- `OmniFocusBridge` — functions to poll status and send commands via osascript
- Animations handled via SwiftUI `.animation()` and `Timer.publish()`

**Build:** Standard Xcode project or `swift build` with Package.swift. Target: macOS 13+.

**Launch at login:** Either via macOS Login Items (System Settings → General → Login Items) or a launchd plist.

---

## Technical Notes

- The osascript call takes ~0.5-1s. With a 2-second poll interval, there's a ~1-3 second lag between timer state changes and widget updates. This is acceptable — the pulsing animation runs independently of the data refresh.
- When OmniFocus is not running, the osascript call will fail. The widget should handle this gracefully (show nothing / stay hidden).
- The widget should not prevent sleep or interfere with screen savers.
- The fade-out animation state (current opacity, hover timer) is local to the Swift app and independent of the OmniFocus timer state.
