# OmniFocus Task Timer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a start/stop/pause timer OmniFocus plugin that logs actual time to task notes, with CLI integration and Letta agent two-way communication.

**Architecture:** OmniFocus Automation plugin bundle (actions + library) persists state in Preferences and writes time logs to task notes. omnifocus-cli gets a `timer` command group via plugin-aware bridge routing. Host bridge service relays timer events to Letta agents.

**Tech Stack:** OmniFocus Automation JavaScript (plugin), Python/Click (CLI), Node.js (host bridge)

**Spec:** `docs/superpowers/specs/2026-03-14-omnifocus-task-timer-design.md`

---

## File Structure

### New Files (Phase 1 — Plugin)

| File | Responsibility |
|------|---------------|
| `omnifocus-timer/omnifocus-timer.omnifocusjs/manifest.json` | Plugin metadata, action and library declarations |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js` | Core timer logic: state management, note formatting, guardian, orphan recovery, all library functions |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/start-timer.js` | Action: Start/Switch Timer (Automation menu item) |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/pause-timer.js` | Action: Pause/Resume Timer |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/stop-timer.js` | Action: Stop Timer |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/check-timer.js` | Action: Check Timer Status |

### New Files (Phase 2 — CLI)

| File | Responsibility |
|------|---------------|
| `omnifocus-cli/src/omnifocus_cli/timer.py` | Click command group for `timer start/stop/pause/resume/status/history` |
| `omnifocus-cli/tests/test_timer.py` | Unit tests for timer CLI commands |

### Modified Files (Phase 2 — Bridge Routing)

| File | Change |
|------|--------|
| `omnifocus-cli/src/omnifocus_cli/bridge.py` | Add `plugin` and `library` parameters to `build_applescript()`, `_call_via_osascript()`, `_call_via_http()`, `call_omnifocus()` |
| `omnifocus-mcp-letta/host-bridge-service.js` | Accept `plugin`/`library` in `/execute` payload; generate plugin-aware osascript |

### Modified Files (Phase 3 — Letta Integration)

| File | Change |
|------|--------|
| `omnifocus-mcp-letta/host-bridge-service.js` | Add `POST /timer-event` endpoint that relays to Letta agent messages API |
| `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js` | Add outbound event emission via `URL.FetchRequest`, pending event queue, heartbeat logic |

### Installation

The plugin bundle directory `omnifocus-timer.omnifocusjs/` is developed in the repo under `omnifocus-timer/` and symlinked (or copied) to `~/Library/Application Support/OmniFocus/Plug-Ins/` for OmniFocus to load it.

---

## Chunk 1: Phase 1 — Core Timer Plugin

### Task 1: Plugin Scaffold and Manifest

**Files:**
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/manifest.json`

- [ ] **Step 1: Create the plugin directory structure**

```bash
mkdir -p omnifocus-timer/omnifocus-timer.omnifocusjs
```

- [ ] **Step 2: Write manifest.json**

```json
{
  "defaultLocale": "en",
  "identifier": "com.dorsey.omnifocus-timer",
  "author": "Chad Dorsey",
  "description": "Start/stop/pause timer for tracking actual time spent on tasks",
  "version": "1.0.0",
  "actions": [
    { "identifier": "start-timer" },
    { "identifier": "pause-timer" },
    { "identifier": "stop-timer" },
    { "identifier": "check-timer" }
  ],
  "libraries": [
    { "identifier": "timer-lib" }
  ]
}
```

- [ ] **Step 3: Commit**

```bash
git add omnifocus-timer/
git commit -m "feat(omnifocus-timer): scaffold plugin bundle with manifest"
```

---

### Task 2: Timer Library — Preferences State Management

**Files:**
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

This is the core of the plugin. We build it incrementally across Tasks 2–6. Start with the state layer.

- [ ] **Step 1: Write the library skeleton with Preferences read/write helpers**

```javascript
/*{
  "type": "library",
  "targets": ["omnifocus"],
  "identifier": "timer-lib",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Core timer logic for OmniFocus task timer"
}*/
(() => {
  const lib = new PlugIn.Library(new Version("1.0.0"));

  // --- Preferences helpers ---
  let _prefs = null;
  function prefs() {
    if (!_prefs) _prefs = new Preferences(null);
    return _prefs;
  }

  function readState() {
    const state = prefs().readString("state") || "idle";
    const sessionsJson = prefs().readString("sessions") || "[]";
    const pendingJson = prefs().readString("pendingEvents") || "[]";
    return {
      activeTaskId: prefs().readString("activeTaskId"),
      activeTaskName: prefs().readString("activeTaskName"),
      activeProjectName: prefs().readString("activeProjectName"),
      state: state,
      currentIntervalStart: prefs().readNumber("currentIntervalStart") || 0,
      accumulatedMs: prefs().readNumber("accumulatedMs") || 0,
      originalEstimate: prefs().readNumber("originalEstimate"),
      sessions: JSON.parse(sessionsJson),
      pendingEvents: JSON.parse(pendingJson),
    };
  }

  function writeState(s) {
    prefs().write("activeTaskId", s.activeTaskId || null);
    prefs().write("activeTaskName", s.activeTaskName || null);
    prefs().write("activeProjectName", s.activeProjectName || null);
    prefs().write("state", s.state);
    prefs().write("currentIntervalStart", s.currentIntervalStart || null);
    prefs().write("accumulatedMs", s.accumulatedMs || null);
    prefs().write("originalEstimate", s.originalEstimate || null);
    prefs().write("sessions", JSON.stringify(s.sessions || []));
    prefs().write("pendingEvents", JSON.stringify(s.pendingEvents || []));
  }

  function clearState() {
    writeState({
      activeTaskId: null,
      activeTaskName: null,
      activeProjectName: null,
      state: "idle",
      currentIntervalStart: 0,
      accumulatedMs: 0,
      originalEstimate: null,
      sessions: [],
      pendingEvents: [],
    });
  }

  // --- Config ---
  const CONFIG = {
    relayEndpoint: "http://localhost:8889/timer-event",
    notificationIntervalMin: 15,
    guardianIntervalSec: 60,
    maxSessions: 100,
    maxPendingEvents: 50,
  };

  // Placeholder for guardian timer reference
  let guardianTimer = null;
  let lastNotificationTime = 0;
  let lastHeartbeatTime = 0;

  // --- Note formatting (Task 3) ---
  // --- Timer operations (Task 4) ---
  // --- Guardian (Task 5) ---
  // --- Library exports (Task 6) ---

  return lib;
})();
```

- [ ] **Step 2: Verify the plugin loads in OmniFocus**

```bash
# Symlink the plugin bundle into OmniFocus Plug-Ins
ln -sf /Volumes/main-drive/ai-PA/omnifocus-timer/omnifocus-timer.omnifocusjs \
  ~/Library/Application\ Support/OmniFocus/Plug-Ins/omnifocus-timer.omnifocusjs
```

Open OmniFocus → Automation menu → verify "com.dorsey.omnifocus-timer" appears in the plugin list (no errors in console).

- [ ] **Step 3: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): add timer library with Preferences state management"
```

---

### Task 3: Timer Library — Note Format Read/Write

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

Add functions that read and write the time tracking block in task notes.

- [ ] **Step 1: Add duration formatting helper**

Insert after the `CONFIG` block:

```javascript
  // --- Duration formatting ---
  function formatDuration(ms) {
    const totalMin = Math.round(ms / 60000);
    if (totalMin < 60) return totalMin + " min";
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    return h + "h " + (m < 10 ? "0" : "") + m + "m";
  }

  function formatTime(date) {
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    return hh + ":" + mm;
  }

  function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }
```

- [ ] **Step 2: Add note block read/write functions**

```javascript
  // --- Note block constants ---
  const NOTE_START = "--- Time Tracking ---";
  const NOTE_END = "--- End Time Tracking ---";

  function parseNoteBlock(noteText) {
    // Returns {exists, agentEstimate, originalEstimate, sessions, rawBlock, beforeBlock, afterBlock}
    const startIdx = noteText.indexOf(NOTE_START);
    const endIdx = noteText.indexOf(NOTE_END);
    if (startIdx === -1 || endIdx === -1) {
      return { exists: false, agentEstimate: null, originalEstimate: null, sessions: [], beforeBlock: noteText, afterBlock: "" };
    }
    const beforeBlock = noteText.substring(0, startIdx);
    const afterBlock = noteText.substring(endIdx + NOTE_END.length);
    const block = noteText.substring(startIdx + NOTE_START.length, endIdx);

    let agentEstimate = null;
    const agentMatch = block.match(/Agent Estimate: (\d+) min/);
    if (agentMatch) agentEstimate = parseInt(agentMatch[1], 10);

    let originalEstimate = null;
    const origMatch = block.match(/Original Estimate: (?:(\d+) min|none)/);
    if (origMatch && origMatch[1]) originalEstimate = parseInt(origMatch[1], 10);

    const sessions = [];
    // Same-day sessions
    const sameDayRe = /\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})–(\d{2}:\d{2})\] (.+)/g;
    let m;
    while ((m = sameDayRe.exec(block)) !== null) {
      sessions.push({ date: m[1], start: m[2], end: m[3], duration: m[4] });
    }
    // Cross-midnight sessions
    const crossRe = /\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})–(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\] (.+)/g;
    while ((m = crossRe.exec(block)) !== null) {
      sessions.push({ startDate: m[1], start: m[2], endDate: m[3], end: m[4], duration: m[5] });
    }

    return { exists: true, agentEstimate, originalEstimate, sessions, beforeBlock, afterBlock };
  }

  function buildNoteBlock(agentEstimate, originalEstimate, sessionLines, totalMs, inProgressLine) {
    let lines = [NOTE_START];
    if (agentEstimate !== null) lines.push("Agent Estimate: " + agentEstimate + " min");
    if (originalEstimate !== null) {
      lines.push("Original Estimate: " + originalEstimate + " min");
    } else {
      lines.push("Original Estimate: none");
    }
    lines = lines.concat(sessionLines);
    if (inProgressLine) lines.push(inProgressLine);
    lines.push("Total: " + formatDuration(totalMs));
    if (originalEstimate !== null && originalEstimate > 0) {
      const diffMs = totalMs - (originalEstimate * 60000);
      const diffMin = Math.round(diffMs / 60000);
      const pct = Math.round((diffMs / (originalEstimate * 60000)) * 100);
      const sign = diffMin >= 0 ? "+" : "";
      lines.push("Variance: " + sign + diffMin + " min (" + sign + pct + "%)");
    }
    lines.push(NOTE_END);
    return lines.join("\n");
  }

  function computeTotalMs(sessions, currentAccumulated) {
    let total = 0;
    for (const s of sessions) total += s.durationMs;
    total += (currentAccumulated || 0);
    return total;
  }

  function writeNoteBlock(task, state, inProgressMs) {
    const noteText = task.note || "";
    const parsed = parseNoteBlock(noteText);

    // Build session lines from finalized sessions in state
    const sessionLines = [];
    for (const s of state.sessions) {
      const startDate = new Date(s.start);
      const endDate = new Date(s.end);
      const sameDay = formatDate(startDate) === formatDate(endDate);
      if (sameDay) {
        sessionLines.push("[" + formatDate(startDate) + " " + formatTime(startDate) + "–" + formatTime(endDate) + "] " + formatDuration(s.durationMs));
      } else {
        sessionLines.push("[" + formatDate(startDate) + " " + formatTime(startDate) + "–" + formatDate(endDate) + " " + formatTime(endDate) + "] " + formatDuration(s.durationMs));
      }
    }

    // In-progress line
    let ipLine = null;
    if (inProgressMs !== null && inProgressMs !== undefined && state.state !== "idle") {
      const now = new Date();
      const sessionStart = new Date(state.currentIntervalStart - (state.accumulatedMs - (inProgressMs - (state.accumulatedMs))));
      // Simpler: use stored interval start for display
      const displayStart = new Date(state.currentIntervalStart - state.accumulatedMs + (state.sessions.length > 0 ? 0 : 0));
      ipLine = "[" + formatDate(now) + " " + formatTime(new Date(state.currentIntervalStart)) + " in progress] ~" + formatDuration(inProgressMs);
    }

    const totalMs = computeTotalMs(state.sessions, inProgressMs || 0);
    const agentEst = parsed.exists ? parsed.agentEstimate : null;
    const origEst = state.originalEstimate;
    const block = buildNoteBlock(agentEst, origEst, sessionLines, totalMs, ipLine);

    // Reconstruct note
    if (parsed.exists) {
      task.note = parsed.beforeBlock + block + parsed.afterBlock;
    } else {
      const separator = noteText.length > 0 ? "\n\n" : "";
      task.note = noteText + separator + block;
    }
  }
```

- [ ] **Step 3: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): add note format read/write with three-way estimate support"
```

---

### Task 4: Timer Library — Core Timer Operations

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

Add the start, stop, pause, resume, and status functions.

- [ ] **Step 1: Add startTimerOnTask function**

Insert after the note formatting functions:

```javascript
  // --- Timer operations ---

  function getElapsedMs(state) {
    if (state.state === "running") {
      return state.accumulatedMs + (Date.now() - state.currentIntervalStart);
    }
    return state.accumulatedMs;
  }

  function stopCurrentTimer(state) {
    // Finalize the current session and write to note
    if (state.state === "idle") return state;
    const elapsed = getElapsedMs(state);
    if (elapsed > 0) {
      const sessionStart = state.currentIntervalStart - state.accumulatedMs;
      state.sessions.push({
        start: sessionStart,
        end: Date.now(),
        durationMs: elapsed,
      });
      // Enforce session cap
      if (state.sessions.length > CONFIG.maxSessions) {
        state.sessions = state.sessions.slice(-CONFIG.maxSessions);
      }
    }
    // Write finalized note
    const task = Task.byIdentifier(state.activeTaskId);
    if (task) {
      writeNoteBlock(task, state, null);
    }
    const result = {
      previousTaskId: state.activeTaskId,
      previousTaskName: state.activeTaskName,
      finalSessionMs: elapsed,
      totalMs: computeTotalMs(state.sessions, 0),
    };
    // Reset accumulation for next timer
    state.state = "idle";
    state.accumulatedMs = 0;
    state.currentIntervalStart = 0;
    return result;
  }

  function startTimerOnTask(taskOrId) {
    const task = (typeof taskOrId === "string") ? Task.byIdentifier(taskOrId) : taskOrId;
    if (!task) return { status: "error", message: "Task not found" };

    let state = readState();
    let switchResult = null;

    // If already timing this task
    if (state.state !== "idle" && state.activeTaskId === task.id.primaryKey) {
      return { status: "already_timing", taskName: task.name };
    }

    // If timing a different task, stop it first
    if (state.state !== "idle") {
      switchResult = stopCurrentTimer(state);
      // Cancel existing guardian
      if (guardianTimer) { guardianTimer.cancel(); guardianTimer = null; }
    }

    // Read existing note block to check for agent estimate and prior sessions
    const parsed = parseNoteBlock(task.note || "");

    // Snapshot original estimate on first-ever timing
    let origEst = null;
    if (parsed.exists && parsed.originalEstimate !== null) {
      origEst = parsed.originalEstimate;
    } else {
      origEst = task.estimatedMinutes || null;
    }

    const projectName = task.containingProject ? task.containingProject.name : null;

    state = {
      activeTaskId: task.id.primaryKey,
      activeTaskName: task.name,
      activeProjectName: projectName,
      state: "running",
      currentIntervalStart: Date.now(),
      accumulatedMs: 0,
      originalEstimate: origEst,
      sessions: parsed.exists ? [] : [], // Fresh sessions for this timing engagement
      pendingEvents: state.pendingEvents || [],
    };

    writeState(state);
    startGuardian();

    const result = {
      status: switchResult ? "switched" : "started",
      taskId: task.id.primaryKey,
      taskName: task.name,
      projectName: projectName,
      originalEstimateMin: origEst,
    };
    if (switchResult) {
      result.previousTaskId = switchResult.previousTaskId;
      result.previousTaskName = switchResult.previousTaskName;
      result.previousSessionMs = switchResult.finalSessionMs;
    }
    return result;
  }

  function stopTimer() {
    const state = readState();
    if (state.state === "idle") return { status: "idle", message: "No timer running" };

    const result = stopCurrentTimer(state);
    if (guardianTimer) { guardianTimer.cancel(); guardianTimer = null; }
    clearState();

    return {
      status: "stopped",
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      finalSessionMs: result.finalSessionMs,
      totalMs: result.totalMs,
      originalEstimateMin: state.originalEstimate,
    };
  }

  function pauseTimer() {
    const state = readState();
    if (state.state !== "running") return { status: "error", message: "Timer not running" };

    state.accumulatedMs = getElapsedMs(state);
    state.state = "paused";
    state.currentIntervalStart = 0;
    writeState(state);

    // Write in-progress note immediately on pause
    const task = Task.byIdentifier(state.activeTaskId);
    if (task) writeNoteBlock(task, state, state.accumulatedMs);

    return {
      status: "paused",
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      elapsedMs: state.accumulatedMs,
    };
  }

  function resumeTimer() {
    const state = readState();
    if (state.state !== "paused") return { status: "error", message: "Timer not paused" };

    state.state = "running";
    state.currentIntervalStart = Date.now();
    writeState(state);

    return { status: "resumed", taskId: state.activeTaskId, taskName: state.activeTaskName };
  }

  function getTimerStatus() {
    const state = readState();
    if (state.state === "idle") return { state: "idle" };
    const elapsed = getElapsedMs(state);
    const totalMs = computeTotalMs(state.sessions, elapsed);
    return {
      state: state.state,
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      projectName: state.activeProjectName,
      currentSessionMs: elapsed,
      totalMs: totalMs,
      sessionCount: state.sessions.length + 1,
      originalEstimateMin: state.originalEstimate,
    };
  }

  function getTimerHistory(taskId) {
    const task = Task.byIdentifier(taskId);
    if (!task) return { status: "error", message: "Task not found" };
    const parsed = parseNoteBlock(task.note || "");
    if (!parsed.exists) return { status: "ok", sessions: [], totalMs: 0, agentEstimateMin: null, originalEstimateMin: null, variance: null };

    // Parse duration strings to ms for structured output
    let totalMs = 0;
    const sessions = parsed.sessions.map(s => {
      // Parse "Xh YYm" or "N min" back to ms
      const dur = parseDurationToMs(s.duration);
      totalMs += dur;
      return { ...s, durationMs: dur };
    });

    let variance = null;
    if (parsed.originalEstimate !== null && parsed.originalEstimate > 0) {
      const diffMs = totalMs - (parsed.originalEstimate * 60000);
      variance = { diffMin: Math.round(diffMs / 60000), pct: Math.round((diffMs / (parsed.originalEstimate * 60000)) * 100) };
    }

    return {
      status: "ok",
      sessions: sessions,
      totalMs: totalMs,
      agentEstimateMin: parsed.agentEstimate,
      originalEstimateMin: parsed.originalEstimate,
      variance: variance,
    };
  }

  function parseDurationToMs(durStr) {
    // "32 min" or "1h 06m"
    const hm = durStr.match(/(\d+)h\s*(\d+)m/);
    if (hm) return (parseInt(hm[1]) * 60 + parseInt(hm[2])) * 60000;
    const minMatch = durStr.match(/(\d+)\s*min/);
    if (minMatch) return parseInt(minMatch[1]) * 60000;
    return 0;
  }
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): add core timer operations (start, stop, pause, resume, status, history)"
```

---

### Task 5: Timer Library — Guardian Timer and Orphan Recovery

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

- [ ] **Step 1: Add guardian timer implementation**

```javascript
  // --- Guardian Timer ---

  function startGuardian() {
    if (guardianTimer) { guardianTimer.cancel(); guardianTimer = null; }
    lastNotificationTime = Date.now();
    lastHeartbeatTime = Date.now();

    guardianTimer = Timer.repeating(CONFIG.guardianIntervalSec, function(timer) {
      try {
        const state = readState();
        if (state.state === "idle") {
          timer.cancel();
          guardianTimer = null;
          return;
        }

        // 1. Persist to note
        const task = Task.byIdentifier(state.activeTaskId);
        if (!task) {
          // Task deleted — auto-stop
          console.log("Guardian: task not found, auto-stopping timer");
          clearState();
          timer.cancel();
          guardianTimer = null;
          return;
        }

        // 2. Check task completion
        if (task.completed || task.taskStatus === Task.Status.Completed ||
            task.taskStatus === Task.Status.Dropped) {
          console.log("Guardian: task completed/dropped, auto-stopping");
          stopCurrentTimer(state);
          clearState();
          timer.cancel();
          guardianTimer = null;
          return;
        }

        // 3. Write in-progress note
        if (state.state === "running") {
          const elapsed = getElapsedMs(state);
          writeNoteBlock(task, state, elapsed);
        } else if (state.state === "paused") {
          writeNoteBlock(task, state, state.accumulatedMs);
        }

        // 4. Notification cadence
        const now = Date.now();
        const notifIntervalMs = CONFIG.notificationIntervalMin * 60000;
        if (now - lastNotificationTime >= notifIntervalMs) {
          lastNotificationTime = now;
          const elapsed = getElapsedMs(state);
          try {
            const notif = new Notification("Timer: " + formatDuration(elapsed) + " on '" + state.activeTaskName + "'");
            notif.subtitle = state.state === "paused" ? "Paused" : "Running";
            notif.show();
          } catch (e) {
            console.log("Guardian: notification failed: " + e.message);
          }
        }
      } catch (e) {
        console.log("Guardian tick error: " + e.message);
      }
    });
  }

  // --- Orphan Recovery ---
  function checkOrphanedTimer() {
    const state = readState();
    if (state.state === "idle") return;

    const gapMs = Date.now() - (state.currentIntervalStart || Date.now());

    if (state.state === "running" && gapMs > CONFIG.guardianIntervalSec * 2000) {
      // OmniFocus was closed with a running timer
      const gapMin = Math.round(gapMs / 60000);
      const alert = new Alert(
        "Timer Recovery",
        "Timer was running on '" + state.activeTaskName + "' when OmniFocus quit. Approximately " + gapMin + " min untracked."
      );
      alert.addOption("Resume (exclude gap)");
      alert.addOption("Stop and log");
      alert.addOption("Resume (include gap)");
      alert.show().then(function(idx) {
        if (idx === 0) {
          // Resume excluding gap — reset interval start to now
          state.currentIntervalStart = Date.now();
          writeState(state);
          startGuardian();
        } else if (idx === 1) {
          // Stop and log what we have
          stopCurrentTimer(state);
          clearState();
        } else if (idx === 2) {
          // Resume including gap — keep original start time, accumulate gap
          state.accumulatedMs = getElapsedMs(state);
          state.currentIntervalStart = Date.now();
          writeState(state);
          startGuardian();
        }
      });
    } else if (state.state === "paused" || gapMs <= CONFIG.guardianIntervalSec * 2000) {
      // Small gap or paused — silently resume guardian
      startGuardian();
    }
  }

  // Run orphan check on library load
  checkOrphanedTimer();
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): add guardian timer with note persistence and orphan recovery"
```

---

### Task 6: Timer Library — Export Library Functions

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

Expose functions for external callers (omnifocus-cli, other plugins).

- [ ] **Step 1: Add library exports before `return lib;`**

```javascript
  // --- Library exports ---
  lib.startTimer = startTimerOnTask;
  lib.stopTimer = stopTimer;
  lib.pauseTimer = pauseTimer;
  lib.resumeTimer = resumeTimer;
  lib.getTimerStatus = getTimerStatus;
  lib.getTimerHistory = getTimerHistory;

  return lib;
})();
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): export library functions for external callers"
```

---

### Task 7: Start Timer Action

**Files:**
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/start-timer.js`

- [ ] **Step 1: Write the Start/Switch Timer action**

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "start-timer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Start or switch the task timer on the selected task",
  "label": "Start Timer",
  "shortLabel": "Start Timer",
  "image": "clock"
}*/
(() => {
  const action = new PlugIn.Action(async function(selection) {
    const task = selection.tasks[0];
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
    const result = timerLib.startTimer(task.id.primaryKey);

    if (result.status === "already_timing") {
      const alert = new Alert("Timer", "Already timing '" + result.taskName + "'.");
      alert.show();
    } else if (result.status === "switched") {
      const alert = new Alert("Timer Switched",
        "Stopped timer on '" + result.previousTaskName + "' (" + Math.round(result.previousSessionMs / 60000) + " min).\n\nStarted timer on '" + result.taskName + "'.");
      alert.show();
    } else if (result.status === "started") {
      const estNote = result.originalEstimateMin ? " (estimate: " + result.originalEstimateMin + " min)" : "";
      const alert = new Alert("Timer Started", "Timing '" + result.taskName + "'" + estNote + ".");
      alert.show();
    } else if (result.status === "error") {
      const alert = new Alert("Timer Error", result.message);
      alert.show();
    }
  });

  action.validate = function(selection) {
    return selection.tasks.length === 1;
  };

  return action;
})();
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/start-timer.js
git commit -m "feat(omnifocus-timer): add Start Timer action"
```

---

### Task 8: Pause, Stop, and Check Timer Actions

**Files:**
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/pause-timer.js`
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/stop-timer.js`
- Create: `omnifocus-timer/omnifocus-timer.omnifocusjs/check-timer.js`

- [ ] **Step 1: Write Pause/Resume Timer action**

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "pause-timer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Pause or resume the active task timer",
  "label": "Pause Timer",
  "shortLabel": "Pause Timer",
  "image": "pause"
}*/
(() => {
  const action = new PlugIn.Action(async function(selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
    const status = timerLib.getTimerStatus();

    let result;
    if (status.state === "running") {
      result = timerLib.pauseTimer();
      const alert = new Alert("Timer Paused",
        "Paused '" + result.taskName + "' at " + Math.round(result.elapsedMs / 60000) + " min.");
      alert.show();
    } else if (status.state === "paused") {
      result = timerLib.resumeTimer();
      const alert = new Alert("Timer Resumed", "Resumed '" + result.taskName + "'.");
      alert.show();
    }
  });

  action.validate = function(selection) {
    try {
      const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
      const status = timerLib.getTimerStatus();
      return status.state === "running" || status.state === "paused";
    } catch (e) {
      return false;
    }
  };

  return action;
})();
```

- [ ] **Step 2: Write Stop Timer action**

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "stop-timer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Stop the active task timer and log the session",
  "label": "Stop Timer",
  "shortLabel": "Stop Timer",
  "image": "stop"
}*/
(() => {
  const action = new PlugIn.Action(async function(selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
    const result = timerLib.stopTimer();

    if (result.status === "stopped") {
      const totalMin = Math.round(result.totalMs / 60000);
      const estNote = result.originalEstimateMin ? "\nEstimate was " + result.originalEstimateMin + " min." : "";
      const alert = new Alert("Timer Stopped",
        "Logged " + Math.round(result.finalSessionMs / 60000) + " min on '" + result.taskName + "'.\nTotal: " + totalMin + " min." + estNote);
      alert.show();
    } else {
      const alert = new Alert("Timer", result.message || "No timer running.");
      alert.show();
    }
  });

  action.validate = function(selection) {
    try {
      const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
      const status = timerLib.getTimerStatus();
      return status.state !== "idle";
    } catch (e) {
      return false;
    }
  };

  return action;
})();
```

- [ ] **Step 3: Write Check Timer action**

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "check-timer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Show current timer status",
  "label": "Check Timer",
  "shortLabel": "Check Timer",
  "image": "info"
}*/
(() => {
  const action = new PlugIn.Action(async function(selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timer-lib");
    const status = timerLib.getTimerStatus();

    if (status.state === "idle") {
      const alert = new Alert("Timer Status", "No timer active.");
      alert.show();
      return;
    }

    const currentMin = Math.round(status.currentSessionMs / 60000);
    const totalMin = Math.round(status.totalMs / 60000);
    const stateLabel = status.state === "paused" ? "PAUSED" : "RUNNING";
    const estNote = status.originalEstimateMin ? "\nEstimate: " + status.originalEstimateMin + " min" : "";

    const alert = new Alert("Timer Status — " + stateLabel,
      "Task: " + status.taskName +
      (status.projectName ? "\nProject: " + status.projectName : "") +
      "\nCurrent session: " + currentMin + " min" +
      "\nTotal: " + totalMin + " min" +
      "\nSessions: " + status.sessionCount +
      estNote);
    alert.show();
  });

  action.validate = function(selection) {
    return true;
  };

  return action;
})();
```

- [ ] **Step 4: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/pause-timer.js \
        omnifocus-timer/omnifocus-timer.omnifocusjs/stop-timer.js \
        omnifocus-timer/omnifocus-timer.omnifocusjs/check-timer.js
git commit -m "feat(omnifocus-timer): add Pause, Stop, and Check Timer actions"
```

---

### Task 9: Manual Integration Test in OmniFocus

**Files:** None (manual testing)

- [ ] **Step 1: Reload plugin in OmniFocus**

Close and reopen OmniFocus (or use Automation → Reload Plug-Ins if available). Verify all four actions appear in the Automation menu.

- [ ] **Step 2: Test basic timer flow**

1. Select a task with an estimated duration set
2. Run "Start Timer" from Automation menu → verify alert shows "Timer Started"
3. Wait ~70 seconds → verify the task's note has `--- Time Tracking ---` block with `[in progress]` line
4. Run "Check Timer" → verify alert shows running status with correct elapsed time
5. Run "Pause Timer" → verify alert shows "Paused"
6. Run "Pause Timer" again → verify it resumes (alert shows "Resumed")
7. Run "Stop Timer" → verify alert shows final time, note has finalized session line

- [ ] **Step 3: Test switch behavior**

1. Start timer on Task A
2. Select Task B and run "Start Timer" → verify alert shows "Timer Switched", Task A's note has a finalized session
3. Stop timer on Task B

- [ ] **Step 4: Test orphan recovery**

1. Start timer on a task
2. Quit OmniFocus
3. Reopen OmniFocus → verify recovery alert appears with three options
4. Choose "Stop and log" → verify the note has the session

- [ ] **Step 5: Commit any fixes discovered during testing**

```bash
git add -A omnifocus-timer/
git commit -m "fix(omnifocus-timer): fixes from manual integration testing"
```

---

## Chunk 2: Phase 2 — CLI Integration

### Task 10: Plugin-Aware Bridge Routing — bridge.py

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/bridge.py:16-29` (build_applescript and related functions)

- [ ] **Step 1: Add plugin/library parameters to all bridge functions**

Replace the entire `bridge.py` with plugin-aware routing:

```python
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BRIDGE_URL = "http://host.docker.internal:8889"

# Default plugin (existing MCP bridge)
DEFAULT_PLUGIN_ID = "omnifocus-mcp"
DEFAULT_LIBRARY_ID = "omnifocus-mcp"


def build_payload(method: str, params: dict | None = None) -> str:
    """Build the JSON payload for the OmniFocus plugin."""
    return json.dumps({"method": method, "params": params or {}})


def build_applescript(
    method: str,
    params: dict | None = None,
    *,
    plugin: str = DEFAULT_PLUGIN_ID,
    library: str = DEFAULT_LIBRARY_ID,
) -> str:
    """Build the AppleScript that calls an OmniFocus plugin via base64-encoded JSON.

    For the default MCP plugin, routes through lib.request(payload).
    For other plugins, calls lib.<method>(params) directly.
    """
    if plugin == DEFAULT_PLUGIN_ID:
        # Legacy path: MCP plugin uses request() dispatcher
        payload = build_payload(method, params)
        b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        js_call = f"JSON.stringify(lib.request(r))"
        decode_and_call = (
            f"var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='{b64}',r='';"
            f"for(var i=0;i<s.length;){{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);"
            f"r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));"
            f"if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}"
            f"var p=PlugIn.find('{plugin}');if(!p)throw new Error('Plugin not found');"
            f"var lib=p.library('{library}');{js_call}"
        )
    else:
        # Direct library call path: call lib.<method>(params)
        params_json = json.dumps(params or {})
        b64_params = base64.b64encode(params_json.encode("utf-8")).decode("ascii")
        decode_params = (
            f"var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='{b64_params}',r='';"
            f"for(var i=0;i<s.length;){{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);"
            f"r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));"
            f"if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}"
        )
        decode_and_call = (
            f"{decode_params}"
            f"var p=PlugIn.find('{plugin}');if(!p)throw new Error('Plugin not found');"
            f"var lib=p.library('{library}');"
            f"var params=JSON.parse(r);"
            f"var firstParam=Object.values(params)[0];"
            f"JSON.stringify(lib.{method}(Object.keys(params).length===0?undefined:"
            f"Object.keys(params).length===1?firstParam:params))"
        )

    return f"""tell application "OmniFocus"
  set _res to evaluate javascript "{decode_and_call}"
end tell
return _res
"""


def _call_via_osascript(
    method: str, params: dict | None = None, *, plugin: str = DEFAULT_PLUGIN_ID, library: str = DEFAULT_LIBRARY_ID
) -> dict:
    """Call OmniFocus via osascript and return parsed JSON result."""
    script = build_applescript(method, params, plugin=plugin, library=library)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        script_path = Path(f.name)
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(script_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"osascript failed (exit {result.returncode}): {result.stderr.strip()}")
        raw = result.stdout.strip()
        parsed = json.loads(raw)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict) and "error" in parsed:
            raise RuntimeError(f"OmniFocus plugin error: {parsed['error']}")
        if isinstance(parsed, dict):
            return parsed.get("result", parsed)
        return parsed
    finally:
        script_path.unlink(missing_ok=True)


def _call_via_http(
    method: str, params: dict | None = None, *, plugin: str = DEFAULT_PLUGIN_ID, library: str = DEFAULT_LIBRARY_ID
) -> dict:
    """Call OmniFocus via HTTP bridge and return parsed JSON result."""
    bridge_url = os.environ.get("OMNIFOCUS_BRIDGE_URL", DEFAULT_BRIDGE_URL)
    url = f"{bridge_url}/execute"
    payload = {"command": method, "args": params or {}}
    if plugin != DEFAULT_PLUGIN_ID:
        payload["plugin"] = plugin
        payload["library"] = library
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP bridge request failed: {exc}") from exc

    parsed = json.loads(raw)
    if isinstance(parsed, dict) and "error" in parsed:
        raise RuntimeError(f"OmniFocus bridge error: {parsed['error']}")
    result = parsed.get("result", parsed)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            pass
    return result


def call_omnifocus(
    method: str, params: dict | None = None, *, plugin: str = DEFAULT_PLUGIN_ID, library: str = DEFAULT_LIBRARY_ID
) -> dict:
    """Call OmniFocus via osascript (local) or HTTP bridge (Docker)."""
    if shutil.which("osascript"):
        return _call_via_osascript(method, params, plugin=plugin, library=library)
    return _call_via_http(method, params, plugin=plugin, library=library)
```

- [ ] **Step 2: Verify existing CLI commands still work**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli
poetry run omnifocus-cli task list --format json | head -20
```

Expected: existing task list output, unchanged behavior.

- [ ] **Step 3: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/bridge.py
git commit -m "feat(omnifocus-cli): add plugin-aware routing to bridge layer"
```

---

### Task 11: Plugin-Aware Bridge Routing — host-bridge-service.js

**Files:**
- Modify: `omnifocus-mcp-letta/host-bridge-service.js:31-65`

- [ ] **Step 1: Update the /execute handler to support plugin parameter**

Replace the request handler (lines 31–95) to check for `plugin`/`library` in the payload:

```javascript
  if (req.method !== 'POST') {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
    return;
  }

  let body = '';
  req.on('data', chunk => {
    body += chunk.toString();
  });

  req.on('end', () => {
    if (req.url === '/execute') {
      handleExecute(body, res);
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  });
```

Extract the execute logic into a function that handles plugin routing:

```javascript
function handleExecute(body, res) {
  try {
    const parsed = JSON.parse(body);
    const { command, args } = parsed;
    const pluginId = parsed.plugin || 'omnifocus-mcp';
    const libraryId = parsed.library || 'omnifocus-mcp';

    let jsCall;
    if (pluginId === 'omnifocus-mcp') {
      // Legacy path: base64 → lib.request(decoded)
      const payload = JSON.stringify({ method: command, params: args || {} });
      const b64 = Buffer.from(payload).toString('base64');
      jsCall = `var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='${b64}',r='';for(var i=0;i<s.length;){var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}var p=PlugIn.find('${pluginId}');if(!p)throw new Error('Plugin not found');var lib=p.library('${libraryId}');JSON.stringify(lib.request(r))`;
    } else {
      // Direct library call: base64 → lib.<method>(params)
      const paramsJson = JSON.stringify(args || {});
      const b64 = Buffer.from(paramsJson).toString('base64');
      jsCall = `var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='${b64}',r='';for(var i=0;i<s.length;){var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}var p=PlugIn.find('${pluginId}');if(!p)throw new Error('Plugin not found');var lib=p.library('${libraryId}');var params=JSON.parse(r);var firstParam=Object.values(params)[0];JSON.stringify(lib.${command}(Object.keys(params).length===0?undefined:Object.keys(params).length===1?firstParam:params))`;
    }

    const script = `
tell application "OmniFocus"
  set _res to evaluate javascript "${jsCall}"
end tell
return _res
`;
    const tmpApple = path.join(os.tmpdir(), `omnifocus-${Date.now()}-${Math.random().toString(36).substr(2, 9)}.applescript`);
    fs.writeFileSync(tmpApple, script, 'utf8');

    try {
      const raw = execSync(`/usr/bin/osascript "${tmpApple}"`, { encoding: 'utf8' });
      const result = JSON.parse(raw);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: true, result }));
    } catch (err) {
      console.error('OmniFocus call failed:', err.message);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: false, error: 'Bridge call failed', details: err.message }));
    } finally {
      try { fs.unlinkSync(tmpApple); } catch (e) {}
    }
  } catch (err) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid request', details: err.message }));
  }
}
```

- [ ] **Step 2: Restart the host bridge service**

```bash
launchctl stop com.omnifocus.bridge
launchctl start com.omnifocus.bridge
```

- [ ] **Step 3: Verify existing MCP commands still work**

```bash
curl -s -X POST http://localhost:8889/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "listRemaining", "args": {}}' | python3 -m json.tool | head -10
```

Expected: task list output, same as before.

- [ ] **Step 4: Test timer plugin routing through bridge**

```bash
curl -s -X POST http://localhost:8889/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "getTimerStatus", "args": {}, "plugin": "com.dorsey.omnifocus-timer", "library": "timer-lib"}' | python3 -m json.tool
```

Expected: `{"state": "idle"}` (or current timer state).

- [ ] **Step 5: Commit**

```bash
git add omnifocus-mcp-letta/host-bridge-service.js
git commit -m "feat(host-bridge): add plugin-aware routing for timer and future plugins"
```

---

### Task 12: Timer CLI Command Group

**Files:**
- Create: `omnifocus-cli/src/omnifocus_cli/timer.py`
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py` (register timer group)

- [ ] **Step 1: Write the timer command group**

```python
"""Timer commands for OmniFocus task time tracking."""
from __future__ import annotations

import json

import click

from omnifocus_cli.bridge import call_omnifocus
from omnifocus_cli.formatters import output_result, should_use_json

TIMER_PLUGIN = "com.dorsey.omnifocus-timer"
TIMER_LIBRARY = "timer-lib"


def _timer_call(method: str, params: dict | None = None) -> dict:
    return call_omnifocus(method, params, plugin=TIMER_PLUGIN, library=TIMER_LIBRARY)


@click.group()
def timer():
    """Task timer — track actual time spent on OmniFocus tasks."""
    pass


@timer.command()
@click.argument("task_id")
@click.pass_context
def start(ctx, task_id):
    """Start timer on a task. Auto-stops any running timer."""
    result = _timer_call("startTimer", {"taskId": task_id})
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)


@timer.command()
@click.pass_context
def stop(ctx):
    """Stop the active timer and log the session."""
    result = _timer_call("stopTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)


@timer.command()
@click.pass_context
def pause(ctx):
    """Pause the active timer."""
    result = _timer_call("pauseTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)


@timer.command()
@click.pass_context
def resume(ctx):
    """Resume the paused timer."""
    result = _timer_call("resumeTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)


@timer.command()
@click.pass_context
def status(ctx):
    """Show current timer state."""
    result = _timer_call("getTimerStatus")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)


@timer.command()
@click.argument("task_id")
@click.pass_context
def history(ctx, task_id):
    """Show time tracking history for a task."""
    result = _timer_call("getTimerHistory", {"taskId": task_id})
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, use_json)
```

- [ ] **Step 2: Register timer group in cli.py**

Add at the end of `omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
from omnifocus_cli.timer import timer
cli.add_command(timer)
```

- [ ] **Step 3: Verify CLI commands work**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli
poetry run omnifocus-cli timer status --format json
```

Expected: `{"state": "idle"}` or current timer state.

- [ ] **Step 4: Test full CLI timer flow**

```bash
# Get a task ID first
TASK_ID=$(poetry run omnifocus-cli task list --format json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Start timer
poetry run omnifocus-cli timer start "$TASK_ID" --format json

# Check status
poetry run omnifocus-cli timer status --format json

# Pause
poetry run omnifocus-cli timer pause --format json

# Resume
poetry run omnifocus-cli timer resume --format json

# Stop
poetry run omnifocus-cli timer stop --format json

# Check history
poetry run omnifocus-cli timer history "$TASK_ID" --format json
```

- [ ] **Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/timer.py omnifocus-cli/src/omnifocus_cli/cli.py
git commit -m "feat(omnifocus-cli): add timer command group (start, stop, pause, resume, status, history)"
```

---

### Task 13: Timer CLI Unit Tests

**Files:**
- Create: `omnifocus-cli/tests/test_timer.py`

- [ ] **Step 1: Write unit tests with mocked bridge calls**

```python
"""Tests for timer CLI commands."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from omnifocus_cli.cli import cli


@patch("omnifocus_cli.timer._timer_call")
def test_timer_status_idle(mock_call):
    mock_call.return_value = {"state": "idle"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "status"])
    assert result.exit_code == 0
    assert '"state": "idle"' in result.output
    mock_call.assert_called_once_with("getTimerStatus")


@patch("omnifocus_cli.timer._timer_call")
def test_timer_start(mock_call):
    mock_call.return_value = {"status": "started", "taskId": "abc", "taskName": "Test"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "start", "abc"])
    assert result.exit_code == 0
    assert '"status": "started"' in result.output
    mock_call.assert_called_once_with("startTimer", {"taskId": "abc"})


@patch("omnifocus_cli.timer._timer_call")
def test_timer_stop(mock_call):
    mock_call.return_value = {"status": "stopped", "totalMs": 120000}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "stop"])
    assert result.exit_code == 0
    assert '"status": "stopped"' in result.output


@patch("omnifocus_cli.timer._timer_call")
def test_timer_pause(mock_call):
    mock_call.return_value = {"status": "paused", "elapsedMs": 60000}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "pause"])
    assert result.exit_code == 0
    assert '"status": "paused"' in result.output


@patch("omnifocus_cli.timer._timer_call")
def test_timer_resume(mock_call):
    mock_call.return_value = {"status": "resumed"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "resume"])
    assert result.exit_code == 0
    assert '"status": "resumed"' in result.output


@patch("omnifocus_cli.timer._timer_call")
def test_timer_history(mock_call):
    mock_call.return_value = {"status": "ok", "sessions": [], "totalMs": 0}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "timer", "history", "abc"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTimerHistory", {"taskId": "abc"})
```

- [ ] **Step 2: Run tests**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli
poetry run pytest tests/test_timer.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add omnifocus-cli/tests/test_timer.py
git commit -m "test(omnifocus-cli): add unit tests for timer CLI commands"
```

---

## Chunk 3: Phase 3 — Letta Integration

### Task 14: Host Bridge Timer Event Relay

**Files:**
- Modify: `omnifocus-mcp-letta/host-bridge-service.js`

- [ ] **Step 1: Add /timer-event endpoint and Letta message formatting**

Add after the `handleExecute` function:

```javascript
// --- Timer event relay ---
const LETTA_URL = process.env.LETTA_URL || 'http://localhost:8283';
const ROVER_AGENT_ID = process.env.ROVER_AGENT_ID || '';

function formatTimerMessage(event) {
  const taskName = event.taskName || 'unknown task';
  const projectName = event.projectName ? ` (${event.projectName})` : '';
  const sessionMin = event.sessionDurationMs ? Math.round(event.sessionDurationMs / 60000) : 0;
  const totalMin = event.totalDurationMs ? Math.round(event.totalDurationMs / 60000) : 0;
  const estMin = event.originalEstimateMin;

  switch (event.event) {
    case 'timer.started':
      return `Timer started on '${taskName}'${projectName}.${estMin ? ` Estimated duration: ${estMin} min.` : ''}`;
    case 'timer.switched':
      return `Timer switched from '${event.previousTaskName || 'previous task'}' to '${taskName}'${projectName}. Previous session: ${sessionMin} min.`;
    case 'timer.stopped':
      const overNote = estMin ? ` Original estimate: ${estMin} min.` : '';
      return `Timer stopped on '${taskName}'. Session: ${sessionMin} min. Total: ${totalMin} min.${overNote}`;
    case 'timer.paused':
      return `Timer paused on '${taskName}'. Elapsed: ${sessionMin} min.`;
    case 'timer.resumed':
      return `Timer resumed on '${taskName}'.`;
    case 'timer.auto-stopped':
      return `Timer auto-stopped: '${taskName}' was marked complete. Final time: ${totalMin} min.${estMin ? ` (estimate was ${estMin} min)` : ''}`;
    default:
      return `Timer event: ${event.event} on '${taskName}'.`;
  }
}

function handleTimerEvent(body, res) {
  try {
    const event = JSON.parse(body);

    // Don't forward heartbeats
    if (event.event === 'timer.heartbeat') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: true, forwarded: false }));
      return;
    }

    const message = formatTimerMessage(event);
    console.log(`Timer event: ${event.event} → "${message}"`);

    // Forward to Letta agent
    if (ROVER_AGENT_ID) {
      const lettaPayload = JSON.stringify({
        messages: [{ role: 'user', content: message }]
      });

      const lettaReq = http.request(
        `${LETTA_URL}/v1/agents/${ROVER_AGENT_ID}/messages`,
        { method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(lettaPayload) } },
        (lettaRes) => {
          console.log(`Letta relay: ${lettaRes.statusCode}`);
          lettaRes.resume(); // drain response
        }
      );
      lettaReq.on('error', (err) => {
        console.error(`Letta relay failed: ${err.message}`);
      });
      lettaReq.write(lettaPayload);
      lettaReq.end();
    } else {
      console.log('No ROVER_AGENT_ID configured, skipping Letta relay');
    }

    // Always return 200 to the plugin
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success: true, forwarded: !!ROVER_AGENT_ID }));
  } catch (err) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid timer event', details: err.message }));
  }
}
```

- [ ] **Step 2: Update the request router to dispatch /timer-event**

In the `req.on('end', ...)` callback, add the `/timer-event` route:

```javascript
  req.on('end', () => {
    if (req.url === '/execute') {
      handleExecute(body, res);
    } else if (req.url === '/timer-event') {
      handleTimerEvent(body, res);
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  });
```

- [ ] **Step 3: Restart the host bridge and test**

```bash
launchctl stop com.omnifocus.bridge
launchctl start com.omnifocus.bridge

# Test the endpoint
curl -s -X POST http://localhost:8889/timer-event \
  -H "Content-Type: application/json" \
  -d '{"event":"timer.started","taskId":"test","taskName":"Test Task","projectName":"Test Project","originalEstimateMin":30,"timestamp":"2026-03-14T10:00:00Z"}' | python3 -m json.tool
```

Expected: `{"success": true, "forwarded": true}` (or `forwarded: false` if ROVER_AGENT_ID is not set).

- [ ] **Step 4: Commit**

```bash
git add omnifocus-mcp-letta/host-bridge-service.js
git commit -m "feat(host-bridge): add /timer-event relay endpoint for Letta integration"
```

---

### Task 15: Plugin Outbound Event Emission

**Files:**
- Modify: `omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js`

Add `URL.FetchRequest` calls on timer state changes.

- [ ] **Step 1: Add event emission function**

Insert after the CONFIG block:

```javascript
  // --- Event emission ---
  function emitEvent(eventData) {
    try {
      const req = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
      req.method = "POST";
      req.headers = { "Content-Type": "application/json" };
      req.bodyString = JSON.stringify(eventData);
      req.fetch().then(function(response) {
        // Success — no action needed
      }).catch(function(err) {
        console.log("Event delivery failed: " + err.message);
        // Queue for retry
        queuePendingEvent(eventData);
      });
    } catch (e) {
      console.log("Event emission error: " + e.message);
      queuePendingEvent(eventData);
    }
  }

  function queuePendingEvent(eventData) {
    const state = readState();
    const pending = state.pendingEvents || [];
    // Drop heartbeats first if at capacity
    if (pending.length >= CONFIG.maxPendingEvents) {
      const nonHeartbeats = pending.filter(e => e.event !== "timer.heartbeat");
      if (nonHeartbeats.length < CONFIG.maxPendingEvents) {
        state.pendingEvents = nonHeartbeats;
      } else {
        state.pendingEvents = pending.slice(-CONFIG.maxPendingEvents + 1);
      }
    }
    state.pendingEvents.push(eventData);
    prefs().write("pendingEvents", JSON.stringify(state.pendingEvents));
  }

  function retryPendingEvents() {
    const state = readState();
    const pending = state.pendingEvents || [];
    if (pending.length === 0) return;
    // Try to send all pending, keep failures
    const remaining = [];
    for (const evt of pending) {
      try {
        const req = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
        req.method = "POST";
        req.headers = { "Content-Type": "application/json" };
        req.bodyString = JSON.stringify(evt);
        req.fetch().catch(function() { remaining.push(evt); });
      } catch (e) {
        remaining.push(evt);
      }
    }
    prefs().write("pendingEvents", JSON.stringify(remaining));
  }

  function buildEventPayload(eventType, state, extras) {
    const payload = {
      event: eventType,
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      projectName: state.activeProjectName,
      originalEstimateMin: state.originalEstimate,
      timestamp: new Date().toISOString(),
    };
    if (extras) Object.assign(payload, extras);
    return payload;
  }
```

- [ ] **Step 2: Add emitEvent calls to startTimerOnTask, stopTimer, pauseTimer, resumeTimer**

After each operation's state write, add the appropriate emit call. For example, at the end of `startTimerOnTask`:

```javascript
    // Emit event
    emitEvent(buildEventPayload(
      switchResult ? "timer.switched" : "timer.started",
      state,
      switchResult ? { previousTaskId: switchResult.previousTaskId, previousTaskName: switchResult.previousTaskName, sessionDurationMs: switchResult.finalSessionMs } : {}
    ));
```

Similar additions for `stopTimer` (emit `timer.stopped`), `pauseTimer` (emit `timer.paused`), `resumeTimer` (emit `timer.resumed`).

- [ ] **Step 3: Add heartbeat and retry to guardian tick**

In the guardian timer callback, after the notification check:

```javascript
        // 5. Retry pending events
        retryPendingEvents();

        // 6. Heartbeat (every 5 minutes)
        if (now - lastHeartbeatTime >= 300000) {
          lastHeartbeatTime = now;
          const heartbeat = buildEventPayload("timer.heartbeat", state, { currentSessionMs: getElapsedMs(state) });
          // Don't queue heartbeats on failure
          try {
            const req = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
            req.method = "POST";
            req.headers = { "Content-Type": "application/json" };
            req.bodyString = JSON.stringify(heartbeat);
            req.fetch().catch(function() {}); // Silently ignore
          } catch (e) {}
        }
```

- [ ] **Step 4: Test end-to-end event flow**

1. Start timer on a task via OmniFocus Automation menu
2. Check host bridge logs: `tail -f ~/ai-PA/omnifocus-mcp-letta/bridge-service.log`
3. Verify `Timer event: timer.started` appears in the log
4. If ROVER_AGENT_ID is configured, verify Letta receives the message

- [ ] **Step 5: Commit**

```bash
git add omnifocus-timer/omnifocus-timer.omnifocusjs/timer-lib.js
git commit -m "feat(omnifocus-timer): add outbound event emission with retry queue"
```

---

### Task 16: Configure ROVER_AGENT_ID and Validate Integration

**Files:**
- Modify: launchd plist for host bridge (or `.env` file)

- [ ] **Step 1: Set ROVER_AGENT_ID environment variable**

The Rover agent ID is `agent-76ee5448-68ec-4fdd-b102-d4895d44e090` (from project memory).

Update the launchd plist for `com.omnifocus.bridge` to include the environment variable, or set it in the bridge startup script.

- [ ] **Step 2: Restart bridge and run full integration test**

```bash
launchctl stop com.omnifocus.bridge
launchctl start com.omnifocus.bridge

# Start timer via CLI
cd /Volumes/main-drive/ai-PA/omnifocus-cli
TASK_ID=$(poetry run omnifocus-cli task list --format json | python3 -c "import sys,json; tasks=json.load(sys.stdin); print(tasks[0]['id'])")
poetry run omnifocus-cli timer start "$TASK_ID" --format json

# Wait a few seconds, then check Letta messages
sleep 5
curl -s "http://localhost:8283/v1/agents/agent-76ee5448-68ec-4fdd-b102-d4895d44e090/messages?limit=5" | python3 -m json.tool | head -30

# Stop timer
poetry run omnifocus-cli timer stop --format json
```

Expected: Letta agent has received timer.started and timer.stopped messages.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(omnifocus-timer): configure Rover agent ID for timer event relay"
```

---

### Task 17: Verify Rover Has OmniFocus CLI Tool

**Files:** Depends on findings

- [ ] **Step 1: Check Rover's current tools**

```bash
curl -s "http://localhost:8283/v1/agents/agent-76ee5448-68ec-4fdd-b102-d4895d44e090/tools?limit=50" | python3 -c "import sys,json; [print(t['name']) for t in json.load(sys.stdin)]"
```

Look for a tool that can execute shell commands or specifically `omnifocus-cli`.

- [ ] **Step 2: If no suitable tool exists, create one**

Create a Letta custom tool that executes `omnifocus-cli timer <subcommand>` commands. Follow the patterns in `letta/register_*.py` and the coding guidelines in `context/coding_custom_letta_tools.md`.

- [ ] **Step 3: Verify Rover can call timer status**

Send a test message to Rover asking it to check the timer status. Verify it calls the tool and returns the result.

- [ ] **Step 4: Commit if new tool was created**

```bash
git add letta/
git commit -m "feat(letta): add OmniFocus timer tool for Rover agent"
```

---

### Task 18: Final Integration Smoke Test

**Files:** None (testing only)

- [ ] **Step 1: Full round-trip test**

1. In OmniFocus, select a task with an estimate
2. Run "Start Timer" from Automation menu
3. Verify Rover receives `timer.started` message
4. Wait 2+ minutes for guardian to write note
5. Run `omnifocus-cli timer status` — verify state is "running"
6. Run "Pause Timer" from Automation menu
7. Verify note has in-progress line, Rover gets `timer.paused`
8. Run `omnifocus-cli timer resume` — verify CLI can control the timer
9. Run "Stop Timer" from Automation menu
10. Verify final note format matches spec (Agent Estimate if pre-seeded, Original Estimate, session lines, Total, Variance)
11. Run `omnifocus-cli timer history <task-id>` — verify structured output

- [ ] **Step 2: Verify orphan recovery still works after Phase 3 changes**

1. Start timer, quit OmniFocus, reopen — verify recovery alert

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "fix(omnifocus-timer): final integration fixes"
```
