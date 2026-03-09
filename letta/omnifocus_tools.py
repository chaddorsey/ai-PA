from typing import Dict, Any, Optional


def run_omnifocus(command: str, fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any OmniFocus CLI command. Provides full task, project, folder,
    tag, inbox, perspective, review, search, analytics, and transaction management.

    Commands follow the pattern: <group> <action> [OPTIONS] [ARGS]
    All options are CLI flags passed directly in the command string.
    Use "schema --list" to see all available commands.

    Task examples:
      command="task list"
      command="task list --flagged"
      command="task list --include-completed"
      command="task list --project PROJECT_ID"
      command="task create --name 'Buy groceries' --flag --due 2026-03-10"
      command="task get TASK_ID"
      command="task update TASK_ID --name 'New name' --flag --due 2026-03-15"
      command="task complete TASK_ID"
      command="task batch-status"

    Project examples:
      command="project list"
      command="project create --name 'Q2 Planning' --folder FOLDER_ID"
      command="project get PROJECT_ID"

    Search examples (all filters are CLI flags):
      command="search --flagged"
      command="search --overdue"
      command="search --due-before 2026-03-08T23:59:59"
      command="search --due-before 2026-03-08T23:59:59 --due-after 2026-03-08T00:00:00"
      command="search --text 'meeting notes' --limit 10"
      command="search --available"
      command="search --tag TAG_ID"
      Note: search only returns active tasks. For completed tasks, use "task list --include-completed".

    Inbox examples:
      command="inbox list"
      command="inbox list --include-completed"

    Other groups: folder, tag, inbox, perspective, review, analytics, transaction

    Schema discovery:
      command="schema --list"
      command="schema task.create"
      command="schema project.list"

    Args:
        command: The full omnifocus-cli command with all flags and arguments (e.g. "task list --flagged" or "search --overdue")
        fields: Comma-separated output fields to return (optional). Limits token usage.
        timeout: Command timeout in seconds (default 30)

    Returns:
        Dictionary with status and the parsed JSON response.
    """
    import json
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        global_opts = []

        if fields:
            global_opts.extend(["--fields", fields])

        # Add --format json unless this is a schema command
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word != "schema":
            global_opts.extend(["--format", "json"])

        # Split command respecting quoted strings
        import shlex
        cmd_parts = ["omnifocus-cli"] + global_opts + shlex.split(command.strip())

        r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            return {"status": "error", "error_message": r.stderr[:1000] if r.stderr else f"Exit code {r.returncode}"}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
