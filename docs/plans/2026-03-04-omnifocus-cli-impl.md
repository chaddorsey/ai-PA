# OmniFocus CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI (`omnifocus-cli`) that replaces the OmniFocus MCP server, allowing Letta agents to call OmniFocus via subprocess instead of MCP protocol.

**Architecture:** Python Click CLI on the host calls `osascript` which invokes the existing `omnifocus-mcp.omnijs` plugin inside OmniFocus. Letta tools wrap CLI calls via `subprocess.run`. No Docker, no HTTP, no MCP protocol.

**Tech Stack:** Python 3.11+, Click, Poetry, pytest

**Design doc:** `docs/plans/2026-03-04-omnifocus-cli-design.md`

---

### Task 1: Project Scaffold

**Files:**
- Create: `omnifocus-cli/pyproject.toml`
- Create: `omnifocus-cli/src/omnifocus_cli/__init__.py`
- Create: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/__init__.py`

**Step 1: Create project directory**

```bash
mkdir -p omnifocus-cli/src/omnifocus_cli omnifocus-cli/tests
```

**Step 2: Write pyproject.toml**

```toml
[tool.poetry]
name = "omnifocus-cli"
version = "0.1.0"
description = "CLI for OmniFocus via Omni Automation plugin"
authors = ["ai-PA"]
packages = [{include = "omnifocus_cli", from = "src"}]

[tool.poetry.dependencies]
python = "^3.11"
click = "^8.1"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"

[tool.poetry.scripts]
omnifocus-cli = "omnifocus_cli.cli:cli"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Step 3: Write minimal CLI entry point**

`omnifocus-cli/src/omnifocus_cli/__init__.py`: empty file

`omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
import click


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, json_output):
    """OmniFocus CLI - manage tasks, projects, and tags."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
```

`omnifocus-cli/tests/__init__.py`: empty file

**Step 4: Install and verify**

```bash
cd omnifocus-cli && poetry install
poetry run omnifocus-cli --help
```

Expected: Help text showing `--json` option and no subcommands yet.

**Step 5: Commit**

```bash
git add omnifocus-cli/
git commit -m "feat(omnifocus-cli): scaffold project with Click entry point"
```

---

### Task 2: Bridge Module (osascript + base64)

**Files:**
- Create: `omnifocus-cli/src/omnifocus_cli/bridge.py`
- Create: `omnifocus-cli/tests/test_bridge.py`

**Step 1: Write the failing test**

`omnifocus-cli/tests/test_bridge.py`:

```python
import json
from omnifocus_cli.bridge import build_payload, build_applescript


def test_build_payload_creates_correct_json():
    result = build_payload("getTask", {"taskId": "abc-123"})
    parsed = json.loads(result)
    assert parsed == {"method": "getTask", "params": {"taskId": "abc-123"}}


def test_build_payload_empty_params():
    result = build_payload("listTags", {})
    parsed = json.loads(result)
    assert parsed == {"method": "listTags", "params": {}}


def test_build_payload_defaults_params_to_empty():
    result = build_payload("listTags")
    parsed = json.loads(result)
    assert parsed == {"method": "listTags", "params": {}}


def test_build_applescript_contains_base64():
    script = build_applescript("listTags", {})
    assert 'tell application "OmniFocus"' in script
    assert "evaluate javascript" in script
    assert "PlugIn.find" in script
    assert "omnifocus-mcp" in script


def test_build_applescript_roundtrip_decode():
    """Verify that the base64 payload in the script decodes to the original JSON."""
    import base64
    import re

    script = build_applescript("getTask", {"taskId": "test-id"})
    # Extract the base64 string from the script (it's between s=' and ')
    match = re.search(r"s='([A-Za-z0-9+/=]+)'", script)
    assert match, "Could not find base64 payload in script"
    decoded = base64.b64decode(match.group(1)).decode("utf-8")
    parsed = json.loads(decoded)
    assert parsed["method"] == "getTask"
    assert parsed["params"]["taskId"] == "test-id"
```

**Step 2: Run test to verify it fails**

```bash
cd omnifocus-cli && poetry run pytest tests/test_bridge.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'omnifocus_cli.bridge'`

**Step 3: Write bridge implementation**

`omnifocus-cli/src/omnifocus_cli/bridge.py`:

```python
import base64
import json
import subprocess
import tempfile
from pathlib import Path


def build_payload(method: str, params: dict | None = None) -> str:
    """Build the JSON payload for the OmniFocus plugin."""
    return json.dumps({"method": method, "params": params or {}})


def build_applescript(method: str, params: dict | None = None) -> str:
    """Build the AppleScript that calls the OmniFocus plugin via base64-encoded JSON."""
    payload = build_payload(method, params)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")

    # Inline base64 decoder in JS (matches omnifocus-mcp-letta/bridge.ts)
    return f"""tell application "OmniFocus"
  set _res to evaluate javascript "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='{b64}',r='';for(var i=0;i<s.length;){{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}var p=PlugIn.find('omnifocus-mcp');if(!p)throw new Error('Plugin not found');var lib=p.library('omnifocus-mcp');JSON.stringify(lib.request(r))"
end tell
return _res
"""


def call_omnifocus(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via osascript and return parsed JSON result.

    Returns the unwrapped result from the plugin (the value inside {"result": ...}).
    Raises RuntimeError on osascript failure or plugin error.
    """
    script = build_applescript(method, params)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".applescript", delete=False
    ) as f:
        f.write(script)
        script_path = Path(f.name)

    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"osascript failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        raw = result.stdout.strip()
        parsed = json.loads(raw)
        if "error" in parsed:
            raise RuntimeError(f"OmniFocus plugin error: {parsed['error']}")
        return parsed.get("result", parsed)
    finally:
        script_path.unlink(missing_ok=True)
```

**Step 4: Run tests to verify they pass**

```bash
cd omnifocus-cli && poetry run pytest tests/test_bridge.py -v
```

Expected: All 5 tests PASS (these are unit tests that don't need OmniFocus running).

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/bridge.py omnifocus-cli/tests/test_bridge.py
git commit -m "feat(omnifocus-cli): add osascript bridge with base64 encoding"
```

---

### Task 3: Output Formatting Module

**Files:**
- Create: `omnifocus-cli/src/omnifocus_cli/formatters.py`
- Create: `omnifocus-cli/tests/test_formatters.py`

**Step 1: Write the failing test**

`omnifocus-cli/tests/test_formatters.py`:

```python
import json
from click.testing import CliRunner
from omnifocus_cli.formatters import output_result, output_error


def test_output_result_json(capsys):
    data = {"id": "abc", "name": "Test Task"}
    output_result(data, json_output=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == data


def test_output_result_human_dict(capsys):
    data = {"id": "abc-123", "name": "Buy milk", "flagged": True}
    output_result(data, json_output=False)
    captured = capsys.readouterr()
    assert "abc-123" in captured.out
    assert "Buy milk" in captured.out


def test_output_result_human_list(capsys):
    data = [
        {"id": "1", "name": "Task A"},
        {"id": "2", "name": "Task B"},
    ]
    output_result(data, json_output=False)
    captured = capsys.readouterr()
    assert "Task A" in captured.out
    assert "Task B" in captured.out


def test_output_error_json(capsys):
    output_error("Something broke", json_output=True)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err)
    assert parsed["error"] == "Something broke"


def test_output_error_human(capsys):
    output_error("Something broke", json_output=False)
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Something broke" in captured.err
```

**Step 2: Run test to verify it fails**

```bash
cd omnifocus-cli && poetry run pytest tests/test_formatters.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write formatters implementation**

`omnifocus-cli/src/omnifocus_cli/formatters.py`:

```python
import json
import sys


def output_result(data, json_output: bool = False):
    """Print result to stdout in JSON or human-readable format."""
    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return

    if isinstance(data, list):
        for item in data:
            _print_item(item)
            print()
    elif isinstance(data, dict):
        _print_item(data)
    else:
        print(data)


def output_error(message: str, json_output: bool = False):
    """Print error to stderr in JSON or human-readable format."""
    if json_output:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def _print_item(item: dict):
    """Print a single dict item in human-readable key: value format."""
    for key, value in item.items():
        if value is None:
            continue
        if isinstance(value, list):
            print(f"  {key}: {', '.join(str(v) for v in value)}")
        else:
            print(f"  {key}: {value}")
```

**Step 4: Run tests to verify they pass**

```bash
cd omnifocus-cli && poetry run pytest tests/test_formatters.py -v
```

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/formatters.py omnifocus-cli/tests/test_formatters.py
git commit -m "feat(omnifocus-cli): add JSON and human-readable output formatters"
```

---

### Task 4: Task Commands

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/test_cli_task.py`

This is the largest command group. It maps to plugin methods: `createTask`, `getTask`, `updateTask`, `completeTask`, `listRemaining`, `queryTasks`.

**Step 1: Write the failing tests**

`omnifocus-cli/tests/test_cli_task.py`:

```python
"""Tests for the task command group.

These test CLI argument parsing and bridge call construction.
They mock call_omnifocus since we can't run OmniFocus in CI.
"""
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_create_minimal(mock_call):
    mock_call.return_value = {"id": "new-1", "name": "Buy milk"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "task", "create", "--name", "Buy milk"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with(
        "createTask", {"name": "Buy milk"}
    )


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_create_full(mock_call):
    mock_call.return_value = {"id": "new-2", "name": "Write report"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--name", "Write report",
        "--project", "proj-1",
        "--note", "Include charts",
        "--flag",
        "--due", "2026-03-10",
        "--defer", "2026-03-08",
        "--duration", "60",
        "--tag", "tag-1",
        "--tag", "tag-2",
    ])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "createTask"
    params = call_args[1]
    assert params["name"] == "Write report"
    assert params["projectId"] == "proj-1"
    assert params["note"] == "Include charts"
    assert params["flagged"] is True
    assert params["dueDate"] == "2026-03-10"
    assert params["deferDate"] == "2026-03-08"
    assert params["estimatedMinutes"] == 60
    assert params["tagIds"] == ["tag-1", "tag-2"]


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_get(mock_call):
    mock_call.return_value = {"id": "t-1", "name": "Test"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "task", "get", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getTask", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_complete(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "complete", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("completeTask", {"taskId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_update_flag_and_defer(mock_call):
    mock_call.return_value = {"id": "t-1", "name": "Updated", "flagged": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "update", "t-1",
        "--flag",
        "--defer", "2026-03-15",
        "--duration", "45",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "t-1"
    assert params["flagged"] is True
    assert params["deferDate"] == "2026-03-15"
    assert params["estimatedMinutes"] == 45


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_update_unflag(mock_call):
    mock_call.return_value = {"id": "t-1", "flagged": False}
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "update", "t-1", "--no-flag"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is False


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_list_by_project(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "Task A"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "task", "list", "--project", "proj-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_task_list_flagged(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "list", "--flagged"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is True
```

**Step 2: Run tests to verify they fail**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_task.py -v
```

Expected: FAIL — no `task` command group exists yet.

**Step 3: Implement task commands**

Replace `omnifocus-cli/src/omnifocus_cli/cli.py` with:

```python
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
    """Call OmniFocus and handle output/errors."""
    try:
        # Remove None values so the plugin uses its defaults
        clean_params = {k: v for k, v in params.items() if v is not None}
        result = call_omnifocus(method, clean_params)
        output_result(result, json_output=ctx.obj["json"])
    except RuntimeError as e:
        output_error(str(e), json_output=ctx.obj["json"])
        sys.exit(1)


# ── Task commands ──────────────────────────────────────────


@cli.group()
def task():
    """Create, read, update, complete, and list tasks."""
    pass


@task.command()
@click.option("--name", required=True, help="Task name")
@click.option("--project", "project_id", help="Project UUID")
@click.option("--note", help="Task notes")
@click.option("--flag/--no-flag", default=None, help="Flag the task")
@click.option("--due", "due_date", help="Due date (ISO format or natural)")
@click.option("--defer", "defer_date", help="Defer/start date")
@click.option("--planned", "planned_date", help="Planned date (Forecast view)")
@click.option("--duration", "estimated_minutes", type=int, help="Estimated minutes")
@click.option("--tag", "tag_ids", multiple=True, help="Tag UUID (repeatable)")
@click.pass_context
def create(ctx, name, project_id, note, flag, due_date, defer_date, planned_date,
           estimated_minutes, tag_ids):
    """Create a new task."""
    params = {"name": name}
    if project_id:
        params["projectId"] = project_id
    if note:
        params["note"] = note
    if flag is not None:
        params["flagged"] = flag
    if due_date:
        params["dueDate"] = due_date
    if defer_date:
        params["deferDate"] = defer_date
    if planned_date:
        params["plannedDate"] = planned_date
    if estimated_minutes is not None:
        params["estimatedMinutes"] = estimated_minutes
    if tag_ids:
        params["tagIds"] = list(tag_ids)
    _run(ctx, "createTask", params)


@task.command()
@click.argument("task_id")
@click.pass_context
def get(ctx, task_id):
    """Get task details by ID."""
    _run(ctx, "getTask", {"taskId": task_id})


@task.command()
@click.argument("task_id")
@click.option("--name", help="New task name")
@click.option("--note", help="New task notes")
@click.option("--flag/--no-flag", default=None, help="Set/unset flag")
@click.option("--due", "due_date", help="Due date (ISO format)")
@click.option("--defer", "defer_date", help="Defer/start date")
@click.option("--planned", "planned_date", help="Planned date")
@click.option("--duration", "estimated_minutes", type=int, help="Estimated minutes")
@click.option("--project", "project_id", help="Move to project UUID")
@click.option("--tag", "tag_ids", multiple=True, help="Replace tags (repeatable UUIDs)")
@click.pass_context
def update(ctx, task_id, name, note, flag, due_date, defer_date, planned_date,
           estimated_minutes, project_id, tag_ids):
    """Update a task by ID."""
    params = {"taskId": task_id}
    if name is not None:
        params["name"] = name
    if note is not None:
        params["note"] = note
    if flag is not None:
        params["flagged"] = flag
    if due_date:
        params["dueDate"] = due_date
    if defer_date:
        params["deferDate"] = defer_date
    if planned_date:
        params["plannedDate"] = planned_date
    if estimated_minutes is not None:
        params["estimatedMinutes"] = estimated_minutes
    if project_id:
        params["projectId"] = project_id
    if tag_ids:
        params["tagIds"] = list(tag_ids)
    _run(ctx, "updateTask", params)


@task.command()
@click.argument("task_id")
@click.pass_context
def complete(ctx, task_id):
    """Mark a task as complete."""
    _run(ctx, "completeTask", {"taskId": task_id})


@task.command("list")
@click.option("--project", "project_id", help="Filter by project UUID")
@click.option("--tag", "tag_id", help="Filter by tag UUID")
@click.option("--flagged", is_flag=True, default=None, help="Only flagged tasks")
@click.option("--include-completed", is_flag=True, default=False, help="Include completed tasks")
@click.pass_context
def list_tasks(ctx, project_id, tag_id, flagged, include_completed):
    """List tasks with optional filters."""
    params = {}
    if project_id:
        params["projectId"] = project_id
    if tag_id:
        params["tagId"] = tag_id
    if flagged:
        params["flagged"] = True
    if include_completed:
        params["includeCompleted"] = True
    _run(ctx, "queryTasks", params)
```

**Step 4: Run tests to verify they pass**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_task.py -v
```

Expected: All 9 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/cli.py omnifocus-cli/tests/test_cli_task.py
git commit -m "feat(omnifocus-cli): add task command group (create/get/update/complete/list)"
```

---

### Task 5: Search Command

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/test_cli_search.py`

Maps to plugin methods: `searchTasks` (text search) and `queryTasks` (filter-only queries).

**Step 1: Write the failing tests**

`omnifocus-cli/tests/test_cli_search.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_text(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "Dentist appt"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "--text", "dentist"])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "searchTasks"
    assert call_args[1]["query"] == "dentist"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_due_before(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--due-before", "2026-03-10"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["dueBefore"] == "2026-03-10"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_flagged_in_project(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, [
        "search", "--flagged", "--project", "proj-1"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["flagged"] is True
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_by_tag(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--tag", "tag-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["tagId"] == "tag-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_available_only(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--available"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["isAvailable"] is True


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_defer_range(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, [
        "search", "--defer-after", "2026-03-01", "--defer-before", "2026-03-31"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["deferAfter"] == "2026-03-01"
    assert params["deferBefore"] == "2026-03-31"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_search_requires_at_least_one_filter(mock_call):
    runner = CliRunner()
    result = runner.invoke(cli, ["search"])
    assert result.exit_code != 0
    assert "at least one filter" in result.output.lower() or result.exit_code == 2
```

**Step 2: Run tests to verify they fail**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_search.py -v
```

Expected: FAIL — no `search` command.

**Step 3: Add search command to cli.py**

Append to `omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
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
    # Use searchTasks when text query is provided, queryTasks for filter-only
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
```

**Step 4: Run tests**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_search.py -v
```

Expected: All 7 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/cli.py omnifocus-cli/tests/test_cli_search.py
git commit -m "feat(omnifocus-cli): add search command with text and filter queries"
```

---

### Task 6: Project Commands

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/test_cli_project.py`

Maps to: `listProjects`, `getProjectById`, `createProject`, `setProjectProperties` (for update), `listFolders`.

**Step 1: Write the failing tests**

`omnifocus-cli/tests/test_cli_project.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list(mock_call):
    mock_call.return_value = [{"id": "p-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listProjects", {"completion": "active"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_all(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--all"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["completion"] == "all"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_by_folder(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--folder", "f-1"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["folderId"] == "f-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_get(mock_call):
    mock_call.return_value = {"id": "p-1", "name": "Work", "taskCount": 5}
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "get", "p-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("getProjectById", {"projectId": "p-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_create_minimal(mock_call):
    mock_call.return_value = {"projectId": "p-new", "projectName": "New Project"}
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "create", "--name", "New Project"])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "createProject"
    assert call_args[1]["name"] == "New Project"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_create_full(mock_call):
    mock_call.return_value = {"projectId": "p-new"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "project", "create",
        "--name", "Q2 Goals",
        "--folder", "f-1",
        "--sequential",
        "--due", "2026-06-30",
        "--defer", "2026-04-01",
        "--flag",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["name"] == "Q2 Goals"
    assert params["folderId"] == "f-1"
    assert params["properties"]["sequential"] is True
    assert params["properties"]["dueDate"] == "2026-06-30"
    assert params["properties"]["deferDate"] == "2026-04-01"
    assert params["properties"]["flagged"] is True


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_update_status(mock_call):
    mock_call.return_value = {"updated": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "project", "update", "p-1", "--status", "onHold"
    ])
    assert result.exit_code == 0
    call_args = mock_call.call_args[0]
    assert call_args[0] == "setProjectProperties"
    assert call_args[1]["projectId"] == "p-1"
    assert call_args[1]["properties"]["status"] == "onHold"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_project_list_folders(mock_call):
    mock_call.return_value = [{"id": "f-1", "name": "Work"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "project", "folders"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listFolders", {})
```

**Step 2: Run tests to verify they fail**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_project.py -v
```

Expected: FAIL — no `project` command group.

**Step 3: Add project commands to cli.py**

Append to `omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
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


@project.command()
@click.argument("project_id")
@click.pass_context
def get(ctx, project_id):
    """Get project details by ID."""
    _run(ctx, "getProjectById", {"projectId": project_id})


@project.command()
@click.option("--name", required=True, help="Project name")
@click.option("--folder", "folder_id", help="Folder UUID")
@click.option("--note", help="Project notes")
@click.option("--flag/--no-flag", default=None, help="Flag the project")
@click.option("--sequential/--parallel", default=None, help="Sequential or parallel")
@click.option("--due", "due_date", help="Due date (ISO)")
@click.option("--defer", "defer_date", help="Defer date (ISO)")
@click.pass_context
def create(ctx, name, folder_id, note, flag, sequential, due_date, defer_date):
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


@project.command()
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
def update(ctx, project_id, name, note, flag, sequential, status, due_date, defer_date):
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
```

**Step 4: Run tests**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_project.py -v
```

Expected: All 8 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/cli.py omnifocus-cli/tests/test_cli_project.py
git commit -m "feat(omnifocus-cli): add project command group (list/get/create/update/folders)"
```

---

### Task 7: Inbox Commands

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/test_cli_inbox.py`

Maps to: `listInbox`, `processInboxItem`.

**Step 1: Write the failing tests**

`omnifocus-cli/tests/test_cli_inbox.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_list(mock_call):
    mock_call.return_value = [{"id": "i-1", "name": "Random thought"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inbox", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listInbox", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_list_with_limit(mock_call):
    mock_call.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "list", "--limit", "5"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["limit"] == 5


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_process_to_project(mock_call):
    mock_call.return_value = {"success": True, "operations": ["assign_project"]}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "inbox", "process", "i-1", "--project", "proj-1"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["taskId"] == "i-1"
    assert params["projectId"] == "proj-1"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_inbox_process_with_tags(mock_call):
    mock_call.return_value = {"success": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "inbox", "process", "i-1",
        "--project", "proj-1",
        "--tag", "tag-1",
        "--tag", "tag-2",
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["tagIds"] == ["tag-1", "tag-2"]
```

**Step 2: Run tests to verify they fail**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_inbox.py -v
```

**Step 3: Add inbox commands to cli.py**

Append to `omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
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
    params = {}
    if limit:
        params["limit"] = limit
    if include_completed:
        params["includeCompleted"] = True
    _run(ctx, "listInbox", params)


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
    _run(ctx, "processInboxItem", params)
```

**Step 4: Run tests**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_inbox.py -v
```

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/cli.py omnifocus-cli/tests/test_cli_inbox.py
git commit -m "feat(omnifocus-cli): add inbox command group (list/process)"
```

---

### Task 8: Tags Commands

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Create: `omnifocus-cli/tests/test_cli_tags.py`

Maps to: `listTags`, `createTag`, `updateTag`, `deleteTag`.

**Step 1: Write the failing tests**

`omnifocus-cli/tests/test_cli_tags.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_list(mock_call):
    mock_call.return_value = [{"id": "t-1", "name": "urgent"}]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "tags", "list"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("listTags", {})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_create(mock_call):
    mock_call.return_value = {"tagId": "t-new", "tagName": "ai-generated", "created": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "create", "--name", "ai-generated"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTag", {"name": "ai-generated"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_create_nested(mock_call):
    mock_call.return_value = {"tagId": "t-new", "created": True}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "tags", "create", "--name", "sub-tag", "--parent", "t-parent"
    ])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["parentTagId"] == "t-parent"


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_rename(mock_call):
    mock_call.return_value = {"tagId": "t-1", "updated": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "rename", "t-1", "--name", "new-name"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("updateTag", {"tagId": "t-1", "name": "new-name"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_delete(mock_call):
    mock_call.return_value = {"tagId": "t-1", "deleted": True}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "delete", "t-1"])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("deleteTag", {"tagId": "t-1"})


@patch("omnifocus_cli.cli.call_omnifocus")
def test_tags_delete_force(mock_call):
    mock_call.return_value = {"tagId": "t-1", "deleted": True, "tasksAffected": 3}
    runner = CliRunner()
    result = runner.invoke(cli, ["tags", "delete", "t-1", "--force"])
    assert result.exit_code == 0
    params = mock_call.call_args[0][1]
    assert params["force"] is True
```

**Step 2: Run tests to verify they fail**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_tags.py -v
```

**Step 3: Add tags commands to cli.py**

Append to `omnifocus-cli/src/omnifocus_cli/cli.py`:

```python
# ── Tags commands ──────────────────────────────────────────


@cli.group()
def tags():
    """List, create, rename, and delete tags."""
    pass


@tags.command("list")
@click.pass_context
def list_tags(ctx):
    """List all tags."""
    _run(ctx, "listTags", {})


@tags.command()
@click.option("--name", required=True, help="Tag name")
@click.option("--parent", "parent_tag_id", help="Parent tag UUID for nesting")
@click.pass_context
def create(ctx, name, parent_tag_id):
    """Create a new tag."""
    params = {"name": name}
    if parent_tag_id:
        params["parentTagId"] = parent_tag_id
    _run(ctx, "createTag", params)


@tags.command()
@click.argument("tag_id")
@click.option("--name", required=True, help="New tag name")
@click.pass_context
def rename(ctx, tag_id, name):
    """Rename a tag."""
    _run(ctx, "updateTag", {"tagId": tag_id, "name": name})


@tags.command()
@click.argument("tag_id")
@click.option("--force", is_flag=True, help="Delete even if tasks use this tag")
@click.pass_context
def delete(ctx, tag_id, force):
    """Delete a tag."""
    params = {"tagId": tag_id}
    if force:
        params["force"] = True
    _run(ctx, "deleteTag", params)
```

**Step 4: Run tests**

```bash
cd omnifocus-cli && poetry run pytest tests/test_cli_tags.py -v
```

Expected: All 6 tests PASS.

**Step 5: Commit**

```bash
git add omnifocus-cli/src/omnifocus_cli/cli.py omnifocus-cli/tests/test_cli_tags.py
git commit -m "feat(omnifocus-cli): add tags command group (list/create/rename/delete)"
```

---

### Task 9: Integration Smoke Test (requires OmniFocus running)

**Files:**
- Create: `omnifocus-cli/tests/test_integration.py`

**Step 1: Write integration test**

`omnifocus-cli/tests/test_integration.py`:

```python
"""Integration tests — require OmniFocus running on macOS.

Run with: poetry run pytest tests/test_integration.py -v -m integration
Skip in CI with: poetry run pytest -m "not integration"
"""
import json
import subprocess

import pytest


pytestmark = pytest.mark.integration


def run_cli(*args):
    """Run omnifocus-cli with --json and return parsed output."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli", "--json", *args],
        capture_output=True,
        text=True,
        cwd="/Volumes/main-drive/ai-PA/omnifocus-cli",
        timeout=30,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout)


def test_list_projects():
    projects = run_cli("project", "list")
    assert isinstance(projects, list)
    if projects:
        assert "id" in projects[0] or "projectId" in projects[0]


def test_list_tags():
    tags = run_cli("tags", "list")
    assert isinstance(tags, list)


def test_list_inbox():
    items = run_cli("inbox", "list")
    assert isinstance(items, list)


def test_search_flagged():
    results = run_cli("search", "--flagged")
    assert isinstance(results, list)


def test_task_lifecycle():
    """Create a task, verify it, complete it."""
    # Create
    created = run_cli("task", "create", "--name", "CLI Integration Test Task")
    task_id = created.get("id") or created.get("taskId")
    assert task_id, f"No task ID in response: {created}"

    # Get
    fetched = run_cli("task", "get", task_id)
    name = fetched.get("name") or fetched.get("taskName")
    assert name == "CLI Integration Test Task"

    # Complete
    completed = run_cli("task", "complete", task_id)
    assert completed.get("success") is True or "markComplete" not in str(completed)
```

**Step 2: Add pytest marker config**

Add to `omnifocus-cli/pyproject.toml` after `[build-system]`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires OmniFocus running on macOS",
]
```

**Step 3: Run unit tests (should still pass)**

```bash
cd omnifocus-cli && poetry run pytest -m "not integration" -v
```

Expected: All unit tests pass. Integration tests skipped.

**Step 4: Run integration tests (if OmniFocus is running)**

```bash
cd omnifocus-cli && poetry run pytest tests/test_integration.py -v -m integration
```

Expected: Tests pass if OmniFocus is running with the plugin installed.

**Step 5: Commit**

```bash
git add omnifocus-cli/tests/test_integration.py omnifocus-cli/pyproject.toml
git commit -m "test(omnifocus-cli): add integration smoke tests for OmniFocus"
```

---

### Task 10: Letta Tool Wrappers

**Files:**
- Create: `omnifocus-cli/letta_tools/omnifocus_task.py`
- Create: `omnifocus-cli/letta_tools/omnifocus_search.py`
- Create: `omnifocus-cli/letta_tools/omnifocus_project.py`
- Create: `omnifocus-cli/letta_tools/omnifocus_inbox.py`
- Create: `omnifocus-cli/letta_tools/omnifocus_tags.py`
- Create: `omnifocus-cli/letta_tools/__init__.py`

These follow the Letta custom tool pattern from `context/coding_custom_letta_tools.md`: all imports inside function, no nested defs, all params documented in docstring, try-except wrapper, returns `Dict[str, Any]`.

**Important:** These tools call `subprocess.run` to invoke the CLI. The CLI must be installed on the host where Letta's sandbox runs. The `omnifocus-cli` binary path is resolved at runtime.

**Step 1: Create letta_tools directory**

```bash
mkdir -p omnifocus-cli/letta_tools
touch omnifocus-cli/letta_tools/__init__.py
```

**Step 2: Write omnifocus_task tool**

`omnifocus-cli/letta_tools/omnifocus_task.py`:

```python
from typing import Dict, Any, Optional


def omnifocus_task(
    action: str,
    task_id: Optional[str] = None,
    name: Optional[str] = None,
    project_id: Optional[str] = None,
    note: Optional[str] = None,
    flagged: Optional[bool] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
    planned_date: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
    tag_ids: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus tasks: create, get, update, complete, or list.

    Args:
        action: Operation to perform. One of: create, get, update, complete, list (REQUIRED)
        task_id: Task UUID - required for get, update, complete
        name: Task name - required for create, optional for update
        project_id: Project UUID to assign task to (for create, update, or list filter)
        note: Task notes/description
        flagged: Whether task is flagged (true/false)
        due_date: Due date in ISO format (e.g. 2026-03-10)
        defer_date: Defer/start date in ISO format
        planned_date: Planned date for Forecast view in ISO format
        estimated_minutes: Estimated duration in minutes
        tag_ids: Comma-separated tag UUIDs to assign (for create/update), or single tag UUID (for list filter)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "create":
            cli_args.extend(["task", "create", "--name", name])
            if project_id:
                cli_args.extend(["--project", project_id])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])
            if planned_date:
                cli_args.extend(["--planned", planned_date])
            if estimated_minutes is not None:
                cli_args.extend(["--duration", str(estimated_minutes)])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])

        elif action == "get":
            cli_args.extend(["task", "get", task_id])

        elif action == "update":
            cli_args.extend(["task", "update", task_id])
            if name:
                cli_args.extend(["--name", name])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])
            if planned_date:
                cli_args.extend(["--planned", planned_date])
            if estimated_minutes is not None:
                cli_args.extend(["--duration", str(estimated_minutes)])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])

        elif action == "complete":
            cli_args.extend(["task", "complete", task_id])

        elif action == "list":
            cli_args.extend(["task", "list"])
            if project_id:
                cli_args.extend(["--project", project_id])
            if tag_ids:
                cli_args.extend(["--tag", tag_ids.split(",")[0].strip()])
            if flagged is True:
                cli_args.append("--flagged")

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: create, get, update, complete, list"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            return {"status": "error", "error_message": error_msg}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 3: Write omnifocus_search tool**

`omnifocus-cli/letta_tools/omnifocus_search.py`:

```python
from typing import Dict, Any, Optional


def omnifocus_search(
    text: Optional[str] = None,
    project_id: Optional[str] = None,
    tag_id: Optional[str] = None,
    flagged: Optional[bool] = None,
    available: Optional[bool] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    defer_before: Optional[str] = None,
    defer_after: Optional[str] = None,
    overdue: Optional[bool] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Search OmniFocus tasks with text and/or filters. At least one parameter required.

    Args:
        text: Text to search in task names and notes
        project_id: Filter by project UUID
        tag_id: Filter by tag UUID
        flagged: Only flagged tasks (true/false)
        available: Only available tasks - not blocked or deferred (true/false)
        due_before: Tasks due before this date (ISO format, e.g. 2026-03-10)
        due_after: Tasks due after this date (ISO format)
        defer_before: Tasks deferred before this date (ISO format)
        defer_after: Tasks deferred after this date (ISO format)
        overdue: Only overdue tasks (true/false)
        limit: Maximum number of results

    Returns:
        Dictionary with status and list of matching tasks.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json", "search"]

        if text:
            cli_args.extend(["--text", text])
        if project_id:
            cli_args.extend(["--project", project_id])
        if tag_id:
            cli_args.extend(["--tag", tag_id])
        if flagged is True:
            cli_args.append("--flagged")
        if available is True:
            cli_args.append("--available")
        if due_before:
            cli_args.extend(["--due-before", due_before])
        if due_after:
            cli_args.extend(["--due-after", due_after])
        if defer_before:
            cli_args.extend(["--defer-before", defer_before])
        if defer_after:
            cli_args.extend(["--defer-after", defer_after])
        if overdue is True:
            cli_args.append("--overdue")
        if limit is not None:
            cli_args.extend(["--limit", str(limit)])

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            return {"status": "error", "error_message": error_msg}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 4: Write omnifocus_project tool**

`omnifocus-cli/letta_tools/omnifocus_project.py`:

```python
from typing import Dict, Any, Optional


def omnifocus_project(
    action: str,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    folder_id: Optional[str] = None,
    note: Optional[str] = None,
    flagged: Optional[bool] = None,
    sequential: Optional[bool] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus projects: list, get, create, update, or list-folders.

    Args:
        action: Operation to perform. One of: list, get, create, update, folders (REQUIRED)
        project_id: Project UUID - required for get, update
        name: Project name - required for create, optional for update
        folder_id: Folder UUID - for create (target folder) or list (filter by folder)
        note: Project notes
        flagged: Whether project is flagged (true/false)
        sequential: True for sequential project, false for parallel
        status: Project status for update: active, onHold, completed, dropped
        due_date: Due date in ISO format (e.g. 2026-06-30)
        defer_date: Defer date in ISO format

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "list":
            cli_args.extend(["project", "list"])
            if folder_id:
                cli_args.extend(["--folder", folder_id])

        elif action == "get":
            cli_args.extend(["project", "get", project_id])

        elif action == "create":
            cli_args.extend(["project", "create", "--name", name])
            if folder_id:
                cli_args.extend(["--folder", folder_id])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            if sequential is True:
                cli_args.append("--sequential")
            elif sequential is False:
                cli_args.append("--parallel")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        elif action == "update":
            cli_args.extend(["project", "update", project_id])
            if name:
                cli_args.extend(["--name", name])
            if note:
                cli_args.extend(["--note", note])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if sequential is True:
                cli_args.append("--sequential")
            elif sequential is False:
                cli_args.append("--parallel")
            if status:
                cli_args.extend(["--status", status])
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        elif action == "folders":
            cli_args.extend(["project", "folders"])

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: list, get, create, update, folders"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 5: Write omnifocus_inbox tool**

`omnifocus-cli/letta_tools/omnifocus_inbox.py`:

```python
from typing import Dict, Any, Optional


def omnifocus_inbox(
    action: str,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    tag_ids: Optional[str] = None,
    flagged: Optional[bool] = None,
    due_date: Optional[str] = None,
    defer_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Manage OmniFocus inbox: list items or process them into projects.

    Args:
        action: Operation to perform. One of: list, process (REQUIRED)
        task_id: Inbox item UUID - required for process
        project_id: Project UUID to move item to (for process)
        tag_ids: Comma-separated tag UUIDs to assign (for process)
        flagged: Whether to flag the item (true/false, for process)
        due_date: Due date in ISO format (for process)
        defer_date: Defer date in ISO format (for process)
        limit: Max items to return (for list)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "--json"]

        if action == "list":
            cli_args.extend(["inbox", "list"])
            if limit is not None:
                cli_args.extend(["--limit", str(limit)])

        elif action == "process":
            cli_args.extend(["inbox", "process", task_id])
            if project_id:
                cli_args.extend(["--project", project_id])
            if tag_ids:
                for tid in tag_ids.split(","):
                    cli_args.extend(["--tag", tid.strip()])
            if flagged is True:
                cli_args.append("--flag")
            elif flagged is False:
                cli_args.append("--no-flag")
            if due_date:
                cli_args.extend(["--due", due_date])
            if defer_date:
                cli_args.extend(["--defer", defer_date])

        else:
            return {"status": "error", "error_message": f"Unknown action: {action}. Use: list, process"}

        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip()}

        parsed = json.loads(result.stdout)
        return {"status": "ok", "result": parsed}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 6: Write omnifocus_tags tool**

`omnifocus-cli/letta_tools/omnifocus_tags.py`:

```python
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
```

**Step 7: Commit**

```bash
git add omnifocus-cli/letta_tools/
git commit -m "feat(omnifocus-cli): add 5 Letta tool wrappers for CLI"
```

---

### Task 11: Letta Tool Registration Script

**Files:**
- Create: `omnifocus-cli/register_letta_tools.py`

This script registers the 5 Letta tools with the Letta server, following the pattern in `letta/register_omnifocus_mcp_tools.py`.

**Step 1: Write registration script**

`omnifocus-cli/register_letta_tools.py`:

```python
"""Register omnifocus-cli Letta tools with the Letta server.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_letta_tools.py [--agent-id <id>]

Reads each tool file from letta_tools/, registers it, and optionally attaches to an agent.
"""
import argparse
import inspect
import importlib.util
import sys
from pathlib import Path

TOOL_FILES = [
    "letta_tools/omnifocus_task.py",
    "letta_tools/omnifocus_search.py",
    "letta_tools/omnifocus_project.py",
    "letta_tools/omnifocus_inbox.py",
    "letta_tools/omnifocus_tags.py",
]


def load_function_from_file(filepath: str):
    """Load the first function defined in a file."""
    spec = importlib.util.spec_from_file_location("mod", filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if not name.startswith("_"):
            return name, inspect.getsource(obj)
    raise ValueError(f"No public function found in {filepath}")


def main():
    import os
    import requests

    parser = argparse.ArgumentParser(description="Register omnifocus-cli tools with Letta")
    parser.add_argument("--agent-id", help="Agent ID to attach tools to")
    args = parser.parse_args()

    base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    tools_dir = Path(__file__).parent

    registered_ids = []

    for rel_path in TOOL_FILES:
        filepath = tools_dir / rel_path
        func_name, source_code = load_function_from_file(str(filepath))

        # Check if tool already exists
        existing = requests.get(f"{base_url}/v1/tools", params={"limit": 100})
        existing.raise_for_status()
        existing_tool = next(
            (t for t in existing.json() if t["name"] == func_name), None
        )

        if existing_tool:
            # Update existing tool
            resp = requests.patch(
                f"{base_url}/v1/tools/{existing_tool['id']}",
                json={"source_code": source_code},
            )
            resp.raise_for_status()
            tool_id = existing_tool["id"]
            print(f"  Updated: {func_name} ({tool_id})")
        else:
            # Create new tool
            resp = requests.post(
                f"{base_url}/v1/tools",
                json={"source_code": source_code},
            )
            resp.raise_for_status()
            tool_id = resp.json()["id"]
            print(f"  Created: {func_name} ({tool_id})")

        registered_ids.append(tool_id)

    if args.agent_id:
        print(f"\nAttaching {len(registered_ids)} tools to agent {args.agent_id}...")
        for tool_id in registered_ids:
            resp = requests.patch(
                f"{base_url}/v1/agents/{args.agent_id}",
                json={"tool_ids": registered_ids},
            )
            resp.raise_for_status()
        print("  Done.")

    print(f"\n{len(registered_ids)} tools registered successfully.")


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add omnifocus-cli/register_letta_tools.py
git commit -m "feat(omnifocus-cli): add Letta tool registration script"
```

---

### Task 12: Install CLI and Run Full Test Suite

**Step 1: Install CLI globally (pip install --editable)**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli && pip install -e .
```

This makes `omnifocus-cli` available in the system PATH.

**Step 2: Verify CLI is available**

```bash
omnifocus-cli --help
omnifocus-cli task --help
omnifocus-cli search --help
omnifocus-cli project --help
omnifocus-cli inbox --help
omnifocus-cli tags --help
```

Expected: All help text displays correctly.

**Step 3: Run all unit tests**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli && poetry run pytest -m "not integration" -v
```

Expected: All unit tests pass (bridge: 5, formatters: 5, task: 9, search: 7, project: 8, inbox: 4, tags: 6 = ~44 tests).

**Step 4: Run integration tests**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-cli && poetry run pytest tests/test_integration.py -v -m integration
```

Expected: Passes if OmniFocus is running with the plugin installed.

**Step 5: Final commit if any fixes were needed**

```bash
git add -A && git commit -m "fix(omnifocus-cli): integration test fixes"
```

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Project scaffold (Poetry + Click) | Manual verify |
| 2 | Bridge module (osascript + base64) | 5 unit tests |
| 3 | Output formatters (JSON + human) | 5 unit tests |
| 4 | Task commands (create/get/update/complete/list) | 9 unit tests |
| 5 | Search command (text + filters) | 7 unit tests |
| 6 | Project commands (list/get/create/update/folders) | 8 unit tests |
| 7 | Inbox commands (list/process) | 4 unit tests |
| 8 | Tags commands (list/create/rename/delete) | 6 unit tests |
| 9 | Integration smoke tests | 5 integration tests |
| 10 | Letta tool wrappers (5 tools) | — |
| 11 | Letta registration script | — |
| 12 | Install + full test run | All tests |

**Total: ~44 unit tests + 5 integration tests across 12 tasks.**
