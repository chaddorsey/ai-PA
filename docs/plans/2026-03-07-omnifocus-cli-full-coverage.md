# OmniFocus CLI Full Plugin Coverage — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the OmniFocus CLI from 17 methods to full coverage of the 87-method plugin, organized into prioritized phases.

**Architecture:** Each new method gets a schema entry, a CLI subcommand (with `--body` + convenience flags), and tests. The existing patterns (`_run` helper, schema validation, field masks) handle everything — no new infrastructure needed.

**Tech Stack:** Python 3.11+, Click 8.x, pytest 8.x, Poetry

**Working directory:** `/Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli/`

---

## Phase 1: Core Gaps (High-value methods missing from daily use)

These are methods the old MCP exposed that the CLI doesn't yet cover.

### Task 1: Task Delete + Move

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Modify: `tests/test_cli_task.py`

**New schema entries:**

```python
"task.delete": {
    "method": "deleteTask",
    "description": "Delete a task",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Task ID to delete"},
    },
},
"task.move": {
    "method": "moveTask",
    "description": "Move a task to a different project or inbox",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Task ID to move"},
        "targetProjectId": {"type": "string", "required": False, "description": "Destination project ID (null for inbox)"},
        "parentTaskId": {"type": "string", "required": False, "description": "Make subtask of this task ID"},
        "position": {"type": "integer", "required": False, "description": "Position within target (0-indexed)"},
    },
},
```

**New CLI commands:**

```python
@task.command("delete")
@click.argument("task_id")
@click.pass_context
def task_delete(ctx, task_id):
    """Delete a task."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.delete", "deleteTask", {})
    else:
        _run(ctx, "task.delete", "deleteTask", {"taskId": task_id})


@task.command("move")
@click.argument("task_id")
@click.option("--project", "target_project_id", default=None, help="Destination project ID")
@click.option("--parent", "parent_task_id", default=None, help="Parent task ID (make subtask)")
@click.option("--position", type=int, default=None, help="Position within target (0-indexed)")
@click.pass_context
def task_move(ctx, task_id, target_project_id, parent_task_id, position):
    """Move a task to a different project or make it a subtask."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [target_project_id, parent_task_id, position])
        _run(ctx, "task.move", "moveTask", {}, had_convenience_flags=had_flags)
    else:
        params = {"taskId": task_id}
        if target_project_id is not None:
            params["targetProjectId"] = target_project_id
        if parent_task_id is not None:
            params["parentTaskId"] = parent_task_id
        if position is not None:
            params["position"] = position
        _run(ctx, "task.move", "moveTask", params)
```

**Step 1: Write failing tests**

```python
# Add to tests/test_cli_task.py

@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_delete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "delete", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("deleteTask", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_move_to_project(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "move", "t-1", "--project", "p-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["targetProjectId"] == "p-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_move_as_subtask(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "move", "t-1", "--parent", "t-2"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["parentTaskId"] == "t-2"
```

**Step 2:** Run tests to verify they fail
**Step 3:** Add schema entries + CLI commands
**Step 4:** Run tests to verify they pass
**Step 5:** Update `test_schema.py` — add `task.delete` and `task.move` to `test_list_schemas_returns_all_keys`
**Step 6:** Run full suite: `poetry run pytest -v -m "not integration"`
**Step 7:** Commit: `feat(omnifocus-cli): add task delete and move commands`

---

### Task 2: Task Hierarchy (subtasks)

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Create: `tests/test_cli_hierarchy.py`

**New schema entries:**

```python
"task.subtasks": {
    "method": "getTaskSubtasks",
    "description": "Get subtasks of a task",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Parent task ID"},
    },
},
"task.add-subtask": {
    "method": "createSubtask",
    "description": "Create a subtask under a parent task",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Parent task ID"},
        "name": {"type": "string", "required": True, "description": "Subtask name"},
        "note": {"type": "string", "required": False, "description": "Subtask note"},
        "flagged": {"type": "boolean", "required": False, "description": "Whether the subtask is flagged"},
        "dueDate": {"type": "string", "required": False, "description": "Due date (ISO 8601)"},
        "deferDate": {"type": "string", "required": False, "description": "Defer date (ISO 8601)"},
        "estimatedMinutes": {"type": "integer", "required": False, "description": "Duration in minutes"},
        "tagIds": {"type": "array[string]", "required": False, "description": "Tag IDs to apply"},
    },
},
"task.hierarchy": {
    "method": "getTaskHierarchy",
    "description": "Get full task hierarchy tree",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Root task ID"},
    },
},
"task.flatten": {
    "method": "flattenTaskHierarchy",
    "description": "Flatten a task hierarchy (promote subtasks)",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Parent task ID to flatten"},
    },
},
```

**New CLI commands** under the existing `task` group:

```python
@task.command("subtasks")
@click.argument("task_id")
@click.pass_context
def task_subtasks(ctx, task_id):
    """Get subtasks of a task."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.subtasks", "getTaskSubtasks", {})
    else:
        _run(ctx, "task.subtasks", "getTaskSubtasks", {"taskId": task_id})


@task.command("add-subtask")
@click.argument("task_id")
@click.option("--name", default=None, help="Subtask name")
@click.option("--note", default=None, help="Subtask note")
@click.option("--flag/--no-flag", "flagged", default=None)
@click.option("--due", "due_date", default=None, help="Due date (ISO)")
@click.option("--defer", "defer_date", default=None, help="Defer date (ISO)")
@click.option("--duration", "estimated_minutes", type=int, default=None)
@click.option("--tag", "tag_ids", multiple=True, help="Tag ID (repeatable)")
@click.pass_context
def task_add_subtask(ctx, task_id, name, note, flagged, due_date, defer_date,
                     estimated_minutes, tag_ids):
    """Create a subtask under a parent task."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [
            name, note, flagged, due_date, defer_date, estimated_minutes,
        ]) or bool(tag_ids)
        _run(ctx, "task.add-subtask", "createSubtask", {}, had_convenience_flags=had_flags)
    else:
        params = {
            "taskId": task_id,
            "name": name,
            "note": note,
            "flagged": flagged,
            "dueDate": due_date,
            "deferDate": defer_date,
            "estimatedMinutes": estimated_minutes,
            "tagIds": list(tag_ids) if tag_ids else None,
        }
        cleaned = {k: v for k, v in params.items() if v is not None}
        _run(ctx, "task.add-subtask", "createSubtask", cleaned)


@task.command("hierarchy")
@click.argument("task_id")
@click.pass_context
def task_hierarchy(ctx, task_id):
    """Get full task hierarchy tree."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.hierarchy", "getTaskHierarchy", {})
    else:
        _run(ctx, "task.hierarchy", "getTaskHierarchy", {"taskId": task_id})


@task.command("flatten")
@click.argument("task_id")
@click.pass_context
def task_flatten(ctx, task_id):
    """Flatten a task hierarchy (promote subtasks to siblings)."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "task.flatten", "flattenTaskHierarchy", {})
    else:
        _run(ctx, "task.flatten", "flattenTaskHierarchy", {"taskId": task_id})
```

**Step 1: Write failing tests** in `tests/test_cli_hierarchy.py`

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_subtasks(mock_call):
    mock_call.return_value = [{"id": "st-1", "name": "Subtask A"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "subtasks", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTaskSubtasks", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_add_subtask(mock_call):
    mock_call.return_value = {"id": "st-new", "name": "Do sub-thing"}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "add-subtask", "t-1", "--name", "Do sub-thing"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["name"] == "Do sub-thing"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_hierarchy(mock_call):
    mock_call.return_value = {"id": "t-1", "children": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "hierarchy", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTaskHierarchy", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_flatten(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "flatten", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("flattenTaskHierarchy", {"taskId": "t-1"})
```

**Step 2:** Run tests — fail
**Step 3:** Add schema entries + CLI commands
**Step 4:** Run tests — pass
**Step 5:** Update `test_schema.py`
**Step 6:** Run full suite
**Step 7:** Commit: `feat(omnifocus-cli): add task hierarchy commands (subtasks, add-subtask, hierarchy, flatten)`

---

### Task 3: Folder CRUD

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Create: `tests/test_cli_folder.py`
- Modify: `letta_tools/omnifocus_folder.py` (update action list)

**New schema entries:**

```python
"folder.get": {
    "method": "getFolderById",
    "description": "Get details of a specific folder",
    "params": {
        "folderId": {"type": "string", "required": True, "description": "Folder ID to retrieve"},
    },
},
"folder.create": {
    "method": "createFolder",
    "description": "Create a new folder",
    "params": {
        "name": {"type": "string", "required": True, "description": "Folder name"},
        "parentFolderId": {"type": "string", "required": False, "description": "Parent folder ID for nesting"},
    },
},
"folder.delete": {
    "method": "deleteFolder",
    "description": "Delete a folder",
    "params": {
        "folderId": {"type": "string", "required": True, "description": "Folder ID to delete"},
    },
},
"folder.tree": {
    "method": "getFolderHierarchy",
    "description": "Get folder hierarchy tree",
    "params": {
        "folderId": {"type": "string", "required": False, "description": "Root folder ID (omit for entire library)"},
    },
},
```

**New CLI commands:**

```python
@folder.command("get")
@click.argument("folder_id")
@click.pass_context
def folder_get(ctx, folder_id):
    """Get folder details by ID."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "folder.get", "getFolderById", {})
    else:
        _run(ctx, "folder.get", "getFolderById", {"folderId": folder_id})


@folder.command("create")
@click.option("--name", default=None, help="Folder name")
@click.option("--parent", "parent_folder_id", default=None, help="Parent folder ID")
@click.pass_context
def folder_create(ctx, name, parent_folder_id):
    """Create a new folder."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [name, parent_folder_id])
        _run(ctx, "folder.create", "createFolder", {}, had_convenience_flags=had_flags)
    else:
        params = {"name": name}
        if parent_folder_id:
            params["parentFolderId"] = parent_folder_id
        _run(ctx, "folder.create", "createFolder", params)


@folder.command("delete")
@click.argument("folder_id")
@click.pass_context
def folder_delete(ctx, folder_id):
    """Delete a folder."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "folder.delete", "deleteFolder", {})
    else:
        _run(ctx, "folder.delete", "deleteFolder", {"folderId": folder_id})


@folder.command("tree")
@click.option("--root", "folder_id", default=None, help="Root folder ID (omit for entire library)")
@click.pass_context
def folder_tree(ctx, folder_id):
    """Get folder hierarchy tree."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "folder.tree", "getFolderHierarchy", {})
    else:
        params = {}
        if folder_id:
            params["folderId"] = folder_id
        _run(ctx, "folder.tree", "getFolderHierarchy", params)
```

**Step 1: Write failing tests** in `tests/test_cli_folder.py`

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_list(mock_call):
    mock_call.return_value = [{"id": "f-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listFolders", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_get(mock_call):
    mock_call.return_value = {"id": "f-1", "name": "Work", "projectCount": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "get", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderById", {"folderId": "f-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_create(mock_call):
    mock_call.return_value = {"id": "f-new", "name": "New Folder"}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "create", "--name", "New Folder"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createFolder", {"name": "New Folder"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_create_nested(mock_call):
    mock_call.return_value = {"id": "f-new"}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "create", "--name", "Sub", "--parent", "f-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["parentFolderId"] == "f-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_delete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "delete", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("deleteFolder", {"folderId": "f-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_tree(mock_call):
    mock_call.return_value = {"folders": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "folder", "tree"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderHierarchy", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_folder_tree_from_root(mock_call):
    mock_call.return_value = {"folders": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["folder", "tree", "--root", "f-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getFolderHierarchy", {"folderId": "f-1"})
```

**Step 2:** Run tests — fail
**Step 3:** Add schema entries + CLI commands
**Step 4:** Run tests — pass
**Step 5:** Update `test_schema.py`, update `letta_tools/omnifocus_folder.py` docstring (actions: list, get, create, delete, tree)
**Step 6:** Run full suite
**Step 7:** Commit: `feat(omnifocus-cli): add folder CRUD + tree commands`

---

### Task 4: Project Complete + Move + Convert

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Modify: `tests/test_cli_project.py`

**New schema entries:**

```python
"project.complete": {
    "method": "completeProject",
    "description": "Mark a project as completed",
    "params": {
        "projectId": {"type": "string", "required": True, "description": "Project ID to complete"},
    },
},
"project.move": {
    "method": "moveProject",
    "description": "Move a project to a different folder",
    "params": {
        "projectId": {"type": "string", "required": True, "description": "Project ID to move"},
        "folderId": {"type": "string", "required": True, "description": "Destination folder ID"},
        "position": {"type": "integer", "required": False, "description": "Position within folder"},
    },
},
"project.convert": {
    "method": "convertTaskToProject",
    "description": "Convert a task into a project",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Task ID to convert"},
        "folderId": {"type": "string", "required": False, "description": "Folder to place new project"},
    },
},
```

**New CLI commands** under the existing `project` group:

```python
@project.command("complete")
@click.argument("project_id")
@click.pass_context
def project_complete(ctx, project_id):
    """Mark a project as completed."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "project.complete", "completeProject", {})
    else:
        _run(ctx, "project.complete", "completeProject", {"projectId": project_id})


@project.command("move")
@click.argument("project_id")
@click.option("--folder", "folder_id", required=True, help="Destination folder ID")
@click.option("--position", type=int, default=None, help="Position within folder")
@click.pass_context
def project_move(ctx, project_id, folder_id, position):
    """Move a project to a different folder."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = any(v is not None for v in [folder_id, position])
        _run(ctx, "project.move", "moveProject", {}, had_convenience_flags=had_flags)
    else:
        params = {"projectId": project_id, "folderId": folder_id}
        if position is not None:
            params["position"] = position
        _run(ctx, "project.move", "moveProject", params)


@project.command("convert")
@click.argument("task_id")
@click.option("--folder", "folder_id", default=None, help="Folder for new project")
@click.pass_context
def project_convert(ctx, task_id, folder_id):
    """Convert a task into a project."""
    body = ctx.obj.get("body")
    if body is not None:
        had_flags = folder_id is not None
        _run(ctx, "project.convert", "convertTaskToProject", {}, had_convenience_flags=had_flags)
    else:
        params = {"taskId": task_id}
        if folder_id:
            params["folderId"] = folder_id
        _run(ctx, "project.convert", "convertTaskToProject", params)
```

**Step 1: Write tests**

```python
# Add to tests/test_cli_project.py

@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_complete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "complete", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("completeProject", {"projectId": "p-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_move(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "move", "p-1", "--folder", "f-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["projectId"] == "p-1"
    assert params["folderId"] == "f-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_convert_task(mock_call):
    mock_call.return_value = {"projectId": "p-new"}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "convert", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("convertTaskToProject", {"taskId": "t-1"})
```

**Step 2-7:** Same TDD cycle as above.
**Commit:** `feat(omnifocus-cli): add project complete, move, and convert commands`

---

### Task 5: Tags Get + Query Tasks by Tag

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Modify: `tests/test_cli_tags.py`

**New schema entries:**

```python
"tags.get": {
    "method": "getTagById",
    "description": "Get details of a specific tag",
    "params": {
        "tagId": {"type": "string", "required": True, "description": "Tag ID to retrieve"},
    },
},
```

**New CLI command:**

```python
@tags.command("get")
@click.argument("tag_id")
@click.pass_context
def tag_get(ctx, tag_id):
    """Get tag details by ID."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "tags.get", "getTagById", {})
    else:
        _run(ctx, "tags.get", "getTagById", {"tagId": tag_id})
```

Note: "query tasks by tag" is already covered by `task list --tag <id>` and `search --tag <id>`.

**Step 1: Write test**

```python
# Add to tests/test_cli_tags.py

@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_get(mock_call):
    mock_call.return_value = {"id": "t-1", "name": "urgent", "taskCount": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "tags", "get", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTagById", {"tagId": "t-1"})
```

**Step 2-7:** TDD cycle.
**Commit:** `feat(omnifocus-cli): add tags get command`

---

### Task 6: Inbox Context + Bulk Processing

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Modify: `tests/test_cli_inbox.py`

**New schema entries:**

```python
"inbox.context": {
    "method": "getInboxProcessingContext",
    "description": "Get context for processing an inbox item (available projects, tags)",
    "params": {
        "taskId": {"type": "string", "required": True, "description": "Inbox item ID"},
    },
},
"inbox.bulk": {
    "method": "executeBulkInboxProcessing",
    "description": "Process multiple inbox items at once",
    "params": {
        "operations": {"type": "array[object]", "required": True, "description": "Array of {taskId, projectId, action} objects"},
        "validateFirst": {"type": "boolean", "required": False, "description": "Validate before executing"},
        "continueOnError": {"type": "boolean", "required": False, "description": "Continue if an operation fails"},
    },
},
```

**New CLI commands:**

```python
@inbox.command("context")
@click.argument("task_id")
@click.pass_context
def inbox_context(ctx, task_id):
    """Get processing context for an inbox item."""
    body = ctx.obj.get("body")
    if body is not None:
        _run(ctx, "inbox.context", "getInboxProcessingContext", {})
    else:
        _run(ctx, "inbox.context", "getInboxProcessingContext", {"taskId": task_id})


@inbox.command("bulk")
@click.pass_context
def inbox_bulk(ctx):
    """Process multiple inbox items at once. Requires --body."""
    body = ctx.obj.get("body")
    if body is None:
        click.echo("Error: inbox bulk requires --body with operations array", err=True)
        ctx.exit(2)
        return
    _run(ctx, "inbox.bulk", "executeBulkInboxProcessing", {})
```

**Step 1: Write tests**

```python
# Add to tests/test_cli_inbox.py

@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_context(mock_call):
    mock_call.return_value = {"projects": [], "tags": []}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "inbox", "context", "i-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getInboxProcessingContext", {"taskId": "i-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_bulk(mock_call):
    mock_call.return_value = {"processed": 2}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--body", '{"operations": [{"taskId": "i-1", "projectId": "p-1"}]}',
        "inbox", "bulk",
    ])
    assert result.exit_code == 0


def test_inbox_bulk_requires_body():
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "bulk"])
    assert result.exit_code == 2
```

**Step 2-7:** TDD cycle.
**Commit:** `feat(omnifocus-cli): add inbox context and bulk commands`

---

### Task 7: Update Letta tools + schema test + CONTEXT.md

**Files:**
- Modify: `letta_tools/omnifocus_task.py` (update action list)
- Modify: `letta_tools/omnifocus_project.py` (update action list)
- Modify: `letta_tools/omnifocus_folder.py` (update action list)
- Modify: `letta_tools/omnifocus_inbox.py` (update action list)
- Modify: `letta_tools/omnifocus_tags.py` (update action list)
- Modify: `tests/test_schema.py` (add all new keys)
- Modify: `CONTEXT.md` (update command table)

Update each Letta tool's `action` docstring to reflect the new actions:

- `omnifocus_task`: `create, get, update, complete, delete, move, subtasks, add-subtask, hierarchy, flatten`
- `omnifocus_project`: `list, get, create, update, complete, move, convert`
- `omnifocus_folder`: `list, get, create, delete, tree`
- `omnifocus_inbox`: `list, process, context, bulk`
- `omnifocus_tags`: `list, get, create, rename, delete`

Update `test_schema.py` to assert all new schema keys exist.

Update `CONTEXT.md` command table.

**Commit:** `docs(omnifocus-cli): update Letta tools and CONTEXT.md for full Phase 1 coverage`

---

## Phase 2: Perspectives

### Task 8: Perspective Commands

**Files:**
- Modify: `src/omnifocus_cli/schema.py`
- Modify: `src/omnifocus_cli/cli.py`
- Create: `tests/test_cli_perspective.py`
- Create: `letta_tools/omnifocus_perspective.py`

**New schema entries:**

```python
"perspective.list": {
    "method": "listPerspectives",
    "description": "List all perspectives",
    "params": {
        "includeBuiltIn": {"type": "boolean", "required": False, "description": "Include built-in perspectives"},
    },
},
"perspective.get": {
    "method": "getPerspective",
    "description": "Get perspective details",
    "params": {
        "perspectiveId": {"type": "string", "required": True, "description": "Perspective ID"},
    },
},
"perspective.switch": {
    "method": "switchToPerspective",
    "description": "Switch OmniFocus to a perspective view",
    "params": {
        "perspectiveId": {"type": "string", "required": False, "description": "Perspective ID"},
        "perspectiveName": {"type": "string", "required": False, "description": "Perspective name (alternative to ID)"},
    },
},
```

**New CLI group:**

```python
@cli.group()
def perspective():
    """List, view, and switch perspectives."""
    pass


@perspective.command("list")
@click.option("--include-builtin/--no-builtin", default=True, help="Include built-in perspectives")
@click.pass_context
def perspective_list(ctx, include_builtin):
    ...


@perspective.command("get")
@click.argument("perspective_id")
@click.pass_context
def perspective_get(ctx, perspective_id):
    ...


@perspective.command("switch")
@click.option("--id", "perspective_id", default=None, help="Perspective ID")
@click.option("--name", "perspective_name", default=None, help="Perspective name")
@click.pass_context
def perspective_switch(ctx, perspective_id, perspective_name):
    ...
```

Follow same TDD pattern. Create `letta_tools/omnifocus_perspective.py`.

**Commit:** `feat(omnifocus-cli): add perspective commands (list, get, switch)`

---

## Phase 3: Reviews + Analytics + System

### Task 9: Review Commands

**New schema entries:** `review.list`, `review.mark`, `review.next`
**Plugin methods:** `listProjectsNeedingReview`, `markProjectReviewed`, `getProjectNextReview`

**New CLI group:**

```python
@cli.group()
def review():
    """Manage project reviews."""
```

Commands: `review list`, `review mark <project-id>`, `review next <project-id>`

Follow same TDD pattern. Create `letta_tools/omnifocus_review.py`.

**Commit:** `feat(omnifocus-cli): add review commands (list, mark, next)`

---

### Task 10: Analytics Commands

**New schema entries:** `analytics.health`, `analytics.workload`, `analytics.trends`, `analytics.summary`
**Plugin methods:** `getProjectHealth`, `getWorkloadSummary`, `getTrendInsights`, `getAnalyticsSummary`

**New CLI group:**

```python
@cli.group()
def analytics():
    """Project health, workload, and trend analytics."""
```

Commands: `analytics health`, `analytics workload`, `analytics trends`, `analytics summary`

Follow same TDD pattern. Create `letta_tools/omnifocus_analytics.py`.

**Commit:** `feat(omnifocus-cli): add analytics commands (health, workload, trends, summary)`

---

### Task 11: System Health

**New schema entry:** `system.health`
**Plugin method:** `health`

**New CLI command** (top-level, not a group):

```python
@cli.command("health")
@click.pass_context
def system_health(ctx):
    """Check OmniFocus plugin health status."""
    _run(ctx, "system.health", "health", {})
```

**Commit:** `feat(omnifocus-cli): add system health command`

---

## Phase 4: Transactions + Advanced Operations

### Task 12: Transaction Commands

**New schema entries:** `transaction.begin`, `transaction.execute`, `transaction.accept`, `transaction.rollback`, `transaction.history`
**Plugin methods:** `beginTransaction`, `executeTransactional`, `acceptTransaction`, `rollbackTransaction`, `getTransactionHistory`

**New CLI group:**

```python
@cli.group()
def transaction():
    """Batch operations with rollback support."""
```

Commands: `transaction begin`, `transaction execute` (--body only), `transaction accept <id>`, `transaction rollback <id>`, `transaction history`

Follow same TDD pattern. Create `letta_tools/omnifocus_transaction.py`.

**Commit:** `feat(omnifocus-cli): add transaction commands`

---

### Task 13: Group Type Commands (Task + Project)

**New schema entries:** `task.get-group-type`, `task.set-group-type`, `project.get-group-type`, `project.set-group-type`
**Plugin methods:** `getTaskGroupType`, `setTaskGroupType`, `getProjectGroupType`, `setProjectGroupType`

Add as subcommands under existing `task` and `project` groups:

```python
@task.command("group-type")        # get
@task.command("set-group-type")    # set sequential/parallel

@project.command("group-type")     # get
@project.command("set-group-type") # set sequential/parallel
```

**Commit:** `feat(omnifocus-cli): add group type commands for tasks and projects`

---

### Task 14: Validation + Automation + Remaining Methods

**New schema entries for validation:** `validate.transaction`, `validate.move`, `validate.create`
**New schema entries for automation:** `automation.suggest`, `automation.diagnose`, `automation.cleanup`

**New CLI groups:**

```python
@cli.group()
def validate():
    """Validate operations before executing."""

@cli.group()
def automation():
    """Automation helpers — suggestions, diagnostics, cleanup."""
```

Follow same TDD pattern.

**Commit:** `feat(omnifocus-cli): add validation and automation commands`

---

### Task 15: Final Cleanup + Full Test Suite

- Run full test suite
- Update `CONTEXT.md` with complete command table
- Update all Letta tool docstrings
- Verify `schema --list` shows all methods
- Run integration tests

**Commit:** `chore(omnifocus-cli): final cleanup for full plugin coverage`

---

## Summary

| Phase | Tasks | New Methods | Focus |
|-------|-------|-------------|-------|
| **1: Core Gaps** | 1-7 | ~16 | Daily-use CRUD: task delete/move, hierarchy, folder CRUD, project complete/move/convert, tags get, inbox context/bulk |
| **2: Perspectives** | 8 | 3 | Perspective list/get/switch |
| **3: Reviews + Analytics** | 9-11 | 8 | Reviews, analytics, system health |
| **4: Advanced** | 12-14 | ~14 | Transactions, group types, validation, automation |
| **Cleanup** | 15 | 0 | Final verification |

**Total new methods:** ~41 (17 existing + 41 new = 58 CLI methods)
**Remaining plugin-only methods:** ~29 (niche: hierarchy restructuring, nest-as-hierarchy, move-branch, completion behavior, project path, repetition rules, bulk hierarchy creation, perspective CRUD beyond list/get/switch)

These 29 are accessible via `--body` + the plugin method name even without dedicated CLI commands, since the bridge accepts any method string. A future task could add a `raw` command for direct method calls.
