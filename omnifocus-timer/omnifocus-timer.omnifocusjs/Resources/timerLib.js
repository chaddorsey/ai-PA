/*{
  "type": "library",
  "targets": ["omnifocus"],
  "identifier": "timerLib",
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

  // Preferences MUST be constructed during plugin load, not lazily
  var _prefs = new Preferences(null);
  function getPrefs() {
    return _prefs;
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

  var CONFIG = {
    relayEndpoint: "http://100.99.171.119:8889/timer-event",
  };

  const GUARDIAN_INTERVAL_SEC = 60;
  const HEARTBEAT_INTERVAL_MS = 5 * 60 * 1000;
  const NOTIFICATION_INTERVAL_MS = 15 * 60 * 1000;
  const MAX_PENDING_EVENTS = 50;
  const NOTE_BLOCK_START = "--- Time Tracking ---";
  const NOTE_BLOCK_END = "--- End Time Tracking ---";

  // ---------------------------------------------------------------------------
  // 3. Duration / date formatting helpers
  // ---------------------------------------------------------------------------

  function formatDuration(ms) {
    var totalSec = Math.round(ms / 1000);
    if (totalSec < 1) {
      return "0s";
    }
    if (totalSec < 60) {
      return totalSec + "s";
    }
    var totalMin = Math.floor(totalSec / 60);
    var secs = totalSec % 60;
    if (totalMin < 60) {
      return totalMin + "m " + (secs < 10 ? "0" : "") + secs + "s";
    }
    var hours = Math.floor(totalMin / 60);
    var mins = totalMin % 60;
    return hours + "h " + (mins < 10 ? "0" : "") + mins + "m " + (secs < 10 ? "0" : "") + secs + "s";
  }

  function parseDurationToMs(str) {
    if (!str) {
      return 0;
    }
    var trimmed = str.replace(/^~/, "").trim();
    var total = 0;

    // Hours: "1h" or "2h "
    var hMatch = trimmed.match(/(\d+)h/);
    if (hMatch) total += parseInt(hMatch[1], 10) * 3600000;

    // Minutes: "06m" or "32m " or legacy "32 min"
    var mMatch = trimmed.match(/(\d+)m(?:\s|$)/);
    if (mMatch) total += parseInt(mMatch[1], 10) * 60000;
    var minMatch = trimmed.match(/(\d+)\s*min/);
    if (minMatch) total += parseInt(minMatch[1], 10) * 60000;

    // Seconds: "05s"
    var sMatch = trimmed.match(/(\d+)s/);
    if (sMatch) total += parseInt(sMatch[1], 10) * 1000;

    // Legacy "< 1 min"
    if (trimmed === "< 1 min") return 30000;

    return total;
  }

  function formatDateTimePart(d) {
    var year = d.getFullYear();
    var month = (d.getMonth() + 1 < 10 ? "0" : "") + (d.getMonth() + 1);
    var day = (d.getDate() < 10 ? "0" : "") + d.getDate();
    var hours = (d.getHours() < 10 ? "0" : "") + d.getHours();
    var minutes = (d.getMinutes() < 10 ? "0" : "") + d.getMinutes();
    var seconds = (d.getSeconds() < 10 ? "0" : "") + d.getSeconds();
    return year + "-" + month + "-" + day + " " + hours + ":" + minutes + ":" + seconds;
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
  // 5. Event emission
  // ---------------------------------------------------------------------------

  function buildEventPayload(eventType, state, extras) {
    var payload = {
      event: eventType,
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      projectName: state.activeProjectName,
      originalEstimateMin: state.originalEstimate || null,
      agentEstimateMin: null,
      timestamp: new Date().toISOString(),
    };

    // Try to read agent estimate from the task note
    if (state.activeTaskId) {
      try {
        var task = Task.byIdentifier(state.activeTaskId);
        if (task) {
          var parsed = parseNoteBlock(task.note || "");
          if (parsed.agentEstimate) {
            var agentMs = parseDurationToMs(parsed.agentEstimate);
            if (agentMs > 0) {
              payload.agentEstimateMin = Math.round(agentMs / 60000);
            }
          }
        }
      } catch (e) {
        // Ignore — best effort
      }
    }

    if (extras) {
      var keys = Object.keys(extras);
      for (var i = 0; i < keys.length; i++) {
        payload[keys[i]] = extras[keys[i]];
      }
    }

    return payload;
  }

  function emitEvent(eventData) {
    try {
      var req = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
      req.method = "POST";
      req.headers = { "Content-Type": "application/json" };
      req.bodyString = JSON.stringify(eventData);
      req.fetch().then(function (response) {
        // success — no action needed
      }).catch(function (err) {
        console.log("Event delivery failed: " + err.message);
        queuePendingEvent(eventData);
      });
    } catch (e) {
      console.log("Event emission error: " + e.message);
      queuePendingEvent(eventData);
    }
  }

  function queuePendingEvent(eventData) {
    // Don't queue heartbeats
    if (eventData.event === "timer.heartbeat") {
      return;
    }

    var state = readState();
    var queue = state.pendingEvents || [];

    // If at capacity, drop heartbeats first, then oldest
    if (queue.length >= MAX_PENDING_EVENTS) {
      // Try dropping a heartbeat first
      var dropped = false;
      for (var i = 0; i < queue.length; i++) {
        if (queue[i].event === "timer.heartbeat") {
          queue.splice(i, 1);
          dropped = true;
          break;
        }
      }
      if (!dropped) {
        queue.shift(); // drop oldest
      }
    }

    queue.push(eventData);
    state.pendingEvents = queue;
    writeState(state);
  }

  function retryPendingEvents() {
    var state = readState();
    var queue = state.pendingEvents || [];
    if (queue.length === 0) {
      return;
    }

    // Process ONE event at a time to avoid async race conditions
    var evt = queue[0];
    try {
      var req = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
      req.method = "POST";
      req.headers = { "Content-Type": "application/json" };
      req.bodyString = JSON.stringify(evt);
      req.fetch().then(function (response) {
        // Success — remove from queue
        var freshState = readState();
        var freshQueue = freshState.pendingEvents || [];
        if (freshQueue.length > 0) {
          freshQueue.shift();
          freshState.pendingEvents = freshQueue;
          writeState(freshState);
        }
      }).catch(function (err) {
        // Leave in queue for next tick
        console.log("Retry delivery failed: " + err.message);
      });
    } catch (e) {
      console.log("Retry error: " + e.message);
    }
  }

  // ---------------------------------------------------------------------------
  // 6. Timer operations
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

    // Emit event
    if (switchedFrom) {
      emitEvent(buildEventPayload("timer.switched", newState, {
        switchedFrom: switchedFrom,
        previousSessionMin: null,  // previous session already stopped
      }));
    } else {
      emitEvent(buildEventPayload("timer.started", newState, {}));
    }

    return result;
  }

  function stopTimer() {
    var state = readState();
    if (state.state === STATE_IDLE || !state.activeTaskId) {
      return { status: "idle", message: "No timer is running" };
    }

    var elapsed = getElapsedMs(state);
    var sessionMs = elapsed;  // current engagement total
    var origEst = state.originalEstimate;

    var result = stopCurrentTimer(state);

    if (result.status === "stopped") {
      emitEvent(buildEventPayload("timer.stopped", {
        activeTaskId: result.taskId || state.activeTaskId,
        activeTaskName: result.taskName,
        activeProjectName: state.activeProjectName,
        originalEstimate: origEst,
      }, {
        sessionMs: sessionMs,
        totalMs: result.totalElapsed,
      }));
    }

    return result;
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

    // Emit pause event
    emitEvent(buildEventPayload("timer.paused", state, {
      elapsedMs: state.accumulatedMs,
    }));

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

    // Emit resume event
    emitEvent(buildEventPayload("timer.resumed", state, {}));

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

    // Count sessions from the note (prior engagements) + current engagement
    var noteSessionCount = 0;
    var task = resolveTask(state.activeTaskId);
    if (task) {
      var parsed = parseNoteBlock(task.note || "");
      noteSessionCount = parsed.sessions.length;
    }
    var totalSessions = noteSessionCount + state.sessions.length + (state.state === STATE_RUNNING ? 1 : 0);

    return {
      status: state.state,
      taskId: state.activeTaskId,
      taskName: state.activeTaskName,
      projectName: state.activeProjectName,
      elapsed: elapsed,
      elapsedFormatted: formatDuration(elapsed),
      sessionCount: totalSessions,
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

    // Include current in-progress session from Preferences if timer is active on this task
    var state = readState();
    var inProgressMs = 0;
    if (state.activeTaskId === task.id.primaryKey && state.state !== STATE_IDLE) {
      inProgressMs = getElapsedMs(state);
      totalMs += inProgressMs;
    }

    return {
      status: "ok",
      taskId: task.id.primaryKey,
      taskName: task.name,
      agentEstimate: parsed.agentEstimate,
      originalEstimate: parsed.originalEstimate,
      sessionCount: parsed.sessions.length + (inProgressMs > 0 ? 1 : 0),
      totalMs: totalMs,
      totalFormatted: formatDuration(totalMs),
      sessions: parsed.sessions,
      inProgress: inProgressMs > 0 ? { elapsedMs: inProgressMs, state: state.state } : null,
    };
  }

  // ---------------------------------------------------------------------------
  // 7. Guardian timer
  // ---------------------------------------------------------------------------

  var guardianTimer = null;
  var lastNotificationMs = 0;
  var lastHeartbeatMs = 0;

  function cancelGuardian() {
    if (guardianTimer) {
      guardianTimer.cancel();
      guardianTimer = null;
    }
    lastNotificationMs = 0;
    lastHeartbeatMs = 0;
  }

  function startGuardian() {
    cancelGuardian();
    lastNotificationMs = Date.now();
    lastHeartbeatMs = Date.now();

    guardianTimer = Timer.repeating(GUARDIAN_INTERVAL_SEC, function () {
      var state = readState();

      // Retry any pending events each tick
      retryPendingEvents();

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
        var elapsed = getElapsedMs(state);
        var origEst = state.originalEstimate;
        var taskName = state.activeTaskName;

        // Emit auto-stop event before stopping (state still has task info)
        emitEvent(buildEventPayload("timer.auto-stopped", state, {
          totalMs: elapsed,
        }));

        stopCurrentTimer(state);
        var note = new Notification("Timer auto-stopped");
        note.subtitle =
          taskName + " was completed. Timer stopped at " + formatDuration(elapsed) + ".";
        note.show();
        return;
      }

      // Persist current state to note
      var elapsed = getElapsedMs(state);
      writeNoteBlock(task, state, elapsed - state.accumulatedMs);

      // 5-minute heartbeat (not queued on failure)
      var now = Date.now();
      if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        var heartbeat = buildEventPayload("timer.heartbeat", state, {
          elapsedMs: elapsed,
        });
        // Fire directly — don't queue heartbeats on failure
        try {
          var hbReq = URL.FetchRequest.fromString(CONFIG.relayEndpoint);
          hbReq.method = "POST";
          hbReq.headers = { "Content-Type": "application/json" };
          hbReq.bodyString = JSON.stringify(heartbeat);
          hbReq.fetch().then(function () {}).catch(function () {});
        } catch (e) {
          // Ignore heartbeat failures
        }
      }

      // 15-minute notification
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
  // 8. Orphan recovery
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
          var now = Date.now();
          var staleDuration = now - state.currentIntervalStart;
          // Keep accumulated, restart interval from now
          state.accumulatedMs += staleDuration;
          state.sessions.push({
            start: state.currentIntervalStart,
            end: now,
            durationMs: staleDuration,
          });
          state.currentIntervalStart = now;
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

  // Orphan check is NOT run on library load because the library IIFE
  // re-executes on every `evaluate javascript` call from osascript.
  // Instead, orphan recovery is triggered by the startTimer action
  // when OmniFocus first opens (via action validate/perform).

  // ---------------------------------------------------------------------------
  // 9. Library exports
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
