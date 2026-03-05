from typing import Dict, Any, Optional


def omnifocus_task(
    action: str,
    task_id: Optional[str] = None,
    name: Optional[str] = None,
    project_id: Optional[str] = None,
    note: Optional[str] = None,
    flagged: Optional[bool] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
    planned_date: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
    tag_ids: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus tasks: create, get, update, complete, or list.

    Args:
        action: Operation to perform. One of: create, get, update, complete, list (REQUIRED)
        task_id: Task UUID - required for get, update, complete
        name: Task name - required for create, optional for update
        project_id: Project UUID to assign task to (for create, update, or list filter)
        note: Task notes/description
        flagged: Whether task is flagged (true/false)
        due_date: Due date in ISO format (e.g. 2026-03-10)
        defer_date: Defer/start date in ISO format
        planned_date: Planned date for Forecast view in ISO format
        estimated_minutes: Estimated duration in minutes
        tag_ids: Comma-separated tag UUIDs to assign (for create/update), or single tag UUID (for list filter)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "create":
            cli_args.extend(["task", "create", "--name", name])
            if project_id:
                cli_args.extend(["--project", project_id])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])
            if planned_date:
                cli_args.extend(["--planned", planned_date])
            if estimated_minutes is not None:
                cli_args.extend(["--duration", str(estimated_minutes)])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])

        elif action == "get":
            cli_args.extend(["task", "get", task_id])

        elif action == "update":
            cli_args.extend(["task", "update", task_id])
            if name:
                cli_args.extend(["--name", name])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])
            if planned_date:
                cli_args.extend(["--planned", planned_date])
            if estimated_minutes is not None:
                cli_args.extend(["--duration", str(estimated_minutes)])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])

        elif action == "complete":
            cli_args.extend(["task", "complete", task_id])

        elif action == "list":
            cli_args.extend(["task", "list"])
            if project_id:
                cli_args.extend(["--project", project_id])
            if tag_ids:
                cli_args.extend(["--tag", tag_ids.split(",")[0].strip()])
            if flagged is True:
                cli_args.append("--flagged")

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: create, get, update, complete, list"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
