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


# ── Search command ─────────────────────────────────────────


@cli.command()
@click.option("--text", "query", help="Text to search in task names/notes")
@click.option("--project", "project_id", help="Filter by project UUID")
@click.option("--tag", "tag_id", help="Filter by tag UUID")
@click.option("--flagged", is_flag=True, default=None, help="Only flagged tasks")
@click.option("--available", is_flag=True, default=None, help="Only available (not blocked/deferred)")
@click.option("--due-before", help="Tasks due before date (ISO)")
@click.option("--due-after", help="Tasks due after date (ISO)")
@click.option("--defer-before", help="Tasks deferred before date (ISO)")
@click.option("--defer-after", help="Tasks deferred after date (ISO)")
@click.option("--overdue", is_flag=True, default=None, help="Only overdue tasks")
@click.option("--limit", type=int, help="Max results")
@click.pass_context
def search(ctx, query, project_id, tag_id, flagged, available, due_before,
           due_after, defer_before, defer_after, overdue, limit):
    """Search tasks with filters. Requires at least one filter option."""
    has_text = query is not None
    has_filter = any(v is not None for v in [
        project_id, tag_id, flagged, available, due_before, due_after,
        defer_before, defer_after, overdue, limit,
    ])

    if not has_text and not has_filter:
        click.echo("Error: at least one filter is required. See --help.", err=True)
        sys.exit(2)

    if has_text:
        params = {"query": query}
        if project_id:
            params["scope"] = "project"
            params["scopeId"] = project_id
        if tag_id:
            params["tagId"] = tag_id
        if flagged:
            params["flagged"] = True
        if available:
            params["isAvailable"] = True
        if due_before:
            params["dueBefore"] = due_before
        if due_after:
            params["dueAfter"] = due_after
        if defer_before:
            params["deferBefore"] = defer_before
        if defer_after:
            params["deferAfter"] = defer_after
        if overdue:
            params["isOverdue"] = True
        if limit:
            params["maxResults"] = limit
        _run(ctx, "searchTasks", params)
    else:
        params = {}
        if project_id:
            params["projectId"] = project_id
        if tag_id:
            params["tagId"] = tag_id
        if flagged:
            params["flagged"] = True
        if available:
            params["isAvailable"] = True
        if due_before:
            params["dueBefore"] = due_before
        if due_after:
            params["dueAfter"] = due_after
        if defer_before:
            params["deferBefore"] = defer_before
        if defer_after:
            params["deferAfter"] = defer_after
        if overdue:
            params["isOverdue"] = True
        _run(ctx, "queryTasks", params)


# ── Project commands ───────────────────────────────────────


@cli.group()
def project():
    """List, view, create, and update projects."""
    pass


@project.command("list")
@click.option("--folder", "folder_id", help="Filter by folder UUID")
@click.option("--all", "show_all", is_flag=True, help="Include completed/dropped projects")
@click.option("--by-folder", is_flag=True, help="Group results by folder")
@click.pass_context
def list_projects(ctx, folder_id, show_all, by_folder):
    """List projects (active by default)."""
    params = {"completion": "all" if show_all else "active"}
    if folder_id:
        params["folderId"] = folder_id
    if by_folder:
        params["listByFolder"] = True
    _run(ctx, "listProjects", params)


@project.command("get")
@click.argument("project_id")
@click.pass_context
def project_get(ctx, project_id):
    """Get project details by ID."""
    _run(ctx, "getProjectById", {"projectId": project_id})


@project.command("create")
@click.option("--name", required=True, help="Project name")
@click.option("--folder", "folder_id", help="Folder UUID")
@click.option("--note", help="Project notes")
@click.option("--flag/--no-flag", default=None, help="Flag the project")
@click.option("--sequential/--parallel", default=None, help="Sequential or parallel")
@click.option("--due", "due_date", help="Due date (ISO)")
@click.option("--defer", "defer_date", help="Defer date (ISO)")
@click.pass_context
def create_project(ctx, name, folder_id, note, flag, sequential, due_date, defer_date):
    """Create a new project."""
    params = {"name": name}
    if folder_id:
        params["folderId"] = folder_id
    properties = {}
    if note:
        properties["note"] = note
    if flag is not None:
        properties["flagged"] = flag
    if sequential is not None:
        properties["sequential"] = sequential
    if due_date:
        properties["dueDate"] = due_date
    if defer_date:
        properties["deferDate"] = defer_date
    if properties:
        params["properties"] = properties
    _run(ctx, "createProject", params)


@project.command("update")
@click.argument("project_id")
@click.option("--name", help="New project name")
@click.option("--note", help="New project notes")
@click.option("--flag/--no-flag", default=None, help="Set/unset flag")
@click.option("--sequential/--parallel", default=None, help="Sequential or parallel")
@click.option("--status", type=click.Choice(["active", "onHold", "completed", "dropped"]),
              help="Project status")
@click.option("--due", "due_date", help="Due date (ISO)")
@click.option("--defer", "defer_date", help="Defer date (ISO)")
@click.pass_context
def update_project(ctx, project_id, name, note, flag, sequential, status, due_date, defer_date):
    """Update a project by ID."""
    properties = {}
    if name:
        properties["name"] = name
    if note:
        properties["note"] = note
    if flag is not None:
        properties["flagged"] = flag
    if sequential is not None:
        properties["sequential"] = sequential
    if status:
        properties["status"] = status
    if due_date:
        properties["dueDate"] = due_date
    if defer_date:
        properties["deferDate"] = defer_date
    _run(ctx, "setProjectProperties", {"projectId": project_id, "properties": properties})


@project.command("folders")
@click.pass_context
def list_folders(ctx):
    """List all folders."""
    _run(ctx, "listFolders", {})
