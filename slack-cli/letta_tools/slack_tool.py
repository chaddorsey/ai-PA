from typing import Dict, Any, Optional


def run_slack(command: str, body: Optional[str] = None, fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any Slack CLI command. Provides access to the full Slack Web API
    including conversations, chat, users, search, reactions, files, pins,
    bookmarks, reminders, and team info.

    Commands follow the pattern: <resource> <method>
    Use "schema <dotted.method>" to discover API parameters and response shapes.

    IMPORTANT: Use --fields on every list/get call to limit response size.
    Use --dry-run before any destructive operation (delete, archive).
    Use channel IDs (C0123ABCDEF) instead of names for reliability.

    Conversations examples:
      command="conversations list", body='{"types":"public_channel","limit":20}'
      command="conversations history", body='{"channel":"C0123ABCDEF","limit":50}'
      command="conversations info", body='{"channel":"C0123ABCDEF"}'
      command="conversations members", body='{"channel":"C0123ABCDEF"}'
      command="conversations +find --name project"

    Chat examples:
      command="chat postMessage", body='{"channel":"C0123ABCDEF","text":"Hello"}'
      command="chat update", body='{"channel":"C0123ABCDEF","ts":"1234567890.123456","text":"Updated"}'
      command="chat delete --dry-run", body='{"channel":"C0123ABCDEF","ts":"1234567890.123456"}'
      command="chat +send --channel general --text Hello"
      command="chat +send --channel general --text 'Thread reply' --thread-ts 1234567890.123456"

    Users examples:
      command="users list", body='{"limit":100}'
      command="users info", body='{"user":"U0123ABCDEF"}'
      command="users lookupByEmail", body='{"email":"user@example.com"}'
      command="users +whois --name John"

    Reactions examples:
      command="reactions add", body='{"channel":"C0123ABCDEF","timestamp":"1234567890.123456","name":"thumbsup"}'
      command="reactions get", body='{"channel":"C0123ABCDEF","timestamp":"1234567890.123456"}'

    Search examples (requires user token):
      command="search messages", body='{"query":"from:@user in:#general after:2026-03-01"}'
      command="search files", body='{"query":"type:pdf"}'

    Files, pins, bookmarks, reminders:
      command="files list", body='{"channel":"C0123ABCDEF"}'
      command="pins list", body='{"channel":"C0123ABCDEF"}'
      command="reminders add", body='{"text":"Check reports","time":"tomorrow at 9am"}'
      command="reminders list"

    Schema discovery (learn any method's parameters):
      command="schema chat.postMessage"
      command="schema conversations.history"
      command="schema search.messages"
      command="schema --group conversations"
      command="schema"

    Auth status:
      command="auth status"
      command="auth test"

    Args:
        command: Slack CLI command string (everything after `slack`). (REQUIRED)
        body: JSON string of API parameters (optional). Passed as --body to the CLI.
        fields: Comma-separated output fields to return, reduces token usage (e.g. "id,name,topic")
        timeout: Command timeout in seconds (default 30, increase for large paginated operations)

    Returns:
        Dictionary with status and the parsed JSON response, or raw output for non-JSON responses.
    """
    import json
    import shlex
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        cli_args = ["slack"] + shlex.split(command)

        if body:
            cli_args.extend(["--body", body])
        if fields:
            cli_args.extend(["--fields", fields])

        # Add --format json unless this is a schema or auth command
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word not in ("schema", "auth") and "--format" not in cli_args:
            cli_args.extend(["--format", "json"])

        r = subprocess.run(cli_args, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            error_detail = r.stdout.strip() or r.stderr.strip() or f"Exit code {r.returncode}"
            return {"status": "error", "error_message": error_detail[:1000]}

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
