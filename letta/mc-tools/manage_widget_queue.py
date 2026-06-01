from typing import Dict, Any, Optional, List


def manage_widget_queue(action: str, task_ids: Optional[str] = None, position: Optional[int] = None) -> Dict[str, Any]:
    """
    Manage the OmniFocus timer widget queue on the laptop.

    Controls the floating timer widget's task queue — add, remove, reorder,
    or list tasks queued for focused work sessions.

    Args:
        action: Queue operation. One of: list, set, push, insert, remove, move, clear.
            list — return current queue contents
            set — replace entire queue (task_ids: comma-separated OmniFocus task IDs in priority order)
            push — append task(s) to end of queue (task_ids: comma-separated)
            insert — insert task at position (task_ids: single ID, position: 0-indexed)
            remove — remove task from queue (task_ids: single ID)
            move — move task to position (task_ids: single ID, position: 0-indexed)
            clear — empty the queue
        task_ids: Comma-separated OmniFocus task IDs. Required for set, push, insert, remove, move.
        position: Target position for insert/move (0-indexed). Required for insert, move.

    Returns:
        Dictionary with status and current queue state.
    """
    import subprocess
    import json
    import traceback

    try:
        LAPTOP_USER = "chaddorsey"
        LAPTOP_HOST = "100.95.213.46"
        QUEUE_SCRIPT = "~/Dropbox/dev/omnifocus-timer/widget-queue.sh"

        valid_actions = ("list", "set", "push", "insert", "remove", "move", "clear")
        if not action or action not in valid_actions:
            return {"status": "error", "error_message": f"Invalid action: {action}. Must be one of: {', '.join(valid_actions)}"}

        # Build the remote command
        cmd_parts = [QUEUE_SCRIPT, action]
        if action == "set" and task_ids:
            for tid in task_ids.split(","):
                tid = tid.strip()
                if tid:
                    cmd_parts.append(tid)
        elif action == "push" and task_ids:
            for tid in task_ids.split(","):
                tid = tid.strip()
                if tid:
                    cmd_parts.append(tid)
        elif action == "insert":
            if position is None:
                return {"status": "error", "error_message": "position is required for insert"}
            if not task_ids:
                return {"status": "error", "error_message": "task_ids is required for insert"}
            cmd_parts.append(str(position))
            cmd_parts.append(task_ids.strip())
        elif action == "remove":
            if not task_ids:
                return {"status": "error", "error_message": "task_ids is required for remove"}
            cmd_parts.append(task_ids.strip())
        elif action == "move":
            if not task_ids:
                return {"status": "error", "error_message": "task_ids is required for move"}
            if position is None:
                return {"status": "error", "error_message": "position is required for move"}
            cmd_parts.append(task_ids.strip())
            cmd_parts.append(str(position))

        remote_cmd = " ".join(cmd_parts)
        ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
            f"{LAPTOP_USER}@{LAPTOP_HOST}",
            remote_cmd,
        ]

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            return {"status": "error", "error_message": f"SSH failed (exit {result.returncode}): {result.stderr.strip()[:500]}"}

        output = result.stdout.strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"status": "ok", "raw_output": output}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
