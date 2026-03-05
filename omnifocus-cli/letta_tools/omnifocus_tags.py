from typing import Dict, Any, Optional


def omnifocus_tags(
    action: str,
    tag_id: Optional[str] = None,
    name: Optional[str] = None,
    parent_tag_id: Optional[str] = None,
    force: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus tags: list, create, rename, or delete.

    Args:
        action: Operation to perform. One of: list, create, rename, delete (REQUIRED)
        tag_id: Tag UUID - required for rename, delete
        name: Tag name - required for create and rename
        parent_tag_id: Parent tag UUID for creating nested tags
        force: Force delete even if tasks use this tag (true/false)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "list":
            cli_args.extend(["tags", "list"])

        elif action == "create":
            cli_args.extend(["tags", "create", "--name", name])
            if parent_tag_id:
                cli_args.extend(["--parent", parent_tag_id])

        elif action == "rename":
            cli_args.extend(["tags", "rename", tag_id, "--name", name])

        elif action == "delete":
            cli_args.extend(["tags", "delete", tag_id])
            if force is True:
                cli_args.append("--force")

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: list, create, rename, delete"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
