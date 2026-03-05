from typing import Dict, Any, Optional


def omnifocus_search(
    text: Optional[str] = None,
    project_id: Optional[str] = None,
    tag_id: Optional[str] = None,
    flagged: Optional[bool] = None,
    available: Optional[bool] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    defer_before: Optional[str] = None,
    defer_after: Optional[str] = None,
    overdue: Optional[bool] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Search OmniFocus tasks with text and/or filters. At least one parameter required.

    Args:
        text: Text to search in task names and notes
        project_id: Filter by project UUID
        tag_id: Filter by tag UUID
        flagged: Only flagged tasks (true/false)
        available: Only available tasks - not blocked or deferred (true/false)
        due_before: Tasks due before this date (ISO format, e.g. 2026-03-10)
        due_after: Tasks due after this date (ISO format)
        defer_before: Tasks deferred before this date (ISO format)
        defer_after: Tasks deferred after this date (ISO format)
        overdue: Only overdue tasks (true/false)
        limit: Maximum number of results

    Returns:
        Dictionary with status and list of matching tasks.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json", "search"]

        if text:
            cli_args.extend(["--text", text])
        if project_id:
            cli_args.extend(["--project", project_id])
        if tag_id:
            cli_args.extend(["--tag", tag_id])
        if flagged is True:
            cli_args.append("--flagged")
        if available is True:
            cli_args.append("--available")
        if due_before:
            cli_args.extend(["--due-before", due_before])
        if due_after:
            cli_args.extend(["--due-after", due_after])
        if defer_before:
            cli_args.extend(["--defer-before", defer_before])
        if defer_after:
            cli_args.extend(["--defer-after", defer_after])
        if overdue is True:
            cli_args.append("--overdue")
        if limit is not None:
            cli_args.extend(["--limit", str(limit)])

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
