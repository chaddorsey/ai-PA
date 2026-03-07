from typing import Dict, Any, Optional


def run_omnifocus(command: str, params: Optional[str] = None, fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any OmniFocus CLI command. Provides full task, project, folder,
    tag, inbox, perspective, review, search, analytics, and transaction management.

    Commands follow the pattern: <group> <action>
    Use "schema --list" to see all available commands.
    Use "schema <group.action>" to see parameters for a specific command.

    Task examples:
      command="task list"
      command="task create", params='{"name":"Buy groceries","flagged":true}'
      command="task get", params='{"taskId":"TASK_ID"}'
      command="task update", params='{"taskId":"TASK_ID","flagged":false}'
      command="task complete", params='{"taskId":"TASK_ID"}'
      command="task batch-status", params='{"taskIds":["t-1","t-2"]}'

    Project examples:
      command="project list"
      command="project create", params='{"name":"Q2 Planning","folderId":"FOLDER_ID"}'
      command="project get", params='{"projectId":"PROJECT_ID"}'

    Search examples:
      command="search query", params='{"text":"meeting notes","limit":10}'
      command="search flagged"
      command="search due-soon", params='{"days":3}'

    Other groups: folder, tag, inbox, perspective, review, analytics, transaction

    Schema discovery:
      command="schema --list"
      command="schema task.create"
      command="schema project.list"

    Args:
        command: The omnifocus-cli subcommand (e.g. "task list" or "schema task.create")
        params: JSON string of parameters (optional). Passed as --body to omnifocus-cli.
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

        # CRITICAL: Global options go BEFORE subcommand
        # omnifocus-cli [global-opts] <group> <action> [group-opts]
        global_opts = []

        if params:
            global_opts.extend(["--body", params])
        if fields:
            global_opts.extend(["--fields", fields])

        # Add --format json unless this is a schema command
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word != "schema":
            global_opts.extend(["--format", "json"])

        cmd_parts = ["omnifocus-cli"] + global_opts + command.strip().split()

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
