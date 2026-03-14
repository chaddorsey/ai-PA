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

  // ---------------------------------------------------------------------------
  // 1. Preferences helpers
  // ---------------------------------------------------------------------------

  const PREF_KEYS = {
    ACTIVE_TASK_ID: "activeTaskId",
    ACTIVE_TASK_NAME: "activeTaskName",
    ACTIVE_PROJECT_NAME: "activeProjectName",
    STATE: "state",
    CURRENT_INTERVAL_START: "currentIntervalStart",
    ACCUMULATED_MS: "accumulatedMs",
    ORIGINAL_ESTIMATE: "originalEstimate",
    SESSIONS: "sessions",
    PENDING_EVENTS: "pendingEvents",
  };

  const STATE_RUNNING = "running";
  const STATE_PAUSED = "paused";
  const STATE_IDLE = "idle";

  function getPrefs() {
    return new Preferences(null);
  }

  function readState() {
    const prefs = getPrefs();
    const sessionsRaw = prefs.readString(PREF_KEYS.SESSIONS);
    const pendingRaw = prefs.readString(PREF_KEYS.PENDING_EVENTS);
    return {
      activeTaskId: prefs.readString(PREF_KEYS.ACTIVE_TASK_ID) || null,
      activeTaskName: prefs.readString(PREF_KEYS.ACTIVE_TASK_NAME) || null,
      activeProjectName: prefs.readString(PREF_KEYS.ACTIVE_PROJECT_NAME) || null,
      state: prefs.readString(PREF_KEYS.STATE) || STATE_IDLE,
      currentIntervalStart: prefs.readNumber(PREF_KEYS.CURRENT_INTERVAL_START) || 0,
      accumulatedMs: prefs.readNumber(PREF_KEYS.ACCUMULATED_MS) || 0,
      originalEstimate: prefs.readNumber(PREF_KEYS.ORIGINAL_ESTIMATE),
      sessions: sessionsRaw ? JSON.parse(sessionsRaw) : [],
      pendingEvents: pendingRaw ? JSON.parse(pendingRaw) : [],
    };
  }

  function writeState(s) {
    const prefs = getPrefs();
    prefs.write(PREF_KEYS.ACTIVE_TASK_ID, s.activeTaskId || "");
    prefs.write(PREF_KEYS.ACTIVE_TASK_NAME, s.activeTaskName || "");
    prefs.write(PREF_KEYS.ACTIVE_PROJECT_NAME, s.activeProjectName || "");
    prefs.write(PREF_KEYS.STATE, s.state || STATE_IDLE);
    prefs.write(PREF_KEYS.CURRENT_INTERVAL_START, s.currentIntervalStart || 0);
    prefs.write(PREF_KEYS.ACCUMULATED_MS, s.accumulatedMs || 0);
    if (s.originalEstimate !== null && s.originalEstimate !== undefined) {
      prefs.write(PREF_KEYS.ORIGINAL_ESTIMATE, s.originalEstimate);
    } else {
      prefs.remove(PREF_KEYS.ORIGINAL_ESTIMATE);
    }
    prefs.write(PREF_KEYS.SESSIONS, JSON.stringify(s.sessions || []));
    prefs.write(PREF_KEYS.PENDING_EVENTS, JSON.stringify(s.pendingEvents || []));
  }

  function clearState() {
    const prefs = getPrefs();
    var keys = Object.values(PREF_KEYS);
    for (var i = 0; i < keys.length; i++) {
      prefs.remove(keys[i]);
    }
  }

  // ---------------------------------------------------------------------------
  // 2. Config constants
  // ---------------------------------------------------------------------------

  const GUARDIAN_INTERVAL_SEC = 60;
  const NOTIFICATION_INTERVAL_MS = 15 * 60 * 1000;
  const NOTE_BLOCK_START = "--- Time Tracking ---";
  const NOTE_BLOCK_END = "--- End Time Tracking ---";

  // ---------------------------------------------------------------------------
  // 3. Duration / date formatting helpers
  // ---------------------------------------------------------------------------

  function formatDuration(ms) {
    var totalMin = Math.round(ms / 60000);
    if (totalMin < 1) {
      return "0 min";
    }
    if (totalMin < 60) {
      return totalMin + " min";
    }
    var hours = Math.floor(totalMin / 60);
    var mins = totalMin % 60;
    var minsStr = mins < 10 ? "0" + mins : "" + mins;
    return hours + "h " + minsStr + "m";
  }

  function parseDurationToMs(str) {
    if (!str) {
      return 0;
    }
    var trimmed = str.replace(/^~/, "").trim();
    // "1h 06m"
    var hm = trimmed.match(/^(\d+)h\s*(\d+)m$/);
    if (hm) {
      return (parseInt(hm[1], 10) * 60 + parseInt(hm[2], 10)) * 60000;
    }
    // "32 min"
    var m = trimmed.match(/^(\d+)\s*min$/);
    if (m) {
      return parseInt(m[1], 10) * 60000;
    }
    return 0;
  }

  function formatDateTimePart(d) {
    var year = d.getFullYear();
    var month = (d.getMonth() + 1 < 10 ? "0" : "") + (d.getMonth() + 1);
    var day = (d.getDate() < 10 ? "0" : "") + d.getDate();
    var hours = (d.getHours() < 10 ? "0" : "") + d.getHours();
    var minutes = (d.getMinutes() < 10 ? "0" : "") + d.getMinutes();
    return year + "-" + month + "-" + day + " " + hours + ":" + minutes;
  }

  function formatDatePart(d) {
    var year = d.getFullYear();
    var month = (d.getMonth() + 1 < 10 ? "0" : "") + (d.getMonth() + 1);
    var day = (d.getDate() < 10 ? "0" : "") + d.getDate();
    return year + "-" + month + "-" + day;
  }

  function sameDay(d1, d2) {
    return (
      d1.getFullYear() === d2.getFullYear() &&
      d1.getMonth() === d2.getMonth() &&
      d1.getDate() === d2.getDate()
    );
  }

  function formatSessionLine(session) {
    var startDate = new Date(session.start);
    var endDate = new Date(session.end);
    var dur = formatDuration(session.durationMs);
    if (sameDay(startDate, endDate)) {
      var datePrefix = formatDatePart(startDate);
      var startTime =
        (startDate.getHours() < 10 ? "0" : "") +
        startDate.getHours() +
        ":" +
        (startDate.getMinutes() < 10 ? "0" : "") +
        startDate.getMinutes();
      var endTime =
        (endDate.getHours() < 10 ? "0" : "") +
        endDate.getHours() +
        ":" +
        (endDate.getMinutes() < 10 ? "0" : "") +
        endDate.getMinutes();
      return "[" + datePrefix + " " + startTime + "\u2013" + endTime + "] " + dur;
    }
    return (
      "[" +
      formatDateTimePart(startDate) +
      "\u2013" +
      formatDateTimePart(endDate) +
      "] " +
      dur
    );
  }

  function formatInProgressLine(startMs, elapsedMs) {
    var startDate = new Date(startMs);
    var dur = formatDuration(elapsedMs);
    return "[" + formatDateTimePart(startDate) + " in progress] ~" + dur;
  }

  // ---------------------------------------------------------------------------
  // 4. Note block parsing & building
  // ---------------------------------------------------------------------------

  function parseNoteBlock(noteText) {
    var result = {
      agentEstimate: null,
      originalEstimate: null,
      sessions: [],
      beforeBlock: "",
      afterBlock: "",
    };

    if (!noteText) {
      return result;
    }

    var startIdx = noteText.indexOf(NOTE_BLOCK_START);
    var endIdx = noteText.indexOf(NOTE_BLOCK_END);

    if (startIdx === -1 || endIdx === -1) {
      result.beforeBlock = noteText;
      return result;
    }

    result.beforeBlock = noteText.substring(0, startIdx);
    result.afterBlock = noteText.substring(endIdx + NOTE_BLOCK_END.length);

    var blockContent = noteText.substring(
      startIdx + NOTE_BLOCK_START.length,
      endIdx
    );
    var lines = blockContent.split("\n");

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) {
        continue;
      }

      // Agent Estimate line
      var agentMatch = line.match(/^Agent Estimate:\s*(.+)$/);
      if (agentMatch) {
        result.agentEstimate = agentMatch[1].trim();
        continue;
      }

      // Original Estimate line
      var origMatch = line.match(/^Original Estimate:\s*(.+)$/);
      if (origMatch) {
        var origVal = origMatch[1].trim();
        if (origVal !== "none") {
          result.originalEstimate = origVal;
        }
        continue;
      }

      // Session line: [date time–time] duration or [date time–date time] duration
      var sessionMatch = line.match(/^\[(.+?)\]\s+(.+)$/);
      if (sessionMatch) {
        var timeRange = sessionMatch[1];
        var duration = sessionMatch[2];
        // Skip "in progress" lines — they get regenerated
        if (timeRange.indexOf("in progress") !== -1) {
          continue;
        }
        result.sessions.push({
          range: timeRange,
          duration: duration,
          durationMs: parseDurationToMs(duration),
        });
        continue;
      }

      // Total and Variance lines are derived — skip them
      if (line.indexOf("Total:") === 0 || line.indexOf("Variance:") === 0) {
        continue;
      }
    }

    return result;
  }

  function buildNoteBlock(
    agentEstimate,
    originalEstimate,
    priorSessions,
    currentSessions,
    inProgressLine,
    totalMs,
    originalEstimateMs
  ) {
    var lines = [];
    lines.push(NOTE_BLOCK_START);

    if (agentEstimate) {
      lines.push("Agent Estimate: " + agentEstimate);
    }

    if (originalEstimate !== null && originalEstimate !== undefined) {
      lines.push("Original Estimate: " + originalEstimate);
    } else {
      lines.push("Original Estimate: none");
    }

    // Prior sessions (from previous timing engagements, parsed from note)
    for (var i = 0; i < priorSessions.length; i++) {
      lines.push(
        "[" + priorSessions[i].range + "] " + priorSessions[i].duration
      );
    }

    // Current engagement sessions (from preferences state)
    for (var j = 0; j < currentSessions.length; j++) {
      lines.push(formatSessionLine(currentSessions[j]));
    }

    // In-progress line if timer is running
    if (inProgressLine) {
      lines.push(inProgressLine);
    }

    lines.push("Total: " + formatDuration(totalMs));

    // Variance only if original estimate exists
    if (originalEstimateMs !== null && originalEstimateMs > 0) {
      var diffMs = totalMs - originalEstimateMs;
      var sign = diffMs >= 0 ? "+" : "";
      var diffMin = Math.round(diffMs / 60000);
      var pct = Math.round((diffMs / originalEstimateMs) * 100);
      lines.push(
        "Variance: " + sign + diffMin + " min (" + sign + pct + "%)"
      );
    }

    lines.push(NOTE_BLOCK_END);
    return lines.join("\n");
  }

  function writeNoteBlock(task, state, inProgressMs) {
    var noteText = task.note || "";
    var parsed = parseNoteBlock(noteText);

    // Determine original estimate string and ms
    var origEstStr = parsed.originalEstimate;
    var origEstMs = null;
    if (
      state.originalEstimate !== null &&
      state.originalEstimate !== undefined
    ) {
      origEstStr = formatDuration(state.originalEstimate * 60000);
      origEstMs = state.originalEstimate * 60000;
    } else if (parsed.originalEstimate) {
      origEstMs = parseDurationToMs(parsed.originalEstimate);
    }

    // Calculate total ms across all engagements
    var priorTotalMs = 0;
    for (var i = 0; i < parsed.sessions.length; i++) {
      priorTotalMs += parsed.sessions[i].durationMs;
    }
    var currentTotalMs = 0;
    for (var j = 0; j < state.sessions.length; j++) {
      currentTotalMs += state.sessions[j].durationMs;
    }
    var grandTotalMs = priorTotalMs + currentTotalMs + (inProgressMs || 0);

    // Build in-progress line
    var ipLine = null;
    if (state.state === STATE_RUNNING && state.currentIntervalStart > 0) {
      ipLine = formatInProgressLine(state.currentIntervalStart, inProgressMs || 0);
    }

    var block = buildNoteBlock(
      parsed.agentEstimate,
      origEstStr,
      parsed.sessions,
      state.sessions,
      ipLine,
      grandTotalMs,
      origEstMs
    );

    // Reassemble note
    var before = parsed.beforeBlock;
    var after = parsed.afterBlock;

    // Clean up whitespace around block insertion
    if (before && !before.endsWith("\n")) {
      before = before + "\n";
    }
    if (after && !after.startsWith("\n")) {
      after = "\n" + after;
    }

    task.note = before + block + after;
  }

  // ---------------------------------------------------------------------------
  // 5. Timer operations
  // ---------------------------------------------------------------------------

  function getElapsedMs(state) {
    var accumulated = state.accumulatedMs || 0;
    if (state.state === STATE_RUNNING && state.currentIntervalStart > 0) {
      accumulated += Date.now() - state.currentIntervalStart;
    }
    return accumulated;
  }

  function resolveTask(taskOrId) {
    if (typeof taskOrId === "string") {
      return Task.byIdentifier(taskOrId);
    }
    return taskOrId;
  }

  function stopCurrentTimer(state) {
    // Finalize the current running/paused timer, write to note, return result
    var task = Task.byIdentifier(state.activeTaskId);
    if (!task) {
      clearState();
      return { status: "error", message: "Active task no longer exists" };
    }

    // If running, close the current interval
    if (state.state === STATE_RUNNING && state.currentIntervalStart > 0) {
      var now = Date.now();
      var intervalMs = now - state.currentIntervalStart;
      state.sessions.push({
        start: state.currentIntervalStart,
        end: now,
        durationMs: intervalMs,
      });
      state.accumulatedMs += intervalMs;
      state.currentIntervalStart = 0;
    }

    state.state = STATE_IDLE;

    // Write final note
    writeNoteBlock(task, state, 0);

    var totalElapsed = state.accumulatedMs;
    var taskName = state.activeTaskName;

    // Cancel guardian
    cancelGuardian();
    clearState();

    return {
      status: "stopped",
      taskName: taskName,
      totalElapsed: totalElapsed,
      totalFormatted: formatDuration(totalElapsed),
    };
  }

  function startTimerOnTask(taskOrId) {
    var task = resolveTask(taskOrId);
    if (!task) {
      return { status: "error", message: "Task not found" };
    }

    var taskId = task.id.primaryKey;
    var state = readState();

    // Already timing this task?
    if (state.activeTaskId === taskId && state.state === STATE_RUNNING) {
      return {
        status: "already_timing",
        taskName: state.activeTaskName,
        elapsed: getElapsedMs(state),
        elapsedFormatted: formatDuration(getElapsedMs(state)),
      };
    }

    // If timing a different task, stop it first
    var switchedFrom = null;
    if (state.activeTaskId && state.activeTaskId !== taskId && state.state !== STATE_IDLE) {
      var stopResult = stopCurrentTimer(state);
      switchedFrom = stopResult.taskName;
      state = readState(); // re-read after clear
    }

    // If paused on same task, resume instead
    if (state.activeTaskId === taskId && state.state === STATE_PAUSED) {
      return resumeTimer();
    }

    // Determine original estimate
    var origEst = null;
    var existingParsed = parseNoteBlock(task.note || "");
    if (existingParsed.originalEstimate) {
      // Preserve existing original estimate from note
      origEst = parseDurationToMs(existingParsed.originalEstimate) / 60000;
    } else if (
      task.estimatedMinutes !== null &&
      task.estimatedMinutes !== undefined &&
      task.estimatedMinutes > 0
    ) {
      origEst = task.estimatedMinutes;
    }

    var projectName = null;
    if (task.containingProject) {
      projectName = task.containingProject.name;
    }

    var newState = {
      activeTaskId: taskId,
      activeTaskName: task.name,
      activeProjectName: projectName,
      state: STATE_RUNNING,
      currentIntervalStart: Date.now(),
      accumulatedMs: 0,
      originalEstimate: origEst,
      sessions: [],
      pendingEvents: [],
    };

    writeState(newState);

    // Write initial note block
    writeNoteBlock(task, newState, 0);

    // Start guardian timer
    startGuardian();

    var result = {
      status: switchedFrom ? "switched" : "started",
      taskId: taskId,
      taskName: task.name,
      projectName: projectName,
    };
    if (switchedFrom) {
      result.switchedFrom = switchedFrom;
    }
    return result;
  }

  function stopTimer() {
    var state = readState();
    if (state.state === STATE_IDLE || !state.activeTaskId) {
      return { status: "idle", message: "No timer is running" };
    }
    return stopCurrentTimer(state);
  }

  function pauseTimer() {
    var state = readState();
    if (state.state !== STATE_RUNNING) {
      if (state.state === STATE_PAUSED) {
        return {
          status: "already_paused",
          taskName: state.activeTaskName,
          elapsed: getElapsedMs(state),
          elapsedFormatted: formatDuration(getElapsedMs(state)),
        };
      }
      return { status: "idle", message: "No timer is running" };
    }

    // Close current interval
    var now = Date.now();
    var intervalMs = now - state.currentIntervalStart;
    state.sessions.push({
      start: state.currentIntervalStart,
      end: now,
      durationMs: intervalMs,
    });
    state.accumulatedMs += intervalMs;
    state.currentIntervalStart = 0;
    state.state = STATE_PAUSED;

    writeState(state);

    // Write note with no in-progress line
    var task = Task.byIdentifier(state.activeTaskId);
    if (task) {
      writeNoteBlock(task, state, 0);
    }

    return {
      status: "paused",
      taskName: state.activeTaskName,
      elapsed: state.accumulatedMs,
      elapsedFormatted: formatDuration(state.accumulatedMs),
    };
  }

  function resumeTimer() {
    var state = readState();
    if (state.state !== STATE_PAUSED) {
      if (state.state === STATE_RUNNING) {
        return {
          status: "already_running",
          taskName: state.activeTaskName,
          elapsed: getElapsedMs(state),
          elapsedFormatted: formatDuration(getElapsedMs(state)),
        };
      }
      return { status: "idle", message: "No timer is paused" };
    }

    state.state = STATE_RUNNING;
    state.currentIntervalStart = Date.now();

    writeState(state);

    // Restart guardian
    startGuardian();

    return {
      status: "resumed",
      taskName: state.activeTaskName,
      elapsed: state.accumulatedMs,
      elapsedFormatted: formatDuration(state.accumulatedMs),
    };
  }

  function getTimerStatus() {
    var state = readState();
    if (state.state === STATE_IDLE || !state.activeTaskId) {
      return { status: "idle" };
    }

    var elapsed = getElapsedMs(state);
    return {
      status: state.state,
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      projectName: state.activeProjectName,
      elapsed: elapsed,
      elapsedFormatted: formatDuration(elapsed),
      sessionCount: state.sessions.length + (state.state === STATE_RUNNING ? 1 : 0),
      originalEstimate: state.originalEstimate,
    };
  }

  function getTimerHistory(taskId) {
    var task = resolveTask(taskId);
    if (!task) {
      return { status: "error", message: "Task not found" };
    }

    var parsed = parseNoteBlock(task.note || "");
    var totalMs = 0;
    for (var i = 0; i < parsed.sessions.length; i++) {
      totalMs += parsed.sessions[i].durationMs;
    }

    return {
      status: "ok",
      taskId: task.id.primaryKey,
      taskName: task.name,
      agentEstimate: parsed.agentEstimate,
      originalEstimate: parsed.originalEstimate,
      sessionCount: parsed.sessions.length,
      totalMs: totalMs,
      totalFormatted: formatDuration(totalMs),
      sessions: parsed.sessions,
    };
  }

  // ---------------------------------------------------------------------------
  // 6. Guardian timer
  // ---------------------------------------------------------------------------

  var guardianTimer = null;
  var lastNotificationMs = 0;

  function cancelGuardian() {
    if (guardianTimer) {
      guardianTimer.cancel();
      guardianTimer = null;
    }
    lastNotificationMs = 0;
  }

  function startGuardian() {
    cancelGuardian();
    lastNotificationMs = Date.now();

    guardianTimer = Timer.repeating(GUARDIAN_INTERVAL_SEC, function () {
      var state = readState();

      // Not running? Cancel self.
      if (state.state !== STATE_RUNNING || !state.activeTaskId) {
        cancelGuardian();
        return;
      }

      var task = Task.byIdentifier(state.activeTaskId);
      if (!task) {
        // Task deleted — clean up
        cancelGuardian();
        clearState();
        return;
      }

      // Check if task was completed externally — auto-stop
      if (task.completed || task.taskStatus === Task.Status.Completed || task.taskStatus === Task.Status.Dropped) {
        stopCurrentTimer(state);
        var note = new Notification("Timer auto-stopped");
        note.subtitle =
          state.activeTaskName + " was completed. Timer stopped at " + formatDuration(getElapsedMs(state)) + ".";
        note.show();
        return;
      }

      // Persist current state to note
      var elapsed = getElapsedMs(state);
      writeNoteBlock(task, state, elapsed - state.accumulatedMs);

      // 15-minute notification
      var now = Date.now();
      if (now - lastNotificationMs >= NOTIFICATION_INTERVAL_MS) {
        lastNotificationMs = now;
        var notification = new Notification("Timer running");
        notification.subtitle =
          state.activeTaskName + " \u2014 " + formatDuration(elapsed);
        notification.show();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 7. Orphan recovery
  // ---------------------------------------------------------------------------

  function checkOrphanedTimer() {
    var state = readState();
    if (state.state === STATE_IDLE || !state.activeTaskId) {
      return;
    }

    // There's a stale running/paused state from a previous session
    var taskName = state.activeTaskName || "Unknown task";
    var elapsed = getElapsedMs(state);
    var elapsedStr = formatDuration(elapsed);

    var alert = new Alert(
      "Orphaned Timer Detected",
      "A timer for \"" +
        taskName +
        "\" was left " +
        state.state +
        " (" +
        elapsedStr +
        "). What would you like to do?"
    );
    alert.addOption("Resume timer");
    alert.addOption("Stop and save");
    alert.addOption("Discard timer");

    alert.show().then(function (idx) {
      if (idx === 0) {
        // Resume
        if (state.state === STATE_PAUSED) {
          resumeTimer();
        } else {
          // Was running — the interval start is stale, adjust
          var staleDuration = Date.now() - state.currentIntervalStart;
          // Keep accumulated, restart interval from now
          state.accumulatedMs += staleDuration;
          state.sessions.push({
            start: state.currentIntervalStart,
            end: Date.now(),
            durationMs: staleDuration,
          });
          state.currentIntervalStart = Date.now();
          writeState(state);
          startGuardian();
        }
      } else if (idx === 1) {
        // Stop and save
        stopCurrentTimer(state);
      } else {
        // Discard
        cancelGuardian();
        clearState();
      }
    });
  }

  // Run orphan check on library load
  checkOrphanedTimer();

  // ---------------------------------------------------------------------------
  // 8. Library exports
  // ---------------------------------------------------------------------------

  lib.startTimerOnTask = startTimerOnTask;
  lib.stopTimer = stopTimer;
  lib.pauseTimer = pauseTimer;
  lib.resumeTimer = resumeTimer;
  lib.getTimerStatus = getTimerStatus;
  lib.getTimerHistory = getTimerHistory;
  lib.checkOrphanedTimer = checkOrphanedTimer;

  // Expose helpers for actions and testing
  lib.formatDuration = formatDuration;
  lib.parseDurationToMs = parseDurationToMs;
  lib.parseNoteBlock = parseNoteBlock;
  lib.readState = readState;
  lib.writeState = writeState;
  lib.clearState = clearState;

  return lib;
})();
