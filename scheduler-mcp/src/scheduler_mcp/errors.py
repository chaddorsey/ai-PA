"""Error types and message formatting for scheduler MCP tools."""

from __future__ import annotations

from typing import Any, Dict, Optional


class SchedulerToolError(Exception):
    """Base exception for scheduler tool errors with helpful messages."""

    def __init__(
        self,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to MCP-compatible response."""
        return {
            "success": False,
            "error": self.error_type,
            "message": self.message,
            **self.details,
        }


def missing_required_parameter_error(param_name: str, context: Dict[str, Any]) -> SchedulerToolError:
    """Generate error for missing required parameter with contextual examples."""
    examples = {
        "action_type": (
            f"The 'action_type' parameter is required but was not provided.\n\n"
            f"You must specify either 'script' or 'http' to indicate what kind of action to schedule.\n\n"
            f"For HTTP/API calls, use action_type='http':\n"
            f"schedule_action(\n"
            f"    action_type='http',\n"
            f"    target='https://api.example.com/webhook',\n"
            f"    when='every hour',\n"
            f"    title='Hourly sync'\n"
            f")\n\n"
            f"For running scripts, use action_type='script':\n"
            f"schedule_action(\n"
            f"    action_type='script',\n"
            f"    target='sync_data.py',\n"
            f"    when='every hour',\n"
            f"    title='Hourly data sync',\n"
            f"    args=['--incremental']\n"
            f")"
        ),
        "updates": (
            f"When operation='update', you must provide the 'updates' parameter with at least "
            f"one field to change.\n\n"
            f"Correct examples:\n\n"
            f"# Change when the job runs:\n"
            f"manage_scheduled_job(\n"
            f"    job_id='{context.get('job_id', 'abc-123')}',\n"
            f"    operation='update',\n"
            f"    updates={{'when': 'every day at 10am'}}\n"
            f")\n\n"
            f"# Change multiple fields:\n"
            f"manage_scheduled_job(\n"
            f"    job_id='{context.get('job_id', 'abc-123')}',\n"
            f"    operation='update',\n"
            f"    updates={{\n"
            f"        'title': 'Updated title',\n"
            f"        'message': 'New reminder text',\n"
            f"        'when': 'every 2 hours'\n"
            f"    }}\n"
            f")\n\n"
            f"If you just want to pause the job temporarily, use operation='pause' instead "
            f"(no updates needed)."
        ),
    }

    message = examples.get(
        param_name,
        f"Required parameter '{param_name}' is missing. Please provide this parameter and try again.",
    )

    return SchedulerToolError("MissingRequiredParameter", message, {"parameter": param_name})


def invalid_parameter_combination_error(
    param_name: str, action_type: str, target: Optional[str] = None
) -> SchedulerToolError:
    """Generate error for invalid parameter combinations (e.g., body for script)."""
    if param_name == "body" and action_type == "script":
        message = (
            f"The 'body' parameter is only valid for HTTP requests, but you specified "
            f"a script target ('{target or 'script'}').\n\n"
            f"For scripts, use the 'args' parameter instead:\n\n"
            f"Correct example:\n"
            f"schedule_action(\n"
            f"    action_type='script',\n"
            f"    target='{target or 'backup.sh'}',\n"
            f"    when='every day at 2am',\n"
            f"    title='Database backup',\n"
            f"    args=['--database', 'prod', '--compress']\n"
            f")\n\n"
            f"The 'body' parameter is for HTTP requests:\n"
            f"schedule_action(\n"
            f"    action_type='http',\n"
            f"    target='https://api.example.com/backup',\n"
            f"    when='every day at 2am',\n"
            f"    title='Trigger backup API',\n"
            f"    method='POST',\n"
            f"    body={{'database': 'prod', 'compress': True}}\n"
            f")"
        )
    elif param_name == "method" and action_type == "script":
        message = (
            f"The 'method' parameter is only valid for HTTP requests, but you specified "
            f"a script target ('{target or 'script'}').\n\n"
            f"For scripts, remove the 'method' parameter:\n\n"
            f"schedule_action(\n"
            f"    action_type='script',\n"
            f"    target='{target or 'backup.sh'}',\n"
            f"    when='every day at 2am',\n"
            f"    title='Database backup'\n"
            f")"
        )
    elif param_name == "headers" and action_type == "script":
        message = (
            f"The 'headers' parameter is only valid for HTTP requests, but you specified "
            f"a script target ('{target or 'script'}').\n\n"
            f"For scripts, remove the 'headers' parameter. If you need to pass configuration, "
            f"use 'args' instead:\n\n"
            f"schedule_action(\n"
            f"    action_type='script',\n"
            f"    target='{target or 'process_data.py'}',\n"
            f"    when='every hour',\n"
            f"    title='Data processing',\n"
            f"    args=['--config', 'production.yaml']\n"
            f")"
        )
    else:
        message = (
            f"The '{param_name}' parameter is not valid for action_type='{action_type}'. "
            f"Please check the tool documentation for valid parameters."
        )

    return SchedulerToolError("InvalidParameterCombination", message)


def invalid_schedule_expression_error(when: str, reason: str) -> SchedulerToolError:
    """Generate error for unparseable schedule expressions."""
    suggestions = {
        "too_vague": (
            f"Could not parse '{when}' as a valid schedule.\n\n"
            f"The expression is too vague. Please specify an exact time.\n\n"
            f"Valid examples:\n"
            f"- 'tomorrow at 9am'\n"
            f"- 'tomorrow at 9:30am'\n"
            f"- 'every Tuesday at 9am'\n"
            f"- 'in 3 days at 9am'\n\n"
            f"For recurring patterns:\n"
            f"- 'every day at 8am'\n"
            f"- 'every Monday at 5pm'\n"
            f"- 'every weekday at 9am'\n"
            f"- 'every 2 hours'"
        ),
        "invalid_format": (
            f"Could not parse '{when}' as a valid schedule.\n\n"
            f"Valid formats include:\n\n"
            f"Relative times:\n"
            f"- 'in 30 minutes'\n"
            f"- 'in 2 hours'\n"
            f"- 'in 3 days'\n\n"
            f"Absolute times:\n"
            f"- 'tomorrow at 9am'\n"
            f"- 'next Monday at 5pm'\n"
            f"- '2025-10-14 at 9:00am'\n\n"
            f"Recurring patterns:\n"
            f"- 'every day at 8am'\n"
            f"- 'every Monday at 5pm'\n"
            f"- 'every weekday at 9am'\n"
            f"- 'every hour'\n"
            f"- 'every 15 minutes'"
        ),
    }

    message = suggestions.get(reason, f"Invalid schedule expression: '{when}'")
    return SchedulerToolError("InvalidScheduleExpression", message)


def invalid_timezone_error(timezone: str) -> SchedulerToolError:
    """Generate error for invalid timezone names."""
    message = (
        f"Timezone '{timezone}' is not recognized. Please use IANA timezone names.\n\n"
        f"Common US timezones:\n"
        f"- 'America/New_York' (Eastern)\n"
        f"- 'America/Chicago' (Central)\n"
        f"- 'America/Denver' (Mountain)\n"
        f"- 'America/Los_Angeles' (Pacific)\n\n"
        f"Other examples:\n"
        f"- 'Europe/London'\n"
        f"- 'Asia/Tokyo'\n"
        f"- 'UTC' (default)\n\n"
        f"The default timezone is 'America/New_York' (Eastern Time) if not specified."
    )
    return SchedulerToolError("InvalidTimezone", message)


def script_not_allowlisted_error(script_path: str, available_scripts: list[str]) -> SchedulerToolError:
    """Generate error when script is not in allow-list."""
    available_list = "\n".join(f"- {script}" for script in sorted(available_scripts))
    message = (
        f"Script '{script_path}' is not in the allow-listed scripts directory.\n\n"
        f"For security, only scripts in /app/scripts/ can be scheduled.\n\n"
        f"Available scripts:\n{available_list}\n\n"
        f"If you need to run a new script:\n"
        f"1. Add it to /app/scripts/ directory\n"
        f"2. Ensure it's marked as executable\n"
        f"3. Reference it by filename only:\n\n"
        f"schedule_action(\n"
        f"    action_type='script',\n"
        f"    target='backup_database.sh',  # Just the filename\n"
        f"    when='tomorrow',\n"
        f"    title='Database backup'\n"
        f")"
    )
    return SchedulerToolError("ScriptNotAllowListed", message, {"available_scripts": available_scripts})


def invalid_operation_for_parameter_error(operation: str, param_name: str, job_id: str) -> SchedulerToolError:
    """Generate error when parameter doesn't match operation."""
    if param_name == "updates" and operation != "update":
        message = (
            f"The 'updates' parameter is only valid for operation='update', but you specified "
            f"operation='{operation}'.\n\n"
            f"To {operation} a job, simply use:\n"
            f"manage_scheduled_job(\n"
            f"    job_id='{job_id}',\n"
            f"    operation='{operation}'\n"
            f")\n\n"
        )

        if operation == "cancel":
            message += "The job will be permanently deleted and will not run again.\n\n"
        elif operation == "pause":
            message += "The job will be temporarily stopped. Use operation='resume' to re-activate it.\n\n"

        message += (
            "Other operations:\n"
            "- operation='update': Modify job details (requires 'updates' parameter)\n"
            "- operation='pause': Temporarily stop (can resume later)\n"
            "- operation='resume': Re-activate a paused job\n"
            "- operation='cancel': Permanently delete the job"
        )
    else:
        message = f"Parameter '{param_name}' is not valid for operation='{operation}'."

    return SchedulerToolError("InvalidParameterForOperation", message)


def job_not_found_error(job_id: str) -> SchedulerToolError:
    """Generate error when job ID doesn't exist."""
    message = (
        f"Job '{job_id}' not found.\n\n"
        f"The job may have been deleted or the ID is incorrect.\n\n"
        f"To list your jobs:\n"
        f"list_scheduled_jobs(\n"
        f"    filters={{'created_by': 'me'}}\n"
        f")"
    )
    return SchedulerToolError("JobNotFound", message, {"job_id": job_id})

