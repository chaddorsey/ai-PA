# OmniFocus Sync Standalone Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract the deterministic OmniFocus completion sync logic from a Letta agent tool into a standalone host-based HTTP service that silently syncs, only sending Slack notifications for external-origin task completions.

**Architecture:** Host-based Python HTTP service (port 8091) using stdlib `http.server` + `httpx`. Scheduler-service fires `POST /v1/sync` via webhook cron jobs. Service queries Letta archival for `status:confirmed` passages, batch-checks OmniFocus bridge (localhost:8889), transitions passages, and conditionally POSTs to slackbot `/api/notify` for external-origin completions.

**Tech Stack:** Python 3.11+, httpx, stdlib http.server (no FastAPI — matching Granola ingest pattern)

**Design Doc:** `docs/plans/2026-02-25-omnifocus-sync-standalone-service-design.md`

---

### Task 1: Create the sync service scaffold

**Files:**
- Create: `scripts/omnifocus_sync_service.py`

**Step 1: Create the HTTP service skeleton**

Model this after `scripts/granola_ingest_service.py` which uses `http.server.HTTPServer` + `BaseHTTPRequestHandler`.

```python
#!/usr/bin/env python3
"""
OmniFocus Completion Sync Service

Standalone HTTP service that polls OmniFocus for completed tasks and
updates their Letta archival records. Sends Slack notifications only
for external-origin task completions.

Endpoints:
    POST /v1/sync    — Run sync (scheduler webhook target)
    GET  /v1/status  — Last run info
    GET  /health     — Health check

Usage:
    python scripts/omnifocus_sync_service.py              # port 8091
    python scripts/omnifocus_sync_service.py --port 8092  # custom port
"""

import argparse
import json
import logging
import os
import re
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import httpx

DEFAULT_PORT = 8091
STATE_DIR = Path.home() / ".omnifocus-sync"

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"
BRIDGE_URL = "http://localhost:8889"
SLACKBOT_URL = "http://localhost:8081"
USER_NAME = "Chad Dorsey"
NOTIFIED_EXPIRY_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Concurrency guard and run state
_sync_lock = threading.Lock()
_last_result = None
_last_run_time = None
_start_time = time.time()


class SyncHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the sync service."""

    def do_POST(self):
        if self.path == "/v1/sync":
            logger.info("Sync triggered")
            result = run_sync()
            self._json_response(200, result)
        else:
            self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        if self.path == "/health":
            self._json_response(200, {"status": "healthy"})
        elif self.path == "/v1/status":
            self._json_response(200, {
                "status": "ok",
                "last_run_result": _last_result,
                "last_run_time": _last_run_time,
                "uptime_seconds": round(time.time() - _start_time),
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status_code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        logger.debug(f"{self.client_address[0]} - {format % args}")


def run_sync() -> dict:
    """Placeholder — implemented in Task 2."""
    return {"status": "ok", "checked": 0, "completed": 0, "dropped": 0, "not_found": 0, "details": []}


def main():
    parser = argparse.ArgumentParser(description="OmniFocus completion sync service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("0.0.0.0", args.port), SyncHandler)
    logger.info(f"OmniFocus sync service listening on port {args.port}")
    logger.info(f"  POST /v1/sync    — run sync")
    logger.info(f"  GET  /v1/status  — check state")
    logger.info(f"  GET  /health     — health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
```

**Step 2: Verify the scaffold starts and serves requests**

Run:
```bash
python scripts/omnifocus_sync_service.py &
sleep 2
curl -s http://localhost:8091/health | python -m json.tool
curl -s http://localhost:8091/v1/status | python -m json.tool
curl -s -X POST http://localhost:8091/v1/sync | python -m json.tool
kill %1
```

Expected: Three JSON responses — health returns `{"status": "healthy"}`, status returns `last_run_result: null`, sync returns the placeholder with all zeros.

**Step 3: Commit**

```bash
git add scripts/omnifocus_sync_service.py
git commit -m "feat: scaffold OmniFocus sync standalone service"
```

---

### Task 2: Implement the core sync logic

**Files:**
- Modify: `scripts/omnifocus_sync_service.py`

**Reference:** The sync logic is extracted from `letta/sync_omnifocus_completions_tool.py`. The key differences from the Letta tool version:
- Uses `httpx` instead of `urllib.request` (consistent with host-based services)
- Uses `http://localhost:8283` and `http://localhost:8889` (not `host.docker.internal`)
- Adds notification dedup tracking via `notified.json`

**Step 1: Implement `run_sync()` function**

Replace the placeholder `run_sync()` with the full implementation. The logic follows these steps:

1. **Query Letta archival** for `status:confirmed` passages via agent archival memory substring search (`/v1/agents/{AGENT_ID}/archival-memory?search=Status%3A%20confirmed&limit=200`)
2. **Filter** to passages that have both `"- Status: confirmed"` in text AND `"status:confirmed"` in tags
3. **Extract** OmniFocus task IDs, ref_ids, and source metadata from passage text using regex patterns:
   - `REF_ID: (\S+)` for ref_id
   - `- Task ID: (\S+)` for OmniFocus task ID
   - `- Type: (.+)$` for source_type
   - `- From: (.+)$` for from_person
   - `^TASK: (.+)$` for task description
4. **Batch-check OmniFocus** via bridge POST to `{BRIDGE_URL}/execute` with `{"command": "checkTaskCompletionStatus", "args": {"taskIds": [...]}}`
5. **Handle bridge double-encoding**: result may be `{"success": true, "result": "<json-string>"}` — parse `result` if string
6. **Transition each completed/dropped task**: insert new passage with updated status/tags/timestamps, then delete old passage
7. **Extract SOURCE TEXT** from passage for notification context
8. **Return** result dict with counts and details

Key patterns from the existing tool to preserve exactly:
- Passage text mutation: `TASK:` prefix with `[COMPLETED]`/`[DROPPED]`, timestamp insertion into `TIMESTAMPS` section, `- Status:` field update
- Tag mutation: remove old `status:*` tag, add new `status:completed`/`status:dropped`
- Insert-then-delete order for crash safety

```python
def run_sync() -> dict:
    """Run the OmniFocus completion sync."""
    global _last_result, _last_run_time

    if not _sync_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Sync already in progress"}

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/New_York")
        iso_timestamp = datetime.now(tz).isoformat()

        # ── Step 1: Find confirmed passages ──
        search_url = (
            f"{LETTA_BASE_URL}/v1/agents/{AGENT_ID}/archival-memory"
            f"?search=Status%3A%20confirmed&limit=200"
        )
        with httpx.Client(timeout=30) as client:
            resp = client.get(search_url)
            resp.raise_for_status()
            search_results = resp.json()

        confirmed_passages = []
        for p in search_results:
            text = p.get("text", "")
            tags = p.get("tags", [])
            if "- Status: confirmed" in text and "status:confirmed" in tags:
                confirmed_passages.append(p)

        if not confirmed_passages:
            result = _make_result(0, 0, 0, 0, [])
            _last_result = result
            _last_run_time = time.time()
            return result

        # ── Step 2: Extract task IDs and metadata ──
        task_map = {}
        for p in confirmed_passages:
            text = p.get("text", "")
            ref_match = re.search(r"REF_ID: (\S+)", text)
            task_id_match = re.search(r"- Task ID: (\S+)", text)
            if ref_match and task_id_match:
                of_id = task_id_match.group(1)
                ref_id = ref_match.group(1)
                if of_id != "pending":
                    source_type_match = re.search(r"- Type: (.+)$", text, re.MULTILINE)
                    from_person_match = re.search(r"- From: (.+)$", text, re.MULTILINE)
                    task_desc_match = re.search(r"^TASK: (.+)$", text, re.MULTILINE)
                    source_text_match = re.search(r"SOURCE TEXT\n(.*)", text, re.DOTALL)
                    location_match = re.search(r"^- Location: (.+)$", text, re.MULTILINE)
                    reference_id_match = re.search(r"^- Reference ID: (.+)$", text, re.MULTILINE)

                    source_type = source_type_match.group(1).strip() if source_type_match else ""
                    from_person = from_person_match.group(1).strip() if from_person_match else ""
                    task_desc = task_desc_match.group(1).strip() if task_desc_match else ""
                    source_text = source_text_match.group(1).strip() if source_text_match else ""
                    location = location_match.group(1).strip() if location_match else ""
                    reference_id = reference_id_match.group(1).strip() if reference_id_match else ""

                    task_map[of_id] = {
                        "ref_id": ref_id,
                        "passage_id": p.get("id", ""),
                        "text": text,
                        "tags": p.get("tags", []),
                        "source_type": source_type,
                        "from_person": from_person,
                        "task_description": task_desc,
                        "source_text": source_text,
                        "location": location,
                        "reference_id": reference_id,
                        "has_external_origin": bool(from_person and USER_NAME not in from_person),
                    }

        if not task_map:
            result = _make_result(0, 0, 0, 0, [])
            _last_result = result
            _last_run_time = time.time()
            return result

        # ── Step 3: Batch-check OmniFocus ──
        with httpx.Client(timeout=30) as client:
            bridge_resp = client.post(
                f"{BRIDGE_URL}/execute",
                json={
                    "command": "checkTaskCompletionStatus",
                    "args": {"taskIds": list(task_map.keys())},
                },
            )
            bridge_resp.raise_for_status()
            bridge_data = bridge_resp.json()

        if not bridge_data.get("success"):
            result = {
                "status": "error",
                "checked": len(task_map), "completed": 0, "dropped": 0, "not_found": 0,
                "details": [],
                "error_message": f"Bridge call failed: {bridge_data.get('error', 'unknown')}",
            }
            _last_result = result
            _last_run_time = time.time()
            return result

        # Handle double-encoded bridge response
        raw_result = bridge_data.get("result", {})
        if isinstance(raw_result, str):
            parsed = json.loads(raw_result)
            completion_statuses = parsed.get("result", parsed)
        elif isinstance(raw_result, dict):
            completion_statuses = raw_result.get("result", raw_result)
        else:
            completion_statuses = {}

        # ── Step 4: Transition completed/dropped tasks ──
        completed_count = 0
        dropped_count = 0
        not_found_count = 0
        details = []

        for of_id, status in completion_statuses.items():
            info = task_map.get(of_id)
            if not info:
                continue

            is_completed = status.get("completed", False)
            is_dropped = status.get("dropped", False)
            is_not_found = status.get("notFound", False)

            if not (is_completed or is_dropped or is_not_found):
                continue

            if is_not_found:
                action = "not_found_in_omnifocus"
                not_found_count += 1
            elif is_dropped:
                action = "dropped"
                dropped_count += 1
            else:
                action = "completed"
                completed_count += 1

            # Mutate passage text
            old_text = info["text"]
            old_tags = list(info["tags"])
            passage_id = info["passage_id"]
            ref_id = info["ref_id"]
            new_text = old_text

            # Prefix TASK line
            prefix = "[COMPLETED]" if (is_completed or is_not_found) else "[DROPPED]"
            task_line_match = re.search(r"^TASK: (.+)$", new_text, re.MULTILINE)
            if task_line_match:
                desc = task_line_match.group(1)
                if not desc.startswith("[COMPLETED]") and not desc.startswith("[DROPPED]"):
                    new_text = re.sub(
                        r"^TASK: .+$",
                        f"TASK: {prefix} {desc}",
                        new_text, count=1, flags=re.MULTILINE,
                    )

            # Add timestamp
            timestamp_label = "Completed" if (is_completed or is_not_found) else "Dropped"
            completion_date = status.get("completionDate") or iso_timestamp
            new_text = re.sub(
                r"(TIMESTAMPS\n(?:- .+\n)*)",
                lambda m: m.group(0) + f"- {timestamp_label}: {completion_date}\n",
                new_text, count=1,
            )

            # Update OMNIFOCUS status
            new_status = "completed" if (is_completed or is_not_found) else "dropped"
            new_text = re.sub(
                r"- Status: (extracted|confirmed)",
                f"- Status: {new_status}",
                new_text,
            )

            # Update tags
            new_tags = [t for t in old_tags if not t.startswith("status:")]
            new_tags.append(f"status:{new_status}")

            # Insert new passage, then delete old
            with httpx.Client(timeout=30) as client:
                ins_resp = client.post(
                    f"{LETTA_BASE_URL}/v1/archives/{ARCHIVE_ID}/passages",
                    json={"text": new_text, "tags": new_tags},
                )
                ins_resp.raise_for_status()
                new_passage_id = ins_resp.json().get("id", "")

                client.delete(
                    f"{LETTA_BASE_URL}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}",
                )

            details.append({
                "ref_id": ref_id,
                "omnifocus_id": of_id,
                "action": action,
                "task_name": status.get("name", ""),
                "new_passage_id": new_passage_id,
                "source_type": info.get("source_type", ""),
                "from_person": info.get("from_person", ""),
                "has_external_origin": info.get("has_external_origin", False),
                "task_description": info.get("task_description", ""),
                "source_text": info.get("source_text", ""),
                "location": info.get("location", ""),
                "reference_id": info.get("reference_id", ""),
            })

        result = _make_result(len(task_map), completed_count, dropped_count, not_found_count, details)
        _last_result = result
        _last_run_time = time.time()
        return result

    except Exception as e:
        import traceback
        logger.error("Sync failed: %s", e, exc_info=True)
        result = {
            "status": "error",
            "checked": 0, "completed": 0, "dropped": 0, "not_found": 0,
            "details": [],
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
        _last_result = result
        _last_run_time = time.time()
        return result

    finally:
        _sync_lock.release()


def _make_result(checked, completed, dropped, not_found, details):
    return {
        "status": "ok",
        "checked": checked,
        "completed": completed,
        "dropped": dropped,
        "not_found": not_found,
        "details": details,
        "error_message": "",
    }
```

**Step 2: Test with the service running**

Run:
```bash
python scripts/omnifocus_sync_service.py &
sleep 2
curl -s -X POST http://localhost:8091/v1/sync | python -m json.tool
kill %1
```

Expected: Returns `{"status": "ok", "checked": 0, ...}` (0 checked because there are likely no `status:confirmed` passages currently). If the bridge is unavailable, returns a clean error about the bridge. The service should NOT crash.

**Step 3: Commit**

```bash
git add scripts/omnifocus_sync_service.py
git commit -m "feat: implement core OmniFocus sync logic in standalone service"
```

---

### Task 3: Add notification dedup tracking

**Files:**
- Modify: `scripts/omnifocus_sync_service.py`

**Step 1: Add load/save/check functions for notified.json**

Add these helper functions near the top of the file (after the constants, before `SyncHandler`):

```python
def _load_notified() -> dict:
    """Load the notified ref_id tracking file."""
    path = STATE_DIR / "notified.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_notified(notified: dict) -> None:
    """Save the notified ref_id tracking file, pruning old entries."""
    cutoff = time.time() - (NOTIFIED_EXPIRY_DAYS * 86400)
    pruned = {k: v for k, v in notified.items() if v > cutoff}
    path = STATE_DIR / "notified.json"
    path.write_text(json.dumps(pruned, indent=2))


def _is_already_notified(ref_id: str) -> bool:
    """Check if a ref_id has already been notified."""
    notified = _load_notified()
    return ref_id in notified


def _mark_notified(ref_id: str) -> None:
    """Mark a ref_id as notified."""
    notified = _load_notified()
    notified[ref_id] = time.time()
    _save_notified(notified)
```

**Step 2: Test the dedup helpers manually**

Run in a Python shell:
```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from omnifocus_sync_service import _load_notified, _save_notified, _mark_notified, _is_already_notified, STATE_DIR
STATE_DIR.mkdir(exist_ok=True)
assert not _is_already_notified('test123')
_mark_notified('test123')
assert _is_already_notified('test123')
print('Dedup tracking works')
"
```

Expected: Prints "Dedup tracking works"

**Step 3: Commit**

```bash
git add scripts/omnifocus_sync_service.py
git commit -m "feat: add notification dedup tracking for sync service"
```

---

### Task 4: Add Slack notification posting

**Files:**
- Modify: `scripts/omnifocus_sync_service.py`

**Step 1: Add the notification function**

This function POSTs to the slackbot's `/api/notify` endpoint (defined in `slackbot/health_check.py:43-173`). The endpoint accepts:
- `text` (string) — main notification text
- `detail` (string) — context block content (rendered as Slack context elements — small gray text)
- `suggested_reply` (string) — pre-filled reply text (shown as quote block)
- `originating_agent_id` (string) — agent ID for routing button clicks
- `reply_context` (dict) — routing metadata stored in Supabase `pending_agent_replies`
- `user_slack_id` (string, optional) — defaults to `OWNER_SLACK_USER_ID` env var

```python
def _send_slack_notification(detail: dict) -> bool:
    """
    Send a Slack notification for an external-origin task completion.

    Posts to slackbot /api/notify which creates a pending_agent_reply
    and renders Block Kit with [Send Reply] [Modify] [Skip] buttons.

    Returns True if notification was sent successfully.
    """
    ref_id = detail["ref_id"]

    if _is_already_notified(ref_id):
        logger.info("Skipping duplicate notification for ref_id=%s", ref_id)
        return False

    action = detail["action"]
    is_dropped = action == "dropped"
    task_desc = detail.get("task_description", "")
    # Strip [COMPLETED]/[DROPPED] prefix if present
    task_desc = re.sub(r"^\[(COMPLETED|DROPPED)\]\s*", "", task_desc)

    from_person = detail.get("from_person", "")
    source_type = detail.get("source_type", "")
    source_text = detail.get("source_text", "")
    location = detail.get("location", "")
    reference_id = detail.get("reference_id", "")

    # Build main text
    if is_dropped:
        main_text = f":warning: *Task DROPPED in OmniFocus*\n\n*{task_desc}*"
        reply_template = "Thanks"
    else:
        main_text = f":white_check_mark: *Task completed in OmniFocus*\n\n*{task_desc}*"
        reply_template = "Done."

    # Build context detail (small gray text in Slack)
    context_parts = []
    if from_person:
        context_parts.append(f"From: {from_person}")

    # Format source type for display
    source_labels = {
        "google-docs-comment": "Google Doc comment",
        "google-drive-comment": "Google Doc comment",
        "slack": "Slack message",
        "email": "Email",
        "meeting": "Meeting notes",
    }
    source_label = source_labels.get(source_type, source_type)
    if location and source_label:
        context_parts.append(f"Source: {source_label} on {location}")
    elif source_label:
        context_parts.append(f"Source: {source_label}")

    if source_text:
        # Truncate long source text
        truncated = source_text[:300]
        if len(source_text) > 300:
            truncated += "..."
        context_parts.append(f"\"{truncated}\"")

    context_detail = "\n".join(context_parts)

    # Build reply_context for button routing
    # This gets stored in pending_agent_replies and used by
    # notification_actions.py when user clicks [Send Reply]
    reply_context = {
        "ref_id": ref_id,
        "source_type": source_type,
        "from_person": from_person,
        "reference_id": reference_id,
        "reply_template": reply_template,
        "routing_tool": "prepare_completion_feedback",
        "routing_args": {
            "ref_id": ref_id,
        },
    }

    payload = {
        "text": main_text,
        "detail": context_detail,
        "suggested_reply": reply_template,
        "originating_agent_id": AGENT_ID,
        "reply_context": reply_context,
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"{SLACKBOT_URL}/api/notify", json=payload)
            resp.raise_for_status()
            result = resp.json()

        if result.get("ok"):
            _mark_notified(ref_id)
            logger.info(
                "Slack notification sent: ref_id=%s action=%s pending_id=%s",
                ref_id, action, result.get("pending_reply_id", ""),
            )
            return True
        else:
            logger.warning(
                "Slack notification failed: ref_id=%s error=%s",
                ref_id, result.get("error", "unknown"),
            )
            return False

    except Exception as e:
        logger.error("Failed to send Slack notification for ref_id=%s: %s", ref_id, e)
        return False
```

**Step 2: Wire notifications into `run_sync()`**

At the end of the `run_sync()` function, after the `for of_id, status in completion_statuses.items()` loop (right before building the final result), add notification dispatch:

```python
        # ── Step 5: Send Slack notifications for external-origin completions ──
        notified_count = 0
        for detail in details:
            if detail.get("has_external_origin"):
                if _send_slack_notification(detail):
                    notified_count += 1
            else:
                logger.info(
                    "Skipping notification for self-originated task: ref_id=%s",
                    detail["ref_id"],
                )

        logger.info(
            "Sync complete: checked=%d completed=%d dropped=%d not_found=%d notified=%d",
            len(task_map), completed_count, dropped_count, not_found_count, notified_count,
        )
```

**Step 3: Verify the service starts without import errors**

Run:
```bash
python -c "import scripts.omnifocus_sync_service" 2>&1 || python scripts/omnifocus_sync_service.py --help
```

Expected: No import errors.

**Step 4: Commit**

```bash
git add scripts/omnifocus_sync_service.py
git commit -m "feat: add Slack notification posting for external-origin completions"
```

---

### Task 5: Create launchd plist

**Files:**
- Create: `deployment/launchd/com.ai-pa.omnifocus-sync-service.plist`

**Step 1: Ensure the deployment/launchd directory exists**

```bash
ls deployment/ 2>/dev/null || mkdir -p deployment/launchd
ls deployment/launchd/ 2>/dev/null || mkdir -p deployment/launchd
```

**Step 2: Create the plist file**

Model after `granola-mcp-proxy/com.ai-pa.supergateway-granola.plist` for structure.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-pa.omnifocus-sync-service</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Volumes/main-drive/ai-PA/scripts/omnifocus_sync_service.py</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/omnifocus-sync-service.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/omnifocus-sync-service.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/dorseyhomeserver</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>/Volumes/main-drive/ai-PA</string>
</dict>
</plist>
```

**Step 3: Verify Python path and httpx availability**

```bash
/opt/homebrew/bin/python3 -c "import httpx; print('httpx', httpx.__version__)"
```

If httpx is not available in system Python, install it:
```bash
/opt/homebrew/bin/pip3 install httpx
```

**Step 4: Commit**

```bash
git add deployment/launchd/com.ai-pa.omnifocus-sync-service.plist
git commit -m "feat: add launchd plist for OmniFocus sync service"
```

---

### Task 6: Integration test — run the service and trigger a sync

**Files:** None (manual testing)

**Step 1: Start the service**

```bash
python scripts/omnifocus_sync_service.py &
SERVICE_PID=$!
sleep 2
```

**Step 2: Test health and status endpoints**

```bash
curl -s http://localhost:8091/health | python -m json.tool
curl -s http://localhost:8091/v1/status | python -m json.tool
```

Expected: Both return valid JSON.

**Step 3: Trigger a sync and verify behavior**

```bash
curl -s -X POST http://localhost:8091/v1/sync | python -m json.tool
```

Expected: Returns `{"status": "ok", ...}` — the counts depend on whether there are any `status:confirmed` passages in archival. Check the log output for the sync sequence.

**Step 4: Verify status endpoint shows last run**

```bash
curl -s http://localhost:8091/v1/status | python -m json.tool
```

Expected: `last_run_result` is no longer null, `last_run_time` has a timestamp.

**Step 5: Stop the service**

```bash
kill $SERVICE_PID
```

---

### Task 7: Migrate scheduler jobs from agent_message to webhook

**Files:** None (API calls to scheduler-service)

**Context:** The scheduler-service runs at port 8087 (per MEMORY.md) and accepts job creation via POST. The three existing jobs fire `agent_message` actions. We'll pause the old ones and create new webhook jobs.

**Step 1: Pause old agent_message jobs**

```bash
# Weekday Daytime
curl -s -X PATCH http://localhost:8087/v1/jobs/99453d72-7cef-44cf-be61-56fc5b19e39e \
  -H 'Content-Type: application/json' \
  -d '{"status": "paused"}' | python -m json.tool

# Weekday Overnight
curl -s -X PATCH http://localhost:8087/v1/jobs/3261da2a-3be2-4d28-b0ec-1b2cda75b399 \
  -H 'Content-Type: application/json' \
  -d '{"status": "paused"}' | python -m json.tool

# Weekend
curl -s -X PATCH http://localhost:8087/v1/jobs/89147137-bc62-4deb-96e2-d3e7e7b3b01e \
  -H 'Content-Type: application/json' \
  -d '{"status": "paused"}' | python -m json.tool
```

**Step 2: Create new webhook jobs**

The scheduler-service job schema uses `expression: {"cron": "..."}` and `action` with type `webhook` (alias for `http`).

```bash
# Weekday Daytime — every 15 min, 11am-10pm ET (will increase later)
curl -s -X POST http://localhost:8087/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "OmniFocus Sync - Weekday Daytime (standalone)",
    "expression": {"cron": "*/15 11-22 * * 1-5"},
    "action": {
      "type": "webhook",
      "url": "http://localhost:8091/v1/sync",
      "method": "POST"
    }
  }' | python -m json.tool

# Weekday Overnight — hourly
curl -s -X POST http://localhost:8087/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "OmniFocus Sync - Weekday Overnight (standalone)",
    "expression": {"cron": "0 0-10,23 * * 1-5"},
    "action": {
      "type": "webhook",
      "url": "http://localhost:8091/v1/sync",
      "method": "POST"
    }
  }' | python -m json.tool

# Weekend — every 3 hours
curl -s -X POST http://localhost:8087/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "OmniFocus Sync - Weekend (standalone)",
    "expression": {"cron": "0 */3 * * 0,6"},
    "action": {
      "type": "webhook",
      "url": "http://localhost:8091/v1/sync",
      "method": "POST"
    }
  }' | python -m json.tool
```

**Step 3: Delete the old paused original job**

```bash
curl -s -X DELETE http://localhost:8087/v1/jobs/c243c1e4-3f82-4ee3-ae2b-b94b419f124e | python -m json.tool
```

**Step 4: Verify the new jobs are scheduled**

```bash
curl -s http://localhost:8087/v1/jobs | python -m json.tool | grep -A 3 "OmniFocus Sync.*standalone"
```

Expected: Three new jobs with status "scheduled".

---

### Task 8: Deploy and verify end-to-end

**Files:** None (deployment operations)

**Step 1: Install the launchd service**

```bash
cp deployment/launchd/com.ai-pa.omnifocus-sync-service.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ai-pa.omnifocus-sync-service.plist
```

**Step 2: Verify it's running**

```bash
launchctl list | grep omnifocus-sync
curl -s http://localhost:8091/health | python -m json.tool
```

Expected: Process is listed and health check returns `{"status": "healthy"}`.

**Step 3: Trigger a manual sync to verify end-to-end**

```bash
curl -s -X POST http://localhost:8091/v1/sync | python -m json.tool
```

**Step 4: Check the log file**

```bash
tail -30 /tmp/omnifocus-sync-service.log
```

Expected: Log shows the sync sequence without errors.

**Step 5: Wait for a scheduled sync (or manually test via scheduler)**

Monitor the log to confirm that the scheduler webhook triggers the sync on the next cron tick:
```bash
tail -f /tmp/omnifocus-sync-service.log
```

---

### Task 9: Final commit and cleanup

**Files:**
- Any uncommitted changes from previous tasks

**Step 1: Verify all files are committed**

```bash
git status
git diff --stat
```

**Step 2: Commit any remaining changes**

If there are uncommitted changes:
```bash
git add -A
git commit -m "feat: OmniFocus sync standalone service — complete deployment"
```

**Step 3: Verify the old agent_message jobs are paused**

```bash
curl -s http://localhost:8087/v1/jobs | python -c "
import sys, json
jobs = json.load(sys.stdin)
for j in jobs:
    if 'OmniFocus' in j.get('name', ''):
        print(f\"{j['id'][:8]}  {j['status']:10s}  {j['name']}\")
"
```

Expected: Old jobs show "paused", new standalone jobs show "scheduled".
