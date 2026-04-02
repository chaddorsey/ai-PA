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
    python scripts/omnifocus_sync_service.py              # port 8092
    python scripts/omnifocus_sync_service.py --port 8093  # custom port
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
from zoneinfo import ZoneInfo

import httpx

DEFAULT_PORT = 8093  # 8092 conflicts with task-completion-service container
STATE_DIR = Path.home() / ".omnifocus-sync"

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"
BRIDGE_URL = "http://localhost:8889"
SLACKBOT_URL = os.getenv("SLACKBOT_URL", "http://localhost:8083")
USER_NAME = "Chad Dorsey"
NOTIFIED_EXPIRY_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Concurrency guard and run state
_sync_lock = threading.Lock()
_notified_lock = threading.Lock()
_last_result = None
_last_run_time = None
_start_time = time.time()


# ── Notification dedup tracking ──

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
    with _notified_lock:
        notified = _load_notified()
        return ref_id in notified


def _mark_notified(ref_id: str) -> None:
    """Mark a ref_id as notified."""
    with _notified_lock:
        notified = _load_notified()
        notified[ref_id] = time.time()
        _save_notified(notified)


# ── Slack notification ──

SOURCE_TYPE_LABELS = {
    "google-docs-comment": "Google Doc comment",
    "google-drive-comment": "Google Doc comment",
    "slack": "Slack message",
    "email": "Email",
    "meeting": "Meeting notes",
}


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

    source_label = SOURCE_TYPE_LABELS.get(source_type, source_type)
    if location and source_label:
        context_parts.append(f"Source: {source_label} on {location}")
    elif source_label:
        context_parts.append(f"Source: {source_label}")

    if source_text:
        truncated = source_text[:300]
        if len(source_text) > 300:
            truncated += "..."
        context_parts.append(f"\"{truncated}\"")

    context_detail = "\n".join(context_parts)

    # Build reply_context for button routing
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


# ── Core sync logic ──

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


def run_sync() -> dict:
    """Run the OmniFocus completion sync."""
    global _last_result, _last_run_time

    if not _sync_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Sync already in progress"}

    try:
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

            # Insert new passage, then delete old (crash-safe order)
            with httpx.Client(timeout=30) as client:
                ins_resp = client.post(
                    f"{LETTA_BASE_URL}/v1/archives/{ARCHIVE_ID}/passages",
                    json={"text": new_text, "tags": new_tags},
                )
                ins_resp.raise_for_status()
                new_passage_id = ins_resp.json().get("id", "")

                try:
                    del_resp = client.delete(
                        f"{LETTA_BASE_URL}/v1/archives/{ARCHIVE_ID}/passages/{passage_id}",
                    )
                    del_resp.raise_for_status()
                except Exception as del_err:
                    logger.warning(
                        "Failed to delete old passage %s after inserting %s: %s",
                        passage_id, new_passage_id, del_err,
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

        # ── Step 5: Queue follow-ups for external-origin completions ──
        # Write to JSONL queue (sidebar displays these for user review/send/dismiss)
        # Replaces Slack DM notifications — user reviews in sidebar instead.
        notified_count = 0
        followup_script = Path(__file__).parent / "prepare_follow_up.py"
        for detail in details:
            if detail.get("has_external_origin"):
                if _is_already_notified(detail["ref_id"]):
                    continue
                # Pipe completion data to prepare_follow_up.py (same as bridge does)
                event_data = {
                    "taskId": detail.get("omnifocus_id", ""),
                    "taskName": detail.get("task_description", ""),
                    "refId": detail["ref_id"],
                    "event": "timer.auto-stopped",
                    "projectName": "",
                }
                try:
                    import subprocess
                    proc = subprocess.run(
                        [sys.executable, str(followup_script)],
                        input=json.dumps(event_data),
                        capture_output=True, text=True, timeout=30,
                    )
                    if proc.returncode == 0:
                        _mark_notified(detail["ref_id"])
                        notified_count += 1
                        logger.info("Follow-up queued: ref_id=%s", detail["ref_id"])
                    else:
                        logger.warning(
                            "Follow-up script failed: ref_id=%s stderr=%s",
                            detail["ref_id"], proc.stderr[:200],
                        )
                except Exception as e:
                    logger.error("Follow-up script error: ref_id=%s %s", detail["ref_id"], e)
            else:
                logger.info(
                    "Skipping notification for self-originated task: ref_id=%s",
                    detail["ref_id"],
                )

        logger.info(
            "Sync complete: checked=%d completed=%d dropped=%d not_found=%d notified=%d",
            len(task_map), completed_count, dropped_count, not_found_count, notified_count,
        )

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


# ── HTTP handler ──

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
