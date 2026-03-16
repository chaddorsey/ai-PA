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
