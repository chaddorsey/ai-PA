#!/usr/bin/env python3
"""OmniFocus task snapshot — detect creations, completions, and deletions.

Runs every 15 minutes via scheduler-service. Compares current OmniFocus state
against the previous snapshot and logs changes to task-lifecycle.jsonl.

Zero LLM cost — pure diffing, no AI involved.

Usage:
    python3 omnifocus_snapshot.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime

SNAPSHOT_DIR = os.environ.get(
    "SNAPSHOT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "omnifocus-timer", "logs"),
)
SNAPSHOT_FILE = os.path.join(SNAPSHOT_DIR, "omnifocus-snapshot.json")
LIFECYCLE_LOG = os.path.join(SNAPSHOT_DIR, "task-lifecycle.jsonl")

# Fields we track — keep it lean
FIELDS = "id,name,completed,dropped,added,duration,projectId,folderId,flagged"


def log(msg):
    print(f"[of-snapshot] {msg}", flush=True)


def log_lifecycle(event, **fields):
    entry = {"event": event, "timestamp": datetime.utcnow().isoformat() + "Z"}
    entry.update({k: v for k, v in fields.items() if v is not None})
    try:
        with open(LIFECYCLE_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log(f"Failed to write lifecycle: {e}")


def fetch_tasks():
    """Fetch all active + recently completed tasks from OmniFocus."""
    try:
        # Pull all tasks including completed — needed to distinguish
        # completions from deletions. ~1000 tasks, ~3 seconds, ~320KB.
        result = subprocess.run(
            ["omnifocus-cli", "--format", "json", "--fields", FIELDS,
             "task", "list", "--include-completed"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log(f"CLI error: {result.stderr[:200]}")
            return None

        data = json.loads(result.stdout)

        # Handle standard envelope
        if isinstance(data, dict):
            if "data" in data and "tasks" in data["data"]:
                tasks = data["data"]["tasks"]
            elif "result" in data:
                inner = data["result"]
                if isinstance(inner, str):
                    inner = json.loads(inner)
                if isinstance(inner, dict) and "result" in inner:
                    inner = inner["result"]
                tasks = inner if isinstance(inner, list) else inner.get("tasks", [])
            else:
                tasks = []
        elif isinstance(data, list):
            tasks = data
        else:
            tasks = []

        return {t["id"]: t for t in tasks if isinstance(t, dict) and "id" in t}

    except Exception as e:
        log(f"Fetch failed: {e}")
        return None


def load_snapshot():
    """Load the previous snapshot."""
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE) as f:
            data = json.load(f)
        return data.get("tasks", {})
    except Exception:
        return {}


def save_snapshot(tasks):
    """Save the current snapshot."""
    data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "count": len(tasks),
        "tasks": tasks,
    }
    try:
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        log(f"Failed to save snapshot: {e}")


def is_repeating_instance(task):
    """Check if a task ID looks like a repeating instance (contains dots)."""
    return "." in task.get("id", "")


def diff_snapshots(old_tasks, new_tasks):
    """Compare snapshots and return changes."""
    old_ids = set(old_tasks.keys())
    new_ids = set(new_tasks.keys())

    created = []
    deleted = []
    completed = []
    uncompleted = []

    # New tasks (in new but not old)
    for tid in new_ids - old_ids:
        t = new_tasks[tid]
        if is_repeating_instance(t):
            continue  # Skip repeating task instances
        created.append(t)

    # Deleted tasks (in old but not new) — truly gone from OmniFocus
    for tid in old_ids - new_ids:
        t = old_tasks[tid]
        if is_repeating_instance(t):
            continue
        deleted.append(t)

    # Status changes (in both)
    for tid in old_ids & new_ids:
        old_t = old_tasks[tid]
        new_t = new_tasks[tid]

        # Completed (in OmniFocus, not via timer)
        if not old_t.get("completed") and new_t.get("completed"):
            completed.append(new_t)

        # Uncompleted (undo)
        if old_t.get("completed") and not new_t.get("completed"):
            uncompleted.append(new_t)

    return created, deleted, completed, uncompleted


def main():
    log("Starting snapshot...")

    current = fetch_tasks()
    if current is None:
        log("Failed to fetch tasks — skipping this cycle")
        return

    previous = load_snapshot()

    if not previous:
        log(f"First run — saving baseline snapshot ({len(current)} tasks)")
        save_snapshot(current)
        return

    created, deleted, completed, uncompleted = diff_snapshots(previous, current)

    if not any([created, deleted, completed, uncompleted]):
        log(f"No changes detected ({len(current)} tasks)")
        save_snapshot(current)
        return

    # Log changes
    for t in created:
        log(f"Created: {t['name'][:60]}")
        log_lifecycle(
            "omnifocus_created",
            omnifocus_id=t["id"],
            task=t.get("name"),
            source_type="omnifocus",
            duration=t.get("duration"),
            flagged=t.get("flagged"),
        )

    for t in deleted:
        log(f"Deleted: {t['name'][:60]}")
        log_lifecycle(
            "omnifocus_deleted",
            omnifocus_id=t["id"],
            task=t.get("name"),
        )

    for t in completed:
        log(f"Completed: {t['name'][:60]}")
        log_lifecycle(
            "omnifocus_completed",
            omnifocus_id=t["id"],
            task=t.get("name"),
            duration=t.get("duration"),
        )

    for t in uncompleted:
        log(f"Uncompleted: {t['name'][:60]}")
        log_lifecycle(
            "omnifocus_uncompleted",
            omnifocus_id=t["id"],
            task=t.get("name"),
        )

    log(f"Changes: +{len(created)} created, -{len(deleted)} deleted, "
        f"✓{len(completed)} completed, ↩{len(uncompleted)} uncompleted")

    save_snapshot(current)


if __name__ == "__main__":
    main()
