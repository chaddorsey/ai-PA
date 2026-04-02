from typing import Dict, Any, Optional


def run_omnifocus(command: str, fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any OmniFocus CLI command. Provides full task, project, folder,
    tag, inbox, perspective, review, search, analytics, and transaction management.

    Commands follow the pattern: <group> <action> [OPTIONS] [ARGS]
    All options are CLI flags passed directly in the command string.
    Use "schema --list" to see all available commands.
    Use "schema <group>.<action>" to discover parameters for any command.

    Task CRUD:
      command="task list"
      command="task list --flagged"
      command="task list --include-completed"
      command="task list --project PROJECT_ID"
      command="task get TASK_ID"
      command="task create --name 'Buy groceries' --flag --due 2026-03-10"
      command="task create --name 'Plan meeting' --project PROJECT_ID --defer 2026-04-01"
      command="task update TASK_ID --name 'New name' --flag --due 2026-03-15"
      command="task complete TASK_ID"
      command="task delete TASK_ID"
      command="task count"
      command="task batch-status"

    Subtask / hierarchy (create child tasks, inspect tree, flatten):
      command="task add-subtask PARENT_TASK_ID --name 'Child task'"
      command="task add-subtask PARENT_TASK_ID --name 'Step 1' --flag --due 2026-04-01"
      command="task subtasks TASK_ID"
      command="task hierarchy TASK_ID"
      command="task flatten TASK_ID"
      command="task set-group-type TASK_ID --type parallel"
      command="task set-group-type TASK_ID --type sequential"
      command="task group-type TASK_ID"

    Rich text in notes (styled text, hyperlinks, tables):
      Segments: plain strings or objects with any combo of:
        text (required), url, bold, italic, weight (1-9), size, font,
        underline, strikethrough, color:[r,g,b,a], backgroundColor:[r,g,b,a],
        align (left/right/center/justified), tabStops ("150L,300R"),
        headIndent, firstLineIndent, lineSpacing, lineHeight, paragraphSpacing
      Links: command="task append-rich-text TASK_ID", body='{"segments":["See: ",{"text":"Doc","url":"openfile:///path/to/file.pdf"}]}'
      Styled: command="task append-rich-text TASK_ID", body='{"segments":[{"text":"IMPORTANT","bold":true,"color":[1,0,0,1]},": review by Friday"]}'
      Table:  command="task append-rich-text TASK_ID", body='{"segments":[{"text":"Name\\tStatus\\n","bold":true,"tabStops":"150L"},{"text":"Task 1\\tDone\\n","tabStops":"150L"}]}'
      Use openfile:// URLs for local file links (clickable from OmniFocus).

    Task movement (re-parent, reorder):
      command="task move TASK_ID --project PROJECT_ID"
      command="task move TASK_ID --parent PARENT_TASK_ID"
      command="task move TASK_ID --parent PARENT_TASK_ID --position 0"

    Project management:
      command="project list"
      command="project list --folder FOLDER_ID"
      command="project get PROJECT_ID"
      command="project create --name 'Q2 Planning' --folder FOLDER_ID"
      command="project update PROJECT_ID --name 'Renamed'"
      command="project complete PROJECT_ID"
      command="project move PROJECT_ID --folder FOLDER_ID"
      command="project convert TASK_ID"
      command="project set-group-type PROJECT_ID --type sequential"

    Folder management:
      command="folder list"
      command="folder tree"
      command="folder get FOLDER_ID"
      command="folder create --name 'Work'"
      command="folder delete FOLDER_ID"

    Tag management:
      command="tags list"
      command="tags get TAG_ID"
      command="tags create --name 'urgent'"
      command="tags rename TAG_ID --name 'high-priority'"
      command="tags delete TAG_ID"

    Search (filters are CLI flags, returns active tasks only):
      command="search --flagged"
      command="search --overdue"
      command="search --available"
      command="search --text 'meeting notes' --limit 10"
      command="search --tag TAG_ID"
      command="search --due-before 2026-03-08T23:59:59"
      command="search --due-after 2026-03-08T00:00:00 --due-before 2026-03-08T23:59:59"
      For completed tasks use: command="task list --include-completed"

    Inbox processing:
      command="inbox list"
      command="inbox context TASK_ID"
      command="inbox process TASK_ID --project PROJECT_ID --tag TAG_ID --due 2026-04-01"
      command="inbox bulk --project PROJECT_ID"

    Perspectives:
      command="perspective list"
      command="perspective get PERSPECTIVE_ID"
      command="perspective switch PERSPECTIVE_ID"

    Review:
      command="review list"
      command="review next PROJECT_ID"
      command="review mark PROJECT_ID"

    Analytics:
      command="analytics summary"
      command="analytics health"
      command="analytics workload"
      command="analytics trends"

    Schema discovery:
      command="schema --list"
      command="schema task.create"
      command="schema task.add-subtask"
      command="schema task.move"
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
            # Validation errors (exit 2) go to stdout as JSON; execution errors go to stderr
            detail = r.stdout.strip() or r.stderr.strip() or f"Exit code {r.returncode}"
            return {"status": "error", "error_message": detail[:2000]}

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
