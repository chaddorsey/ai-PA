"""
Report Refs Tool for Letta Agents

This tool allows agents to report actionable references (IDs, titles, etc.)
in a structured way. The routing handler parses tool calls rather than
free-form text, ensuring 100% reliable reference extraction.
"""

from typing import Dict, Any, Optional


def report_refs(
    ref_type: str,
    ref_id: str,
    title: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Report an actionable reference for handler coordination.

    Call this whenever you find, create, or modify a resource that the user
    might want to reference in follow-up requests. The handler will capture
    this reference to enable commands like "update that meeting" or
    "reply to that email".

    Args:
        ref_type: Type of resource. Use one of: calendar_event, task, email,
            jira_issue, confluence_page, drive_doc, slack_message, slack_user.
        ref_id: The unique identifier for the resource (eventId, taskId,
            messageId, issueKey, etc.). This is required for follow-up actions.
        title: Human-readable name or title of the resource (optional but
            recommended for context). Examples: event title, task name,
            email subject, issue summary.
        metadata_json: Optional JSON string with additional metadata like
            start time, project, status, threadId, etc. Example:
            '{"start": "2026-01-11T10:00:00", "attendees": ["alice@co.com"]}'

    Returns:
        Dictionary with keys:
        - status: "ok" indicating reference was logged
        - ref_type: The type of resource reported
        - ref_id: The identifier reported
        - title: The title if provided
        - message: Confirmation message
    """
    # Imports inside function for Letta tool extraction
    import json
    import traceback

    try:
        # Parse metadata if provided
        metadata = None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError:
                metadata = {"raw": metadata_json}

        # Build confirmation message
        parts = [f"{ref_type}={ref_id}"]
        if title:
            parts.append(f'title="{title}"')
        if metadata:
            meta_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
            parts.append(f"({meta_str})")

        confirmation = f"Reference logged: {' '.join(parts)}"

        return {
            "status": "ok",
            "ref_type": ref_type,
            "ref_id": ref_id,
            "title": title,
            "metadata": metadata,
            "message": confirmation,
        }

    except Exception as e:
        return {
            "status": "error",
            "ref_type": ref_type,
            "ref_id": ref_id,
            "title": title,
            "metadata": None,
            "message": f"Error logging reference: {str(e)}",
            "error": traceback.format_exc(),
        }
