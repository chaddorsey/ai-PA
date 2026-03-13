from typing import Dict, Any, Optional


def run_notebooklm(command: str, params: Optional[str] = None,
                   fields: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Run any NotebookLM CLI command. Manage notebooks, sources, chat, artifacts,
    research, and notes in Google NotebookLM.

    Commands follow the pattern: <group> <action>
    Use --body for JSON input (agent path), or convenience flags (human path).
    Use "schema --list" to see all available commands.

    Notebook examples:
      command="notebook list"
      command="notebook create", params='{"title": "My Research"}'
      command="notebook get", params='{"notebookId": "abc123"}'

    Source examples:
      command="source add-url", params='{"notebookId": "abc123", "url": "https://..."}'
      command="source add-file", params='{"notebookId": "abc123", "filePath": "/path/to.pdf"}'
      command="source list", params='{"notebookId": "abc123"}'

    Chat examples:
      command="chat ask", params='{"notebookId": "abc123", "question": "Summarize this"}'

    Artifact examples:
      command="artifact generate", params='{"notebookId": "abc123", "type": "audio", "instructions": "Make it engaging"}'
      command="artifact wait", params='{"notebookId": "abc123", "taskId": "task789"}'
      command="artifact download", params='{"notebookId": "abc123", "type": "audio", "outputPath": "./out.mp3"}'

    Research examples:
      command="research start", params='{"notebookId": "abc123", "query": "topic", "source": "web"}'

    Schema discovery:
      command="schema --list"
      command="schema notebook.create"

    Args:
        command: The notebooklm-cli subcommand (e.g. "notebook list", "chat ask")
        params: JSON string of parameters (optional). Passed as --body.
        fields: Comma-separated output fields (optional). Limits token usage.
        timeout: Command timeout in seconds (default 60). Use 300 for artifact wait.

    Returns:
        Dictionary with status and parsed JSON response.
    """
    import json
    import shlex
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        cli_args = ["notebooklm-cli"]

        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])

        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word != "schema":
            cli_args.extend(["--format", "json"])

        cli_args.extend(shlex.split(command.strip()))

        r = subprocess.run(cli_args, capture_output=True, text=True, timeout=timeout)

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
