from typing import Dict, Any, Optional


def omnifocus_review(action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage OmniFocus project reviews. Run omnifocus-cli schema review.<action> to discover params.

    Args:
        action: One of: list, mark, next (REQUIRED)
        params: JSON string with parameters. Use schema to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "review", action]
        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])
        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip() or result.stdout.strip()}
        return {"status": "ok", "result": json.loads(result.stdout)}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
