"""Register the manage_widget_queue tool with Letta and attach to Rover."""

import json
import os
import urllib.request

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
ROVER_AGENT_ID = "agent-76ee5448-68ec-4fdd-b102-d4895d44e090"

TOOL_SOURCE = '''
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
        return {"status": "error", "error_message": f"{str(e)}\\n{traceback.format_exc()}"}
'''


def _request(method, path, data=None):
    """Make a request to Letta API with redirect handling."""
    url = f"{LETTA_BASE_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        if e.code == 307:
            redirect = e.headers.get("Location", url + "/")
            req2 = urllib.request.Request(redirect, data=body, headers={"Content-Type": "application/json"}, method=method)
            return json.loads(urllib.request.urlopen(req2, timeout=15).read())
        raise


def register_tool():
    """Register or update the tool."""
    # Check if exists
    try:
        tools = _request("GET", "/v1/tools/?name=manage_widget_queue")
        if tools:
            tool_id = tools[0]["id"]
            _request("PATCH", f"/v1/tools/{tool_id}", {"source_code": TOOL_SOURCE})
            print(f"Updated existing tool: {tool_id}")
            return tool_id
    except Exception:
        pass

    tool = _request("POST", "/v1/tools/", {
        "name": "manage_widget_queue",
        "source_code": TOOL_SOURCE,
        "source_type": "json",
        "tags": ["timer", "widget", "queue"],
    })
    tool_id = tool["id"]
    print(f"Created tool: {tool_id}")
    return tool_id


def attach_to_rover(tool_id):
    """Attach to Rover, preserving existing tools."""
    current = _request("GET", f"/v1/agents/{ROVER_AGENT_ID}/tools?limit=50")
    current_ids = [t["id"] for t in current]

    if tool_id in current_ids:
        print("Already attached to Rover")
        return

    all_ids = current_ids + [tool_id]
    _request("PATCH", f"/v1/agents/{ROVER_AGENT_ID}", {"tool_ids": all_ids})
    print(f"Attached to Rover ({len(all_ids)} tools total)")


if __name__ == "__main__":
    tool_id = register_tool()
    attach_to_rover(tool_id)
    print("Done!")
