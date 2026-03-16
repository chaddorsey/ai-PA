# Unified Task Completion & Widget Queue Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace polling-based task completion detection with push-based architecture, integrate the widget queue into the agent ecosystem, and give MC time-awareness tools for real-time coordination.

**Architecture:** OmniFocus server plugin detects all completions and POSTs to a FastAPI Task Completion Service, which routes to the extraction loop and notifies MC. Rover manages the widget queue via a Letta tool that calls LettaBot's HTTP API. MC sets wake timers via scheduler MCP tools for time-critical monitoring.

**Tech Stack:** Python/FastAPI (completion service), JavaScript/OmniFocus Omni Automation (plugin), TypeScript/Node.js (LettaBot endpoints), Python (Letta tools), Python/FastMCP (scheduler MCP)

**Spec:** `docs/plans/2026-03-15-unified-task-completion-design.md`

---

## File Structure

### New Files
| File | Purpose |
|---|---|
| `lettabot/src/api/widget-queue.ts` | LettaBot HTTP endpoint wrapping widget-queue.sh |
| `letta/widget_queue_tool.py` | Letta tool for Rover to manage widget queue via HTTP |
| `letta/register_widget_queue_tool.py` | Registration script for widget queue tool |
| `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/manifest.json` | Plugin manifest |
| `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/watcherLib.js` | Completion detection and HTTP notification logic |
| `task-completion-service/main.py` | FastAPI service: push endpoint, MC notification, dedup |
| `task-completion-service/completion_processor.py` | Shared completion processing logic (extracted from sync tool) |
| `task-completion-service/Dockerfile` | Container build |
| `task-completion-service/requirements.txt` | Python dependencies |

### Modified Files
| File | Change |
|---|---|
| `lettabot/src/api/server.ts` | Add `/api/v1/widget-queue` route |
| `scheduler-mcp/src/scheduler_mcp/server.py` | Add `schedule_reminder` and `cancel_reminder` tools |
| `lettabot/src/config/types.ts` | Add `schedule` field to heartbeat config |
| `lettabot/src/cron/heartbeat.ts` | Self-scheduling setTimeout for dynamic intervals |
| `lettabot/lettabot.yaml` | Update heartbeat config with work/off-hours schedule |
| `docker-compose.yml` | Add task-completion-service container |

---

## Chunk 1: Rover Widget Queue Tool

### Task 1: LettaBot Widget Queue HTTP Endpoint

**Files:**
- Create: `lettabot/src/api/widget-queue.ts`
- Modify: `lettabot/src/api/server.ts`

- [ ] **Step 1: Create the widget-queue handler module**

Create `lettabot/src/api/widget-queue.ts`:

```typescript
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { createLogger } from '../logger.js';

const execFileAsync = promisify(execFile);
const log = createLogger('WidgetQueue');

import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

function getScriptPath(): string {
  // widget-queue.sh is in omnifocus-timer/ alongside the lettabot/ directory
  // __dirname resolves to lettabot/src/api/, so ../../.. gets to project root
  return process.env.WIDGET_QUEUE_SCRIPT
    || resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'omnifocus-timer', 'widget-queue.sh');
}

interface QueueRequest {
  action: string;
  task_ids?: string;
  position?: number;
}

export async function handleWidgetQueue(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  const body: QueueRequest = JSON.parse(Buffer.concat(chunks).toString());

  const { action, task_ids, position } = body;

  if (!action) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'error', error: 'action is required' }));
    return;
  }

  const validActions = ['list', 'set', 'push', 'insert', 'remove', 'move', 'clear'];
  if (!validActions.includes(action)) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'error', error: `Invalid action: ${action}. Valid: ${validActions.join(', ')}` }));
    return;
  }

  const scriptPath = getScriptPath();
  const args: string[] = [action];

  if (action === 'set' || action === 'push') {
    if (!task_ids) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'error', error: 'task_ids required for set/push' }));
      return;
    }
    args.push(...task_ids.split(',').map(id => id.trim()));
  } else if (action === 'insert') {
    if (position === undefined || !task_ids) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'error', error: 'position and task_ids required for insert' }));
      return;
    }
    args.push(String(position), task_ids.trim());
  } else if (action === 'remove') {
    if (!task_ids) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'error', error: 'task_ids required for remove' }));
      return;
    }
    args.push(task_ids.trim());
  } else if (action === 'move') {
    if (position === undefined || !task_ids) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'error', error: 'position and task_ids required for move' }));
      return;
    }
    args.push(task_ids.trim(), String(position));
  }

  try {
    log.info(`Executing: widget-queue.sh ${args.join(' ')}`);
    const { stdout, stderr } = await execFileAsync(scriptPath, args, { timeout: 10000 });
    if (stderr) log.warn(`stderr: ${stderr}`);

    let result: unknown;
    try {
      result = JSON.parse(stdout.trim());
    } catch {
      result = stdout.trim();
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', result }));
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log.error(`widget-queue.sh failed: ${msg}`);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'error', error: msg }));
  }
}
```

- [ ] **Step 2: Add route to server.ts**

In `lettabot/src/api/server.ts`, add the import at the top with other imports:

```typescript
import { handleWidgetQueue } from './widget-queue.js';
```

Add the route before the 404 fallback (before `res.writeHead(404`):

```typescript
    // Widget queue management
    if (req.url === '/api/v1/widget-queue' && req.method === 'POST') {
      if (!validateApiKey(req.headers, options.apiKey)) {
        sendError(res, 401, 'Unauthorized');
        return;
      }
      await handleWidgetQueue(req, res);
      return;
    }
```

- [ ] **Step 3: Test the endpoint manually**

Rebuild and restart LettaBot, then test:

```bash
# From the laptop where LettaBot runs:
curl -s -X POST http://localhost:8080/api/v1/widget-queue \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $(cat ~/.lettabot/api-key 2>/dev/null || echo test)" \
  -d '{"action": "list"}' | python3 -m json.tool
```

Expected: `{"status": "ok", "result": {"tasks": [...]}}`

- [ ] **Step 4: Commit**

```bash
git add lettabot/src/api/widget-queue.ts lettabot/src/api/server.ts
git commit -m "feat(lettabot): add /api/v1/widget-queue HTTP endpoint for queue management"
```

---

### Task 2: Rover Widget Queue Letta Tool

**Files:**
- Create: `letta/widget_queue_tool.py`
- Create: `letta/register_widget_queue_tool.py`

- [ ] **Step 1: Create the Letta tool**

Create `letta/widget_queue_tool.py`:

```python
from typing import Dict, Any, Optional


def manage_widget_queue(action: str, task_ids: Optional[str] = None, position: Optional[int] = None) -> Dict[str, Any]:
    """
    Manage the OmniFocus timer widget queue on the laptop.

    Controls the floating timer widget's task queue — add, remove, reorder,
    or list tasks queued for focused work sessions.

    Args:
        action: Queue operation. One of: list, set, push, insert, remove, move, clear.
            list — return current queue contents
            set — replace entire queue (task_ids: comma-separated OmniFocus task IDs)
            push — append task(s) to end, deduplicates (task_ids: comma-separated)
            insert — insert task at position (task_ids: single ID, position: 0-indexed)
            remove — remove task from queue (task_ids: single ID)
            move — move task to position (task_ids: single ID, position: 0-indexed)
            clear — empty the queue
        task_ids: Comma-separated OmniFocus task IDs. Required for set, push, insert, remove, move.
        position: Target position for insert/move (0-indexed). Required for insert, move.

    Returns:
        Dictionary with status and current queue state.
    """
    import json
    import traceback
    import os

    try:
        import requests

        lettabot_url = os.environ.get("ROVER_LETTABOT_URL", "http://100.95.213.46:8080")
        lettabot_key = os.environ.get("ROVER_LETTABOT_API_KEY", "")

        if not action or action not in ("list", "set", "push", "insert", "remove", "move", "clear"):
            return {"status": "error", "error_message": f"Invalid action: {action}. Must be one of: list, set, push, insert, remove, move, clear"}

        payload = {"action": action}
        if task_ids is not None:
            payload["task_ids"] = task_ids
        if position is not None:
            payload["position"] = position

        headers = {"Content-Type": "application/json"}
        if lettabot_key:
            headers["X-Api-Key"] = lettabot_key

        url = f"{lettabot_url.rstrip('/')}/api/v1/widget-queue"
        resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code != 200:
            return {"status": "error", "error_message": f"HTTP {resp.status_code}: {resp.text[:500]}"}

        return resp.json()

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

- [ ] **Step 2: Create the registration script**

Create `letta/register_widget_queue_tool.py`:

```python
"""Register manage_widget_queue tool with Letta and attach to Rover."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from letta_client import Letta

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
ROVER_AGENT_ID = "agent-76ee5448-68ec-4fdd-b102-d4895d44e090"

client = Letta(base_url=LETTA_BASE_URL)

# Register tool
from widget_queue_tool import manage_widget_queue
tool = client.tools.upsert_from_function(func=manage_widget_queue)
print(f"Registered tool: {tool.name} (id: {tool.id})")

# Get Rover's current tools and add this one
agent = client.agents.retrieve(agent_id=ROVER_AGENT_ID)
current_tool_ids = [t.id for t in agent.tools]
if tool.id not in current_tool_ids:
    current_tool_ids.append(tool.id)
    client.agents.modify(agent_id=ROVER_AGENT_ID, tool_ids=current_tool_ids)
    print(f"Attached to Rover ({ROVER_AGENT_ID})")
else:
    print(f"Already attached to Rover")
```

- [ ] **Step 3: Register and test**

```bash
cd /Volumes/main-drive/ai-PA
LETTA_BASE_URL=http://localhost:8283 python letta/register_widget_queue_tool.py
```

Expected: "Registered tool: manage_widget_queue" and "Attached to Rover"

- [ ] **Step 4: Verify tool works via Letta API**

```bash
curl -sL -X POST "http://localhost:8283/v1/agents/agent-76ee5448-68ec-4fdd-b102-d4895d44e090/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "List my widget queue using manage_widget_queue."}]}' \
  | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2)[:1000])"
```

Expected: Agent calls `manage_widget_queue(action="list")` and returns queue contents.

- [ ] **Step 5: Commit**

```bash
git add letta/widget_queue_tool.py letta/register_widget_queue_tool.py
git commit -m "feat(letta): add manage_widget_queue tool for Rover"
```

---

## Chunk 2: OmniFocus Completion Watcher Plugin

### Task 3: OmniFocus Completion Watcher Plugin

**Files:**
- Create: `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/manifest.json`
- Create: `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/watcherLib.js`

- [ ] **Step 1: Create the plugin manifest**

Create `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/manifest.json`:

```json
{
  "defaultLocale": "en",
  "identifier": "com.dorsey.omnifocus-completion-watcher",
  "author": "Chad Dorsey",
  "description": "Watches for task completions and pushes notifications to the Task Completion Service.",
  "version": "1.0.0",
  "actions": [
    {
      "identifier": "startWatcher",
      "label": "Start Completion Watcher",
      "shortLabel": "Start Watcher",
      "image": "eye"
    },
    {
      "identifier": "stopWatcher",
      "label": "Stop Completion Watcher",
      "shortLabel": "Stop Watcher",
      "image": "eye.slash"
    },
    {
      "identifier": "watcherStatus",
      "label": "Completion Watcher Status",
      "shortLabel": "Watcher Status",
      "image": "info.circle"
    }
  ],
  "libraries": [
    {
      "identifier": "watcherLib"
    }
  ]
}
```

- [ ] **Step 2: Create action stubs**

Create `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/startWatcher.js`:

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.startWatcher",
  "version": "1.0",
  "description": "Start the completion watcher polling timer.",
  "label": "Start Completion Watcher",
  "shortLabel": "Start Watcher"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    lib.startWatcher();
    new Alert("Completion Watcher", "Watcher started.").show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
```

Create `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/stopWatcher.js`:

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.stopWatcher",
  "version": "1.0",
  "description": "Stop the completion watcher polling timer.",
  "label": "Stop Completion Watcher",
  "shortLabel": "Stop Watcher"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    lib.stopWatcher();
    new Alert("Completion Watcher", "Watcher stopped.").show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
```

Create `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/watcherStatus.js`:

```javascript
/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.watcherStatus",
  "version": "1.0",
  "description": "Show completion watcher status.",
  "label": "Completion Watcher Status",
  "shortLabel": "Watcher Status"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    const status = lib.getStatus();
    new Alert("Completion Watcher Status", status).show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
```

- [ ] **Step 3: Create the watcher library**

Create `omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/Resources/watcherLib.js`:

```javascript
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
      events.shift(); // drop oldest
    }
    events.push(eventData);
    savePendingEvents(events);
  }

  function retryPendingEvents() {
    var events = loadPendingEvents();
    if (events.length === 0) return;

    // Process ONE event per tick to avoid race conditions
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
    // Default: 5 minutes ago (catch recent completions on first run)
    return new Date(Date.now() - 5 * 60 * 1000);
  }

  function setLastCheckTimestamp(date) {
    prefs.write(PREF_KEYS.LAST_CHECK, date.toISOString());
  }

  function findNewCompletions() {
    var lastCheck = getLastCheckTimestamp();
    var now = new Date();
    var completions = [];

    // Iterate all tasks — filter by completion date
    flattenedTasks.forEach(function (task) {
      if (!task.completed && task.taskStatus !== Task.Status.Dropped) return;

      // OmniFocus sets completionDate for both completed and dropped tasks
      var completionDate = task.completionDate;
      if (!completionDate) return;
      if (completionDate <= lastCheck) return;

      // Collect tag names
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
        // Update high-water mark only after successful send
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
    // First, retry any pending events from previous failures
    retryPendingEvents();

    // Then check for new completions
    var result = findNewCompletions();
    var completions = result.completions;
    var checkTime = result.checkTime;

    if (completions.length === 0) return;

    // Send each completion
    for (var i = 0; i < completions.length; i++) {
      var isLast = (i === completions.length - 1);
      sendCompletion(completions[i], checkTime, isLast);
    }
  }

  // ── Public API ─────────────────────────────────────────────────

  lib.startWatcher = function () {
    if (watcherTimer) return; // already running
    watcherTimer = Timer.repeating(POLL_INTERVAL_SEC, pollTick);
    prefs.write(PREF_KEYS.WATCHER_RUNNING, "true");
    console.log("[CompletionWatcher] Started (interval: " + POLL_INTERVAL_SEC + "s)");

    // Run an immediate check for orphan recovery (completions during downtime)
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

  // Auto-start if was running before OmniFocus restart.
  // Libraries don't have an onLoad hook — the code runs when the library is first loaded.
  // We auto-start immediately during library initialization.
  var wasRunning = prefs.readString(PREF_KEYS.WATCHER_RUNNING);
  if (wasRunning === "true") {
    lib.startWatcher();
  }

  return lib;
})();
```

- [ ] **Step 4: Install the plugin**

```bash
# Copy plugin to OmniFocus Plug-Ins directory
cp -r omnifocus-timer/omnifocus-completion-watcher.omnifocusjs \
  "$HOME/Library/Application Support/OmniFocus/Plug-Ins/"
```

Then in OmniFocus: Automation menu → check that "Start Completion Watcher" appears. Run it.

- [ ] **Step 5: Test completion detection**

1. In OmniFocus, create a test task "Test completion watcher"
2. Complete the task
3. Wait up to 60 seconds
4. Check if the service received the event (will fail until Task Completion Service is built — that's expected; verify the plugin's pending queue grows):

```bash
# Check OmniFocus console log for watcher output
# In OmniFocus: Automation → Console
# Look for "[CompletionWatcher] Started" and any send attempts
```

- [ ] **Step 6: Commit**

```bash
git add omnifocus-timer/omnifocus-completion-watcher.omnifocusjs/
git commit -m "feat: add OmniFocus completion watcher plugin"
```

---

## Chunk 3: Task Completion Service

### Task 4: Task Completion Service

**Files:**
- Create: `task-completion-service/main.py`
- Create: `task-completion-service/completion_processor.py`
- Create: `task-completion-service/Dockerfile`
- Create: `task-completion-service/requirements.txt`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create requirements.txt**

Create `task-completion-service/requirements.txt`:

```
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
```

- [ ] **Step 2: Create the completion processor (shared logic)**

Create `task-completion-service/completion_processor.py`:

```python
"""Shared completion processing logic.

Handles archival memory lookup, passage updates, and follow-up routing
for completed OmniFocus tasks. Used by both the push endpoint and the
reconciliation poller.
"""
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("completion-processor")

LETTA_BASE_URL = "http://letta:8283"
# Note: archive API not used — we use agent archival memory API which includes shared archives
# This is tasks-agent-sleeptime — the agent whose archival memory stores extracted task passages
TASKS_AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"


def parse_timing_from_note(note: str) -> Optional[str]:
    """Extract timing summary from Time Tracking block in task note."""
    match = re.search(
        r"--- Time Tracking ---\n(.*?)\n--- End Time Tracking ---",
        note,
        re.DOTALL,
    )
    if not match:
        return None
    block = match.group(1)
    total_match = re.search(r"Total:\s*(.+)", block)
    sessions = re.findall(r"\[.+?\]\s+\S+", block)
    summary = f"{len(sessions)} session(s)"
    if total_match:
        summary += f", {total_match.group(1).strip()} active"
    return summary


async def find_extracted_task(task_id: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Search archival memory for an extracted task passage matching this OmniFocus task ID."""
    url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory"
    resp = await client.get(url, params={"search": task_id, "limit": 20})
    if resp.status_code != 200:
        logger.error(f"Archival search failed: {resp.status_code}")
        return None

    for passage in resp.json():
        text = passage.get("text", "")
        if f"- Task ID: {task_id}" in text and "status:confirmed" in str(passage.get("tags", [])):
            return passage
    return None


async def update_passage_completed(
    passage: dict,
    completion_date: str,
    was_dropped: bool,
    client: httpx.AsyncClient,
) -> dict:
    """Update an extracted task passage to completed/dropped status.

    Returns routing metadata for follow-up actions.
    """
    text = passage["text"]
    passage_id = passage["id"]
    status_word = "DROPPED" if was_dropped else "COMPLETED"

    # Prefix TASK line
    text = re.sub(r"^(TASK:\s*)", rf"TASK: [{status_word}] ", text, count=1)

    # Update status in OMNIFOCUS section
    text = re.sub(r"- Status:\s*\w+", f"- Status: {status_word.lower()}", text)

    # Add completion timestamp
    timestamp_line = f"- {'Dropped' if was_dropped else 'Completed'}: {completion_date}"
    text = re.sub(
        r"(TIMESTAMPS\n(?:- .+\n)*)",
        rf"\g<1>{timestamp_line}\n",
        text,
    )

    # Extract routing metadata
    source_type = ""
    from_person = ""
    m = re.search(r"- Type:\s*(.+)", text)
    if m:
        source_type = m.group(1).strip()
    m = re.search(r"- From:\s*(.+)", text)
    if m:
        from_person = m.group(1).strip()
    has_external_origin = bool(from_person) and "Chad Dorsey" not in from_person

    ref_id = ""
    m = re.search(r"REF_ID:\s*(\S+)", text)
    if m:
        ref_id = m.group(1)

    # Update tags
    old_tags = passage.get("tags", [])
    new_tags = [t for t in old_tags if not t.startswith("status:")]
    new_tags.append(f"status:{status_word.lower()}")

    # Insert new passage first, then delete old (safer ordering)
    insert_url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory"
    insert_resp = await client.post(
        insert_url,
        json={"text": text, "tags": new_tags},
    )

    if insert_resp.status_code in (200, 201):
        delete_url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory/{passage_id}"
        await client.delete(delete_url)

    return {
        "ref_id": ref_id,
        "source_type": source_type,
        "from_person": from_person,
        "has_external_origin": has_external_origin,
    }


async def notify_mc(
    task_name: str,
    project_name: Optional[str],
    completion_date: str,
    timing_summary: Optional[str],
    extraction_info: Optional[dict],
    client: httpx.AsyncClient,
) -> None:
    """Send a completion notification to Mission Control."""
    lines = [f"TASK COMPLETED: '{task_name}'"]
    if project_name:
        lines.append(f"Project: {project_name}")
    lines.append(f"Completed: {completion_date}")
    if timing_summary:
        lines.append(f"Timing: {timing_summary}")
    if extraction_info:
        ref = extraction_info.get("ref_id", "")
        src = extraction_info.get("source_type", "")
        ext = extraction_info.get("has_external_origin", False)
        lines.append(f"Extraction: ref_id {ref}, source: {src}, follow-up {'pending' if ext else 'none'}")

    content = "\n".join(lines)

    url = f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}/messages/"
    resp = await client.post(
        url,
        json={"messages": [{"role": "system", "content": content}]},
        timeout=300.0,
    )
    if resp.status_code not in (200, 201):
        # Fall back to user role if system role rejected
        logger.warning(f"MC notification with system role failed ({resp.status_code}), retrying with user role")
        await client.post(
            url,
            json={"messages": [{"role": "user", "content": f"[SYSTEM NOTIFICATION] {content}"}]},
            timeout=300.0,
        )
```

- [ ] **Step 3: Create the FastAPI main app**

Create `task-completion-service/main.py`:

```python
"""Task Completion Service.

Receives push notifications from OmniFocus completion watcher plugin,
processes completions (archival updates, follow-up routing), and notifies MC.
Also provides a reconciliation endpoint and recent completions query.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from completion_processor import (
    find_extracted_task,
    update_passage_completed,
    notify_mc,
    parse_timing_from_note,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("task-completion-service")

app = FastAPI(title="Task Completion Service", version="1.0.0")

# ── State ─────────────────────────────────────────────────────────
STATE_DIR = Path(os.environ.get("STATE_DIR", "/data"))
DEDUP_FILE = STATE_DIR / "processed_completions.json"

# In-memory dedup set: {task_id: completion_date_iso}
processed: dict[str, str] = {}
# Recent completions ring buffer
recent_completions: list[dict] = []
MAX_RECENT = 50


def load_dedup_state():
    """Load dedup state from disk, prune entries older than 30 days."""
    global processed
    if DEDUP_FILE.exists():
        try:
            data = json.loads(DEDUP_FILE.read_text())
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            processed = {k: v for k, v in data.items() if v > cutoff}
        except Exception as e:
            logger.error(f"Failed to load dedup state: {e}")
            processed = {}


def save_dedup_state():
    """Persist dedup state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(processed))


@app.on_event("startup")
async def startup():
    load_dedup_state()
    logger.info(f"Loaded {len(processed)} dedup entries")


# ── Models ────────────────────────────────────────────────────────

class CompletionEvent(BaseModel):
    task_id: str
    task_name: str
    note: str = ""
    completion_date: str
    was_dropped: bool = False
    project_name: Optional[str] = None
    tags: list[str] = []


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "processed_count": len(processed), "recent_count": len(recent_completions)}


@app.post("/v1/completion")
async def receive_completion(event: CompletionEvent):
    """Receive a completion notification from the OmniFocus plugin."""

    # Dedup check
    if event.task_id in processed:
        logger.info(f"Duplicate completion for {event.task_id}, skipping")
        return {"status": "ok", "action": "duplicate_skipped"}

    logger.info(f"Processing completion: {event.task_name} ({event.task_id})")

    async with httpx.AsyncClient() as client:
        # Check if this is an extracted task
        extraction_info = None
        passage = await find_extracted_task(event.task_id, client)
        if passage:
            logger.info(f"Found extracted task passage for {event.task_id}")
            extraction_info = await update_passage_completed(
                passage, event.completion_date, event.was_dropped, client
            )

        # Parse timing data from note
        timing_summary = parse_timing_from_note(event.note) if event.note else None

        # Record completion
        record = {
            "task_id": event.task_id,
            "task_name": event.task_name,
            "completion_date": event.completion_date,
            "was_dropped": event.was_dropped,
            "project_name": event.project_name,
            "timing": timing_summary,
            "is_extracted": passage is not None,
            "extraction_info": extraction_info,
        }
        recent_completions.append(record)
        if len(recent_completions) > MAX_RECENT:
            recent_completions.pop(0)

        # Mark as processed
        processed[event.task_id] = event.completion_date
        save_dedup_state()

        # Notify MC
        await notify_mc(
            event.task_name,
            event.project_name,
            event.completion_date,
            timing_summary,
            extraction_info,
            client,
        )

    action = "processed_extracted" if passage else "processed_standalone"
    return {"status": "ok", "action": action}


@app.get("/v1/completions/recent")
async def get_recent_completions(limit: int = 20):
    """Query recent completions."""
    return {"completions": recent_completions[-limit:]}
```

- [ ] **Step 4: Create Dockerfile**

Create `task-completion-service/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8092"]
```

- [ ] **Step 5: Add to docker-compose.yml**

Add after the `cli-proxy-api` service block:

```yaml
  # Task Completion Service — receives push notifications from OmniFocus completion watcher
  task-completion-service:
    build: ./task-completion-service
    container_name: task-completion-service
    restart: unless-stopped
    ports:
      - "8092:8092"
    volumes:
      - task-completion-data:/data
    networks: [pa-internal]
    environment:
      STATE_DIR: /data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:8092/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    labels:
      - "com.ai-pa.service=task-completion-service"
      - "com.ai-pa.component=completion-service"
      - "com.ai-pa.network=internal"
```

Add to the `volumes:` section at the bottom of docker-compose.yml:

```yaml
  task-completion-data:
```

- [ ] **Step 6: Stop the old sync service and build the new one**

The existing `scripts/omnifocus_sync_service.py` also runs on port 8092 (as a launchd service). Stop it first:

```bash
# Stop existing sync service (if running via launchd)
launchctl unload ~/Library/LaunchAgents/com.ai-pa.omnifocus-sync-service.plist 2>/dev/null || true
# Or kill directly
lsof -ti :8092 | xargs kill 2>/dev/null || true

docker compose up -d --build task-completion-service
```

Expected: Service starts, health check passes.

```bash
curl -s http://localhost:8092/health | python3 -m json.tool
```

Expected: `{"status": "ok", "processed_count": 0, "recent_count": 0}`

- [ ] **Step 7: Test end-to-end with a manual POST**

```bash
curl -s -X POST http://localhost:8092/v1/completion \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-task-123",
    "task_name": "Test completion notification",
    "note": "",
    "completion_date": "2026-03-15T16:00:00Z",
    "was_dropped": false,
    "project_name": "Testing",
    "tags": ["test"]
  }' | python3 -m json.tool
```

Expected: `{"status": "ok", "action": "processed_standalone"}` and MC receives a notification message.

```bash
# Verify recent completions endpoint
curl -s http://localhost:8092/v1/completions/recent | python3 -m json.tool
```

- [ ] **Step 8: Test deduplication**

```bash
# Send the same completion again
curl -s -X POST http://localhost:8092/v1/completion \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-task-123",
    "task_name": "Test completion notification",
    "completion_date": "2026-03-15T16:00:00Z"
  }' | python3 -m json.tool
```

Expected: `{"status": "ok", "action": "duplicate_skipped"}`

- [ ] **Step 9: Commit**

```bash
git add task-completion-service/ docker-compose.yml
git commit -m "feat: add Task Completion Service for push-based completion detection"
```

---

## Chunk 4: Scheduler MCP Wake Timers

### Task 5: Merge Wake Timer Tools into Scheduler MCP

**Files:**
- Modify: `scheduler-mcp/src/scheduler_mcp/server.py`

- [ ] **Step 1: Read the v2 tool pattern**

Read `scheduler-mcp/src/scheduler_mcp/server_v2.py` to see how `schedule_reminder` builds raw dict payloads instead of using Pydantic models from `tools.py`. The models (`ActionModel`, `ScheduleModel`, `JobCreateModel`) have strict schemas (`extra="forbid"`, required fields like `action_id`) that don't fit the reminder use case. We'll follow the v2 pattern of raw dicts passed directly to `client.create_job()`.

- [ ] **Step 2: Add schedule_reminder tool to server.py**

Add after the last existing tool (`scheduler_search_jobs`) and before `create_app()`:

```python
@mcp.tool(description="""Schedule a one-shot reminder/wake-up message to be delivered to a Letta agent at a specified time.

Use natural language for timing: "in 30 minutes", "at 1:45pm", "tomorrow at 9am".
The message will be delivered as a system message to the specified agent via the Letta API.

This is designed for agent self-scheduling: set wake timers for time-critical monitoring,
meeting prep, or session checkpoints. The job auto-completes after delivery.""")
async def schedule_reminder(
    when: str,
    message: str,
    agent_id: str,
    title: Optional[str] = None,
    created_by: Optional[str] = None,
    category: Optional[str] = "wake-timer",
) -> Dict[str, Any]:
    """Schedule a reminder message to an agent.

    Args:
        when: Natural language time expression (e.g., "in 20 minutes", "at 1:45pm")
        message: Context message delivered to the agent when the timer fires
        agent_id: Target Letta agent ID to receive the message
        title: Optional job title (defaults to "Wake timer: <truncated message>")
        created_by: Who created this reminder (defaults to agent_id)
        category: Job category (defaults to "wake-timer")
    """
    try:
        client = await _get_client()

        if not title:
            title = f"Wake timer: {message[:60]}{'...' if len(message) > 60 else ''}"
        if not created_by:
            created_by = agent_id

        # Build raw dict payload — bypasses Pydantic models whose strict schemas
        # (action_id required, expression must be Dict) don't fit the reminder use case.
        # This matches the pattern in server_v2.py.
        job_data = {
            "title": title,
            "description": f"Reminder: {message}",
            "created_by": created_by,
            "schedule": {
                "type": "natural",
                "expression": when,
                "timezone": "America/New_York",
            },
            "actions": [
                {
                    "action_type": "agent_message",
                    "config": {
                        "agent_id": agent_id,
                        "message": message,
                    },
                }
            ],
        }

        if category:
            job_data["metadata"] = [{"key": "category", "value": {"category": category}}]

        result = await client.create_job(job_data)
        return {
            "success": True,
            "job_id": result.get("job_id"),
            "message": f"Reminder scheduled: {title}",
            "next_run_at": result.get("next_run_at"),
            "created_by": created_by,
            "recipient": agent_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(description="Cancel a previously scheduled reminder or wake timer by job ID.")
async def cancel_reminder(
    job_id: str,
) -> Dict[str, Any]:
    """Cancel a scheduled reminder.

    Args:
        job_id: The job ID returned by schedule_reminder
    """
    try:
        client = await _get_client()
        await client.delete_job(job_id)
        return {"success": True, "message": f"Reminder {job_id} cancelled"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 3: Verify the import for ScheduleModel, ActionModel, JobCreateModel**

Check that `scheduler_mcp/tools.py` exports these models. If the names differ, adjust the import in step 2. Run:

```bash
cd scheduler-mcp && grep -n "class.*Model" src/scheduler_mcp/tools.py
```

- [ ] **Step 4: Restart scheduler-mcp and verify tools appear**

```bash
docker compose up -d --build scheduler-mcp
# Wait a moment, then check health
curl -s http://localhost:8088/health
```

- [ ] **Step 5: Test schedule_reminder end-to-end**

Create a wake timer that fires in 1 minute targeting MC:

```bash
# Via the Letta agent that has scheduler tools attached, or directly via API:
curl -s -X POST http://localhost:8088/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "schedule_reminder",
      "arguments": {
        "when": "in 1 minute",
        "message": "Test wake timer — if you see this, the timer system works.",
        "agent_id": "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
      }
    }
  }'
```

Wait 1 minute, then check MC's messages:

```bash
docker logs ai-pa-letta-1 --since 2m 2>&1 | grep -i "wake timer\|Test wake"
```

- [ ] **Step 6: Commit**

```bash
git add scheduler-mcp/src/scheduler_mcp/server.py
git commit -m "feat(scheduler-mcp): add schedule_reminder and cancel_reminder tools for agent wake timers"
```

---

## Chunk 5: Dynamic Heartbeat & Cleanup

### Task 6: Dynamic Heartbeat Scheduling

**Files:**
- Modify: `lettabot/src/config/types.ts`
- Modify: `lettabot/src/cron/heartbeat.ts`
- Modify: `lettabot/lettabot.yaml`

- [ ] **Step 1: Add schedule types to config**

In `lettabot/src/config/types.ts`, add after the `HeartbeatSkipRecentPolicy` type (line 14):

```typescript
export interface HeartbeatSchedule {
  workHours?: {
    start: number;  // hour (0-23), default 8
    end: number;    // hour (0-23), default 18
    intervalMin: number;  // default 10
  };
  offHours?: {
    intervalMin: number;  // default 60
  };
}
```

In the heartbeat config block within `AgentConfig.features` (around line 88), add the `schedule` field:

```typescript
schedule?: HeartbeatSchedule;
```

Do the same in `LettaBotConfig.features` (around line 188).

- [ ] **Step 2: Modify HeartbeatService for dynamic intervals**

In `lettabot/src/cron/heartbeat.ts`, modify the `HeartbeatConfig` interface (line 47) to add:

```typescript
schedule?: {
  workHours?: { start: number; end: number; intervalMin: number };
  offHours?: { intervalMin: number };
};
```

Replace the `start()` method (lines 186-210) with self-scheduling logic:

```typescript
start(): void {
  if (!this.config.enabled) {
    log.info('Disabled');
    return;
  }

  if (this.intervalId) {
    log.info('Already running');
    return;
  }

  log.info(`Starting in SILENT MODE (dynamic scheduling)`);
  this.scheduleNext();

  logEvent('heartbeat_started', {
    schedule: this.config.schedule || { fixed: this.config.intervalMinutes },
    mode: 'silent',
  });
}

private getIntervalForCurrentHour(): number {
  const schedule = this.config.schedule;
  if (!schedule) return this.config.intervalMinutes;

  const hour = new Date().getHours();
  const workStart = schedule.workHours?.start ?? 8;
  const workEnd = schedule.workHours?.end ?? 18;

  if (hour >= workStart && hour < workEnd) {
    return schedule.workHours?.intervalMin ?? this.config.intervalMinutes;
  }
  return schedule.offHours?.intervalMin ?? 60;
}

private scheduleNext(): void {
  const intervalMin = this.getIntervalForCurrentHour();
  const intervalMs = intervalMin * 60 * 1000;

  log.info(`Next heartbeat in ${intervalMin} minutes`);

  this.intervalId = setTimeout(async () => {
    await this.runHeartbeat();
    this.intervalId = null;
    this.scheduleNext(); // self-reschedule with potentially different interval
  }, intervalMs);
}
```

Update the `stop()` method to handle `setTimeout` (it uses `clearInterval` currently — `clearTimeout` works the same way for `setTimeout`):

```typescript
stop(): void {
  if (this.intervalId) {
    clearTimeout(this.intervalId);
    this.intervalId = null;
    log.info('Stopped');
  }
}
```

- [ ] **Step 3: Update lettabot.yaml with dynamic schedule**

In `lettabot/lettabot.yaml`, update the heartbeat config:

```yaml
features:
  disallowedTools:
    - Task
  cron: false
  heartbeat:
    enabled: true
    intervalMin: 15          # fallback if schedule not set
    skipRecentUserMin: 5
    schedule:
      workHours:
        start: 8
        end: 18
        intervalMin: 10
      offHours:
        intervalMin: 60
```

- [ ] **Step 4: Wire schedule config through to HeartbeatService**

In `lettabot/src/main.ts`, where `HeartbeatService` is instantiated (around line 493), add the `schedule` field:

```typescript
schedule: heartbeatConfig?.schedule,
```

- [ ] **Step 5: Test**

Rebuild LettaBot and verify logs show dynamic scheduling:

```bash
# Check LettaBot logs
tail -f /tmp/lettabot.log | grep -i heartbeat
```

Expected: "Next heartbeat in 10 minutes" (during work hours) or "Next heartbeat in 60 minutes" (off-hours).

- [ ] **Step 6: Commit**

```bash
git add lettabot/src/config/types.ts lettabot/src/cron/heartbeat.ts lettabot/lettabot.yaml lettabot/src/main.ts
git commit -m "feat(lettabot): add dynamic heartbeat scheduling (work hours vs off-hours)"
```

---

### Task 7: Reduce Reconciliation Polling Frequency

**Files:**
- No code changes — scheduler configuration only

- [ ] **Step 1: Verify the completion watcher plugin and service are both running**

```bash
# Check service health
curl -s http://localhost:8092/health | python3 -m json.tool

# Check recent completions have been flowing
curl -s http://localhost:8092/v1/completions/recent | python3 -m json.tool
```

- [ ] **Step 2: Update the sync cron job schedule**

Check current sync job in the scheduler:

```bash
curl -s "http://localhost:8087/v1/jobs?category_filter=omnifocus-sync" \
  -H "x-api-key: ${SCHEDULER_API_KEY}" | python3 -m json.tool
```

If found, update its schedule to every 2 hours:

```bash
curl -s -X PATCH "http://localhost:8087/v1/jobs/{JOB_ID}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${SCHEDULER_API_KEY}" \
  -d '{"schedule": {"type": "cron", "expression": {"cron": "0 */2 * * *"}}}'
```

- [ ] **Step 3: Verify no completions are missed**

Over 24 hours, compare:
- Completions caught by push service (`GET /v1/completions/recent`)
- Completions caught by reconciliation poll (check execution logs)

If push service catches everything, the reconciliation poll is confirmed as backup-only.

- [ ] **Step 4: Commit (if any config files changed)**

```bash
git add -A && git commit -m "chore: reduce reconciliation polling to every 2 hours (push-based is primary)"
```

---

## Execution Notes

### Dependencies Between Tasks

```
Task 1 (LettaBot endpoint) ──→ Task 2 (Letta tool) [tool calls endpoint]
Task 3 (OF plugin) ──→ Task 4 (Completion Service) [plugin POSTs to service]
Task 5 (Scheduler MCP) ── independent
Task 6 (Dynamic heartbeat) ── independent
Task 7 (Reconciliation reduction) ── depends on Tasks 3+4 being stable
```

Tasks 1+2, 3+4, 5, and 6 can be worked in parallel.
Task 7 should be done last, after verifying the push path is reliable.

### Testing Strategy

- **Task 1+2:** Manual curl to LettaBot endpoint, then Letta agent tool call
- **Task 3:** Manual OmniFocus completion + wait for plugin POST (check pending queue until service is up)
- **Task 4:** Manual POST to service, then end-to-end with plugin
- **Task 5:** Create a 1-minute wake timer, verify MC receives message
- **Task 6:** Check logs for dynamic interval selection
- **Task 7:** Compare push vs poll catches over 24 hours

### Rollback

Each component is independent. If any component has issues:
- Widget queue tool: detach from Rover via Letta API
- Completion plugin: stop watcher via OmniFocus Automation menu
- Completion service: `docker compose stop task-completion-service`
- Wake timers: tools are additive, existing scheduler tools unaffected
- Dynamic heartbeat: revert `lettabot.yaml` to fixed `intervalMin: 30`
