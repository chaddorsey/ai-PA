from typing import Dict, Any, Optional


def omnifocus_inbox(
    action: str,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    tag_ids: Optional[str] = None,
    flagged: Optional[bool] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus inbox: list items or process them into projects.

    Args:
        action: Operation to perform. One of: list, process (REQUIRED)
        task_id: Inbox item UUID - required for process
        project_id: Project UUID to move item to (for process)
        tag_ids: Comma-separated tag UUIDs to assign (for process)
        flagged: Whether to flag the item (true/false, for process)
        due_date: Due date in ISO format (for process)
        defer_date: Defer date in ISO format (for process)
        limit: Max items to return (for list)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "list":
            cli_args.extend(["inbox", "list"])
            if limit is not None:
                cli_args.extend(["--limit", str(limit)])

        elif action == "process":
            cli_args.extend(["inbox", "process", task_id])
            if project_id:
                cli_args.extend(["--project", project_id])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: list, process"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
