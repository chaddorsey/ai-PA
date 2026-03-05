from typing import Dict, Any, Optional


def omnifocus_project(
    action: str,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    folder_id: Optional[str] = None,
    note: Optional[str] = None,
    flagged: Optional[bool] = None,
    sequential: Optional[bool] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus projects: list, get, create, update, or list-folders.

    Args:
        action: Operation to perform. One of: list, get, create, update, folders (REQUIRED)
        project_id: Project UUID - required for get, update
        name: Project name - required for create, optional for update
        folder_id: Folder UUID - for create (target folder) or list (filter by folder)
        note: Project notes
        flagged: Whether project is flagged (true/false)
        sequential: True for sequential project, false for parallel
        status: Project status for update: active, onHold, completed, dropped
        due_date: Due date in ISO format (e.g. 2026-06-30)
        defer_date: Defer date in ISO format

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "list":
            cli_args.extend(["project", "list"])
            if folder_id:
                cli_args.extend(["--folder", folder_id])

        elif action == "get":
            cli_args.extend(["project", "get", project_id])

        elif action == "create":
            cli_args.extend(["project", "create", "--name", name])
            if folder_id:
                cli_args.extend(["--folder", folder_id])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            if sequential is True:
                cli_args.append("--sequential")
            elif sequential is False:
                cli_args.append("--parallel")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        elif action == "update":
            cli_args.extend(["project", "update", project_id])
            if name:
                cli_args.extend(["--name", name])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if sequential is True:
                cli_args.append("--sequential")
            elif sequential is False:
                cli_args.append("--parallel")
            if status:
                cli_args.extend(["--status", status])
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        elif action == "folders":
            cli_args.extend(["project", "folders"])

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: list, get, create, update, folders"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
