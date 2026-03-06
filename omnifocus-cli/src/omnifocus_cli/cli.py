import json
import sys

import click

from omnifocus_cli.bridge import call_omnifocus
from omnifocus_cli.fields import apply_field_mask
from omnifocus_cli.formatters import output_error, output_result, should_use_json
from omnifocus_cli.schema import get_schema, list_schemas
from omnifocus_cli.validate import validate_body, validate_date, validate_name, validate_uuid


@click.group()
@click.option("--format", "format_flag", type=click.Choice(["json", "text"]), default=None)
@click.option("--body", "body_json", default=None, help="Raw JSON input (agent-first path)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate + preview, no execution")
@click.option("--fields", default=None, help="Comma-separated output fields")
@click.pass_context
def cli(ctx, format_flag, body_json, dry_run, fields):
    """OmniFocus CLI - manage tasks, projects, and tags."""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format_flag
    ctx.obj["body"] = body_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["fields"] = fields.split(",") if fields else None


_DATE_SUFFIXES = ("Date", "Before", "After")


def _validate_semantics(schema_key: str, params: dict) -> list[dict]:
    """Validate UUID, date, and name values in params."""
    errors: list[dict] = []
    schema = get_schema(schema_key)
    if schema is None:
        return errors

    for field_name, value in params.items():
        if value is None:
            continue
        param_def = schema["params"].get(field_name)
        if param_def is None:
            continue

        # UUID fields: string type, name ends with "Id"
        if param_def["type"] == "string" and field_name.endswith("Id"):
            err = validate_uuid(value)
            if err:
                errors.append({"field": field_name, "error": err})

        # Date fields: string type, name ends with "Date", "Before", or "After"
        elif param_def["type"] == "string" and any(
            field_name.endswith(s) for s in _DATE_SUFFIXES
        ):
            err = validate_date(value)
            if err:
                errors.append({"field": field_name, "error": err})

        # Name field
        elif field_name == "name" and param_def["type"] == "string":
            err = validate_name(value)
            if err:
                errors.append({"field": field_name, "error": err})

    return errors


def _run(ctx, schema_key: str, method: str, params: dict, had_convenience_flags: bool = False):
    """Core execution helper.

    1. If --body was provided, parse JSON and validate against schema; ignore params arg.
    2. If --body AND convenience flags: use --body, warn to stderr.
    3. If no --body: use params from convenience flags.
    4. Validation errors -> stdout JSON, exit 2.
    5. --dry-run -> stdout JSON, exit 0 (valid) or 2 (invalid).
    6. Otherwise: call bridge, apply field mask, output.
    """
    body_json = ctx.obj.get("body")
    dry_run = ctx.obj.get("dry_run", False)
    use_json = should_use_json(ctx.obj.get("format"))
    field_list = ctx.obj.get("fields")

    if body_json is not None:
        # Agent path: parse --body JSON
        try:
            parsed_body = json.loads(body_json)
        except json.JSONDecodeError as exc:
            click.echo(json.dumps({"error": "invalid_json", "detail": str(exc)}), nl=True)
            ctx.exit(2)
            return

        if had_convenience_flags:
            click.echo("Warning: --body provided; ignoring convenience flags", err=True)

        # Validate against schema
        errors = validate_body(schema_key, parsed_body)
        if errors:
            if dry_run:
                click.echo(json.dumps({
                    "dry_run": True,
                    "method": method,
                    "validation_errors": errors,
                }, indent=2))
                ctx.exit(2)
                return
            click.echo(json.dumps({
                "error": "validation_failed",
                "errors": errors,
            }, indent=2))
            ctx.exit(2)
            return

        final_params = parsed_body
    else:
        # Convenience-flag path: use params as-is (already cleaned by caller).
        # Skip schema validation here -- convenience flags are already
        # structurally correct by construction and may include params
        # (e.g. filter-only search fields) not in the primary schema.
        final_params = params

    # Semantic validation: UUIDs, dates, names
    semantic_errors = _validate_semantics(schema_key, final_params)
    if semantic_errors:
        if dry_run:
            click.echo(json.dumps({
                "dry_run": True,
                "method": method,
                "validation_errors": semantic_errors,
            }, indent=2))
            ctx.exit(2)
            return
        click.echo(json.dumps({
            "error": "validation_failed",
            "errors": semantic_errors,
        }, indent=2))
        ctx.exit(2)
        return

    if dry_run:
        click.echo(json.dumps({
            "dry_run": True,
            "method": method,
            "params": final_params,
            "validation": "passed",
        }, indent=2))
        ctx.exit(0)
        return

    # Execute
    try:
        result = call_omnifocus(method, final_params)
        result = apply_field_mask(result, field_list)
        output_result(result, json_output=use_json)
    except Exception as exc:
        output_error(str(exc), json_output=use_json)
        sys.exit(1)


# ── schema command ──────────────────────────────────────────────────


@cli.command("schema")
@click.argument("method", required=False)
@click.option("--list", "list_all", is_flag=True, help="List all available methods")
@click.pass_context
def schema_cmd(ctx, method, list_all):
    """Show schema for a method, or list all methods."""
    if list_all:
        print("\n".join(list_schemas()))
        ctx.exit(0)
        return
    if not method:
        click.echo("Usage: omnifocus-cli schema <method> or --list", err=True)
        ctx.exit(2)
        return
    s = get_schema(method)
    if s is None:
        click.echo(f"Unknown method: {method}", err=True)
        ctx.exit(2)
        return
    print(json.dumps(s, indent=2))


# ── task command group ───────────────────────────────────────────────


@cli.group()
def task():
    """Manage OmniFocus tasks."""


@task.command("create")
@click.option("--name", default=None, help="Task name")
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
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [
            name, project_id, note, flagged, due_date, defer_date,
            planned_date, estimated_minutes,
        ]) or bool(tag_ids)
        _run(ctx, "task.create", "createTask", {}, had_convenience_flags=had_flags)
    else:
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
        cleaned = {k: v for k, v in params.items() if v is not None}
        _run(ctx, "task.create", "createTask", cleaned)


@task.command("get")
@click.argument("task_id")
@click.pass_context
def task_get(ctx, task_id):
    """Get a task by ID."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.get", "getTask", {})
    else:
        _run(ctx, "task.get", "getTask", {"taskId": task_id})


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
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [
            name, project_id, note, flagged, due_date, defer_date,
            planned_date, estimated_minutes,
        ]) or bool(tag_ids)
        _run(ctx, "task.update", "updateTask", {}, had_convenience_flags=had_flags)
    else:
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
        cleaned = {k: v for k, v in params.items() if v is not None}
        _run(ctx, "task.update", "updateTask", cleaned)


@task.command("complete")
@click.argument("task_id")
@click.pass_context
def task_complete(ctx, task_id):
    """Mark a task as complete."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.complete", "completeTask", {})
    else:
        _run(ctx, "task.complete", "completeTask", {"taskId": task_id})


@task.command("list")
@click.option("--project", "project_id", default=None, help="Filter by project ID")
@click.option("--tag", "tag_id", default=None, help="Filter by tag ID")
@click.option("--flagged", is_flag=True, default=False, help="Show only flagged tasks")
@click.option("--include-completed", is_flag=True, default=False, help="Include completed tasks")
@click.pass_context
def task_list(ctx, project_id, tag_id, flagged, include_completed):
    """List tasks with optional filters."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [project_id, tag_id]) or flagged or include_completed
        _run(ctx, "task.list", "queryTasks", {}, had_convenience_flags=had_flags)
    else:
        params = {
            "projectId": project_id,
            "tagId": tag_id,
            "flagged": flagged if flagged else None,
            "includeCompleted": include_completed if include_completed else None,
        }
        cleaned = {k: v for k, v in params.items() if v is not None}
        _run(ctx, "task.list", "queryTasks", cleaned)


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
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [
            query, project_id, tag_id, flagged, available, due_before,
            due_after, defer_before, defer_after, overdue, limit,
        ])
        _run(ctx, "search", "searchTasks", {}, had_convenience_flags=had_flags)
        return

    # Convenience-flag path
    has_text = query is not None
    has_filter = any(v is not None for v in [
        project_id, tag_id, flagged, available, due_before, due_after,
        defer_before, defer_after, overdue, limit,
    ])

    if not has_text and not has_filter:
        click.echo("Error: at least one filter is required. See --help.", err=True)
        ctx.exit(2)
        return

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
        _run(ctx, "search", "searchTasks", params)
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
        _run(ctx, "task.list", "queryTasks", params)


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
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [folder_id]) or show_all or by_folder
        _run(ctx, "project.list", "listProjects", {}, had_convenience_flags=had_flags)
    else:
        params = {"completion": "all" if show_all else "active"}
        if folder_id:
            params["folderId"] = folder_id
        if by_folder:
            params["listByFolder"] = True
        _run(ctx, "project.list", "listProjects", params)


@project.command("get")
@click.argument("project_id")
@click.pass_context
def project_get(ctx, project_id):
    """Get project details by ID."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "project.get", "getProjectById", {})
    else:
        _run(ctx, "project.get", "getProjectById", {"projectId": project_id})


@project.command("create")
@click.option("--name", default=None, help="Project name")
@click.option("--folder", "folder_id", help="Folder UUID")
@click.option("--note", help="Project notes")
@click.option("--flag/--no-flag", default=None, help="Flag the project")
@click.option("--sequential/--parallel", default=None, help="Sequential or parallel")
@click.option("--due", "due_date", help="Due date (ISO)")
@click.option("--defer", "defer_date", help="Defer date (ISO)")
@click.pass_context
def create_project(ctx, name, folder_id, note, flag, sequential, due_date, defer_date):
    """Create a new project."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [name, folder_id, note, flag, sequential, due_date, defer_date])
        _run(ctx, "project.create", "createProject", {}, had_convenience_flags=had_flags)
    else:
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
        _run(ctx, "project.create", "createProject", params)


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
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [name, note, flag, sequential, status, due_date, defer_date])
        _run(ctx, "project.update", "setProjectProperties", {}, had_convenience_flags=had_flags)
    else:
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
        _run(ctx, "project.update", "setProjectProperties",
             {"projectId": project_id, "properties": properties})


@project.command("folders")
@click.pass_context
def list_folders(ctx):
    """List all folders."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "project.folders", "listFolders", {})
    else:
        _run(ctx, "project.folders", "listFolders", {})


# ── Inbox commands ─────────────────────────────────────────


@cli.group()
def inbox():
    """List and process inbox items."""
    pass


@inbox.command("list")
@click.option("--limit", type=int, help="Max items to return")
@click.option("--include-completed", is_flag=True, default=False, help="Include completed items")
@click.pass_context
def list_inbox(ctx, limit, include_completed):
    """List inbox items."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = limit is not None or include_completed
        _run(ctx, "inbox.list", "listInbox", {}, had_convenience_flags=had_flags)
    else:
        params = {}
        if limit:
            params["limit"] = limit
        if include_completed:
            params["includeCompleted"] = True
        _run(ctx, "inbox.list", "listInbox", params)


@inbox.command()
@click.argument("task_id")
@click.option("--project", "project_id", help="Move to project UUID")
@click.option("--tag", "tag_ids", multiple=True, help="Assign tag UUID (repeatable)")
@click.option("--flag/--no-flag", default=None, help="Flag the item")
@click.option("--due", "due_date", help="Set due date")
@click.option("--defer", "defer_date", help="Set defer date")
@click.pass_context
def process(ctx, task_id, project_id, tag_ids, flag, due_date, defer_date):
    """Process an inbox item (assign project, tags, dates)."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [project_id, flag, due_date, defer_date]) or bool(tag_ids)
        _run(ctx, "inbox.process", "processInboxItem", {}, had_convenience_flags=had_flags)
    else:
        params = {"taskId": task_id}
        if project_id:
            params["projectId"] = project_id
        if tag_ids:
            params["tagIds"] = list(tag_ids)
        if flag is not None:
            params["flagged"] = flag
        if due_date:
            params["dueDate"] = due_date
        if defer_date:
            params["deferDate"] = defer_date
        _run(ctx, "inbox.process", "processInboxItem", params)


# ── Tags commands ──────────────────────────────────────────


@cli.group()
def tags():
    """List, create, rename, and delete tags."""
    pass


@tags.command("list")
@click.pass_context
def list_tags(ctx):
    """List all tags."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "tags.list", "listTags", {})
    else:
        _run(ctx, "tags.list", "listTags", {})


@tags.command()
@click.option("--name", default=None, help="Tag name")
@click.option("--parent", "parent_tag_id", help="Parent tag UUID for nesting")
@click.pass_context
def create(ctx, name, parent_tag_id):
    """Create a new tag."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [name, parent_tag_id])
        _run(ctx, "tags.create", "createTag", {}, had_convenience_flags=had_flags)
    else:
        params = {"name": name}
        if parent_tag_id:
            params["parentTagId"] = parent_tag_id
        _run(ctx, "tags.create", "createTag", params)


@tags.command()
@click.argument("tag_id")
@click.option("--name", default=None, help="New tag name")
@click.pass_context
def rename(ctx, tag_id, name):
    """Rename a tag."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = name is not None
        _run(ctx, "tags.rename", "updateTag", {}, had_convenience_flags=had_flags)
    else:
        _run(ctx, "tags.rename", "updateTag", {"tagId": tag_id, "name": name})


@tags.command()
@click.argument("tag_id")
@click.option("--force", is_flag=True, help="Delete even if tasks use this tag")
@click.pass_context
def delete(ctx, tag_id, force):
    """Delete a tag."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = force
        _run(ctx, "tags.delete", "deleteTag", {}, had_convenience_flags=had_flags)
    else:
        params = {"tagId": tag_id}
        if force:
            params["force"] = True
        _run(ctx, "tags.delete", "deleteTag", params)
