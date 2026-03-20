from typing import Dict, Any, Optional


def manage_widget_queue(action: str, task_ids: Optional[str] = None, position: Optional[int] = None) -> Dict[str, Any]:
    """
    Manage the OmniFocus timer widget queue on the laptop via SSH.

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
    import subprocess
    import traceback
    import os

    try:
        if not action or action not in ("list", "set", "push", "insert", "remove", "move", "clear"):
            return {"status": "error", "error_message": f"Invalid action: {action}. Must be one of: list, set, push, insert, remove, move, clear"}

        laptop_host = os.environ.get("LAPTOP_SSH_HOST", "chaddorsey@100.95.213.46")
        ssh_key = os.environ.get("LAPTOP_SSH_KEY", "/root/.ssh/id_ed25519")
        queue_script = "~/Dropbox/dev/omnifocus-timer/widget-queue.sh"

        # Build the remote command
        cmd_parts = [queue_script, action]
        if action in ("set", "push") and task_ids:
            for tid in task_ids.split(","):
                tid = tid.strip()
                if tid:
                    cmd_parts.append(tid)
        elif action == "insert" and task_ids and position is not None:
            cmd_parts.append(str(position))
            cmd_parts.append(task_ids.strip())
        elif action == "remove" and task_ids:
            cmd_parts.append(task_ids.strip())
        elif action == "move" and task_ids and position is not None:
            cmd_parts.append(task_ids.strip())
            cmd_parts.append(str(position))

        remote_cmd = " ".join(cmd_parts)

        result = subprocess.run(
            [
                "ssh",
                "-i", ssh_key,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                laptop_host,
                remote_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return {"status": "error", "error_message": f"SSH exit {result.returncode}: {stderr or stdout}"}

        # Parse the JSON output from widget-queue.sh
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"status": "ok", "raw_output": stdout}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": "SSH command timed out (20s)"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
