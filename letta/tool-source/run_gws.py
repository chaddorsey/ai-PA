def run_gws(command: str, params: Optional[str] = None, body: Optional[str] = None,
            output_file: Optional[str] = None, format: Optional[str] = None,
            page_all: bool = False, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any Google Workspace CLI command. Provides access to ALL Google APIs.

    The gws CLI follows a consistent pattern: gws <service> <resource> <method>
    Use "schema <dotted.path>" to discover any API's parameters and response shapes.

    IMPORTANT: All params values must be JSON-typed scalars (string, number, boolean), NOT arrays. For multi-value
    fields like labelIds, use a comma-separated string: "INBOX,UNREAD" not ["INBOX","UNREAD"].

    Available services: gmail, calendar, drive, docs, sheets, slides, tasks, people,
      chat, classroom, forms, keep, meet, events, admin-reports, workflow

    === SELF-DISCOVERY ===
    The gws CLI is self-documenting. Use these to discover current capabilities:
      command="gmail --help"                    — list Gmail helpers and subcommands
      command="gmail +send --help"              — see flags for +send (--draft, -a, --html, etc.)
      command="schema gmail.users.drafts.create" — see API parameters for any method
      command="calendar --help"                 — list Calendar helpers and subcommands

    === SCHEMA DISCOVERY ===
    Discover API parameters before calling any method:
      command="schema docs.documents.get"
      command="schema drive.files.export"
      command="schema gmail.users.messages.list"
      command="schema calendar.events.list"

    === GMAIL ===
    Helpers handle MIME, threading, attachments, and drafts automatically:
      +send       — compose and send (supports --draft, -a/--attach, --html, --cc, --bcc)
      +reply      — reply with threading (supports --draft, -a)
      +reply-all  — reply-all (supports --draft, -a)
      +forward    — forward to new recipients (supports --draft, -a)
      +read       — extract message body and headers
      +triage     — unread inbox summary
      +watch      — stream new emails as NDJSON
    Use command="gmail +send --help" (etc.) to see current flags for each helper.
    Raw API for operations not covered by helpers:
      command="gmail users messages list", params='{"userId":"me","q":"is:unread","maxResults":5}'
      command="gmail users messages get", params='{"userId":"me","id":"MSG_ID","format":"full"}'
    Get inbox counts (use labels get, NOT messages list):
      command="gmail users labels get", params='{"userId":"me","id":"INBOX"}'
      Returns messagesTotal and messagesUnread — these are exact counts.
      WARNING: Gmail's "resultSizeEstimate" from messages.list is inaccurate. Use labels.get.
    Modify labels:
      command="gmail users messages modify", params='{"userId":"me","id":"MSG_ID"}', body='{"addLabelIds":["STARRED"]}'

    === DOCS ===
    Read a document (first tab only):
      command="docs documents get", params='{"documentId":"DOC_ID"}'
    Read a document (ALL tabs — use this for multi-tab docs):
      command="docs documents get", params='{"documentId":"DOC_ID","includeTabsContent":true}'
      With tabs: content is in result.tabs[].documentTab.body (not result.body)
    Append text:
      command="docs +write --document DOC_ID --text 'Text to append'"

    === DRIVE ===
    Export Google Docs/Sheets/Slides:
      command="drive files export", params='{"fileId":"DOC_ID","mimeType":"text/plain"}', output_file="/dev/stdout"
      Supported mimeTypes: text/plain, text/markdown, application/pdf
      IMPORTANT: Use output_file="/dev/stdout" to get exported content returned directly.
    Upload a file:
      command="drive +upload --help"    — see current flags
    List/search files:
      command="drive files list", params='{"q":"name contains \\'report\\'","pageSize":10}'

    === CALENDAR ===
    Helpers:
      command="calendar +agenda"
      command="calendar +insert --help"    — see current flags
    Raw API:
      command="calendar events list", params='{"calendarId":"primary","timeMin":"2026-04-01T00:00:00Z","maxResults":10}'

    === SHEETS ===
    Helpers:
      command="sheets +read --spreadsheet SHEET_ID --range Sheet1!A1:D10"
      command="sheets +append --spreadsheet SHEET_ID --range Sheet1 --values 'val1,val2,val3'"

    === OTHER SERVICES ===
    slides, tasks, people, chat, keep, meet, events — use command="<service> --help"

    === WORKFLOW HELPERS ===
    Cross-service productivity helpers:
      command="workflow +standup-report"
      command="workflow +meeting-prep"
      command="workflow +email-to-task"
      command="workflow +weekly-digest"
      command="workflow +file-announce"

    === FLAGS ===
    format: Override output format — "json" (default), "table", "yaml", "csv"
    output_file: Write binary/text output to this path (use "/dev/stdout" to capture export content)
    page_all: Auto-paginate through all results (for list operations with many pages)
    timeout: Command timeout in seconds (default 30, increase for large docs/exports)

    Args:
        command: The gws subcommand (e.g. "docs documents get" or "schema docs.documents.get")
        params: JSON string of query/path parameters (optional)
        body: JSON string of request body (optional). Used for create, update, modify operations.
        output_file: File path for binary/export output (optional). Use "/dev/stdout" to return
            content directly (essential for drive files export).
        format: Output format override (optional). One of: json, table, yaml, csv.
            Default is json. Use "table" or "yaml" for more readable output on complex responses.
        page_all: Auto-paginate through all results (default False). Useful for list operations.
        timeout: Command timeout in seconds (default 30, increase for large operations)

    Returns:
        Dictionary with status and the parsed JSON response, or result_text for non-JSON output.
    """
    import json
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        # Build the gws command
        cmd_parts = ["gws"] + command.strip().split()

        if params:
            cmd_parts.extend(["--params", params])
        if body:
            cmd_parts.extend(["--json", body])
        if output_file:
            cmd_parts.extend(["-o", output_file])
        if page_all:
            cmd_parts.append("--page-all")

        # Determine output format
        first_word = command.strip().split()[0] if command.strip() else ""
        if format:
            cmd_parts.extend(["--format", format])
        elif first_word not in ("schema", "auth"):
            cmd_parts.extend(["--format", "json"])

        # For export to /dev/stdout, capture stdout as binary-safe text
        r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            error_detail = r.stderr.strip() or r.stdout.strip() or f"Exit code {r.returncode}"
            return {"status": "error", "error_message": error_detail[:2000]}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        # If output_file was /dev/stdout, return the raw content as text
        if output_file == "/dev/stdout":
            return {"status": "ok", "result_text": output}

        # Try to parse as JSON; fall back to raw text (schema, table, yaml, csv output)
        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s. Try increasing the timeout parameter."}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}

