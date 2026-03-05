import sys

import click

from omnifocus_cli.bridge import call_omnifocus
from omnifocus_cli.formatters import output_error, output_result


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, json_output):
    """OmniFocus CLI - manage tasks, projects, and tags."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


def _run(ctx, method: str, params: dict):
    """Call the OmniFocus bridge, stripping None values from params."""
    cleaned = {k: v for k, v in params.items() if v is not None}
    try:
        result = call_omnifocus(method, cleaned)
        output_result(result, json_output=ctx.obj["json"])
    except Exception as exc:
        output_error(str(exc), json_output=ctx.obj["json"])
        sys.exit(1)


# ── task command group ───────────────────────────────────────────────


@cli.group()
def task():
    """Manage OmniFocus tasks."""


@task.command("create")
@click.option("--name", required=True, help="Task name")
@click.option("--project", "project_id", default=None, help="Project ID")
@click.option("--note", default=None, help="Task note")
@click.option("--flag/--no-flag", "flagged", default=None, help="Flag the task")
@click.option("--due", "due_date", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--defer", "defer_date", default=None, help="Defer date (YYYY-MM-DD)")
@click.option("--planned", "planned_date", default=None, help="Planned date (YYYY-MM-DD)")
@click.option("--duration", "estimated_minutes", default=None, type=int, help="Estimated minutes")
@click.option("--tag", "tag_ids", multiple=True, help="Tag ID (repeatable)")
@click.pass_context
def task_create(ctx, name, project_id, note, flagged, due_date, defer_date,
                planned_date, estimated_minutes, tag_ids):
    """Create a new task."""
    params = {
        "name": name,
        "projectId": project_id,
        "note": note,
        "flagged": flagged,
        "dueDate": due_date,
        "deferDate": defer_date,
        "plannedDate": planned_date,
        "estimatedMinutes": estimated_minutes,
        "tagIds": list(tag_ids) if tag_ids else None,
    }
    _run(ctx, "createTask", params)


@task.command("get")
@click.argument("task_id")
@click.pass_context
def task_get(ctx, task_id):
    """Get a task by ID."""
    _run(ctx, "getTask", {"taskId": task_id})


@task.command("update")
@click.argument("task_id")
@click.option("--name", default=None, help="New task name")
@click.option("--project", "project_id", default=None, help="Project ID")
@click.option("--note", default=None, help="Task note")
@click.option("--flag/--no-flag", "flagged", default=None, help="Flag the task")
@click.option("--due", "due_date", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--defer", "defer_date", default=None, help="Defer date (YYYY-MM-DD)")
@click.option("--planned", "planned_date", default=None, help="Planned date (YYYY-MM-DD)")
@click.option("--duration", "estimated_minutes", default=None, type=int, help="Estimated minutes")
@click.option("--tag", "tag_ids", multiple=True, help="Tag ID (repeatable)")
@click.pass_context
def task_update(ctx, task_id, name, project_id, note, flagged, due_date,
                defer_date, planned_date, estimated_minutes, tag_ids):
    """Update a task by ID."""
    params = {
        "taskId": task_id,
        "name": name,
        "projectId": project_id,
        "note": note,
        "flagged": flagged,
        "dueDate": due_date,
        "deferDate": defer_date,
        "plannedDate": planned_date,
        "estimatedMinutes": estimated_minutes,
        "tagIds": list(tag_ids) if tag_ids else None,
    }
    _run(ctx, "updateTask", params)


@task.command("complete")
@click.argument("task_id")
@click.pass_context
def task_complete(ctx, task_id):
    """Mark a task as complete."""
    _run(ctx, "completeTask", {"taskId": task_id})


@task.command("list")
@click.option("--project", "project_id", default=None, help="Filter by project ID")
@click.option("--tag", "tag_id", default=None, help="Filter by tag ID")
@click.option("--flagged", is_flag=True, default=False, help="Show only flagged tasks")
@click.option("--include-completed", is_flag=True, default=False, help="Include completed tasks")
@click.pass_context
def task_list(ctx, project_id, tag_id, flagged, include_completed):
    """List tasks with optional filters."""
    params = {
        "projectId": project_id,
        "tagId": tag_id,
        "flagged": flagged if flagged else None,
        "includeCompleted": include_completed if include_completed else None,
    }
    _run(ctx, "queryTasks", params)
