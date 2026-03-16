/*{
  "type": "library",
  "targets": ["omnifocus"],
  "identifier": "com.dorsey.omnifocus-completion-watcher.watcherLib",
  "version": "1.0",
  "description": "Completion watcher core logic: polls for completed tasks, POSTs to Task Completion Service."
}*/
(() => {
  const lib = new PlugIn.Library(new Version("1.0"));

  // ── Configuration ──────────────────────────────────────────────
  const POLL_INTERVAL_SEC = 60;
  const SERVICE_URL = "http://localhost:8092/v1/completion";
  const MAX_PENDING_EVENTS = 50;

  const PREF_KEYS = {
    LAST_CHECK: "lastCheckTimestamp",
    WATCHER_RUNNING: "watcherRunning",
    PENDING_EVENTS: "pendingEvents",
    STATS_TOTAL: "statsTotal",
    STATS_ERRORS: "statsErrors",
  };

  var prefs = new Preferences("com.dorsey.omnifocus-completion-watcher");
  var watcherTimer = null;

  // ── Pending Events Queue ───────────────────────────────────────

  function loadPendingEvents() {
    try {
      var raw = prefs.readString(PREF_KEYS.PENDING_EVENTS);
      if (raw) return JSON.parse(raw);
    } catch (e) { /* ignore */ }
    return [];
  }

  function savePendingEvents(events) {
    prefs.write(PREF_KEYS.PENDING_EVENTS, JSON.stringify(events));
  }

  function queuePendingEvent(eventData) {
    var events = loadPendingEvents();
    if (events.length >= MAX_PENDING_EVENTS) {
      events.shift();
    }
    events.push(eventData);
    savePendingEvents(events);
  }

  function retryPendingEvents() {
    var events = loadPendingEvents();
    if (events.length === 0) return;

    var event = events[0];
    var req = URL.FetchRequest.fromString(SERVICE_URL);
    req.method = "POST";
    req.headers = { "Content-Type": "application/json" };
    req.bodyString = JSON.stringify(event);
    req.fetch().then(function (response) {
      if (response.statusCode >= 200 && response.statusCode < 300) {
        events.shift();
        savePendingEvents(events);
      }
    }).catch(function (err) {
      // Leave in queue for next tick
    });
  }

  // ── Completion Detection ───────────────────────────────────────

  function getLastCheckTimestamp() {
    var ts = prefs.readString(PREF_KEYS.LAST_CHECK);
    if (ts) return new Date(ts);
    return new Date(Date.now() - 5 * 60 * 1000);
  }

  function setLastCheckTimestamp(date) {
    prefs.write(PREF_KEYS.LAST_CHECK, date.toISOString());
  }

  function findNewCompletions() {
    var lastCheck = getLastCheckTimestamp();
    var now = new Date();
    var completions = [];

    flattenedTasks.forEach(function (task) {
      if (!task.completed && task.taskStatus !== Task.Status.Dropped) return;

      var completionDate = task.completionDate;
      if (!completionDate) return;
      if (completionDate <= lastCheck) return;

      var tagNames = [];
      task.tags.forEach(function (tag) {
        tagNames.push(tag.name);
      });

      completions.push({
        task_id: task.id.primaryKey,
        task_name: task.name,
        note: task.note || "",
        completion_date: completionDate.toISOString(),
        was_dropped: task.taskStatus === Task.Status.Dropped,
        project_name: task.containingProject ? task.containingProject.name : null,
        tags: tagNames,
      });
    });

    return { completions: completions, checkTime: now };
  }

  // ── Notification Sending ───────────────────────────────────────

  function sendCompletion(completionData, checkTime, isLast) {
    var req = URL.FetchRequest.fromString(SERVICE_URL);
    req.method = "POST";
    req.headers = { "Content-Type": "application/json" };
    req.bodyString = JSON.stringify(completionData);
    req.fetch().then(function (response) {
      if (response.statusCode >= 200 && response.statusCode < 300) {
        var total = (prefs.readString(PREF_KEYS.STATS_TOTAL) || "0");
        prefs.write(PREF_KEYS.STATS_TOTAL, String(parseInt(total) + 1));
        if (isLast) {
          setLastCheckTimestamp(checkTime);
        }
      } else {
        queuePendingEvent(completionData);
        var errors = (prefs.readString(PREF_KEYS.STATS_ERRORS) || "0");
        prefs.write(PREF_KEYS.STATS_ERRORS, String(parseInt(errors) + 1));
      }
    }).catch(function (err) {
      queuePendingEvent(completionData);
    });
  }

  // ── Poll Tick ──────────────────────────────────────────────────

  function pollTick() {
    retryPendingEvents();

    var result = findNewCompletions();
    var completions = result.completions;
    var checkTime = result.checkTime;

    if (completions.length === 0) return;

    for (var i = 0; i < completions.length; i++) {
      var isLast = (i === completions.length - 1);
      sendCompletion(completions[i], checkTime, isLast);
    }
  }

  // ── Public API ─────────────────────────────────────────────────

  lib.startWatcher = function () {
    if (watcherTimer) return;
    watcherTimer = Timer.repeating(POLL_INTERVAL_SEC, pollTick);
    prefs.write(PREF_KEYS.WATCHER_RUNNING, "true");
    console.log("[CompletionWatcher] Started (interval: " + POLL_INTERVAL_SEC + "s)");

    pollTick();
  };

  lib.stopWatcher = function () {
    if (watcherTimer) {
      watcherTimer.cancel();
      watcherTimer = null;
    }
    prefs.write(PREF_KEYS.WATCHER_RUNNING, "false");
    console.log("[CompletionWatcher] Stopped");
  };

  lib.getStatus = function () {
    var running = watcherTimer !== null;
    var lastCheck = prefs.readString(PREF_KEYS.LAST_CHECK) || "never";
    var pending = loadPendingEvents().length;
    var total = prefs.readString(PREF_KEYS.STATS_TOTAL) || "0";
    var errors = prefs.readString(PREF_KEYS.STATS_ERRORS) || "0";
    return "Running: " + running +
           "\nLast check: " + lastCheck +
           "\nPending events: " + pending +
           "\nTotal sent: " + total +
           "\nErrors: " + errors;
  };

  var wasRunning = prefs.readString(PREF_KEYS.WATCHER_RUNNING);
  if (wasRunning === "true") {
    lib.startWatcher();
  }

  return lib;
})();
