from typing import Dict, Any, Optional


def run_notebooklm(command: str, output_file: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Run any NotebookLM CLI command. Manage notebooks, sources, chat, artifacts,
    research, and notes in Google NotebookLM.

    Commands follow the pattern: <group> <action> [args] [--flags]
    Include all flags directly in the command string, just as you would on the command line.
    Add --json to any command that supports it for structured output.

    === DISCOVERY ===
    Use --help on any command to see its flags and usage:
      command="--help"                           (list all commands and groups)
      command="source --help"                    (list source subcommands)
      command="source add --help"                (show add flags and examples)
      command="ask --help"                       (show ask flags)
      command="generate --help"                  (show artifact types)

    Available services: list, create, delete, rename, share, summary, use,
      status, clear, ask, configure, history, generate, download
    Command groups: source, artifact, note, research

    === NOTEBOOKS ===
    List notebooks:
      command="list --json"
    Create notebook:
      command='create "My Research"'
    Set current notebook (avoids passing --notebook everywhere):
      command="use NOTEBOOK_ID"
    Show current context:
      command="status"

    === SOURCES ===
    List sources in a notebook:
      command="source list --notebook NOTEBOOK_ID --json"
    Get source details (supports partial IDs):
      command="source get SOURCE_ID --notebook NOTEBOOK_ID"
    Add a URL source:
      command='source add "https://example.com" --notebook NOTEBOOK_ID --json'
    Add text source:
      command='source add "My notes here" --title "Research Notes" --notebook NOTEBOOK_ID --json'
    Add a file (auto-fetched from laptop via SCP if not local):
      command='source add "/path/to/file.pdf" --notebook NOTEBOOK_ID --json'
    Get AI-generated source guide (summary + keywords):
      command="source guide SOURCE_ID --notebook NOTEBOOK_ID"
    Add sources from web search:
      command='source add-research "curiosity in education" --source web --notebook NOTEBOOK_ID'
    Delete a source:
      command="source delete SOURCE_ID --notebook NOTEBOOK_ID"
    Refresh a URL/Drive source:
      command="source refresh SOURCE_ID --notebook NOTEBOOK_ID"

    === CHAT ===
    Ask a question (continues last conversation):
      command='ask "What are the main themes?" --notebook NOTEBOOK_ID'
    Ask with new conversation:
      command='ask --new "Summarize everything" --notebook NOTEBOOK_ID'
    Ask about specific sources only:
      command='ask -s SOURCE_ID1 -s SOURCE_ID2 "Compare these two" --notebook NOTEBOOK_ID'
    View conversation history:
      command="history --notebook NOTEBOOK_ID"

    === ARTIFACTS ===
    Generate an artifact (audio overview, quiz, report, etc.):
      command='generate audio --notebook NOTEBOOK_ID --instructions "Make it engaging"'
      Artifact types: audio, quiz, report, flashcards, slide-deck, mind-map,
        infographic, data-table, video
    Check generation status:
      command="artifact poll --notebook NOTEBOOK_ID --json"
    Wait for artifact to complete:
      command="artifact wait --notebook NOTEBOOK_ID --timeout 300"
    List artifacts:
      command="artifact list --notebook NOTEBOOK_ID --json"
    Download artifact:
      command="download audio --notebook NOTEBOOK_ID -o ./output.mp3"

    === NOTES ===
    List notes:
      command="note list --notebook NOTEBOOK_ID --json"
    Create a note:
      command='note create "Note title" --content "Note body" --notebook NOTEBOOK_ID'
    Save chat response as note:
      command='note save "Note title" --notebook NOTEBOOK_ID'

    === RESEARCH ===
    Start web or drive research:
      command='source add-research "topic" --source web --notebook NOTEBOOK_ID'
    Check research status:
      command="research status --notebook NOTEBOOK_ID"

    === TIPS ===
    - Use "use NOTEBOOK_ID" first to set context, then omit --notebook from subsequent commands
    - Source IDs support partial matching (e.g., "abc" matches "abc123def456...")
    - For large operations (artifact generation, research), increase timeout to 300
    - File paths that don't exist locally are auto-fetched from the laptop via SCP

    === OUTPUT TO FILE ===
    Use output_file to write large results directly to disk (avoids tool return truncation):
      command="source list --notebook ID --json", output_file="/Users/dorseyhomeserver/Dropbox/letta-shared-files/sources.json"
      command='ask "Summarize all sources" --notebook ID', output_file="/tmp/summary.txt"
    The tool returns a confirmation with byte count instead of the full content.

    Args:
        command: The full CLI command with all flags (e.g. 'source list --notebook ID --json')
        output_file: Write output to this file path instead of returning it (optional).
            Use for large results that would be truncated in the tool return.
        timeout: Command timeout in seconds (default 60). Use 300 for artifact wait/generation.

    Returns:
        Dictionary with status and parsed JSON response, or result_text for non-JSON output.
    """
    import json
    import os
    import shlex
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        # Parse command to check for file paths that need staging
        parts = shlex.split(command.strip())
        staging_files = []

        # Server paths → container paths via volume mounts
        VOLUME_MAPS = [
            ("/Volumes/main-drive/ai-PA/letta/", "/app/tools/letta/"),
            ("/Users/dorseyhomeserver/Dropbox/letta-shared-files/", "/data/shared/"),
        ]

        for i, part in enumerate(parts):
            if part.startswith("/") and not part.startswith("/dev/") and not os.path.exists(part):
                # Try volume mount path mapping first
                mapped = False
                for server_prefix, container_prefix in VOLUME_MAPS:
                    if part.startswith(server_prefix):
                        container_path = container_prefix + part[len(server_prefix):]
                        if os.path.exists(container_path):
                            parts[i] = container_path
                            mapped = True
                            break
                if mapped:
                    continue

                # Try SCP from remote host (for laptop files)
                remote_host = os.environ.get("NOTEBOOKLM_REMOTE_HOST", "")
                if remote_host:
                    staging_dir = "/tmp/notebooklm-staging"
                    os.makedirs(staging_dir, exist_ok=True)
                    basename = os.path.basename(part)
                    local_staging = os.path.join(staging_dir, basename)
                    scp_result = subprocess.run(
                        ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                         f"{remote_host}:{part}", local_staging],
                        capture_output=True, text=True, timeout=30,
                    )
                    if scp_result.returncode != 0:
                        return {"status": "error", "error_message": f"Failed to fetch {part} from {remote_host}: {scp_result.stderr[:300]}"}
                    parts[i] = local_staging
                    staging_files.append(local_staging)

        # Build CLI command with storage path
        storage_path = os.environ.get("NOTEBOOKLM_STORAGE", "/notebooklm-auth/storage_state.json")
        cli_args = ["notebooklm", "--storage", storage_path] + parts

        r = subprocess.run(cli_args, capture_output=True, text=True, timeout=timeout)

        # Clean up staging files
        for f in staging_files:
            try:
                os.remove(f)
            except OSError:
                pass

        if r.returncode != 0:
            error = r.stderr.strip() or r.stdout.strip() or f"Exit code {r.returncode}"
            return {"status": "error", "error_message": error[:2000]}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        # If output_file specified, write to disk instead of returning content
        if output_file:
            out_dir = os.path.dirname(output_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_file, "w") as f:
                f.write(output)
            return {"status": "ok", "wrote_file": output_file, "bytes": len(output)}

        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s. Try increasing the timeout parameter."}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}


    # _scp_fetch was here — inlined into run_notebooklm to avoid Letta extraction issues
