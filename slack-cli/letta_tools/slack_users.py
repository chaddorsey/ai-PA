from typing import Dict, Any, Optional


def run_slack_users(action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Look up Slack users and profiles. Run `slack schema users.<action>` to discover params.

    Args:
        action: One of: list, info, lookupByEmail, getPresence, setPresence, +whois (REQUIRED)
        params: JSON string with parameters. Use `slack schema users.<action>` to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from Slack API.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["slack", "users", action]
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
