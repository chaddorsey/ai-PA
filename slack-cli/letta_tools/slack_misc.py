from typing import Dict, Any, Optional


def run_slack_misc(group: str, action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage Slack files, pins, bookmarks, reminders, and team info. Run `slack schema <group>.<action>` to discover params.

    Args:
        group: One of: files, pins, bookmarks, reminders, team (REQUIRED)
        action: Method name within the group (REQUIRED). Run `slack schema --group <group>` to list available actions.
        params: JSON string with parameters. Use `slack schema <group>.<action>` to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from Slack API.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["slack", group, action]
        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])
        cli_args.extend(["--format", "json"])
        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            error_output = result.stdout.strip() or result.stderr.strip()
            return {"status": "error", "error_message": error_output}
        return {"status": "ok", "result": json.loads(result.stdout)}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
